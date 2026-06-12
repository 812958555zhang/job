"""
人类行为模拟 MCP 工具集 - 鼠标/键盘/截图
"""

import random
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from utils.delay_simulator import DelaySimulator
from utils.logger import get_logger

_logger = get_logger(__name__)

try:
    import pyautogui
    import pyperclip

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.01
    _PYAUTOGUI_AVAILABLE = True
except ImportError:
    pyautogui = None  # type: ignore
    pyperclip = None  # type: ignore
    _PYAUTOGUI_AVAILABLE = False


class MouseTool:
    """鼠标控制 - 模拟人类移动与点击"""

    def __init__(self, delay_simulator: Optional[DelaySimulator] = None):
        self._simulator = delay_simulator or DelaySimulator()

    def move_to(self, x: int, y: int, duration: float = 0.5) -> None:
        if not _PYAUTOGUI_AVAILABLE:
            raise RuntimeError("请安装 pyautogui: pip install pyautogui")
        pyautogui.moveTo(x, y, duration=duration, tween=pyautogui.easeOutQuad)

    def click(
        self,
        x: Optional[int] = None,
        y: Optional[int] = None,
        button: str = "left",
        clicks: int = 1,
    ) -> None:
        if not _PYAUTOGUI_AVAILABLE:
            raise RuntimeError("请安装 pyautogui: pip install pyautogui")
        if x is not None and y is not None:
            self.move_to(x, y)
            time.sleep(random.uniform(0.1, 0.3))
        pyautogui.click(x=x, y=y, button=button, clicks=clicks)

    def scroll(self, clicks: int = 3, x: Optional[int] = None, y: Optional[int] = None) -> None:
        if not _PYAUTOGUI_AVAILABLE:
            raise RuntimeError("请安装 pyautogui: pip install pyautogui")
        if x is not None and y is not None:
            self.move_to(x, y, duration=0.2)
            time.sleep(0.1)
        pyautogui.scroll(clicks, x=x, y=y)


class KeyboardTool:
    """键盘控制 - 打字与粘贴"""

    def __init__(self, delay_simulator: Optional[DelaySimulator] = None):
        self._simulator = delay_simulator or DelaySimulator()

    def type_text(self, text: str, interval: float = 0.05) -> None:
        if not _PYAUTOGUI_AVAILABLE:
            raise RuntimeError("请安装 pyautogui: pip install pyautogui")
        for char in text:
            pyautogui.write(char, interval=interval)
            if random.random() < 0.05:
                time.sleep(random.uniform(0.3, 0.8))

    def paste_text(self, text: str) -> None:
        if not _PYAUTOGUI_AVAILABLE or pyperclip is None:
            raise RuntimeError("请安装 pyautogui pyperclip")
        pyperclip.copy(text)
        time.sleep(0.05)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.1)

    def press_key(self, key: str) -> None:
        if not _PYAUTOGUI_AVAILABLE:
            raise RuntimeError("请安装 pyautogui: pip install pyautogui")
        pyautogui.press(key)

    def hotkey(self, *keys: str) -> None:
        if not _PYAUTOGUI_AVAILABLE:
            raise RuntimeError("请安装 pyautogui: pip install pyautogui")
        pyautogui.hotkey(*keys)


class ScreenTool:
    """屏幕截图工具"""

    def __init__(self):
        self._root = Path(__file__).resolve().parent.parent
        self._dir = self._root / "data" / "screenshots"
        self._dir.mkdir(parents=True, exist_ok=True)

    def capture(self, region: Optional[Tuple[int, int, int, int]] = None) -> str:
        try:
            import mss
        except ImportError as exc:
            raise ImportError("请安装 mss: pip install mss") from exc

        from datetime import datetime

        filepath = self._dir / f"screen_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        with mss.mss() as sct:
            monitor = (
                {
                    "left": region[0],
                    "top": region[1],
                    "width": region[2],
                    "height": region[3],
                }
                if region
                else sct.monitors[1]
            )
            sct.shot(mon=monitor, output=str(filepath))
        return str(filepath)


class HumanActionToolkit:
    """MCP 风格工具集，供 Vision Agent 调用"""

    def __init__(self, delay_simulator: Optional[DelaySimulator] = None):
        self.simulator = delay_simulator or DelaySimulator()
        self.mouse = MouseTool(self.simulator)
        self.keyboard = KeyboardTool(self.simulator)
        self.screen = ScreenTool()

    def get_available_tools(self) -> List[Dict[str, Any]]:
        return [
            {"name": "mouse_click", "description": "在指定坐标点击鼠标"},
            {"name": "mouse_move", "description": "移动鼠标到指定坐标"},
            {"name": "type_text", "description": "逐字输入文本"},
            {"name": "paste_text", "description": "剪贴板粘贴文本（适合中文）"},
            {"name": "key_press", "description": "按下指定按键"},
            {"name": "hotkey", "description": "按下组合键"},
            {"name": "scroll", "description": "滚动鼠标滚轮"},
            {"name": "wait", "description": "等待指定秒数"},
        ]

    def execute_action(self, action: Dict[str, Any]) -> bool:
        """同步执行 AI 决策的操作"""
        tool_name = action.get("tool")
        params = action.get("params") or {}

        self.simulator.random_short_delay()

        if tool_name == "mouse_click":
            self.mouse.click(
                x=params.get("x"),
                y=params.get("y"),
                button=params.get("button", "left"),
            )
        elif tool_name == "mouse_move":
            self.mouse.move_to(
                x=params.get("x"),
                y=params.get("y"),
                duration=params.get("duration", 0.5),
            )
        elif tool_name == "type_text":
            self.keyboard.type_text(
                text=params.get("text", ""),
                interval=params.get("interval", 0.05),
            )
        elif tool_name == "paste_text":
            self.keyboard.paste_text(text=params.get("text", ""))
        elif tool_name == "key_press":
            self.keyboard.press_key(params.get("key", "enter"))
        elif tool_name == "hotkey":
            keys = params.get("keys") or ["ctrl", "v"]
            self.keyboard.hotkey(*keys)
        elif tool_name == "scroll":
            self.mouse.scroll(
                clicks=params.get("clicks", -3),
                x=params.get("x"),
                y=params.get("y"),
            )
        elif tool_name == "wait":
            time.sleep(params.get("seconds", 2))
        else:
            raise ValueError(f"未知工具: {tool_name}")

        self.simulator.random_short_delay()
        return True
