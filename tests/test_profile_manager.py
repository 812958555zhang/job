"""
ProfileManager 模块测试

测试用户画像管理模块的核心功能：
- 创建用户画像
- 获取用户画像
- 更新用户画像
- 删除用户画像
- 导入/导出功能
"""

import os
import sys
import json
from pathlib import Path

# 添加项目路径到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.profile_manager import ProfileManager, get_profile_manager
from core.models import UserProfile


class TestProfileManager:
    """ProfileManager 测试类"""

    def __init__(self):
        self.manager = get_profile_manager()
        self.test_profile_id = None

    def test_create_profile(self):
        """测试创建用户画像"""
        print("\n1. 测试创建用户画像...")
        profile_data = {
            'name': '测试用户',
            'education': '本科',
            'total_experience_years': 3.0,
            'skills': ['Python', 'Django', 'SQL'],
            'expected_positions': ['后端开发工程师'],
        }
        try:
            profile_id = self.manager.create_profile(profile_data)
            self.test_profile_id = profile_id
            print(f"   [OK] 创建成功, ID={profile_id}")
            return True
        except Exception as e:
            print(f"   [FAIL] 创建失败: {e}")
            return False

    def test_get_profile(self):
        """测试获取用户画像"""
        print("\n2. 测试获取用户画像...")
        if not self.test_profile_id:
            print("   [SKIP] 请先创建用户画像")
            return True

        try:
            profile = self.manager.get_profile(self.test_profile_id)
            if profile and isinstance(profile, UserProfile):
                print(f"   [OK] 获取成功: {profile.name}, {profile.education}")
                return True
            else:
                print("   [FAIL] 获取失败")
                return False
        except Exception as e:
            print(f"   [FAIL] 获取失败: {e}")
            return False

    def test_update_profile(self):
        """测试更新用户画像"""
        print("\n3. 测试更新用户画像...")
        if not self.test_profile_id:
            print("   [SKIP] 请先创建用户画像")
            return True

        try:
            update_data = {
                'phone': '13900139000',
                'email': 'test@example.com',
                'current_position': '软件工程师'
            }
            success = self.manager.update_profile(self.test_profile_id, update_data)
            if success:
                # 验证更新结果
                updated_profile = self.manager.get_profile(self.test_profile_id)
                if updated_profile and updated_profile.phone == '13900139000':
                    print("   [OK] 更新成功")
                    return True
                else:
                    print("   [FAIL] 更新后验证失败")
                    return False
            else:
                print("   [FAIL] 更新失败")
                return False
        except Exception as e:
            print(f"   [FAIL] 更新失败: {e}")
            return False

    def test_list_profiles(self):
        """测试获取用户画像列表"""
        print("\n4. 测试获取用户画像列表...")
        try:
            profiles = self.manager.list_profiles()
            print(f"   [OK] 共 {len(profiles)} 个画像")
            for p in profiles:
                print(f"        - {p.name}")
            return True
        except Exception as e:
            print(f"   [FAIL] 获取列表失败: {e}")
            return False

    def test_export_import_profile(self):
        """测试导出和导入用户画像"""
        print("\n5. 测试导出和导入用户画像...")
        if not self.test_profile_id:
            print("   [SKIP] 请先创建用户画像")
            return True

        export_path = "data/profiles/test_export.json"
        try:
            # 导出画像
            export_success = self.manager.export_profile(self.test_profile_id, export_path)
            if not export_success:
                print("   [FAIL] 导出失败")
                return False

            # 验证导出文件
            if Path(export_path).exists():
                print(f"   [OK] 导出成功: {export_path}")
            else:
                print("   [FAIL] 导出文件不存在")
                return False

            # 导入画像
            new_id = self.manager.import_profile(export_path)
            if new_id:
                print(f"   [OK] 导入成功, 新ID={new_id}")
                # 清理导入的测试数据
                self.manager.delete_profile(new_id)
                return True
            else:
                print("   [FAIL] 导入失败")
                return False
        except Exception as e:
            print(f"   [FAIL] 导出/导入失败: {e}")
            return False
        finally:
            # 清理导出文件
            if Path(export_path).exists():
                os.remove(export_path)

    def test_get_active_profile(self):
        """测试获取活跃用户画像"""
        print("\n6. 测试获取活跃用户画像...")
        try:
            profile = self.manager.get_active_profile()
            if profile:
                print(f"   [OK] 获取成功: {profile.name}")
                return True
            else:
                print("   [WARN] 未找到活跃画像")
                return True
        except Exception as e:
            print(f"   [FAIL] 获取失败: {e}")
            return False

    def test_has_profile(self):
        """测试检查画像存在性"""
        print("\n7. 测试检查画像存在性...")
        try:
            has_profile = self.manager.has_profile()
            print(f"   [OK] 存在用户画像: {has_profile}")
            return True
        except Exception as e:
            print(f"   [FAIL] 检查失败: {e}")
            return False

    def run_all_tests(self):
        """运行所有测试"""
        print("=" * 60)
        print("ProfileManager 模块测试")
        print("=" * 60)

        results = [
            self.test_create_profile(),
            self.test_get_profile(),
            self.test_update_profile(),
            self.test_list_profiles(),
            self.test_export_import_profile(),
            self.test_get_active_profile(),
            self.test_has_profile(),
        ]

        print("\n" + "=" * 60)
        passed = sum(results)
        total = len(results)
        print(f"测试结果: {passed}/{total} 通过")
        if passed == total:
            print("[SUCCESS] 所有测试通过！")
        else:
            print("[FAILURE] 部分测试失败")
        print("=" * 60)


if __name__ == "__main__":
    # 设置控制台编码
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')

    test = TestProfileManager()
    test.run_all_tests()
