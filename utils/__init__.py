"""
utils 模块 - 工具函数和通用组件集合

包含：
- 日志系统 (logger)
- 配置加载器 (config_loader)
- 数据库操作封装 (db_helper)
- 人类行为模拟器 (delay_simulator)
"""

# 导出核心工具模块
from .logger import setup_logger, get_logger, set_log_level
from .config_loader import get_config, load_settings, load_api_config
from .db_helper import DatabaseHelper as DBHelper, get_db as get_db_helper
from .delay_simulator import (
    DelaySimulator,
    get_simulator,
    random_delay,
    simulate_typing,
    human_like_delay
)

# 模块版本信息
__version__ = "1.0.0"

# 导出的公共接口
__all__ = [
    # 日志系统
    'setup_logger',
    'get_logger',
    'set_log_level',
    
    # 配置加载器
    'get_config',
    'load_settings',
    'load_api_config',
    
    # 数据库操作
    'DBHelper',
    'get_db_helper',
    
    # 人类行为模拟器
    'DelaySimulator',
    'get_simulator',
    'random_delay',
    'simulate_typing',
    'human_like_delay',
]