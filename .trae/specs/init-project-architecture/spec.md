# BOSS直聘求职助手 - 项目架构初始化 Spec

## Why
根据PRD文档需求，需要搭建完整的项目基础架构，为后续AI核心能力、自动化执行引擎等模块开发奠定基础。当前项目仅有PRD文档，需要从零开始构建可运行的代码骨架。

## What Changes
- 初始化Python项目结构（虚拟环境、依赖管理、目录组织）
- 定义Pydantic数据模型（岗位信息、用户画像、聊天消息等核心实体）
- 实现配置管理模块（YAML配置文件的加载、保存、校验）
- 搭建SQLite数据库层（表结构定义、CRUD操作封装）
- 建立日志系统（控制台+文件双输出、按日期轮转）
- 构建Gradio GUI主框架（多页面Tab布局、基础组件）

## Impact
- Affected specs: 无（首次初始化）
- Affected code: 全部项目代码（新建）

## ADDED Requirements

### Requirement: 项目基础架构
系统SHALL提供完整的Python项目基础设施，包括：
- Python 3.11+ 虚拟环境配置
- 标准化的项目目录结构
- 第三方依赖管理（requirements.txt）
- 代码规范配置（PEP8）

#### Scenario: 项目初始化完成
- **WHEN** 开发者克隆项目并运行初始化脚本
- **THEN** 自动创建虚拟环境、安装依赖、生成标准目录结构

### Requirement: Pydantic数据模型
系统SHALL使用Pydantic定义以下核心数据模型：
- `JobInfo`: 岗位信息（名称、公司、薪资、JD、要求等）
- `UserProfile`: 用户画像（基本信息、技能、经历、期望等）
- `ChatMessage`: 聊天消息（发送者、内容、时间戳、类型）
- `JobCriteria`: 求职筛选标准（关键词、薪资范围、地点等）
- `ApplicationRecord`: 求职记录（岗位ID、匹配度、话术、时间等）

#### Scenario: 数据模型验证
- **WHEN** 使用非法数据实例化模型
- **THEN** Pydantic自动进行类型校验并抛出ValidationError

### Requirement: 配置管理系统
系统SHALL提供YAML配置文件的管理能力：
- 加载settings.yaml（求职标准配置）
- 加载api_config.yaml（API密钥配置）
- 配置项校验与默认值处理
- 配置修改后的持久化保存

#### Scenario: 配置加载
- **WHEN** 程序启动时
- **THEN** 自动读取config/目录下的YAML配置文件并提供全局访问接口

### Requirement: SQLite数据库层
系统SHALL提供本地SQLite数据库的完整操作能力：
- 自动创建数据库文件和表结构
- 用户画像表的CRUD操作
- 求职记录表的CRUD操作
- 对话历史表的CRUD操作
- 数据库连接管理与异常处理

#### Scenario: 数据库初始化
- **WHEN** 首次启动程序且数据库不存在
- **THEN** 自动创建job_assistant.db及所有必要的表结构

### Requirement: 日志系统
系统SHALL提供完善的日志记录功能：
- 控制台输出（彩色格式化）
- 文件输出（按日期轮转，存储在data/logs/目录）
- 多级别日志支持（DEBUG/INFO/WARNING/ERROR）
- 统一的日志调用接口

#### Scenario: 日志记录
- **WHEN** 系统运行过程中产生各类事件
- **THEN** 日志同时输出到控制台和当日日志文件

### Requirement: Gradio GUI主框架
系统SHALL提供基于Gradio的Web界面基础框架：
- 主控制面板（状态显示、操作按钮）
- 简历管理页（文件上传、画像编辑）
- 配置设置页（表单输入、参数调整）
- 实时日志面板（滚动文本显示）
- AI回复助手面板（聊天界面预留）

#### Scenario: GUI启动
- **WHEN** 运行主程序app.py
- **THEN** 启动Gradio Web服务器并在浏览器中打开界面

## MODIFIED Requirements
无（新项目首次初始化）

## REMOVED Requirements
无

## 技术约束
- Python版本：3.11+
- GUI框架：Gradio >= 5.0
- 数据验证：Pydantic v2
- 数据库：SQLite3（Python内置）
- 配置格式：YAML（PyYAML >= 6.0）
- 代码规范：PEP8
- 注释语言：中文
