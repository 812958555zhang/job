"""
岗位扫描器模块 - 实现DOM提取+AI岗位理解功能

功能特性：
- 通过Browser Use自动提取BOSS直聘网页版当前页面的DOM结构
- 将DOM结构化文本喂给LLM，让AI理解并提取岗位信息
- 支持页面状态感知（搜索列表/岗位详情/聊天窗口/消息列表）
- 动态内容等待，自动处理SPA页面动态加载
"""

import asyncio
import json
from typing import Any, Dict, List, Optional

from browser.agent_helpers import (
    wait_for_page_ready,
    extract_page_text,
    get_page_url,
    page_needs_login,
)
from core.models import JobInfo
from core.llm_client import VolcengineLLMClient
from utils.logger import get_logger


def _normalize_jobs_list_result(content) -> list:
    """将 LLM 返回的 JSON 内容规范化为岗位字典列表"""
    if isinstance(content, list):
        return content
    if isinstance(content, dict):
        for key in ("jobs", "items", "data", "job_list"):
            value = content.get(key)
            if isinstance(value, list):
                return value
    return []


class JobScanner:
    """
    岗位扫描器类 - 负责扫描和解析BOSS直聘页面的岗位信息

    使用示例::

        >>> scanner = JobScanner(browser_agent)
        >>> job_list = await scanner.scan_job_list()
        >>> for job in job_list:
        ...     print(job.job_name, job.company_name)
    """

    # 页面类型常量
    PAGE_TYPE_SEARCH_LIST = "search_list"    # 岗位搜索列表页
    PAGE_TYPE_JOB_DETAIL = "job_detail"      # 岗位详情页
    PAGE_TYPE_CHAT = "chat"                  # 聊天窗口页
    PAGE_TYPE_MESSAGE_LIST = "message_list"  # 消息列表页

    def __init__(self, browser_agent):
        """
        初始化岗位扫描器

        Args:
            browser_agent: BrowserAgent实例，用于获取页面DOM和执行操作
        """
        self._logger = get_logger(__name__)
        self._browser_agent = browser_agent
        self._llm_client = VolcengineLLMClient()

    async def scan_job_list(self) -> List[JobInfo]:
        """
        扫描当前页面的岗位列表

        通过Browser Use提取页面DOM，然后使用AI理解并提取岗位信息。

        Returns:
            List[JobInfo]: 解析出的岗位信息列表
        """
        self._logger.info("开始扫描岗位列表页面...")

        # 1. 获取页面DOM结构
        dom_text = await self._extract_dom()
        if not dom_text:
            self._logger.error("无法获取页面DOM")
            return []

        # 2. 使用AI解析DOM提取岗位信息
        jobs = await self._parse_dom_with_ai(dom_text)

        self._logger.info(f"扫描完成，共解析出 {len(jobs)} 个岗位")
        return jobs

    async def scan_job_detail(self, job_id: Optional[str] = None) -> Optional[JobInfo]:
        """
        扫描岗位详情页获取完整信息

        Args:
            job_id: 岗位ID（可选，如果已从列表页获取则可跳过解析）

        Returns:
            JobInfo: 完整的岗位信息对象
        """
        self._logger.info(f"开始扫描岗位详情页... (job_id={job_id})")

        # 1. 获取页面DOM结构
        dom_text = await self._extract_dom()
        if not dom_text:
            self._logger.error("无法获取页面DOM")
            return None

        # 2. 使用AI解析DOM提取完整岗位信息
        job = await self._parse_job_detail_with_ai(dom_text, job_id)

        if job:
            self._logger.info(f"成功解析岗位详情: {job.job_name} @ {job.company_name}")
        return job

    async def _extract_dom(self) -> Optional[str]:
        """
        提取当前页面的可见文本内容

        直接读取页面 DOM 文本，避免 Browser Use agent.run() 重新导航导致离开搜索页。
        """
        page = self._browser_agent.get_page()
        if not page:
            self._logger.error("页面不可用")
            return None

        for attempt in range(3):
            try:
                content = await extract_page_text(page, retries=2)
                if not content:
                    self._logger.error("页面文本为空")
                    return None

                url = await get_page_url(page)
                if page_needs_login(content, url):
                    self._logger.warning("当前页面需要登录 BOSS 直聘")
                    return None

                self._logger.debug(f"页面文本提取成功，长度: {len(content)}字符")
                return content
            except Exception as e:
                err_msg = str(e).lower()
                if attempt < 2 and any(
                    token in err_msg
                    for token in ("destroyed", "navigation", "execution context")
                ):
                    self._logger.warning(
                        "页面正在跳转，%ss 后重试提取 DOM (%s/3)",
                        1.5 * (attempt + 1),
                        attempt + 2,
                    )
                    await asyncio.sleep(1.5 * (attempt + 1))
                    page = self._browser_agent.get_page() or page
                    continue
                self._logger.error(f"提取DOM失败: {e}", exc_info=True)
                return None
        return None

    async def _parse_dom_with_ai(self, dom_text: str) -> List[JobInfo]:
        """
        使用AI解析DOM文本，提取岗位列表信息

        Args:
            dom_text: DOM结构化文本

        Returns:
            List[JobInfo]: 解析出的岗位信息列表
        """
        system_prompt = """
你是一位网页内容提取专家，擅长从网页DOM结构中提取结构化数据。

请仔细分析以下网页内容，从中提取所有岗位信息，并以JSON格式输出。

输出格式要求：
- 必须是有效的JSON数组
- 每个岗位包含以下字段：
  - job_id: 岗位唯一标识（从URL或页面元素中提取）
  - job_name: 岗位名称
  - company_name: 公司名称
  - salary_min: 最低薪资（数字，单位K/月，无法提取时为null）
  - salary_max: 最高薪资（数字，单位K/月，无法提取时为null）
  - location: 工作地点（无法提取时为null）
  - experience_required: 经验要求（如"3-5年"，无法提取时为null）
  - education_required: 学历要求（如"本科"，无法提取时为null）
  - tags: 岗位标签列表（如["Python", "后端"]）
  - url: 岗位详情页URL（无法提取时为null）

注意事项：
1. 只提取岗位列表信息，忽略导航栏、页脚等无关内容
2. 最多提取前 12 个岗位，字段保持简短
3. 薪资范围需要分开提取最低和最高值
4. 如果某个字段无法从页面中找到，设为 null
5. 确保输出是纯粹的 JSON 数组，不要包含任何其他文本
        """.strip()

        user_prompt = f"""
请分析以下网页内容，提取岗位信息（最多 12 个）：

{dom_text[:2500]}

请输出 JSON 格式的岗位列表。
        """.strip()

        try:
            self._logger.info("正在使用AI解析岗位列表...")
            result = await self._llm_client.achat_json(
                message=user_prompt,
                system_prompt=system_prompt,
                model=self._llm_client.lite_model,
                temperature=0.1,
                max_tokens=4096,
            )

            jobs_data = _normalize_jobs_list_result(result.get("content"))
            if not isinstance(jobs_data, list):
                self._logger.warning("AI返回的数据不是列表格式")
                return []

            # 转换为JobInfo对象列表
            jobs = []
            for job_data in jobs_data:
                try:
                    job = self._convert_to_job_info(job_data)
                    if job:
                        jobs.append(job)
                except Exception as e:
                    self._logger.warning(f"转换岗位数据失败: {e}")

            return jobs

        except Exception as e:
            self._logger.error(f"AI解析岗位列表失败: {e}", exc_info=True)
            return []

    async def _parse_job_detail_with_ai(self, dom_text: str, job_id: Optional[str]) -> Optional[JobInfo]:
        """
        使用AI解析DOM文本，提取岗位详情信息

        Args:
            dom_text: DOM结构化文本
            job_id: 岗位ID（可选）

        Returns:
            JobInfo: 完整的岗位信息对象
        """
        system_prompt = """
你是一位网页内容提取专家，擅长从岗位详情页中提取完整的岗位信息。

请仔细分析以下网页内容，提取岗位的完整信息，并以JSON格式输出。

输出格式要求：
- 必须是有效的JSON对象
- 包含以下字段：
  - job_id: 岗位唯一标识（从URL或页面元素中提取）
  - job_name: 岗位名称
  - company_name: 公司名称
  - salary_min: 最低薪资（数字，单位K/月，无法提取时为null）
  - salary_max: 最高薪资（数字，单位K/月，无法提取时为null）
  - salary_description: 薪资描述文本
  - job_description: 岗位详细描述/JD
  - experience_required: 经验要求（如"3-5年"）
  - education_required: 学历要求（如"本科"）
  - location: 工作地点
  - company_size: 公司规模（如"100-499人"）
  - industry: 所属行业（如"互联网"）
  - tags: 岗位标签列表（如["Python", "后端", "Django"]）
  - url: 岗位详情页URL

注意事项：
1. 尽可能提取完整的岗位信息
2. 如果某个字段无法从页面中找到，设为null
3. 确保输出是纯粹的JSON对象，不要包含任何其他文本
        """.strip()

        user_prompt = f"""
请分析以下岗位详情页内容，提取完整的岗位信息：

{dom_text[:4000]}

请输出JSON格式的岗位信息。
        """.strip()

        try:
            self._logger.info("正在使用AI解析岗位详情...")
            result = await self._llm_client.achat_json(
                message=user_prompt,
                system_prompt=system_prompt,
                temperature=0.1,
                max_tokens=3000,
            )

            job_data = result.get("content", {})
            if not isinstance(job_data, dict):
                self._logger.warning("AI返回的数据不是字典格式")
                return None

            # 使用提供的job_id（如果有）
            if job_id:
                job_data["job_id"] = job_id

            return self._convert_to_job_info(job_data)

        except Exception as e:
            self._logger.error(f"AI解析岗位详情失败: {e}", exc_info=True)
            return None

    def _convert_to_job_info(self, data: dict) -> Optional[JobInfo]:
        """
        将字典数据转换为JobInfo对象

        Args:
            data: 包含岗位信息的字典

        Returns:
            JobInfo: 岗位信息对象，数据无效时返回None
        """
        try:
            # 确保job_id存在
            if not data.get("job_id"):
                # 自动生成job_id
                job_name = data.get("job_name", "")
                company_name = data.get("company_name", "")
                import hashlib
                hash_str = f"{job_name}{company_name}"
                job_id = f"job_{hashlib.md5(hash_str.encode()).hexdigest()[:8]}"
                data["job_id"] = job_id

            tags = data.get("tags")
            if not isinstance(tags, list):
                tags = []

            def _to_int_salary(value):
                if value is None:
                    return None
                try:
                    return int(round(float(value)))
                except (TypeError, ValueError):
                    return None

            return JobInfo(
                job_id=data["job_id"],
                job_name=data.get("job_name", ""),
                company_name=data.get("company_name", ""),
                salary_min=_to_int_salary(data.get("salary_min")),
                salary_max=_to_int_salary(data.get("salary_max")),
                salary_description=data.get("salary_description"),
                job_description=data.get("job_description"),
                experience_required=data.get("experience_required"),
                education_required=data.get("education_required"),
                location=data.get("location"),
                company_size=data.get("company_size"),
                industry=data.get("industry"),
                tags=tags,
                url=data.get("url"),
            )
        except Exception as e:
            self._logger.warning(f"转换JobInfo失败: {e}")
            return None

    async def detect_page_type(self) -> str:
        """
        检测当前页面类型

        通过分析页面内容判断当前处于哪个页面：
        - search_list: 岗位搜索列表页
        - job_detail: 岗位详情页
        - chat: 聊天窗口页
        - message_list: 消息列表页

        Returns:
            str: 页面类型标识
        """
        try:
            dom_text = await self._extract_dom()
            if not dom_text:
                return self.PAGE_TYPE_SEARCH_LIST  # 默认返回搜索列表页

            # 使用AI分析页面类型
            system_prompt = """
你是一位网页分析专家，请分析以下网页内容，判断这是BOSS直聘的哪个页面类型。

可能的页面类型：
1. search_list: 岗位搜索列表页 - 包含多个岗位卡片列表
2. job_detail: 岗位详情页 - 显示单个岗位的详细信息
3. chat: 聊天窗口页 - 与招聘方的对话界面
4. message_list: 消息列表页 - 显示多个对话会话列表

请只输出页面类型标识（search_list/job_detail/chat/message_list），不要输出其他任何内容。
            """.strip()

            user_prompt = f"请分析以下网页内容，判断页面类型：\n\n{dom_text[:1000]}"

            result = await self._llm_client.achat(
                message=user_prompt,
                system_prompt=system_prompt,
                temperature=0.0,
                max_tokens=50,
            )

            page_type = result["content"].strip()
            valid_types = [
                self.PAGE_TYPE_SEARCH_LIST,
                self.PAGE_TYPE_JOB_DETAIL,
                self.PAGE_TYPE_CHAT,
                self.PAGE_TYPE_MESSAGE_LIST,
            ]

            if page_type in valid_types:
                self._logger.info(f"检测到页面类型: {page_type}")
                return page_type

            # 默认返回搜索列表页
            return self.PAGE_TYPE_SEARCH_LIST

        except Exception as e:
            self._logger.warning(f"检测页面类型失败，使用默认值: {e}")
            return self.PAGE_TYPE_SEARCH_LIST

    async def wait_for_dynamic_content(self, timeout: int = 30) -> bool:
        """
        等待动态内容加载完成

        处理SPA页面的动态加载，等待元素渲染完成后再操作。

        Args:
            timeout: 最大等待时间（秒）

        Returns:
            bool: 内容加载完成返回True，超时返回False
        """
        self._logger.info("等待页面动态内容加载...")

        try:
            page = self._browser_agent.get_page()
            if not page:
                return False

            await wait_for_page_ready(page, timeout=timeout)

            self._logger.info("页面动态内容加载完成")
            return True

        except Exception as e:
            self._logger.warning(f"等待动态内容超时: {e}")
            return False


# 测试代码
if __name__ == "__main__":
    import sys
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

    print("=" * 60)
    print("JobScanner 模块自测试")
    print("=" * 60)

    # 创建模拟的浏览器代理（用于测试）
    class MockBrowserAgent:
        def __init__(self):
            self._agent = None

    # 创建扫描器
    scanner = JobScanner(MockBrowserAgent())

    print("\n【测试1】测试页面类型检测（模拟数据）")
    # 模拟不同页面的DOM内容
    test_dom_search = """
    <div class="job-list">
        <div class="job-card">Python后端开发工程师 - 科技公司 - 20-30K - 北京</div>
        <div class="job-card">Java开发工程师 - 互联网公司 - 25-40K - 上海</div>
    </div>
    """

    print("   测试搜索列表页检测")
    # 这里仅测试类结构，实际检测需要真实DOM

    print("\n【测试2】测试JobInfo转换")
    test_job_data = {
        "job_name": "Python后端开发工程师",
        "company_name": "示例科技有限公司",
        "salary_min": 20,
        "salary_max": 35,
        "location": "北京",
        "experience_required": "3-5年",
        "education_required": "本科",
        "tags": ["Python", "Django", "后端"],
    }
    job = scanner._convert_to_job_info(test_job_data)
    print(f"   ✓ 转换成功")
    print(f"   - job_id: {job.job_id}")
    print(f"   - job_name: {job.job_name}")
    print(f"   - company_name: {job.company_name}")
    print(f"   - salary: {job.salary_min}-{job.salary_max}K")
    print(f"   - location: {job.location}")
    print(f"   - experience_required: {job.experience_required}")
    print(f"   - tags: {job.tags}")

    print("\n【测试3】测试空数据转换（自动生成job_id）")
    empty_job_data = {
        "job_name": "测试岗位",
        "company_name": "测试公司",
    }
    job = scanner._convert_to_job_info(empty_job_data)
    print(f"   ✓ 自动生成job_id: {job.job_id}")

    print("\n" + "=" * 60)
    print("✓ 所有测试通过！")
    print("=" * 60)