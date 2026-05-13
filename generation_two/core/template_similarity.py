"""
Template Similarity Checker
Checks similarity between templates to avoid duplicates
"""

import logging
import re
import hashlib
from typing import List, Dict, Set, Tuple
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


class TemplateSimilarityChecker:
    """
    Checks similarity between templates using multiple methods:
    1. String similarity (Levenshtein-like)
    2. Operator overlap
    3. Field overlap
    4. Structural similarity (AST-based)
    """
    
    def __init__(self, similarity_threshold: float = 0.7):
        """
        Initialize similarity checker
        
        Args:
            similarity_threshold: Threshold for considering templates similar (0.0-1.0)
        """
        self.similarity_threshold = similarity_threshold
    
    def extract_operators(self, template: str) -> Set[str]:
        """Extract operator names from template"""
        operators = set()
        
        # Common operators pattern
        operator_patterns = [
            r'\b(ts_\w+)',  # Time series operators (ts_rank, ts_delta, etc.)
            r'\b(winsorize|zscore|rank|delta|correlation|add|subtract|multiply|divide|power|signed_power|abs|log|sqrt|inverse|min|max|sign|reverse)',
            r'\b(vec_\w+)',  # Vector operators
            r'\b(group_\w+)',  # Group operators
        ]
        
        for pattern in operator_patterns:
            matches = re.findall(pattern, template)
            operators.update(matches)
        
        return operators
    
    def extract_fields(self, template: str) -> Set[str]:
        """Extract field IDs from template"""
        fields = set()
        
        # Field pattern: alphanumeric with underscores (like anl49_1stfiscalquarterearningspershare)
        field_pattern = r'\b([a-z][a-z0-9_]{10,})\b'
        matches = re.findall(field_pattern, template)
        
        # Filter out operators and common keywords
        excluded = {
            'ts_rank', 'ts_delta', 'ts_mean', 'ts_std', 'ts_sum', 'ts_min', 'ts_max',
            'winsorize', 'zscore', 'rank', 'delta', 'correlation', 'add', 'subtract',
            'multiply', 'divide', 'power', 'signed_power', 'abs', 'log', 'sqrt', 'inverse',
            'min', 'max', 'sign', 'reverse', 'true', 'false', 'filter'
        }
        
        for match in matches:
            if match not in excluded and len(match) > 10:  # Field IDs are typically long
                fields.add(match)
        
        return fields
    
    def calculate_string_similarity(self, template1: str, template2: str) -> float:
        """Calculate string similarity using SequenceMatcher"""
        return SequenceMatcher(None, template1, template2).ratio()
    
    def calculate_operator_overlap(self, template1: str, template2: str) -> float:
        """Calculate operator overlap ratio"""
        ops1 = self.extract_operators(template1)
        ops2 = self.extract_operators(template2)
        
        if not ops1 and not ops2:
            return 1.0  # Both have no operators
        if not ops1 or not ops2:
            return 0.0  # One has operators, other doesn't
        
        intersection = ops1.intersection(ops2)
        union = ops1.union(ops2)
        
        return len(intersection) / len(union) if union else 0.0
    
    def calculate_field_overlap(self, template1: str, template2: str) -> float:
        """Calculate field overlap ratio"""
        fields1 = self.extract_fields(template1)
        fields2 = self.extract_fields(template2)
        
        if not fields1 and not fields2:
            return 1.0  # Both have no fields
        if not fields1 or not fields2:
            return 0.0  # One has fields, other doesn't
        
        intersection = fields1.intersection(fields2)
        union = fields1.union(fields2)
        
        return len(intersection) / len(union) if union else 0.0
    
    def calculate_structural_similarity(self, template1: str, template2: str) -> float:
        """Calculate structural similarity (operator pattern)"""
        ops1 = sorted(list(self.extract_operators(template1)))
        ops2 = sorted(list(self.extract_operators(template2)))
        
        if not ops1 and not ops2:
            return 1.0
        if not ops1 or not ops2:
            return 0.0
        
        # Compare operator sequences
        ops1_str = '|'.join(ops1)
        ops2_str = '|'.join(ops2)
        
        return SequenceMatcher(None, ops1_str, ops2_str).ratio()
    
    def calculate_similarity(self, template1: str, template2: str) -> float:
        """
        Calculate overall similarity score (0.0-1.0)
        
        Combines multiple similarity metrics:
        - String similarity (40%)
        - Operator overlap (30%)
        - Field overlap (20%)
        - Structural similarity (10%)
        
        Note: Placeholder normalization is applied to ensure OPERATOR1/OPERATOR2/OPERATOR3
        permutations are treated as equivalent.
        """
        # Normalize placeholders before comparison
        normalized1 = self.normalize_placeholders(template1)
        normalized2 = self.normalize_placeholders(template2)
        
        string_sim = self.calculate_string_similarity(normalized1, normalized2)
        operator_sim = self.calculate_operator_overlap(normalized1, normalized2)
        field_sim = self.calculate_field_overlap(normalized1, normalized2)
        structural_sim = self.calculate_structural_similarity(normalized1, normalized2)
        
        # Weighted combination
        overall_sim = (
            string_sim * 0.4 +
            operator_sim * 0.3 +
            field_sim * 0.2 +
            structural_sim * 0.1
        )
        
        return overall_sim
    
    def is_similar(self, template1: str, template2: str) -> bool:
        """Check if two templates are similar"""
        similarity = self.calculate_similarity(template1, template2)
        return similarity >= self.similarity_threshold
    
    def find_similar_templates(
        self, 
        new_template: str, 
        existing_templates: List[str]
    ) -> List[Tuple[str, float]]:
        """
        Find similar templates from a list
        
        Returns:
            List of (template, similarity_score) tuples, sorted by similarity (highest first)
        """
        similar = []
        
        for existing in existing_templates:
            similarity = self.calculate_similarity(new_template, existing)
            if similarity >= self.similarity_threshold:
                similar.append((existing, similarity))
        
        # Sort by similarity (highest first)
        similar.sort(key=lambda x: x[1], reverse=True)
        
        return similar
    
    def normalize_placeholders(self, template: str) -> str:
        """
        Normalize placeholder numbers to canonical form based on occurrence order
        
        Example:
        - OPERATOR3(OPERATOR2(OPERATOR1(DATA_FIELD1))) 
        - OPERATOR1(OPERATOR2(OPERATOR3(DATA_FIELD1)))
        Both become: OPERATOR_A(OPERATOR_B(OPERATOR_C(DATA_FIELD_A)))
        
        This ensures deduplication is not affected by placeholder number permutation.
        The key is to replace by occurrence order (left to right), not by placeholder name.
        """
        normalized = template
        
        # Find all operator placeholder occurrences with their positions
        operator_pattern = r'\bOPERATOR(\d+)\b'
        operator_matches = []
        for match in re.finditer(operator_pattern, normalized, re.IGNORECASE):
            start, end = match.span()
            placeholder = match.group(0).upper()  # OPERATOR1, OPERATOR2, etc.
            operator_matches.append((start, end, placeholder))
        
        # Find all field placeholder occurrences with their positions
        field_pattern = r'\bDATA_FIELD(\d+)\b'
        field_matches = []
        for match in re.finditer(field_pattern, normalized, re.IGNORECASE):
            start, end = match.span()
            placeholder = match.group(0).upper()  # DATA_FIELD1, DATA_FIELD2, etc.
            field_matches.append((start, end, placeholder))
        
        # Sort by position (left to right) to get occurrence order
        operator_matches.sort(key=lambda x: x[0])
        field_matches.sort(key=lambda x: x[0])
        
        # Create replacement mapping: first occurrence -> _A, second -> _B, etc.
        # But we need to replace from right to left to preserve positions
        # So we'll build a list of replacements and apply them in reverse order
        
        operator_replacements = []
        for idx, (start, end, original) in enumerate(operator_matches):
            canonical = f"OPERATOR_{chr(65 + idx)}"  # A, B, C, D, ...
            operator_replacements.append((start, end, original, canonical))
        
        field_replacements = []
        for idx, (start, end, original) in enumerate(field_matches):
            canonical = f"DATA_FIELD_{chr(65 + idx)}"  # A, B, C, D, ...
            field_replacements.append((start, end, original, canonical))
        
        # Combine and sort by position (right to left for replacement)
        all_replacements = operator_replacements + field_replacements
        all_replacements.sort(key=lambda x: x[0], reverse=True)  # Right to left
        
        # Apply replacements from right to left to preserve positions
        for start, end, original, canonical in all_replacements:
            normalized = normalized[:start] + canonical + normalized[end:]
        
        return normalized
    
    def get_template_hash(self, template: str) -> str:
        """Get hash of template for quick duplicate detection"""
        # Normalize placeholders first (OPERATOR1, OPERATOR2 -> OPERATOR_A, OPERATOR_B)
        normalized = self.normalize_placeholders(template)
        
        # Then normalize template (remove extra spaces, lowercase)
        normalized = re.sub(r'\s+', ' ', normalized.strip().lower())
        return hashlib.md5(normalized.encode()).hexdigest()
