"""
Browser Use Agent 辅助函数

封装 browser-use 0.11+ 的异步调用与任务执行，供 agent / operator / scanner 复用。
"""

import asyncio
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class BrowserTaskResult:
    """兼容旧代码的 Browser Use 任务返回结构"""

    content: Optional[str]


def run_async(coro):
    """在同步上下文中安全运行协程"""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(asyncio.run, coro)
        return future.result()


async def run_browser_use_task(agent, task: str, max_steps: int = 15) -> Optional[BrowserTaskResult]:
    """
    向 Browser Use Agent 下发单次任务并执行

    browser-use 0.11+ 的任务在 Agent 初始化或 add_new_task 中设置，
    run() 不再接受 task 参数。
    """
    if agent is None:
        return None

    agent.add_new_task(task)
    history = await agent.run(max_steps=max_steps)
    if history is None or len(history) == 0:
        return None

    content = history.final_result()
    if not content:
        extracted = history.extracted_content()
        content = "\n".join(extracted) if extracted else str(history)

    return BrowserTaskResult(content=content)


async def navigate_page(
    page: Any, url: str, wait_seconds: float = 2.0, focus: bool = False
) -> bool:
    """兼容 browser-use Page 与 Playwright Page 的导航"""
    if page is None:
        return False

    # 执行导航 - Playwright 使用 wait_until="networkidle" 确保页面真正加载
    if hasattr(page, "goto"):
        try:
            # 使用 networkidle 确保页面网络请求完成
            await page.goto(url, wait_until="networkidle", timeout=60000)
        except Exception:
            # 如果失败，尝试更宽松的选项
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            except Exception:
                # 最后一次尝试，不等待
                try:
                    await page.goto(url)
                except Exception:
                    pass
    elif hasattr(page, "navigate"):
        await page.navigate(url)
    else:
        return False

    if wait_seconds > 0:
        await asyncio.sleep(wait_seconds)

    # 验证导航是否成功
    try:
        current_url = ""
        if hasattr(page, "url"):
            url_attr = page.url
            if asyncio.iscoroutine(url_attr):
                current_url = await url_attr
            else:
                current_url = str(url_attr)
        elif hasattr(page, "evaluate"):
            current_url = await page.evaluate("() => window.location.href")

        # 检查 URL 是否包含目标域名
        target_domain = url.split("/")[2] if "/" in url else url
        if target_domain in current_url:
            if focus and hasattr(page, "bring_to_front"):
                try:
                    await page.bring_to_front()
                except Exception:
                    pass
            return True
        return False
    except Exception:
        return False


async def pick_zhipin_page(
    context: Any, login_url: str = "", focus: bool = False
) -> Any:
    """
    从浏览器上下文中选出最合适的 BOSS 直聘页面（优先登录页）

    focus=False 时不调用 bring_to_front，避免打断用户正在操作的标签。
    """
    if context is None or not hasattr(context, "pages"):
        return None

    pages = list(context.pages)
    if not pages:
        return None

    login_hint = login_url or "https://www.zhipin.com/web/user/"
    login_pages = []
    zhipin_pages = []

    for page in pages:
        try:
            if page.is_closed():
                continue
            url = await get_page_url(page)
        except Exception:
            continue
        if "zhipin.com" not in url:
            continue
        zhipin_pages.append(page)
        if "/web/user" in url or "login" in url.lower() or login_hint.split("?")[0] in url:
            login_pages.append(page)

    chosen = login_pages[0] if login_pages else (zhipin_pages[0] if zhipin_pages else None)
    if chosen and focus and hasattr(chosen, "bring_to_front"):
        try:
            await chosen.bring_to_front()
        except Exception:
            pass
    return chosen


async def scan_pages_for_login(context: Any) -> tuple[bool, Any, str]:
    """
    扫描所有标签页是否已登录（不切换焦点、不导航）

    Returns:
        (是否已登录, 命中的页面对象, 该页 URL)
    """
    if context is None or not hasattr(context, "pages"):
        return False, None, ""

    for page in context.pages:
        try:
            if page.is_closed():
                continue
            url = await get_page_url(page)
            text = await extract_page_text(page)
            if is_logged_in(text, url):
                return True, page, url
        except Exception:
            continue
    return False, None, ""


async def any_zhipin_page_open(context: Any) -> bool:
    """是否存在任意已打开 BOSS 直聘页面的标签"""
    if context is None or not hasattr(context, "pages"):
        return False
    for page in context.pages:
        try:
            if page.is_closed():
                continue
            url = await get_page_url(page)
            if "zhipin.com" in url:
                return True
        except Exception:
            continue
    return False


async def open_single_login_tab(context: Any, login_url: str) -> Any:
    """
    关闭多余标签，保留一个标签并打开登录页（仅启动时调用一次）
    """
    if context is None:
        return None

    pages = [p for p in context.pages if not p.is_closed()]
    if pages:
        page = pages[0]
        for extra in pages[1:]:
            try:
                await extra.close()
            except Exception:
                pass
    else:
        page = await context.new_page()

    for attempt in range(3):
        await navigate_page(page, login_url, wait_seconds=1.5, focus=False)
        url = await get_page_url(page)
        if "zhipin.com" in url:
            return page
        await asyncio.sleep(1.0)

    return page


async def go_back_page(page: Any, wait_seconds: float = 1.0) -> bool:
    """兼容 browser-use Page 与 Playwright Page 的后退"""
    if page is None:
        return False

    if hasattr(page, "go_back"):
        await page.go_back()
    else:
        return False

    if wait_seconds > 0:
        await asyncio.sleep(wait_seconds)
    return True


async def get_page_url(page: Any) -> str:
    """获取当前页面 URL"""
    if page is None:
        return ""

    if hasattr(page, "get_url"):
        return await page.get_url()

    url = getattr(page, "url", "")
    if asyncio.iscoroutine(url):
        return await url
    return str(url) if url else ""


async def get_page_title(page: Any) -> str:
    """获取当前页面标题"""
    if page is None:
        return ""

    if hasattr(page, "get_title"):
        return await page.get_title()

    title = getattr(page, "title", None)
    if callable(title):
        result = title()
        if asyncio.iscoroutine(result):
            return await result
        return str(result)
    return str(title) if title else ""


async def scroll_page(page: Any, pixels: Optional[int] = None) -> bool:
    """向下滚动页面"""
    if page is None:
        return False

    script = (
        f"window.scrollBy(0, {pixels});"
        if pixels
        else "window.scrollBy(0, window.innerHeight);"
    )

    if hasattr(page, "evaluate"):
        await page.evaluate(script)
        await asyncio.sleep(0.5)
        return True
    return False


async def wait_for_page_ready(page: Any, timeout: float = 30.0) -> bool:
    """等待页面加载完成（兼容 browser-use Page）"""
    if page is None:
        return False

    if hasattr(page, "wait_for_load_state"):
        await page.wait_for_load_state("networkidle", timeout=int(timeout * 1000))
    else:
        await asyncio.sleep(min(timeout, 5.0))

    await asyncio.sleep(2)
    return True


_EXTRACT_PAGE_TEXT_JS = """
() => {
  const selectors = [
    '.job-list-box',
    '.search-job-result',
    '.job-card-wrapper',
    '.job-list',
    '.rec-job-list',
    'main',
  ];
  for (const sel of selectors) {
    const el = document.querySelector(sel);
    if (el && el.innerText && el.innerText.trim().length > 100) {
      return el.innerText.trim();
    }
  }
  return document.body ? document.body.innerText.trim() : '';
}
"""


async def extract_page_text(page: Any, max_chars: int = 12000) -> str:
    """从当前页面提取可见文本（不触发 Browser Use 重新导航）"""
    if page is None:
        return ""

    text = ""
    if hasattr(page, "evaluate"):
        text = await page.evaluate(_EXTRACT_PAGE_TEXT_JS)
    elif hasattr(page, "content"):
        text = await page.content()

    if not text:
        return ""
    text = str(text).strip()
    if len(text) > max_chars:
        return text[:max_chars]
    return text


def page_needs_login(page_text: str, page_url: str = "") -> bool:
    """判断当前页面是否处于未登录或登录失效状态"""
    url = (page_url or "").lower()
    if any(token in url for token in ("login.zhipin.com", "/login", "passport", "signin")):
        return True

    text = page_text or ""
    login_markers = (
        "扫码登录",
        "登录状态已失效",
        "请登录",
        "验证码登录",
        "短信登录",
        "账号登录",
        "登录/注册",
    )
    return any(marker in text for marker in login_markers)


def is_logged_in(page_text: str, page_url: str = "") -> bool:
    """判断用户是否已完成 BOSS 直聘登录（严格模式，避免首页误判）"""
    if not page_text or len(page_text) < 80:
        return False

    url = (page_url or "").lower()

    if "login.zhipin.com" in url:
        return False

    if "/web/user" in url or "/web/geek/login" in url:
        return False

    if page_needs_login(page_text, page_url):
        return False

    geek_paths = (
        "/web/geek/jobs",
        "/web/geek/chat",
        "/web/geek/recommend",
        "/web/geek/job",
    )
    if any(path in url for path in geek_paths):
        return True

    session_markers = ("我的沟通", "在线简历", "投递记录", "谁看过我", "附件简历")
    return any(marker in page_text for marker in session_markers)


def _is_strayed_from_login(url: str) -> bool:
    """当前标签 URL 是否为空白/非 BOSS 域（仅用于诊断，不再触发立即重导航）"""
    url = (url or "").lower().strip()
    if not url:
        return True
    if any(token in url for token in ("about:blank", "edge://", "chrome://", "newtab")):
        return True
    if "zhipin.com" not in url:
        return True
    return False


BOSS_AUTH_COOKIE_NAMES = frozenset({
    "wt2",
    "__zp_stoken__",
    "zp_at",
    "sid",
    "geek_zp_token",
    "__c",
    "bst",
})


async def check_login_by_cookies(context: Any, page: Any = None) -> bool:
    """
    通过 Cookie 和页面 URL 判断 BOSS 直聘是否已登录

    必须同时满足：
    1. 页面 URL 在 zhipin.com 域名下（不是 about:blank）
    2. 存在有效的认证 Cookie
    """
    if context is None or not hasattr(context, "cookies"):
        return False

    # 先检查页面 URL
    if page is not None:
        try:
            current_url = ""
            if hasattr(page, "url"):
                url_attr = page.url
                if asyncio.iscoroutine(url_attr):
                    current_url = await url_attr
                else:
                    current_url = str(url_attr)

            # URL 必须是 zhipin.com 且不是登录页
            if "zhipin.com" not in current_url or "about:blank" in current_url:
                return False
            # 在登录页说明还没登录成功
            if "/web/user" in current_url or "login" in current_url.lower():
                return False
        except Exception:
            pass

    try:
        cookies = await context.cookies()
    except Exception:
        return False

    # 检查是否有有效的认证 Cookie
    has_auth_cookie = False
    for cookie in cookies:
        domain = cookie.get("domain", "")
        if "zhipin.com" not in domain:
            continue
        name = cookie.get("name", "")
        value = (cookie.get("value") or "").strip()
        # 必须是真正的会话 Cookie（有值且长度合理）
        if value and len(value) > 10 and name in BOSS_AUTH_COOKIE_NAMES:
            has_auth_cookie = True
            break

    return has_auth_cookie


async def wait_for_user_login(
    page: Any,
    should_continue,
    logger,
    poll_interval: float = 5.0,
    max_wait: float = 180.0,
    login_url: str = "",
    grace_period: float = 10.0,
    confirm_checks: int = 2,
    browser_agent=None,
) -> bool:
    """
    等待用户完成 BOSS 直聘登录

    等待期间只读 Cookie，不 evaluate DOM、不切换标签、不导航，避免打断扫码。
    """
    logger.warning(
        f"请在浏览器窗口中登录 BOSS 直聘（扫码或账号登录），"
        f"系统将等待 {int(max_wait)} 秒，期间不会触碰浏览器页面"
    )
    logger.info(f"登录页已打开，等待 {int(grace_period)} 秒供您完成登录...")

    if grace_period > 0:
        await asyncio.sleep(grace_period)

    elapsed = grace_period
    confirmed = 0
    context = getattr(browser_agent, "_playwright_context", None) if browser_agent else None

    while elapsed < max_wait:
        if not should_continue():
            return False

        # 使用当前页面检查登录状态（必须同时满足 URL 在 zhipin.com 且 Cookie 有效）
        if context and await check_login_by_cookies(context, page):
            confirmed += 1
            logger.info(f"检测到已登录状态 ({confirmed}/{confirm_checks})")
            if confirmed >= confirm_checks:
                logger.info("登录确认完成，准备进入岗位搜索")
                if browser_agent:
                    # 获取当前活动页面
                    try:
                        pages = context.pages
                        for p in pages:
                            if not p.is_closed():
                                url = p.url if hasattr(p, "url") else ""
                                if "zhipin.com" in url and "/web/user" not in url:
                                    browser_agent._page = p
                                    break
                    except Exception:
                        pass
                    if hasattr(browser_agent, "_async_save_session"):
                        await browser_agent._async_save_session()
                return True
        else:
            confirmed = 0

        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

    logger.error(f"等待登录超时（{int(max_wait)} 秒），请重新启动任务")
    return False
