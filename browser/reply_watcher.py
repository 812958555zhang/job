"""
新回复监听器模块 - 实现DOM变化检测和新消息通知功能

功能特性：
- 定时检查消息列表DOM变化（未读标记/新消息数量）
- 检测到BOSS新回复时触发回调
- 支持配置检查间隔和重试策略
- 可暂停/恢复监听
"""

import asyncio
import time
from typing import Callable, Dict, Optional

from browser.agent_helpers import run_browser_use_task
from utils.logger import get_logger


class ReplyWatcher:
    """
    新回复监听器类 - 负责检测BOSS直聘消息列表中的新回复

    使用示例::

        >>> def on_new_reply(message):
        ...     print(f"收到新回复: {message}")
        ...
        >>> watcher = ReplyWatcher(browser_agent)
        >>> watcher.register_callback(on_new_reply)
        >>> watcher.start()
        >>> # ... 执行其他操作 ...
        >>> watcher.stop()
    """

    def __init__(self, browser_agent):
        """
        初始化新回复监听器

        Args:
            browser_agent: BrowserAgent实例，用于获取页面和执行操作
        """
        self._logger = get_logger(__name__)
        self._browser_agent = browser_agent

        # 监听状态
        self._running = False
        self._paused = False
        self._task = None

        # 配置参数
        self._check_interval = 10  # 默认检查间隔（秒）
        self._max_retries = 3      # 最大重试次数

        # 回调函数列表
        self._callbacks = []

        # 状态跟踪
        self._last_unread_count = 0
        self._last_message_count = 0
        self._last_check_time = 0

    def start(self, check_interval: int = 10) -> bool:
        """
        启动新回复监听

        Args:
            check_interval: 检查间隔（秒），默认10秒

        Returns:
            bool: 启动成功返回True，失败返回False
        """
        if self._running:
            self._logger.warning("新回复监听器已在运行中")
            return False

        self._check_interval = check_interval
        self._running = True
        self._paused = False

        # 创建异步任务
        self._task = asyncio.create_task(self._watch_loop())
        self._logger.info(f"新回复监听器已启动，检查间隔: {check_interval}秒")

        return True

    def stop(self) -> None:
        """
        停止新回复监听
        """
        if not self._running:
            self._logger.warning("新回复监听器未在运行")
            return

        self._running = False
        self._paused = False

        # 取消异步任务
        if self._task:
            self._task.cancel()
            self._task = None

        self._logger.info("新回复监听器已停止")

    def pause(self) -> None:
        """
        暂停监听（保留状态，可恢复）
        """
        if not self._running:
            self._logger.warning("新回复监听器未在运行")
            return

        self._paused = True
        self._logger.info("新回复监听器已暂停")

    def resume(self) -> None:
        """
        恢复监听
        """
        if not self._running:
            self._logger.warning("新回复监听器未在运行")
            return

        self._paused = False
        self._logger.info("新回复监听器已恢复")

    def register_callback(self, callback: Callable[[Dict], None]) -> None:
        """
        注册新回复回调函数

        Args:
            callback: 回调函数，接收一个包含新回复信息的字典参数
        """
        if callback not in self._callbacks:
            self._callbacks.append(callback)
            self._logger.debug(f"已注册新回复回调: {callback.__qualname__}")

    def unregister_callback(self, callback: Callable[[Dict], None]) -> None:
        """
        移除已注册的回调函数

        Args:
            callback: 要移除的回调函数引用
        """
        try:
            self._callbacks.remove(callback)
            self._logger.debug(f"已移除新回复回调: {callback.__qualname__}")
        except ValueError:
            self._logger.debug(f"回调函数未在列表中: {callback.__qualname__}")

    async def _watch_loop(self) -> None:
        """
        监听主循环（异步）
        """
        self._logger.debug("进入新回复监听循环")

        while self._running:
            try:
                if self._paused:
                    # 暂停状态下只检查运行状态
                    await asyncio.sleep(1)
                    continue

                # 检查新回复
                await self._check_for_new_replies()

                # 等待下一次检查
                await asyncio.sleep(self._check_interval)

            except asyncio.CancelledError:
                self._logger.debug("监听循环被取消")
                break
            except Exception as e:
                self._logger.error(f"监听循环发生异常: {e}", exc_info=True)
                await asyncio.sleep(5)  # 出错后等待5秒再继续

        self._logger.debug("退出新回复监听循环")

    async def _check_for_new_replies(self) -> None:
        """
        检查是否有新回复

        通过比较当前未读消息数量与上次检查的数量，判断是否有新回复。
        """
        try:
            current_state = await self._get_message_state()
            if not current_state:
                return

            self._last_check_time = time.time()

            # 检查未读消息数量变化
            if current_state["unread_count"] > self._last_unread_count:
                new_unread = current_state["unread_count"] - self._last_unread_count
                self._logger.info(f"检测到 {new_unread} 条新未读消息")
                await self._trigger_callbacks({
                    "type": "new_unread",
                    "unread_count": current_state["unread_count"],
                    "new_unread_count": new_unread,
                })

            # 检查消息总数变化（即使未读标记被清除，也能检测到新消息）
            if current_state["message_count"] > self._last_message_count:
                new_messages = current_state["message_count"] - self._last_message_count
                self._logger.info(f"检测到 {new_messages} 条新消息")
                await self._trigger_callbacks({
                    "type": "new_messages",
                    "message_count": current_state["message_count"],
                    "new_message_count": new_messages,
                })

            # 更新状态
            self._last_unread_count = current_state["unread_count"]
            self._last_message_count = current_state["message_count"]

        except Exception as e:
            self._logger.error(f"检查新回复失败: {e}", exc_info=True)

    async def _get_message_state(self) -> Optional[Dict]:
        """
        获取当前消息状态

        Returns:
            Dict: 包含 unread_count 和 message_count 的字典，失败返回 None
        """
        try:
            if hasattr(self._browser_agent, "ensure_browser_use_agent"):
                agent = await self._browser_agent.ensure_browser_use_agent()
            else:
                agent = self._browser_agent._agent
            if not agent:
                self._logger.error("Browser Use Agent 未初始化")
                return None

            # 使用Browser Use获取消息列表状态
            result = await run_browser_use_task(
                agent,
                "获取当前消息列表的状态，包括：1)未读消息数量；2)消息会话总数",
            )

            if result and hasattr(result, 'content'):
                content = str(result.content)
                return self._parse_message_state(content)

            return None

        except Exception as e:
            self._logger.error(f"获取消息状态失败: {e}", exc_info=True)
            return None

    def _parse_message_state(self, content: str) -> Dict:
        """
        解析消息状态文本

        Args:
            content: Browser Use返回的状态文本

        Returns:
            Dict: 包含 unread_count 和 message_count 的字典
        """
        # 尝试从文本中提取数字
        import re

        # 提取未读数量
        unread_match = re.search(r'未读.*?(\d+)', content)
        unread_count = int(unread_match.group(1)) if unread_match else 0

        # 提取消息总数
        count_match = re.search(r'消息.*?(\d+)', content)
        message_count = int(count_match.group(1)) if count_match else 0

        # 如果上述方法失败，尝试提取所有数字
        if unread_count == 0 and message_count == 0:
            numbers = re.findall(r'\d+', content)
            if len(numbers) >= 2:
                unread_count = int(numbers[0])
                message_count = int(numbers[1])
            elif len(numbers) == 1:
                unread_count = int(numbers[0])

        return {
            "unread_count": unread_count,
            "message_count": message_count,
        }

    async def _trigger_callbacks(self, data: Dict) -> None:
        """
        触发所有已注册的回调函数

        Args:
            data: 要传递给回调函数的数据
        """
        for callback in self._callbacks:
            try:
                # 支持同步和异步回调
                result = callback(data)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                self._logger.error(f"回调函数执行异常: {e}", exc_info=True)

    @property
    def is_running(self) -> bool:
        """
        检查监听器是否正在运行

        Returns:
            bool: True表示正在运行，False表示已停止
        """
        return self._running

    @property
    def is_paused(self) -> bool:
        """
        检查监听器是否处于暂停状态

        Returns:
            bool: True表示已暂停，False表示正常运行
        """
        return self._paused

    @property
    def last_check_time(self) -> float:
        """
        获取最后一次检查的时间戳

        Returns:
            float: 时间戳
        """
        return self._last_check_time

    @property
    def unread_count(self) -> int:
        """
        获取当前未读消息数量

        Returns:
            int: 未读消息数量
        """
        return self._last_unread_count

    def set_check_interval(self, interval: int) -> None:
        """
        设置检查间隔

        Args:
            interval: 检查间隔（秒）
        """
        self._check_interval = interval
        self._logger.info(f"检查间隔已设置为: {interval}秒")


# 测试代码
if __name__ == "__main__":
    import sys
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

    print("=" * 60)
    print("ReplyWatcher 模块自测试")
    print("=" * 60)

    # 创建模拟的浏览器代理（用于测试）
    class MockBrowserAgent:
        def __init__(self):
            self._agent = None

    # 创建监听器
    watcher = ReplyWatcher(MockBrowserAgent())

    print("\n【测试1】测试状态管理")
    print(f"   初始运行状态: {watcher.is_running}")
    print(f"   初始暂停状态: {watcher.is_paused}")

    watcher.start(check_interval=5)
    print(f"   启动后运行状态: {watcher.is_running}")
    print(f"   启动后暂停状态: {watcher.is_paused}")

    watcher.pause()
    print(f"   暂停后暂停状态: {watcher.is_paused}")

    watcher.resume()
    print(f"   恢复后暂停状态: {watcher.is_paused}")

    watcher.stop()
    print(f"   停止后运行状态: {watcher.is_running}")

    print("\n【测试2】测试回调注册与触发")
    callback_results = []

    def test_callback(data):
        callback_results.append(data)
        print(f"   ✓ 回调被触发: {data}")

    watcher.register_callback(test_callback)
    assert len(watcher._callbacks) == 1, "回调注册失败"

    # 模拟触发回调
    import asyncio
    asyncio.run(watcher._trigger_callbacks({"type": "test", "data": "hello"}))
    assert len(callback_results) == 1, "回调未被触发"

    watcher.unregister_callback(test_callback)
    assert len(watcher._callbacks) == 0, "回调注销失败"

    print("\n【测试3】测试消息状态解析")
    test_cases = [
        ("未读消息: 3条，消息总数: 15条", {"unread_count": 3, "message_count": 15}),
        ("有5条未读消息", {"unread_count": 5, "message_count": 0}),
        ("消息列表显示20条会话", {"unread_count": 0, "message_count": 20}),
        ("未读: 1, 总数: 10", {"unread_count": 1, "message_count": 10}),
        ("数字: 7 和 25", {"unread_count": 7, "message_count": 25}),
    ]

    for input_text, expected in test_cases:
        result = watcher._parse_message_state(input_text)
        status = "✓" if result == expected else "✗"
        print(f"   {status} '{input_text}' -> {result}")
        assert result == expected, f"解析失败: {input_text}"

    print("\n【测试4】测试属性访问")
    watcher._last_unread_count = 5
    watcher._last_check_time = time.time()
    print(f"   unread_count: {watcher.unread_count}")
    print(f"   last_check_time: {watcher.last_check_time}")

    print("\n【测试5】测试检查间隔设置")
    watcher.set_check_interval(15)
    assert watcher._check_interval == 15, "检查间隔设置失败"
    print(f"   ✓ 检查间隔设置成功: {watcher._check_interval}秒")

    print("\n" + "=" * 60)
    print("✓ 所有测试通过！")
    print("=" * 60)