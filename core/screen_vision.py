"""
屏幕视觉理解模块 - 截图 + Vision 模型分析界面元素
"""

import asyncio
import base64
import io
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.llm_client import VolcengineLLMClient
from utils.logger import get_logger

_logger = get_logger(__name__)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SCREENSHOT_DIR = _PROJECT_ROOT / "data" / "screenshots"


class ScreenElement:
    """屏幕元素信息（含像素坐标）"""

    def __init__(
        self,
        name: str,
        element_type: str,
        x: int,
        y: int,
        width: int,
        height: int,
        confidence: float = 0.9,
        text: str = "",
    ):
        self.name = name
        self.element_type = element_type
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.confidence = confidence
        self.text = text

    @property
    def center(self) -> Tuple[int, int]:
        return (self.x + self.width // 2, self.y + self.height // 2)


class ScreenVision:
    """截取屏幕并调用 Vision 模型理解界面"""

    VISION_SYSTEM_PROMPT = """
你是一个屏幕界面分析专家。请分析用户提供的屏幕截图，完成以下任务：

1. 识别 page_type：login / search_list / job_detail / chat / message_list / other
2. 识别可交互元素（按钮、输入框、链接、岗位卡片等），每个元素包含：
   name, type, x, y, width, height, text（可选）, confidence（0-1）
3. 提取 screen_text：页面上所有可见文字（尽量完整）

请严格输出 JSON 对象，格式：
{
  "page_type": "search_list",
  "elements": [
    {"name": "立即沟通", "type": "button", "x": 100, "y": 200, "width": 80, "height": 30, "text": "立即沟通", "confidence": 0.95}
  ],
  "screen_text": "..."
}
坐标单位为像素，原点在屏幕左上角。
""".strip()

    def __init__(self, llm_client: Optional[VolcengineLLMClient] = None):
        self._llm = llm_client or VolcengineLLMClient()
        self._logger = get_logger(__name__)
        self.last_screenshot_path: Optional[str] = None
        _SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

    async def capture_and_understand(
        self,
        region: Optional[Tuple[int, int, int, int]] = None,
        task_context: str = "",
    ) -> Dict[str, Any]:
        """截屏 + Vision 分析，返回页面类型与元素列表"""
        screenshot_path, image_base64 = await asyncio.to_thread(
            self._capture_screen, region
        )
        self.last_screenshot_path = screenshot_path

        result = await self._analyze_with_vision(image_base64, task_context)
        result["screenshot_path"] = screenshot_path
        return result

    def _capture_screen(
        self, region: Optional[Tuple[int, int, int, int]] = None
    ) -> Tuple[str, str]:
        try:
            import mss
            from PIL import Image
        except ImportError as exc:
            raise ImportError(
                "视觉模式需要安装: pip install mss Pillow"
            ) from exc

        with mss.mss() as sct:
            if region:
                monitor = {
                    "left": region[0],
                    "top": region[1],
                    "width": region[2],
                    "height": region[3],
                }
            else:
                monitor = sct.monitors[1]

            shot = sct.grab(monitor)
            img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = _SCREENSHOT_DIR / f"screen_{timestamp}.png"
        img.save(filepath, format="PNG")

        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        image_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
        return str(filepath), image_base64

    async def _analyze_with_vision(
        self, image_base64: str, task_context: str
    ) -> Dict[str, Any]:
        user_prompt = f"{task_context}\n\n请分析这张屏幕截图，返回 JSON。"
        try:
            result = await self._llm.avision_chat_json(
                image_base64=image_base64,
                message=user_prompt,
                system_prompt=self.VISION_SYSTEM_PROMPT,
                temperature=0.1,
                max_tokens=4096,
            )
            return self._parse_vision_result(result.get("content", {}))
        except Exception as exc:
            self._logger.error("Vision 分析失败: %s", exc, exc_info=True)
            return {
                "page_type": "unknown",
                "elements": [],
                "screen_text": "",
            }

    def _parse_vision_result(self, content: Any) -> Dict[str, Any]:
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except json.JSONDecodeError:
                match = re.search(r"\{.*\}", content, re.DOTALL)
                content = json.loads(match.group(0)) if match else {}

        if not isinstance(content, dict):
            content = {}

        elements: List[ScreenElement] = []
        for elem_data in content.get("elements") or []:
            if not isinstance(elem_data, dict):
                continue
            elements.append(
                ScreenElement(
                    name=str(elem_data.get("name", "")),
                    element_type=str(elem_data.get("type", "unknown")),
                    x=int(elem_data.get("x", 0) or 0),
                    y=int(elem_data.get("y", 0) or 0),
                    width=int(elem_data.get("width", 0) or 0),
                    height=int(elem_data.get("height", 0) or 0),
                    confidence=float(elem_data.get("confidence", 0.9) or 0.9),
                    text=str(elem_data.get("text", "") or ""),
                )
            )

        return {
            "page_type": content.get("page_type", "unknown"),
            "elements": elements,
            "screen_text": content.get("screen_text", "") or "",
        }

    @staticmethod
    def find_element_by_name(
        elements: List[ScreenElement],
        target_name: str,
        fuzzy: bool = True,
    ) -> Optional[ScreenElement]:
        target = (target_name or "").strip()
        if not target:
            return None
        for elem in elements:
            if fuzzy:
                if target in elem.name or elem.name in target:
                    return elem
                if target in elem.text or elem.text in target:
                    return elem
            elif elem.name == target:
                return elem
        return None
