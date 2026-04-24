"""
Cyberpunk-themed GUI for Generation Two
Modular components for monitoring and control
"""

from .main_window import CyberpunkGUI
from .components.dashboard import DashboardPanel
from .components.evolution_panel import EvolutionPanel
from .components.config_panel import ConfigPanel
from .components.monitor_panel import MonitorPanel

__all__ = [
    'CyberpunkGUI',
    'DashboardPanel',
    'EvolutionPanel',
    'ConfigPanel',
    'MonitorPanel'
]
