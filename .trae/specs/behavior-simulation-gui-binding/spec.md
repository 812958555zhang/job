# BOSS直聘求职助手 - 行为模拟与GUI绑定功能需求文档

## Overview
- **Summary**: 完成三个核心任务：创建人类行为模拟器模块、完善GUI事件绑定、创建API配置文件模板
- **Purpose**: 为自动化流程提供反检测能力，建立GUI与后端的交互桥梁，配置API密钥管理
- **Target Users**: 求职者用户使用自动化求职功能

## Goals
- 实现人类行为模拟（随机延迟、打字节奏、鼠标轨迹）
- 完善主控制面板的按钮事件绑定（启动/暂停/停止）
- 创建API配置文件模板（火山引擎、Browser Use）

## Non-Goals (Out of Scope)
- 不实现完整的自动化流程编排
- 不涉及浏览器操作执行器的实现
- 不修改核心LLM客户端逻辑

## Background & Context
根据项目进度计划，当前需要完成P1优先级任务，为后续自动化执行引擎提供基础设施支持。

## Functional Requirements
- **FR-1**: 创建 `utils/delay_simulator.py` 模块，提供随机延迟、打字节奏模拟功能
- **FR-2**: 完善 `gui/main_panel.py`，实现启动/暂停/停止按钮的事件回调绑定
- **FR-3**: 创建 `config/api_config.yaml` 配置文件模板，包含火山引擎API和Browser Use配置

## Non-Functional Requirements
- **NFR-1**: 延迟模拟需符合反检测要求（3-8秒随机范围）
- **NFR-2**: GUI事件绑定需支持异步操作和状态同步
- **NFR-3**: API配置需支持加密存储和安全访问

## Constraints
- **Technical**: 基于Python 3.11+，使用Gradio 5.x，遵循PEP8规范
- **Dependencies**: 依赖browser-use、gradio、pyyaml等已配置的包

## Assumptions
- 项目已初始化，基础框架已搭建完成
- 配置加载器 `utils/config_loader.py` 已实现
- 日志系统 `utils/logger.py` 已实现

## Acceptance Criteria

### AC-1: 人类行为模拟器创建完成
- **Given**: 项目结构完整，utils目录已存在
- **When**: 创建 `utils/delay_simulator.py` 文件
- **Then**: 文件包含随机延迟、打字节奏模拟函数，符合项目代码风格
- **Verification**: `programmatic`

### AC-2: GUI事件绑定完善
- **Given**: `gui/main_panel.py` 已存在基本框架
- **When**: 实现启动/暂停/停止按钮的事件回调
- **Then**: 按钮点击能正确触发状态变更和后台任务控制
- **Verification**: `programmatic`

### AC-3: API配置文件模板创建
- **Given**: config目录已存在，`settings.yaml` 已创建
- **When**: 创建 `api_config.yaml` 文件
- **Then**: 文件包含完整的API密钥配置结构和注释说明
- **Verification**: `human-judgment`

## Open Questions
- [ ] 暂无

## Implementation Details

### 1. utils/delay_simulator.py
- 实现 `random_delay()` - 3-8秒随机延迟
- 实现 `simulate_typing()` - 模拟人类打字节奏
- 实现 `human_like_delay()` - 综合行为延迟

### 2. gui/main_panel.py 事件绑定
- 启动按钮：初始化浏览器Agent，开始岗位扫描流程
- 暂停按钮：暂停当前自动化任务，保持浏览器状态
- 停止按钮：停止自动化任务，释放浏览器资源

### 3. config/api_config.yaml
- 火山引擎API配置（api_key, base_url, models）
- Browser Use配置（浏览器设置、反检测设置）