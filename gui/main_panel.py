"""
主控制面板模块 - 提供自动化任务的控制和状态监控
包含：启动/暂停/停止按钮、状态指示器、今日统计信息
"""

import gradio as gr


def create_main_panel():
    """
    创建主控制面板界面

    Returns:
        None（直接渲染到父级容器）
    """
    gr.Markdown("### 🎯 任务控制")

    with gr.Row():
        # 控制按钮组
        with gr.Column(scale=1):
            start_btn = gr.Button(
                "▶️ 启动自动求职",
                variant="primary",
                size="lg"
            )
            pause_btn = gr.Button(
                "⏸️ 暂停",
                variant="secondary"
            )
            stop_btn = gr.Button(
                "⏹️ 停止",
                variant="stop"
            )

        # 状态显示区
        with gr.Column(scale=2):
            status_text = gr.Textbox(
                label="当前状态",
                value="⏹️ 已停止",
                interactive=False
            )
            progress_bar = gr.Progress()

    gr.Markdown("### 📊 今日统计")

    with gr.Row(equal_height=True):
        with gr.Column():
            total_count = gr.Number(
                label="总沟通数",
                value=0,
                interactive=False
            )
        with gr.Column():
            matched_count = gr.Number(
                label="匹配数",
                value=0,
                interactive=False
            )
        with gr.Column():
            replied_count = gr.Number(
                label="已回复数",
                value=0,
                interactive=False
            )
        with gr.Column():
            skipped_count = gr.Number(
                label="跳过数",
                value=0,
                interactive=False
            )

    gr.Markdown("### ⚙️ 快速设置")

    with gr.Accordion("高级选项", open=False):
        daily_limit = gr.Slider(
            minimum=10,
            maximum=100,
            value=50,
            step=5,
            label="每日最大沟通数量"
        )
        match_threshold = gr.Slider(
            minimum=0,
            maximum=100,
            value=60,
            step=5,
            label="匹配度阈值（分）"
        )
        # 使用两个Slider替代RangeSlider（兼容Gradio 6.x）
        delay_min = gr.Slider(
            minimum=2,
            maximum=15,
            value=3,
            step=1,
            label="最小操作间隔（秒）"
        )
        delay_max = gr.Slider(
            minimum=2,
            maximum=15,
            value=8,
            step=1,
            label="最大操作间隔（秒）"
        )

    # TODO: 注册按钮事件回调（后续实现）
    # start_btn.click(fn=start_automation, outputs=status_text)
    # pause_btn.click(fn=pause_automation, outputs=status_text)
    # stop_btn.click(fn=stop_automation, outputs=status_text)
