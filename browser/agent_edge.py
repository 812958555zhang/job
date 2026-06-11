"""
Microsoft Edge 连接模块（仅手动启动模式）

使用前请先手动启动 Edge 并开启 CDP 调试端口，程序只连接、不自动拉起浏览器。
"""

import asyncio
import socket
from typing import Optional, Tuple

from playwright.async_api import Browser, BrowserContext, Playwright

from browser.agent_helpers import apply_stealth_context
from utils.logger import get_logger

_logger = get_logger(__name__)

EDGE_DEBUG_PORT = 9222
MANUAL_CDP_WAIT_SECONDS = 15

EDGE_MANUAL_START_HINT = (
    "请先手动启动 Edge，再点击「启动自动求职」："
    r' "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" '
    f"--remote-debugging-port={EDGE_DEBUG_PORT} --remote-allow-origins=* "
    "https://www.zhipin.com/web/user/?ka=header-login"
)


def is_port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex(("localhost", port)) == 0


def check_edge_cdp_sync(port: int = EDGE_DEBUG_PORT) -> bool:
    """同步检测 Edge CDP 是否就绪（供 GUI 启动前校验）"""
    if not is_port_open(port):
        return False
    try:
        import urllib.request

        req = urllib.request.Request(
            f"http://localhost:{port}/json/version", method="GET"
        )
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


async def check_edge_cdp(port: int = EDGE_DEBUG_PORT) -> bool:
    return check_edge_cdp_sync(port)


async def connect_to_edge_cdp(
    playwright: Playwright,
    port: int = EDGE_DEBUG_PORT,
    connect_timeout: float = 20.0,
) -> Tuple[Optional[Browser], Optional[BrowserContext]]:
    """连接用户手动启动、已开启 CDP 的 Edge"""
    if not await check_edge_cdp(port):
        return None, None

    try:
        browser = await asyncio.wait_for(
            playwright.chromium.connect_over_cdp(f"http://localhost:{port}"),
            timeout=connect_timeout,
        )
        for _ in range(20):
            if browser.contexts:
                context = browser.contexts[0]
                await apply_stealth_context(context)
                _logger.info("已连接手动启动的 Microsoft Edge（CDP 端口 %s）", port)
                return browser, context
            await asyncio.sleep(0.5)
        await browser.close()
        return None, None
    except Exception as exc:
        _logger.warning("连接 Edge CDP 失败: %s", exc)
        return None, None


async def get_or_launch_edge(
    playwright: Playwright,
    port: int = EDGE_DEBUG_PORT,
    auto_launch: bool = True,
    prefer_manual_cdp: bool = True,
) -> Tuple[Optional[Browser], Optional[BrowserContext], Optional[object]]:
    """
    连接手动启动的 Edge（仅 CDP，不自动启动浏览器）

    auto_launch / prefer_manual_cdp 参数保留兼容，但不再自动拉起 Edge。
    """
    del auto_launch, prefer_manual_cdp

    _logger.info(
        "等待手动 Edge（CDP 端口 %s，最多 %ss）...",
        port,
        MANUAL_CDP_WAIT_SECONDS,
    )
    _logger.info(EDGE_MANUAL_START_HINT)

    for elapsed in range(MANUAL_CDP_WAIT_SECONDS):
        if await check_edge_cdp(port):
            browser, context = await connect_to_edge_cdp(playwright, port)
            if context:
                return browser, context, None
        if elapsed > 0 and elapsed % 10 == 0:
            _logger.info("仍在等待 Edge CDP（已等待 %ss）...", elapsed)
        await asyncio.sleep(1)

    _logger.error(
        "未检测到 Edge CDP（端口 %s）。请按上述命令手动启动 Edge 后重试。",
        port,
    )
    return None, None, None


async def close_edge_browser(
    browser: Optional[Browser],
    proc: Optional[object],
) -> None:
    """断开 Playwright 与 Edge 的连接（不关闭用户 Edge 窗口）"""
    if browser:
        try:
            await browser.close()
        except Exception:
            pass
