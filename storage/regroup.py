"""
Regroup Module
Groups and organizes alphas by various criteria
"""

import logging
from typing import List, Dict, Optional
from collections import defaultdict

logger = logging.getLogger(__name__)


class AlphaRegrouper:
    """
    Regroups alphas by various criteria
    
    Separated for modularity and reusability.
    """
    
    def __init__(self):
        """Initialize regrouper"""
        pass
    
    def regroup_by_region(self, results: List) -> Dict[str, List]:
        """
        Regroup results by region
        
        Args:
            results: List of results
            
        Returns:
            Dictionary mapping region to list of results
        """
        grouped = defaultdict(list)
        
        for result in results:
            region = getattr(result, 'region', result.get('region', 'UNKNOWN'))
            grouped[region].append(result)
        
        logger.info(f"Regrouped {len(results)} results into {len(grouped)} regions")
        return dict(grouped)
    
    def regroup_by_sharpe_tier(
        self, 
        results: List,
        tiers: Dict[str, float] = None
    ) -> Dict[str, List]:
        """
        Regroup results by Sharpe ratio tiers
        
        Args:
            results: List of results
            tiers: Dictionary mapping tier name to minimum Sharpe
            
        Returns:
            Dictionary mapping tier to list of results
        """
        if tiers is None:
            tiers = {
                'excellent': 2.0,
                'good': 1.5,
                'acceptable': 1.25,
                'poor': 0.0
            }
        
        grouped = defaultdict(list)
        
        for result in results:
            sharpe = getattr(result, 'sharpe', result.get('sharpe', 0.0))
            
            # Find appropriate tier
            tier = 'poor'
            for tier_name, min_sharpe in sorted(tiers.items(), key=lambda x: x[1], reverse=True):
                if sharpe >= min_sharpe:
                    tier = tier_name
                    break
            
            grouped[tier].append(result)
        
        logger.info(f"Regrouped {len(results)} results into {len(grouped)} Sharpe tiers")
        return dict(grouped)
    
    def regroup_by_operator(self, results: List) -> Dict[str, List]:
        """
        Regroup results by main operator
        
        Args:
            results: List of results
            
        Returns:
            Dictionary mapping operator to list of results
        """
        grouped = defaultdict(list)
        
        for result in results:
            template = getattr(result, 'template', result.get('template', ''))
            operator = self._extract_main_operator(template)
            grouped[operator].append(result)
        
        logger.info(f"Regrouped {len(results)} results into {len(grouped)} operators")
        return dict(grouped)
    
    def regroup_by_performance_metric(
        self, 
        results: List,
        metric: str = 'fitness',
        thresholds: List[float] = None
    ) -> Dict[str, List]:
        """
        Regroup by performance metric
        
        Args:
            results: List of results
            metric: Metric name ('fitness', 'returns', 'margin', etc.)
            thresholds: List of threshold values
            
        Returns:
            Dictionary mapping threshold range to list of results
        """
        if thresholds is None:
            if metric == 'fitness':
                thresholds = [0.0, 1.0, 1.5, 2.0]
            elif metric == 'returns':
                thresholds = [0.0, 0.1, 0.2, 0.3]
            else:
                thresholds = [0.0, 0.5, 1.0, 1.5]
        
        grouped = defaultdict(list)
        
        for result in results:
            value = getattr(result, metric, result.get(metric, 0.0))
            
            # Find appropriate range
            range_name = f"<{thresholds[0]}"
            for i in range(len(thresholds) - 1):
                if thresholds[i] <= value < thresholds[i + 1]:
                    range_name = f"{thresholds[i]}-{thresholds[i+1]}"
                    break
            if value >= thresholds[-1]:
                range_name = f">={thresholds[-1]}"
            
            grouped[range_name].append(result)
        
        logger.info(f"Regrouped {len(results)} results by {metric} into {len(grouped)} ranges")
        return dict(grouped)
    
    def regroup_by_time_period(
        self, 
        results: List,
        period_days: int = 7
    ) -> Dict[str, List]:
        """
        Regroup by time period
        
        Args:
            results: List of results
            period_days: Number of days per period
            
        Returns:
            Dictionary mapping period to list of results
        """
        import time
        from datetime import datetime, timedelta
        
        grouped = defaultdict(list)
        current_time = time.time()
        
        for result in results:
            timestamp = getattr(result, 'timestamp', result.get('timestamp', current_time))
            days_ago = (current_time - timestamp) / (24 * 3600)
            
            period = int(days_ago / period_days)
            period_name = f"{period * period_days}-{(period + 1) * period_days} days ago"
            
            grouped[period_name].append(result)
        
        logger.info(f"Regrouped {len(results)} results into {len(grouped)} time periods")
        return dict(grouped)
    
    def _extract_main_operator(self, template: str) -> str:
        """Extract main operator from template"""
        if not template:
            return 'unknown'
        
        # Find the outermost operator
        template = template.strip()
        if '(' in template:
            paren_pos = template.find('(')
            operator_part = template[:paren_pos].strip()
            if operator_part:
                return operator_part
        
        # Fallback: return first word
        parts = template.split()
        return parts[0] if parts else 'unknown'
    
    def get_regroup_summary(self, grouped: Dict[str, List]) -> Dict[str, int]:
        """
        Get summary of regrouped data
        
        Args:
            grouped: Dictionary of grouped results
            
        Returns:
            Dictionary mapping group name to count
        """
        return {name: len(results) for name, results in grouped.items()}

