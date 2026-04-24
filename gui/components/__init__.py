"""
GUI Components
"""

from .dashboard import DashboardPanel
from .evolution_panel import EvolutionPanel
from .config_panel import ConfigPanel
from .monitor_panel import MonitorPanel
from .database_panel import DatabasePanel
from .workflow_panel import WorkflowPanel

__all__ = [
    'DashboardPanel',
    'EvolutionPanel',
    'ConfigPanel',
    'MonitorPanel',
    'DatabasePanel',
    'WorkflowPanel'
]
