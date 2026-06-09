"""
YAML配置管理模块 - 负责配置文件的读取、校验和保存

功能：
- 加载 settings.yaml 和 api_config.yaml
- 配置项校验（必填项、类型检查、默认值）
- 配置修改后持久化保存
- 提供全局单例访问接口
"""

import os
import yaml
from typing import Any, Dict, Optional, List, Tuple
from pathlib import Path


class ConfigLoader:
    """
    配置加载器类 - 负责YAML配置文件的读取、校验和保存

    功能：
    - 加载 settings.yaml 和 api_config.yaml
    - 配置项校验（必填项、类型检查、默认值）
    - 配置修改后持久化保存
    - 提供全局单例访问接口
    """

    def __init__(self, config_dir: str = "config"):
        """
        初始化配置加载器

        Args:
            config_dir: 配置文件目录路径（相对于项目根目录）
        """
        # 定位项目根目录（基于当前文件位置向上查找）
        self._project_root = self._find_project_root()
        # 处理配置目录路径（支持相对路径和绝对路径）
        if os.path.isabs(config_dir):
            self.config_dir = Path(config_dir)
        else:
            self.config_dir = self._project_root / config_dir

        # 缓存已加载的配置
        self._settings_cache: Optional[Dict[str, Any]] = None
        self._api_config_cache: Optional[Dict[str, Any]] = None

    def _find_project_root(self) -> Path:
        """
        查找项目根目录（基于当前文件向上查找）

        Returns:
            项目根目录的Path对象
        """
        current = Path(__file__).resolve().parent
        while current.parent != current:
            if (current / "config").exists() or (current / ".git").exists():
                return current
            current = current.parent
        # 如果找不到，返回当前文件所在目录的上级目录
        return Path(__file__).resolve().parent.parent

    def _load_yaml(self, filename: str) -> Dict[str, Any]:
        """
        内部方法：加载YAML文件

        Args:
            filename: 配置文件名（不含路径）

        Returns:
            解析后的配置字典

        Raises:
            FileNotFoundError: 配置文件不存在
            yaml.YAMLError: YAML格式错误
        """
        file_path = self.config_dir / filename
        if not file_path.exists():
            raise FileNotFoundError(f"配置文件不存在: {file_path}")

        with open(file_path, 'r', encoding='utf-8') as f:
            try:
                return yaml.safe_load(f) or {}
            except yaml.YAMLError as e:
                raise yaml.YAMLError(f"YAML解析错误 {filename}: {e}")

    def _save_yaml(self, filename: str, config: Dict[str, Any]) -> bool:
        """
        内部方法：保存配置到YAML文件

        Args:
            filename: 配置文件名
            config: 要保存的配置字典

        Returns:
            保存成功返回True
        """
        file_path = self.config_dir / filename
        # 确保目录存在
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(file_path, 'w', encoding='utf-8') as f:
            yaml.dump(
                config,
                f,
                allow_unicode=True,
                default_flow_style=False,
                sort_keys=False,
                Dumper=yaml.SafeDumper
            )
        return True

    def load_settings(self) -> Dict[str, Any]:
        """
        加载求职标准配置

        Returns:
            包含求职标准的字典

        Raises:
            FileNotFoundError: 配置文件不存在
            yaml.YAMLError: YAML格式错误
            ValueError: 必填配置项缺失
        """
        config = self._load_yaml("settings.yaml")
        # 校验配置有效性
        is_valid, errors = self.validate_settings(config)
        if not is_valid:
            raise ValueError(f"配置校验失败: {'; '.join(errors)}")

        self._settings_cache = config
        return config

    def load_api_config(self) -> Dict[str, Any]:
        """
        加载API密钥配置

        Returns:
            包含API配置的字典

        Raises:
            FileNotFoundError: 配置文件不存在
            yaml.YAMLError: YAML格式错误
        """
        config = self._load_yaml("api_config.yaml")
        self._api_config_cache = config
        return config

    def save_settings(self, config: Dict[str, Any]) -> bool:
        """
        保存求职标准配置到文件

        Args:
            config: 要保存的配置字典

        Returns:
            保存成功返回True
        """
        # 保存前进行校验
        is_valid, errors = self.validate_settings(config)
        if not is_valid:
            raise ValueError(f"无法保存无效配置: {'; '.join(errors)}")

        success = self._save_yaml("settings.yaml", config)
        if success:
            self._settings_cache = config
        return success

    def save_api_config(self, config: Dict[str, Any]) -> bool:
        """
        保存API配置到文件

        Args:
            config: 要保存的配置字典

        Returns:
            保存成功返回True
        """
        success = self._save_yaml("api_config.yaml", config)
        if success:
            self._api_config_cache = config
        return success

    def validate_settings(self, config: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        校验求职标准配置的完整性和有效性

        Args:
            config: 待校验的配置字典

        Returns:
            (是否有效, 错误信息列表)
        """
        errors: List[str] = []

        # 检查 job_keywords 是否为非空列表
        job_keywords = config.get("job_keywords")
        if not isinstance(job_keywords, list) or len(job_keywords) == 0:
            errors.append("job_keywords 必须是非空列表")

        # 检查 salary_range 的 min 和 max
        salary_range = config.get("salary_range", {})
        if not isinstance(salary_range, dict):
            errors.append("salary_range 必须是字典类型")
        else:
            salary_min = salary_range.get("min")
            salary_max = salary_range.get("max")

            if not isinstance(salary_min, int) or salary_min <= 0:
                errors.append("salary_range.min 必须是正整数")
            if not isinstance(salary_max, int) or salary_max <= 0:
                errors.append("salary_range.max 必须是正整数")
            if (isinstance(salary_min, int) and isinstance(salary_max, int) and
                    salary_min > salary_max):
                errors.append("salary_range.min 不能大于 salary_range.max")

        # 检查 locations 是否为非空列表
        locations = config.get("locations")
        if not isinstance(locations, list) or len(locations) == 0:
            errors.append("locations 必须是非空列表")

        # 检查 experience_years.min 是否为非负数
        experience_years = config.get("experience_years", {})
        if isinstance(experience_years, dict):
            exp_min = experience_years.get("min")
            if exp_min is not None and (not isinstance(exp_min, (int, float)) or exp_min < 0):
                errors.append("experience_years.min 必须是非负数")

        return (len(errors) == 0, errors)

    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置值（支持点号分隔的嵌套键，如 'volcengine.api_key'）

        Args:
            key: 配置键名（支持点号分隔的嵌套访问）
            default: 默认值

        Returns:
            配置值或默认值
        """
        # 优先从缓存获取，合并 settings 和 api_config
        config = {}
        if self._settings_cache:
            config.update(self._settings_cache)
        if self._api_config_cache:
            config.update(self._api_config_cache)

        # 如果缓存为空，尝试加载
        if not config:
            try:
                config.update(self.load_settings())
            except (FileNotFoundError, ValueError):
                pass
            try:
                config.update(self.load_api_config())
            except FileNotFoundError:
                pass

        # 支持点号分隔的嵌套键访问
        keys = key.split(".")
        value = config
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value

    def reload(self) -> None:
        """
        重新加载所有配置（清除缓存）

        用于配置文件被外部修改后刷新
        """
        self._settings_cache = None
        self._api_config_cache = None


# 全局配置加载器实例（延迟初始化）
_config_instance: Optional[ConfigLoader] = None


def get_config() -> ConfigLoader:
    """
    获取全局配置加载器实例（单例模式）

    Returns:
        ConfigLoader 全局唯一实例
    """
    global _config_instance
    if _config_instance is None:
        _config_instance = ConfigLoader()
    return _config_instance


def load_settings() -> Dict[str, Any]:
    """便捷函数：直接加载求职标准配置"""
    return get_config().load_settings()


def load_api_config() -> Dict[str, Any]:
    """便捷函数：直接加载API配置"""
    return get_config().load_api_config()


# 测试代码块
if __name__ == "__main__":
    print("=" * 60)
    print("YAML配置管理模块测试")
    print("=" * 60)

    try:
        # 创建配置加载器实例
        loader = ConfigLoader()
        print(f"\n✓ 配置目录: {loader.config_dir}")
        print(f"✓ 项目根目录: {loader._project_root}")

        # 测试加载求职标准配置
        print("\n--- 加载求职标准配置 ---")
        settings = loader.load_settings()
        print(f"✓ 岗位关键词: {settings.get('job_keywords')}")
        print(f"✓ 薪资范围: {settings.get('salary_range')}")
        print(f"✓ 工作地点: {settings.get('locations')}")
        print(f"✓ 工作年限: {settings.get('experience_years')}")

        # 测试加载API配置
        print("\n--- 加载API配置 ---")
        api_config = loader.load_api_config()
        print(f"✓ 火山引擎API Key: {api_config.get('volcengine', {}).get('api_key', '未设置')[:20]}...")
        print(f"✓ Browser Use配置: {api_config.get('browser_use')}")

        # 测试嵌套键访问
        print("\n--- 测试嵌套键访问 ---")
        api_key = loader.get("volcengine.api_key", "默认值")
        print(f"✓ volcengine.api_key: {api_key[:20] if api_key != '默认值' else api_key}...")

        chat_model = loader.get("volcengine.models.chat", "未找到")
        print(f"✓ volcengine.models.chat: {chat_model}")

        missing_value = loader.get("不存在的键", "这是默认值")
        print(f"✓ 不存在的键（使用默认值）: {missing_value}")

        # 测试配置校验
        print("\n--- 测试配置校验 ---")
        valid_config = {
            "job_keywords": ["Python开发"],
            "salary_range": {"min": 15, "max": 30},
            "locations": ["北京"],
            "experience_years": {"min": 3}
        }
        is_valid, errors = loader.validate_settings(valid_config)
        print(f"✓ 有效配置校验结果: {is_valid}, 错误数: {len(errors)}")

        invalid_config = {
            "job_keywords": [],
            "salary_range": {"min": -1, "max": 0},
            "locations": [],
            "experience_years": {"min": -1}
        }
        is_valid, errors = loader.validate_settings(invalid_config)
        print(f"✓ 无效配置校验结果: {is_valid}")
        print(f"  错误信息:")
        for error in errors:
            print(f"    - {error}")

        # 测试全局单例
        print("\n--- 测试全局单例模式 ---")
        config1 = get_config()
        config2 = get_config()
        print(f"✓ 单例检查: config1 is config2 = {config1 is config2}")

        # 测试便捷函数
        print("\n--- 测试便捷函数 ---")
        settings_simple = load_settings()
        print(f"✓ 便捷函数加载成功: {bool(settings_simple)}")

        print("\n" + "=" * 60)
        print("✓ 所有测试通过！")
        print("=" * 60)

    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
