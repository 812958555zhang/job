# Tasks - 火山引擎API接入（豆包LLM调用封装）

## 任务列表

- [x] Task 1: 更新api_config.yaml配置文件
  - [x] 将volcengine.api_key更新为用户提供的真实API Key
  - [x] 添加base_url字段指向火山引擎API端点
  - [x] 更新models.chat/vision/lite为GLM-5.1模型标识

- [x] Task 2: 实现core/llm_client.py - LLM客户端核心类
  - [x] 创建VolcengineLLMClient类，封装OpenAI兼容协议调用
  - [x] 实现__init__方法：从api_config.yaml加载配置，支持构造函数参数覆盖
  - [x] 实现chat()同步方法：支持system prompt + 用户消息 + 历史消息列表
  - [x] 实现chat_json()方法：支持JSON结构化输出（response_format=json_object）
  - [x] 实现chat_stream()方法：支持流式输出（SSE逐token返回）
  - [x] 实现异步版本：achat() / achat_json() / achat_stream()
  - [x] 所有公共方法添加完整的中文注释和类型注解

- [x] Task 3: 实现错误处理与重试机制
  - [x] 封装自定义异常类：LLMAPIError / LLMAuthError / LLMRateLimitError / LLMContextLengthError
  - [x] 使用tenacity库实现指数退避重试（最多3次，间隔1s/2s/4s）
  - [x] 区分可重试错误（网络超时、5xx服务器错误）和不可重试错误（401认证失败、400参数错误）
  - [x] 实现429速率限制的Retry-After等待逻辑
  - [x] 实现Token超限时的自动截断历史重试逻辑

- [x] Task 4: 实现日志与可观测性
  - [x] 集成现有utils/logger.py日志系统
  - [x] 记录每次调用的请求摘要（模型名、输入token估算、prompt摘要）
  - [x] 记录每次调用的响应摘要（输出token数、耗时ms、成功/失败状态）
  - [x] API Key脱敏处理（日志中只显示前8位...后4位）
  - [x] 调用耗时超过5秒时发出WARNING级别日志

- [x] Task 5: 编写单元测试tests/test_llm_client.py
  - [x] 测试正常Chat Completion调用（Mock OpenAI客户端返回预设结果）
  - [x] 测试JSON模式输出（验证返回值可被json.loads解析）
  - [x] 测试流式输出（验证生成器逐token产出内容）
  - [x] 测试API Key无效时的错误处理（模拟401响应）
  - [x] 测试网络超时的重试机制（模拟超时后验证重试次数）
  - [x] 测试Token超限的截断处理（模拟context_length_exceeded错误）
  - [x] 测试配置缺失时的优雅降级（api_key为空时的行为）
  - [x] 所有测试使用mock，禁止真实调用外部API

- [x] Task 6: 集成验证与端到端测试
  - [x] 使用真实API Key执行一次简单的chat()调用验证连通性
  - [x] 验证返回结果包含预期的assistant消息内容
  - [x] 验证token使用量等元数据正确返回
  - [x] 验证异常场景（如传入无效model名称）的错误提示清晰
  - [x] 确认代码符合PEP8规范

## Task Dependencies
- [Task 2, Task 3, Task 4] depends on [Task 1] （需要先更新配置文件）
- [Task 5] depends on [Task 2, Task 3, Task 4] （测试需要核心代码完成）
- [Task 6] depends on [Task 2, Task 3, Task 4, Task 5] （集成验证在所有代码和测试完成后）

## 可并行执行的任务组
**Group 1 (串行)**: Task 1 → Task 2 + Task 3 + Task 4 → Task 5 → Task 6
