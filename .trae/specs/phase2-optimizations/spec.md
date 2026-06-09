# BOSS直聘求职助手 - P2优化功能需求文档

## Overview
- **Summary**: 实现P2阶段的四个优化功能：数据统计、去重机制、AI回复助手完善、风控策略优化
- **Purpose**: 提升用户体验，增强系统稳定性和安全性
- **Target Users**: 求职者用户

## Goals
- 实现数据统计功能（今日沟通数/匹配数/回复率可视化）
- 实现去重机制（已沟通岗位记录与自动跳过）
- 完善AI回复助手（对话历史展示/一键复制/自动填充）
- 实现风控策略优化（自适应延迟、每日上限、异常模式学习）

## Non-Goals (Out of Scope)
- 不实现断点续传功能
- 不修改核心LLM客户端逻辑
- 不改变整体架构设计

## Background & Context
根据项目进度计划，P2阶段是MVP完成后的优化工作，提升系统的完整性和用户体验。

## Functional Requirements
- **FR-1**: 数据统计功能 - 实现今日统计、历史趋势、详细报表
- **FR-2**: 去重机制 - 在JobScreener中集成已投递岗位检测
- **FR-3**: AI回复助手完善 - 实现消息发送、AI生成、一键复制功能
- **FR-4**: 风控策略优化 - 实现自适应延迟调整、每日上限控制

## Non-Functional Requirements
- **NFR-1**: 统计数据实时更新（每2秒刷新）
- **NFR-2**: 去重检测高效（O(1)查询）
- **NFR-3**: 风控策略可配置

## Constraints
- **Technical**: Python 3.11+, Gradio 5.x, SQLite

## Acceptance Criteria

### AC-1: 数据统计功能
- **Given**: 用户打开主控制面板
- **When**: 查看统计面板
- **Then**: 显示今日沟通数、匹配数、跳过数、回复率
- **Verification**: `programmatic`

### AC-2: 去重机制
- **Given**: 岗位已被申请过
- **When**: 再次扫描到该岗位
- **Then**: 自动跳过并记录跳过原因
- **Verification**: `programmatic`

### AC-3: AI回复助手完善
- **Given**: 进入AI回复助手页面
- **When**: 点击AI生成按钮
- **Then**: 生成回复建议并支持一键复制
- **Verification**: `human-judgment`

### AC-4: 风控策略优化
- **Given**: 配置了每日上限
- **When**: 达到每日上限
- **Then**: 自动暂停任务并提示用户
- **Verification**: `programmatic`

## Implementation Details

### 1. 数据统计功能
- 在 `gui/main_panel.py` 中实现统计面板
- 使用 `utils/db_helper.py` 的 `get_today_stats()` 方法
- 实现每日报表展示

### 2. 去重机制
- 在 `core/job_screener.py` 中集成 `check_job_applied()` 检查
- 在扫描流程中自动跳过已申请岗位

### 3. AI回复助手完善
- 在 `gui/reply_assistant.py` 中实现消息发送、AI生成、复制功能
- 连接 `core/chat_generator.py` 的 `generate_reply()` 方法

### 4. 风控策略优化
- 在 `utils/delay_simulator.py` 中实现自适应延迟
- 在 `gui/main_panel.py` 中实现每日上限控制