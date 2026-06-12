# AI 自动求职系统 - 纯视觉驱动 + MCP 工具调用 技术方案

## 一、核心需求澄清（来自对话）

### 1.1 彭梁超的关键质疑
> "自动求职这一块**完全没有ai的成分**"
> "后面**自动回复 对话 这一步是最难的地方**"

### 1.2 你确认的正确方向
> "正确的方案是**直接让 AI《截图分析定位元素》模拟人类点击鼠标操作键盘执行**"
> "**完全不需要爬网站的数据**"
> "**就不会触发网站的防御机制**"

### 1.3 本质区别

| 维度 | ❌ 当前项目（Browser Use DOM方案） | ✅ 你期望的方案（视觉+MCP方案） |
|------|----------------------------------|------------------------------|
| **页面理解方式** | DOM结构提取（`extract_page_text()`） | **截图 + 视觉模型识别** |
| **元素定位** | CSS选择器 / AI语义描述 | **像素坐标定位** |
| **操作执行** | Playwright API 调用 | **MCP 工具包（pyautogui/系统级模拟）** |
| **反检测原理** | undetectable 模式 | **完全模拟真人操作行为** |
| **通用性** | 仅限浏览器 | **任何桌面应用/网页** |
| **AI参与度** | 仅话术生成用AI | **全流程AI驱动（看→想→做）** |

---

## 二、目标架构：纯视觉驱动的 AI Agent

### 2.1 核心理念
```
人类操作电脑的方式：
  👀 用眼睛看屏幕 → 🧠 大脑理解内容 → 🖱️ 手操作鼠标键盘

AI 模拟人类的方式：
  📸 截图给视觉模型 → 🤖 LLM 理解并决策 → 🎮 MCP 工具调用模拟操作
```

### 2.2 技术架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                     用户交互层 (Gradio GUI)                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐  │
│  │ 主控制面板│ │简历管理页 │ │配置设置页 │ │ 实时画面监控     │  │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └───────┬──────────┘  │
├───────┼────────────┼────────────┼────────────────┼─────────────┤
│       │    AI 决策大脑层 (豆包 LLM + Vision)                       │
│  ┌────▼─────────────────────────────────────────────────────┐   │
│  │                                                           │   │
│  │  ┌─────────────┐    ┌─────────────┐    ┌──────────────┐  │   │
│  │  │ 视觉理解模块 │    │ 决策推理模块 │    │ 任务规划模块  │  │   │
│  │  │ (截图→语义)  │───▶│ (当前状态)  │───▶│ (步骤分解)   │  │   │
│  │  └─────────────┘    └─────────────┘    └──────────────┘  │   │
│  │         ▲                  │                   │          │   │
│  │         │                  ▼                   ▼          │   │
│  │  ┌─────────────┐    ┌─────────────┐    ┌──────────────┐  │   │
│  │  │ 话术生成模块 │    │ 匹配判断模块 │    │ 异常处理模块  │  │   │
│  │  │ (个性化消息) │    │ (人岗匹配)  │    │ (验证码等)   │  │   │
│  │  └─────────────┘    └─────────────┘    └──────────────┘  │   │
│  └───────────────────────────────────────────────────────────┘   │
├──────────────────────────────────────────────────────────────────┤
│                    MCP 工具执行层（模拟真人操作）                    │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌─────────────┐  │
│  │ 鼠标控制   │ │ 键盘控制   │ │ 截图捕获   │ │ 剪贴板操作  │  │
│  │ (移动/点击) │ │ (输入/快捷键)│ (屏幕/区域)│ │ (复制/粘贴) │  │
│  └────────────┘ └────────────┘ └────────────┘ └─────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

### 2.3 核心工作循环（Agent Loop）

```
                    ┌──────────────────┐
                    │   ① 截取屏幕     │ ← pyautogui/mss 截图
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │ ② 视觉模型理解   │ ← 豆包 Vision 分析截图
                    │ 返回: 当前状态   │
                    │ - 页面类型       │
                    │ - 可见元素列表   │
                    │ - 元素位置(坐标) │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │ ③ LLM 决策      │ ← 豆包 LLM 推理下一步
                    │ 输出: 操作决策   │
                    │ - 操作类型       │
                    │ - 目标坐标       │
                    │ - 操作参数       │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │ ④ MCP 工具执行   │ ← pyautogui 执行操作
                    │ - mouse_click()  │
                    │ - type_text()    │
                    │ - key_press()    │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │ ⑤ 行为模拟延迟   │ ← DelaySimulator
                    │ - 随机等待        │
                    │ - 打字节奏        │
                    │ - 鼠标轨迹        │
                    └────────┬─────────┘
                             │
                             ▼
                         回到 ① （循环）
```

---

## 三、技术实现方案详解

### 3.1 第一层：视觉理解模块（Screen Vision）

#### 功能职责
- 截取当前屏幕/窗口画面
- 调用豆包 Vision 模型分析截图
- 返回结构化的界面元素信息（名称、类型、坐标）

#### 核心代码结构

```python
# core/screen_vision.py

import base64
from typing import List, Dict, Optional
from core.llm_client import VolcengineLLMClient


class ScreenElement:
    """屏幕元素信息"""
    def __init__(self, name: str, element_type: str,
                 x: int, y: int, width: int, height: int,
                 confidence: float = 0.9):
        self.name = name            # 元素名称（如"立即沟通按钮"）
        self.element_type = element_type  # 类型（button/input/text/link）
        self.x = x                  # 左上角 X 坐标
        self.y = y                  # 左上角 Y 坐标
        self.width = width          # 元素宽度
        self.height = height        # 元素高度
        self.confidence = confidence # 置信度

    @property
    def center(self) -> tuple:
        """返回元素中心点坐标"""
        return (self.x + self.width // 2, self.y + self.height // 2)


class ScreenVision:
    """
    屏幕视觉理解模块
    
    功能：
    - 截取屏幕画面
    - 调用 Vision 模型识别界面元素
    - 返回元素的位置和类型信息
    """

    def __init__(self, llm_client: VolcengineLLMClient):
        self._llm = llm_client
        self._logger = get_logger(__name__)

    async def capture_and_understand(
        self,
        region: tuple = None,  # (x, y, width, height) 可选区域
        task_context: str = ""  # 任务上下文提示
    ) -> Dict:
        """
        截屏 + AI 理解，返回当前界面状态
        
        Args:
            region: 截图区域（None则全屏）
            task_context: 当前任务描述（帮助AI理解意图）
        
        Returns:
            dict: {
                'page_type': 'search_list',  # 页面类型
                'elements': [ScreenElement, ...],  # 识别到的元素
                'screen_text': '...',  # 屏幕上的文字内容
                'screenshot_path': '...',  # 截图保存路径
            }
        """
        # 1. 截图
        screenshot = await self._capture_screen(region)
        
        # 2. 转为 base64
        image_base64 = self._image_to_base64(screenshot)
        
        # 3. 调用 Vision 模型分析
        result = await self._analyze_with_vision(
            image_base64, task_context
        )
        
        return result

    async def _capture_screen(self, region: tuple = None):
        """截取屏幕画面"""
        import mss
        import mss.tools
        
        with mss.mss() as sct:
            if region:
                monitor = {
                    'left': region[0],
                    'top': region[1],
                    'width': region[2],
                    'height': region[3]
                }
            else:
                monitor = sct.monitors[1]  # 主显示器
            
            screenshot = sct.grab(monitor)
            return screenshot

    async def _analyze_with_vision(
        self,
        image_base64: str,
        task_context: str
    ) -> Dict:
        """调用豆包 Vision 分析截图"""
        
        system_prompt = """
你是一个屏幕界面分析专家。请分析用户提供的屏幕截图，完成以下任务：

1. **识别页面类型**：判断当前是什么页面（搜索列表/岗位详情/聊天窗口/登录页/其他）

2. **识别界面元素**：找出页面上所有可交互的重要元素，包括：
   - 按钮（如"立即沟通"、"发送"、"下一页"）
   - 输入框（如搜索框、聊天输入框）
   - 文本链接（如岗位名称、公司名）
   - 其他重要UI组件

3. **输出每个元素的精确信息**：
   - name: 元素名称（中文描述）
   - type: 元素类型（button/input/text/link/tab/icon）
   - x, y: 元素左上角坐标（像素）
   - width, height: 元素尺寸（像素）
   - text: 元素上显示的文字（如果有）

4. **提取屏幕文字内容**：读取页面上所有可见的文字信息

请以 JSON 格式输出结果。
""".strip()

        user_prompt = f"""
{task_context}

请分析这张屏幕截图，返回界面元素信息。
""".strip()

        # 调用多模态 API（图片 + 文本）
        result = await self._llm_client.avision_chat(
            image_base64=image_base64,
            message=user_prompt,
            system_prompt=system_prompt,
        )
        
        # 解析返回结果
        return self._parse_vision_result(result)

    def _parse_vision_result(self, result: Dict) -> Dict:
        """解析 Vision 模型返回的结果"""
        content = result.get('content', {})
        
        elements = []
        for elem_data in content.get('elements', []):
            elem = ScreenElement(
                name=elem_data.get('name', ''),
                element_type=elem_data.get('type', 'unknown'),
                x=elem_data.get('x', 0),
                y=elem_data.get('y', 0),
                width=elem_data.get('width', 0),
                height=elem_data.get('height', 0),
                confidence=elem_data.get('confidence', 0.9),
            )
            elements.append(elem)
        
        return {
            'page_type': content.get('page_type', 'unknown'),
            'elements': elements,
            'screen_text': content.get('screen_text', ''),
        }

    def find_element_by_name(
        self,
        elements: List[ScreenElement],
        target_name: str,
        fuzzy: bool = True
    ) -> Optional[ScreenElement]:
        """根据名称查找元素（支持模糊匹配）"""
        for elem in elements:
            if fuzzy:
                if target_name in elem.name or elem.name in target_name:
                    return elem
            else:
                if elem.name == target_name:
                    return elem
        return None
```

#### 关键依赖
```python
# requirements.txt 新增
mss>=9.0.0           # 跨平台高速截图库
Pillow>=10.0.0       # 图像处理
pyautogui>=0.9.54     # 鼠标键盘模拟（跨平台）
pyperclip>=1.8.2      # 剪贴板操作
```

---

### 3.2 第二层：MCP 工具执行层（Human Action Simulator）

#### 功能职责
- 提供模拟人类操作的 MCP 工具集
- 鼠标控制（移动、点击、滚动）
- 键盘控制（输入文本、快捷键）
- 剪贴板操作（复制/粘贴）

#### 核心代码结构

```python
# tools/human_action_tools.py

import random
import time
import pyautogui
import pyperclip
from typing import Optional, Tuple
from utils.delay_simulator import DelaySimulator


# 安全设置：防止失控
pyautogui.FAILSAFE = True   # 移动到左上角角落时抛出异常
pyautogui.PAUSE = 0.01      # 每个操作后暂停 10ms


class MouseTool:
    """鼠标控制工具 - 模拟人类鼠标操作"""

    def __init__(self, delay_simulator: DelaySimulator = None):
        self._simulator = delay_simulator or DelaySimulator()

    def move_to(self, x: int, y: int, duration: float = 0.5) -> None:
        """
        移动鼠标到指定坐标（贝塞尔曲线轨迹）
        
        Args:
            x: 目标 X 坐标
            y: 目标 Y 坐标
            duration: 移动持续时间（秒）
        """
        # 获取当前位置
        current_x, current_y = pyautogui.position()
        
        # 使用 pyautogui 的 moveTo（内置缓动）
        pyautogui.moveTo(x, y, duration=duration, 
                        tween=pyautogui.easeOutQuad)

    def click(self, x: int = None, y: int = None, 
              button: str = 'left', clicks: int = 1) -> None:
        """
        点击指定位置
        
        Args:
            x: X 坐标（None 则使用当前位置）
            y: Y 坐标
            button: 'left'/'right'/'middle'
            clicks: 点击次数（2=双击）
        """
        if x is not None and y is not None:
            # 先移动到目标位置（带轨迹）
            self.move_to(x, y)
            
            # 点击前短暂停顿（模拟人类瞄准）
            time.sleep(random.uniform(0.1, 0.3))
        
        pyautogui.click(x=x, y=y, button=button, clicks=clicks)

    def double_click(self, x: int, y: int) -> None:
        """双击指定位置"""
        self.click(x, y, clicks=2)

    def right_click(self, x: int, y: int) -> None:
        """右键点击"""
        self.click(x, y, button='right')

    def scroll(self, clicks: int = 3, x: int = None, y: int = None) -> None:
        """
        滚动鼠标滚轮
        
        Args:
            clicks: 滚动次数（正数向上，负数向下）
            x, y: 滚动位置（可选）
        """
        if x and y:
            self.move_to(x, y)
            time.sleep(0.1)
        pyautogui.scroll(clicks, x=x, y=y)


class KeyboardTool:
    """键盘控制工具 - 模拟人类打字"""

    def __init__(self, delay_simulator: DelaySimulator = None):
        self._simulator = delay_simulator or DelaySimulator()

    def type_text(self, text: str, interval: float = 0.05) -> None:
        """
        输入文本（逐字符，模拟打字速度）
        
        Args:
            text: 要输入的文本
            interval: 每个字符间的间隔（秒），默认 50ms
        """
        for char in text:
            pyautogui.write(char, interval=interval)
            
            # 随机偶尔停顿（模拟思考下一个词）
            if random.random() < 0.05:  # 5% 概率
                time.sleep(random.uniform(0.3, 0.8))

    def paste_text(self, text: str) -> None:
        """
        通过剪贴板粘贴文本（适用于中文/长文本）
        
        Args:
            text: 要粘贴的文本
        """
        # 复制到剪贴板
        pyperclip.copy(text)
        
        # 短暂延迟
        time.sleep(0.05)
        
        # Ctrl+V 粘贴
        pyautogui.hotkey('ctrl', 'v')
        
        time.sleep(0.1)

    def press_key(self, key: str) -> None:
        """按下单个按键"""
        pyautogui.press(key)

    def hotkey(self, *keys: str) -> None:
        """按下组合键"""
        pyautogui.hotkey(*keys)

    def enter(self) -> None:
        """按回车键"""
        pyautogui.press('enter')

    def tab(self) -> None:
        """按 Tab 键"""
        pyautogui.press('tab')


class ScreenTool:
    """屏幕截图工具"""

    def capture(self, region: tuple = None) -> str:
        """
        截取屏幕并保存到临时文件
        
        Args:
            region: (x, y, width, height) 截图区域
        
        Returns:
            str: 截图文件路径
        """
        import mss
        import tempfile
        from datetime import datetime
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'screen_{timestamp}.png'
        filepath = f'data/temp/{filename}'
        
        with mss.mss() as sct:
            if region:
                monitor = {
                    'left': region[0],
                    'top': region[1],
                    'width': region[2],
                    'height': region[3]
                }
            else:
                monitor = sct.monitors[1]
            
            sct.shot(monitor, output=filepath)
        
        return filepath

    def capture_region(self, x: int, y: int, 
                       width: int, height: int) -> str:
        """截取指定区域"""
        return self.capture(region=(x, y, width, height))


# ============================================================
# MCP 工具注册表（供 AI Agent 调用）
# ============================================================

class HumanActionToolkit:
    """
    人类行为模拟工具集（MCP 风格）
    
    将所有操作封装为 AI 可调用的工具函数，
    AI 通过自然语言描述意图，工具集负责执行具体操作。
    """

    def __init__(self):
        self.mouse = MouseTool()
        self.keyboard = KeyboardTool()
        self.screen = ScreenTool()
        self.simulator = DelaySimulator()

    def get_available_tools(self) -> list:
        """
        返回可用工具列表（用于构建 AI 提示词）
        
        Returns:
            list: 工具定义列表
        """
        return [
            {
                'name': 'mouse_click',
                'description': '在指定坐标位置点击鼠标',
                'parameters': {
                    'x': 'X坐标（像素）',
                    'y': 'Y坐标（像素）',
                    'button': '按钮类型：left/right/middle（默认left）',
                }
            },
            {
                'name': 'mouse_move',
                'description': '将鼠标移动到指定坐标位置',
                'parameters': {
                    'x': 'X坐标（像素）',
                    'y': 'Y坐标（像素）',
                    'duration': '移动持续时间秒数（默认0.5）',
                }
            },
            {
                'name': 'type_text',
                'description': '在当前位置输入文本（模拟打字）',
                'parameters': {
                    'text': '要输入的文本内容',
                    'interval': '每个字符间隔秒数（默认0.05）',
                }
            },
            {
                'name': 'paste_text',
                'description': '通过剪贴板粘贴文本（适合中文/长文本）',
                'parameters': {
                    'text': '要粘贴的文本内容',
                }
            },
            {
                'name': 'key_press',
                'description': '按下指定按键',
                'parameters': {
                    'key': '按键名称（enter/tab/space/escape等）',
                }
            },
            {
                'name': 'hotkey',
                'description': '按下组合键',
                'parameters': {
                    'keys': '按键列表（如 ["ctrl", "v"] 表示粘贴）',
                }
            },
            {
                'name': 'scroll',
                'description': '滚动鼠标滚轮',
                'parameters': {
                    'clicks': '滚动次数（正数向上，负数向下，默认3）',
                }
            },
            {
                'name': 'take_screenshot',
                'description': '截取当前屏幕画面',
                'parameters': {
                    'region': '可选截图区域 [x,y,width,height]',
                }
            },
            {
                'name': 'wait',
                'description': '等待指定时间（模拟人类思考）',
                'parameters': {
                    'seconds': '等待秒数',
                }
            },
        ]

    async def execute_action(self, action: Dict) -> bool:
        """
        执行 AI 决策的操作
        
        Args:
            action: AI 返回的操作指令
                {
                    'tool': 'mouse_click',  # 工具名
                    'params': { ... },      # 参数
                }
        
        Returns:
            bool: 是否执行成功
        """
        tool_name = action.get('tool')
        params = action.get('params', {})

        try:
            # 执行前随机延迟（模拟思考时间）
            think_time = self.simulator.human_like_delay()

            if tool_name == 'mouse_click':
                self.mouse.click(
                    x=params.get('x'),
                    y=params.get('y'),
                    button=params.get('button', 'left')
                )
                
            elif tool_name == 'mouse_move':
                self.mouse.move_to(
                    x=params.get('x'),
                    y=params.get('y'),
                    duration=params.get('duration', 0.5)
                )
                
            elif tool_name == 'type_text':
                self.keyboard.type_text(
                    text=params.get('text', ''),
                    interval=params.get('interval', 0.05)
                )
                
            elif tool_name == 'paste_text':
                self.keyboard.paste_text(text=params.get('text', ''))
                
            elif tool_name == 'key_press':
                self.keyboard.press_key(params.get('key', 'enter'))
                
            elif tool_name == 'hotkey':
                self.keyboard.hotkey(*params.get('keys', ['ctrl', 'v']))
                
            elif tool_name == 'scroll':
                self.mouse.scroll(clicks=params.get('clicks', 3))
                
            elif tool_name == 'take_screenshot':
                path = self.screen.capture(region=params.get('region'))
                return path
                
            elif tool_name == 'wait':
                time.sleep(params.get('seconds', 2))
            
            else:
                raise ValueError(f"未知工具: {tool_name}")

            # 操作后短暂延迟
            self.simulator.random_short_delay()
            
            return True

        except Exception as e:
            raise RuntimeError(f"执行操作失败 [{tool_name}]: {e}")
```

---

### 3.3 第三层：AI 决策大脑（Agent Orchestrator）

#### 功能职责
- 协调视觉理解和工具执行
- 维护任务状态和上下文
- 生成个性化话术
- 处理异常情况

#### 核心代码结构

```python
# core/vision_agent.py

import asyncio
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field

from core.screen_vision import ScreenVision, ScreenElement
from tools.human_action_tools import HumanActionToolkit
from core.chat_generator import ChatGenerator
from core.llm_client import VolcengineLLMClient
from utils.delay_simulator import DelaySimulator
from utils.logger import get_logger


@dataclass
class TaskState:
    """任务状态"""
    current_phase: str = 'init'       # 当前阶段
    step_number: int = 0              # 步骤计数
    context_history: List[Dict] = field(default_factory=list)  # 历史记录
    last_action: Dict = None          # 上一次操作
    error_count: int = 0              # 错误计数


class VisionAgent:
    """
    视觉驱动 AI Agent - 核心调度器
    
    工作原理：
    1. 截图 → 视觉模型理解界面
    2. LLM 根据状态决策下一步操作
    3. 调用 MCP 工具执行操作
    4. 循环直到任务完成
    """

    # 定义任务阶段
    PHASE_INIT = 'init'
    PHASE_LOGIN = 'login'
    PHASE_SEARCH = 'search'
    PHASE_SCAN = 'scan'
    PHASE_MATCH = 'match'
    PHASE_CHAT = 'chat'
    PHASE_REPLY = 'reply'
    PHASE_COMPLETE = 'complete'

    def __init__(
        self,
        llm_client: VolcengineLLMClient,
        chat_generator: ChatGenerator = None,
    ):
        self._llm = llm_client
        self._vision = ScreenVision(llm_client)
        self._tools = HumanActionToolkit()
        self._chat_gen = chat_generator or ChatGenerator()
        self._simulator = DelaySimulator()
        self._logger = get_logger(__name__)
        
        self.state = TaskState()

    async def run_job_search_loop(
        self,
        job_criteria: Dict,
        daily_limit: int = 20,
        on_stats_update: Callable = None,
        should_continue: Callable[[], bool] = lambda: True,
    ) -> Dict:
        """
        运行自动求职主循环（纯视觉驱动版）
        
        Args:
            job_criteria: 求职标准（关键词/薪资/地点等）
            daily_limit: 每日最大沟通数量
            on_stats_update: 统计更新回调
            should_continue: 是否继续运行检查
        
        Returns:
            dict: 执行统计结果
        """
        stats = {
            'total_scanned': 0,
            'matched': 0,
            'sent': 0,
            'skipped': 0,
        }

        while should_continue() and stats['sent'] < daily_limit:
            try:
                # ===== 第一步：截图 + 视觉理解 =====
                screen_info = await self._vision.capture_and_understand(
                    task_context=f"正在搜索岗位，标准: {job_criteria}"
                )
                
                page_type = screen_info['page_type']
                elements = screen_info['elements']
                
                self._logger.info(f"当前页面类型: {page_type} | "
                                 f"识别到 {len(elements)} 个元素")

                # ===== 第二步：根据页面类型决策 =====
                if page_type == 'login':
                    # 需要登录
                    await self._handle_login(screen_info)
                    
                elif page_type == 'search_list':
                    # 搜索列表页：扫描岗位
                    jobs = await self._parse_jobs_from_screen(screen_info)
                    
                    for job in jobs:
                        if stats['sent'] >= daily_limit:
                            break
                        
                        # 匹配判断
                        match_result = await self._judge_match(job, job_criteria)
                        
                        if match_result['passed']:
                            # 生成个性化打招呼语
                            greeting = self._chat_gen.generate_greeting(job)
                            
                            # 执行沟通操作
                            success = await self._perform_chat_action(
                                job, greeting, elements
                            )
                            
                            if success:
                                stats['sent'] += 1
                                stats['matched'] += 1
                            else:
                                stats['skipped'] += 1
                        else:
                            stats['skipped'] += 1
                        
                        stats['total_scanned'] += 1
                        
                        if on_stats_update:
                            on_stats_update(stats)
                            
                        # 岗位间间隔
                        await self._simulator.adaptive_delay()
                
                elif page_type == 'chat':
                    # 聊天窗口：处理发送或回复
                    await self._handle_chat_window(screen_info)
                    
                # 循环间延迟
                await self._simulator.random_delay(3.0, 6.0)

            except Exception as e:
                self._logger.error(f"循环执行异常: {e}", exc_info=True)
                self.state.error_count += 1
                
                if self.state.error_count >= 3:
                    self._logger.error("连续错误过多，暂停任务")
                    break
                    
                await asyncio.sleep(5)  # 异常后等待

        self._logger.info(f"求职循环结束 | {stats}")
        return stats

    async def _handle_login(self, screen_info: Dict) -> bool:
        """
        处理登录流程（视觉驱动）
        
        通过截图识别登录界面的元素位置，
        然后 AI 决策如何填写表单并提交。
        """
        self._logger.info("检测到需要登录...")
        elements = screen_info['elements']

        # 让 AI 决定登录操作
        decision = await self._ask_llm_for_decision(
            task_context="用户需要登录 BOSS 直聘",
            available_elements=elements,
            current_state=self.state,
        )

        # 执行 AI 决定的操作
        for action in decision.get('actions', []):
            success = await self._tools.execute_action(action)
            if not success:
                return False
            
            # 操作后再次截图验证
            await asyncio.sleep(2)
            new_screen = await self._vision.capture_and_understand()
            if new_screen['page_type'] != 'login':
                self._logger.info("登录成功")
                return True

        return False

    async def _parse_jobs_from_screen(self, screen_info: Dict) -> List[Dict]:
        """
        从屏幕截图中解析岗位信息（视觉方式）
        
        与传统 DOM 解析不同，这里直接从 Vision 模型
        返回的屏幕文字内容中提取岗位信息。
        """
        from core.models import JobInfo
        
        screen_text = screen_info.get('screen_text', '')
        elements = screen_info.get('elements', [])
        
        # 使用 LLM 从屏幕文字中提取岗位
        system_prompt = """
你是一位岗位信息提取专家。从以下屏幕文字内容中提取所有可见的岗位信息。

每个岗位包含：
- job_name: 岗位名称
- company_name: 公司名称  
- salary: 薪资描述（如"20-30K"）
- location: 地点
- tags: 技能标签（如有）

只输出 JSON 数组格式。
        """.strip()

        result = await self._llm.achat_json(
            message=f"提取以下屏幕中的岗位信息：\n\n{screen_text[:2000]}",
            system_prompt=system_prompt,
            temperature=0.1,
        )

        jobs_data = result.get('content', [])
        
        # 结合元素坐标信息
        jobs = []
        for job_data in jobs_data:
            # 尝试找到对应的 UI 元素（获取坐标）
            matching_elem = self._find_element_for_job(
                job_data.get('job_name', ''), elements
            )
            
            job_info = {
                **job_data,
                'ui_element': matching_elem,  # 关联 UI 元素（含坐标）
            }
            jobs.append(job_info)
        
        return jobs

    async def _perform_chat_action(
        self,
        job: Dict,
        greeting: str,
        elements: List[ScreenElement],
    ) -> bool:
        """
        执行沟通操作（视觉驱动）
        
        流程：
        1. 定位"立即沟通"按钮坐标
        2. 模拟鼠标移动到按钮
        3. 点击按钮
        4. 等待聊天窗口打开
        5. 在输入框输入打招呼语
        6. 发送
        """
        job_elem = job.get('ui_element')  # 岗位关联的 UI 元素
        
        # 1. 让 AI 找到"立即沟通"按钮
        chat_button = await self._find_chat_button(elements, job)
        
        if not chat_button:
            self._logger.warning(f"未找到沟通按钮: {job.get('job_name')}")
            return False

        # 2. 移动鼠标到按钮位置（带轨迹）
        center = chat_button.center
        await self._tools.execute_action({
            'tool': 'mouse_move',
            'params': {'x': center[0], 'y': center[1], 'duration': 0.5}
        })
        
        # 3. 点击前短暂停顿（模拟人类确认）
        await asyncio.sleep(random.uniform(0.5, 1.0))
        
        # 4. 点击按钮
        await self._tools.execute_action({
            'tool': 'mouse_click',
            'params': {'x': center[0], 'y': center[1]}
        })
        
        # 5. 等待聊天窗口加载
        await asyncio.sleep(random.uniform(2.0, 3.5))
        
        # 6. 再次截图，定位输入框
        chat_screen = await self._vision.capture_and_understand(
            task_context="已点击沟通，现在需要在聊天框输入消息"
        )
        
        input_box = self._vision.find_element_by_name(
            chat_screen['elements'], 
            target_name='输入框',
            fuzzy=True
        )
        
        if not input_box:
            self._logger.warning("未找到聊天输入框")
            return False
        
        # 7. 点击输入框获取焦点
        input_center = input_box.center
        await self._tools.execute_action({
            'tool': 'mouse_click',
            'params': {'x': input_center[0], 'y': input_center[1]}
        })
        
        await asyncio.sleep(0.5)
        
        # 8. 粘贴打招呼语（中文用粘贴，不用打字）
        await self._tools.execute_action({
            'tool': 'paste_text',
            'params': {'text': greeting}
        })
        
        # 9. 发送前停顿（模拟检查消息）
        await asyncio.sleep(random.uniform(1.0, 2.0))
        
        # 10. 按 Enter 发送
        await self._tools.execute_action({
            'tool': 'key_press',
            'params': {'key': 'enter'}
        })
        
        self._logger.info(f"✅ 已发送沟通: {job.get('job_name')}")
        return True

    async def _ask_llm_for_decision(
        self,
        task_context: str,
        available_elements: List[ScreenElement],
        current_state: TaskState,
    ) -> Dict:
        """
        询问 LLM 下一步操作决策
        
        这是核心方法：AI 根据当前屏幕状态和历史，
        决定接下来应该做什么操作。
        """
        # 构建元素描述（供 LLM 理解）
        elements_desc = '\n'.join([
            f"- [{elem.name}] 类型={elem.type} "
            f"位置=({elem.x},{elem.y}) 尺寸={elem.width}x{elem.height}"
            for elem in available_elements
        ])

        # 构建可用工具列表
        tools_desc = '\n'.join([
            f"- {t['name']}: {t['description']}"
            for t in self._tools.get_available_tools()
        ])

        system_prompt = """
你是一个桌面自动化 AI 助手，通过控制鼠标和键盘来操作电脑界面。

你的任务是：根据当前屏幕截图中的界面元素，决定下一步应该执行什么操作。

决策原则：
1. 始终模拟真实人类的操作方式（有思考时间、操作轨迹）
2. 优先使用视觉信息（坐标）而非假设元素位置
3. 如果不确定，选择保守操作（先观察再行动）
4. 遇到异常情况（验证码、弹窗）立即报告

输出格式（JSON）：
{
    "thinking": "你的思考过程",
    "actions": [
        {"tool": "工具名", "params": {...}},
        ...
    ],
    "expectation": "执行后期望看到什么变化"
}
        """.strip()

        user_prompt = f"""
【当前任务】{task_context}

【当前阶段】{current_state.current_phase}
【历史操作】最近 {len(current_state.context_history)} 步

【屏幕上可见的元素】
{elements_desc}

【你可以使用的工具】
{tools_desc}

请根据以上信息，决定下一步应该执行的操作。
        """.strip()

        result = await self._llm.achat_json(
            message=user_prompt,
            system_prompt=system_prompt,
            temperature=0.3,  # 适度创造性
        )

        return result.get('content', {})
```

---

## 四、完整流程示例（BOSS 直聘自动求职）

### 4.1 登录流程（视觉驱动）

```
用户启动程序
    ↓
① AI 截图 → Vision 分析 → 识别到"登录页面"
    ↓
② LLM 决策："需要点击手机号输入框"
    ↓
③ MCP 工具执行：mouse_click(x=580, y=280)  ← 输入框坐标
    ↓
④ AI 再次截图 → 确认输入框已获焦点
    ↓
⑤ LLM 决策："输入手机号 138xxxx1234"
    ↓
⑥ MCP 工具执行：paste_text("138xxxx1234")  ← 粘贴输入
    ↓
⑦ AI 截图 → 识别到"发送验证码"按钮
    ↓
⑧ MCP 工具执行：mouse_click(x=750, y=280)
    ↓
⑨ 【人机协作】程序暂停，GUI 显示：
   "请在控制台输入收到的短信验证码：[输入框]"
    ↓
⑩ 用户输入验证码 → 程序继续
    ↓
⑪ MCP 工具执行：paste_text(user_input_code)
    ↓
⑫ MCP 工具执行：mouse_click(x=580, y=350)  ← 登录按钮
    ↓
⑬ AI 截图 → 确认进入主页面 → 登录成功 ✅
```

### 4.2 搜索岗位流程

```
AI 截图 → 识别到"搜索列表页"
    ↓
LLM 决策："点击搜索框，输入关键词 Python后端开发"
    ↓
MCP 执行：mouse_click(search_box) → paste_text("Python后端开发") → key_press("enter")
    ↓
等待 3-5 秒（页面加载）
    ↓
AI 截图 → Vision 提取屏幕上的岗位卡片信息
    ↓
LLM 解析出 10 个岗位（名称/公司/薪资/坐标位置）
    ↓
遍历每个岗位：
    ├── 匹配评分（画像 vs JD）
    ├── 通过？→ 继续
    ├── 生成个性化打招呼语
    └── 执行沟通操作（见下方）
```

### 4.3 沟通操作流程（核心难点）

```
目标：对"Python后端开发 @ XX科技"岗位发起沟通

① AI 从之前的截图中找到该岗位的"立即沟通"按钮坐标
   → button_center = (850, 420)
   
② 模拟鼠标移动（贝塞尔曲线，0.5秒）
   → mouse_move(850, 420, duration=0.5)
   
③ 到达后短暂停顿（0.5-1秒，模拟人类确认）
   → wait(0.7)
   
④ 点击按钮
   → mouse_click(850, 420)
   
⑤ 等待聊天窗口弹出（2-3秒）
   → wait(2.5)
   
⑥ AI 截图 → 识别到聊天输入框位置
   → input_box = (650, 720)
   
⑦ 点击输入框获取焦点
   → mouse_click(650, 720)
   
⑧ 粘贴打招呼语（AI 生成的个性化内容）
   → paste_text("您好，我是XXX，5年Python经验...")
   
⑨ 发送前停顿（1-2秒，模拟检查消息）
   → wait(1.5)
   
⑩ 按 Enter 发送
   → key_press("enter")
   
⑪ 记录已沟通 → 下一个岗位
```

---

## 五、与当前项目的迁移策略

### 5.1 保留的模块（无需修改）

| 模块 | 文件 | 说明 |
|------|------|------|
| 用户画像管理 | `core/profile_manager.py` | 完全复用 |
| 简历 AI 解析 | `core/resume_parser.py` | 完全复用 |
| 话术生成器 | `core/chat_generator.py` | 完全复用 |
| 人岗匹配引擎 | `core/job_screener.py` | 完全复用 |
| 配置管理 | `config/settings.yaml` | 完全复用 |
| 数据库存储 | `utils/db_helper.py` | 完全复用 |
| GUI 界面 | `gui/` | 小幅调整（新增画面监控） |
| 日志系统 | `utils/logger.py` | 完全复用 |

### 5.2 需要重构的模块

| 原模块 | 新模块 | 变化说明 |
|--------|--------|---------|
| `browser/agent.py` (Browser Use) | `core/screen_vision.py` | **DOM提取 → 截图+Vision** |
| `browser/operator.py` (Playwright) | `tools/human_action_tools.py` | **API调用 → MCP工具** |
| `browser/job_scanner.py` (DOM解析) | `core/vision_agent.py` 内置 | **DOM解析 → 视觉识别** |
| `core/automation_engine.py` | `core/vision_agent.py` | **重写为视觉驱动循环** |

### 5.3 可以移除的依赖

```bash
# 不再需要的依赖
pip uninstall browser-use playwright playwright-stealth

# 新增的依赖
pip install mss pyautogui pyperclip Pillow
```

---

## 六、技术优势对比

### 6.1 为什么这个方案更好？

| 维度 | Browser Use DOM 方案 | **视觉+MCP 方案（推荐）** |
|------|---------------------|--------------------------|
| **AI 参与度** | ~30%（仅话术生成） | **~100%（全流程）** |
| **反检测能力** | 中（仍可能被检测为自动化） | **高（完全模拟人类操作）** |
| **通用性** | 仅浏览器 | **任何桌面应用/网页/客户端** |
| **抗改版能力** | 高（语义理解 DOM） | **极高（不依赖 DOM 结构）** |
| **调试难度** | 中（需查看 DOM） | **低（直接看截图）** |
| **商业价值** | 低（类似爬虫脚本） | **高（通用 RPA 平台）** |
| **实现复杂度** | 低（Browser Use 封装好） | **中（需自己组装）** |

### 6.2 彭梁超说的"最难的地方"

> "后面**自动回复 对话 这一步是最难的地方**"

确实如此！但视觉方案的解决思路：

```
传统方案的问题：
  Browser Use 要监听 DOM 变化 → 检测新消息 → 触发回调
  但 BOSS 可能用 WebSocket 推送消息，DOM 变化不一定及时

视觉方案的解决：
  ① 定时截图（每 10-15 秒）
  ② Vision 检测是否有"未读标记"/"红点"/"新消息"
  ③ 对比前后截图差异（像素级 diff）
  ④ 发现新消息 → 截取消息区域 → Vision 读取内容
  ⑤ 调用豆包生成回复 → 粘贴到输入框 → 发送
```

---

## 七、实施路线图

### Phase 1：基础框架搭建（1 周）

- [ ] 创建 `core/screen_vision.py` - 视觉理解模块
- [ ] 创建 `tools/human_action_tools.py` - MCP 工具集
- [ ] 安装新依赖（mss, pyautogui, pyperclip）
- [ ] 编写单元测试：截图 → 元素识别 → 坐标返回

### Phase 2：登录流程实现（3 天）

- [ ] 实现 `_handle_login()` 方法
- [ ] 测试：截图识别登录页 → 定位输入框 → 输入账号 → 短信验证码
- [ ] 实现人机协作：GUI 弹窗让用户输入验证码

### Phase 3：搜索+扫描流程（3 天）

- [ ] 实现视觉驱动的岗位扫描
- [ ] 测试：截图 → Vision 提取岗位信息 → 结构化数据
- [ ] 对比准确率（vs 原 DOM 方案）

### Phase 4：沟通操作流程（5 天）⭐ 核心难点

- [ ] 实现 `_perform_chat_action()` 方法
- [ ] 测试完整流程：定位按钮 → 点击 → 输入 → 发送
- [ ] 加入行为模拟（延迟/轨迹/打字节奏）
- [ ] 反测试：手动观察操作是否像人类

### Phase 5：自动回复功能（5 天）⭐ 最难

- [ ] 实现定时截图监控新消息
- [ ] Vision 检测未读标记/红点
- [ ] 消息内容 OCR 识别
- [ ] 调用豆包生成回复
- [ ] 自动填充并发送

### Phase 6：集成测试 & 优化（3 天）

- [ ] 全流程端到端测试
- [ ] 风控对抗测试（长时间运行是否被封）
- [ ] 参数调优（延迟时间/操作频率）
- [ ] GUI 新增实时画面监控面板

---

## 八、风险与应对

| 风险 | 影响 | 应对措施 |
|------|------|---------|
| **Vision 模型坐标不准** | 点击位置偏移 | 多次截图取平均 + 区域点击（点击元素中心区域而非单点） |
| **响应速度慢** | 单步操作 >5秒 | 使用豆包-lite 做视觉理解；缓存不变的区域 |
| **pyautogui 被拦截** | 某些软件阻止模拟 | 备选方案：win32api / autoit / pywinauto |
| **成本增加** | 每次 API 调用都要钱 | 降低截图频率；简单场景用规则匹配；本地小模型辅助 |
| **光线/分辨率影响** | 不同电脑效果不同 | 自适应校准；支持用户标注参考点 |

---

## 九、结论

### 这个方案的本质

**不是写一个"BOSS直聘爬虫"，而是开发一个通用的"AI 操作电脑助手"。**

就像你在教一个**看不见的人**如何操作电脑：
1. 你告诉他"屏幕长什么样"（截图）
2. 他理解了"现在在哪里"（Vision）
3. 他思考"接下来做什么"（LLM）
4. 他动手操作（MCP 工具）

这套能力一旦打通：
- ✅ BOSS 直聘自动求职
- ✅ 自动刷评论/发帖
- ✅ 自动填表/报税
- ✅ 任何需要重复操作的桌面任务

**这就是彭梁超说的"能商业化"的方向。**

---

**方案版本**: v2.0（视觉驱动版）
**创建日期**: 2026-06-11
**基于对话**: 用户与彭梁超的技术讨论
**核心理念**: AI 截图看界面 → 思考决策 → 模拟人类操作
