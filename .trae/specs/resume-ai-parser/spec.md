# 简历AI解析 - Vision模型集成 Spec

## Why
根据PRD文档F001模块需求，系统需要支持用户上传简历文件（PDF/Word/TXT/图片），通过调用火山引擎豆包Vision多模态模型自动解析简历内容，提取关键信息生成结构化用户画像。这是整个求职自动化流程的第一步，用户画像质量直接影响后续岗位匹配和话术生成的准确性。

## What Changes
- 新增简历文件上传与格式转换模块（支持PDF/Word/TXT/图片多种格式）
- 集成火山引擎豆包Vision API进行简历内容智能解析
- 实现简历内容结构化提取（姓名、学历、工作经验、技能标签、项目经历、期望岗位等）
- 将解析结果转换为UserProfile Pydantic模型并持久化到SQLite
- 提供解析结果的人工校验与编辑能力
- 在GUI简历管理页集成上传-解析-预览完整流程

## Impact
- Affected specs: init-project-architecture（依赖其数据模型和数据库层）
- Affected code:
  - core/resume_parser.py（新建 - 核心解析模块）
  - gui/resume_page.py（修改 - 集成上传解析功能）
  - core/models.py（可能扩展 - UserProfile模型字段验证）
  - utils/db_helper.py（使用现有profiles表CRUD）

## ADDED Requirements

### Requirement: 简历文件上传
系统SHALL支持用户上传以下格式的简历文件：
- PDF格式（.pdf）
- Word文档（.docx, .doc）
- 纯文本（.txt）
- 图片格式（.png, .jpg, .jpeg）

#### Scenario: 文件上传成功
- **WHEN** 用户通过Gradio FileUploader组件选择符合格式的简历文件
- **THEN** 系统接收文件并进行格式验证，返回文件路径和基本信息

#### Scenario: 不支持的文件格式
- **WHEN** 用户上传不在支持列表中的文件类型
- **THEN** 系统提示"不支持的文件格式"错误信息，拒绝处理

### Requirement: 简历格式预处理
系统SHALL对上传的简历文件进行统一的文本提取预处理：
- PDF文件：使用PyPDF2或pdfplumber提取文本内容
- Word文件：使用python-docx提取文本内容
- TXT文件：直接读取文本内容
- 图片文件：保持原始图片数据用于Vision模型输入

#### Scenario: PDF文本提取成功
- **WHEN** 用户上传PDF格式简历
- **THEN** 系统提取PDF中的所有文本内容，保留段落结构和排版信息

### Requirement: 火山引擎Vision API集成
系统SHALL通过OpenAI兼容协议调用火山引擎豆包Vision多模态模型进行简历解析：
- 使用豆包-vision模型（支持图像+文本理解）
- 对于图片简历：直接发送图片数据给Vision模型
- 对于文本文档：将文本内容包装后发送给LLM模型（可使用豆包-pro-32k）
- 配置API端点、API Key、模型名称等参数（从api_config.yaml读取）
- 实现请求重试机制（最多3次，指数退避）
- 统一错误处理和日志记录

#### Scenario: Vision API调用成功
- **WHEN** 系统将预处理后的简历内容发送给Vision/LLM API
- **THEN** API返回结构化的JSON格式解析结果，包含简历各维度信息

#### Scenario: API调用失败
- **WHEN** Vision API返回错误或网络超时
- **THEN** 系统记录详细错误日志，重试最多3次后向用户显示友好的错误提示

### Requirement: AI简历智能解析
系统SHALL使用结构化Prompt指导AI模型从简历中提取以下信息：
- **基本信息**：姓名、性别、年龄、联系电话、电子邮箱
- **教育背景**：学历（本科/硕士/博士等）、毕业院校、专业、毕业时间
- **工作经验**：工作年限、最近N份工作经历（公司名、职位、工作时间、工作描述）
- **技能标签**：编程语言、框架、工具、软技能等（列表形式）
- **项目经历**：项目名称、项目描述、担任角色、技术栈、项目成果
- **期望岗位**：目标职位方向、期望薪资范围、期望工作地点
- **自我评价/个人优势**：核心竞争力和亮点总结

#### Scenario: 解析结果完整性
- **WHEN** AI完成简历解析
- **THEN** 返回的UserProfile对象包含所有必填字段，可选字段缺失时填充默认值或空值

### Requirement: 解析结果结构化存储
系统SHALL将AI解析结果转换为UserProfile Pydantic模型实例：
- 使用现有的core/models.py中定义的UserProfile模型
- 进行数据验证和类型转换
- 通过db_helper持久化到SQLite的profiles表
- 同时保存原始JSON到data/profiles/目录作为备份

#### Scenario: 画像持久化成功
- **WHEN** 简历解析完成且验证通过
- **THEN** UserProfile数据写入SQLite数据库，原始JSON保存到本地文件

### Requirement: 解析结果人工校验
系统SHALL提供解析结果的查看和编辑能力：
- 在Gradio界面中以JSON Editor形式展示解析结果
- 支持用户手动修改任何字段
- 保存修改后的画像数据
- 提供"重新解析"按钮允许用户重新触发AI解析

#### Scenario: 用户编辑画像
- **WHEN** 用户在JSON Editor中修改了解析结果并点击保存
- **THEN** 更新后的数据同步到SQLite数据库和本地JSON文件

### Requirement: GUI集成 - 上传解析流程
系统SHALL在gui/resume_page.py中实现完整的简历上传解析流程：
1. 用户通过FileUploader选择简历文件
2. 点击"开始解析"按钮触发解析流程
3. 显示解析进度状态（正在上传/正在解析/解析完成/解析失败）
4. 解析完成后在JSON Editor中展示UserProfile结果
5. 提供"保存画像"、"重新解析"、"清空"等操作按钮

#### Scenario: 完整上传解析流程
- **WHEN** 用户上传简历文件并点击"开始解析"
- **THEN** 界面依次显示进度状态，最终展示结构化的用户画像数据

## MODIFIED Requirements
无（新功能开发）

## REMOVED Requirements
无

## 技术约束
- Vision模型：火山引擎豆包-vision（图片简历）或 豆包-pro-32k（文本简历）
- API协议：OpenAI兼容接口（base_url从api_config.yaml读取）
- 文件大小限制：单文件不超过10MB
- 支持格式：PDF, DOCX, DOC, TXT, PNG, JPG, JPEG
- PDF解析库：PyPDF2 >= 3.0 或 pdfplumber
- Word解析库：python-docx >= 0.8.11
- 图片处理：Pillow（如需格式转换）
- 数据模型：复用现有UserProfile Pydantic模型
- 存储：SQLite profiles表 + data/profiles/ JSON备份
- 错误处理：API调用重试3次，指数退避（1s/2s/4s）
- 日志：所有关键操作记录到日志系统
- 注释语言：中文
