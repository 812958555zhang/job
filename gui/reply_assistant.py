"""
AI回复助手模块 - 提供与招聘方对话的AI辅助功能
包含：聊天界面、消息历史、AI建议生成、一键发送
"""

import gradio as gr


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
                choices=[],
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
    with gr.Accordion("AI 建议预览", open=False):
        ai_suggestion = gr.Textbox(
            label="AI生成的回复建议",
            value="点击「AI生成回复建议」按钮生成...",
            interactive=False,
            lines=5
        )
        use_suggestion_btn = gr.Button(
            "✅ 采用此建议并准备发送",
            variant="primary"
        )

    # TODO: 注册事件回调
    # send_btn.click(fn=send_message, inputs=msg_input, outputs=chatbot)
    # ai_generate_btn.click(fn=generate_ai_reply, outputs=ai_suggestion)
