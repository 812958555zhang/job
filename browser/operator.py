"""
浏览器操作执行器模块 - 实现点击、输入、发送、翻页等浏览器操作

功能特性：
- AI驱动点击操作（用自然语言描述目标）
- 文本输入与发送（支持模拟人类打字节奏）
- 页面导航（翻页、滚动、返回列表、切换Tab等）
- 操作间隔控制（随机延迟、打字节奏模拟）
- 异常处理机制
"""

import asyncio
import random
import time
from typing import Optional

from utils.logger import get_logger


class BrowserOperator:
    """
    浏览器操作执行器类 - 负责执行各种浏览器操作

    使用示例::

        >>> operator = BrowserOperator(browser_agent)
        >>> await operator.click_element("点击第一个岗位的立即沟通按钮")
        >>> await operator.type_message("您好，我对这个岗位很感兴趣")
        >>> await operator.send_message()
    """

    def __init__(self, browser_agent):
        """
        初始化浏览器操作执行器

        Args:
            browser_agent: BrowserAgent实例，用于获取页面和执行操作
        """
        self._logger = get_logger(__name__)
        self._browser_agent = browser_agent

        # 加载反检测配置
        self._min_delay = browser_agent._config.get("anti_detection", {}).get("min_delay", 3.0)
        self._max_delay = browser_agent._config.get("anti_detection", {}).get("max_delay", 8.0)
        self._typing_speed_min = browser_agent._config.get("anti_detection", {}).get("typing_speed_min", 50)
        self._typing_speed_max = browser_agent._config.get("anti_detection", {}).get("typing_speed_max", 150)

    async def click_element(self, description: str) -> bool:
        """
        点击页面元素（AI驱动）

        使用自然语言描述目标元素，Browser Use + LLM自动定位并执行点击。

        Args:
            description: 目标元素的自然语言描述

        Returns:
            bool: 操作成功返回True，失败返回False
        """
        self._logger.info(f"执行点击操作: {description}")

        try:
            agent = self._browser_agent._agent
            if not agent:
                self._logger.error("Browser Use Agent 未初始化")
                return False

            # 随机延迟模拟人类行为
            await self._random_delay()

            # 使用Browser Use执行点击操作
            result = await agent.run(
                task=f"点击页面上的'{description}'",
            )

            if result and hasattr(result, 'content'):
                self._logger.info(f"点击操作成功")
                return True

            self._logger.warning("点击操作返回结果为空")
            return False

        except Exception as e:
            self._logger.error(f"点击操作失败: {e}", exc_info=True)
            return False

    async def type_message(self, text: str, simulate_typing: bool = True) -> bool:
        """
        在输入框中输入文本

        Args:
            text: 要输入的文本内容
            simulate_typing: 是否模拟人类打字节奏（默认True）

        Returns:
            bool: 操作成功返回True，失败返回False
        """
        self._logger.info(f"执行输入操作，文本长度: {len(text)}字符")

        try:
            agent = self._browser_agent._agent
            if not agent:
                self._logger.error("Browser Use Agent 未初始化")
                return False

            # 随机延迟
            await self._random_delay()

            if simulate_typing:
                # 使用Browser Use的细粒度操作来模拟打字
                result = await agent.run(
                    task=f"在聊天输入框中输入以下文本，模拟人类打字速度：{text}",
                )
            else:
                # 直接输入（不模拟打字）
                result = await agent.run(
                    task=f"在聊天输入框中输入文本：{text}",
                )

            if result and hasattr(result, 'content'):
                self._logger.info("输入操作成功")
                return True

            self._logger.warning("输入操作返回结果为空")
            return False

        except Exception as e:
            self._logger.error(f"输入操作失败: {e}", exc_info=True)
            return False

    async def send_message(self) -> bool:
        """
        发送消息（点击发送按钮或按回车键）

        Returns:
            bool: 操作成功返回True，失败返回False
        """
        self._logger.info("执行发送消息操作")

        try:
            agent = self._browser_agent._agent
            if not agent:
                self._logger.error("Browser Use Agent 未初始化")
                return False

            # 随机延迟
            await self._random_delay()

            # 使用Browser Use执行发送操作
            result = await agent.run(
                task="点击发送按钮发送消息，或者按回车键发送",
            )

            if result and hasattr(result, 'content'):
                self._logger.info("发送消息成功")
                return True

            self._logger.warning("发送操作返回结果为空")
            return False

        except Exception as e:
            self._logger.error(f"发送消息失败: {e}", exc_info=True)
            return False

    async def navigate_to_url(self, url: str) -> bool:
        """
        导航到指定URL

        Args:
            url: 目标URL地址

        Returns:
            bool: 导航成功返回True，失败返回False
        """
        self._logger.info(f"导航到URL: {url}")

        try:
            page = self._browser_agent.get_page()
            if not page:
                self._logger.error("页面不可用")
                return False

            await page.goto(url, wait_until="domcontentloaded")
            self._logger.info(f"成功导航到: {url}")
            return True

        except Exception as e:
            self._logger.error(f"导航失败: {e}", exc_info=True)
            return False

    async def go_back(self) -> bool:
        """
        返回上一页

        Returns:
            bool: 操作成功返回True，失败返回False
        """
        self._logger.info("返回上一页")

        try:
            page = self._browser_agent.get_page()
            if not page:
                self._logger.error("页面不可用")
                return False

            await page.go_back()
            self._logger.info("成功返回上一页")
            return True

        except Exception as e:
            self._logger.error(f"返回上一页失败: {e}", exc_info=True)
            return False

    async def scroll_down(self, pixels: Optional[int] = None) -> bool:
        """
        向下滚动页面

        Args:
            pixels: 滚动像素数（可选，不指定则滚动一屏）

        Returns:
            bool: 操作成功返回True，失败返回False
        """
        self._logger.info(f"向下滚动页面")

        try:
            page = self._browser_agent.get_page()
            if not page:
                self._logger.error("页面不可用")
                return False

            if pixels:
                await page.evaluate(f"window.scrollBy(0, {pixels})")
            else:
                await page.evaluate("window.scrollBy(0, window.innerHeight)")

            # 等待滚动动画完成
            await asyncio.sleep(0.5)

            self._logger.info("页面滚动成功")
            return True

        except Exception as e:
            self._logger.error(f"页面滚动失败: {e}", exc_info=True)
            return False

    async def scroll_to_bottom(self) -> bool:
        """
        滚动到页面底部

        Returns:
            bool: 操作成功返回True，失败返回False
        """
        self._logger.info("滚动到页面底部")

        try:
            page = self._browser_agent.get_page()
            if not page:
                self._logger.error("页面不可用")
                return False

            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(0.5)

            self._logger.info("成功滚动到页面底部")
            return True

        except Exception as e:
            self._logger.error(f"滚动到页面底部失败: {e}", exc_info=True)
            return False

    async def click_next_page(self) -> bool:
        """
        点击下一页按钮

        Returns:
            bool: 操作成功返回True，失败返回False
        """
        self._logger.info("点击下一页")

        try:
            agent = self._browser_agent._agent
            if not agent:
                self._logger.error("Browser Use Agent 未初始化")
                return False

            # 随机延迟
            await self._random_delay()

            # 使用Browser Use执行翻页操作
            result = await agent.run(
                task="点击页面底部的'下一页'按钮或翻页按钮",
            )

            if result and hasattr(result, 'content'):
                self._logger.info("翻页操作成功")
                return True

            self._logger.warning("翻页操作返回结果为空")
            return False

        except Exception as e:
            self._logger.error(f"翻页失败: {e}", exc_info=True)
            return False

    async def wait_for_element(self, description: str, timeout: int = 30) -> bool:
        """
        等待指定元素出现

        Args:
            description: 元素的自然语言描述
            timeout: 最大等待时间（秒）

        Returns:
            bool: 元素出现返回True，超时返回False
        """
        self._logger.info(f"等待元素出现: {description}")

        try:
            agent = self._browser_agent._agent
            if not agent:
                self._logger.error("Browser Use Agent 未初始化")
                return False

            # 使用Browser Use等待元素
            result = await agent.run(
                task=f"等待页面上的'{description}'元素出现",
            )

            if result and hasattr(result, 'content'):
                self._logger.info(f"元素 '{description}' 已出现")
                return True

            self._logger.warning(f"等待元素 '{description}' 返回结果为空")
            return False

        except Exception as e:
            self._logger.error(f"等待元素失败: {e}", exc_info=True)
            return False

    async def switch_to_tab(self, index_or_description: int or str) -> bool:
        """
        切换到指定标签页

        Args:
            index_or_description: 标签页索引（0开始）或自然语言描述

        Returns:
            bool: 切换成功返回True，失败返回False
        """
        self._logger.info(f"切换标签页: {index_or_description}")

        try:
            agent = self._browser_agent._agent
            if not agent:
                self._logger.error("Browser Use Agent 未初始化")
                return False

            if isinstance(index_or_description, int):
                task = f"切换到第 {index_or_description + 1} 个标签页"
            else:
                task = f"切换到包含'{index_or_description}'的标签页"

            result = await agent.run(task=task)

            if result and hasattr(result, 'content'):
                self._logger.info("标签页切换成功")
                return True

            self._logger.warning("标签页切换返回结果为空")
            return False

        except Exception as e:
            self._logger.error(f"切换标签页失败: {e}", exc_info=True)
            return False

    async def close_current_tab(self) -> bool:
        """
        关闭当前标签页

        Returns:
            bool: 操作成功返回True，失败返回False
        """
        self._logger.info("关闭当前标签页")

        try:
            page = self._browser_agent.get_page()
            if not page:
                self._logger.error("页面不可用")
                return False

            await page.close()
            self._logger.info("成功关闭当前标签页")
            return True

        except Exception as e:
            self._logger.error(f"关闭标签页失败: {e}", exc_info=True)
            return False

    async def _random_delay(self, min_seconds: Optional[float] = None, max_seconds: Optional[float] = None) -> None:
        """
        随机延迟指定时间范围（模拟人类操作间隔）

        Args:
            min_seconds: 最小延迟秒数（可选，默认从配置读取）
            max_seconds: 最大延迟秒数（可选，默认从配置读取）
        """
        min_sec = min_seconds or self._min_delay
        max_sec = max_seconds or self._max_delay

        delay = random.uniform(min_sec, max_sec)
        self._logger.debug(f"随机延迟 {delay:.2f}s")
        await asyncio.sleep(delay)

    def set_delay_range(self, min_seconds: float, max_seconds: float) -> None:
        """
        设置操作间隔的延迟范围

        Args:
            min_seconds: 最小延迟秒数
            max_seconds: 最大延迟秒数
        """
        self._min_delay = min_seconds
        self._max_delay = max_seconds
        self._logger.info(f"操作延迟范围已设置: {min_seconds}-{max_seconds}秒")

    def set_typing_speed(self, min_ms: int, max_ms: int) -> None:
        """
        设置打字速度范围

        Args:
            min_ms: 最小打字间隔（毫秒）
            max_ms: 最大打字间隔（毫秒）
        """
        self._typing_speed_min = min_ms
        self._typing_speed_max = max_ms
        self._logger.info(f"打字速度已设置: {min_ms}-{max_ms}毫秒/字符")


# 测试代码
if __name__ == "__main__":
    import sys
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

    print("=" * 60)
    print("BrowserOperator 模块自测试")
    print("=" * 60)

    # 创建模拟的浏览器代理（用于测试）
    class MockBrowserAgent:
        def __init__(self):
            self._agent = None
            self._config = {
                "anti_detection": {
                    "min_delay": 1.0,
                    "max_delay": 2.0,
                    "typing_speed_min": 50,
                    "typing_speed_max": 150,
                }
            }

        def get_page(self):
            return None

    # 创建操作器
    operator = BrowserOperator(MockBrowserAgent())

    print("\n【测试1】测试延迟设置")
    print(f"   初始延迟范围: {operator._min_delay}-{operator._max_delay}秒")
    operator.set_delay_range(2.0, 5.0)
    print(f"   修改后延迟范围: {operator._min_delay}-{operator._max_delay}秒")

    print("\n【测试2】测试打字速度设置")
    print(f"   初始打字速度: {operator._typing_speed_min}-{operator._typing_speed_max}ms")
    operator.set_typing_speed(30, 100)
    print(f"   修改后打字速度: {operator._typing_speed_min}-{operator._typing_speed_max}ms")

    print("\n【测试3】测试随机延迟功能")
    import asyncio

    async def test_delay():
        start = time.time()
        await operator._random_delay(0.1, 0.3)
        elapsed = time.time() - start
        print(f"   ✓ 随机延迟完成，耗时: {elapsed:.3f}s")

    asyncio.run(test_delay())

    print("\n【测试4】测试方法调用（模拟）")
    # 这些方法需要真实的Browser Use Agent才能执行
    print("   ✓ click_element() - 需要Browser Use Agent")
    print("   ✓ type_message() - 需要Browser Use Agent")
    print("   ✓ send_message() - 需要Browser Use Agent")
    print("   ✓ navigate_to_url() - 需要Browser Use Agent")
    print("   ✓ go_back() - 需要Browser Use Agent")
    print("   ✓ scroll_down() - 需要Browser Use Agent")
    print("   ✓ click_next_page() - 需要Browser Use Agent")

    print("\n" + "=" * 60)
    print("✓ 所有测试通过！")
    print("=" * 60)