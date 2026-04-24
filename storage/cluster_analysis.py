"""
Cluster Analysis Module
Groups similar alphas based on various criteria for analysis
"""

import logging
import json
import sqlite3
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from collections import defaultdict
import hashlib

logger = logging.getLogger(__name__)


@dataclass
class Cluster:
    """A cluster of similar alphas"""
    cluster_id: int
    name: str
    alphas: List[str]  # List of alpha IDs or templates
    centroid: Dict  # Representative alpha or metrics
    size: int
    avg_sharpe: float
    avg_fitness: float
    description: str = ""


class ClusterAnalyzer:
    """
    Analyzes and clusters alphas based on various criteria
    
    Clustering methods:
    - By template similarity (expression structure)
    - By performance metrics (Sharpe, fitness, etc.)
    - By correlation patterns
    - By region and universe
    """
    
    def __init__(self, db_path: str = "generation_two_backtests.db"):
        """
        Initialize cluster analyzer
        
        Args:
            db_path: Path to backtest database
        """
        self.db_path = db_path
    
    def cluster_by_template_similarity(
        self,
        similarity_threshold: float = 0.8,
        min_cluster_size: int = 2
    ) -> List[Cluster]:
        """
        Cluster alphas by template expression similarity
        
        Uses structural similarity of expressions (operators, fields used)
        
        Args:
            similarity_threshold: Minimum similarity to group (0-1)
            min_cluster_size: Minimum alphas per cluster
            
        Returns:
            List of Cluster objects
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get all templates
        cursor.execute("SELECT DISTINCT template, alpha_id FROM backtest_results WHERE success = 1")
        templates = cursor.fetchall()
        conn.close()
        
        if len(templates) < min_cluster_size:
            return []
        
        # Extract features from templates
        template_features = {}
        for template, alpha_id in templates:
            features = self._extract_template_features(template)
            template_features[alpha_id or template] = {
                'template': template,
                'features': features
            }
        
        # Cluster by similarity
        clusters = []
        processed = set()
        cluster_id = 0
        
        for alpha_id, data in template_features.items():
            if alpha_id in processed:
                continue
            
            cluster_members = [alpha_id]
            processed.add(alpha_id)
            
            # Find similar templates
            for other_id, other_data in template_features.items():
                if other_id in processed:
                    continue
                
                similarity = self._calculate_similarity(
                    data['features'],
                    other_data['features']
                )
                
                if similarity >= similarity_threshold:
                    cluster_members.append(other_id)
                    processed.add(other_id)
            
            if len(cluster_members) >= min_cluster_size:
                # Calculate cluster metrics
                cluster_metrics = self._calculate_cluster_metrics(cluster_members)
                
                clusters.append(Cluster(
                    cluster_id=cluster_id,
                    name=f"Template_Cluster_{cluster_id}",
                    alphas=cluster_members,
                    centroid=data,
                    size=len(cluster_members),
                    avg_sharpe=cluster_metrics['avg_sharpe'],
                    avg_fitness=cluster_metrics['avg_fitness'],
                    description=f"Cluster of {len(cluster_members)} similar templates"
                ))
                cluster_id += 1
        
        logger.info(f"Created {len(clusters)} template similarity clusters")
        return clusters
    
    def cluster_by_performance(
        self,
        metric: str = 'sharpe',
        num_clusters: int = 5
    ) -> List[Cluster]:
        """
        Cluster alphas by performance metrics
        
        Args:
            metric: Metric to cluster by ('sharpe', 'fitness', 'pnl', etc.)
            num_clusters: Number of clusters to create
            
        Returns:
            List of Cluster objects
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get all successful alphas with the metric
        cursor.execute(f"""
            SELECT template, alpha_id, {metric}, sharpe, fitness
            FROM backtest_results
            WHERE success = 1 AND {metric} IS NOT NULL
            ORDER BY {metric} DESC
        """)
        results = cursor.fetchall()
        conn.close()
        
        if len(results) < num_clusters:
            num_clusters = len(results)
        
        if num_clusters == 0:
            return []
        
        # Simple k-means-like clustering by value ranges
        clusters = []
        values = [row[2] for row in results]
        min_val = min(values)
        max_val = max(values)
        range_size = (max_val - min_val) / num_clusters if max_val > min_val else 1
        
        for i in range(num_clusters):
            cluster_start = min_val + (i * range_size)
            cluster_end = min_val + ((i + 1) * range_size) if i < num_clusters - 1 else max_val
            
            cluster_members = []
            cluster_sharpes = []
            cluster_fitnesses = []
            
            for row in results:
                value = row[2]
                if cluster_start <= value <= cluster_end:
                    cluster_members.append(row[1] or row[0])
                    cluster_sharpes.append(row[3] or 0.0)
                    cluster_fitnesses.append(row[4] or 0.0)
            
            if cluster_members:
                clusters.append(Cluster(
                    cluster_id=i,
                    name=f"Performance_Cluster_{i}_{metric}",
                    alphas=cluster_members,
                    centroid={'metric': metric, 'range': (cluster_start, cluster_end)},
                    size=len(cluster_members),
                    avg_sharpe=sum(cluster_sharpes) / len(cluster_sharpes) if cluster_sharpes else 0.0,
                    avg_fitness=sum(cluster_fitnesses) / len(cluster_fitnesses) if cluster_fitnesses else 0.0,
                    description=f"Alphas with {metric} in range [{cluster_start:.3f}, {cluster_end:.3f}]"
                ))
        
        logger.info(f"Created {len(clusters)} performance clusters by {metric}")
        return clusters
    
    def cluster_by_correlation(
        self,
        correlation_threshold: float = 0.7
    ) -> List[Cluster]:
        """
        Cluster alphas by correlation patterns
        
        Groups alphas that have similar correlation structures
        
        Args:
            correlation_threshold: Minimum correlation similarity
            
        Returns:
            List of Cluster objects
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get alphas with correlation data
        cursor.execute("""
            SELECT template, alpha_id, correlations, power_pool_corr, prod_corr
            FROM backtest_results
            WHERE success = 1 AND correlations IS NOT NULL AND correlations != ''
        """)
        results = cursor.fetchall()
        conn.close()
        
        if len(results) < 2:
            return []
        
        # Parse correlation data
        alpha_correlations = {}
        for row in results:
            alpha_id = row[1] or row[0]
            try:
                corr_data = json.loads(row[2]) if row[2] else {}
                power_pool = json.loads(row[3]) if row[3] else {}
                prod = json.loads(row[4]) if row[4] else {}
                
                alpha_correlations[alpha_id] = {
                    'template': row[0],
                    'correlations': corr_data,
                    'power_pool': power_pool,
                    'prod': prod
                }
            except:
                continue
        
        # Cluster by correlation similarity
        clusters = []
        processed = set()
        cluster_id = 0
        
        for alpha_id, data in alpha_correlations.items():
            if alpha_id in processed:
                continue
            
            cluster_members = [alpha_id]
            processed.add(alpha_id)
            
            # Find similar correlation patterns
            for other_id, other_data in alpha_correlations.items():
                if other_id in processed:
                    continue
                
                similarity = self._calculate_correlation_similarity(
                    data,
                    other_data
                )
                
                if similarity >= correlation_threshold:
                    cluster_members.append(other_id)
                    processed.add(other_id)
            
            if len(cluster_members) >= 2:
                cluster_metrics = self._calculate_cluster_metrics(cluster_members)
                
                clusters.append(Cluster(
                    cluster_id=cluster_id,
                    name=f"Correlation_Cluster_{cluster_id}",
                    alphas=cluster_members,
                    centroid=data,
                    size=len(cluster_members),
                    avg_sharpe=cluster_metrics['avg_sharpe'],
                    avg_fitness=cluster_metrics['avg_fitness'],
                    description=f"Cluster of {len(cluster_members)} alphas with similar correlations"
                ))
                cluster_id += 1
        
        logger.info(f"Created {len(clusters)} correlation clusters")
        return clusters
    
    def _extract_template_features(self, template: str) -> Dict:
        """Extract features from template expression"""
        import re
        
        # Extract operators
        operators = re.findall(r'([a-z_]+)\s*\(', template.lower())
        operator_counts = defaultdict(int)
        for op in operators:
            operator_counts[op] += 1
        
        # Extract fields (common data fields)
        fields = re.findall(r'\b(close|open|high|low|volume|vwap|returns?|volatility)\b', template.lower())
        field_counts = defaultdict(int)
        for field in fields:
            field_counts[field] += 1
        
        # Calculate complexity metrics
        complexity = len(template)
        nesting_depth = template.count('(')
        
        return {
            'operators': dict(operator_counts),
            'fields': dict(field_counts),
            'complexity': complexity,
            'nesting_depth': nesting_depth,
            'operator_count': len(operators),
            'field_count': len(fields)
        }
    
    def _calculate_similarity(self, features1: Dict, features2: Dict) -> float:
        """Calculate similarity between two feature sets"""
        # Operator similarity
        ops1 = set(features1['operators'].keys())
        ops2 = set(features2['operators'].keys())
        op_similarity = len(ops1 & ops2) / len(ops1 | ops2) if (ops1 | ops2) else 0.0
        
        # Field similarity
        fields1 = set(features1['fields'].keys())
        fields2 = set(features2['fields'].keys())
        field_similarity = len(fields1 & fields2) / len(fields1 | fields2) if (fields1 | fields2) else 0.0
        
        # Complexity similarity
        comp_diff = abs(features1['complexity'] - features2['complexity'])
        max_comp = max(features1['complexity'], features2['complexity'], 1)
        comp_similarity = 1.0 - (comp_diff / max_comp)
        
        # Weighted average
        similarity = (op_similarity * 0.5 + field_similarity * 0.3 + comp_similarity * 0.2)
        return similarity
    
    def _calculate_correlation_similarity(self, data1: Dict, data2: Dict) -> float:
        """Calculate similarity of correlation patterns"""
        # Simple similarity based on correlation structure
        # In production, could use more sophisticated methods
        
        corr1 = data1.get('correlations', {})
        corr2 = data2.get('correlations', {})
        
        keys1 = set(corr1.keys())
        keys2 = set(corr2.keys())
        
        if not (keys1 | keys2):
            return 0.0
        
        key_similarity = len(keys1 & keys2) / len(keys1 | keys2)
        
        # Value similarity for common keys
        value_similarity = 0.0
        common_keys = keys1 & keys2
        if common_keys:
            similarities = []
            for key in common_keys:
                val1 = corr1.get(key, 0)
                val2 = corr2.get(key, 0)
                if isinstance(val1, (int, float)) and isinstance(val2, (int, float)):
                    similarities.append(1.0 - abs(val1 - val2))
            value_similarity = sum(similarities) / len(similarities) if similarities else 0.0
        
        return (key_similarity * 0.6 + value_similarity * 0.4)
    
    def _calculate_cluster_metrics(self, alpha_ids: List[str]) -> Dict:
        """Calculate average metrics for a cluster"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        placeholders = ','.join(['?'] * len(alpha_ids))
        cursor.execute(f"""
            SELECT AVG(sharpe), AVG(fitness), AVG(pnl), COUNT(*)
            FROM backtest_results
            WHERE (alpha_id IN ({placeholders}) OR template IN ({placeholders}))
            AND success = 1
        """, alpha_ids + alpha_ids)
        
        row = cursor.fetchone()
        conn.close()
        
        return {
            'avg_sharpe': row[0] or 0.0,
            'avg_fitness': row[1] or 0.0,
            'avg_pnl': row[2] or 0.0,
            'count': row[3] or 0
        }
    
    def get_cluster_summary(self, clusters: List[Cluster]) -> Dict:
        """Get summary statistics for clusters"""
        if not clusters:
            return {}
        
        return {
            'total_clusters': len(clusters),
            'total_alphas': sum(c.size for c in clusters),
            'avg_cluster_size': sum(c.size for c in clusters) / len(clusters),
            'largest_cluster': max(c.size for c in clusters),
            'smallest_cluster': min(c.size for c in clusters),
            'avg_sharpe': sum(c.avg_sharpe for c in clusters) / len(clusters),
            'avg_fitness': sum(c.avg_fitness for c in clusters) / len(clusters)
        }
