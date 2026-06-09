"""
用户画像管理模块

提供用户画像的完整生命周期管理，包括：
- 用户画像的创建、读取、更新、删除（CRUD）
- 画像数据与数据库的持久化存储
- JSON格式的导入/导出
- 用户画像与Pydantic模型的转换

依赖：
- DatabaseHelper: SQLite数据库操作封装
- UserProfile: 用户画像数据模型
- get_logger: 日志记录工具
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

from core.models import UserProfile
from utils.db_helper import get_db
from utils.logger import get_logger

# 获取日志记录器
logger = get_logger(__name__)


class ProfileManager:
    """
    用户画像管理器类

    负责用户画像的完整生命周期管理：
    1. 数据库CRUD操作封装
    2. Pydantic模型与数据库数据的双向转换
    3. JSON文件导入/导出
    4. 活跃画像的管理
    """

    def __init__(self):
        """初始化用户画像管理器"""
        self.db = get_db()

    def create_profile(self, profile_data: Dict[str, Any]) -> Optional[int]:
        """
        创建新的用户画像

        Args:
            profile_data: 用户画像数据字典，需符合 UserProfile 模型字段

        Returns:
            新创建画像的ID，失败返回 None

        Raises:
            ValidationError: 数据验证失败时抛出
            Exception: 数据库操作失败时抛出
        """
        # 使用Pydantic验证数据
        try:
            profile = UserProfile(**profile_data)
        except ValidationError as e:
            logger.error(f"用户画像数据验证失败: {e}")
            raise

        # 转换为数据库存储格式（移除None值字段）
        db_data = profile.model_dump(exclude_none=True)

        # 移除Pydantic内部字段和不需要存储的字段
        db_data.pop('created_at', None)
        db_data.pop('updated_at', None)

        try:
            profile_id = self.db.create_profile(db_data)
            logger.info(f"用户画像创建成功, ID={profile_id}")
            return profile_id
        except Exception as e:
            logger.error(f"创建用户画像失败: {e}")
            raise

    def get_profile(self, profile_id: int = 1) -> Optional[UserProfile]:
        """
        获取指定ID的用户画像

        默认获取ID=1的活跃画像（系统默认画像）

        Args:
            profile_id: 画像主键ID

        Returns:
            UserProfile对象，如果不存在则返回 None
        """
        try:
            data = self.db.get_profile(profile_id)
            if data is None:
                logger.warning(f"用户画像不存在, ID={profile_id}")
                return None

            # 将数据库数据转换为UserProfile对象
            return UserProfile(**data)
        except Exception as e:
            logger.error(f"获取用户画像失败, ID={profile_id}: {e}")
            return None

    def get_active_profile(self) -> Optional[UserProfile]:
        """
        获取当前活跃的用户画像

        返回is_active=1的第一条记录，如果没有活跃画像则返回None

        Returns:
            UserProfile对象，如果不存在活跃画像则返回 None
        """
        try:
            profiles = self.db.list_profiles()
            for profile_data in profiles:
                if profile_data.get('is_active', 1) == 1:
                    return UserProfile(**profile_data)
            logger.warning("未找到活跃的用户画像")
            return None
        except Exception as e:
            logger.error(f"获取活跃用户画像失败: {e}")
            return None

    def update_profile(self, profile_id: int, profile_data: Dict[str, Any]) -> bool:
        """
        更新用户画像信息

        Args:
            profile_id: 画像主键ID
            profile_data: 需要更新的字段字典

        Returns:
            更新成功返回 True，失败返回 False
        """
        # 使用Pydantic验证数据（创建临时对象进行验证）
        if 'name' in profile_data or 'education' in profile_data:
            # 如果更新必填字段，需要完整验证
            try:
                existing = self.get_profile(profile_id)
                if existing is None:
                    logger.warning(f"用户画像不存在, ID={profile_id}")
                    return False

                # 合并现有数据和更新数据进行验证
                merged_data = existing.model_dump()
                merged_data.update(profile_data)
                UserProfile(**merged_data)
            except ValidationError as e:
                logger.error(f"用户画像数据验证失败: {e}")
                return False

        # 移除不需要更新的字段
        profile_data.pop('id', None)
        profile_data.pop('created_at', None)
        profile_data.pop('updated_at', None)

        try:
            success = self.db.update_profile(profile_id, profile_data)
            if success:
                logger.info(f"用户画像更新成功, ID={profile_id}")
            else:
                logger.warning(f"用户画像不存在或未修改, ID={profile_id}")
            return success
        except Exception as e:
            logger.error(f"更新用户画像失败, ID={profile_id}: {e}")
            return False

    def delete_profile(self, profile_id: int) -> bool:
        """
        删除指定用户画像

        Args:
            profile_id: 画像主键ID

        Returns:
            删除成功返回 True，失败返回 False
        """
        try:
            success = self.db.delete_profile(profile_id)
            if success:
                logger.info(f"用户画像删除成功, ID={profile_id}")
            else:
                logger.warning(f"用户画像不存在, ID={profile_id}")
            return success
        except Exception as e:
            logger.error(f"删除用户画像失败, ID={profile_id}: {e}")
            return False

    def list_profiles(self) -> List[UserProfile]:
        """
        获取所有用户画像列表

        Returns:
            UserProfile对象列表，按创建时间倒序排列
        """
        try:
            data_list = self.db.list_profiles()
            profiles = []
            for data in data_list:
                try:
                    profiles.append(UserProfile(**data))
                except ValidationError as e:
                    logger.error(f"用户画像数据转换失败: {e}")
            return profiles
        except Exception as e:
            logger.error(f"获取用户画像列表失败: {e}")
            return []

    def set_active_profile(self, profile_id: int) -> bool:
        """
        设置指定画像为活跃状态

        将指定画像设置为活跃状态，并将其他画像设置为非活跃状态

        Args:
            profile_id: 要设为活跃的画像ID

        Returns:
            设置成功返回 True，失败返回 False
        """
        try:
            # 获取所有画像
            profiles = self.db.list_profiles()

            # 将所有画像设为非活跃
            for profile in profiles:
                self.db.update_profile(profile['id'], {'is_active': 0})

            # 将指定画像设为活跃
            success = self.db.update_profile(profile_id, {'is_active': 1})
            if success:
                logger.info(f"已设置活跃用户画像, ID={profile_id}")
            return success
        except Exception as e:
            logger.error(f"设置活跃用户画像失败: {e}")
            return False

    def export_profile(self, profile_id: int, file_path: str) -> bool:
        """
        将用户画像导出为JSON文件

        Args:
            profile_id: 要导出的画像ID
            file_path: 导出文件路径

        Returns:
            导出成功返回 True，失败返回 False
        """
        try:
            profile = self.get_profile(profile_id)
            if profile is None:
                logger.warning(f"用户画像不存在, ID={profile_id}")
                return False

            # 确保目录存在
            output_path = Path(file_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # 导出为JSON格式
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(profile.model_dump(), f, ensure_ascii=False, indent=2)

            logger.info(f"用户画像导出成功, ID={profile_id}, 文件={file_path}")
            return True
        except Exception as e:
            logger.error(f"导出用户画像失败, ID={profile_id}: {e}")
            return False

    def import_profile(self, file_path: str) -> Optional[int]:
        """
        从JSON文件导入用户画像

        Args:
            file_path: JSON文件路径

        Returns:
            新创建画像的ID，失败返回 None
        """
        try:
            # 读取JSON文件
            with open(file_path, 'r', encoding='utf-8') as f:
                profile_data = json.load(f)

            # 使用Pydantic验证数据
            profile = UserProfile(**profile_data)

            # 创建新画像（不包含原有ID）
            create_data = profile.model_dump(exclude={'id', 'created_at', 'updated_at'})
            profile_id = self.create_profile(create_data)

            logger.info(f"用户画像导入成功, 文件={file_path}, 新ID={profile_id}")
            return profile_id
        except FileNotFoundError:
            logger.error(f"导入文件不存在: {file_path}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"JSON文件解析失败: {e}")
            return None
        except ValidationError as e:
            logger.error(f"用户画像数据验证失败: {e}")
            return None
        except Exception as e:
            logger.error(f"导入用户画像失败: {e}")
            return None

    def create_from_resume(self, resume_content: Dict[str, Any]) -> Optional[int]:
        """
        从简历解析结果创建用户画像

        Args:
            resume_content: 简历解析结果字典

        Returns:
            新创建画像的ID，失败返回 None
        """
        # 映射简历字段到用户画像字段
        profile_data = {
            'name': resume_content.get('name', ''),
            'phone': resume_content.get('phone'),
            'email': resume_content.get('email'),
            'education': resume_content.get('education', ''),
            'major': resume_content.get('major'),
            'school': resume_content.get('school'),
            'total_experience_years': resume_content.get('experience_years', 0.0),
            'current_position': resume_content.get('current_position'),
            'current_company': resume_content.get('current_company'),
            'skills': resume_content.get('skills', []),
            'core_competencies': resume_content.get('core_competencies', []),
            'projects': resume_content.get('projects', []),
            'expected_positions': resume_content.get('expected_positions', []),
            'expected_salary_min': resume_content.get('expected_salary_min'),
            'expected_salary_max': resume_content.get('expected_salary_max'),
            'expected_locations': resume_content.get('expected_locations', []),
            'resume_file_path': resume_content.get('resume_file_path'),
        }

        # 确保必填字段有值
        if not profile_data['name']:
            profile_data['name'] = '未命名用户'
        if not profile_data['education']:
            profile_data['education'] = '不限'

        return self.create_profile(profile_data)

    def has_profile(self) -> bool:
        """
        检查是否存在用户画像

        Returns:
            存在至少一个画像返回 True，否则返回 False
        """
        try:
            profiles = self.list_profiles()
            return len(profiles) > 0
        except Exception as e:
            logger.error(f"检查用户画像存在性失败: {e}")
            return False


# ==================== 全局单例访问接口 ====================

_profile_manager_instance: Optional[ProfileManager] = None


def get_profile_manager() -> ProfileManager:
    """
    获取全局用户画像管理器实例（单例模式）

    整个应用生命周期内共享同一个 ProfileManager 实例

    Returns:
        ProfileManager 全局唯一实例
    """
    global _profile_manager_instance
    if _profile_manager_instance is None:
        _profile_manager_instance = ProfileManager()
    return _profile_manager_instance


# ==================== 测试代码 ====================

if __name__ == "__main__":
    # 设置控制台输出编码为UTF-8
    import sys
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

    print("=" * 60)
    print("ProfileManager 模块测试")
    print("=" * 60)

    # 创建管理器实例
    manager = get_profile_manager()

    # 测试1: 创建用户画像
    print("\n1. 测试创建用户画像...")
    test_profile_data = {
        'name': '张三',
        'education': '本科',
        'total_experience_years': 5.0,
        'skills': ['Python', 'Django', 'MySQL', 'Redis'],
        'core_competencies': ['系统架构设计', '性能优化', '团队管理'],
        'projects': [
            {
                'name': '电商平台后端系统',
                'role': '技术负责人',
                'description': '负责系统架构设计和核心模块开发'
            }
        ],
        'expected_positions': ['Python后端开发工程师', '技术主管'],
        'expected_salary_min': 25,
        'expected_salary_max': 40,
        'expected_locations': ['北京', '上海'],
    }
    try:
        profile_id = manager.create_profile(test_profile_data)
        print(f"   [OK] 创建成功, ID={profile_id}")
    except Exception as e:
        print(f"   [FAIL] 创建失败: {e}")
        profile_id = None

    # 测试2: 获取用户画像
    print("\n2. 测试获取用户画像...")
    if profile_id:
        profile = manager.get_profile(profile_id)
        if profile:
            print(f"   [OK] 获取成功: {profile.name}, {profile.education}, {profile.total_experience_years}年经验")
        else:
            print(f"   [FAIL] 获取失败")

    # 测试3: 更新用户画像
    print("\n3. 测试更新用户画像...")
    if profile_id:
        update_data = {
            'phone': '13800138000',
            'email': 'zhangsan@example.com',
            'current_position': '高级工程师',
            'current_company': '某科技公司'
        }
        success = manager.update_profile(profile_id, update_data)
        if success:
            # 验证更新结果
            updated_profile = manager.get_profile(profile_id)
            if updated_profile and updated_profile.phone == '13800138000':
                print(f"   [OK] 更新成功")
            else:
                print(f"   [FAIL] 更新后验证失败")
        else:
            print(f"   [FAIL] 更新失败")

    # 测试4: 获取活跃画像
    print("\n4. 测试获取活跃画像...")
    active_profile = manager.get_active_profile()
    if active_profile:
        print(f"   [OK] 获取成功: {active_profile.name}")
    else:
        print(f"   [WARN] 未找到活跃画像")

    # 测试5: 列出所有画像
    print("\n5. 测试列出所有画像...")
    profiles = manager.list_profiles()
    print(f"   [OK] 共 {len(profiles)} 个画像")
    for p in profiles:
        print(f"        - {p.name} ({p.created_at.strftime('%Y-%m-%d')})")

    # 测试6: 导出画像
    print("\n6. 测试导出用户画像...")
    if profile_id:
        export_path = f"data/profiles/test_profile_{profile_id}.json"
        success = manager.export_profile(profile_id, export_path)
        if success:
            print(f"   [OK] 导出成功: {export_path}")
        else:
            print(f"   [FAIL] 导出失败")

    # 测试7: 导入画像
    print("\n7. 测试导入用户画像...")
    import_path = f"data/profiles/test_profile_{profile_id}.json" if profile_id else ""
    if import_path and Path(import_path).exists():
        new_id = manager.import_profile(import_path)
        if new_id:
            print(f"   [OK] 导入成功, 新ID={new_id}")
        else:
            print(f"   [FAIL] 导入失败")

    # 测试8: 检查是否存在画像
    print("\n8. 测试检查画像存在性...")
    has_profile = manager.has_profile()
    print(f"   [OK] 存在用户画像: {has_profile}")

    print("\n" + "=" * 60)
    print("[SUCCESS] ProfileManager 模块测试完成！")
    print("=" * 60)