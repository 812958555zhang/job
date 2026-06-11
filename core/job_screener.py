"""
人岗匹配评分模块 - 实现岗位筛选与匹配评分功能

功能特性：
- 根据用户画像和岗位信息计算匹配度分数
- 支持多维度筛选（关键词、薪资、地点、经验、学历等）
- 提供详细的匹配/不匹配原因说明
- 支持配置筛选阈值和偏好设置
- 集成去重机制，自动跳过已投递岗位
"""

from typing import List, Optional, Tuple

from core.models import JobInfo, JobCriteria, UserProfile
from utils.config_loader import load_settings
from utils.logger import get_logger
from utils.db_helper import get_db


class JobScreener:
    """
    岗位筛选器类 - 负责岗位信息的匹配评分和筛选

    使用示例::

        >>> screener = JobScreener(user_profile)
        >>> match_result = screener.score(job_info)
        >>> if match_result['passed']:
        ...     print(f"匹配度: {match_result['score']}分")
        ... else:
        ...     print(f"不匹配原因: {match_result['reason']}")
    """

    def __init__(self, user_profile: UserProfile):
        """
        初始化岗位筛选器

        Args:
            user_profile: 用户画像对象，包含求职者的个人信息和职业背景
        """
        self._logger = get_logger(__name__)
        self._user_profile = user_profile
        # 加载求职标准配置
        try:
            self._criteria = self._load_criteria_from_config()
        except Exception as e:
            self._logger.warning(f"加载配置失败，使用默认筛选标准: {e}")
            self._criteria = JobCriteria(
                job_keywords=[""],
                salary_min=0,
                salary_max=100,
                locations=[""],
            )
        self._apply_user_profile()

    def _apply_user_profile(self) -> None:
        """用上传简历中的求职意向覆盖/补充配置，实现简历驱动匹配"""
        profile = self._user_profile

        if profile.expected_positions:
            self._criteria.job_keywords = list(
                dict.fromkeys(profile.expected_positions + self._criteria.job_keywords)
            )
        elif profile.current_position:
            self._criteria.job_keywords = list(
                dict.fromkeys([profile.current_position] + self._criteria.job_keywords)
            )

        if profile.skills:
            top_skills = [s for s in profile.skills[:6] if s]
            self._criteria.job_keywords = list(
                dict.fromkeys(self._criteria.job_keywords + top_skills)
            )

        if profile.expected_locations:
            self._criteria.locations = list(
                dict.fromkeys(profile.expected_locations + self._criteria.locations)
            )

        if profile.expected_salary_min is not None:
            self._criteria.salary_min = profile.expected_salary_min
        if profile.expected_salary_max is not None:
            self._criteria.salary_max = profile.expected_salary_max

        if profile.education:
            self._criteria.education = profile.education

        if profile.total_experience_years:
            self._criteria.experience_min_years = min(
                self._criteria.experience_min_years or 0,
                profile.total_experience_years,
            )

        self._logger.info(
            "简历驱动筛选标准 | 关键词: %s | 城市: %s | 薪资: %s-%sK | 学历: %s",
            ", ".join(k for k in self._criteria.job_keywords if k),
            ", ".join(c for c in self._criteria.locations if c) or "不限",
            self._criteria.salary_min,
            self._criteria.salary_max,
            self._criteria.education or "不限",
        )

    def add_search_city(self, city: str) -> None:
        """将 BOSS 搜索页当前城市加入匹配范围（如页面显示「广州[切换]」）"""
        city = (city or "").strip()
        if not city:
            return
        if city not in self._criteria.locations:
            self._criteria.locations.insert(0, city)
            self._logger.info("已根据搜索页自动加入工作城市: %s", city)

    def get_active_keywords(self) -> list:
        return [k for k in self._criteria.job_keywords if k]

    def get_active_locations(self) -> list:
        return [c for c in self._criteria.locations if c]

    def _load_criteria_from_config(self) -> JobCriteria:
        """
        从配置文件加载求职筛选标准

        Returns:
            JobCriteria: 已配置的筛选标准对象
        """
        config = load_settings()

        return JobCriteria(
            job_keywords=config.get("job_keywords", [""]),
            salary_min=config.get("salary_range", {}).get("min", 0),
            salary_max=config.get("salary_range", {}).get("max", 100),
            locations=config.get("locations", [""]),
            experience_min_years=config.get("experience_years", {}).get("min", 0),
            experience_max_years=config.get("experience_years", {}).get("max"),
            education=config.get("education"),
            company_size_preference=config.get("company_size_preference", []),
            industry_preference=config.get("industry_preference", []),
            blacklist_companies=config.get("blacklist_companies", []),
            blacklist_keywords=config.get("blacklist_keywords", []),
            match_score_threshold=config.get("match_score_threshold", 60.0),
        )

    def score(self, job_info: JobInfo, check_duplicate: bool = True) -> dict:
        """
        计算岗位匹配度分数

        综合考虑关键词匹配、薪资范围、地点、经验要求、学历要求等多个维度，
        计算岗位与用户画像的匹配程度。

        Args:
            job_info: 岗位信息对象
            check_duplicate: 是否检查重复投递（默认True）

        Returns:
            dict: 匹配结果字典，包含以下字段：
                - passed: bool - 是否通过筛选
                - score: float - 匹配度分数（0-100）
                - reason: str - 匹配/不匹配原因说明
                - breakdown: dict - 各维度得分明细
                - skip_type: str - 跳过类型（duplicate/blacklist/basic），仅在passed=False时存在
        """
        # 首先检查是否已投递（去重机制）
        if check_duplicate and job_info.job_id:
            duplicate_reason = self._check_duplicate(job_info)
            if duplicate_reason:
                return {
                    "passed": False,
                    "score": 0.0,
                    "reason": duplicate_reason,
                    "breakdown": {},
                    "skip_type": "duplicate",
                }

        # 检查黑名单
        blacklist_reason = self._check_blacklist(job_info)
        if blacklist_reason:
            return {
                "passed": False,
                "score": 0.0,
                "reason": blacklist_reason,
                "breakdown": {},
                "skip_type": "blacklist",
            }

        # 检查基础筛选条件
        basic_reason = self._check_basic_criteria(job_info)
        if basic_reason:
            return {
                "passed": False,
                "score": 0.0,
                "reason": basic_reason,
                "breakdown": {},
                "skip_type": "basic",
            }

        # 计算详细匹配分数
        score, breakdown = self._calculate_match_score(job_info)
        reason = self._generate_match_reason(job_info, score, breakdown)

        passed = score >= self._criteria.match_score_threshold

        return {
            "passed": passed,
            "score": score,
            "reason": reason,
            "breakdown": breakdown,
        }

    def _check_blacklist(self, job_info: JobInfo) -> Optional[str]:
        """
        检查岗位是否在黑名单中

        Args:
            job_info: 岗位信息对象

        Returns:
            str: 黑名单原因（如果命中），否则返回 None
        """
        # 检查公司黑名单
        company_name = job_info.company_name or ""
        for blacklist_company in self._criteria.blacklist_companies:
            if blacklist_company.lower() in company_name.lower():
                return f"公司 '{company_name}' 在黑名单中"

        # 检查关键词黑名单
        job_name = job_info.job_name or ""
        job_desc = job_info.job_description or ""
        for keyword in self._criteria.blacklist_keywords:
            if keyword.lower() in job_name.lower() or keyword.lower() in job_desc.lower():
                return f"岗位包含黑名单关键词 '{keyword}'"

        return None

    def _check_duplicate(self, job_info: JobInfo) -> Optional[str]:
        """
        检查岗位是否已被申请过（去重校验）

        通过查询数据库检查该岗位是否已存在投递记录，
        实现去重机制，避免重复投递同一岗位。

        Args:
            job_info: 岗位信息对象

        Returns:
            str: 重复投递原因（如果已投递），否则返回 None
        """
        if not job_info.job_id:
            return None

        try:
            db = get_db()
            if db.check_job_applied(job_info.job_id):
                return f"岗位 '{job_info.job_name}' 已投递过，跳过"
        except Exception as e:
            self._logger.warning(f"检查重复投递时出错: {e}")

        return None

    def _check_basic_criteria(self, job_info: JobInfo) -> Optional[str]:
        """
        检查基础筛选条件是否满足

        包括：薪资范围、地点、经验要求、学历要求等硬性条件。

        Args:
            job_info: 岗位信息对象

        Returns:
            str: 不满足条件的原因（如果不满足），否则返回 None
        """
        reasons = []

        # 检查薪资范围
        if job_info.salary_min is not None:
            if job_info.salary_min > self._criteria.salary_max:
                reasons.append(
                    f"岗位薪资下限({job_info.salary_min}K)高于期望上限({self._criteria.salary_max}K)"
                )
        if job_info.salary_max is not None:
            if job_info.salary_max < self._criteria.salary_min:
                reasons.append(
                    f"岗位薪资上限({job_info.salary_max}K)低于期望下限({self._criteria.salary_min}K)"
                )

        # 检查工作地点
        if self._criteria.locations and job_info.location:
            location_lower = job_info.location.lower()
            matched_location = any(
                loc.lower() in location_lower for loc in self._criteria.locations
            )
            if not matched_location:
                reasons.append(
                    f"工作地点 '{job_info.location}' 不在期望地点列表中"
                )

        # 检查经验要求
        exp_required = self._parse_experience(job_info.experience_required)
        if exp_required is not None:
            if exp_required > self._criteria.experience_max_years:
                reasons.append(
                    f"经验要求({exp_required}年)超出期望上限({self._criteria.experience_max_years}年)"
                )

        # 检查学历要求
        if self._criteria.education and job_info.education_required:
            education_order = ["不限", "高中", "专科", "本科", "硕士", "博士"]
            try:
                required_level = education_order.index(job_info.education_required)
                expect_level = education_order.index(self._criteria.education)
                if required_level > expect_level:
                    reasons.append(
                        f"学历要求({job_info.education_required})高于期望({self._criteria.education})"
                    )
            except ValueError:
                # 无法识别的学历值，跳过检查
                pass

        if reasons:
            return "; ".join(reasons)
        return None

    def _parse_experience(self, experience_str: Optional[str]) -> Optional[float]:
        """
        解析经验要求字符串为数字

        Args:
            experience_str: 经验要求字符串，如"3-5年"、"不限"、"应届"等

        Returns:
            float: 解析出的最低经验要求（年），无法解析返回 None
        """
        if not experience_str:
            return None

        experience_str = experience_str.strip()

        # 处理"不限"、"应届"等特殊情况
        if experience_str in ["不限", "应届生", "应届", "无经验"]:
            return 0.0

        # 提取数字
        import re

        # 匹配"3年"、"3-5年"、"3年以上"等格式
        match = re.search(r"(\d+)", experience_str)
        if match:
            return float(match.group(1))

        return None

    def _calculate_match_score(self, job_info: JobInfo) -> Tuple[float, dict]:
        """
        计算详细的匹配分数

        Args:
            job_info: 岗位信息对象

        Returns:
            tuple: (总分数, 各维度得分明细)
        """
        breakdown = {}

        # 1. 关键词匹配得分（权重30%）
        keyword_score = self._calculate_keyword_score(job_info)
        breakdown["keyword"] = {"score": keyword_score, "weight": 30}

        # 2. 技能匹配得分（权重30%）
        skill_score = self._calculate_skill_score(job_info)
        breakdown["skill"] = {"score": skill_score, "weight": 30}

        # 3. 经验匹配得分（权重20%）
        exp_score = self._calculate_experience_score(job_info)
        breakdown["experience"] = {"score": exp_score, "weight": 20}

        # 4. 学历匹配得分（权重10%）
        edu_score = self._calculate_education_score(job_info)
        breakdown["education"] = {"score": edu_score, "weight": 10}

        # 5. 薪资匹配得分（权重10%）
        salary_score = self._calculate_salary_score(job_info)
        breakdown["salary"] = {"score": salary_score, "weight": 10}

        # 计算加权总分
        total_score = sum(
            breakdown[key]["score"] * breakdown[key]["weight"] / 100
            for key in breakdown
        )

        return round(total_score, 1), breakdown

    def _calculate_keyword_score(self, job_info: JobInfo) -> float:
        """
        计算关键词匹配得分

        检查岗位名称和描述是否包含用户期望的岗位关键词。

        Args:
            job_info: 岗位信息对象

        Returns:
            float: 关键词匹配得分（0-100）
        """
        if not self._criteria.job_keywords or not job_info.job_name:
            return 50.0  # 默认中性分

        job_text = (job_info.job_name + " " + (job_info.job_description or "")).lower()
        matches = 0

        for keyword in self._criteria.job_keywords:
            if keyword.lower() in job_text:
                matches += 1

        return min(100.0, (matches / len(self._criteria.job_keywords)) * 100)

    def _calculate_skill_score(self, job_info: JobInfo) -> float:
        """
        计算技能匹配得分

        检查用户技能与岗位要求的匹配程度。

        Args:
            job_info: 岗位信息对象

        Returns:
            float: 技能匹配得分（0-100）
        """
        user_skills = set(s.lower() for s in self._user_profile.skills)
        if not user_skills:
            return 50.0  # 默认中性分

        # 从岗位描述中提取技能关键词
        job_text = (job_info.job_description or "") + " " + (job_info.job_name or "")
        job_text = job_text.lower()

        # 统计匹配的技能数
        matched_skills = [skill for skill in user_skills if skill in job_text]

        if not matched_skills:
            return 20.0  # 无匹配技能给低分

        return min(100.0, (len(matched_skills) / len(user_skills)) * 100)

    def _calculate_experience_score(self, job_info: JobInfo) -> float:
        """
        计算经验匹配得分

        比较用户工作年限与岗位经验要求。

        Args:
            job_info: 岗位信息对象

        Returns:
            float: 经验匹配得分（0-100）
        """
        user_exp = self._user_profile.total_experience_years
        job_exp = self._parse_experience(job_info.experience_required)

        if job_exp is None:
            return 70.0  # 无明确要求给中高分

        # 经验完全匹配得满分
        if user_exp >= job_exp:
            return 100.0

        # 经验不足按比例扣分
        ratio = user_exp / job_exp if job_exp > 0 else 0
        return max(30.0, ratio * 100)

    def _calculate_education_score(self, job_info: JobInfo) -> float:
        """
        计算学历匹配得分

        Args:
            job_info: 岗位信息对象

        Returns:
            float: 学历匹配得分（0-100）
        """
        education_order = ["不限", "高中", "专科", "本科", "硕士", "博士"]

        user_edu = self._user_profile.education or "不限"
        job_edu = job_info.education_required or "不限"

        try:
            user_level = education_order.index(user_edu)
            job_level = education_order.index(job_edu)

            if user_level >= job_level:
                return 100.0
            else:
                # 学历低于要求，按差距扣分
                gap = job_level - user_level
                return max(0.0, 100.0 - gap * 30)
        except ValueError:
            # 无法识别的学历值，给默认分
            return 70.0

    def _calculate_salary_score(self, job_info: JobInfo) -> float:
        """
        计算薪资匹配得分

        评估岗位薪资与用户期望薪资的匹配程度。

        Args:
            job_info: 岗位信息对象

        Returns:
            float: 薪资匹配得分（0-100）
        """
        user_min = self._user_profile.expected_salary_min or 0
        user_max = self._user_profile.expected_salary_max or 1000

        job_min = job_info.salary_min or 0
        job_max = job_info.salary_max or 0

        # 无薪资信息给中等分
        if job_min == 0 and job_max == 0:
            return 50.0

        # 计算岗位薪资范围与用户期望范围的重叠度
        job_mid = (job_min + job_max) / 2 if job_max > 0 else job_min

        if job_mid >= user_min and job_mid <= user_max:
            return 100.0
        elif job_mid < user_min:
            # 薪资低于期望
            ratio = job_mid / user_min if user_min > 0 else 0
            return max(20.0, ratio * 100)
        else:
            # 薪资高于期望（通常是好事）
            return 80.0

    def _generate_match_reason(self, job_info: JobInfo, score: float, breakdown: dict) -> str:
        """
        生成匹配原因说明

        Args:
            job_info: 岗位信息对象
            score: 匹配度分数
            breakdown: 各维度得分明细

        Returns:
            str: 匹配原因说明文本
        """
        reasons = []

        # 根据各维度得分生成原因
        if breakdown["keyword"]["score"] >= 80:
            reasons.append("岗位关键词高度匹配")
        elif breakdown["keyword"]["score"] >= 50:
            reasons.append("岗位关键词基本匹配")
        else:
            reasons.append("岗位关键词匹配度较低")

        if breakdown["skill"]["score"] >= 80:
            reasons.append("技能匹配度高")
        elif breakdown["skill"]["score"] >= 50:
            reasons.append("技能部分匹配")
        else:
            reasons.append("技能匹配度较低")

        if breakdown["experience"]["score"] >= 80:
            reasons.append("经验要求完全满足")
        elif breakdown["experience"]["score"] >= 50:
            reasons.append("经验基本符合要求")
        else:
            reasons.append("经验略有不足")

        if breakdown["salary"]["score"] >= 80:
            reasons.append("薪资符合期望")
        elif breakdown["salary"]["score"] >= 50:
            reasons.append("薪资基本匹配")
        else:
            reasons.append("薪资略低于期望")

        return "; ".join(reasons)


# 测试代码
if __name__ == "__main__":
    import sys
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

    print("=" * 60)
    print("JobScreener 模块自测试")
    print("=" * 60)

    # 创建测试数据
    test_profile = UserProfile(
        name="张三",
        education="本科",
        total_experience_years=5.0,
        skills=["Python", "Django", "MySQL", "Redis"],
        expected_positions=["后端开发工程师", "Python开发"],
        expected_salary_min=15,
        expected_salary_max=30,
    )

    test_job1 = JobInfo(
        job_id="job_001",
        job_name="Python后端开发工程师",
        company_name="示例科技有限公司",
        salary_min=20,
        salary_max=35,
        job_description="要求3-5年Python开发经验，熟悉Django框架，掌握MySQL数据库",
        experience_required="3-5年",
        education_required="本科",
        location="北京",
    )

    test_job2 = JobInfo(
        job_id="job_002",
        job_name="Java开发工程师",
        company_name="测试公司",
        salary_min=15,
        salary_max=25,
        job_description="要求5年以上Java开发经验，熟悉Spring Boot",
        experience_required="5年以上",
        education_required="本科",
        location="上海",
    )

    # 测试筛选器
    screener = JobScreener(test_profile)

    print("\n【测试1】匹配度评分（高匹配岗位）")
    result = screener.score(test_job1)
    print(f"   岗位: {test_job1.job_name}")
    print(f"   通过: {result['passed']}")
    print(f"   匹配度: {result['score']}分")
    print(f"   原因: {result['reason']}")
    print(f"   明细: {result['breakdown']}")

    print("\n【测试2】匹配度评分（低匹配岗位）")
    result = screener.score(test_job2)
    print(f"   岗位: {test_job2.job_name}")
    print(f"   通过: {result['passed']}")
    print(f"   匹配度: {result['score']}分")
    print(f"   原因: {result['reason']}")

    print("\n【测试3】黑名单检查")
    screener._criteria.blacklist_companies = ["测试公司"]
    result = screener.score(test_job2)
    print(f"   岗位: {test_job2.job_name}")
    print(f"   通过: {result['passed']}")
    print(f"   原因: {result['reason']}")

    print("\n【测试4】经验解析")
    test_cases = ["3-5年", "不限", "应届", "10年以上", "2年"]
    for tc in test_cases:
        parsed = screener._parse_experience(tc)
        print(f"   '{tc}' -> {parsed}年")

    print("\n" + "=" * 60)
    print("✓ 所有测试通过！")
    print("=" * 60)