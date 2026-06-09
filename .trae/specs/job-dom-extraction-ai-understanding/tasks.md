# Tasks

- [ ] Task 1: 创建 JobExtractor 核心类和 DOM 提取方法
  - [ ] 1.1 创建 `browser/job_extractor.py` 文件，定义 `JobExtractor` 类
  - [ ] 1.2 实现 `extract_job_list(page, scroll_to_load=False)` 方法：从搜索列表页提取岗位卡片原始信息（CSS 选择器定位 `.job-card-box`，提取岗位名/公司/薪资/地点/经验/学历/标签）
  - [ ] 1.3 实现 `extract_job_detail(page, url=None)` 方法：从详情页提取完整纯文本（基本信息区+JD区+公司信息区+标签区），含文本清洗逻辑
  - [ ] 1.4 实现页面状态检测：加载等待、登录重定向检测、登录要求内容检测

- [ ] Task 2: 实现 AI 结构化解析能力
  - [ ] 2.1 设计并编写 `JOB_EXTRACT_PROMPT` 模板常量（角色定义 + schema + 薪资解析规则 + 少样本示例）
  - [ ] 2.2 实现 `parse_with_ai(raw_text, user_profile=None)` 方法：调用 `VolcengineLLMClient.chat_json()` 解析为 `JobInfo`
  - [ ] 2.3 实现 JSON 解析失败自动重试逻辑（更严格 Prompt 约束后重试一次）
  - [ ] 2.4 实现 `parse_with_match(raw_text, user_profile, job_criteria)` 增强方法：附加用户画像信息，返回 match_score + match_reason
  - [ ] 2.5 实现超长文本截断降级处理（优先保留 JD 核心，裁剪低优先级内容）

- [ ] Task 3: 实现端到端组合方法和批量提取
  - [ ] 3.1 实现 `extract_and_parse(job_url, browser_agent)` 组合方法：导航→检测登录→提取DOM→AI解析，含分步骤计时日志
  - [ ] 3.2 实现 `batch_extract(list_page_url, browser_agent, max_count=10)` 批量方法：列表页提取→逐个详情解析，单点故障隔离
  - [ ] 3.3 在组合方法中集成随机延迟防风控（复用 BrowserAgent 的 random_delay）

- [ ] Task 4: 扩展 JobInfo 模型
  - [ ] 4.1 在 `core/models.py` 的 `JobInfo` 模型中新增 `match_score: Optional[float]` 和 `match_reason: Optional[str]` 字段
  - [ ] 4.2 补充 `job_id` 生成策略的文档注释

- [ ] Task 5: 更新模块导出和编写单元测试
  - [ ] 5.1 更新 `browser/__init__.py` 导出 `JobExtractor` 类
  - [ ] 5.2 创建 `tests/test_job_extractor.py` 测试文件
  - [ ] 5.3 编写 DOM 提取层测试（Mock Page 对象，验证选择器逻辑和文本清洗）
  - [ ] 5.4 编写 AI 解析层测试（Mock LLM 返回，验证 JSON→JobInfo 映射、重试逻辑、降级处理）
  - [ ] 5.5 编写端到端流程测试（Mock BrowserAgent，验证完整流程编排和异常路径）
  - [ ] 5.6 编写边界场景测试（空页面、登录跳转、超大文本、畸形 JSON 等）

# Task Dependencies
- [Task 4] 无依赖，可与 [Task 1] 并行
- [Task 2] 依赖 [Task 1]（需要先有 raw_text 输入来源）
- [Task 3] 依赖 [Task 1] 和 [Task 2]（组合方法需要底层能力就绪）
- [Task 5] 依赖 [Task 1]、[Task 2]、[Task 3]、[Task 4]（测试覆盖所有实现）
