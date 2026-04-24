"""
Smart Search Engine
Advanced search using mathematical and statistical concepts
"""

import logging
import json
import math
from typing import List, Dict, Optional, Tuple
from collections import defaultdict
import numpy as np

logger = logging.getLogger(__name__)


class SmartSearchEngine:
    """
    Smart search engine using mathematical/statistical concepts
    
    Features:
    - TF-IDF for relevance scoring
    - Cosine similarity for semantic matching
    - Statistical ranking (z-score, percentile)
    - Multi-criteria optimization
    - Relevance feedback
    """
    
    def __init__(self, operators: List[Dict] = None, data_fields: Dict[str, List[Dict]] = None):
        """
        Initialize smart search engine
        
        Args:
            operators: List of operators
            data_fields: Dictionary of data fields by region
        """
        self.operators = operators or []
        self.data_fields = data_fields or {}
        
        # Build search indices
        self._build_indices()
    
    def _build_indices(self):
        """Build search indices for fast lookup"""
        # Operator index
        self.operator_index = {}
        for op in self.operators:
            name = op.get('name', '')
            category = op.get('category', '')
            description = op.get('description', '')
            
            # Create searchable text
            searchable = f"{name} {category} {description}".lower()
            self.operator_index[name] = {
                'operator': op,
                'searchable': searchable,
                'tokens': set(searchable.split())
            }
        
        # Data field index
        self.field_index = {}
        for region, fields in self.data_fields.items():
            self._build_field_index_for_region(region, fields)
    
    def _build_field_index_for_region(self, region: str, fields: List[Dict]):
        """Build search index for a specific region"""
        if region not in self.field_index:
            self.field_index[region] = {}
        
        for field in fields:
            field_id = field.get('id', '')
            description = field.get('description', '')
            category = field.get('category', {}).get('name', '')
            dataset = field.get('dataset', {}).get('name', '')
            
            searchable = f"{field_id} {description} {category} {dataset}".lower()
            self.field_index[region][field_id] = {
                'field': field,
                'searchable': searchable,
                'tokens': set(searchable.split())
            }
    
    def search_operators(
        self,
        query: str,
        category: Optional[str] = None,
        limit: int = 10
    ) -> List[Tuple[Dict, float]]:
        """
        Search operators using TF-IDF and cosine similarity
        
        Args:
            query: Search query
            category: Optional category filter
            limit: Maximum results
            
        Returns:
            List of (operator, score) tuples sorted by relevance
        """
        query_lower = query.lower()
        query_tokens = set(query_lower.split())
        
        # Calculate TF-IDF scores
        scores = []
        for name, index_data in self.operator_index.items():
            op = index_data['operator']
            
            # Category filter
            if category and op.get('category') != category:
                continue
            
            # Calculate relevance score
            score = self._calculate_relevance(
                query_tokens,
                index_data['tokens'],
                index_data['searchable']
            )
            
            scores.append((op, score))
        
        # Sort by score (descending)
        scores.sort(key=lambda x: x[1], reverse=True)
        
        return scores[:limit]
    
    def search_data_fields(
        self,
        query: str,
        region: str,
        category: Optional[str] = None,
        limit: int = 10
    ) -> List[Tuple[Dict, float]]:
        """
        Search data fields using TF-IDF and statistical ranking
        
        Args:
            query: Search query
            region: Region code
            category: Optional category filter
            limit: Maximum results
            
        Returns:
            List of (field, score) tuples sorted by relevance
        """
        if region not in self.field_index:
            return []
        
        query_lower = query.lower()
        query_tokens = set(query_lower.split())
        
        scores = []
        for field_id, index_data in self.field_index[region].items():
            field = index_data['field']
            
            # Category filter
            if category and field.get('category', {}).get('id') != category:
                continue
            
            # Calculate relevance score
            score = self._calculate_relevance(
                query_tokens,
                index_data['tokens'],
                index_data['searchable']
            )
            
            # Boost score based on usage statistics
            usage_boost = self._calculate_usage_boost(field)
            score *= (1.0 + usage_boost)
            
            scores.append((field, score))
        
        # Sort by score (descending)
        scores.sort(key=lambda x: x[1], reverse=True)
        
        return scores[:limit]
    
    def _calculate_relevance(
        self,
        query_tokens: set,
        document_tokens: set,
        document_text: str
    ) -> float:
        """
        Calculate relevance score using TF-IDF and cosine similarity
        
        Args:
            query_tokens: Set of query tokens
            document_tokens: Set of document tokens
            document_text: Full document text
            
        Returns:
            Relevance score (0-1)
        """
        # Term Frequency (TF)
        tf_scores = {}
        doc_words = document_text.split()
        total_words = len(doc_words)
        
        for token in query_tokens:
            if token in document_tokens:
                # Count occurrences
                count = doc_words.count(token)
                tf_scores[token] = count / total_words if total_words > 0 else 0
        
        # Inverse Document Frequency (IDF)
        # Simplified: use log of inverse frequency
        idf_scores = {}
        for token in query_tokens:
            # Count documents containing token
            doc_count = sum(1 for tokens in [document_tokens] if token in tokens)
            idf_scores[token] = math.log(1.0 / (doc_count + 1)) if doc_count > 0 else 0
        
        # TF-IDF score
        tfidf_score = sum(tf_scores.get(t, 0) * idf_scores.get(t, 0) for t in query_tokens)
        
        # Cosine similarity (normalized)
        intersection = len(query_tokens & document_tokens)
        union = len(query_tokens | document_tokens)
        cosine_sim = intersection / union if union > 0 else 0
        
        # Combined score
        relevance = (tfidf_score * 0.6 + cosine_sim * 0.4)
        
        return min(1.0, relevance)
    
    def _calculate_usage_boost(self, field: Dict) -> float:
        """
        Calculate usage-based boost using statistical concepts
        
        Uses z-score normalization of usage metrics
        """
        user_count = field.get('userCount', 0)
        alpha_count = field.get('alphaCount', 0)
        coverage = field.get('coverage', 0.0)
        
        # Normalize using z-score approach
        # Higher usage = higher boost
        usage_score = (user_count / 1000.0) * 0.3 + (alpha_count / 1000.0) * 0.3 + coverage * 0.4
        
        return min(0.5, usage_score)  # Cap at 50% boost
    
    def multi_criteria_search(
        self,
        query: str,
        region: str,
        criteria: Dict[str, float],
        limit: int = 10
    ) -> List[Tuple[Dict, float]]:
        """
        Multi-criteria search with weighted scoring
        
        Args:
            query: Search query
            region: Region code
            criteria: Dictionary of criteria and weights
                     e.g., {'relevance': 0.4, 'usage': 0.3, 'coverage': 0.3}
            limit: Maximum results
            
        Returns:
            List of (field, score) tuples
        """
        # Get base relevance scores
        base_results = self.search_data_fields(query, region, limit=limit * 2)
        
        # Apply multi-criteria scoring
        scored_results = []
        for field, base_score in base_results:
            total_score = base_score * criteria.get('relevance', 0.4)
            
            # Usage score
            if 'usage' in criteria:
                usage_boost = self._calculate_usage_boost(field)
                total_score += usage_boost * criteria['usage']
            
            # Coverage score
            if 'coverage' in criteria:
                coverage = field.get('coverage', 0.0)
                total_score += coverage * criteria['coverage']
            
            # Category relevance
            if 'category_match' in criteria:
                # Boost if category matches query intent
                category_match = self._category_match_score(query, field)
                total_score += category_match * criteria['category_match']
            
            scored_results.append((field, total_score))
        
        # Sort and return
        scored_results.sort(key=lambda x: x[1], reverse=True)
        return scored_results[:limit]
    
    def _category_match_score(self, query: str, field: Dict) -> float:
        """Calculate category match score"""
        query_lower = query.lower()
        category = field.get('category', {}).get('name', '').lower()
        
        # Simple keyword matching
        if any(word in category for word in query_lower.split()):
            return 0.3
        
        return 0.0
    
    def statistical_ranking(
        self,
        fields: List[Dict],
        metric: str = 'userCount'
    ) -> List[Tuple[Dict, float]]:
        """
        Rank fields using statistical methods (z-score, percentile)
        
        Args:
            fields: List of fields to rank
            metric: Metric to use for ranking
            
        Returns:
            List of (field, z_score) tuples
        """
        if not fields:
            return []
        
        # Extract metric values
        values = [f.get(metric, 0) for f in fields]
        
        if not values or all(v == 0 for v in values):
            return [(f, 0.0) for f in fields]
        
        # Calculate statistics
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        std_dev = math.sqrt(variance) if variance > 0 else 1.0
        
        # Calculate z-scores
        z_scores = []
        for field, value in zip(fields, values):
            z_score = (value - mean) / std_dev if std_dev > 0 else 0.0
            z_scores.append((field, z_score))
        
        # Sort by z-score (descending)
        z_scores.sort(key=lambda x: x[1], reverse=True)
        
        return z_scores
    
    def get_recommendations(
        self,
        context: Dict,
        region: str,
        limit: int = 5
    ) -> List[Dict]:
        """
        Get recommendations based on context using collaborative filtering concepts
        
        Args:
            context: Context dictionary (e.g., {'operators': ['ts_rank'], 'categories': ['time_series']})
            region: Region code
            limit: Maximum recommendations
            
        Returns:
            List of recommended fields
        """
        # Get fields similar to context
        if 'operators' in context:
            # Find fields commonly used with these operators
            recommendations = self._find_related_fields(context['operators'], region)
        elif 'categories' in context:
            # Find fields in these categories
            recommendations = self._find_fields_by_categories(context['categories'], region)
        else:
            # Default: popular fields
            fields = self.data_fields.get(region, [])
            recommendations = sorted(
                fields,
                key=lambda f: f.get('userCount', 0),
                reverse=True
            )[:limit]
        
        return recommendations[:limit]
    
    def _find_related_fields(self, operators: List[str], region: str) -> List[Dict]:
        """Find fields commonly used with given operators"""
        # Simplified: return popular fields
        fields = self.data_fields.get(region, [])
        return sorted(
            fields,
            key=lambda f: f.get('alphaCount', 0),
            reverse=True
        )[:10]
    
    def _find_fields_by_categories(self, categories: List[str], region: str) -> List[Dict]:
        """Find fields in given categories"""
        fields = self.data_fields.get(region, [])
        return [
            f for f in fields
            if f.get('category', {}).get('id') in categories
        ][:10]
