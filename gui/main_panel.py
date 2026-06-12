"""
主控制面板模块 - 提供自动化任务的控制和状态监控

包含：启动/暂停/停止按钮、状态指示器、今日统计信息
实现按钮事件绑定与后台任务状态同步
支持真实岗位扫描、匹配评分与自动沟通流程
"""

import asyncio
import gradio as gr
import threading
from typing import Optional, Tuple

from browser.agent import BrowserAgent
from browser.agent_edge import (
    EDGE_DEBUG_PORT,
    EDGE_MANUAL_START_HINT,
    check_edge_cdp_sync,
)
from core.automation_engine import run_automation_loop
from core.vision_agent import run_vision_automation_loop
from core.profile_manager import get_profile_manager
from utils.config_loader import load_settings
from utils.logger import get_logger
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

# GUI 状态（后台线程失败时由定时器同步到界面）
_ui_status = "⏹️ 已停止"


# ==================== 核心回调函数 ====================

def on_start_click(
    daily_limit: int,
    match_threshold: float,
    delay_min: float,
    delay_max: float,
    automation_mode: str,
) -> Tuple[str, str, str, str]:
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
    global _browser_agent, _is_running, _is_paused, _task_thread, _ui_status

    if _is_running and not _is_paused:
        return "⚠️ 自动化任务已在运行中", "disabled", "enabled", "enabled"

    # 从暂停状态恢复
    if _is_running and _is_paused:
        _is_paused = False
        if _browser_agent:
            _browser_agent._paused = False
        _logger.info("▶️ 自动化任务已继续")
        _ui_status = "▶️ 自动化任务已继续"
        return "▶️ 自动化任务已继续", "disabled", "enabled", "enabled"

    profile = get_profile_manager().get_active_profile()
    if profile is None:
        return (
            "❌ 请先在「简历管理」页上传并解析简历，生成用户画像",
            "enabled", "disabled", "disabled",
        )

    mode = (automation_mode or "browser").strip().lower()
    if mode not in ("browser", "vision"):
        mode = "browser"

    if mode == "browser" and not check_edge_cdp_sync():
        _logger.warning("启动前未检测到 Edge CDP: %s", EDGE_MANUAL_START_HINT)
        return (
            f"❌ 未检测到 Edge（端口 {EDGE_DEBUG_PORT}）。"
            "请先运行项目目录下的 start_edge.bat 启动 Edge，再点击「启动自动求职」。",
            "enabled",
            "disabled",
            "disabled",
        )

    if mode == "vision":
        _logger.info("视觉模式：请手动打开 BOSS 直聘搜索页并置于前台")

    try:
        _is_running = True
        _is_paused = False
        _ui_status = "▶️ 正在连接 Edge..."

        _logger.info("🚀 正在启动自动化求职任务...")

        simulator = get_simulator()
        simulator.set_delay_range(delay_min, delay_max)

        if mode == "browser":
            if _browser_agent is None:
                _browser_agent = BrowserAgent()
            start_automation_task(
                daily_limit, match_threshold, profile, automation_mode=mode
            )
            return "▶️ 自动化任务已启动（连接 Edge 中）", "disabled", "enabled", "enabled"

        start_automation_task(
            daily_limit, match_threshold, profile, automation_mode=mode
        )
        return "▶️ 视觉模式已启动（请将 BOSS 窗口置于前台）", "disabled", "enabled", "enabled"

    except Exception as e:
        _is_running = False
        _ui_status = f"❌ 启动失败: {str(e)}"
        _logger.error(f"💥 启动自动化任务失败: {e}", exc_info=True)
        return f"❌ 启动失败: {str(e)}", "enabled", "disabled", "disabled"


def on_pause_click() -> Tuple[str, str, str, str]:
    """
    点击"暂停"按钮的回调函数

    暂停当前自动化任务，保持浏览器状态

    Returns:
        tuple: (状态文本, 启动按钮状态, 暂停按钮状态, 停止按钮状态)
    """
    global _is_paused, _ui_status

    if not _is_running:
        return "⏹️ 任务未运行", "enabled", "disabled", "disabled"

    _is_paused = True

    # 如果浏览器Agent存在，调用暂停方法
    if _browser_agent:
        _browser_agent._paused = True
        _logger.info("⏸️ 自动化任务已暂停")

    _ui_status = "⏸️ 自动化任务已暂停"
    return "⏸️ 自动化任务已暂停", "enabled", "disabled", "enabled"


def on_stop_click() -> Tuple[str, str, str, str]:
    """
    点击"停止"按钮的回调函数

    停止自动化任务，释放浏览器资源

    Returns:
        tuple: (状态文本, 启动按钮状态, 暂停按钮状态, 停止按钮状态)
    """
    global _is_running, _is_paused, _browser_agent, _task_thread, _ui_status

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
        _ui_status = "⏹️ 自动化任务已停止"
        return "⏹️ 自动化任务已停止", "enabled", "disabled", "disabled"

    except Exception as e:
        _logger.error(f"💥 停止任务时发生错误: {e}", exc_info=True)
        return f"❌ 停止失败: {str(e)}", "enabled", "disabled", "disabled"


def start_automation_task(
    daily_limit: int,
    match_threshold: float,
    user_profile,
    automation_mode: str = "browser",
):
    """
    启动自动化任务线程

    Args:
        daily_limit: 每日最大沟通数量
        match_threshold: 匹配度阈值
        user_profile: 活跃用户画像
    """
    global _task_thread

    def _on_stats_update(stats: dict):
        _today_stats.update(stats)

    def task_loop():
        """自动化任务主循环"""
        global _is_running, _today_stats, _ui_status

        async def _run_all():
            mode = (automation_mode or "browser").strip().lower()
            if mode == "vision":
                _ui_status = "▶️ 视觉模式运行中"
                _logger.info("✅ 视觉驱动模式启动（无需 Edge CDP）")
                return await run_vision_automation_loop(
                    user_profile=user_profile,
                    daily_limit=daily_limit,
                    match_threshold=match_threshold,
                    should_continue=lambda: _is_running,
                    is_paused=lambda: _is_paused,
                    on_stats_update=_on_stats_update,
                )

            if not _browser_agent._running:
                await _browser_agent.async_start()
                _ui_status = "▶️ 自动化任务运行中"
                _logger.info("✅ BrowserAgent 启动成功")
            return await run_automation_loop(
                browser_agent=_browser_agent,
                user_profile=user_profile,
                daily_limit=daily_limit,
                match_threshold=match_threshold,
                should_continue=lambda: _is_running,
                is_paused=lambda: _is_paused,
                on_stats_update=_on_stats_update,
            )

        try:
            _logger.info(
                f"📋 自动化任务线程启动 | 每日上限: {daily_limit} | "
                f"匹配阈值: {match_threshold}"
            )

            final_stats = asyncio.run(_run_all())

            _today_stats.update(final_stats)
            _ui_status = "✅ 任务已完成"
            _logger.info(
                f"📊 任务完成 | 沟通: {final_stats['matched_count']} | "
                f"跳过: {final_stats['skipped_count']}"
            )

        except Exception as e:
            err = str(e)
            if len(err) > 100:
                err = err[:97] + "..."
            _ui_status = f"❌ 任务失败: {err}"
            _logger.error(f"💥 自动化任务异常: {e}", exc_info=True)
        finally:
            _is_running = False
            if _ui_status.startswith(("▶️", "⏸️")):
                _ui_status = "⏹️ 任务已结束"
            # 任务结束时不关闭 Edge，便于用户继续登录或手动操作
            if _browser_agent and _browser_agent._running:
                try:
                    _browser_agent._running = False
                    _logger.info("自动化任务已结束，Edge 浏览器窗口保持打开")
                except Exception as stop_err:
                    _logger.warning(f"重置 BrowserAgent 状态时出错: {stop_err}")

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


def get_task_ui_state() -> Tuple[str, str, str, str]:
    """同步任务状态与按钮可用性（供定时器刷新）"""
    if _is_running:
        pause = "disabled" if _is_paused else "enabled"
        return _ui_status, "disabled", pause, "enabled"
    return _ui_status, "enabled", "disabled", "disabled"


# ==================== 页面构建函数 ====================

def create_main_panel():
    """
    创建主控制面板界面

    Returns:
        None（直接渲染到父级容器）
    """
    gr.Markdown("### 🎯 任务控制")
    gr.Markdown(
        "**Edge 浏览器：** browser 模式需先运行 `start_edge.bat`；"
        "**vision 模式** 只需将 BOSS 直聘窗口置于前台（无需 CDP）。"
    )

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
        settings = load_settings()
        default_mode = str(settings.get("automation_mode") or "browser")
        automation_mode = gr.Radio(
            choices=["browser", "vision"],
            value=default_mode if default_mode in ("browser", "vision") else "browser",
            label="自动化模式（browser=DOM+Edge | vision=截图+Vision+MCP）",
        )
        daily_limit = gr.Slider(
            minimum=1,
            maximum=100,
            value=2,
            step=1,
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
        inputs=[daily_limit, match_threshold, delay_min, delay_max, automation_mode],
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
    timer.tick(
        fn=get_task_ui_state,
        outputs=[status_text, start_btn, pause_btn, stop_btn],
    )