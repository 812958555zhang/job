"""
自动化求职任务编排模块

串联 BrowserAgent、JobScanner、JobScreener、ChatGenerator、BrowserOperator，
完成「扫描岗位 → 匹配筛选 → 生成话术 → 自动沟通」的真实流程。
"""

import asyncio
from typing import Callable, Optional
from urllib.parse import quote

from browser.agent import BrowserAgent
from browser.agent_helpers import extract_page_text, wait_for_user_login
from browser.boss_city import (
    cities_match,
    detect_city_from_page_text,
    ensure_boss_search_city,
    resolve_city_code,
)
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


def _pick_search_keyword(user_profile: UserProfile) -> str:
    """优先用简历中的期望岗位/当前职位，其次用配置关键词"""
    if user_profile.expected_positions:
        return str(user_profile.expected_positions[0])
    if user_profile.current_position:
        return str(user_profile.current_position)
    settings = load_settings()
    config_keywords = settings.get("job_keywords") or []
    if config_keywords:
        return str(config_keywords[0])
    if user_profile.skills:
        return str(user_profile.skills[0])
    return "Python"


def _pick_search_city(user_profile: UserProfile) -> Optional[str]:
    """优先用简历期望城市，其次用配置中的期望城市"""
    for city in user_profile.expected_locations or []:
        city = str(city).strip()
        if city:
            return city

    settings = load_settings()
    for city in settings.get("locations") or []:
        city = str(city).strip()
        if city:
            return city
    return None


def build_job_search_url(
    user_profile: Optional[UserProfile] = None,
    page: int = 1,
    city_code: Optional[str] = None,
) -> str:
    """根据简历/配置构建 BOSS 直聘搜索页 URL（支持城市与自动翻页）"""
    query = _pick_search_keyword(user_profile) if user_profile else "Python"
    url = f"{BOSS_JOB_SEARCH_URL}?query={quote(query)}"
    if city_code:
        url += f"&city={city_code}"
    if page > 1:
        url += f"&page={page}"
    return url


def detect_city_from_text(text: str) -> Optional[str]:
    """从 BOSS 搜索页文本识别当前城市（兼容旧调用）"""
    return detect_city_from_page_text(text)


async def _prepare_search_page(
    browser_agent,
    scanner: JobScanner,
    operator: BrowserOperator,
    target_city_name: Optional[str],
    city_code: Optional[str],
) -> None:
    """搜索页加载后：切换城市 → 等待岗位卡片 → 鼠标滚轮懒加载"""
    from browser.agent_helpers import count_job_cards, wait_for_job_cards

    await scanner.wait_for_dynamic_content(timeout=30)

    page = browser_agent.get_page()
    if page and target_city_name:
        switched = await ensure_boss_search_city(page, target_city_name, city_code)
        if switched:
            await scanner.wait_for_dynamic_content(timeout=15)
        page = browser_agent.get_page()

    if page:
        if not await wait_for_job_cards(page, min_count=3, timeout=25):
            _logger.warning("岗位卡片尚未出现，将尝试滚轮加载...")
        await operator.scroll_to_load_jobs()
        cards = await count_job_cards(page)
        _logger.info("页面就绪 | 可见岗位卡片: %s", cards)
        if cards < 3:
            await operator.scroll_to_load_jobs(steps=8)
            cards = await count_job_cards(page)
            _logger.info("二次滚轮加载后 | 可见岗位卡片: %s", cards)

    await asyncio.sleep(1)


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
    """将求职记录写入 SQLite（已存在则跳过，避免重复告警）"""
    db = get_db()
    if db.check_job_applied(job.job_id):
        _logger.debug("求职记录已存在，跳过写入 job_id=%s", job.job_id)
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

    _logger.info(
        "根据简历自动匹配 | 姓名: %s | 当前职位: %s | 经验: %s年 | 核心技能: %s",
        user_profile.name,
        user_profile.current_position or "未填写",
        user_profile.total_experience_years,
        ", ".join(user_profile.skills[:6]) if user_profile.skills else "未填写",
    )

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

    page_index = 1
    max_pages = 10
    target_city_name = _pick_search_city(user_profile)
    city_code: Optional[str] = None

    live_page = browser_agent.get_page()
    if target_city_name and live_page:
        city_code = await resolve_city_code(live_page, target_city_name)
        if city_code:
            _logger.info(
                "按简历切换搜索城市: %s (city=%s)",
                target_city_name,
                city_code,
            )
            screener.add_search_city(target_city_name)
        else:
            _logger.warning(
                "未找到城市 '%s' 的 BOSS 编码，将使用浏览器当前定位城市",
                target_city_name,
            )

    search_url = build_job_search_url(
        user_profile,
        page=page_index,
        city_code=city_code,
    )
    _logger.info(f"登录成功，导航至岗位搜索页: {search_url}")

    if not await operator.navigate_to_url(search_url):
        _logger.error("无法打开岗位搜索页，请检查网络或登录状态")
        return stats

    await _prepare_search_page(
        browser_agent,
        scanner,
        operator,
        target_city_name,
        city_code,
    )

    live_page = browser_agent.get_page()
    if live_page:
        city_text = await extract_page_text(live_page, max_chars=800)
        detected_city = detect_city_from_text(city_text)
        if detected_city:
            screener.add_search_city(detected_city)
            if target_city_name and not cities_match(detected_city, target_city_name):
                _logger.warning(
                    "搜索页当前城市为 %s，与简历期望 %s 不一致，岗位结果可能不准确",
                    detected_city,
                    target_city_name,
                )

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
            await operator.scroll_to_load_jobs(steps=8)
            await asyncio.sleep(2)
            continue

        empty_scan_rounds = 0
        page_matched = 0
        page_skipped = 0

        for job in jobs:
            await _wait_if_paused(should_continue, is_paused)
            if not should_continue() or sent_count >= remaining:
                break

            stats["total_count"] += 1
            result = screener.score(job)

            if not result.get("passed"):
                stats["skipped_count"] += 1
                page_skipped += 1
                _logger.info(
                    f"跳过岗位: {job.job_name} | 分数: {result.get('score', 0):.1f} | "
                    f"原因: {result.get('reason', '未达标')}"
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
            page_matched += 1
            _logger.info(
                f"✅ 简历匹配岗位: {job.job_name} @ {job.company_name or '未知公司'} | "
                f"分数: {score:.1f} | {reason}"
            )

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

        _logger.info(
            f"第 {page_index} 页筛选完成 | 匹配: {page_matched} | 跳过: {page_skipped} | "
            f"已沟通: {sent_count}/{remaining}"
        )

        if sent_count >= remaining:
            break

        page_index += 1
        if page_index > max_pages:
            _logger.info("已达最大自动翻页数 %s，结束扫描", max_pages)
            break

        next_url = build_job_search_url(
            user_profile,
            page=page_index,
            city_code=city_code,
        )
        _logger.info(f"自动翻页 → 第 {page_index} 页: {next_url}")
        if not await operator.navigate_to_url(next_url):
            _logger.warning("自动翻页失败，停止继续扫描")
            break
        await _prepare_search_page(
            browser_agent,
            scanner,
            operator,
            target_city_name,
            city_code,
        )

    _logger.info(
        f"自动化流程结束 | 扫描: {stats['total_count']} | "
        f"沟通: {stats['matched_count']} | 跳过: {stats['skipped_count']}"
    )
    return stats
