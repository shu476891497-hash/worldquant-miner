"""
Self-Optimization Module for Generation Two
Adaptively tunes system parameters based on performance metrics
"""

import numpy as np
import logging
from typing import Dict, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """Performance metrics for optimization"""
    success_rate: float
    avg_sharpe: float
    exploration_rate: float
    temperature: float
    mutation_rate: float
    discovery_rate: float = 0.0
    avg_fitness: float = 0.0


class SelfOptimizer:
    """
    Self-optimizing parameter tuning system
    
    Continuously optimizes system parameters based on success rates and performance
    metrics. Adapts exploration/exploitation balance dynamically.
    """
    
    def __init__(self, optimization_interval: int = 100):
        """
        Initialize self-optimizer
        
        Args:
            optimization_interval: Number of simulations before optimization
        """
        self.parameter_history = []
        self.performance_history = []
        self.optimization_interval = optimization_interval
        
        # Default parameters
        self.current_params = {
            'exploration_rate': 0.3,
            'temperature': 0.7,
            'mutation_rate': 0.1
        }
        
    def optimize_parameters(
        self, 
        current_performance: Dict
    ) -> Optional[Dict[str, float]]:
        """
        Optimize system parameters based on performance
        
        Args:
            current_performance: Dictionary with performance metrics
            
        Returns:
            Optimized parameters dictionary or None if not enough data
        """
        # Track current performance
        self.performance_history.append(current_performance)
        
        # Update current params from performance dict if present
        if 'exploration_rate' in current_performance:
            self.current_params['exploration_rate'] = current_performance['exploration_rate']
        if 'temperature' in current_performance:
            self.current_params['temperature'] = current_performance['temperature']
        if 'mutation_rate' in current_performance:
            self.current_params['mutation_rate'] = current_performance['mutation_rate']
        
        if len(self.performance_history) < self.optimization_interval:
            return None  # Not enough data yet
        
        # Analyze performance trends
        recent_performance = self.performance_history[-self.optimization_interval:]
        
        # Calculate averages
        avg_success_rate = np.mean([
            p.get('success_rate', 0) 
            for p in recent_performance 
            if 'success_rate' in p
        ])
        avg_sharpe = np.mean([
            p.get('avg_sharpe', 0) 
            for p in recent_performance 
            if 'avg_sharpe' in p
        ])
        
        logger.info(
            f"Optimization cycle: success_rate={avg_success_rate:.3f}, "
            f"avg_sharpe={avg_sharpe:.3f}"
        )
        
        # Adjust parameters based on performance
        optimized_params = self.current_params.copy()
        
        if avg_success_rate < 0.3:
            # Low success rate: increase exploration
            optimized_params['exploration_rate'] = min(
                0.5, 
                self.current_params['exploration_rate'] * 1.2
            )
            optimized_params['temperature'] = min(
                1.0, 
                self.current_params['temperature'] * 1.1
            )
            optimized_params['mutation_rate'] = min(
                0.3, 
                self.current_params['mutation_rate'] * 1.15
            )
            logger.info("Increasing exploration due to low success rate")
            
        elif avg_success_rate > 0.6:
            # High success rate: increase exploitation
            optimized_params['exploration_rate'] = max(
                0.1, 
                self.current_params['exploration_rate'] * 0.9
            )
            optimized_params['temperature'] = max(
                0.5, 
                self.current_params['temperature'] * 0.95
            )
            optimized_params['mutation_rate'] = max(
                0.05, 
                self.current_params['mutation_rate'] * 0.9
            )
            logger.info("Increasing exploitation due to high success rate")
        else:
            # Maintain current parameters with slight adjustments
            if avg_sharpe < 1.0:
                # Low Sharpe: slightly increase exploration
                optimized_params['exploration_rate'] = min(
                    0.5,
                    self.current_params['exploration_rate'] * 1.05
                )
            elif avg_sharpe > 1.5:
                # High Sharpe: slightly increase exploitation
                optimized_params['exploration_rate'] = max(
                    0.1,
                    self.current_params['exploration_rate'] * 0.95
                )
        
        # Store in history
        self.parameter_history.append(optimized_params.copy())
        self.current_params = optimized_params
        
        return optimized_params
    
    def get_current_parameters(self) -> Dict[str, float]:
        """Get current parameter values"""
        return self.current_params.copy()
    
    def reset(self):
        """Reset optimization history"""
        self.parameter_history = []
        self.performance_history = []
        self.current_params = {
            'exploration_rate': 0.3,
            'temperature': 0.7,
            'mutation_rate': 0.1
        }

