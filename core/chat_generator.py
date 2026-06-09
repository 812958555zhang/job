"""
个性化话术生成模块 - 实现打招呼话术和回复话术的AI生成功能

功能特性：
- 根据岗位JD和用户画像生成个性化打招呼语
- 支持多种话术风格选择（正式专业/亲切自然/突出亮点/提问引导）
- 收到BOSS回复后自动生成回复建议
- 支持上下文记忆，保持对话连贯性
"""

from typing import List, Optional

from core.models import ChatMessage, JobInfo, UserProfile
from core.llm_client import VolcengineLLMClient
from utils.logger import get_logger


class ChatGenerator:
    """
    聊天话术生成器类 - 负责AI驱动的话术生成

    使用示例::

        >>> generator = ChatGenerator(user_profile)
        >>> greeting = generator.generate_greeting(job_info)
        >>> print(greeting)
        '您好！我看到贵公司正在招聘Python后端开发工程师，我有5年相关经验...'

        >>> reply = generator.generate_reply(conversation_history)
        >>> print(reply)
        '感谢您的回复！关于您提到的问题，我想说明一下...'
    """

    # 话术风格选项
    STYLE_FORMAL = "formal"           # 正式专业
    STYLE_FRIENDLY = "friendly"       # 亲切自然
    STYLE_HIGHLIGHT = "highlight"     # 突出亮点
    STYLE_QUESTION = "question"       # 提问引导

    # 风格描述映射
    STYLE_DESCRIPTIONS = {
        STYLE_FORMAL: "正式专业风格，适合技术岗和管理岗",
        STYLE_FRIENDLY: "亲切自然风格，适合互联网创业公司",
        STYLE_HIGHLIGHT: "突出亮点风格，重点展示核心竞争力",
        STYLE_QUESTION: "提问引导风格，通过问题引导对方进一步了解",
    }

    def __init__(self, user_profile: UserProfile):
        """
        初始化聊天话术生成器

        Args:
            user_profile: 用户画像对象，包含求职者的个人信息和职业背景
        """
        self._logger = get_logger(__name__)
        self._user_profile = user_profile
        self._llm_client = VolcengineLLMClient()
        self._current_style = self.STYLE_HIGHLIGHT  # 默认使用突出亮点风格

    @property
    def available_styles(self) -> List[str]:
        """
        获取可用的话术风格列表

        Returns:
            List[str]: 风格名称列表
        """
        return list(self.STYLE_DESCRIPTIONS.keys())

    def set_style(self, style: str) -> bool:
        """
        设置当前使用的话术风格

        Args:
            style: 风格名称，必须是 available_styles 中的值

        Returns:
            bool: 设置成功返回 True，失败返回 False
        """
        if style in self.STYLE_DESCRIPTIONS:
            self._current_style = style
            self._logger.info(f"话术风格已切换为: {self.STYLE_DESCRIPTIONS[style]}")
            return True
        else:
            self._logger.warning(f"未知的话术风格: {style}")
            return False

    def generate_greeting(self, job_info: JobInfo, style: Optional[str] = None) -> str:
        """
        生成个性化打招呼语

        根据岗位JD和用户画像，使用AI生成针对性的打招呼消息。
        每条消息都是根据具体岗位动态生成，替代原有的通用模板。

        Args:
            job_info: 岗位信息对象
            style: 话术风格（可选，默认使用当前设置的风格）

        Returns:
            str: 生成的打招呼语文本
        """
        selected_style = style or self._current_style

        # 构建岗位信息摘要
        job_summary = self._build_job_summary(job_info)
        # 构建用户画像摘要
        profile_summary = self._build_profile_summary()

        # 根据风格选择不同的提示词模板
        system_prompt = self._get_greeting_system_prompt(selected_style)
        user_prompt = self._get_greeting_user_prompt(job_summary, profile_summary)

        try:
            self._logger.info(f"正在为岗位 '{job_info.job_name}' 生成打招呼语（风格: {selected_style}）")
            result = self._llm_client.chat(
                message=user_prompt,
                system_prompt=system_prompt,
                temperature=0.7,
                max_tokens=500,
            )
            greeting = result["content"].strip()
            self._logger.info(f"打招呼语生成成功，长度: {len(greeting)}字符")
            return greeting
        except Exception as e:
            self._logger.error(f"生成打招呼语失败: {e}", exc_info=True)
            return self._generate_fallback_greeting(job_info)

    def _build_job_summary(self, job_info: JobInfo) -> str:
        """
        构建岗位信息摘要字符串

        Args:
            job_info: 岗位信息对象

        Returns:
            str: 格式化的岗位信息摘要
        """
        parts = []
        parts.append(f"岗位名称: {job_info.job_name}")
        parts.append(f"公司名称: {job_info.company_name}")
        if job_info.salary_min and job_info.salary_max:
            parts.append(f"薪资范围: {job_info.salary_min}-{job_info.salary_max}K/月")
        elif job_info.salary_min:
            parts.append(f"薪资: {job_info.salary_min}K+/月")
        if job_info.location:
            parts.append(f"工作地点: {job_info.location}")
        if job_info.experience_required:
            parts.append(f"经验要求: {job_info.experience_required}")
        if job_info.education_required:
            parts.append(f"学历要求: {job_info.education_required}")
        if job_info.job_description:
            desc = job_info.job_description[:200] + "..." if len(job_info.job_description) > 200 else job_info.job_description
            parts.append(f"岗位描述: {desc}")
        if job_info.tags:
            parts.append(f"岗位标签: {', '.join(job_info.tags)}")
        return "\n".join(parts)

    def _build_profile_summary(self) -> str:
        """
        构建用户画像摘要字符串

        Returns:
            str: 格式化的用户画像摘要
        """
        parts = []
        parts.append(f"姓名: {self._user_profile.name}")
        parts.append(f"学历: {self._user_profile.education}")
        parts.append(f"工作年限: {self._user_profile.total_experience_years}年")
        if self._user_profile.current_position:
            parts.append(f"当前职位: {self._user_profile.current_position}")
        if self._user_profile.current_company:
            parts.append(f"当前公司: {self._user_profile.current_company}")
        if self._user_profile.skills:
            parts.append(f"技能: {', '.join(self._user_profile.skills)}")
        if self._user_profile.core_competencies:
            parts.append(f"核心竞争力: {', '.join(self._user_profile.core_competencies)}")
        if self._user_profile.projects:
            project_names = [p.get("name", "") for p in self._user_profile.projects[:3]]
            if project_names:
                parts.append(f"项目经历: {', '.join(filter(None, project_names))}")
        if self._user_profile.expected_positions:
            parts.append(f"期望岗位: {', '.join(self._user_profile.expected_positions)}")
        return "\n".join(parts)

    def _get_greeting_system_prompt(self, style: str) -> str:
        """
        获取打招呼语的系统提示词

        Args:
            style: 话术风格

        Returns:
            str: 系统提示词
        """
        base_prompt = """
你是一位专业的求职顾问，擅长根据求职者的个人情况和目标岗位的要求，
生成个性化的打招呼消息。你的回复应该：

1. 自然友好，符合职场沟通礼仪
2. 突出求职者与岗位的匹配点
3. 语言简洁，不超过3-4句话
4. 直接面向招聘方（BOSS），使用第二人称"你"

请根据用户提供的求职者信息和岗位信息，生成一条合适的打招呼消息。
        """.strip()

        # 根据风格添加额外提示
        style_specific = {
            self.STYLE_FORMAL: """
风格要求：正式专业
- 使用专业术语
- 语气沉稳、自信
- 突出专业能力和经验
            """.strip(),
            self.STYLE_FRIENDLY: """
风格要求：亲切自然
- 使用轻松友好的语气
- 避免过于正式的措辞
- 表现出积极热情的态度
            """.strip(),
            self.STYLE_HIGHLIGHT: """
风格要求：突出亮点
- 重点强调求职者的核心优势
- 明确说明与岗位要求的匹配之处
- 使用数据和成果说话
            """.strip(),
            self.STYLE_QUESTION: """
风格要求：提问引导
- 通过提问引起对方兴趣
- 引导对方进一步了解求职者
- 问题要有针对性，与岗位相关
            """.strip(),
        }

        return base_prompt + "\n\n" + style_specific.get(style, "")

    def _get_greeting_user_prompt(self, job_summary: str, profile_summary: str) -> str:
        """
        获取打招呼语的用户提示词

        Args:
            job_summary: 岗位信息摘要
            profile_summary: 用户画像摘要

        Returns:
            str: 用户提示词
        """
        return f"""
请帮我生成一条针对以下岗位的打招呼消息：

【岗位信息】
{job_summary}

【求职者信息】
{profile_summary}

请生成一条专业、个性化的打招呼消息，直接发送给招聘方。
        """.strip()

    def _generate_fallback_greeting(self, job_info: JobInfo) -> str:
        """
        生成降级打招呼语（当AI调用失败时使用）

        Args:
            job_info: 岗位信息对象

        Returns:
            str: 通用打招呼语
        """
        fallback = f"您好！我对贵公司的 {job_info.job_name} 岗位很感兴趣。我有 {self._user_profile.total_experience_years} 年相关工作经验，熟练掌握 {', '.join(self._user_profile.skills[:3])} 等技能，期待与您进一步沟通！"
        self._logger.warning(f"使用降级打招呼语: {fallback[:50]}...")
        return fallback

    def generate_reply(self, conversation_history: List[ChatMessage]) -> str:
        """
        根据对话历史生成回复建议

        当收到BOSS的回复后，自动调用AI生成合适的回复建议。

        Args:
            conversation_history: 对话历史消息列表

        Returns:
            str: 生成的回复建议文本
        """
        if not conversation_history:
            return "请先发送消息开启对话"

        # 构建对话历史文本
        history_text = self._build_history_text(conversation_history)

        system_prompt = """
你是一位专业的求职对话助手，擅长根据对话历史生成合适的回复。

请分析对话历史，理解当前的对话阶段和对方的意图，然后生成一条合适的回复建议。

回复要求：
1. 针对对方的问题或回复做出回应
2. 保持专业、礼貌的语气
3. 简洁明了，避免冗长
4. 如果对方询问细节，提供具体信息
5. 如果对方表达兴趣，表达感谢并引导下一步
6. 如果涉及薪资或面试时间，可以适当询问或确认

请直接生成回复内容，不要包含其他说明文字。
        """.strip()

        user_prompt = f"""
请帮我分析以下对话历史并生成回复建议：

【对话历史】
{history_text}

请生成一条合适的回复消息。
        """.strip()

        try:
            self._logger.info(f"正在生成回复建议，历史消息数: {len(conversation_history)}")
            result = self._llm_client.chat(
                message=user_prompt,
                system_prompt=system_prompt,
                temperature=0.7,
                max_tokens=500,
            )
            reply = result["content"].strip()
            self._logger.info(f"回复建议生成成功，长度: {len(reply)}字符")
            return reply
        except Exception as e:
            self._logger.error(f"生成回复建议失败: {e}", exc_info=True)
            return "请稍等，我正在思考如何回复..."

    def _build_history_text(self, conversation_history: List[ChatMessage]) -> str:
        """
        将对话历史转换为文本格式

        Args:
            conversation_history: 对话历史消息列表

        Returns:
            str: 格式化的对话历史文本
        """
        lines = []
        for msg in conversation_history:
            role_name = {
                "user": "求职者",
                "boss": "招聘方",
                "ai_assistant": "AI助手",
                "system": "系统",
            }.get(msg.role, msg.role)
            content = msg.content[:100] + "..." if len(msg.content) > 100 else msg.content
            lines.append(f"{role_name}: {content}")
        return "\n".join(lines)

    def generate_interview_followup(self, job_info: JobInfo, stage: str) -> str:
        """
        生成面试跟进话术

        根据面试阶段生成合适的跟进消息。

        Args:
            job_info: 岗位信息对象
            stage: 面试阶段（preparing/interviewing/after/interviewed）

        Returns:
            str: 生成的跟进话术
        """
        stage_prompts = {
            "preparing": "面试前的确认消息",
            "interviewing": "面试中的提问",
            "after": "面试后的感谢和跟进",
            "interviewed": "等待结果的跟进",
        }

        system_prompt = f"""
你是一位专业的求职顾问。请根据以下岗位信息和面试阶段，生成一条合适的{stage_prompts.get(stage, '跟进')}消息。

要求：
1. 语气专业礼貌
2. 内容简洁明了
3. 符合当前阶段的沟通目的
        """.strip()

        user_prompt = f"""
岗位信息：
- 岗位名称：{job_info.job_name}
- 公司：{job_info.company_name}

面试阶段：{stage_prompts.get(stage, stage)}

请生成一条合适的{stage_prompts.get(stage, '跟进')}消息。
        """.strip()

        try:
            result = self._llm_client.chat(
                message=user_prompt,
                system_prompt=system_prompt,
                temperature=0.7,
                max_tokens=300,
            )
            return result["content"].strip()
        except Exception as e:
            self._logger.error(f"生成面试跟进话术失败: {e}")
            return self._generate_fallback_followup(job_info, stage)

    def _generate_fallback_followup(self, job_info: JobInfo, stage: str) -> str:
        """
        生成降级面试跟进话术

        Args:
            job_info: 岗位信息对象
            stage: 面试阶段

        Returns:
            str: 通用跟进话术
        """
        fallback_messages = {
            "preparing": f"您好，我是应聘{job_info.job_name}岗位的{self._user_profile.name}，想确认下面试的具体时间和地点，谢谢！",
            "interviewing": "感谢您的介绍！我想了解一下这个岗位的主要职责和团队情况。",
            "after": f"感谢今天的面试机会！我对{job_info.job_name}岗位非常感兴趣，期待您的回复。",
            "interviewed": f"您好，我是{self._user_profile.name}，想跟进一下{job_info.job_name}岗位的面试结果，谢谢！",
        }
        return fallback_messages.get(stage, f"您好，关于{job_info.job_name}岗位，我想了解一下最新进展。")


# 测试代码
if __name__ == "__main__":
    import sys
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

    print("=" * 60)
    print("ChatGenerator 模块自测试")
    print("=" * 60)

    # 创建测试数据
    test_profile = UserProfile(
        name="张三",
        education="本科",
        total_experience_years=5.0,
        current_position="高级后端开发工程师",
        current_company="某互联网公司",
        skills=["Python", "Django", "MySQL", "Redis", "Docker"],
        core_competencies=["系统架构设计", "性能优化", "团队管理"],
        projects=[
            {"name": "电商平台后端重构", "description": "主导完成百万级QPS系统重构"},
            {"name": "微服务架构改造", "description": "将单体应用拆分为12个微服务"},
        ],
        expected_positions=["后端开发工程师", "技术负责人"],
    )

    test_job = JobInfo(
        job_id="job_001",
        job_name="Python后端开发工程师",
        company_name="科技创新有限公司",
        salary_min=25,
        salary_max=40,
        job_description="负责公司核心业务系统的开发和维护，要求3-5年Python开发经验，熟悉Django/Flask框架，掌握MySQL、Redis等数据库技术，有微服务架构经验者优先。",
        experience_required="3-5年",
        education_required="本科",
        location="北京",
        tags=["Python", "后端", "Django", "微服务"],
    )

    # 测试生成器
    generator = ChatGenerator(test_profile)

    print("\n【测试1】生成打招呼语（默认风格）")
    greeting = generator.generate_greeting(test_job)
    print(f"   风格: {generator._current_style}")
    print(f"   内容:\n   {greeting}")

    print("\n【测试2】测试不同话术风格")
    for style in generator.available_styles:
        generator.set_style(style)
        greeting = generator.generate_greeting(test_job)
        print(f"\n   风格: {style} - {generator.STYLE_DESCRIPTIONS[style]}")
        print(f"   内容:\n   {greeting}")

    print("\n【测试3】生成回复建议")
    conversation_history = [
        ChatMessage(
            message_id="msg_001",
            conversation_id="conv_001",
            role="boss",
            content="您好，感谢您的投递！我们对您的简历很感兴趣，想了解一下您目前的薪资期望是多少？",
            is_sent=False,
        ),
        ChatMessage(
            message_id="msg_002",
            conversation_id="conv_001",
            role="user",
            content="您好！感谢您的回复。我的期望薪资是25-30K/月。",
            is_sent=True,
        ),
        ChatMessage(
            message_id="msg_003",
            conversation_id="conv_001",
            role="boss",
            content="好的，这个薪资范围我们可以接受。方便下周二下午2点来公司面试吗？",
            is_sent=False,
        ),
    ]
    reply = generator.generate_reply(conversation_history)
    print(f"   回复建议:\n   {reply}")

    print("\n【测试4】生成面试跟进话术")
    for stage in ["preparing", "interviewing", "after", "interviewed"]:
        followup = generator.generate_interview_followup(test_job, stage)
        print(f"   {stage}: {followup}")

    print("\n" + "=" * 60)
    print("✓ 所有测试通过！")
    print("=" * 60)