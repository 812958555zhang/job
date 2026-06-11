"""
火山引擎豆包 LLM 调用封装模块

提供统一的 LLM 接口调用能力，支持同步/异步、普通/JSON/流式等多种调用模式，
内置错误处理、重试机制和完善的日志记录功能。

功能特性：
- 兼容 OpenAI 协议，使用 openai 库对接火山引擎豆包 API
- 支持同步和异步两种调用方式
- 内置智能重试机制（网络超时、速率限制、服务器错误）
- 自动截断超长上下文并重试
- 完善的日志记录和可观测性
- API Key 脱敏保护
"""

import json
import time
from functools import wraps
from typing import Any, Generator, Optional

from openai import AsyncOpenAI, OpenAI
from openai import (
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    ConflictError,
    InternalServerError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    UnprocessableEntityError,
)
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from utils.config_loader import load_api_config
from utils.logger import get_logger


# ============================================================
# 自定义异常类
# ============================================================


class LLMAPIError(Exception):
    """LLM API 调用基础异常"""

    def __init__(self, message: str = "LLM API 调用失败", original_error: Optional[Exception] = None):
        """
        初始化异常

        Args:
            message: 错误描述信息
            original_error: 原始异常对象（用于保留完整错误链）
        """
        self.original_error = original_error
        super().__init__(message)


class LLMAuthError(LLMAPIError):
    """API 认证失败（401）- 通常由无效或过期的 API Key 导致"""


class LLMRateLimitError(LLMAPIError):
    """速率限制（429）- 请求频率超过 API 限制"""


class LLMContextLengthError(LLMAPIError):
    """上下文长度超限 - 输入内容超过模型最大 token 限制"""


# ============================================================
# 工具函数
# ============================================================


def _mask_api_key(api_key: str) -> str:
    """
    对 API Key 进行脱敏处理

    只显示前8位和后4位字符，中间用省略号代替，
    用于日志输出时保护敏感信息。

    Args:
        api_key: 原始 API Key 字符串

    Returns:
        脱敏后的 API Key 字符串（格式：前8位...后4位）

    Example:
        >>> _mask_api_key("ark-12345678-abcdef-9012")
        'ark-1234...9012'
    """
    if len(api_key) <= 12:
        return "***" * len(api_key)
    return f"{api_key[:8]}...{api_key[-4:]}"


def _strip_markdown_json_fence(text: str) -> str:
    """去掉模型可能包裹的 ```json 代码块"""
    text = (text or "").strip()
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _repair_truncated_json_array(text: str):
    """
    尝试修复被 max_tokens 截断的 JSON 数组（保留最后一个完整对象）
    """
    text = _strip_markdown_json_fence(text)
    start = text.find("[")
    if start < 0:
        return None
    text = text[start:]
    last_obj_end = text.rfind("}")
    if last_obj_end <= 0:
        return None
    candidate = text[: last_obj_end + 1].rstrip().rstrip(",") + "]"
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None


def _parse_model_json(content_text: str, logger) -> Any:
    """解析模型 JSON 输出，截断时尽量 salvage 部分结果"""
    text = _strip_markdown_json_fence(content_text)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        repaired = _repair_truncated_json_array(content_text)
        if repaired is not None:
            logger.warning("模型 JSON 输出被截断，已自动修复并解析部分结果")
            return repaired
        raise exc


def _is_retryable_error(error: Exception) -> bool:
    """
    判断异常是否属于可重试类型

    可重试的错误包括：
    - 网络超时（连接超时、读取超时）
    - 5xx 服务器内部错误
    - 429 速率限制

    Args:
        error: 待判断的异常对象

    Returns:
        bool: 是否为可重试错误
    """
    # 网络超时类错误
    if isinstance(error, APITimeoutError):
        return True

    # 5xx 服务器错误
    if isinstance(error, InternalServerError):
        return True

    # 429 速率限制
    if isinstance(error, RateLimitError):
        return True

    return False


def _extract_retry_after(error: Exception) -> int:
    """
    从 429 异常中提取 Retry-After 响应头值

    当触发速率限制时，API 可能会在响应头中返回建议的等待时间。
    如果未找到该头信息，则返回默认值 60 秒。

    Args:
        error: RateLimitError 异常对象

    Returns:
        int: 建议等待时间（秒），默认 60 秒
    """
    if hasattr(error, "response") and error.response is not None:
        retry_after = error.response.headers.get("Retry-After")
        if retry_after:
            try:
                return int(retry_after)
            except (ValueError, TypeError):
                pass
    return 60


def _truncate_history(history: list[dict]) -> list[dict]:
    """
    截断历史消息列表，保留最近一半的消息

    当遇到上下文长度超限错误时，通过减少历史消息数量来降低 token 消耗。
    采用保留后半部分策略，确保最近的对话上下文不丢失。

    Args:
        history: 完整的历史消息列表

    Returns:
        截断后的消息列表（保留原列表的后半部分）
    """
    if not history or len(history) <= 2:
        return []
    # 保留最近一半的消息（向下取整，至少保留1条）
    keep_count = max(1, len(history) // 2)
    return history[-keep_count:]


# ============================================================
# 重试装饰器
# ============================================================


def _create_retry_decorator(max_retries: int = 3):
    """
    创建重试装饰器工厂函数

    使用 tenacity 库实现指数退避重试策略：
    - 最大重试次数：3 次
    - 退避策略：指数退避，最小等待 1 秒，最大等待 4 秒
    - 仅对可重试类型的异常进行重试

    Args:
        max_retries: 最大重试次数（默认 3 次）

    Returns:
        配置好的 tenacity retry 装饰器
    """

    def before_retry(retry_state):
        """重试前的回调函数，记录重试日志"""
        logger = get_logger(__name__)
        logger.warning(
            f"LLM 调用失败，准备第 {retry_state.attempt_number} 次重试... "
            f"错误原因: {retry_state.outcome.exception()}"
        )

    return retry(
        retry=retry_if_exception_type(
            (APITimeoutError, InternalServerError, RateLimitError)
        ),
        wait=wait_exponential(min=1, max=4),
        stop=stop_after_attempt(max_retries),
        before_sleep=before_retry,
        reraise=True,
    )


# ============================================================
# 核心客户端类
# ============================================================


class VolcengineLLMClient:
    """
    火山引擎豆包 LLM 客户端类

    封装与火山引擎豆包大语言模型的所有交互逻辑，提供：
    - 同步/异步聊天接口
    - 普通/JSON 格式/流式输出
    - 自动错误处理和重试机制
    - 完善的日志记录和可观测性

    使用示例::

        >>> client = VolcengineLLMClient()
        >>> result = client.chat("你好")
        >>> print(result["content"])

        >>> # 流式输出
        >>> for chunk in client.chat_stream("讲个故事"):
        ...     print(chunk, end="", flush=True)
    """

    # 默认配置常量
    DEFAULT_TIMEOUT: float = 90.0  # 默认请求超时时间（秒）
    DEFAULT_TEMPERATURE: float = 0.7  # 默认温度参数
    DEFAULT_MAX_TOKENS: int = 2000  # 默认最大输出 token 数
    MAX_RETRIES: int = 3  # 最大重试次数
    SLOW_REQUEST_THRESHOLD_MS: float = 5000.0  # 慢请求警告阈值（毫秒）

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        """
        初始化火山引擎 LLM 客户端

        从配置文件加载默认参数，支持通过构造函数参数覆盖。
        配置优先级：构造参数 > 配置文件 > 代码默认值

        Args:
            api_key: API 密钥（可选，优先使用此值）
            base_url: API 基础地址（可选，优先使用此值）
            model: 默认模型名称（可选，优先使用此值）
            timeout: 请求超时时间（秒，可选）
        """
        # 初始化日志记录器
        self._logger = get_logger(__name__)

        # 加载配置文件
        try:
            config = load_api_config()
            volc_config = config.get("volcengine", {})
        except Exception as e:
            self._logger.warning(f"加载 API 配置文件失败，将使用默认值: {e}")
            volc_config = {}

        # 解析配置参数（构造参数 > 配置文件 > 默认值）
        self.api_key: str = api_key or volc_config.get("api_key", "")
        self.base_url: str = base_url or volc_config.get(
            "base_url",
            "https://ark.cn-beijing.volces.com/api/coding/v3",
        )

        # 解析模型配置
        models_config = volc_config.get("models", {})
        self.default_model: str = model or models_config.get(
            "chat",
            "GLM-5.1",
        )
        self.vision_model: str = models_config.get("vision", "GLM-5.1")
        self.lite_model: str = models_config.get("lite", "GLM-5.1")

        # 超时设置（构造参数 > 配置文件 > 默认值）
        self.timeout: float = float(
            timeout or volc_config.get("timeout") or self.DEFAULT_TIMEOUT
        )

        # 安全检查：API Key 为空或占位符时发出警告
        if not self.api_key or self.api_key in ["your-api-key", "", "none"]:
            self._logger.warning(
                "⚠️ API Key 未配置或为空值！请检查 config/api_config.yaml 配置文件"
            )
        else:
            self._logger.info(
                f"✓ VolcengineLLMClient 初始化完成 | "
                f"API Key: {_mask_api_key(self.api_key)} | "
                f"Base URL: {self.base_url} | "
                f"默认模型: {self.default_model}"
            )

        # 初始化 OpenAI 同步客户端
        self._client: OpenAI = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.timeout,
        )

        # 初始化 OpenAI 异步客户端（延迟初始化）
        self._async_client: Optional[AsyncOpenAI] = None

    @property
    def async_client(self) -> AsyncOpenAI:
        """
        获取异步 OpenAI 客户端实例（懒加载单例模式）

        Returns:
            AsyncOpenAI: 异步客户端实例
        """
        if self._async_client is None:
            self._async_client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout,
            )
        return self._async_client

    # ----------------------------------------------------------
    # 核心请求构建方法
    # ----------------------------------------------------------

    def _build_messages(
        self,
        message: str,
        system_prompt: Optional[str] = None,
        history: Optional[list[dict]] = None,
    ) -> list[dict]:
        """
        构建完整的消息列表（含系统提示和历史消息）

        按照 OpenAI API 要求的格式组装消息数组，
        依次为：system prompt -> history messages -> current user message

        Args:
            message: 当前用户输入的消息文本
            system_prompt: 系统提示词（可选）
            history: 历史消息列表（可选）

        Returns:
            格式化后的消息列表，可直接传给 OpenAI API
        """
        messages = []

        # 添加系统提示词
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        # 添加历史消息
        if history:
            messages.extend(history)

        # 添加当前用户消息
        messages.append({"role": "user", "content": message})

        return messages

    def _log_request_start(
        self,
        model: str,
        message: str,
        messages_count: int,
    ) -> float:
        """
        记录请求开始的日志信息

        在每次 API 调用前记录关键参数，用于调试和监控。

        Args:
            model: 使用的模型名称
            message: 用户消息文本
            messages_count: 消息总条数（用于估算 token 数量）

        Returns:
            float: 当前时间戳（用于计算耗时）
        """
        start_time = time.time()

        # 预览消息内容（最多显示50个字符）
        message_preview = message[:50] + ("..." if len(message) > 50 else "")

        self._logger.info(
            f"🚀 开始 LLM 调用 | "
            f"模型: {model} | "
            f"消息数: {messages_count} | "
            f"输入预览: {message_preview}"
        )

        return start_time

    def _log_request_end(
        self,
        start_time: float,
        usage: dict,
        success: bool = True,
        error_msg: Optional[str] = None,
    ) -> None:
        """
        记录请求结束的日志信息

        在 API 调用完成后记录耗时、token 用量和执行状态，
        并在慢请求时发出警告。

        Args:
            start_time: 请求开始的时间戳
            usage: Token 使用量字典 {"prompt_tokens", "completion_tokens", "total_tokens"}
            success: 请求是否成功
            error_msg: 失败时的错误信息（可选）
        """
        end_time = time.time()
        elapsed_ms = (end_time - start_time) * 1000  # 转换为毫秒

        status = "✅ 成功" if success else f"❌ 失败 ({error_msg})"

        log_message = (
            f"🏁 LLM 调用完成 | "
            f"状态: {status} | "
            f"耗时: {elapsed_ms:.0f}ms | "
            f"Token 用量: 输入={usage.get('prompt_tokens', 'N/A')}, "
            f"输出={usage.get('completion_tokens', 'N/A')}, "
            f"总计={usage.get('total_tokens', 'N/A')}"
        )

        # 慢请求警告（超过阈值）
        if elapsed_ms > self.SLOW_REQUEST_THRESHOLD_MS:
            self._logger.warning(f"⏱️ 检测到慢请求！{log_message}")
        else:
            self._logger.info(log_message)

    def _parse_response(self, response) -> dict:
        """
        解析 OpenAI API 响应为标准化的结果字典

        将原始 API 响应转换为统一的数据结构，
        方便上层业务代码使用。

        Args:
            response: OpenAI ChatCompletion 响应对象

        Returns:
            dict: 标准化结果 {
                "content": 助手回复文本,
                "model": 实际使用的模型名,
                "usage": token用量统计,
                "finish_reason": 结束原因,
            }
        """
        choice = response.choices[0]

        return {
            "content": choice.message.content or "",
            "model": response.model,
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            },
            "finish_reason": choice.finish_reason,
        }

    # ----------------------------------------------------------
    # 同步方法
    # ----------------------------------------------------------

    @_create_retry_decorator()
    def chat(
        self,
        message: str,
        system_prompt: Optional[str] = None,
        history: Optional[list[dict]] = None,
        model: Optional[str] = None,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> dict:
        """
        发送聊天请求并返回完整回复（同步版本）

        这是最核心的方法，用于与 LLM 进行普通的对话交互。
        支持传入历史消息以实现多轮对话上下文保持。

        Args:
            message: 用户消息文本（必填）
            system_prompt: 系统提示词（可选，用于设定 AI 角色和行为规范）
            history: 历史消息列表（可选，格式：[{"role": "user/assistant", "content": "..."}]）
            model: 模型名称（可选，None 则使用默认模型）
            temperature: 温度参数（0.0-2.0，越高越随机，默认 0.7）
            max_tokens: 最大输出 token 数（默认 2000）

        Returns:
            dict: 标准化响应 {
                "content": str,           # 助手回复文本
                "model": str,            # 实际使用的模型名
                "usage": dict,           # token 使用量统计
                "finish_reason": str,    # 结束原因（stop/length/content_filter）
            }

        Raises:
            LLMAuthError: API 认证失败（401）
            LLMRateLimitError: 速率限制（429）
            LLMContextLengthError: 上下文长度超限
            LLMAPIError: 其他 API 调用错误
        """
        # 确定使用的模型
        actual_model = model or self.default_model

        # 构建消息列表
        messages = self._build_messages(message, system_prompt, history)

        # 记录请求开始日志
        start_time = self._log_request_start(actual_model, message, len(messages))

        try:
            # 发送 API 请求
            response = self._client.chat.completions.create(
                model=actual_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            # 解析并返回标准化结果
            result = self._parse_response(response)

            # 记录请求完成日志
            self._log_request_end(start_time, result["usage"], success=True)

            return result

        except AuthenticationError as e:
            # 认证失败（401）- 不重试，立即抛出
            self._logger.error(f"❌ API 认证失败: {e}")
            raise LLMAuthError(
                message="API 认证失败，请检查 API Key 是否正确",
                original_error=e,
            ) from e

        except RateLimitError as e:
            # 速率限制（429）- 由 tenacity 自动重试
            retry_after = _extract_retry_after(e)
            self._logger.warning(
                f"⚠️ 触发速率限制，建议等待 {retry_after}s 后重试: {e}"
            )
            raise LLMRateLimitError(
                message=f"API 速率限制，请等待 {retry_after} 秒后重试",
                original_error=e,
            ) from e

        except BadRequestError as e:
            # 参数错误（400）- 检查是否为上下文长度超限
            error_str = str(e).lower()
            if "context_length" in error_str or "max tokens" in error_str:
                self._logger.warning(f"⚠️ 上下文长度超限: {e}")
                raise LLMContextLengthError(
                    message="输入内容超过模型上下文长度限制",
                    original_error=e,
                ) from e
            # 其他参数错误直接抛出
            self._logger.error(f"❌ 请求参数错误: {e}")
            raise LLMAPIError(
                message=f"请求参数错误: {e}",
                original_error=e,
            ) from e

        except (APITimeoutError, InternalServerError) as e:
            # 网络超时或服务器错误 - 由 tenacity 自动重试
            self._logger.warning(f"⚠️ 网络或服务端错误（将自动重试）: {e}")
            raise

        except Exception as e:
            # 其他未预期的异常
            self._logger.error(f"❌ LLM 调用异常: {e}", exc_info=True)
            raise LLMAPIError(
                message=f"LLM API 调用异常: {e}",
                original_error=e,
            ) from e

    def chat_with_context_truncation(
        self,
        message: str,
        system_prompt: Optional[str] = None,
        history: Optional[list[dict]] = None,
        model: Optional[str] = None,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> dict:
        """
        带上下文截断重试的聊天方法

        在普通 chat() 方法基础上增加智能截断能力：
        当遇到上下文长度超限错误时，自动截断历史消息至最近一半后重试一次。

        适用场景：长对话场景下避免因 token 超限导致请求完全失败。

        Args:
            （参数同 chat() 方法）

        Returns:
            dict: 标准化响应（同 chat() 方法）
        """
        try:
            # 首次尝试正常调用
            return self.chat(
                message=message,
                system_prompt=system_prompt,
                history=history,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except LLMContextLengthError:
            # 上下文超限时，截断历史消息后重试一次
            self._logger.warning(
                "📝 检测到上下文超限，正在截断历史消息后重试..."
            )
            truncated_history = _truncate_history(history or [])

            return self.chat(
                message=message,
                system_prompt=system_prompt,
                history=truncated_history,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )

    def chat_json(
        self,
        message: str,
        system_prompt: Optional[str] = None,
        history: Optional[list[dict]] = None,
        model: Optional[str] = None,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> dict:
        """
        发送聊天请求并返回 JSON 格式的结构化回复

        与 chat() 方法类似，但强制要求模型以 JSON 格式返回结果，
        并自动解析 content 字段为 Python 字典对象。

        适用场景：需要结构化数据的任务，如数据提取、信息分类等。

        Args:
            （参数同 chat() 方法）

        Returns:
            dict: 标准化响应，其中 content 字段为已解析的 Python dict

        Raises:
            json.JSONDecodeError: 模型返回的内容无法解析为有效 JSON
            LLMAPIError 及其子类: 与 chat() 相同的异常体系
        """
        # 构建增强的系统提示词（添加 JSON 格式要求）
        json_system_prompt = (
            (system_prompt or "") + "\n\n请严格以 JSON 格式返回结果，不要包含任何其他文本说明。"
        ).strip()

        # 调用基础 chat 方法（带 JSON 格式约束）
        raw_result = self.chat(
            message=message,
            system_prompt=json_system_prompt,
            history=history,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        # 尝试解析 JSON 内容（截断时自动修复）
        try:
            parsed_content = _parse_model_json(raw_result["content"], self._logger)

            # 返回解析后的结果（替换原 content 为 dict）
            return {
                **raw_result,
                "content": parsed_content,
            }

        except json.JSONDecodeError as e:
            self._logger.error(
                f"❌ 模型返回的内容无法解析为 JSON: {raw_result['content'][:200]}"
            )
            raise LLMAPIError(
                message="模型返回的内容不是有效的 JSON 格式",
                original_error=e,
            ) from e

    def chat_stream(
        self,
        message: str,
        system_prompt: Optional[str] = None,
        history: Optional[list[dict]] = None,
        model: Optional[str] = None,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> Generator[str, None, None]:
        """
        发送流式聊天请求，逐块返回文本片段（生成器）

        使用 Server-Sent Events (SSE) 协议实现流式输出，
        适用于需要实时展示生成过程的场景（如打字机效果）。

        Args:
            （参数同 chat() 方法）

        Yields:
            str: 模型生成的文本片段（每次 yield 一个 chunk）

        Example:
            >>> for chunk in client.chat_stream("写一首诗"):
            ...     print(chunk, end="", flush=True)
        """
        actual_model = model or self.default_model
        messages = self._build_messages(message, system_prompt, history)

        # 记录请求开始日志
        start_time = self._log_request_start(actual_model, message, len(messages))

        total_usage = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }

        try:
            # 创建流式请求
            stream = self._client.chat.completions.create(
                model=actual_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )

            # 逐块处理流式响应
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    content_piece = chunk.choices[0].delta.content
                    yield content_piece

                # 累计 token 用量（最后一个 chunk 包含完整 usage 信息）
                if chunk.usage:
                    total_usage["prompt_tokens"] = chunk.usage.prompt_tokens or 0
                    total_usage[
                        "completion_tokens"
                    ] = chunk.usage.completion_tokens or 0
                    total_usage["total_tokens"] = chunk.usage.total_tokens or 0

            # 记录请求完成日志
            self._log_request_end(start_time, total_usage, success=True)

        except AuthenticationError as e:
            self._log_request_end(start_time, total_usage, False, str(e))
            raise LLMAuthError(
                message="API 认证失败，请检查 API Key 是否正确",
                original_error=e,
            ) from e

        except RateLimitError as e:
            self._log_request_end(start_time, total_usage, False, str(e))
            raise LLMRateLimitError(
                message="API 速率限制，请稍后重试",
                original_error=e,
            ) from e

        except (APITimeoutError, InternalServerError) as e:
            self._log_request_end(start_time, total_usage, False, str(e))
            raise LLMAPIError(
                message=f"网络或服务端错误: {e}",
                original_error=e,
            ) from e

        except Exception as e:
            self._log_request_end(start_time, total_usage, False, str(e))
            self._logger.error(f"❌ 流式 LLM 调用异常: {e}", exc_info=True)
            raise LLMAPIError(
                message=f"流式 LLM API 调用异常: {e}",
                original_error=e,
            ) from e

    # ----------------------------------------------------------
    # 异步方法
    # ----------------------------------------------------------

    async def achat(
        self,
        message: str,
        system_prompt: Optional[str] = None,
        history: Optional[list[dict]] = None,
        model: Optional[str] = None,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> dict:
        """
        发送聊天请求并返回完整回复（异步版本）

        行为与同步 chat() 方法完全一致，但基于 asyncio 实现，
        适用于高并发场景或异步 Web 框架（如 FastAPI）中调用。

        Args:
            （参数同 chat() 方法）

        Returns:
            dict: 标准化响应（同 chat() 方法）

        Raises:
            LLMAPIError 及其子类: 与 chat() 相同的异常体系
        """
        actual_model = model or self.default_model
        messages = self._build_messages(message, system_prompt, history)

        start_time = self._log_request_start(actual_model, message, len(messages))

        try:
            response = await self.async_client.chat.completions.create(
                model=actual_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            result = self._parse_response(response)
            self._log_request_end(start_time, result["usage"], success=True)

            return result

        except AuthenticationError as e:
            self._log_request_end(start_time, {}, False, str(e))
            raise LLMAuthError(
                message="API 认证失败，请检查 API Key 是否正确",
                original_error=e,
            ) from e

        except RateLimitError as e:
            self._log_request_end(start_time, {}, False, str(e))
            raise LLMRateLimitError(
                message="API 速率限制，请稍后重试",
                original_error=e,
            ) from e

        except BadRequestError as e:
            error_str = str(e).lower()
            if "context_length" in error_str or "max tokens" in error_str:
                self._log_request_end(start_time, {}, False, str(e))
                raise LLMContextLengthError(
                    message="输入内容超过模型上下文长度限制",
                    original_error=e,
                ) from e
            self._log_request_end(start_time, {}, False, str(e))
            raise LLMAPIError(
                message=f"请求参数错误: {e}",
                original_error=e,
            ) from e

        except (APITimeoutError, InternalServerError) as e:
            self._log_request_end(start_time, {}, False, str(e))
            raise

        except Exception as e:
            self._log_request_end(start_time, {}, False, str(e))
            self._logger.error(f"❌ 异步 LLM 调用异常: {e}", exc_info=True)
            raise LLMAPIError(
                message=f"异步 LLM API 调用异常: {e}",
                original_error=e,
            ) from e

    async def achat_json(
        self,
        message: str,
        system_prompt: Optional[str] = None,
        history: Optional[list[dict]] = None,
        model: Optional[str] = None,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> dict:
        """
        发送聊天请求并返回 JSON 格式的结构化回复（异步版本）

        行为与同步 chat_json() 方法完全一致，但基于 asyncio 实现。

        Args:
            （参数同 chat() 方法）

        Returns:
            dict: 标准化响应，其中 content 字段为已解析的 Python dict
        """
        json_system_prompt = (
            (system_prompt or "")
            + "\n\n请严格以 JSON 格式返回结果，不要包含任何其他文本说明。"
        ).strip()

        raw_result = await self.achat(
            message=message,
            system_prompt=json_system_prompt,
            history=history,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        try:
            parsed_content = _parse_model_json(raw_result["content"], self._logger)

            return {
                **raw_result,
                "content": parsed_content,
            }

        except json.JSONDecodeError as e:
            self._logger.error(
                f"❌ 模型返回的内容无法解析为 JSON: {raw_result['content'][:200]}"
            )
            raise LLMAPIError(
                message="模型返回的内容不是有效的 JSON 格式",
                original_error=e,
            ) from e

    async def achat_stream(
        self,
        message: str,
        system_prompt: Optional[str] = None,
        history: Optional[list[dict]] = None,
        model: Optional[str] = None,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> Generator[str, None, None]:
        """
        发送流式聊天请求，逐块返回文本片段（异步生成器）

        行为与同步 chat_stream() 方法完全一致，但基于 asyncio 实现。

        Args:
            （参数同 chat() 方法）

        Yields:
            str: 模型生成的文本片段
        """
        actual_model = model or self.default_model
        messages = self._build_messages(message, system_prompt, history)

        start_time = self._log_request_start(actual_model, message, len(messages))

        total_usage = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }

        try:
            stream = await self.async_client.chat.completions.create(
                model=actual_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )

            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    content_piece = chunk.choices[0].delta.content
                    yield content_piece

                if chunk.usage:
                    total_usage["prompt_tokens"] = chunk.usage.prompt_tokens or 0
                    total_usage[
                        "completion_tokens"
                    ] = chunk.usage.completion_tokens or 0
                    total_usage["total_tokens"] = chunk.usage.total_tokens or 0

            self._log_request_end(start_time, total_usage, success=True)

        except AuthenticationError as e:
            self._log_request_end(start_time, total_usage, False, str(e))
            raise LLMAuthError(
                message="API 认证失败，请检查 API Key 是否正确",
                original_error=e,
            ) from e

        except RateLimitError as e:
            self._log_request_end(start_time, total_usage, False, str(e))
            raise LLMRateLimitError(
                message="API 速率限制，请稍后重试",
                original_error=e,
            ) from e

        except (APITimeoutError, InternalServerError) as e:
            self._log_request_end(start_time, total_usage, False, str(e))
            raise LLMAPIError(
                message=f"网络或服务端错误: {e}",
                original_error=e,
            ) from e

        except Exception as e:
            self._log_request_end(start_time, total_usage, False, str(e))
            self._logger.error(f"❌ 异步流式 LLM 调用异常: {e}", exc_info=True)
            raise LLMAPIError(
                message=f"异步流式 LLM API 调用异常: {e}",
                original_error=e,
            ) from e

    # ----------------------------------------------------------
    # 便捷方法
    # ----------------------------------------------------------

    def simple_chat(self, message: str) -> str:
        """
        简化版聊天方法（仅返回文本内容）

        对于不需要详细元信息的简单场景，可以使用此方法快速获取回复文本。

        Args:
            message: 用户消息文本

        Returns:
            str: 模型的纯文本回复内容
        """
        result = self.chat(message=message)
        return result["content"]

    def close(self) -> None:
        """
        关闭客户端并释放资源

        在不再使用客户端时应调用此方法，
        特别是在长时间运行的应用程序中，确保及时释放 HTTP 连接池。
        """
        try:
            if hasattr(self._client, "close"):
                self._client.close()
            if self._async_client and hasattr(self._async_client, "close"):
                import asyncio

                # 尝试关闭异步客户端（如果事件循环正在运行）
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        loop.create_task(self._async_client.close())
                    else:
                        loop.run_until_complete(self._async_client.close())
                except RuntimeError:
                    pass  # 无事件循环时忽略

            self._logger.info("✓ VolcengineLLMClient 已关闭")
        except Exception as e:
            self._logger.warning(f"关闭客户端时发生异常: {e}")

    def __enter__(self):
        """支持上下文管理器协议（with 语句）"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出上下文时自动释放资源"""
        self.close()
        return False


# ============================================================
# 自测试代码块
# ============================================================

if __name__ == "__main__":
    """模块自测试代码"""
    import sys
    import io

    # 设置控制台输出编码
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

    print("=" * 70)
    print("VolcengineLLMClient 模块自测试")
    print("=" * 70)

    try:
        # 测试1：初始化客户端
        print("\n【测试1】初始化 VolcengineLLMClient...")
        with VolcengineLLMClient() as client:
            print(f"✓ 客户端创建成功")
            print(f"  - 默认模型: {client.default_model}")
            print(f"  - Base URL: {client.base_url}")
            print(f"  - API Key (脱敏): {_mask_api_key(client.api_key)}")

            # 测试2：基础聊天功能
            print("\n【测试2】测试基础 chat() 方法...")
            result = client.chat(
                message="你好，请用一句话介绍你自己",
                system_prompt="你是一个友好的AI助手",
                temperature=0.7,
                max_tokens=100,
            )
            print(f"✓ 聊天成功!")
            print(f"  - 模型: {result['model']}")
            print(f"  - 回复内容: {result['content'][:100]}...")
            print(f"  - Token 用量: {result['usage']}")
            print(f"  - 结束原因: {result['finish_reason']}")

            # 测试3：简化版聊天
            print("\n【测试3】测试 simple_chat() 方法...")
            simple_reply = client.simple_chat("1+1等于几？只回答数字")
            print(f"✓ 简化聊天回复: {simple_reply}")

            # 测试4：流式输出
            print("\n【测试4】测试 chat_stream() 方法...")
            print("  流式输出内容:", end=" ", flush=True)
            chunks = []
            for chunk in client.chat_stream(
                message="用10个字以内介绍Python",
                max_tokens=50,
            ):
                print(chunk, end="", flush=True)
                chunks.append(chunk)
            print(f"\n✓ 流式输出完成，共收到 {len(chunks)} 个文本块")

            # 测试5：JSON 格式回复
            print("\n【测试5】测试 chat_json() 方法...")
            json_result = client.chat_json(
                message='提取以下信息：姓名张三，年龄25岁，城市北京',
                system_prompt="你是一个信息提取助手",
            )
            print(f"✓ JSON 提取成功:")
            print(f"  - 类型: {type(json_result['content'])}")
            print(f"  - 内容: {json_result['content']}")

        print("\n" + "=" * 70)
        print("✅ 所有测试通过！VolcengineLLMClient 工作正常")
        print("=" * 70)

    except LLMAuthError as e:
        print(f"\n❌ 认证失败测试（预期行为）：{e}")
        print("   请检查 config/api_config.yaml 中的 API Key 配置")

    except LLMRateLimitError as e:
        print(f"\n❌ 速率限制测试（预期行为）：{e}")

    except LLMContextLengthError as e:
        print(f"\n❌ 上下文超限测试（预期行为）：{e}")

    except LLMAPIError as e:
        print(f"\n❌ API 调用失败: {e}")
        if e.original_error:
            print(f"   原始错误: {e.original_error}")

    except Exception as e:
        print(f"\n❌ 测试过程中发生未预期异常: {e}")
        import traceback

        traceback.print_exc()
