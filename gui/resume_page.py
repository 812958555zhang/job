"""
简历管理模块 - 提供完整的简历上传、AI解析、结果展示和保存功能

包含：文件上传器、解析控制面板、状态监控、JSON编辑器、数据持久化
集成ResumeParsingPipeline实现一键式简历智能解析流程
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import gradio as gr

# 导入核心解析模块
from core.resume_parser import ResumeParsingPipeline
from core.models import UserProfile
from pydantic import ValidationError


# ==================== 全局状态管理 ====================

# 创建全局Pipeline实例（避免重复初始化）
_pipeline_instance: Optional[ResumeParsingPipeline] = None


def get_pipeline() -> ResumeParsingPipeline:
    """
    获取或创建全局Pipeline实例

    使用单例模式确保整个应用共享同一个解析器实例，
    避免重复初始化API客户端和日志系统。

    Returns:
        ResumeParsingPipeline: 全局唯一的解析流程实例
    """
    global _pipeline_instance
    if _pipeline_instance is None:
        _pipeline_instance = ResumeParsingPipeline()
    return _pipeline_instance


# ==================== 初始值常量 ====================

# 空JSON模板（用于初始化编辑器）
EMPTY_JSON_TEMPLATE = "{\n  \n}"


def _is_empty_json_content(json_content) -> bool:
    """判断 JSON 编辑器内容是否为空或未填写有效数据"""
    if json_content is None:
        return True
    if isinstance(json_content, dict):
        return len(json_content) == 0
    text = str(json_content).strip()
    if not text:
        return True
    if text == EMPTY_JSON_TEMPLATE.strip():
        return True
    if text in ("{}", "{\n}", "{\n\n}"):
        return True
    return False


def _json_content_to_str(json_content) -> str:
    """将 Gradio Code 组件的值统一转为 JSON 字符串"""
    if json_content is None:
        return ""
    if isinstance(json_content, dict):
        return json.dumps(json_content, ensure_ascii=False, indent=2)
    return str(json_content)

# 默认用户画像模板
DEFAULT_PROFILE_TEMPLATE = {
    "name": "",
    "education": "",
    "total_experience_years": 0,
    "skills": [],
    "expected_positions": [],
    "expected_locations": []
}

# 初始状态文本
INITIAL_STATUS = "● 就绪"
INITIAL_STATS = "⏱️ 耗时: -- | 📄 大小: -- | 🔤 Token: --"


# ==================== 核心回调函数 ====================

def on_parse_click(
    file_path: Optional[str],
    progress: gr.Progress = gr.Progress()
) -> Tuple[str, str, str]:
    """
    点击"开始解析"按钮的回调函数

    执行完整的简历AI解析流程：文件预处理 → API调用 → 结果处理 → 展示数据

    Args:
        file_path: FileUploader组件返回的文件路径（未选择时为None）
        progress: Gradio进度条组件（自动注入）

    Returns:
        tuple: (状态文本, 统计信息文本, JSON内容)
              - status_text: 解析状态描述
              - stats_text: 包含耗时、文件大小、Token用量的统计信息
              - json_content: 解析结果的JSON字符串（用于填充编辑器）
    """
    # ========== 步骤1：验证输入 ==========
    if file_path is None or not os.path.exists(file_path):
        error_msg = "❌ 请先选择要解析的简历文件"
        return error_msg, INITIAL_STATS, EMPTY_JSON_TEMPLATE

    # 获取文件信息
    filename = Path(file_path).name
    file_size = os.path.getsize(file_path)
    file_size_display = f"{file_size / 1024:.1f}KB" if file_size < 1024 * 1024 else f"{file_size / 1024 / 1024:.2f}MB"

    try:
        # 更新初始状态
        yield f"🔄 正在解析: {filename}", INITIAL_STATS, EMPTY_JSON_TEMPLATE

        # ========== 步骤2：获取Pipeline并执行解析 ==========
        progress(0.1, desc="正在初始化解析器...")
        pipeline = get_pipeline()

        progress(0.3, desc=f"正在读取文件: {filename}")
        start_time = time.time()

        # 执行完整解析流程（包含文件预处理+AI分析+数据处理）
        progress(0.5, desc="正在调用AI分析...")
        result = pipeline.parse_resume(file_path)

        # 计算实际耗时
        elapsed_time = time.time() - start_time

        # ========== 步骤3：处理解析结果 ==========
        progress(0.8, desc="正在处理结果...")

        if not result.get('success'):
            # 解析失败，返回错误信息
            error_msg = result.get('error', '未知错误')
            error_status = f"❌ 解析失败: {error_msg}"
            stats_text = f"⏱️ 耗时: {elapsed_time:.1f}秒 | 📄 大小: {file_size_display} | ❌ 失败"
            yield error_status, stats_text, EMPTY_JSON_TEMPLATE
            return

        # ========== 步骤4：成功处理 ==========
        progress(1.0, desc="✅ 解析完成！")

        # 提取用户画像数据
        user_profile = result.get('user_profile')
        stats_info = result.get('stats', {})

        if user_profile is None:
            # 有原始响应但无法转换为模型
            warning_status = "⚠️ 解析完成但数据格式异常"
            raw_response = result.get('raw_response', {})
            json_content = json.dumps(raw_response, ensure_ascii=False, indent=2)
            success_status = warning_status
        else:
            # 成功获取结构化数据
            success_status = f"✅ 解析完成！姓名: {user_profile.name}（已自动写入数据库，可编辑后点保存）"
            profile_dict = user_profile.model_dump()
            profile_dict.pop('created_at', None)
            profile_dict.pop('updated_at', None)
            profile_dict.pop('resume_file_path', None)
            json_content = json.dumps(profile_dict, ensure_ascii=False, indent=2)

        # 构建统计信息
        tokens_used = stats_info.get('api_tokens_used', 0)
        parse_time = stats_info.get('parse_time', elapsed_time)
        stats_text = (
            f"⏱️ 耗时: {parse_time:.1f}秒 | "
            f"📄 大小: {file_size_display} | "
            f"🔤 Token: {tokens_used}"
        )

        yield success_status, stats_text, json_content

    except Exception as e:
        # 兜底异常捕获
        error_status = f"💥 异常: {str(e)}"
        yield error_status, INITIAL_STATS, EMPTY_JSON_TEMPLATE


def on_save_click(json_content: str, file_path: Optional[str]) -> str:
    """
    点击"保存画像"按钮的回调函数

    将JSON编辑器中的内容保存到数据库和本地备份文件，
    支持用户手动编辑后的数据保存。若编辑器为空，会尝试使用最近一次解析结果。
    """
    json_text = _json_content_to_str(json_content)

    # 编辑器为空时，尝试从 Pipeline 缓存读取最近一次解析结果
    if _is_empty_json_content(json_text):
        pipeline = get_pipeline()
        cached_json = pipeline.get_profile_as_json()
        if cached_json:
            json_text = cached_json
        else:
            return "❌ 请先点击「开始解析」完成简历解析，或在下方 JSON 编辑器中填写有效数据"

    try:
        data = json.loads(json_text)
    except json.JSONDecodeError as e:
        return f"❌ JSON格式错误: {str(e)}（请检查括号、引号是否匹配）"

    if not isinstance(data, dict):
        return "❌ 画像数据必须是 JSON 对象格式"

    # ========== 步骤3：验证必填字段 ==========
    required_fields = ['name', 'education', 'total_experience_years']
    missing_fields = [field for field in required_fields if field not in data or not data[field]]
    if missing_fields:
        return f"❌ 缺少必填字段: {', '.join(missing_fields)}"

    # ========== 步骤4：创建UserProfile模型进行验证 ==========
    try:
        # 补充可选字段的默认值
        profile_data = {
            'name': data.get('name', ''),
            'education': data.get('education', '未知'),
            'total_experience_years': float(data.get('total_experience_years', 0)),
            'phone': data.get('phone'),
            'email': data.get('email'),
            'major': data.get('major'),
            'school': data.get('school'),
            'current_position': data.get('current_position'),
            'current_company': data.get('current_company'),
            'skills': data.get('skills', []),
            'core_competencies': data.get('core_competencies', []),
            'projects': data.get('projects', []),
            'expected_positions': data.get('expected_positions', []),
            'expected_salary_min': data.get('expected_salary_min'),
            'expected_salary_max': data.get('expected_salary_max'),
            'expected_locations': data.get('expected_locations', []),
            'resume_file_path': file_path,
        }

        # 通过Pydantic验证创建模型实例
        user_profile = UserProfile(**profile_data)

    except ValidationError as e:
        # 收集所有验证错误生成友好提示
        errors = e.errors()
        error_details = []
        for err in errors[:3]:  # 只显示前3个错误避免过长
            field = '.'.join(str(loc) for loc in err['loc'])
            msg = err['msg']
            error_details.append(f"{field}: {msg}")

        error_msg = "❌ 数据验证失败:\n" + "\n".join(error_details)
        return error_msg

    except Exception as e:
        return f"❌ 模型创建失败: {str(e)}"

    # ========== 步骤5：保存到数据库 ==========
    try:
        pipeline = get_pipeline()
        db_success = pipeline._save_to_database(user_profile)

        if not db_success:
            return "⚠️ 数据库保存失败（请查看日志了解详情）"

    except Exception as e:
        return f"❌ 数据库写入错误: {str(e)}"

    # ========== 步骤6：保存JSON备份文件 ==========
    try:
        backup_path = pipeline._save_json_backup(data, user_profile.model_dump(mode='json'))
        if backup_path:
            backup_filename = Path(backup_path).name
    except Exception:
        backup_filename = "无"
        pass  # 备份失败不影响主流程

    # ========== 步骤7：返回成功消息 ==========
    success_msg = (
        f"✅ 保存成功！\n"
        f"   👤 姓名: {user_profile.name}\n"
        f"   🎓 学历: {user_profile.education}\n"
        f"   💾 备份文件: {backup_filename}"
    )
    return success_msg


def on_reparse_click(
    file_path: Optional[str],
    progress: gr.Progress = gr.Progress()
) -> Tuple[str, str, str]:
    """
    点击"重新解析"按钮的回调函数

    清除当前缓存结果后重新执行完整的解析流程，
    用于重新分析同一文件或更换文件后重新解析。

    Args:
        file_path: 当前选择的文件路径
        progress: Gradio进度条组件

    Returns:
        tuple: 与on_parse_click相同的格式
    """
    # 验证文件是否存在
    if file_path is None or not os.path.exists(file_path):
        return "❌ 请先选择要解析的简历文件", INITIAL_STATS, EMPTY_JSON_TEMPLATE

    try:
        # 清除旧的解析结果缓存
        pipeline = get_pipeline()
        pipeline.clear_results()

        # 显示清除状态
        yield "🔄 已清除旧结果，正在重新解析...", INITIAL_STATS, EMPTY_JSON_TEMPLATE

        # 调用标准解析流程（复用on_parse_click的逻辑）
        result = on_parse_click(file_path, progress)

        # 如果是生成器则迭代获取最终结果
        if isinstance(result, type((x for x in []))):
            final_result = None
            for r in result:
                final_result = r
            return final_result
        else:
            return result

    except Exception as e:
        return f"❌ 重新解析失败: {str(e)}", INITIAL_STATS, EMPTY_JSON_TEMPLATE


def on_clear_click() -> Tuple[str, str, str, Optional[str]]:
    """
    点击"清空"按钮的回调函数

    重置所有UI组件到初始状态：
    - 清除状态栏消息
    - 清除统计信息
    - 清空JSON编辑器内容
    - 清除文件选择器的选中文件

    Returns:
        tuple: (状态文本, 统计文本, JSON内容, 文件路径)
              文件路径设为None以清空FileUploader
    """
    # 清除全局Pipeline的缓存
    try:
        pipeline = get_pipeline()
        pipeline.clear_results()
    except Exception:
        pass  # 清除失败不影响UI重置

    # 返回所有组件的初始值
    return INITIAL_STATUS, INITIAL_STATS, EMPTY_JSON_TEMPLATE, None


# ==================== 页面构建函数 ====================

def create_resume_page():
    """
    创建简历管理页面的完整界面

    构建包含以下功能的GUI：
    1. 文件上传区域（支持PDF/Word/TXT/图片格式）
    2. 操作按钮组（开始解析/重新解析/保存/清空）
    3. 实时状态监控面板
    4. JSON编辑器（展示和编辑解析结果）
    5. 字段说明参考表

    界面布局采用上下分区设计：
    - 上半部分：文件上传 + 控制按钮 + 状态显示
    - 下半部分：JSON编辑器 + 辅助说明
    """

    # ========== 页面标题 ==========
    gr.Markdown("### 📄 简历管理")

    # ========== 区域1：文件上传与控制面板 ==========
    with gr.Row():
        with gr.Column(scale=1):
            # 文件上传组件
            file_input = gr.File(
                label="📁 选择简历文件",
                file_types=[".pdf", ".docx", ".doc", ".txt", ".png", ".jpg", ".jpeg"],
                type="filepath",  # 返回文件路径而非文件对象
                interactive=True
            )

            # 操作按钮组（水平排列）
            with gr.Row():
                btn_parse = gr.Button(
                    "🚀 开始解析",
                    variant="primary",
                    size="sm"
                )
                btn_reparse = gr.Button(
                    "🔄 重新解析",
                    size="sm"
                )

            with gr.Row():
                btn_save = gr.Button(
                    "💾 保存画像",
                    variant="secondary",
                    size="sm"
                )
                btn_clear = gr.Button(
                    "🗑️ 清空",
                    size="sm"
                )

        with gr.Column(scale=2):
            # 解析状态显示区域
            status_display = gr.Textbox(
                label="📊 解析状态",
                value=INITIAL_STATUS,
                interactive=False,
                lines=2
            )

            # 统计信息显示区域
            stats_display = gr.Textbox(
                label="📈 统计信息",
                value=INITIAL_STATS,
                interactive=False,
                lines=1
            )

    # ========== 区域2：JSON编辑器（用户画像预览与编辑） ==========
    gr.Markdown("#### 👤 用户画像数据（可编辑）")

    json_editor = gr.Code(
        label="用户画像JSON编辑器",
        language="json",
        value=EMPTY_JSON_TEMPLATE,
        interactive=True,
        lines=20
    )

    # ========== 区域3：字段说明参考表 ==========
    with gr.Accordion("📋 字段说明（点击展开）", open=False):
        gr.Dataframe(
            headers=["字段名", "类型", "必填", "说明"],
            value=[
                ["name", "string", "✅ 是", "求职者姓名"],
                ["education", "string", "✅ 是", "最高学历（本科/硕士等）"],
                ["total_experience_years", "float", "✅ 是", "工作年限（如5.5表示5年半）"],
                ["phone", "string", "否", "联系电话"],
                ["email", "string", "否", "电子邮箱"],
                ["major", "string", "否", "专业名称"],
                ["school", "string", "否", "毕业院校"],
                ["current_position", "string", "否", "当前职位"],
                ["current_company", "string", "否", "当前公司"],
                ["skills", "list", "否", "技能标签列表"],
                ["core_competencies", "list", "否", "核心竞争力列表"],
                ["projects", "list", "否", "项目经历列表"],
                ["expected_positions", "list", "否", "期望岗位列表"],
                ["expected_salary_min", "int", "否", "期望最低薪资（K/月）"],
                ["expected_salary_max", "int", "否", "期望最高薪资（K/月）"],
                ["expected_locations", "list", "否", "期望工作城市列表"]
            ],
            type="array",
            col_count=(4, "fixed"),
            row_count=(16, "fixed"),
            interactive=False,
            wrap=True
        )

    # ========== 区域4：使用提示 ==========
    gr.Markdown("""
    #### 💡 使用提示
    1. **上传文件**：支持PDF、Word（.docx）、TXT、图片（PNG/JPG）格式
    2. **开始解析**：AI将自动提取简历中的关键信息（耗时10-30秒）
    3. **编辑修正**：可在JSON编辑器中手动修改AI提取的结果
    4. **保存画像**：将数据保存到数据库供其他模块使用
    5. **重新解析**：如需更新数据或更换文件，点击重新解析
    """)

    # ==================== 事件绑定 ====================

    # 绑定"开始解析"按钮事件
    btn_parse.click(
        fn=on_parse_click,
        inputs=[file_input],
        outputs=[status_display, stats_display, json_editor]
    )

    # 绑定"重新解析"按钮事件
    btn_reparse.click(
        fn=on_reparse_click,
        inputs=[file_input],
        outputs=[status_display, stats_display, json_editor]
    )

    # 绑定"保存画像"按钮事件
    btn_save.click(
        fn=on_save_click,
        inputs=[json_editor, file_input],
        outputs=[status_display]  # 保存结果显示在状态栏
    )

    # 绑定"清空"按钮事件（同时清空文件选择器）
    btn_clear.click(
        fn=on_clear_click,
        outputs=[status_display, stats_display, json_editor, file_input]
    )
