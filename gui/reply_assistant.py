"""
AI回复助手模块 - 提供与招聘方对话的AI辅助功能
包含：聊天界面、消息历史、AI建议生成、一键发送、一键复制
"""

import gradio as gr
import json
import time
from typing import List, Dict
from core.chat_generator import ChatGenerator
from core.profile_manager import ProfileManager
from utils.logger import get_logger
from utils.db_helper import get_db
from core.models import ChatMessage

# 获取日志记录器
_logger = get_logger(__name__)

# 全局状态
_current_conversation_id = None
_chat_generator = None
_profile_manager = None


def _init_generator():
    """
    初始化聊天生成器和用户画像管理器
    """
    global _chat_generator, _profile_manager
    try:
        _profile_manager = ProfileManager()
        profile = _profile_manager.get_profile()
        if profile:
            _chat_generator = ChatGenerator(profile)
            _logger.info("✅ AI回复助手初始化成功")
        else:
            _logger.warning("⚠️ 未找到用户画像，AI生成功能将受限")
    except Exception as e:
        _logger.error(f"💥 初始化AI回复助手失败: {e}")


# 初始化
_init_generator()


def send_message(
    message: str,
    chat_history: List[List[str]],
    conversation_id: str = None
) -> tuple:
    """
    发送消息到对话
    """
    if not message.strip():
        return chat_history, ""

    # 添加用户消息到聊天历史
    chat_history.append([message, None])

    try:
        # 保存消息到数据库
        db = get_db()
        if conversation_id:
            db.add_message(
                conversation_id,
                {
                    "role": "user",
                    "content": message,
                    "is_sent": True,
                    "ai_generated": 0
                }
            )
        _logger.info(f"📤 消息已发送: {message[:50]}...")
    except Exception as e:
        _logger.warning(f"保存消息失败: {e}")

    return chat_history, ""


def generate_ai_reply(
    chat_history: List[List[str]],
    style: str = "formal",
    context_length: int = 20
) -> str:
    """
    调用AI生成回复建议
    """
    if not _chat_generator:
        return "❌ 请先上传简历创建用户画像"

    try:
        # 设置话术风格
        style_map = {
            "正式专业": "formal",
            "亲切自然": "friendly",
            "突出亮点": "highlight",
            "提问引导": "question"
        }
        _chat_generator.set_style(style_map.get(style, "formal"))

        # 构建对话历史
        messages = []
        for user_msg, bot_msg in chat_history[-context_length:]:
            if user_msg:
                messages.append(ChatMessage(
                    message_id=f"msg_{int(time.time())}",
                    conversation_id="temp",
                    role="user",
                    content=user_msg,
                    is_sent=True
                ))
            if bot_msg:
                messages.append(ChatMessage(
                    message_id=f"msg_{int(time.time())}_bot",
                    conversation_id="temp",
                    role="boss",
                    content=bot_msg,
                    is_sent=False
                ))

        # 生成回复
        reply = _chat_generator.generate_reply(messages)
        _logger.info(f"✨ AI回复建议生成成功: {reply[:50]}...")
        return reply

    except Exception as e:
        _logger.error(f"💥 生成AI回复失败: {e}", exc_info=True)
        return f"❌ AI生成失败: {str(e)}"


def copy_to_clipboard(text: str) -> str:
    """
    复制文本到剪贴板
    """
    import pyperclip
    try:
        pyperclip.copy(text)
        _logger.info("📋 文本已复制到剪贴板")
        return "✅ 已复制到剪贴板"
    except Exception as e:
        _logger.error(f"复制失败: {e}")
        return f"❌ 复制失败: {str(e)}"


def use_suggestion(
    ai_suggestion: str,
    msg_input: gr.Textbox
) -> str:
    """
    将AI建议填充到输入框
    """
    if ai_suggestion and ai_suggestion != "点击「AI生成回复建议」按钮生成...":
        _logger.info("📝 AI建议已填充到输入框")
        return ai_suggestion
    return ""


def refresh_conversations() -> list:
    """
    刷新对话列表
    """
    try:
        db = get_db()
        convs = db.get_recent_conversations(limit=20)
        choices = []
        for conv in convs:
            conv_id = conv.get("conversation_id")
            last_msg = conv.get("last_message", "")[:20] + "..." if len(conv.get("last_message", "")) > 20 else conv.get("last_message", "")
            choices.append((f"会话 {conv_id} - {last_msg}", conv_id))
        return choices
    except Exception as e:
        _logger.error(f"获取对话列表失败: {e}")
        return []


def select_conversation(conversation_id: str) -> tuple:
    """
    选择对话并加载消息历史
    """
    global _current_conversation_id
    _current_conversation_id = conversation_id

    if not conversation_id:
        return [], "未选择对话"

    try:
        db = get_db()
        messages = db.get_conversation_messages(conversation_id, limit=50)

        # 转换为Gradio Chatbot格式
        chat_history = []
        info_lines = []
        last_time = None

        for msg in messages:
            role = msg.get("role")
            content = msg.get("content")
            timestamp = msg.get("timestamp")

            if role == "user":
                chat_history.append([content, None])
            elif role == "boss":
                # 找到最后一个用户消息并添加回复
                if chat_history and chat_history[-1][1] is None:
                    chat_history[-1][1] = content
                else:
                    chat_history.append([None, content])

            if timestamp and not last_time:
                last_time = timestamp

        info_lines.append(f"会话ID: {conversation_id}")
        info_lines.append(f"消息数: {len(messages)}")
        if last_time:
            info_lines.append(f"最后消息: {last_time}")

        _logger.info(f"📂 已加载对话: {conversation_id}")
        return chat_history, "\n".join(info_lines)

    except Exception as e:
        _logger.error(f"加载对话失败: {e}")
        return [], f"加载失败: {str(e)}"


def clear_chat(chat_history: List[List[str]]) -> List[List[str]]:
    """
    清空当前对话
    """
    _logger.info("🗑️ 对话已清空")
    return []


def create_reply_assistant_page():
    """
    创建AI回复助手页面

    Returns:
        None（直接渲染到父级容器）
    """
    gr.Markdown("### 💬 智能对话助手")

    with gr.Row():
        # 左侧：会话列表
        with gr.Column(scale=1):
            gr.Markdown("**对话列表**")
            conversation_list = gr.Dropdown(
                choices=refresh_conversations(),
                label="选择对话",
                interactive=True,
                multiselect=False
            )
            refresh_conv_btn = gr.Button(
                "🔄 刷新列表"
            )

            # 对话摘要信息
            conv_info = gr.Textbox(
                label="对话详情",
                value="未选择对话",
                interactive=False,
                lines=3
            )

        # 右侧：聊天窗口
        with gr.Column(scale=3):
            # 聊天记录显示
            chatbot = gr.Chatbot(
                label="对话内容",
                height=450,
                avatar_images=(
                    None,  # 用户头像（可选）
                    None   # AI头像（可选）
                )
            )

            # 输入区域
            with gr.Row():
                msg_input = gr.Textbox(
                    label="输入消息",
                    placeholder="输入回复内容或让AI生成建议...",
                    lines=2,
                    scale=4,
                    interactive=True
                )
                send_btn = gr.Button(
                    "➤ 发送",
                    variant="primary",
                    scale=1
                )

            # AI辅助工具栏
            with gr.Row():
                ai_generate_btn = gr.Button(
                    "✨ AI生成回复建议",
                    variant="secondary"
                )
                copy_ai_btn = gr.Button(
                    "📋 复制AI建议"
                )
                clear_chat_btn = gr.Button(
                    "🗑️ 清空当前对话"
                )

    gr.Markdown("### 🤖 AI 回复设置")

    with gr.Accordion("回复模式与风格", open=False):
        reply_mode = gr.Radio(
            choices=[
                ("人工确认后发送", "manual"),
                ("全自动回复", "auto"),
                ("仅提供建议不发送", "suggest_only")
            ],
            value="manual",
            label="回复模式"
        )

        reply_style = gr.Dropdown(
            choices=[
                "正式专业",
                "亲切自然",
                "突出亮点",
                "提问引导"
            ],
            value="正式专业",
            label="话术风格"
        )

        context_length = gr.Slider(
            minimum=5,
            maximum=50,
            value=20,
            step=1,
            label="参考上下文消息条数"
        )

    # AI建议预览区
    with gr.Accordion("AI 建议预览", open=True):
        ai_suggestion = gr.Textbox(
            label="AI生成的回复建议",
            value="点击「AI生成回复建议」按钮生成...",
            interactive=False,
            lines=5
        )
        copy_status = gr.Textbox(
            label="复制状态",
            value="",
            interactive=False,
            visible=False
        )
        with gr.Row():
            use_suggestion_btn = gr.Button(
                "✅ 采用此建议并准备发送",
                variant="primary"
            )
            copy_btn = gr.Button(
                "📋 复制建议",
                variant="secondary"
            )

    # ==================== 事件绑定 ====================

    # 发送消息
    send_btn.click(
        fn=send_message,
        inputs=[msg_input, chatbot],
        outputs=[chatbot, msg_input]
    )
    msg_input.submit(
        fn=send_message,
        inputs=[msg_input, chatbot],
        outputs=[chatbot, msg_input]
    )

    # AI生成回复建议
    ai_generate_btn.click(
        fn=generate_ai_reply,
        inputs=[chatbot, reply_style, context_length],
        outputs=[ai_suggestion]
    )

    # 复制AI建议
    copy_ai_btn.click(
        fn=copy_to_clipboard,
        inputs=[ai_suggestion],
        outputs=[copy_status]
    )
    copy_btn.click(
        fn=copy_to_clipboard,
        inputs=[ai_suggestion],
        outputs=[copy_status]
    )

    # 使用AI建议
    use_suggestion_btn.click(
        fn=use_suggestion,
        inputs=[ai_suggestion, msg_input],
        outputs=[msg_input]
    )

    # 刷新对话列表
    refresh_conv_btn.click(
        fn=refresh_conversations,
        outputs=[conversation_list]
    )

    # 选择对话
    conversation_list.change(
        fn=select_conversation,
        inputs=[conversation_list],
        outputs=[chatbot, conv_info]
    )

    # 清空对话
    clear_chat_btn.click(
        fn=clear_chat,
        inputs=[chatbot],
        outputs=[chatbot]
    )