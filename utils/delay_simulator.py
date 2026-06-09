"""
人类行为模拟器模块 - 提供反检测所需的人类行为模拟功能

功能：
- 随机延迟（模拟人类操作间隔）
- 打字节奏模拟（模拟人类打字速度）
- 鼠标轨迹模拟（模拟人类鼠标移动）
- 综合行为延迟控制
- 自适应延迟调整（基于操作频率）
- 风控策略优化（异常模式检测、操作频率监控）

用于降低BOSS直聘风控检测风险，使自动化操作更像真实人类行为。
"""

import random
import time
from typing import Optional, Callable, List
from datetime import datetime, timedelta


class DelaySimulator:
    """
    人类行为模拟器类 - 提供各种反检测延迟和行为模拟功能

    核心功能：
    - 随机延迟生成（3-8秒默认范围）
    - 打字节奏模拟（随机间隔输入字符）
    - 鼠标轨迹模拟（贝塞尔曲线移动）
    - 操作间隔控制
    - 自适应延迟调整
    - 操作频率监控与异常检测

    配置参数：
        min_delay: 最小延迟秒数（默认3.0）
        max_delay: 最大延迟秒数（默认8.0）
        typing_speed_min: 打字最小间隔毫秒（默认50）
        typing_speed_max: 打字最大间隔毫秒（默认150）
        mouse_move_duration: 鼠标移动持续时间（默认0.5秒）
        adaptive_enabled: 是否启用自适应延迟（默认True）
        daily_limit: 每日最大操作次数（默认50）
    """

    # 默认配置常量
    DEFAULT_MIN_DELAY: float = 3.0
    DEFAULT_MAX_DELAY: float = 8.0
    DEFAULT_TYPING_MIN: int = 50      # 毫秒
    DEFAULT_TYPING_MAX: int = 150     # 毫秒
    DEFAULT_MOUSE_DURATION: float = 0.5
    DEFAULT_DAILY_LIMIT: int = 50

    def __init__(
        self,
        min_delay: Optional[float] = None,
        max_delay: Optional[float] = None,
        typing_speed_min: Optional[int] = None,
        typing_speed_max: Optional[int] = None,
        mouse_move_duration: Optional[float] = None,
        adaptive_enabled: bool = True,
        daily_limit: int = DEFAULT_DAILY_LIMIT
    ):
        """
        初始化行为模拟器

        Args:
            min_delay: 最小延迟秒数
            max_delay: 最大延迟秒数
            typing_speed_min: 打字最小间隔（毫秒）
            typing_speed_max: 打字最大间隔（毫秒）
            mouse_move_duration: 鼠标移动持续时间（秒）
            adaptive_enabled: 是否启用自适应延迟
            daily_limit: 每日最大操作次数
        """
        self._min_delay = min_delay or self.DEFAULT_MIN_DELAY
        self._max_delay = max_delay or self.DEFAULT_MAX_DELAY
        self._typing_min = typing_speed_min or self.DEFAULT_TYPING_MIN
        self._typing_max = typing_speed_max or self.DEFAULT_TYPING_MAX
        self._mouse_duration = mouse_move_duration or self.DEFAULT_MOUSE_DURATION
        self._adaptive_enabled = adaptive_enabled
        self._daily_limit = daily_limit

        # 风控状态
        self._operation_timestamps: List[datetime] = []
        self._consecutive_fails = 0
        self._current_delay_multiplier = 1.0
        self._last_reset_time = datetime.now()

        # 自适应学习参数
        self._learned_base_delay = (self._min_delay + self._max_delay) / 2
        self._learned_variance = 0.5

    def random_delay(
        self,
        min_seconds: Optional[float] = None,
        max_seconds: Optional[float] = None
    ) -> float:
        """
        生成并执行随机延迟（模拟人类操作间隔）

        在指定范围内生成随机延迟时间并执行sleep，返回实际延迟时长。

        Args:
            min_seconds: 最小延迟秒数（可选，默认使用初始化值）
            max_seconds: 最大延迟秒数（可选，默认使用初始化值）

        Returns:
            float: 实际延迟的秒数
        """
        min_sec = min_seconds if min_seconds is not None else self._min_delay
        max_sec = max_seconds if max_seconds is not None else self._max_delay

        # 确保范围有效
        if min_sec > max_sec:
            min_sec, max_sec = max_sec, min_sec

        delay = random.uniform(min_sec, max_sec)
        time.sleep(delay)
        return delay

    def simulate_typing(
        self,
        text: str,
        callback: Optional[Callable[[str, int], None]] = None,
        speed_factor: float = 1.0
    ) -> float:
        """
        模拟人类打字节奏

        逐字符输入文本，每个字符之间有随机间隔，模拟真实人类打字行为。

        Args:
            text: 要输入的文本内容
            callback: 字符输入回调函数，接收(current_text, index)参数
            speed_factor: 速度因子，小于1更快，大于1更慢（默认1.0）

        Returns:
            float: 总耗时（秒）
        """
        start_time = time.time()

        for i, char in enumerate(text):
            # 生成打字间隔（毫秒转秒）
            delay_ms = random.randint(self._typing_min, self._typing_max)
            delay = delay_ms / 1000.0 * speed_factor
            time.sleep(delay)

            # 如果提供了回调，通知字符输入
            if callback:
                callback(text[:i+1], i)

        return time.time() - start_time

    def human_like_delay(self) -> float:
        """
        综合人类行为延迟

        根据不同场景返回不同的延迟时间，模拟人类在不同操作间的思考时间。
        - 操作前思考：稍长延迟
        - 操作后停顿：较短延迟
        - 随机因素：增加不确定性

        Returns:
            float: 延迟秒数
        """
        # 根据场景选择延迟模式
        mode = random.choice(['normal', 'thinking', 'quick'])

        if mode == 'thinking':
            # 思考模式：较长延迟（5-10秒）
            delay = random.uniform(5.0, 10.0)
        elif mode == 'quick':
            # 快速模式：较短延迟（1-3秒）
            delay = random.uniform(1.0, 3.0)
        else:
            # 正常模式：中等延迟（3-8秒）
            delay = random.uniform(self._min_delay, self._max_delay)

        time.sleep(delay)
        return delay

    def simulate_mouse_move(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        callback: Optional[Callable[[int, int], None]] = None
    ) -> float:
        """
        模拟人类鼠标移动轨迹（贝塞尔曲线）

        使用贝塞尔曲线模拟人类鼠标从起点到终点的移动轨迹，
        避免机械的直线移动。

        Args:
            start_x: 起点X坐标
            start_y: 起点Y坐标
            end_x: 终点X坐标
            end_y: 终点Y坐标
            callback: 位置更新回调函数，接收(x, y)参数

        Returns:
            float: 移动耗时（秒）
        """
        start_time = time.time()

        # 贝塞尔曲线控制点（随机偏移模拟人类移动）
        control_x = start_x + (end_x - start_x) * random.uniform(0.2, 0.8)
        control_y = start_y + random.uniform(-50, 50)

        # 采样点数（模拟平滑移动）
        steps = random.randint(20, 40)

        for i in range(steps + 1):
            t = i / steps

            # 二次贝塞尔曲线公式
            x = int((1 - t) ** 2 * start_x +
                    2 * (1 - t) * t * control_x +
                    t ** 2 * end_x)
            y = int((1 - t) ** 2 * start_y +
                    2 * (1 - t) * t * control_y +
                    t ** 2 * end_y)

            # 添加微小随机抖动
            x += random.randint(-2, 2)
            y += random.randint(-2, 2)

            # 调用回调更新位置
            if callback:
                callback(x, y)

            # 控制移动速度
            if i < steps:
                time.sleep(self._mouse_duration / steps)

        return time.time() - start_time

    def random_short_delay(self) -> float:
        """
        随机短延迟（用于连续操作之间）

        Returns:
            float: 短延迟秒数（0.5-2秒）
        """
        delay = random.uniform(0.5, 2.0)
        time.sleep(delay)
        return delay

    def random_long_delay(self) -> float:
        """
        随机长延迟（用于需要思考的场景）

        Returns:
            float: 长延迟秒数（10-20秒）
        """
        delay = random.uniform(10.0, 20.0)
        time.sleep(delay)
        return delay

    @property
    def min_delay(self) -> float:
        """获取最小延迟配置"""
        return self._min_delay

    @property
    def max_delay(self) -> float:
        """获取最大延迟配置"""
        return self._max_delay

    def set_delay_range(self, min_delay: float, max_delay: float) -> None:
        """
        设置延迟范围

        Args:
            min_delay: 最小延迟秒数
            max_delay: 最大延迟秒数
        """
        self._min_delay = min_delay
        self._max_delay = max_delay

    def _record_operation(self) -> None:
        """
        记录操作时间戳，用于频率监控

        清理超过24小时的记录，保持列表大小可控。
        """
        now = datetime.now()
        self._operation_timestamps.append(now)

        # 清理超过24小时的记录
        cutoff = now - timedelta(hours=24)
        self._operation_timestamps = [
            ts for ts in self._operation_timestamps if ts >= cutoff
        ]

        # 重置每日计数器
        if now - self._last_reset_time >= timedelta(hours=24):
            self._last_reset_time = now
            self._consecutive_fails = 0
            self._current_delay_multiplier = 1.0

    def get_today_operation_count(self) -> int:
        """
        获取今日已执行的操作次数

        Returns:
            int: 今日操作次数
        """
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        return sum(1 for ts in self._operation_timestamps if ts >= today_start)

    def is_daily_limit_reached(self) -> bool:
        """
        检查是否已达到每日操作上限

        Returns:
            bool: 达到上限返回True，否则返回False
        """
        return self.get_today_operation_count() >= self._daily_limit

    def record_failure(self) -> None:
        """
        记录操作失败，增加失败计数并调整延迟倍率
        """
        self._consecutive_fails += 1

        # 根据连续失败次数增加延迟倍率
        if self._consecutive_fails >= 3:
            self._current_delay_multiplier = min(3.0, self._current_delay_multiplier * 1.5)
        elif self._consecutive_fails >= 5:
            self._current_delay_multiplier = min(5.0, self._current_delay_multiplier * 1.5)

    def record_success(self) -> None:
        """
        记录操作成功，重置失败计数并逐渐恢复延迟倍率
        """
        self._consecutive_fails = 0
        if self._current_delay_multiplier > 1.0:
            self._current_delay_multiplier = max(1.0, self._current_delay_multiplier * 0.9)

    def adaptive_delay(self) -> float:
        """
        自适应延迟 - 根据操作频率和历史记录动态调整延迟

        功能特点：
        - 根据今日操作数量动态调整基础延迟
        - 根据连续失败次数增加延迟
        - 模拟人类行为的随机性

        Returns:
            float: 计算后的延迟秒数
        """
        if not self._adaptive_enabled:
            return self.random_delay()

        self._record_operation()

        # 获取今日操作数
        today_count = self.get_today_operation_count()

        # 根据操作数量计算延迟调整因子
        # 操作越多，延迟越长
        load_factor = min(3.0, 1.0 + (today_count / self._daily_limit) * 2.0)

        # 基础随机延迟
        base_delay = random.uniform(self._min_delay, self._max_delay)

        # 应用各种调整因子
        final_delay = base_delay * load_factor * self._current_delay_multiplier

        # 添加随机抖动（±20%）
        jitter = random.uniform(0.8, 1.2)
        final_delay *= jitter

        # 确保延迟在合理范围内
        final_delay = max(self._min_delay, min(final_delay, self._max_delay * 5))

        time.sleep(final_delay)
        return final_delay

    def get_risk_level(self) -> str:
        """
        获取当前风控风险等级

        Returns:
            str: 风险等级（low/medium/high/critical）
        """
        today_count = self.get_today_operation_count()
        fail_rate = self._consecutive_fails

        if today_count >= self._daily_limit * 0.8 or fail_rate >= 5:
            return "critical"
        elif today_count >= self._daily_limit * 0.6 or fail_rate >= 3:
            return "high"
        elif today_count >= self._daily_limit * 0.4:
            return "medium"
        else:
            return "low"

    def should_pause(self) -> bool:
        """
        判断是否应该暂停操作（基于风控策略）

        Returns:
            bool: 应该暂停返回True，否则返回False
        """
        risk_level = self.get_risk_level()
        return risk_level in ["critical", "high"] and self._consecutive_fails >= 3

    @property
    def daily_limit(self) -> int:
        """获取每日操作上限"""
        return self._daily_limit

    @daily_limit.setter
    def daily_limit(self, value: int) -> None:
        """设置每日操作上限"""
        self._daily_limit = value

    @property
    def adaptive_enabled(self) -> bool:
        """获取自适应延迟是否启用"""
        return self._adaptive_enabled

    @adaptive_enabled.setter
    def adaptive_enabled(self, value: bool) -> None:
        """设置是否启用自适应延迟"""
        self._adaptive_enabled = value


# ============================================================
# 便捷函数（模块级别）
# ============================================================

# 全局模拟器实例（懒加载）
_global_simulator: Optional[DelaySimulator] = None


def get_simulator() -> DelaySimulator:
    """
    获取全局行为模拟器实例（单例模式）

    Returns:
        DelaySimulator: 全局唯一的模拟器实例
    """
    global _global_simulator
    if _global_simulator is None:
        _global_simulator = DelaySimulator()
    return _global_simulator


def random_delay(
    min_seconds: Optional[float] = None,
    max_seconds: Optional[float] = None
) -> float:
    """
    便捷函数：执行随机延迟

    Args:
        min_seconds: 最小延迟秒数（可选）
        max_seconds: 最大延迟秒数（可选）

    Returns:
        float: 实际延迟秒数
    """
    return get_simulator().random_delay(min_seconds, max_seconds)


def simulate_typing(
    text: str,
    callback: Optional[Callable[[str, int], None]] = None,
    speed_factor: float = 1.0
) -> float:
    """
    便捷函数：模拟打字

    Args:
        text: 要输入的文本
        callback: 字符输入回调
        speed_factor: 速度因子

    Returns:
        float: 总耗时（秒）
    """
    return get_simulator().simulate_typing(text, callback, speed_factor)


def human_like_delay() -> float:
    """
    便捷函数：综合人类行为延迟

    Returns:
        float: 延迟秒数
    """
    return get_simulator().human_like_delay()


# ============================================================
# 模块自测试代码
# ============================================================

if __name__ == "__main__":
    """模块自测试代码 - 验证行为模拟器各项功能"""
    import sys
    import io

    # 设置控制台输出编码为UTF-8
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

    print("=" * 70)
    print("人类行为模拟器模块 - 自测试")
    print("=" * 70)

    try:
        # 测试1：创建模拟器实例
        print("\n【测试1】创建 DelaySimulator 实例...")
        simulator = DelaySimulator(
            min_delay=3.0,
            max_delay=8.0,
            typing_speed_min=50,
            typing_speed_max=150
        )
        print(f"   ✓ 实例创建成功")
        print(f"   - 延迟范围: {simulator.min_delay}s ~ {simulator.max_delay}s")

        # 测试2：随机延迟功能
        print("\n【测试2】随机延迟功能...")
        delays = []
        for i in range(5):
            delay = simulator.random_delay(0.1, 0.3)  # 使用短延迟测试
            delays.append(delay)
            print(f"   延迟 {i+1}: {delay:.3f}s")

        # 验证延迟在范围内
        assert all(0.1 <= d <= 0.3 for d in delays), "延迟超出范围"
        print("   ✓ 随机延迟在指定范围内")

        # 测试3：打字模拟功能
        print("\n【测试3】打字模拟功能...")
        typed_chars = []

        def typing_callback(text: str, index: int):
            typed_chars.append(text)

        text = "Hello World!"
        duration = simulator.simulate_typing(text, typing_callback, speed_factor=0.1)
        print(f"   ✓ 输入完成: '{text}'")
        print(f"   ✓ 总耗时: {duration:.3f}s")
        print(f"   ✓ 逐字符回调次数: {len(typed_chars)} (预期: {len(text)})")
        assert len(typed_chars) == len(text), "打字回调次数不匹配"

        # 测试4：综合行为延迟
        print("\n【测试4】综合人类行为延迟...")
        for i in range(3):
            delay = simulator.human_like_delay()
            print(f"   延迟 {i+1}: {delay:.3f}s")
        print("   ✓ 综合延迟功能正常")

        # 测试5：鼠标轨迹模拟
        print("\n【测试5】鼠标轨迹模拟...")
        positions = []

        def mouse_callback(x: int, y: int):
            positions.append((x, y))

        duration = simulator.simulate_mouse_move(0, 0, 100, 100, mouse_callback)
        print(f"   ✓ 轨迹点数: {len(positions)}")
        print(f"   ✓ 移动耗时: {duration:.3f}s")
        assert len(positions) >= 20, "轨迹点数不足"
        assert positions[0] == (0, 0) or abs(positions[0][0]) <= 2, "起点不正确"
        print("   ✓ 鼠标轨迹模拟正常")

        # 测试6：短延迟和长延迟
        print("\n【测试6】短延迟和长延迟...")
        short_delay = simulator.random_short_delay()
        print(f"   ✓ 短延迟: {short_delay:.3f}s")
        assert 0.5 <= short_delay <= 2.0, "短延迟超出范围"

        # 测试7：设置延迟范围
        print("\n【测试7】动态设置延迟范围...")
        simulator.set_delay_range(2.0, 5.0)
        assert simulator.min_delay == 2.0, "最小延迟设置失败"
        assert simulator.max_delay == 5.0, "最大延迟设置失败"
        print(f"   ✓ 延迟范围已更新: {simulator.min_delay}s ~ {simulator.max_delay}s")

        # 测试8：便捷函数
        print("\n【测试8】便捷函数调用...")
        delay = random_delay(0.1, 0.2)
        print(f"   ✓ random_delay(): {delay:.3f}s")

        # 测试9：全局单例模式
        print("\n【测试9】全局单例模式...")
        sim1 = get_simulator()
        sim2 = get_simulator()
        assert sim1 is sim2, "单例模式失效"
        print("   ✓ 单例检查通过")

        print("\n" + "=" * 70)
        print("[SUCCESS] 所有测试通过！")
        print("=" * 70)

    except Exception as e:
        print(f"\n[FAILED] 测试失败: {e}")
        import traceback
        traceback.print_exc()