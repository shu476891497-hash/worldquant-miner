"""
Duplicate Detection System for Ollama
Prevents generating duplicate or very similar alpha expressions
"""

import logging
import hashlib
import sqlite3
import json
from typing import List, Dict, Optional, Set
from dataclasses import dataclass
import re

logger = logging.getLogger(__name__)


@dataclass
class ExpressionSignature:
    """Signature of an alpha expression for duplicate detection"""
    template: str
    normalized: str  # Normalized version for comparison
    hash: str  # Hash for quick lookup
    operators: Set[str]  # Set of operators used
    structure_hash: str  # Hash of expression structure


class DuplicateDetector:
    """
    Detects and prevents duplicate alpha expressions
    
    Features:
    - Normalizes expressions for comparison
    - Tracks all generated expressions
    - Provides context to Ollama to avoid duplicates
    - Supports similarity threshold
    """
    
    def __init__(self, db_path: str = "generation_two_backtests.db"):
        """
        Initialize duplicate detector
        
        Args:
            db_path: Path to database for storing expression history
        """
        self.db_path = db_path
        self._init_database()
        self._memory_cache: Dict[str, ExpressionSignature] = {}
        self.similarity_threshold = 0.85  # Expressions with >85% similarity are considered duplicates
    
    def _init_database(self):
        """Initialize database for expression tracking"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS expression_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                template TEXT NOT NULL,
                normalized TEXT NOT NULL,
                template_hash TEXT NOT NULL UNIQUE,
                structure_hash TEXT NOT NULL,
                operators TEXT,
                region TEXT,
                timestamp REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_template_hash ON expression_history(template_hash)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_structure_hash ON expression_history(structure_hash)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_normalized ON expression_history(normalized)")
        
        conn.commit()
        conn.close()
    
    def normalize_expression(self, expression: str) -> str:
        """
        Normalize expression for comparison
        
        Removes whitespace, normalizes operator names, etc.
        """
        # Remove all whitespace
        normalized = re.sub(r'\s+', '', expression)
        
        # Normalize common variations
        normalized = normalized.lower()
        
        # Remove comments if any
        normalized = re.sub(r'//.*', '', normalized)
        
        return normalized
    
    def extract_structure(self, expression: str) -> str:
        """
        Extract structure of expression (operators and nesting, not values)
        
        Example: ts_rank(close, 20) -> ts_rank(_, _)
        """
        # Replace numbers with placeholder
        structure = re.sub(r'\d+\.?\d*', '_', expression)
        
        # Replace common field names with placeholder
        common_fields = ['close', 'open', 'high', 'low', 'volume', 'vwap', 'returns', 'volatility']
        for field in common_fields:
            structure = re.sub(rf'\b{field}\b', '_', structure, flags=re.IGNORECASE)
        
        return structure
    
    def create_signature(self, expression: str) -> ExpressionSignature:
        """Create signature for an expression"""
        normalized = self.normalize_expression(expression)
        structure = self.extract_structure(expression)
        
        # Extract operators
        operators = set(re.findall(r'([a-z_]+)\s*\(', expression.lower()))
        
        # Create hashes
        template_hash = hashlib.md5(normalized.encode()).hexdigest()
        structure_hash = hashlib.md5(structure.encode()).hexdigest()
        
        return ExpressionSignature(
            template=expression,
            normalized=normalized,
            hash=template_hash,
            operators=operators,
            structure_hash=structure_hash
        )
    
    def is_duplicate(self, expression: str) -> bool:
        """
        Check if expression is a duplicate
        
        Args:
            expression: Alpha expression to check
            
        Returns:
            True if duplicate, False otherwise
        """
        signature = self.create_signature(expression)
        
        # Check memory cache first
        if signature.hash in self._memory_cache:
            return True
        
        # Check database
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Check exact match
        cursor.execute("SELECT id FROM expression_history WHERE template_hash = ?", (signature.hash,))
        if cursor.fetchone():
            conn.close()
            self._memory_cache[signature.hash] = signature
            return True
        
        # Check structure similarity
        cursor.execute("""
            SELECT template, normalized FROM expression_history
            WHERE structure_hash = ?
        """, (signature.structure_hash,))
        
        similar = cursor.fetchall()
        conn.close()
        
        if similar:
            # Check similarity with existing expressions
            for existing_template, existing_normalized in similar:
                similarity = self._calculate_similarity(
                    signature.normalized,
                    existing_normalized
                )
                if similarity >= self.similarity_threshold:
                    logger.debug(f"Found similar expression: {similarity:.2%} similarity")
                    return True
        
        return False
    
    def register_expression(self, expression: str, region: str = ""):
        """
        Register a new expression (mark as used)
        
        Args:
            expression: Alpha expression
            region: Region where it was generated
        """
        import time
        
        signature = self.create_signature(expression)
        
        # Add to memory cache
        self._memory_cache[signature.hash] = signature
        
        # Store in database
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT OR IGNORE INTO expression_history
                (template, normalized, template_hash, structure_hash, operators, region, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                expression,
                signature.normalized,
                signature.hash,
                signature.structure_hash,
                json.dumps(list(signature.operators)),
                region,
                time.time()
            ))
            
            conn.commit()
            conn.close()
            
            logger.debug(f"Registered expression: {expression[:50]}...")
        except sqlite3.IntegrityError:
            # Already exists
            pass
        except Exception as e:
            logger.error(f"Error registering expression: {e}")
    
    def get_avoidance_context(self, limit: int = 10) -> str:
        """
        Get context string for Ollama to avoid generating duplicates
        
        Returns a string listing recent expressions to avoid
        
        Args:
            limit: Number of recent expressions to include
            
        Returns:
            Context string for Ollama prompt
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT DISTINCT template FROM expression_history
            ORDER BY timestamp DESC
            LIMIT ?
        """, (limit,))
        
        recent = cursor.fetchall()
        conn.close()
        
        if not recent:
            return ""
        
        expressions = [row[0] for row in recent]
        
        context = "Avoid generating expressions similar to these recent ones:\n"
        for i, expr in enumerate(expressions, 1):
            context += f"{i}. {expr}\n"
        
        return context
    
    def get_operator_statistics(self) -> Dict[str, int]:
        """Get statistics on operator usage"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT operators FROM expression_history")
        rows = cursor.fetchall()
        conn.close()
        
        operator_counts = {}
        for row in rows:
            try:
                operators = json.loads(row[0]) if row[0] else []
                for op in operators:
                    operator_counts[op] = operator_counts.get(op, 0) + 1
            except:
                continue
        
        return operator_counts
    
    def _calculate_similarity(self, expr1: str, expr2: str) -> float:
        """Calculate similarity between two normalized expressions"""
        # Simple character-based similarity
        # Could be enhanced with more sophisticated methods
        
        if expr1 == expr2:
            return 1.0
        
        # Levenshtein-like similarity
        len1, len2 = len(expr1), len(expr2)
        max_len = max(len1, len2)
        
        if max_len == 0:
            return 1.0
        
        # Count common characters in order
        common = 0
        min_len = min(len1, len2)
        for i in range(min_len):
            if expr1[i] == expr2[i]:
                common += 1
        
        # Also check for common substrings
        common_substrings = 0
        for i in range(min_len - 2):
            substr = expr1[i:i+3]
            if substr in expr2:
                common_substrings += 1
        
        similarity = (common / max_len) * 0.7 + (common_substrings / max(min_len - 2, 1)) * 0.3
        return similarity
    
    def get_statistics(self) -> Dict:
        """Get duplicate detection statistics"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM expression_history")
        total = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(DISTINCT structure_hash) FROM expression_history")
        unique_structures = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            'total_expressions': total,
            'unique_structures': unique_structures,
            'duplicate_rate': 1.0 - (unique_structures / total) if total > 0 else 0.0,
            'cached_signatures': len(self._memory_cache)
        }
