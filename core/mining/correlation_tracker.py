"""
Correlation Tracker for Continuous Mining
Tracks correlations between alphas to maximize low-correlation simulations
"""

import logging
import sqlite3
import json
from typing import List, Dict, Optional, Tuple
from collections import defaultdict

logger = logging.getLogger(__name__)


class CorrelationTracker:
    """
    Tracks correlations between alphas to prioritize low-correlation simulations
    """
    
    def __init__(self, db_path: str = "generation_two_backtests.db"):
        """
        Initialize correlation tracker
        
        Args:
            db_path: Path to database containing backtest results
        """
        self.db_path = db_path
        self._correlation_cache = {}  # Cache for correlation lookups
        self._template_to_alpha_id = {}  # Map template to alpha_id for correlation lookup
    
    def get_correlation(self, alpha_id1: str, alpha_id2: str) -> Optional[float]:
        """
        Get correlation between two alphas
        
        Args:
            alpha_id1: First alpha ID
            alpha_id2: Second alpha ID
            
        Returns:
            Correlation value (0.0-1.0) or None if not available
        """
        if not alpha_id1 or not alpha_id2:
            return None
        
        # Use cache key (sorted to avoid duplicates)
        cache_key = tuple(sorted([alpha_id1, alpha_id2]))
        if cache_key in self._correlation_cache:
            return self._correlation_cache[cache_key]
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Try to find correlation in correlations JSON field
            cursor.execute('''
                SELECT correlations, alpha_id FROM backtest_results
                WHERE alpha_id IN (?, ?) AND success = 1
            ''', (alpha_id1, alpha_id2))
            
            results = cursor.fetchall()
            if len(results) < 2:
                conn.close()
                return None
            
            # Parse correlations JSON
            correlations = {}
            for row in results:
                if row[0]:
                    try:
                        corr_data = json.loads(row[0])
                        if isinstance(corr_data, dict):
                            correlations.update(corr_data)
                    except:
                        pass
            
            # Find correlation between the two alphas
            correlation = None
            if alpha_id1 in correlations:
                if alpha_id2 in correlations[alpha_id1]:
                    correlation = float(correlations[alpha_id1][alpha_id2])
            elif alpha_id2 in correlations:
                if alpha_id1 in correlations[alpha_id2]:
                    correlation = float(correlations[alpha_id2][alpha_id1])
            
            conn.close()
            
            # Cache result
            if correlation is not None:
                self._correlation_cache[cache_key] = correlation
            
            return correlation
            
        except Exception as e:
            logger.debug(f"Error getting correlation: {e}")
            return None
    
    def get_average_correlation(self, template: str, existing_alpha_ids: List[str]) -> float:
        """
        Get average correlation between a template and existing successful alphas
        
        Args:
            template: Template to check
            existing_alpha_ids: List of existing successful alpha IDs
            
        Returns:
            Average correlation (0.0-1.0), or 0.0 if no correlations found
        """
        if not existing_alpha_ids:
            return 0.0
        
        # Find alpha_id for this template if it exists
        template_alpha_id = self._template_to_alpha_id.get(template)
        if not template_alpha_id:
            # Try to find in database
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT alpha_id FROM backtest_results
                    WHERE template = ? AND success = 1 AND alpha_id IS NOT NULL
                    LIMIT 1
                ''', (template,))
                row = cursor.fetchone()
                if row and row[0]:
                    template_alpha_id = row[0]
                    self._template_to_alpha_id[template] = template_alpha_id
                conn.close()
            except Exception as e:
                logger.debug(f"Error finding alpha_id for template: {e}")
        
        if not template_alpha_id:
            return 0.0  # No existing alpha for this template
        
        # Calculate average correlation
        correlations = []
        for existing_alpha_id in existing_alpha_ids[:50]:  # Limit to 50 for performance
            if existing_alpha_id != template_alpha_id:
                corr = self.get_correlation(template_alpha_id, existing_alpha_id)
                if corr is not None:
                    correlations.append(abs(corr))  # Use absolute value
        
        if not correlations:
            return 0.0
        
        return sum(correlations) / len(correlations)
    
    def get_low_correlation_templates(
        self,
        candidate_templates: List[Tuple[str, str]],  # List of (template, region) tuples
        max_correlation: float = 0.3,
        limit: int = 10
    ) -> List[Tuple[str, str, float]]:
        """
        Select templates with low correlation to existing successful alphas
        
        Args:
            candidate_templates: List of (template, region) tuples
            max_correlation: Maximum acceptable average correlation
            limit: Maximum number of templates to return
            
        Returns:
            List of (template, region, avg_correlation) tuples, sorted by correlation (lowest first)
        """
        # Get existing successful alpha IDs
        existing_alpha_ids = self._get_successful_alpha_ids()
        
        if not existing_alpha_ids:
            # No existing alphas, return all candidates
            return [(t, r, 0.0) for t, r in candidate_templates[:limit]]
        
        # Calculate correlations for each candidate
        candidates_with_corr = []
        for template, region in candidate_templates:
            avg_corr = self.get_average_correlation(template, existing_alpha_ids)
            if avg_corr <= max_correlation:
                candidates_with_corr.append((template, region, avg_corr))
        
        # Sort by correlation (lowest first)
        candidates_with_corr.sort(key=lambda x: x[2])
        
        return candidates_with_corr[:limit]
    
    def _get_successful_alpha_ids(self, limit: int = 100) -> List[str]:
        """Get list of successful alpha IDs from database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT DISTINCT alpha_id FROM backtest_results
                WHERE success = 1 AND alpha_id IS NOT NULL AND alpha_id != ''
                ORDER BY sharpe DESC
                LIMIT ?
            ''', (limit,))
            
            alpha_ids = [row[0] for row in cursor.fetchall() if row[0]]
            conn.close()
            return alpha_ids
        except Exception as e:
            logger.debug(f"Error getting successful alpha IDs: {e}")
            return []
    
    def update_template_alpha_mapping(self, template: str, alpha_id: str):
        """Update mapping from template to alpha_id"""
        if template and alpha_id:
            self._template_to_alpha_id[template] = alpha_id
