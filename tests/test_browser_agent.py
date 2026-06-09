"""
BrowserAgent 单元测试模块

测试 Browser Use Agent 核心封装类的完整功能，包括：
- 初始化与配置加载
- 浏览器生命周期管理（start/stop/restart）
- 状态监控属性和健康检查
- 登录状态检测
- 随机延迟功能
- 自定义异常类
- 登录过期回调机制

所有测试使用 Mock，禁止真实启动浏览器或调用 LLM API。
"""

import asyncio
import sys
import os
import time
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock

import pytest

# 确保可以导入项目模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from browser.agent import (
    BrowserAgent,
    BrowserCrashError,
    LoginExpiredError,
    NetworkTimeoutError,
    SessionManager as SimpleSessionManager,
)


# ============================================================
# 测试辅助函数：构建模拟对象
# ============================================================


def _create_mock_agent():
    """创建模拟的 Browser Use Agent 实例"""
    mock_agent = MagicMock()
    
    # 模拟浏览器上下文
    mock_context = AsyncMock()
    mock_context.cookies = AsyncMock(return_value=[
        {"name": "test_cookie", "value": "test_value", "domain": ".zhipin.com"}
    ])
    mock_context.browser = AsyncMock()
    mock_context.new_page = AsyncMock()
    mock_agent._browser_context = mock_context
    
    # 模拟浏览器实例
    mock_browser = AsyncMock()
    mock_browser.is_connected = AsyncMock(return_value=True)
    
    # 模拟页面对象
    mock_page = AsyncMock()
    mock_page.goto = AsyncMock()
    mock_page.url = AsyncMock(return_value="https://www.zhipin.com/")
    mock_page.title = AsyncMock(return_value="BOSS直聘")
    mock_page.query_selector = AsyncMock(return_value=MagicMock())
    mock_page.evaluate = AsyncMock(
        return_value={"ready": "complete", "url": "https://www.zhipin.com/"}
    )
    
    return mock_agent, mock_browser, mock_context, mock_page


def _create_mock_config_loader(**overrides):
    """创建模拟的配置加载器，支持自定义覆盖值"""
    default_config = {
        "volcengine": {
            "api_key": "test-api-key-123456",
            "base_url": "https://ark.cn-beijing.volces.com/api/coding/v3",
            "models": {"chat": "GLM-5.1"},
        },
        "browser_use": {
            "headless": True,
        },
    }
    default_config.update(overrides)
    
    mock_loader = MagicMock()
    mock_loader.load_api_config.return_value = default_config
    mock_loader.get = lambda key, default=None: default_config.get(key, default)
    return mock_loader


# ============================================================
# 测试类1：BrowserAgent 初始化测试
# ============================================================


class TestBrowserAgentInitialization:
    """验证 BrowserAgent 初始化逻辑"""

    @patch("browser.agent.OpenAI")
    @patch("browser.agent.get_config")
    def test_init_with_default_config(self, mock_get_config, mock_openai):
        """使用默认配置初始化 BrowserAgent"""
        mock_get_config.return_value = _create_mock_config_loader()
        mock_openai.return_value = MagicMock()

        agent = BrowserAgent()

        # 验证实例创建成功
        assert agent is not None, "实例应成功创建"
        
        # 验证初始运行状态
        assert agent.is_running is False, "初始状态应为未运行"
        
        # 验证默认配置值正确加载
        assert agent._config["llm_config"]["model_name"] == "GLM-5.1", (
            "默认模型应为 GLM-5.1"
        )
        assert agent._config["browser_config"]["window_width"] == 1280, (
            "默认窗口宽度应为 1280"
        )
        assert agent._config["anti_detection"]["min_delay"] == 3.0, (
            "默认最小延迟应为 3.0s"
        )

    @patch("browser.agent.OpenAI")
    @patch("browser.agent.get_config")
    def test_init_with_custom_config(self, mock_get_config, mock_openai):
        """使用自定义配置覆盖默认值"""
        mock_get_config.return_value = _create_mock_config_loader()
        mock_openai.return_value = MagicMock()

        custom_config = {
            "error_handling": {
                "page_load_timeout": 120.0,
                "max_retry_count": 5,
            },
            "browser_config": {
                "headless": True,
                "window_width": 1920,
            },
        }

        agent = BrowserAgent(config=custom_config)

        # 验证自定义值生效
        assert agent._config["error_handling"]["page_load_timeout"] == 120.0, (
            "自定义超时时间应生效"
        )
        assert agent._config["error_handling"]["max_retry_count"] == 5, (
            "自定义最大重试次数应生效"
        )
        assert agent._config["browser_config"]["window_width"] == 1920, (
            "自定义窗口宽度应生效"
        )

    @patch("browser.agent.OpenAI")
    @patch("browser.agent.get_config")
    def test_init_without_api_key(self, mock_get_config, mock_openai):
        """API Key 未配置时的警告日志"""
        # 返回不含 api_key 的配置
        mock_get_config.return_value = _create_mock_config_loader()
        mock_get_config.return_value.load_api_config.return_value = {
            "volcengine": {},  # 无 api_key
            "browser_use": {},
        }
        mock_openai.return_value = MagicMock()

        # 验证：实例仍可创建（不抛异常）
        agent = BrowserAgent()
        assert agent is not None, "无 API Key 时也应能创建实例"

    @patch("browser.agent.OpenAI")
    @patch("browser.agent.get_config")
    def test_init_session_manager_creation(self, mock_get_config, mock_openai):
        """验证 SessionManager 被正确创建"""
        mock_get_config.return_value = _create_mock_config_loader()
        mock_openai.return_value = MagicMock()

        agent = BrowserAgent()

        # 检查 _session_manager 属性存在且类型正确
        assert hasattr(agent, "_session_manager"), "应包含 _session_manager 属性"
        assert isinstance(agent._session_manager, SimpleSessionManager), (
            "_session_manager 应为 SessionManager 实例"
        )


# ============================================================
# 测试类2：浏览器生命周期管理测试
# ============================================================


class TestBrowserAgentLifecycle:
    """验证浏览器生命周期管理（start/stop/restart）"""

    @patch("browser.agent.time.sleep")  # Mock 延迟避免实际等待
    @patch("browser.agent.Agent")
    @patch("browser.agent.OpenAI")
    @patch("browser.agent.get_config")
    def test_start_success(self, mock_get_config, mock_openai, mock_agent_class, mock_sleep):
        """成功启动浏览器"""
        mock_get_config.return_value = _create_mock_config_loader()
        mock_openai.return_value = MagicMock()

        # 配置 Mock Agent 返回值
        mock_agent_instance, mock_browser, mock_context, mock_page = _create_mock_agent()
        mock_agent_class.return_value = mock_agent_instance

        agent = BrowserAgent()
        
        # 直接 Mock _get_browser_instances 为普通方法（返回元组而非协程）
        def fake_get_instances(self):
            return (mock_browser, mock_context)
        
        # 使用 PropertyMock 模拟异步属性
        with patch.object(type(agent), '_get_browser_instances', fake_get_instances):
            with patch.object(agent, '_page', mock_page, create=True):
                with patch.object(agent, '_navigate_to_home'):  # Mock 导航方法避免异步调用
                    result = agent.start()

        # 验证：is_running == True
        assert result is True, "启动应成功"
        assert agent.is_running is True, "启动后 is_running 应为 True"
        
        # 验证：get_browser() 返回非 None
        browser = agent.get_browser()
        assert browser is not None, "get_browser() 应返回非 None"

    @patch("browser.agent.time.sleep")
    @patch("browser.agent.Agent")
    @patch("browser.agent.OpenAI")
    @patch("browser.agent.get_config")
    def test_start_already_running(self, mock_get_config, mock_openai, mock_agent_class, mock_sleep):
        """重复调用 start()"""
        mock_get_config.return_value = _create_mock_config_loader()
        mock_openai.return_value = MagicMock()
        mock_agent_class.return_value = MagicMock()

        agent = BrowserAgent()
        
        # 第一次 start() 成功
        def fake_get_instances1(self):
            return (MagicMock(), MagicMock())
        
        with patch.object(type(agent), '_get_browser_instances', fake_get_instances1):
            with patch.object(agent, '_page', MagicMock(), create=True):
                with patch.object(agent, '_navigate_to_home'):
                    first_result = agent.start()
        
        assert first_result is True, "第一次启动应成功"
        
        # 第二次 start() 应返回 True 且不重复启动
        second_result = agent.start()
        assert second_result is True, "重复调用 start() 应返回 True"
        
        # 验证 Agent 只被创建一次
        assert mock_agent_class.call_count == 1, "Agent 不应重复创建"

    @patch("browser.agent.time.sleep")
    @patch("browser.agent.Agent")
    @patch("browser.agent.OpenAI")
    @patch("browser.agent.get_config")
    def test_start_browser_crash(self, mock_get_config, mock_openai, mock_agent_class, mock_sleep):
        """启动时浏览器崩溃"""
        mock_get_config.return_value = _create_mock_config_loader()
        mock_openai.return_value = MagicMock()
        
        # Mock Agent() 抛出异常
        mock_agent_class.side_effect = RuntimeError("Chromium 进程崩溃")

        agent = BrowserAgent()

        # 验证：抛出 BrowserCrashError
        with pytest.raises(BrowserCrashError) as exc_info:
            agent.start()

        assert "崩溃" in str(exc_info.value) or "失败" in str(exc_info.value), (
            "异常消息应包含错误描述"
        )
        assert exc_info.value.original_error is not None, "应保留原始异常"
        
        # 验证：is_running == False
        assert agent.is_running is False, "崩溃后 is_running 应为 False"

    @patch("browser.agent.time.sleep")
    @patch("browser.agent.Agent")
    @patch("browser.agent.OpenAI")
    @patch("browser.agent.get_config")
    def test_start_network_timeout(self, mock_get_config, mock_openai, mock_agent_class, mock_sleep):
        """启动时网络超时"""
        mock_get_config.return_value = _create_mock_config_loader()
        mock_openai.return_value = MagicMock()
        mock_agent_class.return_value = MagicMock()

        agent = BrowserAgent()
        
        # Mock 导航操作超时（使用包含 timeout 关键字的错误消息）
        def fake_navigate_timeout(self):
            raise TimeoutError("Request timed out")
        
        def fake_get_instances2(self):
            return (AsyncMock(), AsyncMock())
        
        with patch.object(type(agent), '_get_browser_instances', fake_get_instances2):
            with patch.object(agent, '_page', AsyncMock(), create=True):
                with patch.object(type(agent), '_navigate_to_home', fake_navigate_timeout):
                    # 验证：抛出 NetworkTimeoutError
                    with pytest.raises(NetworkTimeoutError) as exc_info:
                        agent.start()

                    # 验证：timeout 属性设置正确
                    assert exc_info.value.timeout > 0, "timeout 应大于 0"

    @patch("browser.agent.OpenAI")
    @patch("browser.agent.get_config")
    def test_stop_when_not_running(self, mock_get_config, mock_openai):
        """未运行时调用 stop()"""
        mock_get_config.return_value = _create_mock_config_loader()
        mock_openai.return_value = MagicMock()

        agent = BrowserAgent()

        # 直接调用 stop() - 应不抛异常
        agent.stop()
        
        # 验证：不抛异常且状态正确
        assert agent.is_running is False, "停止后 is_running 应为 False"

    @patch("browser.agent.asyncio")
    @patch("browser.agent.time.sleep")
    @patch("browser.agent.Agent")
    @patch("browser.agent.OpenAI")
    @patch("browser.agent.get_config")
    def test_stop_success(self, mock_get_config, mock_openai, mock_agent_class, mock_sleep, mock_asyncio):
        """成功停止浏览器"""
        mock_get_config.return_value = _create_mock_config_loader()
        mock_openai.return_value = MagicMock()
        
        mock_agent_instance = MagicMock()
        mock_agent_instance.stop = AsyncMock()
        mock_agent_class.return_value = mock_agent_instance

        agent = BrowserAgent()
        
        # 先 start()
        def fake_get_instances3(self):
            return (MagicMock(), MagicMock())
        
        with patch.object(type(agent), '_get_browser_instances', fake_get_instances3):
            with patch.object(agent, '_page', MagicMock(), create=True):
                agent.start()
        
        assert agent.is_running is True, "启动后应处于运行状态"
        
        # 再 stop()
        agent.stop()
        
        # 验证：is_running == False
        assert agent.is_running is False, "停止后 is_running 应为 False"
        
        # 验证：资源释放
        assert agent._agent is None, "停止后 _agent 应为 None"
        assert agent._browser is None, "停止后 _browser 应为 None"
        assert agent._page is None, "停止后 _page 应为 None"

    @patch("browser.agent.time.sleep")
    @patch("browser.agent.BrowserAgent.start")
    @patch("browser.agent.BrowserAgent.stop")
    @patch("browser.agent.OpenAI")
    @patch("browser.agent.get_config")
    def test_restart_success(self, mock_get_config, mock_openai, mock_stop, mock_start, mock_sleep):
        """成功重启浏览器"""
        mock_get_config.return_value = _create_mock_config_loader()
        mock_openai.return_value = MagicMock()
        mock_start.return_value = True

        agent = BrowserAgent()
        
        # 执行 restart()
        result = agent.restart()

        # 验证：stop() 被调用
        mock_stop.assert_called_once()
        
        # 验证：等待 2 秒（time.sleep(2) 被调用）
        mock_sleep.assert_called_with(2)
        
        # 验证：start() 再次被调用
        mock_start.assert_called_once()
        
        # 验证：最终返回 True
        assert result is True, "重启应成功"

    @patch("browser.agent.time.sleep")
    @patch("browser.agent.BrowserAgent.start")
    @patch("browser.agent.BrowserAgent.stop")
    @patch("browser.agent.OpenAI")
    @patch("browser.agent.get_config")
    def test_restart_failure(self, mock_get_config, mock_openai, mock_stop, mock_start, mock_sleep):
        """重启失败"""
        mock_get_config.return_value = _create_mock_config_loader()
        mock_openai.return_value = MagicMock()
        
        # Mock start() 返回 False
        mock_start.return_value = False

        agent = BrowserAgent()
        
        # 调用 restart()
        result = agent.restart()

        # 验证：返回 False
        assert result is False, "重启失败应返回 False"


# ============================================================
# 测试类3：状态监控功能测试
# ============================================================


class TestBrowserAgentStatusMonitoring:
    """验证状态监控功能"""

    @patch("browser.agent.OpenAI")
    @patch("browser.agent.get_config")
    def test_is_running_property(self, mock_get_config, mock_openai):
        """验证 is_running 属性"""
        mock_get_config.return_value = _create_mock_config_loader()
        mock_openai.return_value = MagicMock()

        agent = BrowserAgent()

        # 未启动时：False
        assert agent.is_running is False, "未启动时 is_running 应为 False"

    @patch("browser.agent.OpenAI")
    @patch("browser.agent.get_config")
    def test_retry_count_property(self, mock_get_config, mock_openai):
        """验证 retry_count 属性"""
        mock_get_config.return_value = _create_mock_config_loader()
        mock_openai.return_value = MagicMock()

        agent = BrowserAgent()

        # 初始值：0
        assert agent.retry_count == 0, "初始重试次数应为 0"
        
        # 触发重试后递增
        agent._retry_count = 3
        assert agent.retry_count == 3, "重试后 retry_count 应递增"

    @patch("browser.agent.OpenAI")
    @patch("browser.agent.get_config")
    def test_last_error_property(self, mock_get_config, mock_openai):
        """验证 last_error 属性"""
        mock_get_config.return_value = _create_mock_config_loader()
        mock_openai.return_value = MagicMock()

        agent = BrowserAgent()

        # 无异常时：None
        assert agent.last_error is None, "无异常时 last_error 应为 None"
        
        # 发生异常后：返回异常对象
        test_error = RuntimeError("测试错误")
        agent._last_error = test_error
        assert agent.last_error is test_error, "last_error 应返回异常对象"

    @patch("browser.agent.OpenAI")
    @patch("browser.agent.get_config")
    def test_uptime_property(self, mock_get_config, mock_openai):
        """验证 uptime 属性"""
        mock_get_config.return_value = _create_mock_config_loader()
        mock_openai.return_value = MagicMock()

        agent = BrowserAgent()

        # 未启动时：0.0
        assert agent.uptime == 0.0, "未启动时 uptime 应为 0.0"
        
        # 启动一段时间后：正值
        agent._running = True
        agent._start_time = time.time() - 10  # 模拟已运行 10 秒
        assert agent.uptime >= 9.0, "运行后 uptime 应为正值"  # 允许 1 秒误差

    @patch("browser.agent.OpenAI")
    @patch("browser.agent.get_config")
    def test_health_check_when_not_started(self, mock_get_config, mock_openai):
        """未启动时的健康检查"""
        mock_get_config.return_value = _create_mock_config_loader()
        mock_openai.return_value = MagicMock()

        agent = BrowserAgent()
        
        # 调用 health_check()
        report = agent.health_check()

        # 验证：browser_alive == False
        assert report["browser_alive"] is False, "未启动时 browser_alive 应为 False"
        assert report["page_responsive"] is False, "未启动时 page_responsive 应为 False"
        assert report["logged_in"] is False, "未启动时 logged_in 应为 False"
        assert report["retry_count"] == 0, "重试次数应为 0"
        assert report["uptime_seconds"] == 0.0, "运行时长应为 0.0"
        assert report["last_error"] is None, "最后错误应为 None"
        assert report["is_paused"] is False, "暂停状态应为 False"

    @patch("browser.agent.OpenAI")
    @patch("browser.agent.get_config")
    def test_health_check_when_running(self, mock_get_config, mock_openai):
        """运行中的健康检查"""
        mock_get_config.return_value = _create_mock_config_loader()
        mock_openai.return_value = MagicMock()

        agent = BrowserAgent()
        
        # 模拟运行状态
        agent._running = True
        agent._start_time = time.time()
        agent._browser = AsyncMock()
        agent._browser.is_connected = AsyncMock(return_value=True)
        agent._page = AsyncMock()
        agent._page.evaluate = AsyncMock(
            return_value={"ready": "complete", "url": "https://www.zhipin.com/"}
        )
        agent._page.query_selector = AsyncMock(return_value=MagicMock())

        # 调用 health_check()（subprocess 检查可能会失败，但不影响主要验证）
        report = agent.health_check()

        # 验证：返回完整的状态字典
        assert isinstance(report, dict), "应返回字典类型"
        assert "browser_alive" in report, "报告应包含 browser_alive 字段"
        assert "page_responsive" in report, "报告应包含 page_responsive 字段"
        assert "logged_in" in report, "报告应包含 logged_in 字段"
        assert "retry_count" in report, "报告应包含 retry_count 字段"
        assert "uptime_seconds" in report, "报告应包含 uptime_seconds 字段"
        assert "last_error" in report, "报告应包含 last_error 字段"
        assert "is_paused" in report, "报告应包含 is_paused 字段"


# ============================================================
# 测试类4：登录状态检测测试
# ============================================================


class TestBrowserAgentLoginDetection:
    """验证登录态检测功能"""

    @patch("browser.agent.asyncio")
    @patch("browser.agent.OpenAI")
    @patch("browser.agent.get_config")
    def test_check_login_status_logged_in(self, mock_get_config, mock_openai, mock_asyncio_module):
        """已登录状态检测"""
        mock_get_config.return_value = _create_mock_config_loader()
        mock_openai.return_value = MagicMock()

        agent = BrowserAgent()
        agent._page = AsyncMock()
        
        # Mock 页面查询到用户元素
        mock_element = MagicMock()
        agent._page.query_selector = AsyncMock(return_value=mock_element)
        
        # Mock event loop
        mock_loop = MagicMock()
        mock_loop.run_until_complete.return_value = mock_element
        mock_asyncio_module.get_event_loop.return_value = mock_loop

        # 调用 check_login_status()
        result = agent.check_login_status()

        # 验证：返回 True
        assert result is True, "已登录时应返回 True"

    @patch("browser.agent.asyncio")
    @patch("browser.agent.OpenAI")
    @patch("browser.agent.get_config")
    def test_check_login_status_not_logged_in(self, mock_get_config, mock_openai, mock_asyncio_module):
        """未登录状态检测"""
        mock_get_config.return_value = _create_mock_config_loader()
        mock_openai.return_value = MagicMock()

        agent = BrowserAgent()
        agent._page = AsyncMock()
        
        # Mock 页面无用户元素
        agent._page.query_selector = AsyncMock(return_value=None)
        
        # Mock event loop
        mock_loop = MagicMock()
        mock_loop.run_until_complete.return_value = None
        mock_asyncio_module.get_event_loop.return_value = mock_loop

        # 调用 check_login_status() - 应抛出 LoginExpiredError
        with pytest.raises(LoginExpiredError) as exc_info:
            agent.check_login_status()

        assert "登录" in str(exc_info.value) or "过期" in str(exc_info.value), (
            "异常消息应提及登录状态"
        )

    @patch("browser.agent.OpenAI")
    @patch("browser.agent.get_config")
    def test_check_login_status_page_unavailable(self, mock_get_config, mock_openai):
        """页面不可用时检测"""
        mock_get_config.return_value = _create_mock_config_loader()
        mock_openai.return_value = MagicMock()

        agent = BrowserAgent()
        
        # page 为 None
        agent._page = None

        # 调用 check_login_status()
        result = agent.check_login_status()

        # 验证：返回 False
        assert result is False, "页面不可用时应返回 False"

    @patch("browser.agent.OpenAI")
    @patch("browser.agent.get_config")
    def test_login_expired_callback_triggered(self, mock_get_config, mock_openai):
        """登录过期回调触发"""
        mock_get_config.return_value = _create_mock_config_loader()
        mock_openai.return_value = MagicMock()

        agent = BrowserAgent()
        
        # 注册回调函数
        callback_messages = []
        
        def test_callback(msg: str) -> None:
            """测试回调函数"""
            callback_messages.append(msg)

        agent.register_login_expired_callback(test_callback)
        
        # 手动触发回调（模拟检测到登录过期）
        test_message = "BOSS 直聘登录已过期"
        agent._trigger_login_expired_callbacks(test_message)

        # 验证：回调被调用且收到正确的消息
        assert len(callback_messages) == 1, "回调应被调用一次"
        assert callback_messages[0] == test_message, "回调收到的消息应正确"


# ============================================================
# 测试类5：随机延迟功能测试
# ============================================================


class TestBrowserAgentRandomDelay:
    """验证随机延迟功能"""

    @patch("browser.agent.time.sleep")
    @patch("browser.agent.OpenAI")
    @patch("browser.agent.get_config")
    def test_random_delay_default_range(self, mock_get_config, mock_openai, mock_sleep):
        """使用配置中的默认延迟范围"""
        mock_get_config.return_value = _create_mock_config_loader()
        mock_openai.return_value = MagicMock()

        agent = BrowserAgent()

        # 调用 random_delay()
        agent.random_delay()

        # 验证：sleep 被调用一次
        mock_sleep.assert_called_once()
        
        # 验证：等待时间在 [min_delay, max_delay] 范围内
        sleep_arg = mock_sleep.call_args[0][0]
        min_delay = agent.DEFAULT_MIN_DELAY
        max_delay = agent.DEFAULT_MAX_DELAY
        assert min_delay <= sleep_arg <= max_delay, (
            f"延迟时间 {sleep_arg:.2f}s 应在 [{min_delay}, {max_delay}] 范围内"
        )

    @patch("browser.agent.time.sleep")
    @patch("browser.agent.OpenAI")
    @patch("browser.agent.get_config")
    def test_random_delay_custom_range(self, mock_get_config, mock_openai, mock_sleep):
        """使用自定义延迟范围"""
        mock_get_config.return_value = _create_mock_config_loader()
        mock_openai.return_value = MagicMock()

        agent = BrowserAgent()

        # 使用自定义范围
        agent.random_delay(min_seconds=0.1, max_seconds=0.2)

        # 验证：sleep 被调用一次
        mock_sleep.assert_called_once()
        
        # 验证：等待时间在 [0.1, 0.2] 范围内
        sleep_arg = mock_sleep.call_args[0][0]
        assert 0.1 <= sleep_arg <= 0.2, (
            f"延迟时间 {sleep_arg:.2f}s 应在 [0.1, 0.2] 范围内"
        )

    @patch("browser.agent.time.sleep")
    @patch("browser.agent.random.uniform", return_value=5.5)
    @patch("browser.agent.OpenAI")
    @patch("browser.agent.get_config")
    def test_random_delay_with_mock_sleep(self, mock_get_config, mock_openai, mock_uniform, mock_sleep):
        """验证调用了 time.sleep"""
        mock_get_config.return_value = _create_mock_config_loader()
        mock_openai.return_value = MagicMock()

        agent = BrowserAgent()

        # 调用 random_delay()
        agent.random_delay()

        # 验证：sleep 被调用一次
        mock_sleep.assert_called_once()
        
        # 验证：参数在合理范围内
        sleep_arg = mock_sleep.call_args[0][0]
        assert sleep_arg == 5.5, f"sleep 参数应为 5.5，实际为 {sleep_arg}"


# ============================================================
# 测试类6：自定义异常类测试
# ============================================================


class TestCustomExceptions:
    """验证自定义异常类"""

    def test_browser_crash_error(self):
        """BrowserCrashError 异常"""
        original_error = RuntimeError("原始错误")
        
        # 创建异常实例
        error = BrowserCrashError(
            message="浏览器进程崩溃",
            original_error=original_error
        )

        # 验证：message 正确
        assert str(error) == "浏览器进程崩溃", "异常消息应正确"
        
        # 验证：original_error 保存正确
        assert error.original_error is original_error, "original_error 应保存正确"
        
        # 验证：可以 raise 和 except
        try:
            raise error
        except BrowserCrashError as e:
            assert e is error, "捕获的异常应是同一个实例"

    def test_login_expired_error_default_message(self):
        """LoginExpiredError 默认消息"""
        error = LoginExpiredError()
        
        # 验证：默认消息正确
        assert "登录" in str(error), "默认消息应包含'登录'"
        assert "过期" in str(error), "默认消息应包含'过期'"

    def test_login_expired_error_custom_message(self):
        """LoginExpiredError 支持自定义消息"""
        custom_msg = "自定义登录过期消息"
        error = LoginExpiredError(message=custom_msg)
        
        # 验证：自定义消息生效
        assert str(error) == custom_msg, "自定义消息应生效"

    def test_network_timeout_error(self):
        """NetworkTimeoutError 异常"""
        timeout_value = 30.0
        
        # 创建异常实例
        error = NetworkTimeoutError(
            message="网络请求超时",
            timeout=timeout_value
        )

        # 验证：message 和 timeout 属性正确
        assert "超时" in str(error), "消息应包含'超时'"
        assert error.timeout == timeout_value, "timeout 属性应正确"


# ============================================================
# 测试类7：暂停/恢复机制测试
# ============================================================


class TestPauseResumeMechanism:
    """验证暂停/恢复机制"""

    @patch("browser.agent.OpenAI")
    @patch("browser.agent.get_config")
    def test_resume_when_not_paused(self, mock_get_config, mock_openai):
        """未暂停时调用 resume()"""
        mock_get_config.return_value = _create_mock_config_loader()
        mock_openai.return_value = MagicMock()

        agent = BrowserAgent()
        
        # 未暂停状态下调用 resume()
        result = agent.resume()

        # 验证：返回 True
        assert result is True, "未暂停时 resume() 应返回 True"

    @patch("browser.agent.OpenAI")
    @patch("browser.agent.get_config")
    def test_resume_when_paused(self, mock_get_config, mock_openai):
        """暂停状态下调用 resume()"""
        mock_get_config.return_value = _create_mock_config_loader()
        mock_openai.return_value = MagicMock()

        agent = BrowserAgent()
        agent._paused = True  # 设置暂停状态

        # 调用 resume()
        result = agent.resume()

        # 验证：返回 True
        assert result is True, "resume() 应成功"
        
        # 验证：暂停状态已清除
        assert agent.is_paused is False, "恢复后 is_paused 应为 False"


# ============================================================
# 测试类8：增强版登录检测测试
# ============================================================


class TestEnhancedLoginDetection:
    """验证带自动处理逻辑的登录状态检测"""

    @patch("browser.agent.BrowserAgent.check_login_status")
    @patch("browser.agent.OpenAI")
    @patch("browser.agent.get_config")
    def test_check_login_status_with_auto_handle_logged_in(self, mock_get_config, mock_openai, mock_check):
        """已登录状态的自动处理检测"""
        mock_get_config.return_value = _create_mock_config_loader()
        mock_openai.return_value = MagicMock()
        mock_check.return_value = True

        agent = BrowserAgent()
        agent._page = MagicMock()

        # 调用增强版检测
        result = agent.check_login_status_with_auto_handle()

        # 验证：返回 True
        assert result is True, "已登录时应返回 True"
        
        # 验证：未触发暂停
        assert agent.is_paused is False, "已登录时不应暂停"

    @patch("browser.agent.BrowserAgent.check_login_status")
    @patch("browser.agent.OpenAI")
    @patch("browser.agent.get_config")
    def test_check_login_status_with_auto_handle_not_logged_in(self, mock_get_config, mock_openai, mock_check):
        """未登录状态的自动处理检测"""
        mock_get_config.return_value = _create_mock_config_loader()
        mock_openai.return_value = MagicMock()
        mock_check.return_value = False

        agent = BrowserAgent()
        agent._page = MagicMock()

        # 调用增强版检测
        result = agent.check_login_status_with_auto_handle()

        # 验证：返回 False
        assert result is False, "未登录时应返回 False"
        
        # 验证：自动暂停
        assert agent.is_paused is True, "未登录时应自动暂停"


if __name__ == "__main__":
    # 直接运行测试
    pytest.main([__file__, "-v", "--tb=short"])
