"""
Operator Fetcher
Fetches and caches operators from WorldQuant Brain API
"""

import logging
import json
import os
import requests
from typing import List, Dict, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class OperatorFetcher:
    """
    Fetches operators from WorldQuant Brain API
    
    Caches operators locally for cold start
    """
    
    def __init__(self, session: requests.Session = None, cache_dir: str = None):
        """
        Initialize operator fetcher
        
        Args:
            session: Authenticated requests session
            cache_dir: Directory for caching operators (default: generation_two/constants)
        """
        self.session = session
        if cache_dir is None:
            # Default to generation_two/constants relative to this file
            current_file = Path(__file__)
            generation_two_dir = current_file.parent.parent
            cache_dir = str(generation_two_dir / "constants")
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.cache_file = self.cache_dir / "operatorRAW.json"
        self.operators: List[Dict] = []
    
    def fetch_operators(self, force_refresh: bool = False) -> List[Dict]:
        """
        Load operators from operatorRAW.json (matching generation_one approach)
        
        Args:
            force_refresh: Not used (operators loaded from file)
            
        Returns:
            List of operator dictionaries
        """
        # Load from file (matching generation_one approach)
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    self.operators = json.load(f)
                logger.info(f"Loaded {len(self.operators)} operators from {self.cache_file}")
                return self.operators
            except Exception as e:
                logger.error(f"Failed to load operators: {e}")
                return []
        else:
            logger.warning(f"Operator file not found: {self.cache_file}")
            logger.info("Attempting to fetch from API as fallback...")
            
            # Fallback: try to fetch from API if file doesn't exist
            if not self.session:
                logger.error("No session available for fetching operators")
                return []
            
            try:
                logger.info("Fetching operators from WorldQuant Brain API...")
                response = self.session.get('https://api.worldquantbrain.com/operators')
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # Handle different response formats
                    if isinstance(data, list):
                        self.operators = data
                    elif 'results' in data:
                        self.operators = data['results']
                    elif 'items' in data:
                        self.operators = data['items']
                    else:
                        self.operators = []
                    
                    # Cache operators
                    self._save_cache()
                    
                    logger.info(f"Fetched {len(self.operators)} operators from API")
                    return self.operators
                else:
                    logger.error(f"Failed to fetch operators: {response.status_code}")
                    return []
                    
            except Exception as e:
                logger.error(f"Error fetching operators: {e}")
                return []
    
    def _save_cache(self):
        """Save operators to cache file"""
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.operators, f, indent=2, ensure_ascii=False)
            logger.info(f"Cached {len(self.operators)} operators to {self.cache_file}")
        except Exception as e:
            logger.error(f"Error saving cache: {e}")
    
    def get_operators_by_category(self, category: str) -> List[Dict]:
        """Get operators filtered by category"""
        return [op for op in self.operators if op.get('category') == category]
    
    def get_operator_by_name(self, name: str) -> Optional[Dict]:
        """Get operator by name"""
        for op in self.operators:
            if op.get('name') == name:
                return op
        return None
    
    def get_all_categories(self) -> List[str]:
        """Get all operator categories"""
        categories = set()
        for op in self.operators:
            cat = op.get('category')
            if cat:
                categories.add(cat)
        return sorted(list(categories))
