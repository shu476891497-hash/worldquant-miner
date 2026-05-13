"""
Search Strategy for Continuous Mining
Implements BFS (Breadth-First Search) and DFS (Depth-First Search) strategies
"""

import logging
from typing import List, Dict, Tuple, Optional
from enum import Enum
from collections import deque

logger = logging.getLogger(__name__)


class SearchStrategy(Enum):
    """Search strategy types"""
    BFS = "breadth_first"  # Breadth-first: explore all regions before diving deep
    DFS = "depth_first"    # Depth-first: dive deep into one template/region
    HYBRID = "hybrid"      # Hybrid: mix of both


class SearchStrategyManager:
    """
    Manages search strategies for continuous mining:
    - BFS: Generate templates across all regions before diving deep
    - DFS: Generate multiple variations of a successful template
    """
    
    def __init__(self, strategy: SearchStrategy = SearchStrategy.BFS):
        """
        Initialize search strategy manager
        
        Args:
            strategy: Search strategy to use
        """
        self.strategy = strategy
        self.region_queue = deque()  # Queue for BFS region exploration
        self.template_stack = []  # Stack for DFS template exploration
        self.successful_templates: Dict[str, List[str]] = {}  # region -> list of successful templates
        self.current_region_index = 0
        self.regions = ['USA', 'EUR', 'CHN', 'ASI', 'GLB', 'IND']
    
    def initialize(self, regions: List[str] = None):
        """Initialize search strategy"""
        if regions:
            self.regions = regions
        
        if self.strategy == SearchStrategy.BFS:
            # Initialize region queue for BFS
            self.region_queue = deque(self.regions)
            logger.info(f"Initialized BFS with {len(self.regions)} regions")
        
        elif self.strategy == SearchStrategy.DFS:
            # Initialize with first region
            if self.regions:
                self.template_stack = [self.regions[0]]
                logger.info(f"Initialized DFS starting with region: {self.regions[0]}")
        
        elif self.strategy == SearchStrategy.HYBRID:
            # Initialize both
            self.region_queue = deque(self.regions)
            if self.regions:
                self.template_stack = [self.regions[0]]
            logger.info(f"Initialized HYBRID with {len(self.regions)} regions")
    
    def get_next_region(self) -> Optional[str]:
        """
        Get next region to explore based on strategy
        
        Returns:
            Region name or None if no more regions
        """
        if self.strategy == SearchStrategy.BFS:
            # BFS: get from queue
            if self.region_queue:
                region = self.region_queue.popleft()
                # Add back to end for round-robin
                self.region_queue.append(region)
                return region
            return None
        
        elif self.strategy == SearchStrategy.DFS:
            # DFS: stay in current region until we have successful templates
            if self.template_stack:
                return self.template_stack[-1]
            
            # If no templates to explore, move to next region
            if self.current_region_index < len(self.regions):
                region = self.regions[self.current_region_index]
                self.template_stack.append(region)
                return region
            
            return None
        
        elif self.strategy == SearchStrategy.HYBRID:
            # Hybrid: alternate between BFS and DFS
            # Use BFS 70% of the time, DFS 30% of the time
            import random
            if random.random() < 0.7:
                # BFS mode
                if self.region_queue:
                    region = self.region_queue.popleft()
                    self.region_queue.append(region)
                    return region
            else:
                # DFS mode
                if self.template_stack:
                    return self.template_stack[-1]
                elif self.region_queue:
                    region = self.region_queue.popleft()
                    self.template_stack.append(region)
                    return region
            
            return None
        
        return None
    
    def add_successful_template(self, template: str, region: str):
        """
        Add successful template for DFS exploration
        
        Args:
            template: Successful template
            region: Region where template succeeded
        """
        if region not in self.successful_templates:
            self.successful_templates[region] = []
        
        if template not in self.successful_templates[region]:
            self.successful_templates[region].append(template)
            logger.debug(f"Added successful template for {region}: {template[:50]}...")
    
    def get_templates_for_deep_exploration(self, region: str, limit: int = 3) -> List[str]:
        """
        Get templates for deep exploration (DFS)
        
        Args:
            region: Region to explore
            limit: Maximum number of templates to return
            
        Returns:
            List of templates to explore deeply
        """
        if self.strategy == SearchStrategy.DFS or self.strategy == SearchStrategy.HYBRID:
            templates = self.successful_templates.get(region, [])
            # Return most recent successful templates
            return templates[-limit:] if templates else []
        
        return []
    
    def advance_region(self):
        """Advance to next region (for DFS)"""
        if self.strategy == SearchStrategy.DFS:
            self.current_region_index = (self.current_region_index + 1) % len(self.regions)
            if self.template_stack:
                self.template_stack.pop()
            if self.current_region_index < len(self.regions):
                self.template_stack.append(self.regions[self.current_region_index])
    
    def get_strategy_info(self) -> Dict:
        """Get current strategy information"""
        return {
            'strategy': self.strategy.value,
            'regions_queued': len(self.region_queue),
            'templates_in_stack': len(self.template_stack),
            'successful_templates_count': sum(len(templates) for templates in self.successful_templates.values()),
            'current_region_index': self.current_region_index
        }
