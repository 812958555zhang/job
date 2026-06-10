"""
BOSS直聘求职助手 - 主程序入口

功能：初始化系统组件、组装Gradio界面、启动Web服务器
"""

import gradio as gr
import logging

# 初始化日志系统（必须在导入其他模块之前）
from utils.logger import setup_logger, get_logger

# 配置日志系统
setup_logger(
    log_level=logging.INFO,
    console_output=True,
    file_output=True
)

# 导入其他模块
from gui.main_panel import create_main_panel
from gui.resume_page import create_resume_page
from gui.config_page import create_config_page
from gui.log_panel import create_log_panel
from gui.reply_assistant import create_reply_assistant_page

# 获取日志记录器
logger = get_logger(__name__)


def main():
    """
    主函数：启动BOSS直聘求职助手GUI应用

    流程：
    1. 初始化日志系统（已在模块导入时完成）
    2. 初始化数据库连接
    3. 加载配置文件
    4. 组装Gradio多Tab界面
    5. 启动Web服务器
    """
    logger.info("🚀 正在启动 BOSS直聘智能求职助手...")

    try:
        # 创建各页面组件
        with gr.Blocks(
            title="BOSS直聘求职助手"
        ) as demo:
            # 应用标题
            gr.Markdown("# 🤖 BOSS直聘智能求职助手")

            # 创建Tabs容器
            with gr.Tabs():
                with gr.TabItem("🎮 主控制面板"):
                    create_main_panel()

                with gr.TabItem("📄 简历管理"):
                    create_resume_page()

                with gr.TabItem("⚙️ 配置设置"):
                    create_config_page()

                with gr.TabItem("📋 实时日志"):
                    create_log_panel()

                with gr.TabItem("💬 AI回复助手"):
                    create_reply_assistant_page()

        logger.info("✅ GUI界面组装完成")

        # 启动服务器
        demo.launch(
            server_name="0.0.0.0",      # 允许局域网访问
            server_port=7860,           # 默认端口
            share=False,               # 不生成公共链接
            inbrowser=True,            # 自动打开浏览器
            show_error=True,           # 显示错误详情
        )

    except Exception as e:
        logger.error(f"💥 启动应用失败: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()