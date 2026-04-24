"""
Duplicate Detector for Continuous Mining
Detects and filters duplicate templates to reduce redundant simulations
"""

import logging
import sqlite3
from typing import List, Dict, Set, Tuple, Optional
from ..template_similarity import TemplateSimilarityChecker

logger = logging.getLogger(__name__)


class MiningDuplicateDetector:
    """
    Detects duplicates for continuous mining using multiple strategies:
    1. Exact template matching
    2. Template similarity (using TemplateSimilarityChecker)
    3. Hash-based duplicate detection
    """
    
    def __init__(self, db_path: str = "generation_two_backtests.db", similarity_threshold: float = 0.85):
        """
        Initialize duplicate detector
        
        Args:
            db_path: Path to database
            similarity_threshold: Threshold for considering templates similar (0.0-1.0)
        """
        self.db_path = db_path
        self.similarity_checker = TemplateSimilarityChecker(similarity_threshold=similarity_threshold)
        self._seen_templates: Set[str] = set()  # In-memory cache of seen templates
        self._template_hashes: Set[str] = set()  # In-memory cache of template hashes
    
    def is_duplicate(self, template: str, region: str = None) -> Tuple[bool, Optional[str]]:
        """
        Check if template is a duplicate
        
        Args:
            template: Template to check
            region: Optional region filter
            
        Returns:
            Tuple of (is_duplicate, reason)
        """
        # Normalize template
        normalized = self._normalize_template(template)
        
        # Check in-memory cache first
        if normalized in self._seen_templates:
            return True, "Exact match in memory cache"
        
        # Check hash
        template_hash = self.similarity_checker.get_template_hash(normalized)
        if template_hash in self._template_hashes:
            return True, "Hash match in memory cache"
        
        # Check database
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Check exact match
            if region:
                cursor.execute('''
                    SELECT template FROM backtest_results
                    WHERE template = ? AND region = ?
                    LIMIT 1
                ''', (normalized, region))
            else:
                cursor.execute('''
                    SELECT template FROM backtest_results
                    WHERE template = ?
                    LIMIT 1
                ''', (normalized,))
            
            if cursor.fetchone():
                conn.close()
                self._seen_templates.add(normalized)
                return True, "Exact match in database"
            
            # Check hash in database
            cursor.execute('''
                SELECT template FROM generated_templates
                WHERE template_hash = ?
                LIMIT 1
            ''', (template_hash,))
            
            if cursor.fetchone():
                conn.close()
                self._template_hashes.add(template_hash)
                return True, "Hash match in database"
            
            # Check similarity (only for successful templates to avoid false positives)
            if region:
                cursor.execute('''
                    SELECT template FROM backtest_results
                    WHERE region = ? AND success = 1
                    LIMIT 100
                ''', (region,))
            else:
                cursor.execute('''
                    SELECT template FROM backtest_results
                    WHERE success = 1
                    LIMIT 100
                ''')
            
            existing_templates = [row[0] for row in cursor.fetchall() if row[0]]
            conn.close()
            
            if existing_templates:
                similar = self.similarity_checker.find_similar_templates(normalized, existing_templates)
                if similar:
                    return True, f"Similar to existing template (similarity: {similar[0][1]:.2f})"
            
            # Not a duplicate
            self._seen_templates.add(normalized)
            self._template_hashes.add(template_hash)
            return False, None
            
        except Exception as e:
            logger.debug(f"Error checking duplicate: {e}")
            return False, None  # On error, allow template (conservative)
    
    def filter_duplicates(
        self,
        templates: List[Tuple[str, str]],  # List of (template, region) tuples
        max_similarity: float = 0.85
    ) -> List[Tuple[str, str]]:
        """
        Filter duplicates from a list of templates
        
        Args:
            templates: List of (template, region) tuples
            max_similarity: Maximum acceptable similarity
            
        Returns:
            Filtered list of (template, region) tuples
        """
        filtered = []
        seen_hashes = set()
        
        for template, region in templates:
            # Check if duplicate
            is_dup, reason = self.is_duplicate(template, region)
            if not is_dup:
                # Also check against already filtered templates in this batch
                template_hash = self.similarity_checker.get_template_hash(self._normalize_template(template))
                if template_hash not in seen_hashes:
                    # Check similarity with already filtered templates
                    is_similar = False
                    for existing_template, _ in filtered:
                        similarity = self.similarity_checker.calculate_similarity(
                            self._normalize_template(template),
                            self._normalize_template(existing_template)
                        )
                        if similarity >= max_similarity:
                            is_similar = True
                            break
                    
                    if not is_similar:
                        filtered.append((template, region))
                        seen_hashes.add(template_hash)
        
        return filtered
    
    def _normalize_template(self, template: str) -> str:
        """
        Normalize template for comparison
        
        This includes:
        1. Placeholder normalization (OPERATOR1/OPERATOR2/OPERATOR3 -> OPERATOR_A/OPERATOR_B/OPERATOR_C)
        2. Whitespace normalization
        """
        import re
        # First normalize placeholders to handle permutations
        normalized = self.similarity_checker.normalize_placeholders(template)
        # Then remove extra whitespace
        normalized = re.sub(r'\s+', ' ', normalized.strip())
        return normalized
    
    def load_seen_templates(self, limit: int = 1000):
        """Load seen templates from database into memory cache"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Load from backtest_results
            cursor.execute('''
                SELECT DISTINCT template FROM backtest_results
                LIMIT ?
            ''', (limit,))
            
            for row in cursor.fetchall():
                if row[0]:
                    normalized = self._normalize_template(row[0])
                    self._seen_templates.add(normalized)
                    template_hash = self.similarity_checker.get_template_hash(normalized)
                    self._template_hashes.add(template_hash)
            
            # Load from generated_templates
            cursor.execute('''
                SELECT DISTINCT template_hash FROM generated_templates
                LIMIT ?
            ''', (limit,))
            
            for row in cursor.fetchall():
                if row[0]:
                    self._template_hashes.add(row[0])
            
            conn.close()
            logger.info(f"Loaded {len(self._seen_templates)} seen templates and {len(self._template_hashes)} hashes into cache")
            
        except Exception as e:
            logger.debug(f"Error loading seen templates: {e}")
