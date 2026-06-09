# 火山引擎API接入 - 豆包LLM调用封装 Spec

## Why

项目当前已有完整的基础架构（数据模型、配置管理、数据库、日志系统、GUI框架），但**缺少AI核心能力层**——即与火山引擎豆包LLM的通信能力。PRD Phase 2明确要求实现"火山引擎API对接封装（LLM调用 / Vision调用 / 错误处理/重试）"，这是后续**简历AI解析、岗位理解、话术生成、回复生成**等所有AI功能的底层依赖，必须优先实现。

## What Changes

- 新增 `core/llm_client.py` — 火山引擎LLM客户端封装模块（基于OpenAI兼容协议）
- 更新 `config/api_config.yaml` — 填入真实API Key和模型端点信息
- 更新 `requirements.txt` — 确认openai依赖已包含（当前已存在 openai==2.41.0）
- 新增 `tests/test_llm_client.py` — LLM客户端单元测试（Mock外部依赖）

## Impact

- Affected specs: 无（全新模块，不影响现有spec）
- Affected code:
  - `core/llm_client.py`（新建）
  - `config/api_config.yaml`（更新API配置）
  - `core/resume_parser.py`（未来对接，本次不修改）
  - `core/chat_generator.py`（未来对接，本次不修改）

## ADDED Requirements

### Requirement: 火山引擎LLM客户端

系统SHALL提供基于OpenAI兼容协议的火山引擎豆包LLM调用封装，支持同步和异步两种调用方式。

#### 场景1: 基础对话调用（Chat Completion）

- **WHEN** 调用方传入系统提示词和用户消息
- **THEN** 客户端SHALL通过OpenAI兼容协议向火山引擎API发送请求并返回完整的助手回复文本
- **AND** 返回结果SHALL包含模型名称、token使用量等元数据信息

#### 场景2: 结构化输出调用（JSON Mode / Structured Output）

- **WHEN** 调用方指定response_format为json_object或提供Pydantic模型
- **THEN** 客户端SHALL返回符合指定格式的结构化数据（字典或Pydantic模型实例）

#### 场景3: 多轮对话上下文管理

- **WHEN** 调用方传入历史消息列表（含system/user/assistant角色）
- **THEN** 客户端SHALL将完整对话历史发送给LLM以保持上下文连贯性

#### 场景4: 流式输出（Streaming）

- **WHEN** 调用方启用stream=True参数
- **THEN** 客户端SHALL逐token返回生成内容，支持实时显示进度

### Requirement: 错误处理与重试机制

系统SHALL对API调用异常进行完善处理，确保网络波动等临时故障不会导致程序崩溃。

#### 场景5: 网络超时重试

- **WHEN** API请求因网络超时失败
- **THEN** 客户端SHALL自动重试最多3次，每次间隔指数退避（1s → 2s → 4s）
- **AND** 最终仍失败时抛出明确的业务异常，记录完整错误日志

#### 场景6: API Key无效处理

- **WHEN** API Key未配置或已失效（HTTP 401）
- **THEN** 客户端SHALL立即停止重试并返回明确的错误提示："API密钥无效，请检查配置"

#### 场景7: 速率限制处理

- **WHEN** 触发API速率限制（HTTP 429）
- **THEN** 客户端SHALL等待Retry-After头指定的时间后重试，默认等待60秒

#### 场景8: Token超限处理

- **WHEN** 请求内容超过模型上下文长度限制
- **THEN** 客户端SHALL截断消息历史（保留最近的N条）后重试一次

### Requirement: 配置集成

系统SHALL从现有api_config.yaml读取火山引擎配置，无需硬编码。

#### 场景9: 配置加载

- **WHEN** LLM客户端初始化时
- **THEN** 自动从api_config.yaml读取api_key、base_url、model等配置项
- **AND** 支持运行时覆盖配置（构造函数参数优先级高于配置文件）

#### 场景10: 配置校验

- **WHEN** api_config.yaml中volcengine.api_key为空或占位符值
- **THEN** 初始化时发出WARNING级别日志提醒用户配置API Key
- **AND** 首次实际调用时再抛出明确错误

### Requirement: 日志与可观测性

系统SHALL对所有LLM调用进行详细日志记录。

#### 场景11: 调用日志

- **WHEN** 每次发起LLM调用时
- **THEN** 记录请求摘要（模型名、输入token数估算、prompt前50字符）
- **AND** 记录响应摘要（输出token数、耗时ms、是否成功）
- **AND** 敏感信息（API Key完整值）不得出现在日志中

## MODIFIED Requirements

### Requirement: api_config.yaml配置更新

更新api_config.yaml中的占位符为真实配置值：

```yaml
volcengine:
  api_key: "ark-3ada555a-4c56-419d-9803-d6151c838791-821ab"
  base_url: "https://ark.cn-beijing.volces.com/api/coding/v3"
  models:
    chat: "GLM-5.1"
    vision: "GLM-5.1"   # Vision复用同一模型端点
    lite: "GLM-5.1"     # Lite复用同一模型端点（后续可替换为轻量模型）
```

> **注意**: 当前阶段chat/vision/lite均使用GLM-5.1模型，后续可根据成本优化策略切换为不同模型端点。
