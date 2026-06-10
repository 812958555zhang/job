"""
日志系统模块 - 提供统一的日志记录功能

支持控制台彩色输出 + 文件按日期轮转存储，
各模块通过 get_logger() 获取统一配置的日志记录器实例。
"""

import logging
import sys
import os
import platform
from pathlib import Path
from logging.handlers import TimedRotatingFileHandler
from typing import Optional


# 模块级变量：记录是否已完成自动初始化
_AUTO_INITIALIZED: bool = False

# 项目根目录（utils/logger.py -> utils -> project root）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOG_DIR = _PROJECT_ROOT / "data" / "logs"
DEFAULT_LOG_FILE = DEFAULT_LOG_DIR / "job_assistant.log"


class SafeStreamHandler(logging.StreamHandler):
    """控制台 Handler：GBK 终端无法编码的字符自动替换，避免 Logging error"""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            stream = self.stream
            try:
                stream.write(msg + self.terminator)
            except UnicodeEncodeError:
                enc = getattr(stream, "encoding", None) or "utf-8"
                safe = msg.encode(enc, errors="replace").decode(enc, errors="replace")
                stream.write(safe + self.terminator)
            self.flush()
        except Exception:
            self.handleError(record)


class ColorFormatter(logging.Formatter):
    """
    彩色日志格式化器 - 在控制台中为不同级别的日志显示不同颜色

    颜色方案：
    - DEBUG: 青色
    - INFO: 绿色
    - WARNING: 黄色
    - ERROR: 红色
    - CRITICAL: 红色背景加粗

    Attributes:
        COLORS (dict): 日志级别到ANSI颜色码的映射
        RESET (str): ANSI重置颜色码
        _supports_color (bool): 当前终端是否支持彩色输出
    """

    # ANSI颜色码定义
    COLORS = {
        'DEBUG': '\033[36m',      # 青色
        'INFO': '\033[32m',       # 绿色
        'WARNING': '\033[33m',    # 黄色
        'ERROR': '\033[31m',      # 红色
        'CRITICAL': '\033[1;41m'  # 红色背景加粗
    }
    RESET = '\033[0m'  # 重置所有颜色样式

    def __init__(self, formatter: logging.Formatter):
        """
        初始化彩色格式化器

        Args:
            formatter: 基础格式化器对象，用于获取格式模板
        """
        # 直接使用基础格式化器的格式字符串进行初始化
        super().__init__(
            fmt=formatter._fmt,
            datefmt=formatter.datefmt
        )
        # 检测当前终端是否支持ANSI颜色码
        self._supports_color = self._check_color_support()

    @staticmethod
    def _check_color_support() -> bool:
        """
        检测当前运行环境是否支持终端彩色输出

        Windows 10+ 的终端原生支持ANSI颜色，
        旧版本Windows或非终端环境（如IDE、重定向输出）可能不支持。

        Returns:
            bool: 是否支持彩色输出
        """
        # 检查是否为非终端环境（输出被重定向到文件或管道）
        if not hasattr(sys.stdout, 'isatty') or not sys.stdout.isatty():
            return False

        # Windows系统特殊处理
        if platform.system() == 'Windows':
            try:
                # Windows 10+ (build 10586+) 支持ANSI转义序列
                import ctypes
                kernel32 = ctypes.windll.kernel32
                # 获取控制台输出句柄
                stdout_handle = kernel32.GetStdHandle(-11)
                # 尝试启用虚拟终端模式
                mode = ctypes.c_ulong()
                kernel32.GetConsoleMode(stdout_handle, ctypes.byref(mode))
                # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
                return kernel32.SetConsoleMode(
                    stdout_handle,
                    mode.value | 0x0004
                )
            except Exception:
                # 调用失败说明不支持或权限不足
                return False

        # Linux/macOS 默认支持
        return True

    def format(self, record: logging.LogRecord) -> str:
        """
        格式化日志记录，根据环境决定是否添加颜色

        Args:
            record: 日志记录对象，包含日志级别、消息等信息

        Returns:
            str: 格式化后的日志字符串（可能包含ANSI颜色码）
        """
        # 调用父类方法获取基础格式的日志文本
        log_message = super().format(record)

        # 仅在支持彩色的环境下添加颜色标记
        if self._supports_color and record.levelname in self.COLORS:
            log_message = (
                f"{self.COLORS[record.levelname]}"
                f"{log_message}"
                f"{self.RESET}"
            )

        return log_message


def setup_logger(
    log_level: int = logging.INFO,
    log_dir: str = "data/logs",
    console_output: bool = True,
    file_output: bool = True
) -> None:
    """
    配置并初始化日志系统

    设置根日志记录器的处理器，支持控制台彩色输出和文件按日期轮转存储。
    多次调用会清除已有配置后重新设置，确保配置一致性。

    Args:
        log_level: 日志级别，可选值包括：
                   logging.DEBUG(10), logging.INFO(20),
                   logging.WARNING(30), logging.ERROR(40), logging.CRITICAL(50)
        log_dir: 日志文件的存储目录路径，相对于项目根目录
        console_output: 是否启用控制台输出（带颜色）
        file_output: 是否启用文件输出（按天轮转）

    Example:
        >>> import logging
        >>> from utils.logger import setup_logger
        >>> setup_logger(log_level=logging.DEBUG, console_output=True)
    """
    # 获取根日志记录器
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # 清除已有处理器，避免重复添加导致日志重复输出
    if root_logger.handlers:
        root_logger.handlers.clear()

    # 定义统一的日志输出格式
    formatter = logging.Formatter(
        fmt='%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 配置控制台输出处理器
    if console_output:
        console_handler = SafeStreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        # 使用彩色格式化器包装基础格式
        color_formatter = ColorFormatter(formatter)
        console_handler.setFormatter(color_formatter)
        root_logger.addHandler(console_handler)

    # 配置文件输出处理器（按日期轮转）
    if file_output:
        log_path = Path(log_dir)
        if not log_path.is_absolute():
            log_path = _PROJECT_ROOT / log_path
        log_path.mkdir(parents=True, exist_ok=True)

        log_file = log_path / "job_assistant.log"
        file_handler = TimedRotatingFileHandler(
            filename=str(log_file),
            when='midnight',     # 每天午夜进行轮转
            interval=1,          # 每个轮转周期为1天
            backupCount=30,      # 最多保留30天的历史日志文件
            encoding='utf-8'     # 使用UTF-8编码以支持中文
        )
        file_handler.setLevel(log_level)
        # 文件输出使用普通格式化器（不含颜色码）
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    """
    获取日志记录器实例（工厂函数）

    各业务模块应通过此函数获取logger实例，保证使用统一的日志配置。
    如果日志系统尚未初始化，会自动调用默认配置。

    Args:
        name: 日志记录器名称，通常传入 __name__（当前模块的全限定名）
              例如：'core.job_screener' 或 'browser.operator'

    Returns:
        logging.Logger: 已配置好的Logger实例，可直接用于记录日志

    Example:
        >>> from utils.logger import get_logger
        >>> logger = get_logger(__name__)
        >>> logger.info("这是一条信息日志")
        >>> logger.error("操作失败", exc_info=True)
    """
    logger = logging.getLogger(name)

    # 懒加载：如果根logger没有任何处理器且当前logger也没有独立配置，
    # 则自动执行默认初始化
    if not logger.handlers and not logging.getLogger().handlers:
        setup_logger()

    return logger


def set_log_level(level: int) -> None:
    """
    动态调整日志级别（运行时切换）

    在程序运行过程中动态修改日志输出级别，
    例如从INFO切换到DEBUG以便排查问题，无需重启应用。

    Args:
        level: 新的日志级别，可选值：
               logging.DEBUG(10) - 输出所有级别日志
               logging.INFO(20) - 忽略调试信息（默认）
               logging.WARNING(30) - 仅输出警告及以上
               logging.ERROR(40) - 仅输出错误及以上
               logging.CRITICAL(50) - 仅输出严重错误

    Example:
        >>> import logging
        >>> from utils.logger import set_log_level
        >>> set_log_level(logging.DEBUG)  # 切换到调试模式
    """
    root_logger = logging.getLogger()
    # 修改根logger的级别过滤阈值
    root_logger.setLevel(level)

    # 同步更新所有已注册的处理器的级别
    for handler in root_logger.handlers:
        handler.setLevel(level)


def ensure_initialized() -> None:
    """
    确保日志系统已初始化（懒加载机制）

    供模块导入时调用，避免在模块顶层直接执行副作用操作。
    采用单次初始化模式，多次调用不会重复配置。

    此函数通常不需要手动调用，get_logger() 会自动触发初始化。
    仅在需要确保日志就绪但暂不记录日志的场景下使用。
    """
    global _AUTO_INITIALIZED
    if not _AUTO_INITIALIZED:
        setup_logger()
        _AUTO_INITIALIZED = True
