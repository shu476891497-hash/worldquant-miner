"""
Region Theme Manager
Manages region-specific themes and dataset category requirements
"""

import logging
from typing import List, Dict, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class RegionThemeManager:
    """
    Manages region themes and dataset category requirements
    
    Handles:
    - IND Region Theme with weekly category changes
    - Dataset category requirements
    - Excluded datasets
    - Multipliers
    """
    
    def __init__(self):
        """Initialize theme manager"""
        # IND Region Theme schedule
        self.ind_theme_schedule = {
            1: {
                'dates': ('2025-12-08', '2025-12-14'),
                'categories': ['Fundamental', 'Earnings', 'Short Interest', 'PV', 'Broker']
            },
            2: {
                'dates': ('2025-12-15', '2025-12-21'),
                'categories': ['Insiders', 'Sentiment', 'News', 'Other', 'Option']
            },
            3: {
                'dates': ('2025-12-22', '2025-12-28'),
                'categories': ['Institutions', 'Analyst', 'Risk']
            },
            4: {
                'dates': ('2025-12-29', '2026-01-04'),
                'categories': ['Macro', 'Model']
            }
        }
        
        # Always excluded datasets
        self.excluded_datasets = ['imbalance5', 'model110', 'pv1', 'other335', 'model39']
        
        # Permitted grouping fields from pv1
        self.permitted_pv1_fields = [
            'country', 'exchange', 'market', 'sector', 'industry', 'subindustry'
        ]
        
        # Active themes
        self.active_themes = {
            'IND': {
                'name': 'IND Region Theme',
                'multiplier': 2.0,
                'active': True
            },
            'ATOM': {
                'name': 'Scalable ATOM Theme',
                'multiplier': 2.0,
                'active': True,
                'requires_max_trade': True,
                'requires_single_dataset': True,
                'dates': ('2025-12-15', '2026-01-11')
            }
        }
    
    def get_current_ind_week(self) -> Optional[Dict]:
        """
        Get current IND theme week configuration
        
        Returns:
            Week configuration dict or None
        """
        today = datetime.now().date()
        
        for week_num, config in self.ind_theme_schedule.items():
            start_date = datetime.strptime(config['dates'][0], '%Y-%m-%d').date()
            end_date = datetime.strptime(config['dates'][1], '%Y-%m-%d').date()
            
            if start_date <= today <= end_date:
                return {
                    'week': week_num,
                    'categories': config['categories'],
                    'start_date': start_date,
                    'end_date': end_date
                }
        
        return None
    
    def get_required_categories(self, region: str) -> List[str]:
        """
        Get required dataset categories for a region
        
        Args:
            region: Region code
            
        Returns:
            List of required categories
        """
        if region == 'IND':
            current_week = self.get_current_ind_week()
            if current_week:
                return current_week['categories']
        
        return []
    
    def is_theme_active(self, region: str) -> bool:
        """
        Check if theme is active for region
        
        Args:
            region: Region code
            
        Returns:
            True if theme is active
        """
        if region in self.active_themes:
            theme = self.active_themes[region]
            if not theme.get('active', False):
                return False
            
            # Check date range if specified
            if 'dates' in theme:
                today = datetime.now().date()
                start_date = datetime.strptime(theme['dates'][0], '%Y-%m-%d').date()
                end_date = datetime.strptime(theme['dates'][1], '%Y-%m-%d').date()
                return start_date <= today <= end_date
            
            return True
        
        return False
    
    def get_theme_multiplier(self, region: str) -> float:
        """
        Get multiplier for region theme
        
        Args:
            region: Region code
            
        Returns:
            Multiplier (1.0 if no theme)
        """
        if self.is_theme_active(region):
            return self.active_themes[region].get('multiplier', 1.0)
        return 1.0
    
    def get_theme_requirements(self, region: str) -> Dict:
        """
        Get theme requirements for region
        
        Args:
            region: Region code
            
        Returns:
            Dictionary with requirements
        """
        if not self.is_theme_active(region):
            return {}
        
        theme = self.active_themes[region]
        requirements = {
            'multiplier': theme.get('multiplier', 1.0),
            'excluded_datasets': self.excluded_datasets.copy()
        }
        
        if region == 'IND':
            current_week = self.get_current_ind_week()
            if current_week:
                requirements['required_categories'] = current_week['categories']
                requirements['permitted_pv1_fields'] = self.permitted_pv1_fields
        elif region == 'ATOM':
            requirements['requires_max_trade'] = theme.get('requires_max_trade', False)
            requirements['requires_single_dataset'] = theme.get('requires_single_dataset', False)
        
        return requirements
    
    def validate_alpha_for_theme(
        self, 
        alpha_expression: str, 
        region: str,
        datasets_used: List[str] = None
    ) -> tuple[bool, List[str]]:
        """
        Validate alpha expression against theme requirements
        
        Args:
            alpha_expression: Alpha expression
            region: Region code
            datasets_used: List of datasets used (if known)
            
        Returns:
            Tuple of (is_valid, reasons)
        """
        if not self.is_theme_active(region):
            return True, []
        
        reasons = []
        requirements = self.get_theme_requirements(region)
        
        # Check excluded datasets
        if datasets_used:
            for dataset in datasets_used:
                if dataset in requirements.get('excluded_datasets', []):
                    reasons.append(f"Uses excluded dataset: {dataset}")
        
        # Check required categories (for IND)
        if region == 'IND':
            required_categories = requirements.get('required_categories', [])
            if required_categories:
                # This would need dataset metadata to fully validate
                # For now, we'll just check if expression mentions excluded datasets
                for excluded in self.excluded_datasets:
                    if excluded in alpha_expression:
                        reasons.append(f"Uses excluded dataset: {excluded}")
        
        # Check ATOM requirements
        if region == 'ATOM':
            if requirements.get('requires_max_trade', False):
                if 'maxTrade' not in alpha_expression.lower() and 'maxtrade' not in alpha_expression.lower():
                    reasons.append("ATOM theme requires MaxTrade=ON")
            
            if requirements.get('requires_single_dataset', False):
                # Would need to parse expression to count datasets
                # Simplified check
                pass
        
        is_valid = len(reasons) == 0
        return is_valid, reasons

