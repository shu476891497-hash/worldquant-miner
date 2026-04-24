"""
Configuration loader utilities
"""

import json
from typing import Dict, Any
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

from .config_manager import ConfigManager


def load_config(path: str) -> ConfigManager:
    """
    Load configuration from file
    
    Args:
        path: Path to config file (JSON or YAML)
        
    Returns:
        ConfigManager instance
    """
    config = ConfigManager()
    config.load(path)
    return config


def save_config(config: ConfigManager, path: str):
    """
    Save configuration to file
    
    Args:
        config: ConfigManager instance
        path: Path to save config file
    """
    config.save(path)
