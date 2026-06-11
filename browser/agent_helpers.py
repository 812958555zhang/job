"""
Browser Use Agent 辅助函数

封装 browser-use 0.11+ 的异步调用与任务执行，供 agent / operator / scanner 复用。
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Optional


STEALTH_INIT_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
window.chrome = window.chrome || { runtime: {} };
Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en-US', 'en'] });
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
delete window.__playwright;
delete window.__pw_manual;
"""


async def apply_stealth_context(context: Any) -> None:
    """注入反检测脚本，降低 BOSS 直聘识别 Playwright 的概率"""
    if context is None or not hasattr(context, "add_init_script"):
        return
    try:
        await context.add_init_script(STEALTH_INIT_SCRIPT)
    except Exception:
        pass


def _is_blank_url(url: str) -> bool:
    url = (url or "").lower().strip()
    return not url or url in ("about:blank", "chrome://newtab/", "edge://newtab/")


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

    wait_until = "domcontentloaded"
    if hasattr(page, "goto"):
        try:
            await page.goto(url, wait_until=wait_until, timeout=60000)
        except Exception:
            try:
                await page.goto(url, wait_until="commit", timeout=60000)
            except Exception:
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


async def wait_for_context_pages(
    context: Any, timeout: float = 30.0, poll_interval: float = 0.5
) -> Optional[Any]:
    """等待 CDP 连接后浏览器上下文出现至少一个可用标签页"""
    if context is None or not hasattr(context, "pages"):
        return None

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        pages = [p for p in context.pages if not p.is_closed()]
        if pages:
            return pages[0]
        await asyncio.sleep(poll_interval)
    return None


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


def _is_boss_login_url(url: str, login_url: str = "") -> bool:
    """是否为 BOSS 直聘登录页"""
    url = (url or "").lower()
    if "about:blank" in url or "zhipin.com" not in url:
        return False
    if "/web/user" in url or "login.zhipin.com" in url:
        return True
    hint = (login_url or "").split("?")[0].rstrip("/").lower()
    return bool(hint and hint in url)


async def ensure_zhipin_login_page(context: Any, login_url: str) -> Any:
    """
    在已有标签页打开 BOSS 登录页（不 new_page，避免触发反爬 & 焦点切到 blank 标签）
    """
    if context is None:
        return None

    await apply_stealth_context(context)
    await wait_for_context_pages(context, timeout=15.0)

    live = [p for p in context.pages if not p.is_closed()]
    page = live[0] if live else None
    if page is None:
        try:
            page = await context.new_page()
        except Exception:
            return None

    login_hint = login_url or "https://www.zhipin.com/web/user/?ka=header-login"
    for attempt in range(5):
        try:
            await page.goto(
                login_hint,
                wait_until="domcontentloaded",
                timeout=60000,
                referer="https://www.zhipin.com/",
            )
            await asyncio.sleep(3.0)
        except Exception:
            await navigate_page(page, login_hint, wait_seconds=2.0, focus=False)

        url = await get_page_url(page)
        if _is_boss_login_url(url, login_url):
            if hasattr(page, "bring_to_front"):
                try:
                    await page.bring_to_front()
                except Exception:
                    pass
            return page
        if "zhipin.com" in url and not _is_blank_url(url):
            return page
        await asyncio.sleep(2.0)

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


async def click_next_page_playwright(page: Any) -> bool:
    """BOSS 直聘翻页：优先改 URL 参数，其次点击分页按钮"""
    if page is None:
        return False

    from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

    current_url = await get_page_url(page)
    if "zhipin.com" in current_url and "/jobs" in current_url:
        parsed = urlparse(current_url)
        qs = parse_qs(parsed.query, keep_blank_values=True)
        current_page = int((qs.get("page") or ["1"])[0])
        qs["page"] = [str(current_page + 1)]
        flat_qs = {k: v[0] if len(v) == 1 else v for k, v in qs.items()}
        new_query = urlencode(flat_qs, doseq=True)
        new_url = urlunparse(parsed._replace(query=new_query))
        await navigate_page(page, new_url, wait_seconds=2.5)
        return True

    selectors = (
        ".options-pages a.next",
        ".options-pages .next",
        "div.turn-page a.next",
        ".pagination a.next",
    )
    for sel in selectors:
        try:
            if hasattr(page, "locator"):
                loc = page.locator(sel).first
                if await loc.count() > 0:
                    await loc.click(timeout=3000)
                    await asyncio.sleep(2)
                    return True
            elif hasattr(page, "query_selector"):
                el = await page.query_selector(sel)
                if el:
                    await el.click()
                    await asyncio.sleep(2)
                    return True
        except Exception:
            continue
    return False


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


_SCROLL_LAZY_CONTENT_JS = """
async ({ steps, pauseMs }) => {
  const pickScrollEl = () => {
    const selectors = [
      '.job-list-box',
      '.search-job-result',
      '.job-list',
      '.rec-job-list',
    ];
    for (const sel of selectors) {
      const el = document.querySelector(sel);
      if (el && el.scrollHeight > el.clientHeight + 80) {
        return el;
      }
    }
    return document.scrollingElement || document.documentElement || document.body;
  };

  const el = pickScrollEl();
  const viewHeight = el.clientHeight || window.innerHeight || 600;
  const step = Math.max(viewHeight * 0.75, 350);

  for (let i = 0; i < steps; i++) {
    el.scrollBy(0, step);
    window.scrollBy(0, Math.round(step * 0.25));
    await new Promise((resolve) => setTimeout(resolve, pauseMs));
  }

  el.scrollTo(0, 0);
  window.scrollTo(0, 0);
  await new Promise((resolve) => setTimeout(resolve, 300));
  return true;
}
"""


async def scroll_to_load_lazy_content(
    page: Any,
    steps: int = 6,
    pause: float = 0.6,
) -> bool:
    """用鼠标滚轮分步滚动岗位列表，触发 BOSS 懒加载（比 scrollBy 更接近人工操作）"""
    if page is None:
        return False

    await asyncio.sleep(0.4)
    list_selectors = (
        ".job-list-box",
        ".search-job-result",
        ".job-list",
        ".rec-job-list",
    )
    scrolled = False

    if hasattr(page, "locator") and hasattr(page, "mouse"):
        for sel in list_selectors:
            try:
                loc = page.locator(sel).first
                if await loc.count() == 0:
                    continue
                box = await loc.bounding_box()
                if not box:
                    continue
                cx = box["x"] + box["width"] / 2
                cy = box["y"] + min(box["height"] / 2, 420)
                await page.mouse.move(cx, cy)
                for _ in range(max(1, steps)):
                    await page.mouse.wheel(0, 700)
                    await asyncio.sleep(pause)
                scrolled = True
                break
            except Exception:
                continue

        if not scrolled:
            try:
                viewport = page.viewport_size or {"width": 1280, "height": 720}
                await page.mouse.move(
                    viewport["width"] // 2,
                    viewport["height"] // 2,
                )
                for _ in range(max(1, steps)):
                    await page.mouse.wheel(0, 700)
                    await asyncio.sleep(pause)
                scrolled = True
            except Exception:
                pass

    if not scrolled and hasattr(page, "evaluate"):
        try:
            await page.evaluate(
                _SCROLL_LAZY_CONTENT_JS,
                {"steps": max(1, steps), "pauseMs": int(max(pause, 0.3) * 1000)},
            )
            scrolled = True
        except Exception:
            for _ in range(max(1, steps)):
                await scroll_page(page)
                await asyncio.sleep(pause)
            scrolled = True

    if hasattr(page, "evaluate"):
        try:
            await page.evaluate(
                """
                () => {
                  for (const sel of ['.job-list-box', '.search-job-result', '.job-list']) {
                    const el = document.querySelector(sel);
                    if (el) el.scrollTop = 0;
                  }
                  window.scrollTo(0, 0);
                }
                """
            )
        except Exception:
            pass

    await asyncio.sleep(0.5)
    return scrolled


async def count_job_cards(page: Any) -> int:
    """统计当前页面可见岗位卡片数量"""
    if page is None or not hasattr(page, "evaluate"):
        return 0
    try:
        return int(
            await page.evaluate(
                """
                () => {
                  const sels = ['.job-card-wrapper', '.job-card-box', '.job-list-box .job-card'];
                  for (const sel of sels) {
                    const n = document.querySelectorAll(sel).length;
                    if (n > 0) return n;
                  }
                  return 0;
                }
                """
            )
        )
    except Exception:
        return 0


async def wait_for_job_cards(
    page: Any,
    min_count: int = 3,
    timeout: float = 30.0,
) -> bool:
    """等待岗位卡片渲染完成（避免页面只有导航栏时就开始扫描）"""
    if page is None:
        return False

    deadline = time.time() + max(1.0, timeout)
    while time.time() < deadline:
        count = await count_job_cards(page)
        if count >= min_count:
            return True
        await asyncio.sleep(1.0)
    return False


JOB_LIST_SELECTORS = (
    ".job-card-wrapper",
    ".job-list-box",
    ".search-job-result",
    ".rec-job-list",
    ".job-list",
)


async def wait_for_page_ready(page: Any, timeout: float = 30.0) -> bool:
    """等待 BOSS 岗位列表区域渲染（避免 SPA 上 networkidle 永不满足）"""
    if page is None:
        return False

    if hasattr(page, "wait_for_load_state"):
        try:
            await page.wait_for_load_state(
                "domcontentloaded",
                timeout=min(int(timeout * 1000), 15000),
            )
        except Exception:
            pass

    if hasattr(page, "wait_for_selector"):
        for sel in JOB_LIST_SELECTORS:
            try:
                await page.wait_for_selector(sel, timeout=4000)
                await asyncio.sleep(1.5)
                return True
            except Exception:
                continue

    await asyncio.sleep(3)
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


def _is_transient_page_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(
        token in msg
        for token in ("destroyed", "navigation", "execution context", "target closed")
    )


async def extract_page_text(page: Any, max_chars: int = 12000, retries: int = 3) -> str:
    """从当前页面提取可见文本（不触发 Browser Use 重新导航）"""
    if page is None:
        return ""

    last_err: Optional[Exception] = None
    for attempt in range(max(1, retries)):
        try:
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
        except Exception as e:
            last_err = e
            if _is_transient_page_error(e) and attempt < retries - 1:
                await asyncio.sleep(1.5 * (attempt + 1))
                if hasattr(page, "wait_for_load_state"):
                    try:
                        await page.wait_for_load_state("domcontentloaded", timeout=5000)
                    except Exception:
                        pass
                continue
            raise

    if last_err:
        raise last_err
    return ""


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

BOSS_STRONG_AUTH_COOKIES = frozenset({
    "wt2",
    "__zp_stoken__",
    "zp_at",
    "sid",
    "geek_zp_token",
    "bst",
})


def cookies_indicate_login(cookies: list) -> bool:
    """根据 zhipin.com 域强认证 Cookie 判断是否已登录"""
    for cookie in cookies:
        domain = cookie.get("domain", "")
        if "zhipin.com" not in domain:
            continue
        name = cookie.get("name", "")
        value = (cookie.get("value") or "").strip()
        if not value or value == "-":
            continue
        if name not in BOSS_STRONG_AUTH_COOKIES:
            continue
        min_len = 10 if name == "wt2" else 8
        if len(value) >= min_len:
            return True
    return False


async def check_login_by_cookies(context: Any, page: Any = None) -> bool:
    """
    通过 Cookie 判断 BOSS 直聘是否已登录

    以 context 中的认证 Cookie 为主；page 仅作辅助，不再因 about:blank 误判未登录。
    """
    if context is None or not hasattr(context, "cookies"):
        return False

    try:
        cookies = await context.cookies()
    except Exception:
        return False

    if not cookies_indicate_login(cookies):
        return False

    if context and hasattr(context, "pages"):
        for p in context.pages:
            try:
                if p.is_closed():
                    continue
                url = await get_page_url(p)
                if "zhipin.com" in url and "about:blank" not in url:
                    return True
            except Exception:
                continue
    return False


async def list_live_pages(browser_agent: Any) -> list:
    """列出浏览器中所有仍存活的标签页（跨 context 扫描，跳过 about:blank）"""
    pages = []
    browser = getattr(browser_agent, "_browser", None)
    contexts = []
    if browser and hasattr(browser, "contexts"):
        try:
            contexts = list(browser.contexts)
        except Exception:
            contexts = []
    ctx = getattr(browser_agent, "_playwright_context", None)
    if ctx and ctx not in contexts:
        contexts.append(ctx)

    for context in contexts:
        if not hasattr(context, "pages"):
            continue
        for p in context.pages:
            try:
                if p.is_closed():
                    continue
                url = await get_page_url(p)
                if _is_blank_url(url):
                    continue
                pages.append(p)
            except Exception:
                continue
    return pages


async def refresh_browser_page(
    browser_agent: Any, login_url: str = "", logger=None
) -> Optional[Any]:
    """
    从浏览器上下文重新获取可用页面（CDP 模式下原 page 引用常会失效）
    """
    if browser_agent is None:
        return None

    pages = await list_live_pages(browser_agent)
    if logger and not pages:
        logger.warning("Playwright 未检测到任何存活标签页（Edge 可能已关闭最后一个标签）")

    if pages:
        context = getattr(browser_agent, "_playwright_context", None)
        page = None
        if context:
            page = await pick_zhipin_page(context, login_url=login_url, focus=False)
        if page is None:
            for p in pages:
                url = await get_page_url(p)
                if "zhipin.com" in url:
                    page = p
                    break
        page = page or pages[0]
        browser_agent._page = page
        url = await get_page_url(page)
        if logger:
            logger.info(f"已刷新页面对象 | 标签数: {len(pages)} | URL: {url}")
        return page

    page = getattr(browser_agent, "_page", None)
    if page is not None:
        try:
            if not page.is_closed():
                return page
        except Exception:
            pass
    return None


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

    page = await refresh_browser_page(browser_agent, login_url, logger)
    if page is None:
        logger.error(
            "未找到可用的 BOSS 直聘页面。"
            "这通常不是 BOSS 反爬拦截，而是 Edge 最后一个标签被关闭导致浏览器退出。"
            "请重新点击「启动自动求职」，在自动化 Edge 窗口中完成登录"
        )
        return False

    elapsed = grace_period
    confirmed = 0
    context = getattr(browser_agent, "_playwright_context", None) if browser_agent else None

    while elapsed < max_wait:
        if not should_continue():
            return False

        page = await refresh_browser_page(browser_agent, login_url, logger=None)
        if page is None:
            logger.warning("页面对象暂时不可用，继续等待...")
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
            continue

        current_url = await get_page_url(page)
        if _is_blank_url(current_url) and login_url and browser_agent:
            logger.warning(
                "登录页跳转为空白页（可能被 BOSS 识别为自动化）。"
                "建议改用手动启动 Edge，正在尝试重新打开登录页..."
            )
            ctx = getattr(browser_agent, "_playwright_context", None)
            if ctx:
                page = await ensure_zhipin_login_page(ctx, login_url)
                if page:
                    browser_agent._page = page

        logged_in = False
        if context:
            logged_in, hit_page, hit_url = await scan_pages_for_login(context)
            if logged_in:
                if hit_page is not None:
                    page = hit_page
                logger.debug(f"页面内容检测到已登录 | URL: {hit_url}")
            elif await check_login_by_cookies(context, page=None):
                logged_in = True
                logger.debug("Cookie 检测到已登录")

        if logged_in:
            confirmed += 1
            logger.info(f"检测到已登录状态 ({confirmed}/{confirm_checks})")
            if confirmed >= confirm_checks:
                logger.info("登录确认完成，准备进入岗位搜索")
                if browser_agent:
                    if page is not None:
                        browser_agent._page = page
                    elif context:
                        for p in context.pages:
                            try:
                                if p.is_closed():
                                    continue
                                url = await get_page_url(p)
                                if "zhipin.com" in url and "/web/user" not in url:
                                    browser_agent._page = p
                                    break
                            except Exception:
                                continue
                    if hasattr(browser_agent, "_async_save_session"):
                        await browser_agent._async_save_session()
                    if hasattr(browser_agent, "_ensure_keeper_tab"):
                        await browser_agent._ensure_keeper_tab()
                return True
        else:
            confirmed = 0

        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

    logger.error(f"等待登录超时（{int(max_wait)} 秒），请重新启动任务")
    return False
