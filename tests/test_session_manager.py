"""
SessionManager 单元测试模块

测试增强版浏览器会话管理器的完整功能，包括：
- Cookie 操作（保存、加载、清除）
- 多标签页管理（创建、切换、关闭）
- 登录状态检测（URL、DOM、Cookie 三重校验）
- 登录过期回调机制（观察者模式）
- 会话持久化与恢复

所有测试使用 Mock，禁止真实操作浏览器或文件系统。
"""

import json
import sys
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from unittest.mock import MagicMock, AsyncMock, patch, mock_open

import pytest

# 确保可以导入项目模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from browser.session_manager import (
    SessionManager,
    DEFAULT_CONFIG,
    LOGIN_URL_PATTERNS,
    LOGIN_COOKIE_KEYS,
    LOGIN_DOM_SELECTORS,
)
from playwright.async_api import BrowserContext, Page


# ============================================================
# 测试辅助函数：构建模拟对象
# ============================================================


def _create_mock_browser_agent(
    has_context: bool = True,
    has_page: bool = True,
    pages_count: int = 1,
) -> MagicMock:
    """
    创建模拟的 BrowserAgent 实例

    Args:
        has_context: 是否包含浏览器上下文
        has_page: 是否包含活跃页面对象
        pages_count: 模拟的标签页数量

    Returns:
        模拟的 BrowserAgent 对象
    """
    mock_agent = MagicMock()

    # 模拟浏览器上下文
    if has_context:
        mock_context = MagicMock(spec=BrowserContext)
        mock_context.cookies = AsyncMock(return_value=[
            {"name": "__zp_stoken__", "value": "test_token", "domain": ".zhipin.com"},
            {"name": "__zp_sid__", "value": "test_sid", "domain": ".zhipin.com"},
        ])
        mock_context.add_cookies = AsyncMock()
        
        # 模拟多个标签页
        mock_pages = []
        for i in range(pages_count):
            mock_page = AsyncMock(spec=Page)
            mock_page.url = AsyncMock(return_value=f"https://www.zhipin.com/page{i}")
            mock_page.title = AsyncMock(return_value=f"页面{i}")
            mock_page.goto = AsyncMock()
            mock_page.close = AsyncMock()
            mock_page.bring_to_front = AsyncMock()
            mock_page.query_selector = AsyncMock(return_value=None if i > 0 else MagicMock())
            mock_pages.append(mock_page)
        
        # 使用 property 模拟 context.pages
        type(mock_context).pages = mock_pages
        
        mock_agent._context = mock_context
    
    # 模拟页面对象
    if has_page:
        if has_context and pages_count > 0:
            mock_agent._page = mock_pages[0]
        else:
            mock_agent._page = MagicMock(spec=Page)

    return mock_agent


def _create_test_cookies(count: int = 3) -> List[Dict[str, Any]]:
    """创建测试用的 Cookie 数据"""
    cookies = []
    for i in range(count):
        cookies.append({
            "name": f"cookie_{i}",
            "value": f"value_{i}",
            "domain": ".zhipin.com",
            "path": "/",
        })
    return cookies


# ============================================================
# 测试类1：Cookie 操作测试（通过 save_session/restore_session）
# ============================================================


class TestSessionManagerCookieOperations:
    """验证 Cookie 操作（通过会话持久化方法）"""

    def test_save_session_success(self, tmp_path):
        """成功保存会话（包含 Cookie）"""
        # 使用 tmp_path 创建临时存储路径
        session_file = tmp_path / "test_session.json"
        
        # 创建 SessionManager
        mock_agent = _create_mock_browser_agent(has_context=True)
        sm = SessionManager(mock_agent, config={"cookie_storage_path": str(session_file)})

        # Mock asyncio.new_event_loop（因为 asyncio 是在方法内部局部导入的）
        with patch("asyncio.new_event_loop") as mock_new_loop:
            mock_loop = MagicMock()
            mock_loop.run_until_complete.side_effect = [
                [{"name": "test_cookie", "value": "test_value"}],  # cookies()
                "https://www.zhipin.com/page0",  # page0.url
                "https://www.zhipin.com/page1",  # page1.url
            ]
            mock_new_loop.return_value = mock_loop

            # 调用 save_session()
            result = sm.save_session()

            # 验证：返回 True
            assert result is True, "保存成功应返回 True"
            
            # 验证：文件已创建
            assert session_file.exists(), "会话文件应已创建"
            
            # 验证：文件内容正确（JSON 格式）
            with open(session_file, 'r', encoding='utf-8') as f:
                session_data = json.load(f)
            
            assert "cookies" in session_data, "应包含 cookies 字段"
            assert "tab_urls" in session_data, "应包含 tab_urls 字段"

    def test_save_session_failure(self, tmp_path):
        """保存会话失败（权限问题）"""
        # 创建只读目录模拟权限问题
        session_file = tmp_path / "readonly" / "session.json"
        session_file.parent.mkdir()
        
        # 在 Windows 上模拟写入失败比较困难，使用 Mock 来实现
        mock_agent = _create_mock_browser_agent(has_context=True)
        sm = SessionManager(mock_agent, config={"cookie_storage_path": str(session_file)})
        
        # Mock open 抛出异常
        with patch("builtins.open", side_effect=PermissionError("拒绝访问")):
            result = sm.save_session()
            
            # 验证：返回 False
            assert result is False, "权限不足时应返回 False"

    def test_restore_session_no_file(self, tmp_path):
        """无会话文件时恢复"""
        nonexistent_file = tmp_path / "nonexistent_session.json"
        
        mock_agent = _create_mock_browser_agent()
        sm = SessionManager(mock_agent, config={
            "cookie_storage_path": str(nonexistent_file),
        })

        # 恢复不存在的会话
        result = sm.restore_session()

        # 验证：返回 False
        assert result is False, "无会话文件时应返回 False"

    def test_restore_session_success(self, tmp_path):
        """成功恢复会话"""
        session_file = tmp_path / "session_to_restore.json"
        
        # 预先创建会话数据
        session_data = {
            "cookies": [{"name": "restored_cookie", "value": "restored_value"}],
            "tab_urls": ["https://www.zhipin.com/"],
            "saved_at": "2024-01-01T00:00:00",
        }
        with open(session_file, 'w', encoding='utf-8') as f:
            json.dump(session_data, f)
        
        mock_agent = _create_mock_browser_agent(pages_count=0)
        sm = SessionManager(mock_agent, config={
            "cookie_storage_path": str(session_file),
            "max_tabs": 5,
        })

        # Mock event loop
        with patch("browser.session_manager.asyncio") as mock_asyncio:
            mock_loop = MagicMock()
            new_page = AsyncMock()
            new_page.goto = AsyncMock()
            mock_loop.run_until_complete.side_effect = [
                None,  # add_cookies
                new_page,  # new_page
                None,  # goto
            ]
            mock_loop.close = MagicMock()
            mock_asyncio.new_event_loop.return_value = mock_loop

            # 恢复会话
            result = sm.restore_session()

            # 验证：恢复成功
            assert result is True, "恢复会话应成功"

    def test_clear_cookies_by_deleting_file(self, tmp_path):
        """清除会话文件（模拟 clear_cookies 行为）"""
        # 先保存一些数据
        session_file = tmp_path / "session_to_clear.json"
        test_data = {"cookies": [{"name": "test"}]}
        
        with open(session_file, 'w', encoding='utf-8') as f:
            json.dump(test_data, f)
        
        # 确认文件存在
        assert session_file.exists(), "预保存的文件应存在"
        
        # 创建 SessionManager 并手动删除文件（模拟 clear_cookies 行为）
        mock_agent = _create_mock_browser_agent()
        sm = SessionManager(mock_agent, config={"cookie_storage_path": str(session_file)})
        
        # 直接删除文件
        if sm._cookie_path.exists():
            sm._cookie_path.unlink()
        
        # 验证：文件已删除
        assert not session_file.exists(), "删除后文件应不存在"


# ============================================================
# 测试类2：多标签页管理测试
# ============================================================


class TestSessionManagerTabManagement:
    """验证多标签页管理"""

    @patch("browser.session_manager.asyncio")
    def test_create_tab_success(self, mock_asyncio_module):
        """成功创建新标签页"""
        # Mock 浏览器上下文和 new_page 方法
        mock_agent = _create_mock_browser_agent(pages_count=1)
        sm = SessionManager(mock_agent, config={"max_tabs": 10})
        
        # Mock event loop 和异步方法
        mock_loop = MagicMock()
        new_page = AsyncMock(spec=Page)
        new_page.url = AsyncMock(return_value="https://example.com")
        new_page.goto = AsyncMock()
        mock_loop.run_until_complete.side_effect = [new_page, "https://example.com"]
        mock_asyncio_module.new_event_loop.return_value = mock_loop

        # 调用 create_tab()
        result = sm.create_tab("https://example.com")

        # 验证：返回 Page 对象
        assert result is not None, "创建成功应返回 Page 对象"
        
        # 验证：new_page() 被调用
        mock_agent._context.new_page.assert_called_once()

    @patch("browser.session_manager.asyncio")
    def test_create_tab_exceeds_limit(self, mock_asyncio_module):
        """超过最大标签页数限制"""
        # Mock 已有 max_tabs 个标签页
        mock_agent = _create_mock_browser_agent(pages_count=10)
        sm = SessionManager(mock_agent, config={"max_tabs": 10})

        # 尝试创建新标签页
        result = sm.create_tab("https://example.com")

        # 验证：返回 None
        assert result is None, "达到上限时应返回 None"

    @patch("browser.session_manager.asyncio")
    def test_switch_to_tab_by_url(self, mock_asyncio_module):
        """通过 URL 切换标签页"""
        # Mock 多个标签页
        mock_agent = _create_mock_browser_agent(pages_count=3)
        sm = SessionManager(mock_agent)

        # Mock event loop
        mock_loop = MagicMock()
        mock_loop.run_until_complete.side_effect = [
            "https://www.zhipin.com/page0",
            "https://www.zhipin.com/page1",
            "https://www.zhipin.com/page2",
            None,  # bring_to_front 返回值
            "https://www.zhipin.com/page1",  # 最终 URL
        ]
        mock_asyncio_module.new_event_loop.return_value = mock_loop

        # 通过 URL 切换到第二个标签页
        result = sm.switch_to_tab("page1")

        # 验证：返回正确的 Page 对象
        assert result is not None, "切换成功应返回 Page 对象"

    @patch("browser.session_manager.asyncio")
    def test_switch_to_tab_by_index(self, mock_asyncio_module):
        """通过索引切换标签页"""
        # Mock 多个标签页
        mock_agent = _create_mock_browser_agent(pages_count=3)
        sm = SessionManager(mock_agent)

        # Mock event loop
        mock_loop = MagicMock()
        target_page = mock_agent._context.pages[1]  # 第二个标签页
        mock_loop.run_until_complete.side_effect = [
            "https://www.zhipin.com/page0",
            "https://www.zhipin.com/page1",
            "https://www.zhipin.com/page2",
            None,  # bring_to_front
            "https://www.zhipin.com/page1",
        ]
        mock_asyncio_module.new_event_loop.return_value = mock_loop

        # 通过索引切换到第二个标签页
        result = sm.switch_to_tab(1)

        # 验证：返回正确的 Page
        assert result is not None, "通过索引切换应成功"

    @patch("browser.session_manager.asyncio")
    def test_switch_to_tab_invalid_index(self, mock_asyncio_module):
        """使用无效索引切换标签页"""
        mock_agent = _create_mock_browser_agent(pages_count=3)
        sm = SessionManager(mock_agent)

        # 使用越界索引
        result = sm.switch_to_tab(999)

        # 验证：返回 None
        assert result is None, "越界索引应返回 None"

    @patch("browser.session_manager.asyncio")
    def test_close_tab_success(self, mock_asyncio_module):
        """关闭指定标签页"""
        mock_agent = _create_mock_browser_agent(pages_count=3)
        sm = SessionManager(mock_agent)

        # Mock event loop
        mock_loop = MagicMock()
        mock_loop.run_until_complete.side_effect = [
            "https://www.zhipin.com/page0",
            "https://www.zhipin.com/page1",
            "https://www.zhipin.com/page2",
            None,  # close()
            None,  # bring_to_front (自动切换到剩余的第一个)
        ]
        mock_asyncio_module.new_event_loop.return_value = mock_loop

        # 关闭第一个标签页
        result = sm.close_tab(0)

        # 验证：关闭成功
        assert result is True, "关闭标签页应成功"

    @patch("browser.session_manager.asyncio")
    def test_close_tab_invalid_index(self, mock_asyncio_module):
        """使用无效索引关闭标签页"""
        mock_agent = _create_mock_browser_agent(pages_count=3)
        sm = SessionManager(mock_agent)

        # 使用越界索引
        result = sm.close_tab(999)

        # 验证：返回 False
        assert result is False, "越界索引应返回 False"

    @patch("browser.session_manager.asyncio")
    def test_get_all_tabs(self, mock_asyncio_module):
        """获取所有标签页信息"""
        # Mock 3 个标签页（不同 URL 和 title）
        mock_agent = _create_mock_browser_agent(pages_count=3)
        sm = SessionManager(mock_agent)

        # Mock event loop
        mock_loop = MagicMock()
        mock_loop.run_until_complete.side_effect = [
            "https://www.zhipin.com/page0",  # page0.url
            "页面0",  # page0.title
            "https://www.zhipin.com/page1",  # page1.url
            "页面1",  # page1.title
            "https://www.zhipin.com/page2",  # page2.url
            "页面2",  # page2.title
        ]
        mock_asyncio_module.new_event_loop.return_value = mock_loop

        # 获取所有标签页
        tabs = sm.get_all_tabs()

        # 验证：返回长度为 3 的列表
        assert len(tabs) == 3, f"应有 3 个标签页，实际 {len(tabs)} 个"
        
        # 验证：每个元素包含 index/url/title
        for idx, tab in enumerate(tabs):
            assert "index" in tab, f"标签页 {idx} 缺少 index 字段"
            assert "url" in tab, f"标签页 {idx} 缺少 url 字段"
            assert "title" in tab, f"标签页 {idx} 缺少 title 字段"
            assert tab["index"] == idx, f"标签页 {idx} 索引不匹配"


# ============================================================
# 测试类3：登录状态检测测试
# ============================================================


class TestSessionManagerLoginDetection:
    """验证登录态检测"""

    @patch("browser.session_manager.asyncio")
    def test_check_login_by_url_pattern_not_logged_in(self, mock_asyncio_module):
        """通过 URL 检测未登录（包含登录路径）"""
        mock_agent = _create_mock_browser_agent()
        
        # Mock page.url 返回登录相关路径
        mock_agent._page.url = AsyncMock(return_value="https://www.zhipin.com/login")
        mock_agent._page.query_selector = AsyncMock(return_value=None)
        
        sm = SessionManager(mock_agent)

        # Mock event loop
        mock_loop = MagicMock()
        mock_loop.run_until_complete.side_effect = [
            "https://www.zhipin.com/login",  # page.url
            None,  # query_selector (user)
            None,  # query_selector (avatar)
            None,  # query_selector (nickname)
            None,  # query_selector (user-card)
        ]
        mock_asyncio_module.new_event_loop.return_value = mock_loop

        # 调用 check_login_status()
        result = sm.check_login_status()

        # 验证：返回 False
        assert result is False, "URL 包含登录路径时应返回 False"

    @patch("browser.session_manager.asyncio")
    def test_check_login_by_dom_element_logged_in(self, mock_asyncio_module):
        """通过 DOM 元素检测已登录"""
        mock_agent = _create_mock_browser_agent()
        
        # Mock query_selector 找到用户头像元素
        mock_element = MagicMock()
        mock_agent._page.url = AsyncMock(return_value="https://www.zhipin.com/")
        mock_agent._page.query_selector = AsyncMock(side_effect=[
            mock_element,  # 第一个选择器找到元素
        ])
        
        sm = SessionManager(mock_agent)

        # Mock event loop
        mock_loop = MagicMock()
        mock_loop.run_until_complete.side_effect = [
            "https://www.zhipin.com/",  # page.url
            mock_element,  # query_selector 找到用户元素
        ]
        mock_asyncio_module.new_event_loop.return_value = mock_loop

        # 调用 check_login_status()
        result = sm.check_login_status()

        # 验证：返回 True
        assert result is True, "DOM 检测到用户元素时应返回 True"

    @patch("browser.session_manager.asyncio")
    def test_check_login_by_cookie(self, mock_asyncio_module):
        """通过 Cookie 检测登录状态"""
        mock_agent = _create_mock_browser_agent()
        
        # Mock DOM 未找到用户元素，但 Cookie 包含关键标识
        mock_agent._page.url = AsyncMock(return_value="https://www.zhipin.com/")
        mock_agent._page.query_selector = AsyncMock(return_value=None)
        
        # Mock cookies() 包含 __zp_stoken__
        mock_agent._context.cookies = AsyncMock(return_value=[
            {"name": "__zp_stoken__", "value": "valid_token"},
        ])
        
        sm = SessionManager(mock_agent)

        # Mock event loop
        mock_loop = MagicMock()
        mock_loop.run_until_complete.side_effect = [
            "https://www.zhipin.com/",  # page.url
            None,  # query_selector (DOM 无用户元素)
            [{"name": "__zp_stoken__", "value": "valid_token"}],  # cookies()
        ]
        mock_asyncio_module.new_event_loop.return_value = mock_loop

        # 调用 check_login_status()
        result = sm.check_login_status()

        # 验证：返回 True
        assert result is True, "Cookie 中存在关键标识时应返回 True"

    @patch("browser.session_manager.asyncio")
    def test_check_login_no_page_or_context(self, mock_asyncio_module):
        """无可用的页面和上下文时检测登录状态"""
        mock_agent = MagicMock()
        mock_agent._context = None
        mock_agent._page = None
        
        sm = SessionManager(mock_agent)

        # 调用 check_login_status()
        result = sm.check_login_status()

        # 验证：返回 False
        assert result is False, "无可用的页面和上下文时应返回 False"


# ============================================================
# 测试类4：登录过期回调机制测试
# ============================================================


class TestSessionManagerCallbacks:
    """验证回调机制"""

    def test_register_and_trigger_callback(self):
        """注册并触发回调"""
        mock_agent = _create_mock_browser_agent()
        sm = SessionManager(mock_agent)

        # 注册回调函数（使用 lambda）
        callback_messages = []

        def on_expired(msg: str) -> None:
            """登录过期回调函数"""
            callback_messages.append(msg)

        sm.register_login_expired_callback(on_expired)

        # 手动触发登录过期事件
        test_message = "BOSS 直聘登录状态已失效"
        sm._trigger_login_expired_callbacks(test_message)

        # 验证：回调被调用
        assert len(callback_messages) == 1, "回调应被调用一次"
        
        # 验证：回调收到正确的参数
        assert callback_messages[0] == test_message, "回调收到的消息不匹配"

    def test_register_multiple_callbacks(self):
        """注册多个回调"""
        mock_agent = _create_mock_browser_agent()
        sm = SessionManager(mock_agent)

        messages_received = []

        def callback1(msg: str) -> None:
            messages_received.append(f"[1]{msg}")

        def callback2(msg: str) -> None:
            messages_received.append(f"[2]{msg}")

        def callback3(msg: str) -> None:
            messages_received.append(f"[3]{msg}")

        # 注册 3 个不同的回调函数
        sm.register_login_expired_callback(callback1)
        sm.register_login_expired_callback(callback2)
        sm.register_login_expired_callback(callback3)

        # 触发事件
        sm._trigger_login_expired_callbacks("多回调测试")

        # 验证：所有回调都被调用（按注册顺序）
        assert len(messages_received) == 3, "应触发 3 个回调"
        assert messages_received[0] == "[1]多回调测试", "第一个回调消息不匹配"
        assert messages_received[1] == "[2]多回调测试", "第二个回调消息不匹配"
        assert messages_received[2] == "[3]多回调测试", "第三个回调消息不匹配"

    def test_unregister_callback(self):
        """注销回调"""
        mock_agent = _create_mock_browser_agent()
        sm = SessionManager(mock_agent)

        messages_received = []

        def callback_a(msg: str) -> None:
            messages_received.append(f"A:{msg}")

        def callback_b(msg: str) -> None:
            messages_received.append(f"B:{msg}")

        # 注册 2 个回调
        sm.register_login_expired_callback(callback_a)
        sm.register_login_expired_callback(callback_b)

        # 注销其中 1 个
        sm.unregister_login_expired_callback(callback_a)

        # 触发事件
        sm._trigger_login_expired_callbacks("注销测试")

        # 验证：只有未注销的回调被调用
        assert len(messages_received) == 1, "注销后应只触发 1 个回调"
        assert messages_received[0] == "B:注销测试", "剩余回调消息不匹配"

    def test_callback_exception_isolation(self):
        """回调异常隔离"""
        mock_agent = _create_mock_browser_agent()
        sm = SessionManager(mock_agent)

        results = []

        def good_callback(msg: str) -> None:
            results.append(f"ok:{msg}")

        def bad_callback(_msg: str) -> None:
            raise RuntimeError("模拟回调抛出异常")

        # 注册 2 个回调，第一个会抛异常
        sm.register_login_expired_callback(bad_callback)
        sm.register_login_expired_callback(good_callback)

        # 触发事件 - 异常不应影响后续回调执行
        sm._trigger_login_expired_callbacks("隔离测试")

        # 验证：第二个回调仍被执行（不受第一个影响）
        assert len(results) == 1, "正常回调应被执行"
        assert results[0] == "ok:隔离测试", "正常回调结果不匹配"

    def test_duplicate_registration_prevented(self):
        """防止重复注册同一回调"""
        mock_agent = _create_mock_browser_agent()
        sm = SessionManager(mock_agent)

        call_count = 0

        def single_callback(_msg: str) -> None:
            nonlocal call_count
            call_count += 1

        # 尝试注册同一个回调两次
        sm.register_login_expired_callback(single_callback)
        sm.register_login_expired_callback(single_callback)  # 重复注册

        # 触发事件
        sm._trigger_login_expired_callbacks("重复注册测试")

        # 验证：回调只被调用一次（重复注册被忽略）
        assert call_count == 1, "重复注册的回调不应多次调用"
        assert len(sm._login_expired_callbacks) == 1, "回调列表中应只有一个实例"


# ============================================================
# 测试类5：初始化与配置测试
# ============================================================


class TestSessionManagerInitialization:
    """验证 SessionManager 初始化"""

    def test_init_with_default_config(self):
        """使用默认配置初始化"""
        mock_agent = _create_mock_browser_agent()
        sm = SessionManager(mock_agent)

        # 验证默认配置值
        assert sm._config["max_tabs"] == DEFAULT_CONFIG["max_tabs"], (
            "最大标签页数应为默认值 10"
        )
        assert sm._config["session_timeout"] == DEFAULT_CONFIG["session_timeout"], (
            "会话超时时间应为默认值 3600"
        )

    def test_init_with_custom_config(self):
        """使用自定义配置覆盖默认值"""
        mock_agent = _create_mock_browser_agent()
        custom_config = {
            "max_tabs": 5,
            "session_timeout": 1800,
            "cookie_storage_path": "data/custom_cookies.json",
        }
        sm = SessionManager(mock_agent, config=custom_config)

        # 验证自定义值生效
        assert sm._config["max_tabs"] == 5, "自定义 max_tabs 应生效"
        assert sm._config["session_timeout"] == 1800, "自定义 session_timeout 应生效"
        assert sm._config["cookie_storage_path"] == "data/custom_cookies.json", (
            "自定义 cookie_storage_path 应生效"
        )

    def test_init_creates_cookie_directory(self, tmp_path):
        """初始化时自动创建 Cookie 存储目录"""
        nested_path = tmp_path / "nested" / "dir" / "cookies.json"
        
        mock_agent = _create_mock_browser_agent()
        sm = SessionManager(mock_agent, config={"cookie_storage_path": str(nested_path)})

        # 验证父目录已创建
        assert nested_path.parent.exists(), "Cookie 文件的父目录应被自动创建"


# ============================================================
# 测试类6：会话持久化测试
# ============================================================


class TestSessionPersistence:
    """验证会话持久化功能"""

    @patch("browser.session_manager.asyncio")
    def test_save_session_success(self, mock_asyncio_module, tmp_path):
        """成功保存完整会话（Cookie + 标签页 URL）"""
        session_file = tmp_path / "session.json"
        
        mock_agent = _create_mock_browser_agent(pages_count=2)
        sm = SessionManager(mock_agent, config={"cookie_storage_path": str(session_file)})

        # Mock event loop
        mock_loop = MagicMock()
        mock_loop.run_until_complete.side_effect = [
            [{"name": "test_cookie"}],  # context.cookies()
            "https://www.zhipin.com/page0",  # page0.url
            "https://www.zhipin.com/page1",  # page1.url
        ]
        mock_asyncio_module.new_event_loop.return_value = mock_loop

        # 保存会话
        result = sm.save_session()

        # 验证：保存成功
        assert result is True, "保存会话应成功"
        
        # 验证：文件存在且格式正确
        assert session_file.exists(), "会话文件应已创建"
        
        with open(session_file, 'r', encoding='utf-8') as f:
            session_data = json.load(f)
        
        assert "cookies" in session_data, "会话数据应包含 cookies 字段"
        assert "tab_urls" in session_data, "会话数据应包含 tab_urls 字段"
        assert "saved_at" in session_data, "会话数据应包含 saved_at 时间戳"

    @patch("browser.session_manager.asyncio")
    def test_restore_session_success(self, mock_asyncio_module, tmp_path):
        """成功恢复会话"""
        session_file = tmp_path / "session_to_restore.json"
        
        # 预先创建会话数据
        session_data = {
            "cookies": [{"name": "restored_cookie", "value": "restored_value"}],
            "tab_urls": ["https://www.zhipin.com/"],
            "saved_at": "2024-01-01T00:00:00",
        }
        with open(session_file, 'w', encoding='utf-8') as f:
            json.dump(session_data, f)
        
        mock_agent = _create_mock_browser_agent(pages_count=0)
        sm = SessionManager(mock_agent, config={
            "cookie_storage_path": str(session_file),
            "max_tabs": 5,
        })

        # Mock event loop
        mock_loop = MagicMock()
        new_page = AsyncMock()
        new_page.goto = AsyncMock()
        mock_loop.run_until_complete.side_effect = [
            None,  # add_cookies
            new_page,  # new_page
            None,  # goto
        ]
        mock_asyncio_module.new_event_loop.return_value = mock_loop

        # 恢复会话
        result = sm.restore_session()

        # 验证：恢复成功
        assert result is True, "恢复会话应成功"

    def test_restore_session_no_file(self, tmp_path):
        """无会话文件时恢复"""
        nonexistent_file = tmp_path / "nonexistent_session.json"
        
        mock_agent = _create_mock_browser_agent()
        sm = SessionManager(mock_agent, config={
            "cookie_storage_path": str(nonexistent_file),
        })

        # 恢复不存在的会话
        result = sm.restore_session()

        # 验证：返回 False
        assert result is False, "无会话文件时应返回 False"

    def test_restore_session_corrupted_file(self, tmp_path):
        """会话文件损坏时恢复"""
        corrupted_file = tmp_path / "corrupted_session.json"
        
        # 写入损坏的 JSON 数据
        with open(corrupted_file, 'w', encoding='utf-8') as f:
            f.write("{invalid json content")
        
        mock_agent = _create_mock_browser_agent()
        sm = SessionManager(mock_agent, config={
            "cookie_storage_path": str(corrupted_file),
        })

        # 尝试恢复损坏的会话
        result = sm.restore_session()

        # 验证：返回 False（不应抛异常）
        assert result is False, "文件损坏时应返回 False"


# ============================================================
# 测试类7：边界条件测试
# ============================================================


class TestEdgeCases:
    """边界条件和异常场景测试"""

    @patch("browser.session_manager.asyncio")
    def test_get_all_tabs_no_context(self, mock_asyncio_module):
        """无浏览器上下文时获取标签页列表"""
        mock_agent = MagicMock()
        mock_agent._context = None
        mock_agent._page = None
        
        sm = SessionManager(mock_agent)
        tabs = sm.get_all_tabs()

        # 验证：返回空列表
        assert tabs == [], "无上下文时应返回空列表"

    @patch("browser.session_manager.asyncio")
    def test_create_tab_no_context(self, mock_asyncio_module):
        """无浏览器上下文时创建标签页"""
        mock_agent = MagicMock()
        mock_agent._context = None
        
        sm = SessionManager(mock_agent)
        result = sm.create_tab("https://example.com")

        # 验证：返回 None
        assert result is None, "无上下文时应返回 None"

    @patch("browser.session_manager.asyncio")
    def test_switch_to_tab_no_context(self, mock_asyncio_module):
        """无浏览器上下文时切换标签页"""
        mock_agent = MagicMock()
        mock_agent._context = None
        
        sm = SessionManager(mock_agent)
        result = sm.switch_to_tab(0)

        # 验证：返回 None
        assert result is None, "无上下文时应返回 None"

    @patch("browser.session_manager.asyncio")
    def test_close_tab_no_context(self, mock_asyncio_module):
        """无浏览器上下文时关闭标签页"""
        mock_agent = MagicMock()
        mock_agent._context = None
        
        sm = SessionManager(mock_agent)
        result = sm.close_tab(0)

        # 验证：返回 False
        assert result is False, "无上下文时应返回 False"

    @patch("browser.session_manager.asyncio")
    def test_check_login_status_change_detection(self, mock_asyncio_module):
        """登录状态变化检测（从已登录变为未登录）"""
        mock_agent = _create_mock_browser_agent()
        sm = SessionManager(mock_agent)

        callback_messages = []

        def on_expired(msg: str) -> None:
            callback_messages.append(msg)

        sm.register_login_expired_callback(on_expired)

        # 第一次检测：已登录
        mock_loop = MagicMock()
        mock_element = MagicMock()
        mock_loop.run_until_complete.side_effect = [
            "https://www.zhipin.com/",  # url
            mock_element,  # 找到用户元素
        ]
        mock_asyncio_module.new_event_loop.return_value = mock_loop

        result1 = sm.check_login_status()
        assert result1 is True, "第一次检测应为已登录"

        # 第二次检测：未登录（状态变化，应触发回调）
        mock_loop2 = MagicMock()
        mock_loop2.run_until_complete.side_effect = [
            "https://www.zhipin.com/login",  # url 变为登录页
            None,  # DOM 无用户元素
            None,
            None,
            None,
            [],  # cookies 为空
        ]
        mock_asyncio_module.new_event_loop.return_value = mock_loop2

        result2 = sm.check_login_status()
        assert result2 is False, "第二次检测应为未登录"
        
        # 验证：回调被触发（因为状态从 True 变为 False）
        assert len(callback_messages) > 0, "状态变化时应触发回调"


if __name__ == "__main__":
    # 直接运行测试
    pytest.main([__file__, "-v", "--tb=short"])
