"""
主控制面板模块 - 提供自动化任务的控制和状态监控

包含：启动/暂停/停止按钮、状态指示器、今日统计信息
实现按钮事件绑定与后台任务状态同步
支持数据统计、去重机制、风控策略优化
"""

import gradio as gr
import time
from typing import Optional, Tuple
from concurrent.futures import ThreadPoolExecutor
import threading

# 导入核心模块
from browser.agent import BrowserAgent
from utils.logger import get_logger
from utils.config_loader import get_config
from utils.delay_simulator import get_simulator
from utils.db_helper import get_db

# ==================== 全局状态管理 ====================

# 全局浏览器Agent实例
_browser_agent: Optional[BrowserAgent] = None

# 自动化任务状态
_is_running = False
_is_paused = False

# 今日统计数据
_today_stats = {
    'total_count': 0,
    'matched_count': 0,
    'replied_count': 0,
    'skipped_count': 0
}

# 日志记录器
_logger = get_logger(__name__)

# 任务线程
_task_thread: Optional[threading.Thread] = None


# ==================== 核心回调函数 ====================

def on_start_click(
    daily_limit: int,
    match_threshold: float,
    delay_min: float,
    delay_max: float
) -> Tuple[str, str, str]:
    """
    点击"启动自动求职"按钮的回调函数

    初始化浏览器Agent，启动岗位扫描和自动沟通流程

    Args:
        daily_limit: 每日最大沟通数量
        match_threshold: 匹配度阈值
        delay_min: 最小操作间隔（秒）
        delay_max: 最大操作间隔（秒）

    Returns:
        tuple: (状态文本, 启动按钮状态, 暂停按钮状态, 停止按钮状态)
    """
    global _browser_agent, _is_running, _is_paused

    if _is_running and not _is_paused:
        return "⚠️ 自动化任务已在运行中", "disabled", "enabled", "enabled"

    try:
        # 更新状态
        _is_running = True
        _is_paused = False

        # 初始化浏览器Agent
        _logger.info("🚀 正在启动自动化求职任务...")

        # 创建浏览器Agent实例
        _browser_agent = BrowserAgent()

        # 配置延迟模拟器
        simulator = get_simulator()
        simulator.set_delay_range(delay_min, delay_max)

        # 启动浏览器
        if _browser_agent.start():
            _logger.info("✅ BrowserAgent 启动成功")

            # 启动自动化任务线程
            start_automation_task(daily_limit, match_threshold)

            return "▶️ 自动化任务已启动", "disabled", "enabled", "enabled"
        else:
            _is_running = False
            _logger.error("❌ BrowserAgent 启动失败")
            return "❌ 浏览器启动失败，请检查日志", "enabled", "disabled", "disabled"

    except Exception as e:
        _is_running = False
        _logger.error(f"💥 启动自动化任务失败: {e}", exc_info=True)
        return f"❌ 启动失败: {str(e)}", "enabled", "disabled", "disabled"


def on_pause_click() -> Tuple[str, str, str, str]:
    """
    点击"暂停"按钮的回调函数

    暂停当前自动化任务，保持浏览器状态

    Returns:
        tuple: (状态文本, 启动按钮状态, 暂停按钮状态, 停止按钮状态)
    """
    global _is_paused

    if not _is_running:
        return "⏹️ 任务未运行", "enabled", "disabled", "disabled"

    _is_paused = True

    # 如果浏览器Agent存在，调用暂停方法
    if _browser_agent:
        _browser_agent._paused = True
        _logger.info("⏸️ 自动化任务已暂停")

    return "⏸️ 自动化任务已暂停", "enabled", "disabled", "enabled"


def on_stop_click() -> Tuple[str, str, str, str]:
    """
    点击"停止"按钮的回调函数

    停止自动化任务，释放浏览器资源

    Returns:
        tuple: (状态文本, 启动按钮状态, 暂停按钮状态, 停止按钮状态)
    """
    global _is_running, _is_paused, _browser_agent, _task_thread

    if not _is_running:
        return "⏹️ 任务未运行", "enabled", "disabled", "disabled"

    try:
        _is_running = False
        _is_paused = False

        # 停止浏览器Agent
        if _browser_agent:
            _browser_agent.stop()
            _browser_agent = None
            _logger.info("🛑 BrowserAgent 已停止")

        # 等待任务线程结束
        if _task_thread and _task_thread.is_alive():
            _logger.info("等待任务线程结束...")

        _task_thread = None

        _logger.info("✅ 自动化任务已完全停止")
        return "⏹️ 自动化任务已停止", "enabled", "disabled", "disabled"

    except Exception as e:
        _logger.error(f"💥 停止任务时发生错误: {e}", exc_info=True)
        return f"❌ 停止失败: {str(e)}", "enabled", "disabled", "disabled"


def start_automation_task(daily_limit: int, match_threshold: float):
    """
    启动自动化任务线程

    Args:
        daily_limit: 每日最大沟通数量
        match_threshold: 匹配度阈值
    """
    global _task_thread

    def task_loop():
        """自动化任务主循环"""
        global _is_running, _is_paused, _today_stats

        try:
            _logger.info(f"📋 开始自动化求职任务 | 每日上限: {daily_limit} | 匹配阈值: {match_threshold}")

            # 模拟扫描流程（实际实现时替换为真实逻辑）
            processed_count = 0

            while _is_running and processed_count < daily_limit:
                # 等待暂停状态
                while _is_paused and _is_running:
                    time.sleep(1)
                    _logger.debug("⏸️ 任务暂停中...")

                if not _is_running:
                    break

                # 模拟岗位扫描和匹配
                _logger.info(f"🔍 正在扫描第 {processed_count + 1}/{daily_limit} 个岗位...")

                # 模拟随机延迟
                simulator = get_simulator()
                simulator.random_short_delay()

                # 模拟匹配结果
                import random
                match_score = random.uniform(0, 100)

                if match_score >= match_threshold:
                    # 匹配成功
                    _today_stats['matched_count'] += 1
                    _today_stats['total_count'] += 1
                    _logger.info(f"✅ 找到匹配岗位 | 匹配度: {match_score:.1f}分")

                    # 模拟发送打招呼消息
                    simulator.random_delay()
                    _logger.info("💬 已发送打招呼消息")

                else:
                    # 匹配失败，跳过
                    _today_stats['skipped_count'] += 1
                    _logger.info(f"⏭️ 跳过岗位 | 匹配度: {match_score:.1f}分（低于阈值 {match_threshold}）")

                processed_count += 1

            _logger.info(f"📊 任务完成 | 总计处理: {processed_count} | 匹配: {_today_stats['matched_count']} | 跳过: {_today_stats['skipped_count']}")

        except Exception as e:
            _logger.error(f"💥 自动化任务异常: {e}", exc_info=True)
            _is_running = False

    # 启动任务线程
    _task_thread = threading.Thread(target=task_loop, daemon=True)
    _task_thread.start()


def get_today_stats() -> Tuple[int, int, int, int]:
    """
    获取今日统计数据（从数据库读取）

    Returns:
        tuple: (总沟通数, 匹配数, 已回复数, 跳过数)
    """
    try:
        db = get_db()
        db_stats = db.get_today_stats()
        return (
            db_stats.get('total', _today_stats['total_count']),
            db_stats.get('sent', _today_stats['matched_count']),
            db_stats.get('replied', _today_stats['replied_count']),
            db_stats.get('skipped', _today_stats['skipped_count'])
        )
    except Exception as e:
        _logger.warning(f"从数据库获取统计数据失败: {e}")
        return (
            _today_stats['total_count'],
            _today_stats['matched_count'],
            _today_stats['replied_count'],
            _today_stats['skipped_count']
        )


def update_stats() -> Tuple[int, int, int, int, float]:
    """
    更新统计数据（用于定时刷新）

    Returns:
        tuple: (总沟通数, 匹配数, 已回复数, 跳过数, 回复率)
    """
    total, matched, replied, skipped = get_today_stats()
    
    # 计算回复率
    reply_rate = (replied / total * 100) if total > 0 else 0.0
    
    return (total, matched, replied, skipped, round(reply_rate, 1))


# ==================== 页面构建函数 ====================

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
            pause_btn.interactive = False
            stop_btn = gr.Button(
                "⏹️ 停止",
                variant="stop"
            )
            stop_btn.interactive = False

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
        with gr.Column():
            reply_rate = gr.Number(
                label="回复率(%)",
                value=0.0,
                interactive=False,
                precision=1
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

    # ==================== 事件绑定 ====================

    # 启动按钮绑定
    start_btn.click(
        fn=on_start_click,
        inputs=[daily_limit, match_threshold, delay_min, delay_max],
        outputs=[status_text, start_btn, pause_btn, stop_btn]
    )

    # 暂停按钮绑定
    pause_btn.click(
        fn=on_pause_click,
        outputs=[status_text, start_btn, pause_btn, stop_btn]
    )

    # 停止按钮绑定
    stop_btn.click(
        fn=on_stop_click,
        outputs=[status_text, start_btn, pause_btn, stop_btn]
    )

    # 定时刷新统计数据
    timer = gr.Timer(value=2.0)
    timer.tick(
        fn=update_stats,
        outputs=[total_count, matched_count, replied_count, skipped_count, reply_rate]
    )