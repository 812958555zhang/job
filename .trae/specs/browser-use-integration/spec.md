# Browser Use 集成 - 初始化浏览器自动化 Agent Spec

## Why
项目已完成了基础架构搭建（数据模型、配置管理、数据库、日志系统、GUI框架），下一步需要实现核心的浏览器自动化能力。Browser Use 是本项目的核心技术组件，负责控制 Chromium 浏览器访问 BOSS 直聘网页版，是实现自动求职流程的基础设施。

## What Changes
- 新增 `browser/agent.py` 模块：封装 Browser Use Agent 的初始化、启动和关闭逻辑
- 新增 `browser/session_manager.py` 模块：管理浏览器会话（登录态保持、多标签页管理）
- 更新 `browser/__init__.py`：导出新模块的公共接口
- 更新 `config/api_config.yaml`：添加 Browser Use 相关配置项（Chromium 路径、反检测选项等）
- 安装并配置 `browser-use` 依赖及其子依赖（playwright + chromium）

### 核心功能点
1. **Browser Use Agent 初始化**
   - 配置 undetectable 反检测模式
   - 设置自定义 LLM（豆包）用于 DOM 理解和元素定位
   - 配置浏览器启动参数（窗口大小、是否显示浏览器等）

2. **浏览器生命周期管理**
   - 启动 Chromium 浏览器实例
   - 打开 BOSS 直聘网页版（www.zhipin.com）
   - 优雅关闭浏览器（释放资源）

3. **会话管理**
   - 支持接管用户已有的浏览器 Session（保持登录态）
   - Cookie 持久化存储与恢复
   - 多标签页管理（搜索列表页 / 岗位详情页 / 聊天窗口）

4. **异常处理与状态监控**
   - 检测浏览器崩溃或无响应
   - 自动重连机制（最多 3 次）
   - 登录态过期检测与告警

## Impact
- Affected specs: init-project-architecture（基础架构已完成，本模块在其上构建）
- Affected code:
  - `browser/agent.py`（新建）
  - `browser/session_manager.py`（新建）
  - `browser/__init__.py`（更新导出）
  - `config/api_config.yaml`（新增配置项）
  - `requirements.txt`（确认 browser-use 版本锁定）

## ADDED Requirements

### Requirement: Browser Use Agent 初始化与生命周期管理
系统 SHALL 提供完整的 Browser Use Agent 管理能力，包括初始化、启动、运行和关闭的全生命周期控制。

#### Scenario: 成功初始化并启动 Browser Use Agent
- **WHEN** 用户点击 GUI 上的"启动"按钮
- **THEN** 系统 SHALL 自动检查 Chromium 是否已安装，未安装时提示下载
- **AND** 系统 SHALL 使用 undetectable 模式创建 Browser Use Agent 实例
- **AND** 系统 SHALL 配置豆包 LLM 作为 Agent 的智能引擎
- **AND** 系统 SHALL 启动 Chromium 并导航至 BOSS 直聘首页

#### Scenario: 正常关闭浏览器
- **WHEN** 用户点击"停止"按钮或程序退出时
- **THEN** 系统 SHALL 优雅关闭 Browser Use Agent 和浏览器实例
- **AND** 所有资源 SHALL 被正确释放（进程、内存、临时文件）

#### Scenario: Chromium 未安装时的引导
- **WHEN** 系统检测到本地未安装 Chromium 浏览器
- **THEN** 系统 SHALL 显示友好的提示信息，告知用户正在自动下载
- **AND** 系统 SHALL 调用 `playwright install chromium` 自动安装
- **AND** 安装完成后 SHALL 自动继续启动流程

### Requirement: 浏览器会话管理与登录态保持
系统 SHALL 提供浏览器会话管理能力，支持登录态持久化和多标签页操作。

#### Scenario: 保持用户登录态
- **WHEN** 用户已在 BOSS 直聘完成登录
- **THEN** 系统 SHALL 将登录 Cookie 持久化存储到本地
- **AND** 下次启动时 SHALL 自动恢复登录态，无需重复登录

#### Scenario: 登录态过期检测
- **WHEN** Browser Use 检测到页面跳转到登录页面或 Cookie 失效
- **THEN** 系统 SHALL 暂停自动化任务
- **AND** 在 GUI 上显示告警提示："登录已过期，请手动登录后继续"
- **AND** 等待用户完成登录后自动恢复任务

#### Scenario: 多标签页管理
- **WHEN** 自动化流程需要同时操作多个页面
- **THEN** 系统 SHALL 支持创建和管理多个浏览器标签页
- **AND** 提供 API 在不同标签页之间切换（搜索列表 / 岗位详情 / 聊天窗口）
- **AND** 每个 SHALL 标签页可独立执行操作（滚动、点击、输入等）

### Requirement: 反检测与风控对抗配置
系统 SHALL 配置完善的反检测机制，降低被 BOSS 直聘风控系统识别的风险。

#### Scenario: 启用反检测模式
- **WHEN** Browser Use Agent 初始化时
- **THEN** 系统 SHALL 启用 undetectable 模式（隐藏自动化特征）
- **AND** 配置随机 User-Agent 轮换
- **AND** 禁用 WebDriver 标志位检测
- **AND** 模拟真实的浏览器指纹（屏幕分辨率、时区、语言等）

#### Scenario: 操作频率控制
- **WHEN** Agent 执行自动化操作时
- **THEN** 系统 SHALL 在每次操作间插入随机延迟（3-8 秒）
- **AND** 模拟人类打字节奏（每个字符间隔 50-150ms）
- **AND** 随机化鼠标移动轨迹

### Requirement: 异常处理与自动恢复
系统 SHALL 具备健壮的异常处理能力，确保在异常情况下能安全暂停或恢复。

#### Scenario: 浏览器崩溃或无响应
- **WHEN** 检测到浏览器进程崩溃或超过 30 秒无响应
- **THEN** 系统 SHALL 记录错误日志
- **AND** 尝试自动重启浏览器（最多 3 次）
- **AND** 重启失败后在 GUI 显示错误提示

#### Scenario: 网络连接异常
- **WHEN** 页面加载超时（超过 60 秒）或网络断开
- **THEN** 系统 SHALL 暂停当前操作
- **AND** 等待网络恢复后自动重试
- **AND** 连续失败 3 次后触发告警通知用户

## MODIFIED Requirements

### Requirement: 配置文件扩展
**原有**: `config/api_config.yaml` 仅包含火山引擎 API 密钥配置
**修改为**: 新增 Browser Use 相关配置段，包括：
- `browser_use.llm_config`: LLM 配置（模型名称、API 地址、密钥引用）
- `browser_use.browser_config`: 浏览器配置（窗口大小、是否 headless、Chromium 路径）
- `browser_use.anti_detection`: 反检测选项（是否启用、延迟范围、打字速度）
- `browser_use.session_config`: 会话配置（Cookie 存储路径、是否保存会话）

### Requirement: 依赖版本确认
**原有**: `requirements.txt` 中 `browser-use` 和 `playwright` 无具体版本号
**修改为**: 锁定 `browser-use` 和 `playwright` 的兼容版本号，确保稳定性

## REMOVED Requirements
无
