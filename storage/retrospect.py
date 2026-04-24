"""
Retrospect Module
Analyzes historical performance and provides insights
"""

import logging
from typing import List, Dict, Optional
import numpy as np
from datetime import datetime
import time

logger = logging.getLogger(__name__)


class AlphaRetrospect:
    """
    Retrospective analysis of alpha performance
    
    Separated for modularity and focused analysis.
    """
    
    def __init__(self):
        """Initialize retrospect analyzer"""
        pass
    
    def analyze_performance_trends(
        self, 
        results: List,
        time_window_days: int = 30
    ) -> Dict:
        """
        Analyze performance trends over time
        
        Args:
            results: List of results
            time_window_days: Time window for analysis
            
        Returns:
            Dictionary with trend analysis
        """
        current_time = time.time()
        cutoff_time = current_time - (time_window_days * 24 * 3600)
        
        # Filter recent results
        recent_results = [
            r for r in results
            if getattr(r, 'timestamp', r.get('timestamp', 0)) >= cutoff_time
        ]
        
        if len(recent_results) < 2:
            return {'error': 'Insufficient data for trend analysis'}
        
        # Extract metrics
        sharpe_values = [
            getattr(r, 'sharpe', r.get('sharpe', 0.0)) 
            for r in recent_results
        ]
        fitness_values = [
            getattr(r, 'fitness', r.get('fitness', 0.0))
            for r in recent_results
        ]
        
        # Calculate trends
        sharpe_trend = np.polyfit(range(len(sharpe_values)), sharpe_values, 1)[0]
        fitness_trend = np.polyfit(range(len(fitness_values)), fitness_values, 1)[0]
        
        # Calculate averages
        avg_sharpe = np.mean(sharpe_values)
        avg_fitness = np.mean(fitness_values)
        
        # Success rate
        successful = sum(
            1 for r in recent_results
            if getattr(r, 'success', r.get('success', False))
        )
        success_rate = successful / len(recent_results) if recent_results else 0.0
        
        return {
            'time_window_days': time_window_days,
            'total_results': len(recent_results),
            'success_rate': success_rate,
            'avg_sharpe': avg_sharpe,
            'avg_fitness': avg_fitness,
            'sharpe_trend': sharpe_trend,  # Positive = improving
            'fitness_trend': fitness_trend,  # Positive = improving
            'trend_direction': 'improving' if sharpe_trend > 0 else 'declining'
        }
    
    def identify_top_performers(
        self, 
        results: List,
        top_n: int = 10,
        metric: str = 'sharpe'
    ) -> List[Dict]:
        """
        Identify top performing alphas
        
        Args:
            results: List of results
            top_n: Number of top performers
            metric: Metric to rank by
            
        Returns:
            List of top performer dictionaries
        """
        # Filter successful results
        successful = [
            r for r in results
            if getattr(r, 'success', r.get('success', False))
        ]
        
        # Sort by metric
        sorted_results = sorted(
            successful,
            key=lambda r: getattr(r, metric, r.get(metric, 0.0)),
            reverse=True
        )
        
        top_performers = []
        for i, result in enumerate(sorted_results[:top_n]):
            top_performers.append({
                'rank': i + 1,
                'template': getattr(result, 'template', result.get('template', ''))[:100],
                'region': getattr(result, 'region', result.get('region', '')),
                'sharpe': getattr(result, 'sharpe', result.get('sharpe', 0.0)),
                'fitness': getattr(result, 'fitness', result.get('fitness', 0.0)),
                'returns': getattr(result, 'returns', result.get('returns', 0.0)),
                'margin': getattr(result, 'margin', result.get('margin', 0.0))
            })
        
        logger.info(f"Identified {len(top_performers)} top performers by {metric}")
        return top_performers
    
    def analyze_region_performance(self, results: List) -> Dict[str, Dict]:
        """
        Analyze performance by region
        
        Args:
            results: List of results
            
        Returns:
            Dictionary mapping region to performance metrics
        """
        from collections import defaultdict
        
        region_results = defaultdict(list)
        
        for result in results:
            region = getattr(result, 'region', result.get('region', 'UNKNOWN'))
            region_results[region].append(result)
        
        region_analysis = {}
        
        for region, region_data in region_results.items():
            sharpe_values = [
                getattr(r, 'sharpe', r.get('sharpe', 0.0))
                for r in region_data
                if getattr(r, 'success', r.get('success', False))
            ]
            
            if sharpe_values:
                region_analysis[region] = {
                    'total': len(region_data),
                    'successful': len(sharpe_values),
                    'success_rate': len(sharpe_values) / len(region_data) if region_data else 0.0,
                    'avg_sharpe': np.mean(sharpe_values),
                    'max_sharpe': np.max(sharpe_values),
                    'min_sharpe': np.min(sharpe_values),
                    'std_sharpe': np.std(sharpe_values)
                }
            else:
                region_analysis[region] = {
                    'total': len(region_data),
                    'successful': 0,
                    'success_rate': 0.0,
                    'avg_sharpe': 0.0,
                    'max_sharpe': 0.0,
                    'min_sharpe': 0.0,
                    'std_sharpe': 0.0
                }
        
        logger.info(f"Analyzed performance for {len(region_analysis)} regions")
        return region_analysis
    
    def identify_degrading_alphas(
        self, 
        results: List,
        degradation_threshold: float = 0.2
    ) -> List[Dict]:
        """
        Identify alphas that are degrading
        
        Args:
            results: List of results
            degradation_threshold: Threshold for degradation (e.g., 0.2 = 20% drop)
            
        Returns:
            List of degrading alpha dictionaries
        """
        # Group by template
        from collections import defaultdict
        template_results = defaultdict(list)
        
        for result in results:
            template = getattr(result, 'template', result.get('template', ''))
            template_results[template].append(result)
        
        degrading = []
        
        for template, template_data in template_results.items():
            if len(template_data) < 5:  # Need at least 5 results
                continue
            
            # Sort by timestamp
            sorted_data = sorted(
                template_data,
                key=lambda r: getattr(r, 'timestamp', r.get('timestamp', 0))
            )
            
            # Compare recent vs older
            recent = sorted_data[-5:]
            older = sorted_data[:-5] if len(sorted_data) > 5 else []
            
            if not older:
                continue
            
            recent_sharpe = np.mean([
                getattr(r, 'sharpe', r.get('sharpe', 0.0))
                for r in recent
                if getattr(r, 'success', r.get('success', False))
            ])
            
            older_sharpe = np.mean([
                getattr(r, 'sharpe', r.get('sharpe', 0.0))
                for r in older
                if getattr(r, 'success', r.get('success', False))
            ])
            
            if older_sharpe > 0 and recent_sharpe < older_sharpe * (1 - degradation_threshold):
                degrading.append({
                    'template': template[:100],
                    'recent_sharpe': recent_sharpe,
                    'older_sharpe': older_sharpe,
                    'degradation': (older_sharpe - recent_sharpe) / older_sharpe,
                    'num_recent': len(recent),
                    'num_older': len(older)
                })
        
        logger.info(f"Identified {len(degrading)} degrading alphas")
        return degrading
    
    def generate_insights(self, results: List) -> Dict:
        """
        Generate overall insights from results
        
        Args:
            results: List of results
            
        Returns:
            Dictionary with insights
        """
        if not results:
            return {'error': 'No results to analyze'}
        
        # Overall statistics
        successful = [
            r for r in results
            if getattr(r, 'success', r.get('success', False))
        ]
        
        sharpe_values = [
            getattr(r, 'sharpe', r.get('sharpe', 0.0))
            for r in successful
        ]
        
        insights = {
            'total_results': len(results),
            'successful_count': len(successful),
            'success_rate': len(successful) / len(results) if results else 0.0,
            'avg_sharpe': np.mean(sharpe_values) if sharpe_values else 0.0,
            'max_sharpe': np.max(sharpe_values) if sharpe_values else 0.0,
            'min_sharpe': np.min(sharpe_values) if sharpe_values else 0.0,
            'top_performers': self.identify_top_performers(results, top_n=5),
            'region_performance': self.analyze_region_performance(results),
            'performance_trends': self.analyze_performance_trends(results),
            'degrading_alphas': self.identify_degrading_alphas(results)
        }
        
        logger.info("Generated comprehensive insights")
        return insights

