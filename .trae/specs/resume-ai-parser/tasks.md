# Tasks - 简历AI解析（Vision模型集成）

## 任务列表

- [x] Task 1: 简历文件预处理模块
  - [x] 在core/resume_parser.py创建ResumeParser类（简历解析主类）
  - [x] 实现PDF文本提取方法（使用PyPDF2/pdfplumber，支持中文内容）
  - [x] 实现Word文档文本提取方法（使用python-docx）
  - [x] 实现TXT文件读取方法（支持多种编码自动检测）
  - [x] 实现图片文件处理方法（返回图片二进制数据用于Vision API）
  - [x] 实现统一的文件格式检测和路由方法（根据扩展名选择对应处理器）
  - [x] 添加文件大小验证逻辑（限制10MB以内）
  - [x] 编写单元测试验证各格式文件的文本提取正确性

- [x] Task 2: 火山引擎Vision/LLM API集成
  - [x] 在core/resume_parser.py实现VolcengineVisionClient类（API调用封装）
  - [x] 从api_config.yaml读取API配置（endpoint、api_key、model名称）
  - [x] 实现OpenAI兼容协议的HTTP客户端（使用requests或httpx）
  - [x] 实现图片简历的Vision API调用方法（base64编码图片+Prompt）
  - [x] 实现文本文档的LLM API调用方法（文本内容+结构化Prompt）
  - [x] 设计结构化Prompt模板（指导AI提取简历各维度信息）
  - [x] 实现请求重试机制（最多3次，指数退避1s/2s/4s）
  - [x] 实现统一错误处理（网络超时、API限流、认证失败等场景）
  - [x] 添加详细的日志记录（请求参数、响应状态、耗时等）

- [x] Task 3: AI解析结果处理与存储
  - [x] 定义AI返回结果的中间数据结构（RawProfileDict）
  - [x] 实现AI响应JSON解析和数据清洗逻辑
  - [x] 将清洗后的数据映射到UserProfile Pydantic模型（复用core/models.py）
  - [x] 实现数据验证和默认值填充（必填字段缺失时提示警告）
  - [x] 通过db_helper将UserProfile持久化到SQLite profiles表
  - [x] 将原始AI返回JSON保存到data/profiles/目录作为备份（文件名含时间戳）
  - [x] 实现画像数据的更新逻辑（重新解析时覆盖旧数据）

- [x] Task 4: GUI简历管理页功能集成
  - [x] 修改gui/resume_page.py，在FileUploader组件后添加"开始解析"按钮
  - [x] 实现解析状态显示组件（Gradio Textbox或StatusIndicator）
  - [x] 集成ResumeParser类到Gradio回调函数中
  - [x] 实现异步解析流程（避免阻塞GUI界面，使用Gradio的异步事件处理）
  - [x] 解析完成后将UserProfile JSON展示在已有的JSON Editor组件中
  - [x] 实现"保存画像"按钮回调（保存编辑后的数据到数据库）
  - [x] 实现"重新解析"按钮回调（清空当前结果并重新触发解析）
  - [x] 实现错误提示展示（解析失败时在界面显示具体原因）
  - [x] 添加操作日志输出到全局日志面板

- [x] Task 5: 依赖安装与配置更新
  - [x] 安装PDF处理依赖：`pip install PyPDF2 pdfplumber`
  - [x] 安装Word处理依赖：`pip install python-docx`
  - [x] 安装图片处理依赖：`pip install Pillow`
  - [x] 更新requirements.txt添加所有新依赖及版本号
  - [x] 更新config/api_config.yaml添加Vision模型相关配置项（如需要）
  - [x] 验证所有新依赖安装无冲突

- [x] Task 6: 功能测试与验证
  - [x] 准备测试用例简历文件（PDF/Word/TXT/图片各至少1个样本）
  - [x] 测试PDF简历上传和解析完整流程
  - [x] 测试Word简历上传和解析完整流程
  - [x] 测试TXT简历上传和解析完整流程
  - [x] 测试图片简历上传和解析完整流程
  - [x] 测试不支持的文件格式的错误提示
  - [x] 测试超大文件（>10MB）的上传限制
  - [x] 测试API调用失败时的重试机制和错误提示
  - [x] 测试解析结果的人工编辑和保存功能
  - [x] 测试重新解析功能（覆盖旧数据）
  - [x] 验证SQLite数据库中的画像数据正确性
  - [x] 验证备份JSON文件的生成和内容完整性
  - [x] 确认代码符合PEP8规范且注释为中文

## Task Dependencies
- [Task 2] depends on [Task 1] （API调用需要预处理后的内容）
- [Task 3] depends on [Task 2] （结果处理需要API返回的数据）
- [Task 4] depends on [Task 1, Task 2, Task 3] （GUI集成需要完整的解析流程）
- [Task 5] depends on [] （可并行执行，但建议最先完成）
- [Task 6] depends on [Task 1, Task 2, Task 3, Task 4, Task 5] （测试需要全部功能就绪）

## 可并行执行的任务组
**Group 1 (并行)**: Task 5 （依赖安装可在开发开始前完成）
**Group 2 (串行)**: Task 1 → Task 2 → Task 3 → Task 4 → Task 6 （核心功能按顺序开发）
