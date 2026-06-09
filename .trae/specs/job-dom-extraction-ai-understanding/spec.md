# 岗位DOM提取 + AI理解 - 智能岗位识别 Spec

## Why

项目已完成基础架构（数据模型、浏览器自动化Agent、LLM客户端、GUI框架），但尚缺核心的**岗位信息提取与理解**能力。当前 `BrowserAgent` 只能控制浏览器导航和基本操作，无法从 BOSS 直聘页面中自动提取岗位详情并转化为结构化的 `JobInfo` 数据。本模块是连接「浏览器页面」与「人岗匹配」的关键桥梁，没有它整个自动求职流程无法闭环。

## What Changes

- 新增 `browser/job_extractor.py` 模块：封装 DOM 提取 + AI 理解的完整流程
  - **DOM 提取层**：通过 Playwright 选择器从 BOSS 直聘搜索列表页 / 岗位详情页提取原始 HTML/文本
  - **AI 理解层**：调用豆包 LLM 将非结构化 DOM 内容解析为结构化 `JobInfo` 对象
  - **批量提取**：支持从搜索结果列表页批量提取多个岗位摘要信息
- 新增 `browser/job_extractor.py` 中的 Prompt 模板：专门用于岗位信息提取的系统提示词
- 更新 `browser/__init__.py`：导出 `JobExtractor` 公共接口
- 新增 `tests/test_job_extractor.py`：单元测试文件

### 核心功能点

1. **岗位列表页 DOM 提取**
   - 从 BOSS 直聘搜索结果列表页提取所有岗位卡片信息（岗位名、公司、薪资、地点、标签等）
   - 使用 CSS 选择器定位关键 DOM 元素，兼容页面结构小幅变动
   - 返回原始文本列表供 AI 进一步处理

2. **岗位详情页 DOM 提取**
   - 从单个岗位详情页提取完整的 JD（职位描述）、任职要求、公司信息等
   - 处理动态加载内容（等待关键元素渲染完成）
   - 提取干净的纯文本（去除 HTML 标签、广告、无关元素）

3. **AI 结构化解析**
   - 将提取的 DOM 文本发送给豆包 LLM，使用专用 Prompt 解析为 `JobInfo` Pydantic 模型
   - 支持 JSON 模式输出，确保字段完整性
   - 内置重试机制（JSON 解析失败时自动重试一次）

4. **人岗匹配度预评估**
   - 在提取岗位信息的同时，基于用户 `UserProfile` 和 `JobCriteria` 进行初步匹配评估
   - 输出匹配分数和匹配原因说明

## Impact

- Affected specs: `browser-use-integration`（依赖 BrowserAgent 提供的 Page 对象）、`resume-ai-parser`（复用类似的 AI 解析模式）
- Affected code:
  - `browser/job_extractor.py`（新建）
  - `browser/__init__.py`（更新导出）
  - `core/models.py`（复用 JobInfo 模型，可能微调字段）
  - `tests/test_job_extractor.py`（新建）

## ADDED Requirements

### Requirement: 岗位列表页 DOM 提取
系统 SHALL 能够从 BOSS 直聘搜索结果列表页中提取所有可见岗位卡片的原始信息。

#### Scenario: 成功提取搜索列表页岗位信息
- **WHEN** 用户已打开 BOSS 直聘搜索结果页（包含多个岗位卡片）
- **AND** 调用 `JobExtractor.extract_job_list(page)` 方法
- **THEN** 系统 SHALL 使用 Playwright 选择器定位所有岗位卡片元素 `.job-card-box`
- **AND** 从每个卡片中提取以下原始文本：岗位名称、公司名称、薪资描述、地点、经验要求、学历要求、标签
- **AND** 返回 `List[Dict]` 格式的原始数据列表，每个字典包含上述字段的原始文本
- **AND** 提取数量 SHALL 与页面实际显示的岗位卡片数量一致

#### Scenario: 列表页无结果或加载中
- **WHEN** 搜索结果页尚未加载完成或无匹配结果
- **THEN** 系统 SHALL 等待最多 10 秒让页面渲染
- **AND** 若超时后仍无岗位卡片，返回空列表 `[]` 并记录警告日志

#### Scenario: 列表页需要滚动加载更多
- **WHEN** 首屏只显示了部分岗位（BOSS 直聘采用懒加载/无限滚动）
- **AND** 调用方指定了 `scroll_to_load=True` 参数
- **THEN** 系统 SHALL 模拟滚动操作直到加载指定数量的岗位或到达页面底部
- **AND** 返回所有已加载岗位的信息

### Requirement: 岗位详情页 DOM 提取
系统 SHALL 能够从单个岗位详情页中提取完整的岗位信息用于 AI 解析。

#### Scenario: 成功提取岗位详情页完整信息
- **WHEN** 浏览器已导航至某个岗位的详情页
- **AND** 调用 `JobExtractor.extract_job_detail(page, url)` 方法
- **THEN** 系统 SHALL 等待页面主要内容区域加载完成（`.job-detail` 或 `.job-banner` 元素出现）
- **AND** 提取以下区域的纯文本：
  - 岗位基本信息区：岗位名称、薪资、地点、经验要求、学历要求
  - 岗位描述区（JD）：完整的职位描述文本
  - 公司信息区：公司名称、规模、行业、融资阶段
  - 岗位标签：技能标签、福利标签等
- **AND** 对提取的文本进行清洗（去除多余空白、HTML实体解码、去广告）
- **AND** 返回拼接好的完整纯文本字符串供 AI 解析

#### Scenario: 详情页需要登录才能查看完整信息
- **WHEN** 岗位详情页检测到部分内容被遮挡（如「登录后查看全部」提示）
- **THEN** 系统 SHALL 在返回的文本中标注 `[需要登录查看完整内容]`
- **AND** 同时设置返回结果的 `login_required=True` 标记

#### Scenario: 页面跳转到登录页
- **WHEN** 访问详情页时被重定向到 BOSS 直聘登录页
- **THEN** 系统 SHALL 抛出 `LoginExpiredError` 异常
- **AND** 调用方可据此触发重新登录流程

### Requirement: AI 结构化岗位解析
系统 SHALL 能够将提取的 DOM 纯文本通过 LLM 解析为结构化的 `JobInfo` 对象。

#### Scenario: 成功解析为 JobInfo 对象
- **WHEN** 调用 `JobExtractor.parse_with_ai(raw_text, user_profile=None)` 方法
- **AND** LLM 正常返回 JSON 格式的岗位数据
- **THEN** 系统 SHALL 将 LLM 返回的 JSON 映射到 `JobInfo` Pydantic 模型
- **AND** 返回完整的 `JobInfo` 实例（包含 job_id, job_name, company_name, salary_min, salary_max, job_description 等字段）
- **AND** 所有必填字段 SHALL 有有效值（job_id 可根据 URL 或位置生成）

#### Scenario: LLM 返回的 JSON 不完整或格式错误
- **WHEN** LLM 返回的内容无法直接解析为有效的 JSON 或缺少必填字段
- **THEN** 系统 SHALL 自动重试一次（使用更严格的 Prompt 约束）
- **AND** 若仍然失败，返回 `None` 并记录错误日志（包含原始 LLM 返回内容）

#### Scenario: 带用户画像的增强解析
- **WHEN** 调用时传入了 `user_profile: UserProfile` 参数
- **THEN** 系统 SHALL 在 Prompt 中附加用户的技能、经验等背景信息
- **AND** 要求 LLM 在返回 `JobInfo` 的同时额外返回一个初步的 `match_score`（0-100 分）和 `match_reason`（匹配原因说明）
- **AND** 匹配评估 SHALL 基于岗位要求 vs 用户资质的对比（技能重叠度、经验满足度、薪资符合度等）

#### Scenario: Token 超限时的降级处理
- **WHEN** 提取的 DOM 文本超过模型的上下文长度限制
- **THEN** 系统 SHALL 自动截断文本（优先保留 JD 核心区和岗位要求区，裁剪福利标签等低优先级内容）
- **AND** 在截断处标记 `[内容已截断]`

### Requirement: 端到端提取流程（组合方法）
系统 SHALL 提供便捷的组合方法，一次性完成「打开详情页 → 提取DOM → AI解析」的全流程。

#### Scenario: 通过 URL 提取并解析单个岗位
- **WHEN** 调用 `JobExtractor.extract_and_parse(job_url, browser_agent)` 方法
- **THEN** 系统 SHALL 自动执行以下步骤：
  1. 导航浏览器至目标 URL（含随机延迟防风控）
  2. 等待页面加载完成
  3. 检测是否被重定向到登录页
  4. 提取 DOM 纯文本
  5. 调用 AI 解析为 `JobInfo` 对象
- **AND** 返回 `JobInfo` 对象或 None（失败时）
- **AND** 整个过程耗时 SHALL 在日志中记录（分步骤计时）

#### Scenario: 批量提取搜索结果中的前 N 个岗位
- **WHEN** 调用 `JobExtractor.batch_extract(list_page_url, browser_agent, max_count=10)` 方法
- **THEN** 系统 SHALL 先提取列表页的所有岗位卡片
- **AND** 依次对每个岗位执行「打开详情 → 提取 → AI解析」（串行，每次间隔随机延迟）
- **AND** 返回 `List[JobInfo]`（仅包含成功解析的岗位）
- **AND** 单个岗位解析失败不影响其他岗位的处理（记录失败日志后继续下一个）

### Requirement: 岗位提取 Prompt 模板
系统 SHALL 提供专用的 Prompt 模板用于岗位信息提取，确保 LLM 输出的稳定性和一致性。

#### Scenario: Prompt 包含完整的字段定义和示例
- **WHEN** 构建 AI 解析请求时
- **THEN** 系统 Prompt SHALL 包含：
  - 角色定义：「你是一个专业的招聘信息解析助手」
  - 输入格式说明：告知模型输入的是 BOSS 直聘岗位页面的 DOM 文本
  - 输出 schema 定义：明确列出 `JobInfo` 的每个字段及其含义
  - 薪资解析规则：说明如何将「15-25K·14薪」解析为 salary_min/salary_max
  - 输出约束：严格 JSON 格式，不包含 markdown 代码块标记
  - 少样本示例（1-2 个）：展示输入→期望输出的对应关系

## MODIFIED Requirements

### Requirement: JobInfo 模型扩展
**原有**: `core/models.py` 中 `JobInfo` 模型的 `job_id` 为字符串类型但未明确生成规则
**修改为**: 明确 `job_id` 的生成策略——可从 URL 路径提取或使用 `job_{timestamp}_{hash}` 格式；新增可选字段 `match_score: Optional[float]` 和 `match_reason: Optional[str]` 用于存储 AI 预评估结果

### Requirement: BrowserAgent 能力扩展
**原有**: `BrowserAgent` 提供 `get_page()` 返回当前活跃 Page 对象
**修改为**: 无需修改 `BrowserAgent` 本身，`JobExtractor` 通过接收 `BrowserAgent` 实例或直接接收 `Page` 对象两种方式工作，保持松耦合设计

## REMOVED Requirements
无
