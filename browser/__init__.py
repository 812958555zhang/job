"""
Browser 自动化模块

提供基于 Browser Use + Playwright + Chromium 的浏览器控制能力，
包括 Agent 管理、会话管理、多标签页操作等功能。

主要组件：
- BrowserAgent: 浏览器 Agent 核心封装（生命周期管理、LLM 集成）
- SessionManager: 增强版会话管理器（Cookie 持久化、多标签页、登录态检测）
- 自定义异常类：BrowserCrashError, LoginExpiredError, NetworkTimeoutError

使用示例：
    from browser import BrowserAgent, SessionManager, create_browser_agent

    # 方式1：直接创建实例
    agent = BrowserAgent()
    agent.start()

    # 方式2：使用工厂函数（推荐）
    agent = create_browser_agent()
    agent.start()

    # 方式3：配合增强版会话管理器使用
    agent = create_browser_agent(headless=True)
    sm = SessionManager(agent)  # 增强版，支持多标签页和登录回调
"""

# 导入核心类和异常类
from browser.agent import (
    BrowserAgent,
    BrowserCrashError,
    LoginExpiredError,
    NetworkTimeoutError,
)

# 导入增强版会话管理器（支持多标签页、登录状态检测、观察者回调）
from browser.session_manager import SessionManager as EnhancedSessionManager


# ============================================================
# 模块级常量
# ============================================================

BOSS_ZHIPIN_URL: str = "https://www.zhipin.com/"
"""BOSS 直聘首页地址"""

DEFAULT_WINDOW_SIZE: tuple = (1280, 800)
"""默认浏览器窗口尺寸 (宽, 高)"""

MAX_RETRY_COUNT: int = 3
"""最大重试次数"""

PAGE_LOAD_TIMEOUT: int = 60
"""页面加载超时时间（秒）"""


def create_browser_agent(config: dict = None, headless: bool = False) -> BrowserAgent:
    """
    工厂函数：快速创建并配置 BrowserAgent 实例

    提供便捷的创建方式，封装了常见的配置组合。
    推荐使用此函数代替直接实例化 BrowserAgent。

    Args:
        config: 自定义配置字典（可选，覆盖配置文件默认值）
                支持的顶层 key 包括 llm_config / browser_config / anti_detection / session_config
        headless: 是否使用无头模式（默认 False，开发时显示浏览器）

    Returns:
        BrowserAgent: 已初始化的 Agent 实例（尚未启动，需调用 start()）

    示例：
        >>> agent = create_browser_agent()           # 使用默认配置，显示浏览器
        >>> agent = create_browser_agent(headless=True)  # 无头模式
        >>> agent = create_browser_agent(
        ...     config={"browser_config": {"headless": True, "viewport_width": 1920}}
        ... )
    """
    if config is None:
        config = {}

    # 合并 headless 参数到 browser_config 中
    if "browser_config" not in config:
        config["browser_config"] = {}
    config["browser_config"]["headless"] = headless

    return BrowserAgent(config=config)


# ============================================================
# 公共 API 定义
# ============================================================

__all__ = [
    # 核心类
    "BrowserAgent",
    "SessionManager",       # 别名，指向增强版 SessionManager
    "EnhancedSessionManager",
    # 异常类
    "BrowserCrashError",
    "LoginExpiredError",
    "NetworkTimeoutError",
    # 工厂函数
    "create_browser_agent",
    # 模块级常量
    "BOSS_ZHIPIN_URL",
    "DEFAULT_WINDOW_SIZE",
    "MAX_RETRY_COUNT",
    "PAGE_LOAD_TIMEOUT",
]

# 向后兼容别名：SessionManager 直接指向增强版
SessionManager = EnhancedSessionManager
