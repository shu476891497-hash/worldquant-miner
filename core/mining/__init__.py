"""
Mining Module for Continuous Alpha Mining
Provides modular components for continuous simulation and mining
"""

from .correlation_tracker import CorrelationTracker
from .duplicate_detector import MiningDuplicateDetector
from .search_strategy import SearchStrategyManager, SearchStrategy
from .mining_coordinator import MiningCoordinator

__all__ = [
    'CorrelationTracker',
    'MiningDuplicateDetector',
    'SearchStrategyManager',
    'SearchStrategy',
    'MiningCoordinator'
]
