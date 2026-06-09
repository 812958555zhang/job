"""
配置设置模块 - 提供求职标准和API参数的配置界面
包含：表单输入、参数滑块、配置保存/加载
"""

import gradio as gr
import yaml
from pathlib import Path


def create_config_page():
    """
    创建配置设置页面

    Returns:
        None（直接渲染到父级容器）
    """
    gr.Markdown("### 🔍 求职筛选标准")

    with gr.Row():
        with gr.Column():
            # 岗位关键词
            job_keywords = gr.Textbox(
                label="岗位关键词（多个用逗号分隔）",
                placeholder="例如：Python后端开发, 全栈工程师",
                value="Python后端开发"
            )

            # 薪资范围
            salary_min = gr.Slider(
                minimum=5,
                maximum=100,
                value=15,
                step=1,
                label="最低期望薪资（K/月）"
            )
            salary_max = gr.Slider(
                minimum=10,
                maximum=200,
                value=30,
                step=1,
                label="最高期望薪资（K/月）"
            )

        with gr.Column():
            # 工作地点
            locations = gr.Textbox(
                label="期望城市（多个用逗号分隔）",
                placeholder="例如：北京, 上海, 杭州",
                value="北京, 上海"
            )

            # 工作年限
            exp_min = gr.Slider(
                minimum=0,
                maximum=20,
                value=3,
                step=1,
                label="最低工作经验（年）"
            )

            # 学历要求
            education = gr.Dropdown(
                choices=["不限", "大专", "本科", "硕士", "博士"],
                value="本科",
                label="最低学历要求"
            )

    gr.Markdown("### 🚫 排除条件")

    with gr.Row():
        blacklist_companies = gr.Textbox(
            label="黑名单公司（排除不投递的公司，逗号分隔）",
            placeholder="留空表示不排除"
        )
        blacklist_keywords = gr.Textbox(
            label="黑名单关键词（排除包含这些词的岗位）",
            placeholder="例如：实习, 兼职"
        )

    gr.Markdown("### 🔑 API 配置")

    with gr.Group():  # 使用Group突出显示重要配置（兼容Gradio 6.x）
        gr.Markdown("**⚠️ API密钥配置（敏感信息，请妥善保管）**")

        api_key = gr.Textbox(
            label="火山引擎 API Key",
            type="password",
            placeholder="从火山引擎控制台获取"
        )

        chat_model = gr.Textbox(
            label="对话模型Endpoint",
            placeholder="ep-xxxxxxxxxxxxx-xxxxx"
        )

        vision_model = gr.Textbox(
            label="视觉模型Endpoint（用于简历解析）",
            placeholder="ep-xxxxxxxxxxxxx-xxxxx"
        )

    gr.Markdown("### ⚙️ 操作参数")

    with gr.Row():
        with gr.Column():
            undetectable_mode = gr.Checkbox(
                label="启用反检测模式",
                value=True,
                info="降低被平台识别为机器人的风险"
            )
            daily_limit = gr.Slider(
                minimum=20,
                maximum=100,
                value=50,
                step=5,
                label="每日最大沟通数量"
            )

        with gr.Column():
            min_delay = gr.Slider(
                minimum=1,
                maximum=15,
                value=3,
                step=1,
                label="最小操作间隔（秒）"
            )
            max_delay = gr.Slider(
                minimum=3,
                maximum=30,
                value=8,
                step=1,
                label="最大操作间隔（秒）"
            )

    # 操作按钮
    with gr.Row():
        save_config_btn = gr.Button(
            "💾 保存配置",
            variant="primary"
        )
        reload_config_btn = gr.Button(
            "🔄 重新加载"
        )
        reset_default_btn = gr.Button(
            "↩️ 恢复默认"
        )

    config_status = gr.Textbox(
        label="操作状态",
        interactive=False
    )

    # TODO: 注册事件回调
    # save_config_btn.click(fn=save_all_config, outputs=config_status)
