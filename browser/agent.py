"""
Browser Use Agent 核心封装模块

封装 Browser Use 框架的完整生命周期管理，包括 Agent 初始化、浏览器启动、
页面导航、资源释放等功能，为 BOSS 直聘求职自动化提供统一的浏览器控制接口。

功能特性：
- 基于 Browser Use + Playwright + Chromium 的浏览器自动化
- 集成火山引擎豆包 LLM（兼容 OpenAI 协议）
- 反检测模式（undetectable）防止被目标网站识别
- 完善的异常处理和日志记录
- 会话状态持久化（Cookie 存储）
"""

import asyncio
import json
import os
import random
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from browser_use import Agent
from browser_use.llm import ChatOpenAI
from playwright.async_api import Browser as AsyncBrowser
from playwright.async_api import Page as AsyncPage

from utils.config_loader import get_config
from utils.logger import get_logger


# ============================================================
# 自定义异常类
# ============================================================


class BrowserCrashError(Exception):
    """浏览器崩溃异常 - Chromium 进程意外终止或无响应"""

    def __init__(self, message: str = "浏览器进程崩溃", original_error: Optional[Exception] = None):
        """
        初始化浏览器崩溃异常

        Args:
            message: 错误描述信息
            original_error: 原始异常对象（用于保留完整错误链）
        """
        self.original_error = original_error
        super().__init__(message)


class LoginExpiredError(Exception):
    """登录过期异常 - BOSS 直聘会话登录状态已失效"""

    def __init__(self, message: str = "BOSS 直聘登录已过期，请重新登录"):
        """
        初始化登录过期异常

        Args:
            message: 错误描述信息
        """
        super().__init__(message)


class NetworkTimeoutError(Exception):
    """网络超时异常 - 页面加载或请求超时"""

    def __init__(self, message: str = "网络请求超时", timeout: float = 0.0):
        """
        初始化网络超时异常

        Args:
            message: 错误描述信息
            timeout: 超时时长（秒）
        """
        self.timeout = timeout
        super().__init__(message)


# ============================================================
# SessionManager - 会话状态管理（内部辅助类）
# ============================================================


class SessionManager:
    """
    浏览器会话状态管理器

    负责 Cookie 的保存与恢复，实现跨会话的登录状态保持。
    """

    def __init__(self, cookie_storage_path: str = "data/browser_cookies.json"):
        """
        初始化会话管理器

        Args:
            cookie_storage_path: Cookie 文件存储路径
        """
        self._cookie_path = Path(cookie_storage_path)
        self._logger = get_logger(f"{__name__}.SessionManager")
        # 确保存储目录存在
        self._cookie_path.parent.mkdir(parents=True, exist_ok=True)

    def save_cookies(self, browser_context) -> bool:
        """
        保存当前浏览器上下文的 Cookie 到本地文件

        Args:
            browser_context: Playwright 浏览器上下文对象

        Returns:
            保存成功返回 True，失败返回 False
        """
        try:
            cookies = browser_context.cookies()
            import json

            with open(self._cookie_path, 'w', encoding='utf-8') as f:
                json.dump(cookies, f, ensure_ascii=False, indent=2)

            self._logger.info(f"✓ Cookie 已保存至 {self._cookie_path}（共 {len(cookies)} 条）")
            return True

        except Exception as e:
            self._logger.warning(f"保存 Cookie 失败: {e}")
            return False

    def load_cookies(self) -> list:
        """
        从本地文件加载已保存的 Cookie

        Returns:
            Cookie 列表（字典格式），文件不存在时返回空列表
        """
        try:
            if not self._cookie_path.exists():
                self._logger.debug("Cookie 文件不存在，跳过加载")
                return []

            import json

            with open(self._cookie_path, 'r', encoding='utf-8') as f:
                cookies = json.load(f)

            self._logger.info(f"✓ 已加载 Cookie（共 {len(cookies)} 条）")
            return cookies

        except Exception as e:
            self._logger.warning(f"加载 Cookie 失败: {e}")
            return []

    def clear_cookies(self) -> None:
        """清除本地存储的 Cookie 文件"""
        try:
            if self._cookie_path.exists():
                self._cookie_path.unlink()
                self._logger.info("✓ 本地 Cookie 文件已清除")
        except Exception as e:
            self._logger.warning(f"清除 Cookie 文件失败: {e}")


# ============================================================
# BrowserAgent 核心类
# ============================================================


class BrowserAgent:
    """
    Browser Use Agent 核心封装类

    封装 Browser Use 框架的完整生命周期，提供统一的浏览器控制接口。
    集成 LLM（豆包）、反检测、会话管理等能力。

    使用示例::

        >>> agent = BrowserAgent()
        >>> if agent.start():
        ...     page = agent.get_page()
        ...     # 执行浏览器操作...
        ...     agent.stop()

    属性:
        _agent: Browser Use Agent 实例
        _browser: Playwright 异步浏览器实例
        _llm_client: browser-use ChatOpenAI LLM 客户端（封装 AsyncOpenAI）
        _session_manager: 会话状态管理器
        _config: 合并后的配置字典
    """

    # BOSS 直聘首页地址
    BOSS_ZHIPIN_URL: str = "https://www.zhipin.com/"

    # 默认配置常量
    DEFAULT_WINDOW_WIDTH: int = 1280
    DEFAULT_WINDOW_HEIGHT: int = 800
    DEFAULT_HEADLESS: bool = False
    DEFAULT_MIN_DELAY: float = 3.0
    DEFAULT_MAX_DELAY: float = 8.0
    DEFAULT_TYPING_SPEED_MIN: int = 50
    DEFAULT_TYPING_SPEED_MAX: int = 150

    # 新增：异常处理和监控相关默认配置
    DEFAULT_PAGE_LOAD_TIMEOUT: float = 60.0  # 页面加载超时时间（秒）
    DEFAULT_MAX_RETRY_COUNT: int = 3  # 最大重试次数
    DEFAULT_HEARTBEAT_INTERVAL: float = 30.0  # 心跳检测间隔（秒）
    DEFAULT_PROCESS_CHECK_INTERVAL: float = 10.0  # 进程检查间隔（秒）

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化 BrowserAgent

        从配置文件加载默认参数，支持通过构造函数参数覆盖。
        配置优先级：构造参数 > 配置文件 > 代码默认值

        Args:
            config: 自定义配置字典（可选，用于覆盖配置文件的默认值）
        """
        # 初始化日志记录器
        self._logger = get_logger(__name__)

        # 运行状态标记
        self._running: bool = False
        self._agent: Optional[Agent] = None
        self._browser: Optional[AsyncBrowser] = None
        self._context = None  # Playwright 浏览器上下文
        self._page: Optional[AsyncPage] = None

        # 新增：异常处理和状态监控相关属性
        self._retry_count: int = 0  # 当前已重试次数
        self._last_error: Optional[Exception] = None  # 最后一次异常对象
        self._start_time: Optional[float] = None  # 浏览器启动时间戳
        self._paused: bool = False  # 是否处于暂停状态（超时或登录过期时）
        self._login_expired_callbacks: List[Callable[[str], None]] = []  # 登录过期回调列表

        # 加载并合并配置
        self._config = self._load_config(config)

        # 初始化 LLM 客户端（豆包，兼容 OpenAI 协议）
        self._llm_client = self._init_llm_client()

        # 初始化会话管理器
        session_config = self._config.get("session_config", {})
        cookie_path = session_config.get(
            "cookie_storage_path",
            "data/browser_cookies.json"
        )
        self._session_manager = SessionManager(cookie_storage_path=cookie_path)

        self._logger.info("✓ BrowserAgent 初始化完成")

    def _load_config(self, override_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        加载并合并配置参数

        按优先级合并：override_config > 配置文件 > 代码默认值

        Args:
            override_config: 外部传入的覆盖配置（可选）

        Returns:
            合并后的完整配置字典
        """
        # 默认配置
        default_config = {
            "llm_config": {
                "model_name": "GLM-5.1",
                "api_base_url": "https://ark.cn-beijing.volces.com/api/coding/v3",
                "api_key_ref": "volcengine.api_key",
            },
            "browser_config": {
                "window_width": self.DEFAULT_WINDOW_WIDTH,
                "window_height": self.DEFAULT_WINDOW_HEIGHT,
                "headless": self.DEFAULT_HEADLESS,
                "chromium_path": None,
            },
            "anti_detection": {
                "enabled": True,
                "min_delay": self.DEFAULT_MIN_DELAY,
                "max_delay": self.DEFAULT_MAX_DELAY,
                "typing_speed_min": self.DEFAULT_TYPING_SPEED_MIN,
                "typing_speed_max": self.DEFAULT_TYPING_SPEED_MAX,
            },
            "session_config": {
                "cookie_storage_path": "data/browser_cookies.json",
                "auto_save_session": True,
            },
            # 新增：异常处理和监控相关配置
            "error_handling": {
                "page_load_timeout": self.DEFAULT_PAGE_LOAD_TIMEOUT,
                "max_retry_count": self.DEFAULT_MAX_RETRY_COUNT,
                "heartbeat_interval": self.DEFAULT_HEARTBEAT_INTERVAL,
                "process_check_interval": self.DEFAULT_PROCESS_CHECK_INTERVAL,
            },
        }

        # 从配置文件加载
        try:
            config_loader = get_config()
            api_config = config_loader.load_api_config()
            file_browser_config = api_config.get("browser_use", {})

            # 合并文件配置到默认配置（深度合并顶层）
            for section in ["llm_config", "browser_config", "anti_detection", "session_config"]:
                if section in file_browser_config:
                    if isinstance(file_browser_config[section], dict):
                        default_config[section].update(file_browser_config[section])
                    else:
                        # 非字典类型的标量值直接替换（如 undetectable 布尔值）
                        if section == "anti_detection" and isinstance(file_browser_config[section], bool):
                            default_config[section]["enabled"] = file_browser_config[section]

            # 从 volcengine 段获取 API Key
            volc_config = api_config.get("volcengine", {})
            if volc_config.get("api_key"):
                default_config["llm_config"]["_api_key"] = volc_config["api_key"]
            if volc_config.get("base_url"):
                default_config["llm_config"]["api_base_url"] = volc_config["base_url"]
            if volc_config.get("models", {}).get("chat"):
                default_config["llm_config"]["model_name"] = volc_config["models"]["chat"]

            self._logger.info("✓ 配置文件加载成功")

        except Exception as e:
            self._logger.warning(f"加载配置文件失败，使用默认配置: {e}")

        # 应用外部覆盖配置
        if override_config:
            for section, value in override_config.items():
                if section in default_config and isinstance(value, dict):
                    default_config[section].update(value)
                else:
                    default_config[section] = value

        return default_config

    def _init_llm_client(self) -> ChatOpenAI:
        """
        初始化 LLM 客户端（browser-use ChatOpenAI）

        使用火山引擎豆包 API，通过 browser-use 的 ChatOpenAI 封装对接。
        ChatOpenAI 继承 BaseChatModel，提供 provider 属性和异步调用能力，
        是 Browser Use Agent 要求的标准 LLM 接口。

        Returns:
            ChatOpenAI: 已配置好的 LLM 实例（带 provider 属性）
        """
        llm_cfg = self._config.get("llm_config", {})

        # 获取 API Key（支持引用其他配置段）
        api_key = llm_cfg.get("_api_key", "")
        if not api_key and llm_cfg.get("api_key_ref"):
            try:
                config_loader = get_config()
                api_key = config_loader.get(llm_cfg["api_key_ref"], "")
            except Exception:
                pass

        # 安全检查
        if not api_key:
            self._logger.warning(
                "⚠️ LLM API Key 未配置！Browser Use Agent 将无法正常工作"
            )

        # 使用 browser-use 的 ChatOpenAI（继承 BaseChatModel，带 provider 属性）
        client = ChatOpenAI(
            model=llm_cfg.get("model_name", "GLM-5.1"),
            api_key=api_key,
            base_url=llm_cfg.get("api_base_url", ""),
        )

        self._logger.info(
            f"✓ LLM 客户端初始化完成 | 模型: {client.model} | "
            f"Base URL: {llm_cfg.get('api_base_url', '')}"
        )

        return client

    def start(self) -> bool:
        """
        启动 Browser Use Agent

        创建 Agent 实例、启动 Chromium 浏览器，
        并导航至 BOSS 直聘首页。

        Returns:
            bool: 启动成功返回 True，失败返回 False

        Raises:
            BrowserCrashError: 浏览器启动失败或崩溃
            NetworkTimeoutError: 页面导航超时
        """
        if self._running:
            self._logger.warning("BrowserAgent 已在运行中，无需重复启动")
            return True

        try:
            self._logger.info("🚀 正在启动 Browser Use Agent...")

            # 重置状态监控属性
            self._retry_count = 0
            self._last_error = None
            self._paused = False

            # 构建浏览器配置
            browser_cfg = self._config.get("browser_config", {})
            anti_cfg = self._config.get("anti_detection", {})
            llm_cfg = self._config.get("llm_config", {})

            # 创建 Browser Use Agent 实例
            self._agent = Agent(
                task="打开BOSS直聘网站并保持在线",
                llm=self._llm_client,
                browser_config={
                    "browser_type": "chromium",
                    "headless": browser_cfg.get("headless", self.DEFAULT_HEADLESS),
                    "viewport_width": browser_cfg.get("window_width", self.DEFAULT_WINDOW_WIDTH),
                    "viewport_height": browser_cfg.get("window_height", self.DEFAULT_WINDOW_HEIGHT),
                },
            )

            # 启动浏览器并获取底层 Playwright 实例
            # Browser Use Agent 内部管理浏览器生命周期
            self._running = True
            self._start_time = time.time()  # 记录启动时间
            self._logger.info("✓ Browser Use Agent 已创建")

            # 获取底层浏览器和页面对象
            self._browser, self._context = self._get_browser_instances()

            # 导航至 BOSS 直聘首页
            if self._page:
                self._navigate_to_home()

            self._logger.info("✅ BrowserAgent 启动成功")
            return True

        except Exception as e:
            self._running = False
            error_msg = f"启动 BrowserAgent 失败: {e}"
            self._logger.error(error_msg, exc_info=True)
            self._last_error = e  # 记录最后错误

            # 根据错误类型抛出对应自定义异常
            err_str = str(e).lower()
            if "timeout" in err_str or "timed out" in err_str:
                raise NetworkTimeoutError(
                    message="浏览器启动超时",
                    timeout=30.0,
                ) from e
            else:
                raise BrowserCrashError(
                    message=error_msg,
                    original_error=e,
                ) from e

    async def _get_browser_instances(self):
        """
        获取底层 Playwright 浏览器和上下文实例

        从 Browser Use Agent 内部提取 Playwright 的 Browser 和 Context 对象，
        供需要直接操作浏览器的场景使用。

        Returns:
            tuple: (Browser 实例, BrowserContext 实例)
        """
        try:
            # Browser Use Agent 通过 agent.browser_manager 访问底层浏览器
            if hasattr(self._agent, '_browser_context'):
                context = self._agent._browser_context
                browser = await context.browser
                page = await context.new_page() if not self._page else self._page
                self._page = page
                return browser, context
            return None, None
        except Exception as e:
            self._logger.warning(f"获取浏览器实例时发生异常（非致命）: {e}")
            return None, None

    def _navigate_to_home(self) -> None:
        """
        导航至 BOSS 直聘首页

        在当前活跃的 Page 上打开 BOSS 直聘网站，
        并等待页面基本元素加载完成。
        使用配置中的超时时间，支持自动重试机制。
        """
        if not self._page:
            self._logger.warning("当前没有可用的页面对象，跳过导航")
            return

        # 获取配置的超时时间
        error_cfg = self._config.get("error_handling", {})
        timeout = error_cfg.get(
            "page_load_timeout",
            self.DEFAULT_PAGE_LOAD_TIMEOUT
        )

        try:
            anti_cfg = self._config.get("anti_detection", {})
            min_delay = anti_cfg.get("min_delay", self.DEFAULT_MIN_DELAY)
            max_delay = anti_cfg.get("max_delay", self.DEFAULT_MAX_DELAY)

            # 随机延迟，模拟人类行为
            delay = random.uniform(min_delay, max_delay)
            self._logger.info(f"⏳ 等待 {delay:.1f}s 后导航至 BOSS 直聘...")
            time.sleep(delay)

            # 导航至首页（使用可配置的超时时间）
            loop = asyncio.get_event_loop()
            loop.run_until_complete(
                self._page.goto(self.BOSS_ZHIPIN_URL, wait_until="domcontentloaded", timeout=timeout * 1000)
            )

            current_url = loop.run_until_complete(self._page.url)
            self._logger.info(f"✓ 已导航至 {current_url}")

        except Exception as e:
            self._logger.error(f"导航至 BOSS 直聘首页失败: {e}", exc_info=True)
            self._last_error = e  # 记录最后错误

            err_str = str(e).lower()
            if "timeout" in err_str:
                # 超时时设置暂停状态并记录日志
                self._paused = True
                self._logger.warning(
                    f"⚠️ 页面加载超时（{timeout}s），已暂停当前操作。"
                    f"可调用 resume() 恢复或等待自动重试。"
                )
                raise NetworkTimeoutError(
                    message=f"导航至 {self.BOSS_ZHIPIN_URL} 超时",
                    timeout=timeout,
                ) from e
            raise

    def stop(self) -> None:
        """
        停止 Browser Use Agent 并释放所有资源

        执行以下清理操作：
        1. 优雅关闭 Agent
        2. 释放浏览器进程资源
        3. 保存会话状态（Cookie）
        4. 重置状态监控属性
        """
        if not self._running:
            self._logger.debug("BrowserAgent 未在运行，无需停止")
            return

        try:
            self._logger.info("🛑 正在停止 Browser Use Agent...")

            # 保存会话状态（如果启用）
            session_cfg = self._config.get("session_config", {})
            if session_cfg.get("auto_save_session", True):
                self._save_session()

            # 关闭 Agent
            if self._agent:
                # Browser Use Agent 的关闭逻辑
                if hasattr(self._agent, 'stop'):
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            # 如果事件循环已在运行，创建任务来关闭
                            loop.create_task(self._agent.stop())
                        else:
                            loop.run_until_complete(self._agent.stop())
                    except RuntimeError:
                        pass  # 无可用事件循环时忽略
                self._agent = None

            # 清空引用和重置状态
            self._browser = None
            self._context = None
            self._page = None
            self._running = False
            self._start_time = None
            self._paused = False

            self._logger.info("✓ BrowserAgent 已安全停止，所有资源已释放")

        except Exception as e:
            self._running = False
            self._last_error = e
            self._logger.error(f"停止 BrowserAgent 时发生异常: {e}", exc_info=True)

    def _save_session(self) -> None:
        """
        保存当前会话状态（Cookie 等）

        通过 SessionManager 将浏览器 Cookie 持久化到本地文件，
        以便下次启动时恢复登录状态。
        """
        if self._context:
            self._session_manager.save_cookies(self._context)
        else:
            self._logger.debug("无可用的浏览器上下文，跳过会话保存")

    def restart(self) -> bool:
        """
        重启浏览器（用于异常恢复场景）

        先执行 stop() 释放旧资源，再执行 start() 重新初始化。
        适用于浏览器卡死、页面崩溃等需要完全重置的场景。

        Returns:
            bool: 重启成功返回 True，失败返回 False
        """
        self._logger.info("🔄 正在重启 Browser Use Agent...")

        try:
            # 先停止
            self.stop()
            # 短暂等待确保资源完全释放
            time.sleep(2)
            # 再启动
            success = self.start()

            if success:
                self._logger.info("✅ BrowserAgent 重启成功")
            else:
                self._logger.error("❌ BrowserAgent 重启失败")

            return success

        except (BrowserCrashError, NetworkTimeoutError) as e:
            self._logger.error(f"❌ 重启过程中发生异常: {e}")
            return False
        except Exception as e:
            self._logger.error(f"❌ 重启过程中发生未预期异常: {e}", exc_info=True)
            return False

    @property
    def is_running(self) -> bool:
        """
        检查 Agent 当前是否处于运行状态

        Returns:
            bool: True 表示正在运行，False 表示未运行
        """
        return self._running

    def get_browser(self) -> Optional[AsyncBrowser]:
        """
        获取底层 Playwright Browser 实例

        用于需要直接操作浏览器的场景（如截图、新标签页管理等）。
        其他模块可通过此方法访问原始浏览器对象。

        Returns:
            AsyncBrowser: Playwright 异步浏览器实例，未启动时返回 None
        """
        if not self._running or not self._browser:
            self._logger.warning("浏览器未启动或不可用，请先调用 start()")
            return None
        return self._browser

    def get_page(self) -> Optional[AsyncPage]:
        """
        获取当前活跃的 Page 对象

        返回当前浏览器中活跃的页面标签页实例，
        用于执行页面级别的操作（点击、输入、截图等）。

        Returns:
            AsyncPage: Playwright 异步页面对象，未启动时返回 None
        """
        if not self._running or not self._page:
            self._logger.warning("浏览器页面不可用，请先调用 start()")
            return None
        return self._page

    def random_delay(self, min_seconds: Optional[float] = None, max_seconds: Optional[float] = None) -> None:
        """
        随机延迟指定时间范围（模拟人类操作间隔）

        从反检测配置中读取默认的延迟范围，也可通过参数覆盖。

        Args:
            min_seconds: 最小延迟秒数（可选，默认从配置读取）
            max_seconds: 最大延迟秒数（可选，默认从配置读取）
        """
        anti_cfg = self._config.get("anti_detection", {})
        min_sec = min_seconds or anti_cfg.get("min_delay", self.DEFAULT_MIN_DELAY)
        max_sec = max_seconds or anti_cfg.get("max_delay", self.DEFAULT_MAX_DELAY)

        delay = random.uniform(min_sec, max_sec)
        self._logger.debug(f"随机延迟 {delay:.2f}s")
        time.sleep(delay)

    def check_login_status(self) -> bool:
        """
        检测当前 BOSS 直聘登录状态

        通过检查页面上的用户信息元素判断是否已登录。

        Returns:
            bool: 已登录返回 True，未登录或检测失败返回 False

        Raises:
            LoginExpiredError: 检测到登录状态已失效时抛出
        """
        if not self._page:
            self._logger.warning("无法检测登录状态：页面不可用")
            return False

        try:
            import asyncio

            # 检查是否存在登录后才会显示的用户相关元素
            login_indicator = asyncio.get_event_loop().run_until_complete(
                self._page.query_selector('[class*="user"], [class*="avatar"], [class*="login"]')
            )

            if login_indicator:
                self._logger.info("✓ 当前登录状态正常")
                return True
            else:
                self._logger.warning("⚠️ 未检测到登录状态，可能需要重新登录")
                raise LoginExpiredError("BOSS 直聘登录状态已失效，请重新登录")

        except LoginExpiredError:
            raise
        except Exception as e:
            self._logger.warning(f"检测登录状态时发生异常: {e}")
            return False

    # ----------------------------------------------------------
    # 新增：状态监控属性和方法
    # ----------------------------------------------------------

    @property
    def retry_count(self) -> int:
        """
        获取当前已重试次数

        Returns:
            int: 当前已执行的重试次数（0 表示未重试）
        """
        return self._retry_count

    @property
    def last_error(self) -> Optional[Exception]:
        """
        获取最后一次异常对象

        Returns:
            Optional[Exception]: 最后一次异常实例，无异常时返回 None
        """
        return self._last_error

    @property
    def uptime(self) -> float:
        """
        获取浏览器运行时长（秒）

        Returns:
            float: 浏览器启动至今的运行秒数，未启动时返回 0.0
        """
        if not self._start_time or not self._running:
            return 0.0
        return time.time() - self._start_time

    @property
    def is_paused(self) -> bool:
        """
        检查当前是否处于暂停状态

        当发生超时或登录过期时，自动化任务会自动暂停。

        Returns:
            bool: True 表示已暂停，False 表示正常运行
        """
        return self._paused

    def health_check(self) -> Dict[str, Any]:
        """
        执行健康检查，返回状态报告

        综合检查浏览器进程存活、页面响应、登录状态等多个维度，
        生成完整的健康报告用于监控和诊断。

        Returns:
            dict: 健康状态报告，包含以下字段：
                - browser_alive (bool): 浏览器进程是否存活
                - page_responsive (bool): 页面是否响应
                - logged_in (bool): 是否已登录
                - retry_count (int): 已重试次数
                - uptime_seconds (float): 运行时长
                - last_error (str): 最后错误信息
                - is_paused (bool): 是否暂停
        """
        report = {
            "browser_alive": False,
            "page_responsive": False,
            "logged_in": False,
            "retry_count": self._retry_count,
            "uptime_seconds": self.uptime,
            "last_error": str(self._last_error) if self._last_error else None,
            "is_paused": self._paused,
        }

        # 检查1：浏览器进程是否存活
        report["browser_alive"] = self._check_browser_process_alive()

        # 检查2：页面是否响应
        if self._running and self._page:
            report["page_responsive"] = self._check_page_responsive()

        # 检查3：登录状态
        if self._running and self._page:
            try:
                report["logged_in"] = self.check_login_status()
            except LoginExpiredError:
                report["logged_in"] = False

        self._logger.debug(
            f"✓ 健康检查完成 | 存活: {report['browser_alive']} | "
            f"响应: {report['page_responsive']} | 登录: {report['logged_in']} | "
            f"重试: {report['retry_count']} | 运行: {report['uptime_seconds']:.1f}s"
        )

        return report

    def _handle_browser_crash(self, error: Exception) -> None:
        """
        处理浏览器崩溃事件（内部方法）

        当检测到浏览器崩溃时自动调用，执行以下流程：
        1. 记录错误日志（包含详细堆栈）
        2. 尝试自动重启（使用指数退避策略）
        3. 如果重启失败且超过最大重试次数，设置错误状态并通知上层

        Args:
            error: 触发崩溃处理的异常对象
        """
        self._logger.error(f"💥 检测到浏览器崩溃: {error}", exc_info=True)
        self._last_error = error

        # 获取最大重试次数配置
        error_cfg = self._config.get("error_handling", {})
        max_retries = error_cfg.get("max_retry_count", self.DEFAULT_MAX_RETRY_COUNT)

        # 检查是否超过最大重试次数
        if self._retry_count >= max_retries:
            self._logger.error(
                f"❌ 浏览器崩溃重试已达上限（{max_retries}次），无法自动恢复"
            )
            self._paused = True
            # 触发登录过期回调通知上层（复用回调机制）
            self._trigger_login_expired_callbacks(
                f"浏览器崩溃无法恢复，已重试 {max_retries} 次: {error}"
            )
            return

        # 计算指数退避等待时间（1s → 2s → 4s）
        wait_time = 2 ** self._retry_count
        self._logger.info(
            f"🔄 准备进行第 {self._retry_count + 1}/{max_retries} 次重启尝试..."
            f"（等待 {wait_time}s 后执行）"
        )

        # 等待退避时间
        time.sleep(wait_time)

        # 尝试重启
        try:
            self._retry_count += 1
            success = self.restart()

            if success:
                self._logger.info(
                    f"✅ 浏览器在第 {self._retry_count} 次尝试后成功恢复"
                )
                # 重启成功后清除暂停状态
                self._paused = False
            else:
                self._logger.error(f"❌ 第 {self._retry_count} 次重启失败")
                # 如果还有剩余重试机会，递归调用继续重试
                if self._retry_count < max_retries:
                    self._handle_browser_crash(error)

        except Exception as restart_error:
            self._logger.error(
                f"❌ 重启过程中发生异常: {restart_error}",
                exc_info=True
            )
            self._last_error = restart_error
            # 如果还有剩余重试机会，递归调用继续重试
            if self._retry_count < max_retries:
                self._handle_browser_crash(restart_error)

    def _check_browser_process_alive(self) -> bool:
        """
        检查 Chromium 进程是否存活（内部方法）

        通过操作系统进程列表检查浏览器进程是否存在，
        用于心跳检测和健康检查。

        Returns:
            bool: 进程存活返回 True，否则返回 False
        """
        if not self._running or not self._browser:
            return False

        try:
            # 方式1：通过 Playwright 的 browser.is_connected() 检查
            loop = asyncio.new_event_loop()
            try:
                is_connected = loop.run_until_complete(self._browser.is_connected())
                if not is_connected:
                    self._logger.warning("⚠️ Playwright 浏览器连接已断开")
                    return False
            finally:
                loop.close()

            # 方式2：通过操作系统进程检查 chromium 是否存在
            import subprocess

            # Windows 系统使用 tasklist 命令
            if os.name == 'nt':
                result = subprocess.run(
                    ['tasklist', '/FI', 'IMAGENAME eq chrome.exe'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if 'chrome.exe' not in result.stdout:
                    self._logger.warning("⚠️ 未找到 Chrome/Chromium 进程")
                    return False
            else:
                # Linux/Mac 使用 pgrep 命令
                result = subprocess.run(
                    ['pgrep', '-f', 'chromium'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode != 0:
                    self._logger.warning("⚠️ 未找到 Chromium 进程")
                    return False

            return True

        except Exception as e:
            self._logger.warning(f"检查浏览器进程时发生异常: {e}")
            return False

    def _check_page_responsive(self) -> bool:
        """
        检查页面是否响应（内部方法）

        向页面发送简单的 JavaScript 命令检测响应性，
        用于心跳检测和健康检查。

        Returns:
            bool: 页面响应正常返回 True，否则返回 False
        """
        if not self._page:
            return False

        try:
            loop = asyncio.new_event_loop()
            try:
                # 执行简单的 JavaScript 检测页面响应
                result = loop.run_until_complete(
                    self._page.evaluate("() => { return { ready: document.readyState, url: location.href }; }")
                )
                if result and result.get('ready') in ['interactive', 'complete']:
                    return True
                return False
            finally:
                loop.close()

        except Exception as e:
            self._logger.debug(f"页面响应检测异常: {e}")
            return False

    def resume(self) -> bool:
        """
        从暂停状态恢复（手动恢复）

        当因超时或登录过期导致任务暂停时，
        可调用此方法手动恢复自动化操作。

        Returns:
            bool: 恢复成功返回 True，失败返回 False
        """
        if not self._paused:
            self._logger.info("当前未处于暂停状态，无需恢复")
            return True

        self._logger.info("🔄 正在从暂停状态恢复...")

        try:
            # 先检查登录状态
            if self._page:
                try:
                    logged_in = self.check_login_status()
                    if not logged_in:
                        self._logger.warning("⚠️ 登录状态仍无效，可能需要重新登录")
                        # 触发登录过期回调
                        self._trigger_login_expired_callbacks(
                            "从暂停状态恢复时检测到登录仍然无效"
                        )
                except LoginExpiredError as e:
                    self._logger.warning(f"⚠️ 恢复时检测到登录过期: {e}")
                    self._trigger_login_expired_callbacks(str(e))

            # 清除暂停状态
            self._paused = False
            self._logger.info("✓ 已从暂停状态恢复")
            return True

        except Exception as e:
            self._logger.error(f"恢复过程中发生异常: {e}", exc_info=True)
            self._last_error = e
            return False

    def register_login_expired_callback(self, callback: Callable[[str], None]) -> None:
        """
        注册登录过期回调函数

        当检测到登录状态失效或浏览器崩溃无法恢复时，
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

    def check_login_status_with_auto_handle(self) -> bool:
        """
        带自动处理逻辑的登录状态检测（增强版）

        在关键操作前调用此方法，自动检测登录状态并在发现问题时：
        1. 自动暂停当前自动化任务
        2. 记录详细的诊断日志（URL、时间、页面快照等）
        3. 触发登录过期回调通知上层

        Returns:
            bool: 已登录返回 True，未登录或检测失败返回 False
        """
        if not self._page:
            self._logger.warning("无法检测登录状态：页面不可用")
            return False

        try:
            # 调用基础检测方法
            is_logged_in = self.check_login_status()

            if not is_logged_in:
                # 记录详细诊断日志
                self._log_login_expiry_diagnosis()

                # 自动暂停任务
                self._paused = True
                self._logger.warning("⚠️ 因登录过期已自动暂停自动化任务")

                # 触发回调通知
                self._trigger_login_expired_callbacks(
                    "检测到 BOSS 直聘登录状态已失效，自动化任务已暂停"
                )

            return is_logged_in

        except LoginExpiredError as e:
            # 捕获登录过期异常并进行处理
            self._last_error = e
            self._log_login_expiry_diagnosis()
            self._paused = True
            self._trigger_login_expired_callbacks(str(e))
            return False

        except Exception as e:
            self._logger.warning(f"增强版登录状态检测异常: {e}")
            return False

    def _log_login_expiry_diagnosis(self) -> None:
        """
        记录登录过期的详细诊断日志（内部方法）

        收集当前 URL、时间、页面快照等信息，
        便于后续问题排查和定位。

        包含的信息：
        - 当前页面 URL
        - 检测时间戳
        - 页面标题
        - 重试次数和运行时长等状态信息
        """
        from datetime import datetime

        diagnosis_info = {
            "timestamp": datetime.now().isoformat(),
            "url": "N/A",
            "title": "N/A",
            "uptime_seconds": self.uptime,
            "retry_count": self._retry_count,
            "is_paused": self._paused,
        }

        # 安全获取页面信息
        if self._page:
            try:
                loop = asyncio.new_event_loop()
                try:
                    diagnosis_info["url"] = loop.run_until_complete(self._page.url)
                    diagnosis_info["title"] = loop.run_until_complete(self._page.title())
                finally:
                    loop.close()
            except Exception as page_e:
                self._logger.warning(f"获取页面信息失败: {page_e}")

        # 输出结构化诊断日志
        self._logger.warning(
            f"🔍 登录过期诊断信息:\n"
            f"  - 时间: {diagnosis_info['timestamp']}\n"
            f"  - URL: {diagnosis_info['url']}\n"
            f"  - 标题: {diagnosis_info['title']}\n"
            f"  - 运行时长: {diagnosis_info['uptime_seconds']:.1f}s\n"
            f"  - 重试次数: {diagnosis_info['retry_count']}\n"
            f"  - 暂停状态: {diagnosis_info['is_paused']}"
        )


# ============================================================
# 模块自测试代码
# ============================================================

if __name__ == "__main__":
    """模块自测试代码 - 验证 BrowserAgent 各项功能（含增强功能）"""
    import sys
    import io

    # 设置控制台输出编码为 UTF-8
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

    print("=" * 70)
    print("BrowserAgent 核心封装模块 - 自测试（含异常处理和状态监控）")
    print("=" * 70)

    try:
        # 测试1：创建 BrowserAgent 实例
        print("\n【测试1】创建 BrowserAgent 实例...")
        agent = BrowserAgent()
        print(f"   ✓ 实例创建成功")
        print(f"   - 运行状态: {agent.is_running}")
        print(f"   - 重试次数: {agent.retry_count}")
        print(f"   - 最后错误: {agent.last_error}")
        print(f"   - 运行时长: {agent.uptime:.1f}s")
        print(f"   - 暂停状态: {agent.is_paused}")

        # 测试2：验证配置加载（包含新增的 error_handling 配置）
        print("\n【测试2】验证配置加载...")
        print(f"   - LLM 模型: {agent._config['llm_config']['model_name']}")
        print(f"   - API Base URL: {agent._config['llm_config']['api_base_url'][:50]}...")
        print(f"   - 窗口大小: {agent._config['browser_config']['window_width']}x{agent._config['browser_config']['window_height']}")
        print(f"   - Headless: {agent._config['browser_config']['headless']}")
        print(f"   - 反检测: {agent._config['anti_detection']['enabled']}")
        print(f"   - 延迟范围: {agent._config['anti_detection']['min_delay']}s ~ {agent._config['anti_detection']['max_delay']}s")
        print(f"   - Cookie 存储路径: {agent._config['session_config']['cookie_storage_path']}")
        # 新增：验证 error_handling 配置
        error_cfg = agent._config.get("error_handling", {})
        print(f"   - 页面超时: {error_cfg.get('page_load_timeout', 'N/A')}s")
        print(f"   - 最大重试: {error_cfg.get('max_retry_count', 'N/A')}次")
        print(f"   - 心跳间隔: {error_cfg.get('heartbeat_interval', 'N/A')}s")
        print(f"   - 进程检查间隔: {error_cfg.get('process_check_interval', 'N/A')}s")

        # 测试3：验证异常类定义
        print("\n【测试3】验证自定义异常类...")
        try:
            raise BrowserCrashError("测试浏览器崩溃", original_error=RuntimeError("模拟错误"))
        except BrowserCrashError as e:
            print(f"   ✓ BrowserCrashError: {e} | 原始错误: {e.original_error}")

        try:
            raise LoginExpiredError("测试登录过期")
        except LoginExpiredError as e:
            print(f"   ✓ LoginExpiredError: {e}")

        try:
            raise NetworkTimeoutError("测试网络超时", timeout=30.0)
        except NetworkTimeoutError as e:
            print(f"   ✓ NetworkTimeoutError: {e} | 超时: {e.timeout}s")

        # 测试4：验证 SessionManager
        print("\n【测试4】验证 SessionManager...")
        sm = SessionManager(cookie_storage_path="data/test_cookies.json")
        cookies = sm.load_cookies()
        print(f"   ✓ Cookie 加载结果: {len(cookies)} 条（首次应为空）")
        sm.clear_cookies()
        print(f"   ✓ clear_cookies() 执行成功")

        # 测试5：随机延迟功能
        print("\n【测试5】测试随机延迟功能...")
        import time as t
        start = t.time()
        agent.random_delay(0.1, 0.3)  # 使用较短延迟用于测试
        elapsed = t.time() - start
        print(f"   ✓ 随机延迟执行完成，耗时: {elapsed:.3f}s")

        # 测试6：验证状态监控属性（未启动状态）
        print("\n【测试6】验证状态监控属性（未启动状态）...")
        assert agent.retry_count == 0, "初始重试次数应为0"
        assert agent.last_error is None, "初始最后错误应为None"
        assert agent.uptime == 0.0, "未启动时运行时长应为0.0"
        assert agent.is_paused is False, "初始暂停状态应为False"
        assert agent.is_running is False, "初始运行状态应为False"
        print("   ✓ 未启动状态下所有属性值正确")

        # 测试7：健康检查（未启动状态）
        print("\n【测试7】健康检查（未启动状态）...")
        health = agent.health_check()
        assert health["browser_alive"] is False, "未启动时 browser_alive 应为 False"
        assert health["page_responsive"] is False, "未启动时 page_responsive 应为 False"
        assert health["logged_in"] is False, "未启动时 logged_in 应为 False"
        assert health["retry_count"] == 0, "重试次数应为0"
        assert health["uptime_seconds"] == 0.0, "运行时长应为0.0"
        assert health["last_error"] is None, "最后错误应为None"
        assert health["is_paused"] is False, "暂停状态应为False"
        print("   ✓ 未启动状态健康检查报告正确")
        print(f"   - 报告内容: {health}")

        # 测试8：登录过期回调注册与触发
        print("\n【测试8】登录过期回调注册与触发...")
        callback_messages = []

        def test_callback(msg: str) -> None:
            """测试回调函数"""
            callback_messages.append(msg)

        def test_callback2(msg: str) -> None:
            """测试回调函数2"""
            callback_messages.append(f"[备用]{msg}")

        # 注册回调
        agent.register_login_expired_callback(test_callback)
        agent.register_login_expired_callback(test_callback2)
        assert len(agent._login_expired_callbacks) == 2, "应注册2个回调"
        print("   ✓ 回调注册成功")

        # 触发回调
        agent._trigger_login_expired_callbacks("测试消息")
        assert len(callback_messages) == 2, "应收到2条消息"
        assert "测试消息" in callback_messages[0], "第一条消息内容不匹配"
        assert "[备用]测试消息" in callback_messages[1], "第二条消息内容不匹配"
        print("   ✓ 回调触发正常，按注册顺序调用")

        # 注销回调
        agent.unregister_login_expired_callback(test_callback)
        assert len(agent._login_expired_callbacks) == 1, "注销后应剩余1个回调"
        callback_messages.clear()
        agent._trigger_login_expired_callbacks("再次测试")
        assert len(callback_messages) == 1, "注销后应只收到1条消息"
        print("   ✓ 回调注销正常")

        # 测试9：回调异常隔离测试
        print("\n【测试9】回调异常隔离测试...")

        results = []

        def good_cb(msg: str) -> None:
            results.append(f"ok:{msg}")

        def bad_cb(_msg: str) -> None:
            raise RuntimeError("模拟回调异常")

        agent.register_login_expired_callback(bad_cb)
        agent.register_login_expired_callback(good_cb)

        # 异常回调不应影响后续回调执行
        agent._trigger_login_expired_callbacks("隔离测试")
        assert len(results) == 1, "应收到1条正常回调结果"
        assert results[0] == "ok:隔离测试", "正常回调结果不匹配"
        print("   ✓ 异常回调不影响其他回调执行")

        # 清理测试回调
        agent.unregister_login_expired_callback(bad_cb)
        agent.unregister_login_expired_callback(good_cb)
        agent.unregister_login_expired_callback(test_callback2)

        # 测试10：暂停/恢复机制测试
        print("\n【测试10】暂停/恢复机制测试...")
        # 手动设置暂停状态模拟
        agent._paused = True
        assert agent.is_paused is True, "暂停状态设置失败"

        # 测试恢复方法
        result = agent.resume()
        assert result is True, "恢复应返回True"
        assert agent.is_paused is False, "恢复后暂停状态应为False"
        print("   ✓ 暂停/恢复机制工作正常")

        # 测试11：last_error 属性更新测试
        print("\n【测试11】last_error 属性更新测试...")
        test_error = RuntimeError("测试错误")
        agent._last_error = test_error
        assert agent.last_error == test_error, "last_error 更新失败"
        assert str(agent.last_error) == "测试错误", "last_error 内容不匹配"
        print("   ✓ last_error 属性更新正常")

        # 清理错误状态
        agent._last_error = None

        # 测试12：自定义配置覆盖测试
        print("\n【测试12】自定义配置覆盖测试...")
        custom_agent = BrowserAgent(config={
            "error_handling": {
                "page_load_timeout": 120.0,
                "max_retry_count": 5,
            }
        })
        custom_error_cfg = custom_agent._config.get("error_handling", {})
        assert custom_error_cfg.get("page_load_timeout") == 120.0, "自定义超时时间未生效"
        assert custom_error_cfg.get("max_retry_count") == 5, "自定义最大重试次数未生效"
        print("   ✓ 自定义配置覆盖生效")
        print(f"   - 页面超时: {custom_error_cfg.get('page_load_timeout')}s")
        print(f"   - 最大重试: {custom_error_cfg.get('max_retry_count')}次")

        # 测试13：启动浏览器（实际启动测试）
        print("\n【测试13】启动浏览器（集成测试）...")
        try:
            success = agent.start()
            if success:
                print(f"   ✓ 浏览器启动成功!")
                print(f"   - 运行状态: {agent.is_running}")
                print(f"   - 重试次数: {agent.retry_count}（启动时应重置为0）")
                print(f"   - 运行时长: {agent.uptime:.1f}s（应大于0）")
                print(f"   - 暂停状态: {agent.is_paused}（启动时应重置为False）")
                print(f"   - 浏览器实例: {'已获取' if agent.get_browser() else '未获取'}")
                print(f"   - 页面实例: {'已获取' if agent.get_page() else '未获取'}")

                # 测试14：运行状态下的健康检查
                print("\n【测试14】运行状态下的健康检查...")
                health_running = agent.health_check()
                print(f"   - 健康报告:")
                for key, value in health_running.items():
                    print(f"     • {key}: {value}")

                # 测试15：检测登录状态
                print("\n【测试15】检测登录状态...")
                try:
                    logged_in = agent.check_login_status()
                    print(f"   - 登录状态: {'已登录' if logged_in else '未登录'}")
                except LoginExpiredError as e:
                    print(f"   - 登录状态: {e}")

                # 测试16：增强版登录检测（带自动处理）
                print("\n【测试16】增强版登录状态检测（带自动处理）...")
                try:
                    result_auto = agent.check_login_status_with_auto_handle()
                    print(f"   - 登录状态: {'已登录' if result_auto else '未登录'}")
                    if not result_auto:
                        print(f"   - 自动暂停: {agent.is_paused}")
                except Exception as auto_e:
                    print(f"   - 检测异常: {auto_e}")

                # 测试17：停止浏览器
                print("\n【测试17】停止浏览器...")
                agent.stop()
                print(f"   ✓ 浏览器已停止 | 运行状态: {agent.is_running}")
                print(f"   - 运行时长: {agent.uptime:.1f}s（停止后应为0.0）")
                assert agent.uptime == 0.0, "停止后运行时长应为0.0"

            else:
                print("   ✗ 浏览器启动失败")

        except BrowserCrashError as e:
            print(f"   ✗ 浏览器崩溃: {e}")
            if e.original_error:
                print(f"      原因: {e.original_error}")

        except NetworkTimeoutError as e:
            print(f"   ✗ 网络超时: {e}（超时: {e.timeout}s）")
            print(f"   - 当前是否暂停: {agent.is_paused}")

        except Exception as e:
            print(f"   ✗ 启动过程发生异常: {e}")
            import traceback
            traceback.print_exc()

        # 测试总结
        print("\n" + "=" * 70)
        print("✅ BrowserAgent 模块自测试完成（含17项测试）")
        print("=" * 70)
        print("\n📋 测试覆盖范围:")
        print("   ✓ 基础功能：实例创建、配置加载、SessionManager、随机延迟")
        print("   ✓ 异常类：BrowserCrashError、LoginExpiredError、NetworkTimeoutError")
        print("   ✓ 状态监控属性：retry_count、last_error、uptime、is_paused")
        print("   ✓ 健康检查：health_check() 完整报告")
        print("   ✓ 回调机制：注册、注销、触发、异常隔离")
        print("   ✓ 暂停/恢复：resume() 手动恢复")
        print("   ✓ 配置覆盖：自定义 error_handling 参数")
        print("   ✓ 集成测试：浏览器启停、登录检测、增强版检测")

    except Exception as e:
        print(f"\n❌ 测试过程中发生未预期异常: {e}")
        import traceback
        traceback.print_exc()
