"""
实时日志面板模块 - 显示系统运行日志
包含：滚动文本区域、日志级别筛选、清空/导出、定时刷新
"""

import gradio as gr

from utils.log_reader import (
    clear_log_file,
    export_log_file,
    read_log_tail,
)


def create_log_panel():
    """
    创建实时日志显示面板

    Returns:
        None（直接渲染到父级容器）
    """
    gr.Markdown("### 📋 系统运行日志")

    with gr.Row():
        log_level_filter = gr.Dropdown(
            choices=["ALL", "DEBUG", "INFO", "WARNING", "ERROR"],
            value="ALL",
            label="日志级别筛选",
            scale=1,
        )
        auto_scroll = gr.Checkbox(
            label="自动滚动",
            value=True,
            scale=1,
        )
        clear_log_btn = gr.Button(
            "🗑️ 清空日志",
            scale=1,
        )
    export_log_btn = gr.Button(
        "📥 导出日志",
        scale=1,
    )

    _init_text, _init_stats, _init_ts = read_log_tail()

    log_display = gr.Textbox(
        label="日志输出",
        value=_init_text,
        interactive=False,
        lines=25,
        max_lines=50,
        elem_classes="log-container",
    )

    with gr.Row():
        log_stats = gr.Textbox(
            label="日志统计",
            value=_init_stats,
            interactive=False,
            scale=3,
        )
        last_update = gr.Textbox(
            label="最后更新",
            value=_init_ts,
            interactive=False,
            scale=1,
        )

    export_file = gr.File(
        label="导出文件",
        visible=False,
        interactive=False,
    )

    def refresh_logs(level_filter: str):
        text, stats, ts = read_log_tail(level_filter or "ALL")
        return text, stats, ts

    def on_clear_logs(level_filter: str):
        clear_log_file()
        return refresh_logs(level_filter)

    def on_export_logs():
        path = export_log_file()
        if path:
            return gr.update(value=path, visible=True)
        return gr.update(value=None, visible=False)

    log_level_filter.change(
        fn=refresh_logs,
        inputs=[log_level_filter],
        outputs=[log_display, log_stats, last_update],
    )

    clear_log_btn.click(
        fn=on_clear_logs,
        inputs=[log_level_filter],
        outputs=[log_display, log_stats, last_update],
    )

    export_log_btn.click(
        fn=on_export_logs,
        outputs=[export_file],
    )

    timer = gr.Timer(value=2.0)
    timer.tick(
        fn=refresh_logs,
        inputs=[log_level_filter],
        outputs=[log_display, log_stats, last_update],
    )
