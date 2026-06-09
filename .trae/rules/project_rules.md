# BOSS直聘助手 - 项目开发规则

> 本文件定义项目开发的统一规范，所有成员必须遵守。

---

## 一、虚拟环境与启动

1. **虚拟环境路径**：项目使用 `venv/` 作为虚拟环境目录（Python 3.11+）
2. **启动前检查**：每次启动项目前，必须确认 `venv` 已激活（终端提示符显示 `(TraeAI-3)`）
3. **Python 解释器**：统一使用 `venv\Scripts\python.exe`，禁止直接调用系统 Python
4. **IDE 配置**：确保 IDE（Trae/VSCode）已选中 venv 解释器

---

## 二、代码规范

5. **语言要求**：所有代码注释必须使用**中文**，清晰说明函数功能、参数和返回值
6. **PEP8 规范**：所有 Python 代码遵循 PEP8 代码规范
7. **注释风格**：业务代码需写言简意赅的中文注释
8. **前端优先原则**：后端接口设计尽量减少前端参数传递数量，根据需求只暴露必须参数给前端，可后端生成或查询获取的参数尽量后端处理
9. **引导式提问**：遇到不确定的内容或方案，必须使用引导式提问询问用户确认后再实施

---

## 三、依赖管理

10. **安装方式**：新增依赖时使用当前终端的 pip 命令安装（确保 `.venv` 已激活）
11. **同步 requirements.txt**：每次引入新的 Python 依赖包后，必须同步更新 [requirements.txt](requirements.txt)，保持依赖声明与实际安装一致
12. **同步核心依赖清单**：关键依赖变更需同步更新 project_memory.md 中的核心依赖清单
13. **导出命令**：`pip freeze > requirements.txt`

---

## 四、接口测试规范

14. **测试覆盖范围**：接口测试需覆盖以下场景：
    - 正常入参测试
    - 必填字段缺失测试
    - 边界极值测试
    - 非法参数测试
    - 权限越权测试

---

## 五、统一 API 响应格式规范

15. **统一 JSON 格式**：所有接口必须返回统一 JSON 格式：
    ```json
    {"code": 200, "data": ..., "msg": "成功！"}
    ```
    禁止返回裸数据或 HTML

16. **ApiResponse 工具类**：视图层所有响应通过 `twin_management.utils.ApiResponse` 构建：
    - **禁止从 `user.utils` 导入**（已迁移至公共包）
    - **禁止直接使用 DRF 原生 `Response()`**
    - **禁止手动拼装字典**

17. **ApiResponse 三方法**：
    | 方法 | 用途 |
    |------|------|
    `ApiResponse.success(data, msg)` | 成功响应 |
    `ApiResponse.error(msg, code, http_status)` | 错误响应 |
    `ApiResponse.paginated(data, page, limit, total, msg)` | 分页列表响应 |

18. **业务码语义化**：
    | code | 含义 |
    |------|------|
    200 | 成功 |
    400 | 参数错误 |
    401 | 未认证 |
    403 | 权限不足 |
    404 | 资源不存在 |
    500 | 服务异常 |

    HTTP 状态码通过 `http_status` 参数单独控制

19. **禁止本地重复定义响应类**：所有视图文件统一从 `twin_management.utils` 导入 `ApiResponse`
    - **禁止从 `user.utils` 导入**（`user/utils.py` 已退化为兼容重导出 shim）
    - **禁止在视图文件中自定义 SuccessResponse/DetailResponse/ErrorResponse 等响应类**

20. **全局异常三层防护**：

    ```
    第一层：DRF EXCEPTION_HANDLER → user.exceptions.custom_exception_handler
           （精确映射 DRF 内置异常 + 业务异常 + 未注册异常兜底）

    第二层：Django Middleware → twin_management.middleware.exception_middleware.ExceptionMiddleware
           （兜底捕获所有漏网异常，确保返回 JSON）

    第三层：urls.py → handler404 / handler500
           （Django 级别错误页面 JSON 化）
    ```

21. **异常处理器兜底规则**：`custom_exception_handler` 必须对所有未注册异常返回：
    ```json
    {"code": 500, "data": null, "msg": "接口异常！"}
    ```
    同时记录完整堆栈到 error.log，**禁止返回 None 透传给 Django 默认处理**

22. **中间件配置顺序**：`ExceptionMiddleware` 必须放在 MIDDLEWARE 列表第一行（SecurityMiddleware 之前），确保作为最外层兜底

23. **异常注册机制**：新增异常类时注册到 `_EXCEPTION_REGISTRY`：
    - 在 `user/exceptions.py` 的 `_EXCEPTION_REGISTRY` 字典中添加 `{类名: (HTTP状态码, 默认消息)}` 条目
    - 无需修改分发逻辑

---

## 六、单元测试规范

24. **测试先行原则**：每个需求/功能开发完成后，必须编写对应的单元测试，确保代码质量
25. **测试覆盖要求**：
    - 核心业务逻辑覆盖率 **≥ 80%**
    - 工具函数、数据处理类必须 100% 覆盖
    - 每个公开方法至少包含：正常路径 + 异常路径测试用例
26. **测试文件组织**：测试文件统一放在 `tests/` 目录下，命名规则为 `test_{模块名}.py`
27. **测试框架**：使用 `pytest` 作为测试框架，配合 `pytest-cov` 统计覆盖率
28. **运行命令**：`pytest tests/ -v --cov=src --cov-report=term-missing`
29. **Mock 外部依赖**：涉及网络请求（LLM调用）、数据库IO、浏览器操作的测试必须使用 mock，禁止真实调用外部服务

---

## 七、Skill 使用规范

30. **优先使用已安装 Skill**：执行任务前要充分合理运用已安装 skill
31. **Skill 安装目录**：`C:\Users\81295\.trae-cn\skills`

---

## 八、项目技术栈参考

| 类别 | 技术选型 |
|------|----------|
| GUI 框架 | Gradio 5.x |
| AI Agent | PydanticAI |
| LLM 提供商 | 火山引擎豆包 |
| 浏览器自动化 | Browser Use + Playwright + Chromium |
| 数据存储 | SQLite |
| 配置管理 | YAML |
| 打包工具 | PyInstaller |
| Python 版本 | 3.11+ |
