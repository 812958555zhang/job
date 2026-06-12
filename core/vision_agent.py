"""
视觉驱动 AI Agent - 截图 → Vision 理解 → MCP 工具执行
"""

import asyncio
import hashlib
import random
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from core.chat_generator import ChatGenerator
from core.job_screener import JobScreener
from core.llm_client import VolcengineLLMClient
from core.models import JobInfo, UserProfile
from core.screen_vision import ScreenElement, ScreenVision
from tools.human_action_tools import HumanActionToolkit
from utils.db_helper import get_db
from utils.delay_simulator import DelaySimulator
from utils.logger import get_logger

_logger = get_logger(__name__)


@dataclass
class TaskState:
    current_phase: str = "init"
    step_number: int = 0
    context_history: List[Dict] = field(default_factory=list)
    last_action: Optional[Dict] = None
    error_count: int = 0


def _save_application(
    job: JobInfo,
    match_score: float,
    match_reason: str,
    greeting: Optional[str],
    status: str,
) -> None:
    db = get_db()
    if db.check_job_applied(job.job_id):
        return
    try:
        db.create_application(
            {
                "job_id": job.job_id,
                "job_name": job.job_name or "未知岗位",
                "company_name": job.company_name or "未知公司",
                "salary_min": job.salary_min,
                "salary_max": job.salary_max,
                "location": job.location,
                "job_description": job.job_description,
                "match_score": match_score,
                "match_reason": match_reason,
                "greeting_message": greeting,
                "status": status,
            }
        )
    except Exception as exc:
        _logger.warning("保存求职记录失败 job_id=%s: %s", job.job_id, exc)


def _parse_salary(text: str) -> tuple:
    if not text:
        return None, None
    nums = re.findall(r"(\d+(?:\.\d+)?)", str(text))
    if not nums:
        return None, None
    values = [int(round(float(n))) for n in nums[:2]]
    if len(values) == 1:
        return values[0], values[0]
    return values[0], values[1]


def _job_dict_to_job_info(data: dict) -> Optional[JobInfo]:
    job_name = str(data.get("job_name") or data.get("name") or "").strip()
    company_name = str(data.get("company_name") or data.get("company") or "").strip()
    if not job_name:
        return None

    job_id = data.get("job_id")
    if not job_id:
        hash_str = f"{job_name}{company_name}"
        job_id = f"job_{hashlib.md5(hash_str.encode()).hexdigest()[:8]}"

    salary_text = data.get("salary") or data.get("salary_description") or ""
    salary_min = data.get("salary_min")
    salary_max = data.get("salary_max")
    if salary_min is None and salary_max is None and salary_text:
        salary_min, salary_max = _parse_salary(salary_text)

    tags = data.get("tags")
    if not isinstance(tags, list):
        tags = []

    return JobInfo(
        job_id=str(job_id),
        job_name=job_name,
        company_name=company_name,
        salary_min=salary_min,
        salary_max=salary_max,
        salary_description=str(salary_text) if salary_text else None,
        location=data.get("location"),
        tags=tags,
    )


class VisionAgent:
    """纯视觉驱动求职 Agent"""

    PHASE_LOGIN = "login"
    PHASE_SEARCH = "search"
    PHASE_COMPLETE = "complete"

    def __init__(
        self,
        user_profile: UserProfile,
        match_threshold: float = 60.0,
        llm_client: Optional[VolcengineLLMClient] = None,
    ):
        self._llm = llm_client or VolcengineLLMClient()
        self._vision = ScreenVision(self._llm)
        self._tools = HumanActionToolkit()
        self._simulator = DelaySimulator()
        self._chat_gen = ChatGenerator(user_profile)
        self._screener = JobScreener(user_profile)
        self._screener._criteria.match_score_threshold = match_threshold
        self._profile = user_profile
        self._logger = get_logger(__name__)
        self.state = TaskState()

    async def run_job_search_loop(
        self,
        daily_limit: int = 2,
        on_stats_update: Optional[Callable[[dict], None]] = None,
        should_continue: Callable[[], bool] = lambda: True,
        is_paused: Callable[[], bool] = lambda: False,
    ) -> dict:
        stats = {
            "total_count": 0,
            "matched_count": 0,
            "skipped_count": 0,
            "replied_count": 0,
        }

        db = get_db()
        sent_today = db.get_today_stats().get("sent", 0)
        if sent_today >= daily_limit:
            _logger.info("今日已沟通 %s 个岗位，已达上限", sent_today)
            return stats

        remaining = daily_limit - sent_today
        sent_count = 0
        empty_rounds = 0

        _logger.info(
            "启动视觉驱动自动化 | 模式: 截图+Vision+MCP | 今日剩余: %s/%s",
            remaining,
            daily_limit,
        )
        _logger.info(
            "请先将 BOSS 直聘 Edge 窗口置于前台并打开搜索列表页"
        )

        while should_continue() and sent_count < remaining:
            while is_paused() and should_continue():
                await asyncio.sleep(1.0)
            if not should_continue():
                break

            screen_info = await self._vision.capture_and_understand(
                task_context="BOSS 直聘自动求职：识别页面类型与岗位列表"
            )
            page_type = screen_info.get("page_type", "unknown")
            elements = screen_info.get("elements") or []
            self._logger.info(
                "Vision | 页面=%s | 元素=%s | 截图=%s",
                page_type,
                len(elements),
                screen_info.get("screenshot_path"),
            )

            if page_type == "login":
                self.state.current_phase = self.PHASE_LOGIN
                _logger.warning(
                    "检测到登录页，请在 Edge 中完成登录（扫码/账号），系统将每 5 秒重试"
                )
                await asyncio.sleep(5)
                continue

            if page_type not in ("search_list", "job_detail", "unknown"):
                _logger.info("当前页面类型 %s，尝试滚动或等待", page_type)
                await self._scroll_job_list(elements)
                await asyncio.sleep(2)
                continue

            jobs = await self._parse_jobs_from_screen(screen_info)
            if not jobs:
                empty_rounds += 1
                _logger.warning(
                    "Vision 未解析到岗位 (%s/3)，尝试滚轮加载",
                    empty_rounds,
                )
                await self._scroll_job_list(elements)
                if empty_rounds >= 3:
                    _logger.error("连续未解析到岗位，视觉任务结束")
                    break
                continue

            empty_rounds = 0
            for job_data in jobs:
                if not should_continue() or sent_count >= remaining:
                    break

                job = _job_dict_to_job_info(job_data)
                if not job:
                    continue

                stats["total_count"] += 1
                result = self._screener.score(job)
                if not result.get("passed"):
                    stats["skipped_count"] += 1
                    _logger.info(
                        "跳过: %s | %.1f | %s",
                        job.job_name,
                        result.get("score", 0),
                        result.get("reason", ""),
                    )
                    _save_application(
                        job,
                        result.get("score", 0.0),
                        result.get("reason", ""),
                        None,
                        "skipped",
                    )
                    if on_stats_update:
                        on_stats_update(stats)
                    continue

                try:
                    greeting = self._chat_gen.generate_greeting(job)
                except Exception as exc:
                    _logger.warning("生成话术失败: %s", exc)
                    stats["skipped_count"] += 1
                    continue

                success = await self._perform_chat_action(job, greeting, elements)
                status = "sent" if success else "failed"
                _save_application(
                    job,
                    result.get("score", 0.0),
                    result.get("reason", ""),
                    greeting,
                    status,
                )

                if success:
                    sent_count += 1
                    stats["matched_count"] += 1
                    _logger.info("已沟通 (%s/%s): %s", sent_count, remaining, job.job_name)
                else:
                    stats["skipped_count"] += 1

                if on_stats_update:
                    on_stats_update(stats)

                await asyncio.sleep(random.uniform(2.0, 4.0))

            await self._scroll_job_list(elements)
            await asyncio.to_thread(self._simulator.random_delay, 3.0, 6.0)

        self.state.current_phase = self.PHASE_COMPLETE
        _logger.info(
            "视觉驱动流程结束 | 扫描: %s | 沟通: %s | 跳过: %s",
            stats["total_count"],
            stats["matched_count"],
            stats["skipped_count"],
        )
        return stats

    async def _parse_jobs_from_screen(self, screen_info: Dict) -> List[Dict]:
        screen_text = screen_info.get("screen_text") or ""
        if not screen_text.strip():
            return []

        system_prompt = """
从 BOSS 直聘搜索列表页的文字中提取岗位信息，输出 JSON 数组。
每项字段：job_name, company_name, salary（文本）, location, tags（数组，可空）。
最多 12 条。
""".strip()

        result = await self._llm.achat_json(
            message=f"提取岗位：\n\n{screen_text[:2500]}",
            system_prompt=system_prompt,
            temperature=0.1,
            max_tokens=4096,
        )
        content = result.get("content")
        if isinstance(content, dict):
            for key in ("jobs", "items", "data"):
                if isinstance(content.get(key), list):
                    return content[key]
            return [content]
        if isinstance(content, list):
            return content
        return []

    async def _scroll_job_list(self, elements: List[ScreenElement]) -> None:
        list_elem = ScreenVision.find_element_by_name(elements, "岗位", fuzzy=True)
        params: Dict[str, Any] = {"clicks": -4}
        if list_elem:
            cx, cy = list_elem.center
            params.update({"x": cx, "y": cy})
        await asyncio.to_thread(
            self._tools.execute_action, {"tool": "scroll", "params": params}
        )
        await asyncio.sleep(1.0)

    async def _perform_chat_action(
        self,
        job: JobInfo,
        greeting: str,
        elements: List[ScreenElement],
    ) -> bool:
        chat_button = ScreenVision.find_element_by_name(
            elements, "立即沟通", fuzzy=True
        )
        if not chat_button:
            _logger.warning("Vision 未找到「立即沟通」按钮: %s", job.job_name)
            return False

        cx, cy = chat_button.center
        actions = [
            {"tool": "mouse_move", "params": {"x": cx, "y": cy, "duration": 0.5}},
            {"tool": "wait", "params": {"seconds": random.uniform(0.5, 1.0)}},
            {"tool": "mouse_click", "params": {"x": cx, "y": cy}},
            {"tool": "wait", "params": {"seconds": random.uniform(2.0, 3.0)}},
        ]
        for action in actions:
            await asyncio.to_thread(self._tools.execute_action, action)

        chat_screen = await self._vision.capture_and_understand(
            task_context="已打开聊天窗口，定位输入框"
        )
        input_box = ScreenVision.find_element_by_name(
            chat_screen.get("elements") or [],
            "输入",
            fuzzy=True,
        )
        if not input_box:
            input_box = ScreenVision.find_element_by_name(
                chat_screen.get("elements") or [],
                "消息",
                fuzzy=True,
            )
        if not input_box:
            _logger.warning("未找到聊天输入框")
            return False

        ix, iy = input_box.center
        send_actions = [
            {"tool": "mouse_click", "params": {"x": ix, "y": iy}},
            {"tool": "wait", "params": {"seconds": 0.5}},
            {"tool": "paste_text", "params": {"text": greeting}},
            {"tool": "wait", "params": {"seconds": random.uniform(1.0, 2.0)}},
            {"tool": "key_press", "params": {"key": "enter"}},
        ]
        for action in send_actions:
            await asyncio.to_thread(self._tools.execute_action, action)

        _logger.info("Vision 沟通完成: %s", job.job_name)
        return True


async def run_vision_automation_loop(
    user_profile: UserProfile,
    daily_limit: int,
    match_threshold: float,
    should_continue: Callable[[], bool],
    is_paused: Callable[[], bool],
    on_stats_update: Optional[Callable[[dict], None]] = None,
) -> dict:
    """视觉驱动自动化入口（供 automation_engine 调用）"""
    agent = VisionAgent(user_profile, match_threshold=match_threshold)
    return await agent.run_job_search_loop(
        daily_limit=daily_limit,
        on_stats_update=on_stats_update,
        should_continue=should_continue,
        is_paused=is_paused,
    )
