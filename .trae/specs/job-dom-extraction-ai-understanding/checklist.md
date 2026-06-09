# Checklist

## DOM 提取层
- [ ] `extract_job_list()` 能从 Mock 列表页提取岗位卡片信息，返回数量与页面一致
- [ ] `extract_job_list()` 在无结果时返回空列表并记录警告日志
- [ ] `extract_job_list()` 支持 `scroll_to_load` 参数触发滚动加载
- [ ] `extract_job_detail()` 能从 Mock 详情页提取完整的岗位纯文本（基本信息+JD+公司+标签）
- [ ] `extract_job_detail()` 对文本进行清洗（去HTML标签、去空白、实体解码）
- [ ] `extract_job_detail()` 检测到登录重定向时抛出 `LoginExpiredError`
- [ ] `extract_job_detail()` 检测到「需登录查看完整内容」时设置 `login_required` 标记

## AI 解析层
- [ ] `JOB_EXTRACT_PROMPT` 包含角色定义、schema、薪资规则、少样本示例
- [ ] `parse_with_ai()` 正常情况下返回完整 `JobInfo` 实例（所有必填字段有值）
- [ ] `parse_with_ai()` LLM 返回畸形 JSON 时自动重试一次
- [ ] `parse_with_ai()` 重试仍失败时返回 None 并记录错误日志
- [ ] `parse_with_match()` 传入 UserProfile 时返回 match_score 和 match_reason
- [ ] 超长文本自动截断降级，保留核心内容区，标记 `[内容已截断]`

## 端到端流程
- [ ] `extract_and_parse()` 完整执行 导航→检测→提取→解析 流程
- [ ] `extract_and_parse()` 各步骤耗时记录在日志中
- [ ] `batch_extract()` 串行处理多个岗位，单点失败不影响后续
- [ ] `batch_extract()` 返回列表仅包含成功解析的 JobInfo
- [ ] 组合方法中集成随机延迟防风控

## 模型扩展
- [ ] `JobInfo` 新增 `match_score` 和 `match_reason` 可选字段
- [ ] `job_id` 生成策略在代码注释中有明确说明

## 测试覆盖
- [ ] 单元测试文件存在且可运行：`tests/test_job_extractor.py`
- [ ] DOM 提取测试覆盖正常路径 + 空页面 + 登录跳转场景
- [ ] AI 解析测试覆盖正常 JSON + 畸形 JSON + 重试 + 超长文本场景
- [ ] 匹配评估测试验证 match_score 计算逻辑合理性
- [ ] 批量提取测试验证故障隔离和结果过滤
- [ ] 所有公开方法包含中文注释，符合 PEP8 规范
