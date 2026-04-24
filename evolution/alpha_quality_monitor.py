"""
Alpha Quality Monitor for Generation Two
Tracks alpha performance over time and detects degradation
"""

import time
import numpy as np
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


@dataclass
class AlphaPerformanceRecord:
    """Single performance record for an alpha"""
    timestamp: float
    sharpe: float
    fitness: float
    returns: float
    turnover: Optional[float] = None
    max_drawdown: Optional[float] = None


class AlphaQualityMonitor:
    """
    Monitor alpha performance over time and detect degradation
    
    Tracks performance history for each alpha and calculates health scores.
    Detects when alphas are degrading and need to be replaced.
    """
    
    def __init__(self, monitoring_window: int = 30):
        """
        Initialize quality monitor
        
        Args:
            monitoring_window: Number of days to keep in history
        """
        self.monitoring_window = monitoring_window  # days
        self.alpha_history: Dict[str, List[AlphaPerformanceRecord]] = {}
        
    def track_alpha(self, alpha_id: str, performance: Dict):
        """
        Track alpha performance over time
        
        Args:
            alpha_id: Unique identifier for the alpha
            performance: Dictionary with performance metrics
        """
        if alpha_id not in self.alpha_history:
            self.alpha_history[alpha_id] = []
        
        # Create performance record
        record = AlphaPerformanceRecord(
            timestamp=time.time(),
            sharpe=performance.get('sharpe', 0.0),
            fitness=performance.get('fitness', 0.0),
            returns=performance.get('returns', 0.0),
            turnover=performance.get('turnover'),
            max_drawdown=performance.get('max_drawdown')
        )
        
        self.alpha_history[alpha_id].append(record)
        
        # Keep only recent history
        cutoff_time = time.time() - (self.monitoring_window * 24 * 3600)
        self.alpha_history[alpha_id] = [
            record for record in self.alpha_history[alpha_id]
            if record.timestamp > cutoff_time
        ]
        
        logger.debug(
            f"Tracked alpha {alpha_id}: sharpe={record.sharpe:.3f}, "
            f"fitness={record.fitness:.3f}"
        )
    
    def detect_degradation(self, alpha_id: str) -> bool:
        """
        Detect if alpha performance is degrading
        
        Args:
            alpha_id: Alpha identifier
            
        Returns:
            True if degradation detected, False otherwise
        """
        if alpha_id not in self.alpha_history:
            return False
        
        history = self.alpha_history[alpha_id]
        if len(history) < 10:
            return False  # Not enough data
        
        # Calculate trend
        recent_sharpe = [r.sharpe for r in history[-10:]]
        older_sharpe = [r.sharpe for r in history[:-10]]
        
        if len(older_sharpe) > 0:
            recent_avg = np.mean(recent_sharpe)
            older_avg = np.mean(older_sharpe)
            
            # Degradation if recent performance is 20% worse
            if recent_avg < older_avg * 0.8:
                logger.warning(
                    f"Degradation detected for alpha {alpha_id}: "
                    f"recent_avg={recent_avg:.3f}, older_avg={older_avg:.3f}"
                )
                return True
        
        return False
    
    def get_alpha_health_score(self, alpha_id: str) -> float:
        """
        Calculate health score (0-1) for an alpha
        
        Args:
            alpha_id: Alpha identifier
            
        Returns:
            Health score between 0 and 1
        """
        if alpha_id not in self.alpha_history:
            return 1.0  # New alpha, assume healthy
        
        history = self.alpha_history[alpha_id]
        if len(history) < 5:
            return 1.0
        
        # Calculate stability and trend
        sharpe_values = [r.sharpe for r in history]
        
        if len(sharpe_values) < 2:
            return 1.0
        
        # Calculate trend (slope)
        x = np.arange(len(sharpe_values))
        trend = np.polyfit(x, sharpe_values, 1)[0]
        
        # Calculate stability (inverse of standard deviation)
        stability = 1.0 / (1.0 + np.std(sharpe_values))
        
        # Health score combines trend and stability
        # Positive trend contributes positively, negative trend contributes negatively
        trend_component = max(0, 1.0 + trend * 0.1)  # Scale trend
        health = (stability * 0.6) + (trend_component * 0.4)
        
        return min(1.0, max(0.0, health))
    
    def get_alpha_statistics(self, alpha_id: str) -> Optional[Dict]:
        """
        Get statistics for an alpha
        
        Args:
            alpha_id: Alpha identifier
            
        Returns:
            Dictionary with statistics or None if no history
        """
        if alpha_id not in self.alpha_history:
            return None
        
        history = self.alpha_history[alpha_id]
        if len(history) == 0:
            return None
        
        sharpe_values = [r.sharpe for r in history]
        fitness_values = [r.fitness for r in history]
        returns_values = [r.returns for r in history]
        
        return {
            'alpha_id': alpha_id,
            'num_records': len(history),
            'avg_sharpe': np.mean(sharpe_values),
            'std_sharpe': np.std(sharpe_values),
            'min_sharpe': np.min(sharpe_values),
            'max_sharpe': np.max(sharpe_values),
            'avg_fitness': np.mean(fitness_values),
            'avg_returns': np.mean(returns_values),
            'health_score': self.get_alpha_health_score(alpha_id),
            'is_degrading': self.detect_degradation(alpha_id),
            'first_seen': datetime.fromtimestamp(history[0].timestamp),
            'last_seen': datetime.fromtimestamp(history[-1].timestamp)
        }
    
    def get_all_alpha_ids(self) -> List[str]:
        """Get list of all tracked alpha IDs"""
        return list(self.alpha_history.keys())
    
    def remove_alpha(self, alpha_id: str):
        """Remove alpha from tracking"""
        if alpha_id in self.alpha_history:
            del self.alpha_history[alpha_id]
            logger.info(f"Removed alpha {alpha_id} from tracking")

