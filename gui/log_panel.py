"""
实时日志面板模块 - 显示系统运行日志
包含：滚动文本区域、日志级别筛选、清空按钮
"""

import gradio as gr


def create_log_panel():
    """
    创建实时日志显示面板

    Returns:
        None（直接渲染到父级容器）
    """
    gr.Markdown("### 📋 系统运行日志")

    # 工具栏
    with gr.Row():
        log_level_filter = gr.Dropdown(
            choices=["ALL", "DEBUG", "INFO", "WARNING", "ERROR"],
            value="ALL",
            label="日志级别筛选",
            scale=1
        )
        auto_scroll = gr.Checkbox(
            label="自动滚动",
            value=True,
            scale=1
        )
        clear_log_btn = gr.Button(
            "🗑️ 清空日志",
            scale=1
        )
        export_log_btn = gr.Button(
            "📥 导出日志",
            scale=1
        )

    # 日志显示区域
    log_display = gr.Textbox(
        label="日志输出",
        value="=== BOSS直聘求职助手日志 ===\n系统就绪，等待操作...\n",
        interactive=False,
        lines=25,
        max_lines=50,
        elem_classes="log-container"
    )

    # 统计信息
    with gr.Row():
        log_stats = gr.Textbox(
            label="日志统计",
            value="总行数: 0 | INFO: 0 | WARNING: 0 | ERROR: 0",
            interactive=False,
            scale=3
        )
        last_update = gr.Textbox(
            label="最后更新",
            value="--:--:--",
            interactive=False,
            scale=1
        )

    # 定时刷新日志（每2秒）
    # TODO: 使用 gr.Timer 组件实现定时刷新
    # timer = gr.Timer(value=2.0)
    # timer.tick(fn=refresh_logs, outputs=log_display)
