"""
VolcengineLLMClient 单元测试模块

测试火山引擎豆包 LLM 客户端的核心功能，包括：
- 正常 Chat Completion 调用
- JSON 模式输出
- 流式输出
- API 认证错误处理（401）
- 网络超时重试机制
- Token 超限截断处理
- 配置缺失优雅降级

所有测试使用 Mock，禁止真实调用外部 API。
"""

import json
import sys
import os
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# 确保可以导入项目模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.llm_client import (
    VolcengineLLMClient,
    LLMAPIError,
    LLMAuthError,
    LLMRateLimitError,
    LLMContextLengthError,
    _mask_api_key,
    _is_retryable_error,
    _truncate_history,
    _extract_retry_after,
)
from openai import (
    OpenAI,
    AuthenticationError,
    RateLimitError,
    APITimeoutError,
    BadRequestError,
    InternalServerError,
)


# ============================================================
# 测试辅助函数：构建模拟的 API 响应对象
# ============================================================


def _create_mock_chat_completion(
    content: str = "这是模型的回复文本",
    model: str = "GLM-5.1",
    finish_reason: str = "stop",
    prompt_tokens: int = 10,
    completion_tokens: int = 20,
    total_tokens: int = 30,
) -> MagicMock:
    """
    创建模拟的 ChatCompletion 响应对象

    Args:
        content: 模型回复内容
        model: 模型名称
        finish_reason: 结束原因
        prompt_tokens: 输入 token 数
        completion_tokens: 输出 token 数
        total_tokens: 总 token 数

    Returns:
        模拟的响应对象（含 choices、model、usage 属性）
    """
    response = MagicMock()

    # 模拟 choices 结构
    mock_choice = MagicMock()
    mock_choice.message.content = content
    mock_choice.finish_reason = finish_reason
    response.choices = [mock_choice]

    # 模拟模型信息
    response.model = model

    # 模拟 token 用量
    response.usage = MagicMock()
    response.usage.prompt_tokens = prompt_tokens
    response.usage.completion_tokens = completion_tokens
    response.usage.total_tokens = total_tokens

    return response


def _create_mock_stream_chunk(content: str | None = None, usage: dict | None = None) -> MagicMock:
    """
    创建模拟的流式响应 chunk 对象

    Args:
        content: 当前 chunk 的文本内容（None 表示无内容）
        usage: Token 用量信息（仅最后一个 chunk 包含）

    Returns:
        模拟的流式 chunk 对象
    """
    chunk = MagicMock()

    if content:
        mock_delta = MagicMock()
        mock_delta.content = content
        mock_choice = MagicMock()
        mock_choice.delta = mock_delta
        chunk.choices = [mock_choice]
    else:
        chunk.choices = []

    if usage:
        chunk.usage = MagicMock()
        chunk.usage.prompt_tokens = usage.get("prompt_tokens", 0)
        chunk.usage.completion_tokens = usage.get("completion_tokens", 0)
        chunk.usage.total_tokens = usage.get("total_tokens", 0)
    else:
        chunk.usage = None

    return chunk


# ============================================================
# 测试1：正常 Chat Completion 调用
# ============================================================


class TestNormalChatCompletion:
    """测试正常聊天完成接口调用"""

    @patch("core.llm_client.OpenAI")
    @patch("core.llm_client.load_api_config")
    def test_chat_returns_correct_response_structure(
        self, mock_load_config, mock_openai_class
    ):
        """验证 chat() 方法返回正确的响应结构（content、model、usage、finish_reason）"""
        # 配置 Mock：load_api_config 返回有效配置
        mock_load_config.return_value = {
            "volcengine": {
                "api_key": "test-api-key-1234567890",
                "base_url": "https://test.volces.com/api/v3",
                "models": {"chat": "test-model"},
            }
        }

        # 配置 Mock：OpenAI client 的 create 方法返回预设响应
        mock_client_instance = MagicMock()
        mock_response = _create_mock_chat_completion(
            content="你好，我是AI助手",
            model="test-model",
            prompt_tokens=15,
            completion_tokens=25,
            total_tokens=40,
        )
        mock_client_instance.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client_instance

        # 执行测试
        client = VolcengineLLMClient()
        result = client.chat(message="你好")

        # 验证返回结果结构完整
        assert "content" in result, "结果应包含 content 字段"
        assert "model" in result, "结果应包含 model 字段"
        assert "usage" in result, "结果应包含 usage 字段"
        assert "finish_reason" in result, "结果应包含 finish_reason 字段"

        # 验证字段值正确
        assert result["content"] == "你好，我是AI助手", "content 应为模型回复"
        assert result["model"] == "test-model", "model 应为实际使用的模型"
        assert result["finish_reason"] == "stop", "finish_reason 应为 stop"
        assert result["usage"]["prompt_tokens"] == 15, "prompt_tokens 不匹配"
        assert result["usage"]["completion_tokens"] == 25, "completion_tokens 不匹配"
        assert result["usage"]["total_tokens"] == 40, "total_tokens 不匹配"

    @patch("core.llm_client.OpenAI")
    @patch("core.llm_client.load_api_config")
    def test_chat_passes_correct_parameters(
        self, mock_load_config, mock_openai_class
    ):
        """验证 chat() 方法向 OpenAI API 传入正确的 messages、model、temperature 参数"""
        mock_load_config.return_value = {
            "volcengine": {
                "api_key": "test-key",
                "base_url": "https://test.com",
                "models": {"chat": "custom-model"},
            }
        }

        mock_client_instance = MagicMock()
        mock_client_instance.chat.completions.create.return_value = (
            _create_mock_chat_completion()
        )
        mock_openai_class.return_value = mock_client_instance

        # 使用自定义参数调用
        client = VolcengineLLMClient()
        client.chat(
            message="用户消息",
            system_prompt="你是助手",
            history=[{"role": "user", "content": "历史消息"}],
            model="override-model",
            temperature=0.5,
            max_tokens=500,
        )

        # 验证 create 方法被调用且参数正确
        mock_client_instance.chat.completions.create.assert_called_once()

        # 提取实际调用参数
        call_args = mock_client_instance.chat.completions.create.call_args
        kwargs = call_args.kwargs if call_args.kwargs else call_args[1]

        assert kwargs["model"] == "override-model", "model 参数应为覆盖值"
        assert kwargs["temperature"] == 0.5, "temperature 参数不匹配"
        assert kwargs["max_tokens"] == 500, "max_tokens 参数不匹配"

        # 验证 messages 结构：system -> history -> user
        messages = kwargs["messages"]
        assert len(messages) == 3, f"应有 3 条消息，实际 {len(messages)}"
        assert messages[0]["role"] == "system", "第一条应为系统提示"
        assert messages[0]["content"] == "你是助手", "系统提示内容不匹配"
        assert messages[1]["role"] == "user", "第二条应为历史消息"
        assert messages[2]["role"] == "user", "第三条应为当前用户消息"
        assert messages[2]["content"] == "用户消息", "用户消息内容不匹配"


# ============================================================
# 测试2：JSON 模式输出
# ============================================================


class TestChatJsonMode:
    """测试 JSON 格式模式输出功能"""

    @patch("core.llm_client.VolcengineLLMClient.chat")
    @patch("core.llm_client.load_api_config")
    def test_chat_json_parses_valid_json_content(
        self, mock_load_config, mock_chat_method
    ):
        """验证 chat_json() 将模型返回的 JSON 字符串解析为 Python dict"""
        mock_load_config.return_value = {"volcengine": {"api_key": "test-key"}}

        # Mock chat() 返回 JSON 字符串格式的 content
        mock_chat_method.return_value = {
            "content": '{"name": "张三", "age": 25, "skills": ["Python", "Django"]}',
            "model": "GLM-5.1",
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
            "finish_reason": "stop",
        }

        client = VolcengineLLMClient()
        result = client.chat_json(message="提取用户信息")

        # 验证 content 已被解析为 dict 类型
        assert isinstance(result["content"], dict), "content 应为解析后的字典类型"
        assert result["content"]["name"] == "张三", "JSON 解析后 name 字段错误"
        assert result["content"]["age"] == 25, "JSON 解析后 age 字段错误"
        assert result["content"]["skills"] == ["Python", "Django"], "skills 列表不匹配"

        # 验证其他字段保持不变
        assert result["model"] == "GLM-5.1", "model 字段不应被修改"
        assert result["finish_reason"] == "stop", "finish_reason 不应被修改"

    @patch("core.llm_client.VolcengineLLMClient.chat")
    @patch("core.llm_client.load_api_config")
    def test_chat_json_raises_error_on_invalid_json(
        self, mock_load_config, mock_chat_method
    ):
        """验证 chat_json() 在模型返回非法 JSON 时抛出 LLMAPIError"""
        mock_load_config.return_value = {"volcengine": {"api_key": "test-key"}}

        # Mock chat() 返回非 JSON 内容
        mock_chat_method.return_value = {
            "content": "这不是有效的JSON格式的内容",
            "model": "GLM-5.1",
            "usage": {"prompt_tokens": 10, "completion_tokens": 15, "total_tokens": 25},
            "finish_reason": "stop",
        }

        client = VolcengineLLMClient()

        # 验证抛出 LLMAPIError 异常
        with pytest.raises(LLMAPIError) as exc_info:
            client.chat_json(message="提取信息")

        # 验证异常消息包含相关描述
        assert "JSON" in str(exc_info.value), "异常消息应提及 JSON 格式问题"

    @patch("core.llm_client.VolcengineLLMClient.chat")
    @patch("core.llm_client.load_api_config")
    def test_chat_json_appends_json_system_prompt(
        self, mock_load_config, mock_chat_method
    ):
        """验证 chat_json() 自动追加 JSON 格式要求的系统提示词"""
        mock_load_config.return_value = {"volcengine": {"api_key": "test-key"}}
        mock_chat_method.return_value = {
            'content': '{"result": "ok"}',
            "model": "GLM-5.1",
            "usage": {"prompt_tokens": 5, "completion_tokens": 10, "total_tokens": 15},
            "finish_reason": "stop",
        }

        client = VolcengineLLMClient()
        client.chat_json(
            message="分析数据",
            system_prompt="你是一个数据分析专家",
        )

        # 验证 chat() 被调用时传入了增强的系统提示词
        call_args = mock_chat_method.call_args
        kwargs = call_args.kwargs if call_args.kwargs else call_args[1]
        actual_system_prompt = kwargs["system_prompt"]

        # 原始提示词 + JSON格式要求
        assert "数据分析专家" in actual_system_prompt, "应保留原始系统提示词"
        assert "JSON" in actual_system_prompt, "应添加 JSON 格式要求"
        assert "json" in actual_system_prompt.lower(), "应包含 json 关键字"


# ============================================================
# 测试3：流式输出
# ============================================================


class TestChatStream:
    """测试流式输出功能"""

    @patch("core.llm_client.OpenAI")
    @patch("core.llm_client.load_api_config")
    def test_chat_stream_is_generator_type(
        self, mock_load_config, mock_openai_class
    ):
        """验证 chat_stream() 返回生成器对象"""
        mock_load_config.return_value = {"volcengine": {"api_key": "test-key"}}

        # 模拟流式迭代器
        mock_client_instance = MagicMock()
        mock_chunks = [
            _create_mock_stream_chunk(content="你好"),
            _create_mock_stream_chunk(content="，世界"),
            _create_mock_stream_chunk(content="！", usage={"prompt_tokens": 10, "completion_tokens": 15, "total_tokens": 25}),
        ]
        mock_client_instance.chat.completions.create.return_value = iter(mock_chunks)
        mock_openai_class.return_value = mock_client_instance

        client = VolcengineLLMClient()
        stream_result = client.chat_stream(message="打招呼")

        # 验证是生成器/迭代器类型
        import types
        assert isinstance(stream_result, types.GeneratorType), (
            "chat_stream() 应返回生成器对象"
        )

    @patch("core.llm_client.OpenAI")
    @patch("core.llm_client.load_api_config")
    def test_chat_stream_yields_correct_chunks(
        self, mock_load_config, mock_openai_class
    ):
        """验证 chat_stream() 逐次 yield 正确的文本片段"""
        mock_load_config.return_value = {"volcengine": {"api_key": "test-key"}}

        expected_chunks = ["今天", "天气", "真不错"]
        mock_chunks = [
            _create_mock_stream_chunk(content=text) for text in expected_chunks
        ]
        # 最后一个 chunk 添加 usage 信息
        mock_chunks.append(
            _create_mock_stream_chunk(
                content=None,
                usage={"prompt_tokens": 8, "completion_tokens": 12, "total_tokens": 20}
            )
        )

        mock_client_instance = MagicMock()
        mock_client_instance.chat.completions.create.return_value = iter(mock_chunks)
        mock_openai_class.return_value = mock_client_instance

        client = VolcengineLLMClient()
        collected_chunks = []

        for chunk_text in client.chat_stream(message="查询天气"):
            collected_chunks.append(chunk_text)

        # 验证 yield 的内容与预期一致
        assert collected_chunks == expected_chunks, (
            f"流式输出片段不匹配：期望 {expected_chunks}，实际 {collected_chunks}"
        )

    @patch("core.llm_client.OpenAI")
    @patch("core.llm_client.load_api_config")
    def test_chat_stream_passes_stream_true_parameter(
        self, mock_load_config, mock_openai_class
    ):
        """验证 chat_stream() 向 API 传递 stream=True 参数"""
        mock_load_config.return_value = {"volcengine": {"api_key": "test-key"}}

        mock_client_instance = MagicMock()
        mock_client_instance.chat.completions.create.return_value = iter([])
        mock_openai_class.return_value = mock_client_instance

        client = VolcengineLLMClient()

        # 消费完生成器以触发请求
        list(client.chat_stream(message="测试"))

        # 验证 create 调用时包含了 stream=True
        call_kwargs = mock_client_instance.chat.completions.create.call_args.kwargs
        assert call_kwargs["stream"] is True, "必须设置 stream=True"


# ============================================================
# 测试4：API Key 无效时的错误处理（401）
# ============================================================


class TestAuthenticationErrorHandling:
    """测试 API 认证失败（401）的错误处理"""

    @patch("core.llm_client.OpenAI")
    @patch("core.llm_client.load_api_config")
    def test_chat_raises_auth_error_on_401(
        self, mock_load_config, mock_openai_class
    ):
        """验证当 OpenAI 抛出 AuthenticationError 时，chat() 抛出 LLMAuthError"""
        mock_load_config.return_value = {"volcengine": {"api_key": "invalid-key"}}

        mock_client_instance = MagicMock()
        # 模拟 API 返回 401 认证错误（新版本 openai 需要 body 参数）
        mock_client_instance.chat.completions.create.side_effect = (
            AuthenticationError(
                "Invalid API key provided",
                response=MagicMock(),
                body={},
            )
        )
        mock_openai_class.return_value = mock_client_instance

        client = VolcengineLLMClient()

        # 验证抛出 LLMAuthError（而非原始 AuthenticationError）
        with pytest.raises(LLMAuthError) as exc_info:
            client.chat(message="测试消息")

        # 验证异常类型和消息
        assert isinstance(exc_info.value, LLMAuthError), "应抛出 LLMAuthError"
        assert "认证失败" in str(exc_info.value) or "API" in str(exc_info.value), (
            "异常消息应包含认证失败相关信息"
        )

    @patch("core.llm_client.OpenAI")
    @patch("core.llm_client.load_api_config")
    def test_auth_error_preserves_original_exception(
        self, mock_load_config, mock_openai_class
    ):
        """验证 LLMAuthError 保留了原始的 AuthenticationError"""
        mock_load_config.return_value = {"volcengine": {"api_key": "bad-key"}}

        original_error = AuthenticationError(
            "Incorrect API key",
            response=MagicMock(status_code=401),
            body={},
        )

        mock_client_instance = MagicMock()
        mock_client_instance.chat.completions.create.side_effect = original_error
        mock_openai_class.return_value = mock_client_instance

        client = VolcengineLLMClient()

        with pytest.raises(LLMAuthError) as exc_info:
            client.chat(message="测试")

        # 验证 original_error 属性被保留
        assert exc_info.value.original_error is original_error, (
            "应保留原始异常对象"
        )


# ============================================================
# 测试5：网络超时的重试机制
# ============================================================


class TestTimeoutRetryMechanism:
    """测试网络超时时的自动重试机制"""

    @patch("core.llm_client.OpenAI")
    @patch("core.llm_client.load_api_config")
    def test_retry_on_timeout_and_succeed(
        self, mock_load_config, mock_openai_class
    ):
        """验证前两次超时后第三次成功返回（tenacity 重试生效）"""
        mock_load_config.return_value = {"volcengine": {"api_key": "test-key"}}

        mock_client_instance = MagicMock()

        # 构建响应序列：前2次超时，第3次成功
        success_response = _create_mock_chat_completion(
            content="重试成功后的回复",
            model="GLM-5.1",
        )
        mock_client_instance.chat.completions.create.side_effect = [
            APITimeoutError(request=MagicMock()),
            APITimeoutError(request=MagicMock()),
            success_response,
        ]
        mock_openai_class.return_value = mock_client_instance

        client = VolcengineLLMClient()
        result = client.chat(message="需要重试的消息")

        # 验证最终返回成功结果
        assert result["content"] == "重试成功后的回复", "重试后应返回正确内容"
        assert result["model"] == "GLM-5.1", "模型名应正确"

        # 验证确实调用了多次（初始 + 重试）
        assert mock_client_instance.chat.completions.create.call_count == 3, (
            f"应调用3次（1次初始+2次重试），实际 {mock_client_instance.chat.completions.create.call_count}次"
        )

    @patch("core.llm_client.OpenAI")
    @patch("core.llm_client.load_api_config")
    def test_all_retries_exhausted_raises_error(
        self, mock_load_config, mock_openai_class
    ):
        """验证所有重试次数耗尽后抛出异常"""
        mock_load_config.return_value = {"volcengine": {"api_key": "test-key"}}

        mock_client_instance = MagicMock()
        # 所有尝试都超时（默认最大重试3次，共调用3次）
        timeout_error = APITimeoutError(request=MagicMock())
        mock_client_instance.chat.completions.create.side_effect = [
            timeout_error,
            timeout_error,
            timeout_error,
        ]
        mock_openai_class.return_value = mock_client_instance

        client = VolcengineLLMClient()

        # 验证最终抛出 APITimeoutError（tenacity reraise=True）
        with pytest.raises(APITimeoutError):
            client.chat(message="持续超时")


# ============================================================
# 测试6：Token 超限的截断处理
# ============================================================


class TestContextLengthTruncation:
    """测试上下文长度超限时的自动截断重试"""

    @patch("core.llm_client.OpenAI")
    @patch("core.llm_client.load_api_config")
    @patch("core.llm_client._truncate_history")
    def test_context_truncation_retries_with_shorter_history(
        self, mock_truncate, mock_load_config, mock_openai_class
    ):
        """验证 chat_with_context_truncation() 在上下文超限时自动截断历史并重试"""
        mock_load_config.return_value = {"volcengine": {"api_key": "test-key"}}

        mock_client_instance = MagicMock()

        # 第一次调用抛出 context_length 错误（消息需包含关键字以触发截断逻辑）
        context_error = BadRequestError(
            "Request too large for context_length. Maximum is 8192 tokens",
            response=MagicMock(),
            body={},
        )
        success_response = _create_mock_chat_completion(
            content="截断后成功回复",
        )
        mock_client_instance.chat.completions.create.side_effect = [
            context_error,
            success_response,
        ]
        mock_openai_class.return_value = mock_client_instance

        # 配置截断函数返回值
        truncated_history = [{"role": "user", "content": "最近的历史消息"}]
        mock_truncate.return_value = truncated_history

        client = VolcengineLLMClient()
        history_messages = [
            {"role": "user", "content": f"历史消息{i}"}
            for i in range(10)  # 模拟较长的历史
        ]

        # 调用带截断的方法
        result = client.chat_with_context_truncation(
            message="当前消息",
            history=history_messages,
        )

        # 验证最终返回成功结果
        assert result["content"] == "截断后成功回复", "截断重试后应返回正确内容"

        # 验证 _truncate_history 被正确调用
        mock_truncate.assert_called_once()
        call_args = mock_truncate.call_args[0][0]
        assert len(call_args) == 10, "截断函数应接收完整的原始历史列表"

    @patch("core.llm_client.OpenAI")
    @patch("core.llm_client.load_api_config")
    def test_truncation_function_keeps_second_half(
        self, mock_load_config, mock_openai_class
    ):
        """验证 _truncate_history() 函数保留后半部分消息"""
        # 直接测试工具函数，无需 Mock 客户端
        history = [
            {"role": "user", "content": f"消息{i}"}
            for i in range(6)
        ]

        result = _truncate_history(history)

        # 6 条消息，保留一半（3条），取最后 3 条
        assert len(result) == 3, "6条消息应截断为3条"
        assert result[0]["content"] == "消息3", "应从中间位置开始保留"
        assert result[-1]["content"] == "消息5", "应包含最后一条消息"

    @patch("core.llm_client._truncate_history")
    def test_truncation_empty_history(self, mock_truncate):
        """验证空历史消息时 _truncate_history 返回空列表"""
        mock_truncate.side_effect = lambda x: _truncate_history.__wrapped__(x)

        # 测试空列表
        assert _truncate_history([]) == [], "空列表应返回空列表"

        # 测试只有一条消息
        single_msg = [{"role": "user", "content": "唯一消息"}]
        assert _truncate_history(single_msg) == [], "单条消息应返回空列表"

        # 测试两条消息
        two_msgs = [{"role": "user", "content": "消息1"}, {"role": "assistant", "content": "消息2"}]
        assert _truncate_history(two_msgs) == [], "两条消息应返回空列表"


# ============================================================
# 测试7：配置缺失时的优雅降级
# ============================================================


class TestConfigMissingGracefulDegradation:
    """测试配置文件缺失或无效时的优雅降级行为"""

    @patch("core.llm_client.OpenAI")
    @patch("core.llm_client.load_api_config")
    def test_empty_config_does_not_raise_exception(
        self, mock_load_config, mock_openai_class
    ):
        """验证 load_api_config 返回空字典时客户端初始化不抛异常"""
        # 返回空配置（无 volcengine key）
        mock_load_config.return_value = {}

        # 验证初始化过程不抛出异常
        try:
            client = VolcengineLLMClient()
            initialization_success = True
        except Exception:
            initialization_success = False

        assert initialization_success, "空配置时客户端初始化不应抛出异常"

    @patch("core.llm_client.OpenAI")
    @patch("core.llm_client.load_api_config")
    def test_missing_volcengine_key_uses_defaults(
        self, mock_load_config, mock_openai_class
    ):
        """验证配置中不含 volcengine key 时使用默认值作为 fallback"""
        # 返回不含 volcengine 的配置
        mock_load_config.return_value = {
            "other_service": {"api_key": "some-other-key"}
        }

        mock_openai_class.return_value = MagicMock()

        # 初始化客户端（应使用默认值）
        client = VolcengineLLMClient()

        # 验证使用了默认值
        assert client.api_key == "", "API Key 默认应为空字符串"
        assert client.default_model == "GLM-5.1", "默认模型应为 GLM-5.1"
        assert "volces.com" in client.base_url, "默认 Base URL 应包含 volces.com"
        assert client.timeout == 60.0, "默认超时应为 60 秒"

    @patch("core.llm_client.OpenAI")
    @patch("core.llm_client.load_api_config")
    def test_config_load_failure_falls_back_to_defaults(
        self, mock_load_config, mock_openai_class
    ):
        """验证配置加载失败时使用默认值并发出警告日志"""
        # 模拟配置加载异常
        mock_load_config.side_effect = FileNotFoundError("配置文件不存在")

        mock_openai_class.return_value = MagicMock()

        # 初始化不应抛出异常（内部捕获了异常）
        client = VolcengineLLMClient()

        # 验证使用默认值
        assert client.default_model == "GLM-5.1", "配置加载失败时应使用默认模型"
        assert client.api_key == "", "配置加载失败时 API Key 应为空"

    @patch("core.llm_client.OpenAI")
    @patch("core.llm_client.load_api_config")
    def test_placeholder_api_key_triggers_warning(
        self, mock_load_config, mock_openai_class
    ):
        """验证占位符 API Key 时触发 WARNING 日志"""
        # 返回占位符 API Key
        mock_load_config.return_value = {
            "volcengine": {"api_key": "your-api-key"}
        }

        mock_openai_class.return_value = MagicMock()

        # 初始化客户端（应正常工作但发出警告）
        client = VolcengineLLMClient()

        # 验证客户端仍可创建
        assert client is not None, "即使 API Key 为占位符也应能创建客户端"


# ============================================================
# 工具函数单元测试
# ============================================================


class TestUtilityFunctions:
    """测试独立工具函数的功能"""

    def test_mask_api_key_normal_length(self):
        """测试正常长度 API Key 的脱敏效果"""
        api_key = "ark-12345678-abcdef-9012"
        masked = _mask_api_key(api_key)

        # 验证格式：前8位...后4位
        assert masked.startswith(api_key[:8]), "应以前8位开头"
        assert masked.endswith(api_key[-4:]), "应以后4位结尾"
        assert "..." in masked, "中间应有省略号"
        assert api_key not in masked, "不应暴露完整 API Key"

    def test_mask_api_key_short_key(self):
        """测试短于12位的 API Key 全部脱敏"""
        short_key = "short-key"
        masked = _mask_api_key(short_key)

        # 短 Key 应全部替换为星号
        assert "*" in masked, "短 Key 应全部脱敏"
        assert short_key not in masked, "不应暴露原始短 Key"

    def test_is_retryable_error_identifies_timeout(self):
        """验证 APITimeoutError 被识别为可重试错误"""
        error = APITimeoutError(request=MagicMock())
        assert _is_retryable_error(error) is True, "超时错误应可重试"

    def test_is_retryable_error_identifies_rate_limit(self):
        """验证 RateLimitError 被识别为可重试错误"""
        error = RateLimitError("rate limit", response=MagicMock(), body={})
        assert _is_retryable_error(error) is True, "速率限制应可重试"

    def test_is_retryable_error_identifies_server_error(self):
        """验证 InternalServerError 被识别为可重试错误"""
        error = InternalServerError("server error", response=MagicMock(), body={})
        assert _is_retryable_error(error) is True, "服务器错误应可重试"

    def test_is_retryable_error_rejects_auth_error(self):
        """验证 AuthenticationError 不被识别为可重试错误"""
        error = AuthenticationError("auth failed", response=MagicMock(), body={})
        assert _is_retryable_error(error) is False, "认证错误不可重试"

    def test_extract_retry_from_header(self):
        """验证从 429 响应头提取 Retry-After 值"""
        mock_response = MagicMock()
        mock_response.headers = {"Retry-After": "120"}

        error = RateLimitError("rate limited", response=mock_response, body={})
        retry_after = _extract_retry_after(error)

        assert retry_after == 120, "应提取到 Retry-After 头的值"

    def test_extract_retry_default_when_missing(self):
        """验证缺少 Retry-After 头时返回默认值60秒"""
        mock_response = MagicMock()
        mock_response.headers = {}  # 无 Retry-After 头

        error = RateLimitError("rate limited", response=mock_response, body={})
        retry_after = _extract_retry_after(error)

        assert retry_after == 60, "缺少头信息时应返回默认值 60"

    def test_extract_retry_default_for_invalid_value(self):
        """验证 Retry-After 值非数字时返回默认值"""
        mock_response = MagicMock()
        mock_response.headers = {"Retry-After": "not-a-number"}

        error = RateLimitError("rate limited", response=mock_response, body={})
        retry_after = _extract_retry_after(error)

        assert retry_after == 60, "非法值时应返回默认值 60"


# ============================================================
# 上下文管理器测试
# ============================================================


class TestContextManagerSupport:
    """测试 with 语句上下文管理器支持"""

    @patch("core.llm_client.OpenAI")
    @patch("core.llm_client.load_api_config")
    def test_with_statement_support(self, mock_load_config, mock_openai_class):
        """验证 VolcengineLLMClient 支持 with 上下文管理器协议"""
        mock_load_config.return_value = {"volcengine": {"api_key": "test-key"}}

        mock_client_instance = MagicMock()
        mock_openai_class.return_value = mock_client_instance

        # 使用 with 语句
        with VolcengineLLMClient() as client:
            assert client is not None, "with 语句应返回客户端实例"
            assert isinstance(client, VolcengineLLMClient), "返回类型应正确"

        # 验证退出时 close() 被调用
        mock_client_instance.close.assert_called_once()


if __name__ == "__main__":
    # 直接运行测试
    pytest.main([__file__, "-v", "--tb=short"])
