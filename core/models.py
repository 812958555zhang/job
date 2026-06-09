"""
核心数据模型模块

定义系统中使用的所有 Pydantic v2 数据模型，包括岗位信息、用户画像、
聊天消息、求职筛选标准和求职记录等核心业务实体。
"""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class JobInfo(BaseModel):
    """岗位信息模型 - 用于存储从BOSS直聘提取的岗位详情"""

    # 基础信息
    job_id: str = Field(
        ...,
        description=(
            "岗位唯一标识符。来源：1)从BOSS直聘详情页URL路径中提取 "
            "（如 /job_detail/xxxxx 中的 xxxxx）；"
            "2)或使用 job_{timestamp}_{hash} 格式自动生成 "
            "（hash 取自 job_name + company_name 的前8位）"
        ),
    )
    job_name: str = Field(..., description="岗位名称")
    company_name: str = Field(..., description="公司名称")

    # 薪资信息
    salary_min: Optional[int] = Field(None, description="最低薪资（K/月）")
    salary_max: Optional[int] = Field(None, description="最高薪资（K/月）")
    salary_description: Optional[str] = Field(
        None, description="薪资描述文本"
    )

    # 岗位要求
    job_description: Optional[str] = Field(
        None, description="岗位详细描述/JD"
    )
    experience_required: Optional[str] = Field(
        None, description="工作经验要求"
    )
    education_required: Optional[str] = Field(None, description="学历要求")

    # 地点和其他
    location: Optional[str] = Field(None, description="工作地点")
    company_size: Optional[str] = Field(None, description="公司规模")
    industry: Optional[str] = Field(None, description="所属行业")
    tags: List[str] = Field(default_factory=list, description="岗位标签")

    # AI 匹配预评估结果（可选字段）
    match_score: Optional[float] = Field(
        None,
        ge=0,
        le=100,
        description="人岗匹配度预评估分数（0-100），由 AI 在解析时生成",
    )
    match_reason: Optional[str] = Field(
        None,
        description="匹配/不匹配原因说明，由 AI 在解析时生成",
    )

    # 元数据
    url: Optional[str] = Field(None, description="岗位详情页URL")
    extracted_at: datetime = Field(
        default_factory=datetime.now, description="数据提取时间"
    )


class UserProfile(BaseModel):
    """用户画像模型 - 存储求职者的个人信息和职业背景"""

    # 基本信息
    name: str = Field(..., description="姓名")
    phone: Optional[str] = Field(None, description="联系电话")
    email: Optional[str] = Field(None, description="电子邮箱")

    # 教育背景
    education: str = Field(..., description="最高学历")
    major: Optional[str] = Field(None, description="专业")
    school: Optional[str] = Field(None, description="毕业院校")

    # 工作经验
    total_experience_years: float = Field(..., description="总工作年限")
    current_position: Optional[str] = Field(None, description="当前职位")
    current_company: Optional[str] = Field(None, description="当前公司")

    # 技能和专长
    skills: List[str] = Field(default_factory=list, description="技能标签列表")
    core_competencies: List[str] = Field(
        default_factory=list, description="核心竞争力"
    )

    # 项目经历
    projects: List[Dict[str, Any]] = Field(
        default_factory=list, description="项目经历列表"
    )

    # 求职意向
    expected_positions: List[str] = Field(
        default_factory=list, description="期望岗位"
    )
    expected_salary_min: Optional[int] = Field(
        None, description="期望最低薪资（K/月）"
    )
    expected_salary_max: Optional[int] = Field(
        None, description="期望最高薪资（K/月）"
    )
    expected_locations: List[str] = Field(
        default_factory=list, description="期望工作地点"
    )

    # 简历文件路径
    resume_file_path: Optional[str] = Field(
        None, description="上传的简历文件路径"
    )

    # 元数据
    created_at: datetime = Field(
        default_factory=datetime.now, description="创建时间"
    )
    updated_at: datetime = Field(
        default_factory=datetime.now, description="最后更新时间"
    )


class ChatMessage(BaseModel):
    """聊天消息模型 - 记录与BOSS的对话内容"""

    message_id: str = Field(..., description="消息唯一ID")
    conversation_id: str = Field(..., description="所属会话ID")

    # 消息内容
    role: Literal["user", "boss", "ai_assistant", "system"] = Field(
        ...,
        description=(
            "发送者角色：user=用户本人, boss=招聘方, "
            "ai_assistant=AI助手, system=系统"
        ),
    )
    content: str = Field(..., description="消息内容")
    message_type: Literal["text", "image", "resume", "greeting", "follow_up"] = (
        Field("text", description="消息类型：文本/图片/简历/打招呼/跟进")
    )

    # 时间戳
    timestamp: datetime = Field(
        default_factory=datetime.now, description="消息时间"
    )

    # 关联信息
    job_id: Optional[str] = Field(None, description="关联的岗位ID")
    is_sent: bool = Field(..., description="是否为发出的消息")

    # AI辅助信息
    ai_generated: bool = Field(default=False, description="是否由AI生成")
    ai_suggestion: Optional[str] = Field(
        None, description="AI生成的建议回复（未发送时）"
    )


class JobCriteria(BaseModel):
    """求职筛选标准模型 - 用于配置岗位过滤条件"""

    # 岗位关键词（必须匹配）
    job_keywords: List[str] = Field(
        ...,
        min_length=1,
        description="目标岗位关键词列表（至少一个）",
    )

    # 薪资范围（单位：K/月）
    salary_min: int = Field(0, ge=0, description="最低期望薪资")
    salary_max: int = Field(100, ge=0, description="最高期望薪资")

    # 工作地点
    locations: List[str] = Field(default_factory=list, description="期望城市列表")

    # 经验和学历要求
    experience_min_years: float = Field(0, ge=0, description="最低工作经验年限")
    experience_max_years: Optional[float] = Field(
        None, description="最高工作经验年限"
    )
    education: Optional[str] = Field(None, description="最低学历要求")

    # 可选筛选条件
    company_size_preference: List[str] = Field(
        default_factory=list,
        description="偏好公司规模（如：0-20人、20-99人等）",
    )
    industry_preference: List[str] = Field(
        default_factory=list, description="偏好行业列表"
    )

    # 排除条件
    blacklist_companies: List[str] = Field(
        default_factory=list, description="黑名单公司（排除不投递的公司）"
    )
    blacklist_keywords: List[str] = Field(
        default_factory=list, description="黑名单关键词（排除包含这些词的岗位）"
    )

    # 匹配阈值
    match_score_threshold: float = Field(
        60.0,
        ge=0,
        le=100,
        description="匹配度阈值（低于此分数的岗位自动跳过）",
    )


class ApplicationRecord(BaseModel):
    """求职记录模型 - 记录每次自动沟通的详细信息"""

    record_id: str = Field(..., description="记录唯一ID")

    # 关联岗位信息
    job_info: JobInfo = Field(..., description="岗位详细信息")

    # 匹配评估
    match_score: float = Field(
        ..., ge=0, le=100, description="人岗匹配度分数（0-100）"
    )
    match_reason: Optional[str] = Field(
        None, description="匹配/不匹配原因说明"
    )

    # 沟通内容
    greeting_message: Optional[str] = Field(
        None, description="发送的打招呼话术"
    )
    reply_messages: List[ChatMessage] = Field(
        default_factory=list, description="对方回复的消息列表"
    )

    # 时间线
    applied_at: datetime = Field(
        default_factory=datetime.now, description="发起沟通时间"
    )
    last_reply_at: Optional[datetime] = Field(
        None, description="最后回复时间"
    )

    # 状态跟踪
    status: Literal[
        "pending",  # 待处理（已识别但尚未操作）
        "sent",  # 已发送打招呼
        "replied",  # 对方已回复
        "interviewed",  # 已约面试
        "rejected",  # 已拒绝/不合适
        "skipped",  # 已跳过（不符合标准）
    ] = Field("pending", description="当前状态")

    # 统计信息
    reply_count: int = Field(0, ge=0, description="对方回复次数")

    # 备注
    notes: Optional[str] = Field(None, description="人工备注")


# 测试代码
if __name__ == "__main__":
    # 设置控制台输出编码为UTF-8
    import sys
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

    print("=" * 60)
    print("Pydantic 数据模型验证测试")
    print("=" * 60)

    # 测试 JobInfo 模型
    print("\n1. 测试 JobInfo 模型...")
    job = JobInfo(
        job_id="job_001",
        job_name="Python开发工程师",
        company_name="示例科技有限公司",
        salary_min=15,
        salary_max=25,
        location="北京",
    )
    print(f"   [OK] 创建成功: {job.job_name} @ {job.company_name}")

    # 测试 UserProfile 模型
    print("\n2. 测试 UserProfile 模型...")
    user = UserProfile(
        name="张三",
        education="本科",
        total_experience_years=5.0,
        skills=["Python", "Django", "MySQL"],
        expected_positions=["后端开发工程师"],
    )
    print(
        f"   [OK] 创建成功: {user.name} ({user.education}, "
        f"{user.total_experience_years}年)"
    )

    # 测试 ChatMessage 模型
    print("\n3. 测试 ChatMessage 模型...")
    msg = ChatMessage(
        message_id="msg_001",
        conversation_id="conv_001",
        role="boss",
        content="您好，我对您的简历很感兴趣，方便聊聊吗？",
        is_sent=False,
    )
    print(f"   [OK] 创建成功: [{msg.role}] {msg.content[:20]}...")

    # 测试 JobCriteria 模型
    print("\n4. 测试 JobCriteria 模型...")
    criteria = JobCriteria(
        job_keywords=["Python", "后端"],
        salary_min=15,
        salary_max=30,
        locations=["北京", "上海"],
    )
    print(
        f"   [OK] 创建成功: 关键词={criteria.job_keywords}, "
        f"薪资范围={criteria.salary_min}-{criteria.salary_max}K"
    )

    # 测试 ApplicationRecord 模型
    print("\n5. 测试 ApplicationRecord 模型...")
    application = ApplicationRecord(
        record_id="app_001",
        job_info=job,
        match_score=85.5,
        match_reason="技能匹配度高，薪资符合预期",
        status="pending",
    )
    print(
        f"   [OK] 创建成功: 匹配度={application.match_score}, "
        f"状态={application.status}"
    )

    print("\n" + "=" * 60)
    print("[SUCCESS] 所有模型验证通过！")
    print("=" * 60)
