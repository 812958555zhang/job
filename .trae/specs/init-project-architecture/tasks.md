# Tasks - 项目架构初始化

## 任务列表

- [x] Task 1: 项目初始化与目录结构搭建
  - [ ] 创建Python虚拟环境（venv）
  - [ ] 编写requirements.txt（包含所有依赖及版本号）
  - [ ] 创建标准目录结构（core/browser/gui/utils/config/data）
  - [ ] 创建各目录下的__init__.py文件
  - [ ] 添加.gitignore文件（排除虚拟环境、__pycache__、data/等）

- [ ] Task 2: Pydantic核心数据模型定义
  - [ ] 在core/models.py中定义JobInfo模型（岗位名称、公司名、薪资范围、岗位要求JD、工作经验要求、学历要求等字段）
  - [ ] 在core/models.py中定义UserProfile模型（姓名、学历、工作经验、技能标签、项目经历、期望岗位等字段）
  - [ ] 在core/models.py中定义ChatMessage模型（发送者角色、消息内容、时间戳、消息类型等字段）
  - [ ] 在core/models.py中定义JobCriteria模型（岗位关键词列表、薪资范围、工作地点、工作年限、学历要求等字段）
  - [ ] 在core/models.py中定义ApplicationRecord模型（岗位ID引用、匹配度分数、发送话术、操作时间、状态等字段）
  - [ ] 为所有模型添加中文注释说明字段含义
  - [ ] 编写简单的模型实例化测试代码验证

- [ ] Task 3: 配置管理模块实现
  - [ ] 在utils/config_loader.py实现YAML配置加载器类（支持读取config/settings.yaml和config/api_config.yaml）
  - [ ] 实现配置项校验逻辑（必填项检查、类型校验、默认值填充）
  - [ ] 实现配置保存方法（修改后的配置写回YAML文件）
  - [ ] 创建默认配置文件模板config/settings.yaml（包含求职标准的所有配置项及示例值）
  - [ ] 创建默认配置文件模板config/api_config.yaml（包含API密钥占位符）
  - [ ] 提供全局配置访问接口（单例模式或模块级变量）

- [ ] Task 4: SQLite数据库层实现
  - [ ] 在utils/db_helper.py实现数据库连接管理器（连接池、自动重连）
  - [ ] 定义数据库表结构SQL（用户画像表profiles、求职记录表applications、对话历史表conversations）
  - [ ] 实现数据库初始化方法（首次启动自动建表）
  - [ ] 实现profiles表的CRUD操作方法
  - [ ] 实现applications表的CRUD操作方法
  - [ ] 实现conversations表的CRUD操作方法
  - [ ] 添加异常处理和事务管理
  - [ ] 确保data/目录不存在时自动创建

- [ ] Task 5: 日志系统实现
  - [ ] 在utils/logger.py实现日志配置函数（控制台+双处理器）
  - [ ] 配置控制台输出格式化器（彩色输出、时间戳、级别、模块名）
  - [ ] 配置文件输出格式化器（按日期轮转TimedRotatingFileHandler，存储到data/logs/）
  - [ ] 支持日志级别动态调整（DEBUG/INFO/WARNING/ERROR）
  - [ ] 提供统一的get_logger(name)工厂函数供各模块调用
  - [ ] 确保logs目录自动创建

- [ ] Task 6: Gradio GUI主框架搭建
  - [ ] 创建app.py主程序入口（导入所有页面组件、组装Gradio界面）
  - [ ] 在gui/main_panel.py实现主控制面板（启动/暂停/停止按钮、状态指示器、今日统计显示）
  - [ ] 在gui/resume_page.py实现简历管理页（Gradio FileUploader + JSON编辑器组件布局）
  - [ ] 在gui/config_page.py实现配置设置页（求职标准表单、API密钥输入框、参数滑块布局）
  - [ ] 在gui/log_panel.py实现实时日志面板（Gradio Textbox滚动显示区域）
  - [ ] 在gui/reply_assistant.py实现AI回复助手面板（Gradio Chatbot组件预留布局）
  - [ ] 使用Gradio Tabs组件将所有页面整合为多Tab界面
  - [ ] 配置Gradio服务器启动参数（端口、浏览器自动打开等）

- [ ] Task 7: 集成测试与验证
  - [ ] 验证虚拟环境激活正常，所有依赖安装成功
  - [ ] 运行app.py确认GUI界面正常启动且无报错
  - [ ] 测试各Tab页面切换正常显示
  - [ ] 测试配置文件加载与保存功能
  - [ ] 测试数据库自动创建和基本CRUD操作
  - [ ] 测试日志系统正常输出到控制台和文件
  - [ ] 确认所有代码符合PEP8规范

## Task Dependencies
- [Task 2] depends on [Task 1] （需要项目结构先存在）
- [Task 3] depends on [Task 1] （需要config/目录存在）
- [Task 4] depends on [Task 1] （需要data/目录存在）
- [Task 5] depends on [Task 1] （需要data/logs/目录存在）
- [Task 6] depends on [Task 1, Task 2, Task 3, Task 4, Task 5] （GUI需要依赖所有基础模块）
- [Task 7] depends on [Task 2, Task 3, Task 4, Task 5, Task 6] （集成测试需要所有模块就绪）

## 可并行执行的任务组
**Group 1 (并行)**: Task 2, Task 3, Task 4, Task 5 （在Task 1完成后可同时进行）
**Group 2 (串行)**: Task 6 → Task 7 （GUI框架必须在最后集成测试）
