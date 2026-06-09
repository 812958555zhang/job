"""
浏览器会话管理器模块（增强版）

提供完整的浏览器会话生命周期管理能力，包括：
- Cookie 持久化与恢复（支持标签页 URL 记录）
- 多标签页创建、切换、关闭
- BOSS 直聘登录状态检测（多维度判断）
- 登录过期回调机制（观察者模式）

与 browser/agent.py 中的 BrowserAgent 协同工作，
通过 BrowserAgent 实例访问底层 Playwright 浏览器对象。
"""

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from playwright.async_api import BrowserContext, Page

from utils.logger import get_logger


# ============================================================
# 默认配置常量
# ============================================================

DEFAULT_CONFIG: Dict[str, Any] = {
    "cookie_storage_path": "data/browser_cookies.json",
    "auto_save_session": True,
    "session_timeout": 3600,
    "max_tabs": 10,
}

# BOSS 直聘登录相关标识
LOGIN_URL_PATTERNS = ["/login", "/passport", "/sso"]
LOGIN_COOKIE_KEYS = ["__zp_stoken__", "__zp_sid__"]
LOGIN_DOM_SELECTORS = [
    '[class*="user"]',
    '[class*="avatar"]',
    '[class*="nickname"]',
    '[data-selector="user-card"]',
]


class SessionManager:
    """
    增强版浏览器会话管理器

    管理浏览器登录态持久化、多标签页操作、登录状态监控。
    支持观察者模式的登录过期回调，便于 GUI 层及时响应会话失效。

    使用示例::

        >>> from browser.agent import BrowserAgent
        >>> agent = BrowserAgent()
        >>> sm = SessionManager(agent)
        >>> sm.register_login_expired_callback(lambda msg: print(f"告警: {msg}"))
        >>> is_logged = sm.check_login_status()
        >>> new_page = sm.create_tab("https://www.zhipin.com/")
    """

    def __init__(self, browser_agent: Any, config: Optional[Dict[str, Any]] = None):
        """
        初始化增强版会话管理器

        Args:
            browser_agent: BrowserAgent 实例，用于访问底层浏览器上下文和页面对象
            config: 自定义配置字典，可选覆盖默认配置参数
        """
        self._agent = browser_agent
        self._logger = get_logger(f"{__name__}.SessionManager")

        # 合并配置：外部传入 > 默认值
        self._config = {**DEFAULT_CONFIG}
        if config:
            self._config.update(config)

        # Cookie 存储路径处理
        cookie_path = self._config.get("cookie_storage_path", DEFAULT_CONFIG["cookie_storage_path"])
        self._cookie_path = Path(cookie_path)
        self._cookie_path.parent.mkdir(parents=True, exist_ok=True)

        # 登录过期回调列表（观察者模式）
        self._login_expired_callbacks: List[Callable[[str], None]] = []

        # 上一次登录状态缓存（用于检测状态变化）
        self._last_login_status: Optional[bool] = None

        self._logger.info(
            f"✓ SessionManager 初始化完成 | "
            f"Cookie 路径: {self._cookie_path} | "
            f"最大标签页: {self._config['max_tabs']}"
        )

    # ----------------------------------------------------------
    # 会话持久化方法
    # ----------------------------------------------------------

    def save_session(self) -> bool:
        """
        保存当前浏览器会话到本地文件

        同时保存 Cookie 和当前打开的标签页 URL 列表，
        以便后续恢复时还原完整的浏览环境。

        Returns:
            bool: 保存成功返回 True，失败返回 False
        """
        try:
            context = self._get_context()
            if not context:
                self._logger.warning("无法保存会话：浏览器上下文不可用")
                return False

            import asyncio

            # 异步获取 Cookie 和页面信息
            loop = asyncio.new_event_loop()
            try:
                cookies = loop.run_until_complete(context.cookies())
                pages = context.pages
                tab_urls = []
                for page in pages:
                    url = loop.run_until_complete(page.url)
                    if url and url != "about:blank":
                        tab_urls.append(url)
            finally:
                loop.close()

            # 构建会话数据结构
            session_data = {
                "cookies": cookies,
                "tab_urls": tab_urls,
                "saved_at": __import__("datetime").datetime.now().isoformat(),
            }

            # 写入 JSON 文件
            with open(self._cookie_path, "w", encoding="utf-8") as f:
                json.dump(session_data, f, ensure_ascii=False, indent=2)

            self._logger.info(
                f"✓ 会话已保存 | Cookie: {len(cookies)} 条 | 标签页: {len(tab_urls)} 个"
            )
            return True

        except Exception as e:
            self._logger.error(f"保存会话失败: {e}", exc_info=True)
            return False

    def restore_session(self) -> bool:
        """
        从本地文件恢复浏览器会话

        恢复之前保存的 Cookie 到当前浏览器上下文，
        并尝试打开之前保存的标签页 URL。

        Returns:
            bool: 恢复成功返回 True，失败或无数据返回 False
        """
        try:
            if not self._cookie_path.exists():
                self._logger.debug("会话文件不存在，跳过恢复")
                return False

            # 读取会话数据
            with open(self._cookie_path, "r", encoding="utf-8") as f:
                session_data = json.load(f)

            context = self._get_context()
            if not context:
                self._logger.warning("无法恢复会话：浏览器上下文不可用")
                return False

            import asyncio

            loop = asyncio.new_event_loop()
            try:
                # 恢复 Cookie
                cookies = session_data.get("cookies", [])
                if cookies:
                    loop.run_until_complete(context.add_cookies(cookies))
                    self._logger.info(f"✓ 已恢复 Cookie（共 {len(cookies)} 条）")

                # 尝试恢复标签页（可选）
                tab_urls = session_data.get("tab_urls", [])
                restored_count = 0
                max_restore = min(len(tab_urls), self._config.get("max_tabs", 5))
                for i in range(max_restore):
                    try:
                        new_page = loop.run_until_complete(context.new_page())
                        loop.run_until_complete(new_page.goto(tab_urls[i], wait_until="domcontentloaded"))
                        restored_count += 1
                    except Exception as tab_e:
                        self._logger.warning(f"恢复标签页 {tab_urls[i]} 失败: {tab_e}")

                if restored_count > 0:
                    self._logger.info(f"✓ 已恢复 {restored_count} 个标签页")

            finally:
                loop.close()

            self._logger.info("✓ 会话恢复完成")
            return True

        except json.JSONDecodeError as e:
            self._logger.warning(f"会话文件格式错误，无法恢复: {e}")
            return False
        except Exception as e:
            self._logger.error(f"恢复会话失败: {e}", exc_info=True)
            return False

    # ----------------------------------------------------------
    # 登录状态检测
    # ----------------------------------------------------------

    def check_login_status(self) -> bool:
        """
        检测当前 BOSS 直聘登录状态

        通过三种方式综合判断：
        a. 检查页面 URL 是否包含登录相关路径
        b. 检查页面 DOM 是否存在用户头像/用户名等元素
        c. 检查 Cookie 中是否存在关键登录 Cookie

        如果检测到从"已登录"变为"未登录"，自动触发登录过期回调。

        Returns:
            bool: 已登录返回 True，未登录或检测失败返回 False
        """
        try:
            current_status = self._do_login_check()

            # 检测登录状态变化（从已登录变为未登录）
            if (
                self._last_login_status is True
                and current_status is False
            ):
                msg = "检测到 BOSS 直聘登录状态已失效"
                self._logger.warning(f"⚠️ {msg}")
                self._trigger_login_expired_callbacks(msg)

            self._last_login_status = current_status
            return current_status

        except Exception as e:
            self._logger.warning(f"检测登录状态时发生异常: {e}")
            return False

    def _do_login_check(self) -> bool:
        """
        执行实际的登录状态检测逻辑（内部方法）

        通过 URL、DOM、Cookie 三重校验综合判断登录状态。

        Returns:
            bool: 已登录返回 True，否则返回 False
        """
        page = self._get_active_page()
        context = self._get_context()

        if not page and not context:
            self._logger.warning("无法检测登录状态：页面和上下文均不可用")
            return False

        import asyncio

        loop = asyncio.new_event_loop()
        try:
            # 方式a：检查 URL 是否包含登录路径
            if page:
                current_url = loop.run_until_complete(page.url)
                for pattern in LOGIN_URL_PATTERNS:
                    if pattern in current_url:
                        self._logger.debug(f"URL 包含登录路径 '{pattern}'，判定为未登录")
                        return False

            # 方式b：检查 DOM 中是否存在用户元素
            if page:
                dom_login = False
                for selector in LOGIN_DOM_SELECTORS:
                    try:
                        element = loop.run_until_complete(page.query_selector(selector))
                        if element:
                            dom_login = True
                            break
                    except Exception:
                        continue

                if not dom_login:
                    # DOM 未找到用户元素，继续检查 Cookie 再做最终判断
                    self._logger.debug("DOM 中未发现用户元素，需结合 Cookie 综合判断")
                else:
                    self._logger.debug("DOM 检测到用户元素，判定为已登录")
                    # DOM 有用户元素，直接返回已登录
                    return True

            # 方式c：检查关键登录 Cookie
            if context:
                cookies = loop.run_until_complete(context.cookies())
                cookie_names = {c.get("name", "") for c in cookies}
                for key in LOGIN_COOKIE_KEYS:
                    if key in cookie_names:
                        self._logger.debug(f"Cookie 中存在关键标识 '{key}'，判定为已登录")
                        return True

            # 三种方式均未通过，判定为未登录
            self._logger.info("登录状态检测结果：未登录")
            return False

        finally:
            loop.close()

    # ----------------------------------------------------------
    # 多标签页管理
    # ----------------------------------------------------------

    def create_tab(self, url: Optional[str] = None) -> Optional[Page]:
        """
        打开新的浏览器标签页

        可选传入初始 URL，新标签页将导航至该地址。
        受最大标签页数限制约束。

        Args:
            url: 新标签页的初始 URL（可选），为空则打开空白页

        Returns:
            Page: 新创建的页面对象；超过上限或失败返回 None
        """
        try:
            context = self._get_context()
            if not context:
                self._logger.warning("无法创建标签页：浏览器上下文不可用")
                return None

            import asyncio

            loop = asyncio.new_event_loop()
            try:
                # 检查标签页数量限制
                pages = context.pages
                current_count = len(pages)
                max_tabs = self._config.get("max_tabs", DEFAULT_CONFIG["max_tabs"])

                if current_count >= max_tabs:
                    self._logger.warning(
                        f"已达到最大标签页数限制（{current_count}/{max_tabs}），无法创建新标签页"
                    )
                    return None

                # 创建新标签页
                new_page = loop.run_until_complete(context.new_page())

                # 如有指定 URL 则导航
                if url:
                    loop.run_until_complete(new_page.goto(url, wait_until="domcontentloaded"))

                new_url = loop.run_until_complete(new_page.url)
                self._logger.info(
                    f"✓ 新标签页已创建（共 {current_count + 1}/{max_tabs} 个）| URL: {new_url}"
                )
                return new_page

            finally:
                loop.close()

        except Exception as e:
            self._logger.error(f"创建标签页失败: {e}", exc_info=True)
            return None

    def switch_to_tab(self, identifier: Union[str, int]) -> Optional[Page]:
        """
        切换到指定标签页并将其设为活跃状态

        支持通过 URL（字符串匹配）或索引（整数位置）指定目标标签页。

        Args:
            identifier: 目标标签页标识符（URL 字符串或索引整数）

        Returns:
            Page: 目标页面对象；未找到或操作失败返回 None
        """
        try:
            context = self._get_context()
            if not context:
                self._logger.warning("无法切换标签页：浏览器上下文不可用")
                return None

            pages = context.pages
            target_page = None

            import asyncio

            loop = asyncio.new_event_loop()
            try:
                if isinstance(identifier, int):
                    # 通过索引定位
                    if 0 <= identifier < len(pages):
                        target_page = pages[identifier]
                    else:
                        self._logger.warning(
                            f"标签页索引越界: {identifier}（范围: 0~{len(pages) - 1}）"
                        )
                        return None

                elif isinstance(identifier, str):
                    # 通过 URL 匹配定位
                    for page in pages:
                        page_url = loop.run_until_complete(page.url)
                        if identifier in page_url:
                            target_page = page
                            break

                    if not target_page:
                        self._logger.warning(f"未找到 URL 包含 '{identifier}' 的标签页")
                        return None

                else:
                    self._logger.warning(f"不支持的标识符类型: {type(identifier)}")
                    return None

                # 将目标标签页设为活跃（bringToFront）
                loop.run_until_complete(target_page.bring_to_front())
                target_url = loop.run_until_complete(target_page.url)
                self._logger.info(f"✓ 已切换至标签页 | URL: {target_url}")
                return target_page

            finally:
                loop.close()

        except Exception as e:
            self._logger.error(f"切换标签页失败: {e}", exc_info=True)
            return None

    def close_tab(self, identifier: Union[str, int]) -> bool:
        """
        关闭指定的浏览器标签页

        支持 URL 或索引指定目标。如果关闭的是当前活跃标签页，
        自动切换到剩余标签页中的第一个。

        Args:
            identifier: 目标标签页标识符（URL 字符串或索引整数）

        Returns:
            bool: 关闭成功返回 True，失败返回 False
        """
        try:
            context = self._get_context()
            if not context:
                self._logger.warning("无法关闭标签页：浏览器上下文不可用")
                return False

            pages = list(context.pages)
            target_index = -1

            import asyncio

            loop = asyncio.new_event_loop()
            try:
                if isinstance(identifier, int):
                    if 0 <= identifier < len(pages):
                        target_index = identifier
                    else:
                        self._logger.warning(
                            f"标签页索引越界: {identifier}（范围: 0~{len(pages) - 1}）"
                        )
                        return False

                elif isinstance(identifier, str):
                    for idx, page in enumerate(pages):
                        page_url = loop.run_until_complete(page.url)
                        if identifier in page_url:
                            target_index = idx
                            break

                    if target_index == -1:
                        self._logger.warning(f"未找到 URL 包含 '{identifier}' 的标签页")
                        return False

                else:
                    self._logger.warning(f"不支持的标识符类型: {type(identifier)}")
                    return False

                # 关闭目标标签页
                target_page = pages[target_index]
                loop.run_until_complete(target_page.close())

                # 如果关闭的是活跃标签页且还有其他标签页，自动切换
                remaining = context.pages
                if len(remaining) > 0:
                    loop.run_until_complete(remaining[0].bring_to_front())

                self._logger.info(f"✓ 标签页已关闭 | 剩余: {len(remaining)} 个")
                return True

            finally:
                loop.close()

        except Exception as e:
            self._logger.error(f"关闭标签页失败: {e}", exc_info=True)
            return False

    def get_all_tabs(self) -> List[Dict[str, Any]]:
        """
        获取所有打开的标签页信息

        返回每个标签页的索引、URL 和标题，用于 GUI 层展示标签页列表。

        Returns:
            List[Dict]: 标签页信息列表，每项包含 index/url/title 字段；
                       浏览器不可用时返回空列表
        """
        result: List[Dict[str, Any]] = []

        try:
            context = self._get_context()
            if not context:
                self._logger.warning("无法获取标签页列表：浏览器上下文不可用")
                return result

            import asyncio

            loop = asyncio.new_event_loop()
            try:
                pages = context.pages
                for idx, page in enumerate(pages):
                    url = loop.run_until_complete(page.url)
                    title = loop.run_until_complete(page.title())
                    result.append({
                        "index": idx,
                        "url": url,
                        "title": title,
                    })

            finally:
                loop.close()

        except Exception as e:
            self._logger.error(f"获取标签页列表失败: {e}", exc_info=True)

        return result

    # ----------------------------------------------------------
    # 登录过期回调机制（观察者模式）
    # ----------------------------------------------------------

    def register_login_expired_callback(self, callback: Callable[[str], None]) -> None:
        """
        注册登录过期回调函数

        当 check_login_status() 检测到登录状态从"已登录"变为"未登录"时，
        会按注册顺序依次调用所有已注册的回调函数。

        回调函数签名:: def on_login_expired(message: str) -> None

        Args:
            callback: 回调函数，接收一条消息字符串作为参数
        """
        if callback not in self._login_expired_callbacks:
            self._login_expired_callbacks.append(callback)
            self._logger.debug(f"已注册登录过期回调: {callback.__qualname__}")
        else:
            self._logger.debug(f"该回调已存在，跳过重复注册: {callback.__qualname__}")

    def unregister_login_expired_callback(self, callback: Callable[[str], None]) -> None:
        """
        移除指定的登录过期回调函数

        Args:
            callback: 要移除的回调函数引用
        """
        try:
            self._login_expired_callbacks.remove(callback)
            self._logger.debug(f"已移除登录过期回调: {callback.__qualname__}")
        except ValueError:
            self._logger.debug(f"该回调未在列表中，无需移除: {callback.__qualname__}")

    def _trigger_login_expired_callbacks(self, message: str) -> None:
        """
        触发所有已注册的登录过期回调（内部方法）

        按注册顺序依次调用每个回调函数，单个回调抛出异常不影响其余回调执行。

        Args:
            message: 传递给回调函数的消息内容
        """
        for callback in self._login_expired_callbacks:
            try:
                callback(message)
            except Exception as cb_e:
                self._logger.error(
                    f"登录过期回调 {callback.__qualname__} 执行异常: {cb_e}",
                    exc_info=True,
                )

    # ----------------------------------------------------------
    # 内部辅助方法
    # ----------------------------------------------------------

    def _get_context(self) -> Optional[BrowserContext]:
        """
        获取当前浏览器上下文对象

        从 BrowserAgent 实例中提取 Playwright 的 BrowserContext。

        Returns:
            BrowserContext: 浏览器上下文实例；不可用时返回 None
        """
        try:
            if hasattr(self._agent, "_context") and self._agent._context:
                return self._agent._context
            return None
        except Exception:
            return None

    def _get_active_page(self) -> Optional[Page]:
        """
        获取当前活跃的页面对象

        从 BrowserAgent 实例中提取当前活跃的 Playwright Page。

        Returns:
            Page: 当前活跃页面对象；不可用时返回 None
        """
        try:
            if hasattr(self._agent, "_page") and self._agent._page:
                return self._agent._page
            return None
        except Exception:
            return None


# ============================================================
# 模块自测试代码（使用 Mock 对象进行单元测试）
# ============================================================

if __name__ == "__main__":
    """模块自测试代码 - 使用 Mock 浏览器对象验证 SessionManager 各项功能"""

    import sys
    import io
    from unittest.mock import MagicMock, AsyncMock, patch

    # 设置控制台输出编码为 UTF-8
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

    print("=" * 70)
    print("SessionManager 增强版 - 单元测试（Mock 浏览器对象）")
    print("=" * 70)


    class MockBrowserAgent:
        """模拟 BrowserAgent 对象，用于单元测试"""

        def __init__(self):
            # 模拟浏览器上下文
            self._context = MagicMock(spec=BrowserContext)
            self._context.pages = []

            # 模拟页面对象
            self._page = MagicMock(spec=Page)


    def test_init():
        """测试1：初始化"""
        print("\n【测试1】初始化 SessionManager...")
        mock_agent = MockBrowserAgent()
        sm = SessionManager(mock_agent)
        assert sm._config["max_tabs"] == 10
        assert len(sm._login_expired_callbacks) == 0
        print("   ✓ 初始化成功 | 默认配置正确")


    def test_custom_config():
        """测试2：自定义配置"""
        print("\n【测试2】自定义配置...")
        mock_agent = MockBrowserAgent()
        custom_cfg = {"max_tabs": 5, "session_timeout": 1800}
        sm = SessionManager(mock_agent, config=custom_cfg)
        assert sm._config["max_tabs"] == 5
        assert sm._config["session_timeout"] == 1800
        print("   ✓ 自定义配置生效")


    def test_callback_registration():
        """测试3：回调注册与注销"""
        print("\n【测试3】登录过期回调注册与注销...")

        messages_received = []

        def on_expired(msg: str) -> None:
            messages_received.append(msg)

        def on_expired2(msg: str) -> None:
            messages_received.append(f"[备用]{msg}")

        mock_agent = MockBrowserAgent()
        sm = SessionManager(mock_agent)

        # 注册两个回调
        sm.register_login_expired_callback(on_expired)
        sm.register_login_expired_callback(on_expired2)
        assert len(sm._login_expired_callbacks) == 2

        # 触发回调
        sm._trigger_login_expired_callbacks("测试过期消息")
        assert len(messages_received) == 2
        assert "测试过期消息" in messages_received[0]
        assert "[备用]测试过期消息" in messages_received[1]
        print("   ✓ 回调触发正常，按注册顺序调用")

        # 注销一个回调
        sm.unregister_login_expired_callback(on_expired)
        assert len(sm._login_expired_callbacks) == 1
        messages_received.clear()
        sm._trigger_login_expired_callbacks("再次测试")
        assert len(messages_received) == 1
        print("   ✓ 回调注销正常")


    def test_callback_exception_isolation():
        """测试4：回调异常隔离"""
        print("\n【测试4】回调异常隔离...")

        results = []

        def good_callback(msg: str) -> None:
            results.append(f"ok:{msg}")

        def bad_callback(_msg: str) -> None:
            raise RuntimeError("模拟回调异常")

        mock_agent = MockBrowserAgent()
        sm = SessionManager(mock_agent)
        sm.register_login_expired_callback(bad_callback)
        sm.register_login_expired_callback(good_callback)

        # 异常回调不应影响后续回调
        sm._trigger_login_expired_callbacks("隔离测试")
        assert len(results) == 1
        assert results[0] == "ok:隔离测试"
        print("   ✓ 异常回调不影响其他回调执行")


    def test_get_all_tabs_empty():
        """测试5：获取空标签页列表"""
        print("\n【测试5】获取空标签页列表...")
        mock_agent = MockBrowserAgent()
        sm = SessionManager(mock_agent)
        tabs = sm.get_all_tabs()
        assert tabs == []
        print("   ✓ 空标签页列表返回正常")


    def test_save_session_no_context():
        """测试6：无浏览器上下文时保存会话"""
        print("\n【测试6】无浏览器上下文时保存会话...")
        mock_agent = MockBrowserAgent()
        mock_agent._context = None  # 模拟无上下文
        sm = SessionManager(mock_agent)
        result = sm.save_session()
        assert result is False
        print("   ✓ 无上下文时返回 False")


    def test_restore_session_no_file():
        """测试7：无会话文件时恢复"""
        print("\n【测试7】无会话文件时恢复...")
        mock_agent = MockBrowserAgent()
        # 使用不存在的临时路径
        sm = SessionManager(mock_agent, config={"cookie_storage_path": "data/nonexistent_test.json"})
        result = sm.restore_session()
        assert result is False
        print("   ✓ 无文件时返回 False")


    def test_check_login_no_page():
        """测试8：无可用的页面时检测登录状态"""
        print("\n【测试8】无可用的页面时检测登录状态...")
        mock_agent = MockBrowserAgent()
        mock_agent._context = None
        mock_agent._page = None
        sm = SessionManager(mock_agent)
        result = sm.check_login_status()
        assert result is False
        print("   ✓ 无页面时返回 False")


    def test_create_tab_exceeds_limit():
        """测试9：超出标签页数量限制"""
        print("\n【测试9】超出标签页数量限制...")

        async def mock_new_page():
            p = AsyncMock(spec=Page)
            p.url = AsyncMock(return_value="about:blank")
            p.bring_to_front = AsyncMock()
            return p

        mock_agent = MockBrowserAgent()
        mock_agent._context.new_page = mock_new_page
        # 预设已有 10 个标签页（达到上限）
        mock_agent._context.pages = [AsyncMock() for _ in range(10)]

        sm = SessionManager(mock_agent, config={"max_tabs": 10})
        result = sm.create_tab("https://example.com")
        assert result is None
        print("   ✓ 达到上限时返回 None")


    def test_close_tab_by_index():
        """测试10：通过索引关闭标签页"""
        print("\n【测试10】通过索引关闭标签页...")

        mock_pages = []
        for _ in range(3):
            p = AsyncMock(spec=Page)
            p.url = AsyncMock(return_value="https://example.com")
            p.close = AsyncMock()
            mock_pages.append(p)

        mock_agent = MockBrowserAgent()
        mock_agent._context.pages = mock_pages

        sm = SessionManager(mock_agent)
        result = sm.close_tab(1)
        assert result is True
        mock_pages[1].close.assert_called_once()
        print("   ✓ 按索引关闭标签页成功")


    def test_switch_to_tab_not_found():
        """测试11：切换到不存在的标签页"""
        print("\n【测试11】切换到不存在的标签页...")

        mock_agent = MockBrowserAgent()
        sm = SessionManager(mock_agent)
        result = sm.switch_to_tab(999)
        assert result is None
        print("   ✓ 不存在的索引返回 None")


    # 执行所有测试
    tests = [
        test_init,
        test_custom_config,
        test_callback_registration,
        test_callback_exception_isolation,
        test_get_all_tabs_empty,
        test_save_session_no_context,
        test_restore_session_no_file,
        test_check_login_no_page,
        test_create_tab_exceeds_limit,
        test_close_tab_by_index,
        test_switch_to_tab_not_found,
    ]

    passed = 0
    failed = 0

    for test_func in tests:
        try:
            test_func()
            passed += 1
        except AssertionError as e:
            print(f"   ✗ 断言失败: {e}")
            failed += 1
        except Exception as e:
            print(f"   ✗ 测试异常: {e}")
            failed += 1

    print("\n" + "=" * 70)
    print(f"测试结果: ✅ {passed} 通过 | ❌ {failed} 失败 | 共 {len(tests)} 项")
    print("=" * 70)
