"""
Configuration management system
Supports JSON/YAML config files and future GUI configuration
"""

from .config_manager import ConfigManager, ConfigSection
from .config_loader import load_config, save_config

__all__ = [
    'ConfigManager',
    'ConfigSection',
    'load_config',
    'save_config'
]
