"""
自动化求职任务编排模块

串联 BrowserAgent、JobScanner、JobScreener、ChatGenerator、BrowserOperator，
完成「扫描岗位 → 匹配筛选 → 生成话术 → 自动沟通」的真实流程。
"""

import asyncio
from typing import Callable, Optional
from urllib.parse import quote

from browser.agent import BrowserAgent
from browser.agent_helpers import wait_for_user_login
from browser.job_scanner import JobScanner
from browser.operator import BrowserOperator
from core.chat_generator import ChatGenerator
from core.job_screener import JobScreener
from core.models import JobInfo, UserProfile
from utils.config_loader import load_settings
from utils.db_helper import get_db
from utils.logger import get_logger


_logger = get_logger(__name__)

BOSS_JOB_SEARCH_URL = "https://www.zhipin.com/web/geek/jobs"
LOGIN_WAIT_SECONDS = 180


def build_job_search_url() -> str:
    """根据 settings.yaml 中的岗位关键词构建 BOSS 直聘搜索页 URL"""
    settings = load_settings()
    keywords = settings.get("job_keywords") or []
    query = keywords[0] if keywords else "Python"
    return f"{BOSS_JOB_SEARCH_URL}?query={quote(str(query))}"


async def _apply_to_job(
    operator: BrowserOperator,
    job: JobInfo,
    greeting: str,
) -> bool:
    """对单个岗位执行：点击立即沟通 → 输入话术 → 发送"""
    target = f"「{job.job_name}」"
    if job.company_name:
        target += f"（{job.company_name}）"

    clicked = await operator.click_element(
        f"在岗位列表或详情页中，点击岗位{target}的「立即沟通」按钮"
    )
    if not clicked:
        _logger.warning(f"未能点击立即沟通: {job.job_name}")
        return False

    await asyncio.sleep(1.5)

    typed = await operator.type_message(greeting, simulate_typing=True)
    if not typed:
        _logger.warning(f"未能输入打招呼语: {job.job_name}")
        return False

    return await operator.send_message()


def _save_application(
    job: JobInfo,
    match_score: float,
    match_reason: str,
    greeting: Optional[str],
    status: str,
) -> None:
    """将求职记录写入 SQLite"""
    db = get_db()
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
        _logger.warning(f"保存求职记录失败 job_id={job.job_id}: {exc}")


async def _wait_if_paused(
    should_continue: Callable[[], bool],
    is_paused: Callable[[], bool],
) -> None:
    """任务暂停时阻塞等待"""
    while is_paused() and should_continue():
        await asyncio.sleep(1.0)


async def run_automation_loop(
    browser_agent,
    user_profile: UserProfile,
    daily_limit: int,
    match_threshold: float,
    should_continue: Callable[[], bool],
    is_paused: Callable[[], bool],
    on_stats_update: Optional[Callable[[dict], None]] = None,
) -> dict:
    """自动化求职主循环（async）"""
    stats = {
        "total_count": 0,
        "matched_count": 0,
        "skipped_count": 0,
        "replied_count": 0,
    }

    db = get_db()
    sent_today = db.get_today_stats().get("sent", 0)
    if sent_today >= daily_limit:
        _logger.info(f"今日已沟通 {sent_today} 个岗位，已达上限 {daily_limit}")
        return stats

    remaining = daily_limit - sent_today
    _logger.info(
        f"开始真实自动化流程 | 今日剩余配额: {remaining}/{daily_limit} | "
        f"匹配阈值: {match_threshold}"
    )

    scanner = JobScanner(browser_agent)
    operator = BrowserOperator(browser_agent)
    screener = JobScreener(user_profile)
    screener._criteria.match_score_threshold = match_threshold
    generator = ChatGenerator(user_profile)

    page = browser_agent.get_page()
    if page and not await wait_for_user_login(
        page,
        should_continue,
        _logger,
        max_wait=LOGIN_WAIT_SECONDS,
        login_url=BrowserAgent.BOSS_LOGIN_URL,
        grace_period=10.0,
        browser_agent=browser_agent,
    ):
        _logger.error("未完成登录，自动化任务终止")
        return stats

    search_url = build_job_search_url()
    _logger.info(f"登录成功，导航至岗位搜索页: {search_url}")

    if not await operator.navigate_to_url(search_url):
        _logger.error("无法打开岗位搜索页，请检查网络或登录状态")
        return stats

    await scanner.wait_for_dynamic_content(timeout=30)
    await asyncio.sleep(2)

    sent_count = 0
    empty_scan_rounds = 0
    max_empty_rounds = 3

    while should_continue() and sent_count < remaining:
        await _wait_if_paused(should_continue, is_paused)
        if not should_continue():
            break

        _logger.info("🔍 正在扫描当前页面岗位列表...")
        jobs = await scanner.scan_job_list()

        if not jobs:
            empty_scan_rounds += 1
            _logger.warning(
                f"本页未解析到岗位 ({empty_scan_rounds}/{max_empty_rounds})，"
                "请确认已登录且在搜索结果页"
            )
            if empty_scan_rounds >= max_empty_rounds:
                _logger.error("连续多次扫描无结果，任务终止")
                break
            await operator.scroll_down()
            await asyncio.sleep(2)
            continue

        empty_scan_rounds = 0

        for job in jobs:
            await _wait_if_paused(should_continue, is_paused)
            if not should_continue() or sent_count >= remaining:
                break

            stats["total_count"] += 1
            result = screener.score(job)

            if not result.get("passed"):
                stats["skipped_count"] += 1
                _logger.info(
                    f"跳过岗位: {job.job_name} | 原因: {result.get('reason', '未达标')}"
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

            score = result.get("score", 0.0)
            reason = result.get("reason", "")
            _logger.info(f"匹配岗位: {job.job_name} | 分数: {score:.1f}")

            try:
                greeting = generator.generate_greeting(job)
            except Exception as exc:
                _logger.warning(f"生成话术失败: {job.job_name} | {exc}")
                stats["skipped_count"] += 1
                if on_stats_update:
                    on_stats_update(stats)
                continue

            success = await _apply_to_job(operator, job, greeting)
            status = "sent" if success else "failed"
            _save_application(job, score, reason, greeting, status)

            if success:
                sent_count += 1
                stats["matched_count"] += 1
                _logger.info(f"已沟通岗位 ({sent_count}/{remaining}): {job.job_name}")
            else:
                stats["skipped_count"] += 1

            if on_stats_update:
                on_stats_update(stats)

            await asyncio.sleep(2)

        if sent_count >= remaining:
            break

        has_next = await operator.click_next_page()
        if not has_next:
            await operator.scroll_down()
        await asyncio.sleep(2)

    _logger.info(
        f"自动化流程结束 | 扫描: {stats['total_count']} | "
        f"沟通: {stats['matched_count']} | 跳过: {stats['skipped_count']}"
    )
    return stats
