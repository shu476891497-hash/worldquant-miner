"""
Backtest Storage Module
Handles storage and retrieval of backtest results
"""

import logging
import json
import sqlite3
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class BacktestRecord:
    """Record of a backtest result with comprehensive data"""
    template: str
    region: str
    # Core metrics
    sharpe: float
    fitness: float
    turnover: float
    returns: float
    drawdown: float
    margin: float
    longCount: int
    shortCount: int
    # Additional metrics
    pnl: float = 0.0
    volatility: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    avg_return: float = 0.0
    # Correlation and check data (stored as JSON strings)
    correlations: str = ""
    power_pool_corr: str = ""
    prod_corr: str = ""
    checks: str = ""
    # Status
    success: bool = True
    timestamp: float = 0.0
    alpha_id: str = ""
    error_message: str = ""
    # Raw data
    raw_data: str = ""


class BacktestStorage:
    """
    Storage for backtest results
    
    Separated from simulation logic for modularity and persistence.
    """
    
    def __init__(self, db_path: str = "generation_two_backtests.db"):
        """
        Initialize backtest storage
        
        Args:
            db_path: Path to SQLite database (defaults to "generation_two_backtests.db")
        """
        self.db_path = db_path
        self.create_tables()
    
    def create_tables(self):
        """Create database tables"""
        # Use a flag to only log once per database file
        import os
        log_file = f"{self.db_path}.tables_created"
        already_logged = os.path.exists(log_file)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS backtest_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                template TEXT NOT NULL,
                region TEXT NOT NULL,
                sharpe REAL,
                fitness REAL,
                turnover REAL,
                returns REAL,
                drawdown REAL,
                margin REAL,
                longCount INTEGER,
                shortCount INTEGER,
                pnl REAL,
                volatility REAL,
                max_drawdown REAL,
                win_rate REAL,
                avg_return REAL,
                correlations TEXT,
                power_pool_corr TEXT,
                prod_corr TEXT,
                checks TEXT,
                success INTEGER,
                alpha_id TEXT,
                error_message TEXT,
                timestamp REAL,
                raw_data TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Index for faster queries
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_template ON backtest_results(template)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_region ON backtest_results(region)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_sharpe ON backtest_results(sharpe)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_fitness ON backtest_results(fitness)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_pnl ON backtest_results(pnl)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_success ON backtest_results(success)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON backtest_results(timestamp)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_alpha_id ON backtest_results(alpha_id)')
        
        # Create field types table for storing field type information (including event inputs)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS field_types (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                field_id TEXT NOT NULL,
                region TEXT NOT NULL,
                delay INTEGER NOT NULL,
                field_type TEXT,
                is_event_input INTEGER DEFAULT 0,
                category TEXT,
                dataset_id TEXT,
                field_data TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(field_id, region, delay)
            )
        ''')
        
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_field_id ON field_types(field_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_field_region_delay ON field_types(region, delay)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_is_event_input ON field_types(is_event_input)')
        
        # Create templates table for storing generated templates
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS generated_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                template TEXT NOT NULL,
                region TEXT NOT NULL,
                template_hash TEXT,
                operators_used TEXT,
                fields_used TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(template, region)
            )
        ''')
        
        # Index for faster similarity queries
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_template_hash ON generated_templates(template_hash)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_template_region ON generated_templates(region)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_template_text ON generated_templates(template)')
        
        # Create compiler knowledge table for storing learned compiler logic
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS compiler_knowledge (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                knowledge_type TEXT NOT NULL,
                operator_name TEXT,
                field_type TEXT,
                compatibility_status TEXT,
                error_message TEXT,
                learned_from_template TEXT,
                learned_from_error TEXT,
                replacement_operator TEXT,
                ast_pattern TEXT,
                compiler_rule TEXT,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Indexes for compiler knowledge
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_knowledge_type ON compiler_knowledge(knowledge_type)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_operator_name ON compiler_knowledge(operator_name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_compatibility ON compiler_knowledge(compatibility_status)')
        
        # Create AST patterns table for storing learned AST structures
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ast_patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern_type TEXT NOT NULL,
                pattern_structure TEXT NOT NULL,
                operator_sequence TEXT,
                field_types TEXT,
                success_count INTEGER DEFAULT 0,
                failure_count INTEGER DEFAULT 0,
                example_template TEXT,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used_at TIMESTAMP
            )
        ''')
        
        # Indexes for AST patterns
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_pattern_type ON ast_patterns(pattern_type)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_success_count ON ast_patterns(success_count)')
        
        conn.commit()
        conn.close()
        
        # Only log once per database file to reduce spew
        import os
        log_file = f"{self.db_path}.tables_created"
        already_logged = os.path.exists(log_file)
        if not already_logged:
            logger.debug("Backtest storage tables created")
            # Create a marker file to indicate we've logged
            try:
                with open(log_file, 'w') as f:
                    f.write('')
            except:
                pass  # Ignore if we can't create the marker file
    
    def store_result(self, result) -> bool:
        """
        Store a backtest result
        
        Args:
            result: SimulationResult or BacktestRecord
            
        Returns:
            True if successful
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Handle both SimulationResult and BacktestRecord
            if hasattr(result, 'template'):
                template = result.template
                region = result.region
                sharpe = getattr(result, 'sharpe', 0.0)
                fitness = getattr(result, 'fitness', 0.0)
                turnover = getattr(result, 'turnover', 0.0)
                returns = getattr(result, 'returns', 0.0)
                drawdown = getattr(result, 'drawdown', 0.0)
                margin = getattr(result, 'margin', 0.0)
                longCount = getattr(result, 'longCount', 0)
                shortCount = getattr(result, 'shortCount', 0)
                pnl = getattr(result, 'pnl', 0.0)
                volatility = getattr(result, 'volatility', 0.0)
                max_drawdown = getattr(result, 'max_drawdown', 0.0)
                win_rate = getattr(result, 'win_rate', 0.0)
                avg_return = getattr(result, 'avg_return', 0.0)
                correlations = getattr(result, 'correlations', '')
                power_pool_corr = getattr(result, 'power_pool_corr', '')
                prod_corr = getattr(result, 'prod_corr', '')
                checks = getattr(result, 'checks', '')
                success = getattr(result, 'success', False)
                alpha_id = getattr(result, 'alpha_id', '')
                error_message = getattr(result, 'error_message', '')
                timestamp = getattr(result, 'timestamp', 0.0)
                raw_data = getattr(result, 'raw_data', '')
            else:
                # Dictionary
                template = result.get('template', '')
                region = result.get('region', '')
                sharpe = result.get('sharpe', 0.0)
                fitness = result.get('fitness', 0.0)
                turnover = result.get('turnover', 0.0)
                returns = result.get('returns', 0.0)
                drawdown = result.get('drawdown', 0.0)
                margin = result.get('margin', 0.0)
                longCount = result.get('longCount', 0)
                shortCount = result.get('shortCount', 0)
                pnl = result.get('pnl', 0.0)
                volatility = result.get('volatility', 0.0)
                max_drawdown = result.get('max_drawdown', 0.0)
                win_rate = result.get('win_rate', 0.0)
                avg_return = result.get('avg_return', 0.0)
                correlations = result.get('correlations', '')
                power_pool_corr = result.get('power_pool_corr', '')
                prod_corr = result.get('prod_corr', '')
                checks = result.get('checks', '')
                success = result.get('success', False)
                alpha_id = result.get('alpha_id', '')
                error_message = result.get('error_message', '')
                timestamp = result.get('timestamp', 0.0)
                raw_data = result.get('raw_data', '')
            
            cursor.execute('''
                INSERT INTO backtest_results 
                (template, region, sharpe, fitness, turnover, returns, drawdown, 
                 margin, longCount, shortCount, pnl, volatility, max_drawdown, 
                 win_rate, avg_return, correlations, power_pool_corr, prod_corr, 
                 checks, success, alpha_id, error_message, timestamp, raw_data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                template, region, sharpe, fitness, turnover, returns, drawdown,
                margin, longCount, shortCount, pnl, volatility, max_drawdown,
                win_rate, avg_return, correlations, power_pool_corr, prod_corr,
                checks, 1 if success else 0, alpha_id, error_message, timestamp, raw_data
            ))
            
            conn.commit()
            conn.close()
            
            logger.debug(f"Stored backtest result: {template[:50]}... (Sharpe={sharpe:.3f})")
            return True
            
        except Exception as e:
            logger.error(f"Error storing backtest result: {e}")
            return False
    
    def store_template(self, template: str, region: str, operators_used: List[str] = None, fields_used: List[str] = None) -> bool:
        """
        Store a generated template
        
        Args:
            template: Template expression
            region: Region code
            operators_used: List of operators in template
            fields_used: List of fields in template
            
        Returns:
            True if successful
        """
        try:
            from ..core.template_similarity import TemplateSimilarityChecker
            similarity_checker = TemplateSimilarityChecker()
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Get template hash
            template_hash = similarity_checker.get_template_hash(template)
            
            # Store operators and fields as JSON strings
            operators_json = json.dumps(operators_used) if operators_used else ""
            fields_json = json.dumps(fields_used) if fields_used else ""
            
            cursor.execute('''
                INSERT OR IGNORE INTO generated_templates 
                (template, region, template_hash, operators_used, fields_used)
                VALUES (?, ?, ?, ?, ?)
            ''', (template, region, template_hash, operators_json, fields_json))
            
            conn.commit()
            conn.close()
            
            logger.debug(f"Stored template: {template[:50]}... for {region}")
            return True
            
        except Exception as e:
            logger.error(f"Error storing template: {e}")
            return False
    
    def get_all_templates(self, region: str = None, limit: int = None) -> List[str]:
        """
        Get stored templates (with optional limit for performance)
        
        Args:
            region: Optional region filter
            limit: Optional limit on number of templates to return (for performance)
            
        Returns:
            List of template strings
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            query = 'SELECT template FROM generated_templates'
            params = []
            
            if region:
                query += ' WHERE region = ?'
                params.append(region)
            
            query += ' ORDER BY created_at DESC'  # Get most recent first
            
            if limit:
                query += ' LIMIT ?'
                params.append(limit)
            
            cursor.execute(query, params)
            templates = [row[0] for row in cursor.fetchall()]
            conn.close()
            
            return templates
            
        except Exception as e:
            logger.error(f"Error getting templates: {e}")
            return []
    
    def get_unsimulated_templates(self, region: str = None, limit: int = None) -> List[Tuple[str, str]]:
        """
        Get templates that haven't been simulated yet (not in backtest_results)
        
        Args:
            region: Optional region filter
            limit: Optional limit on number of templates to return
            
        Returns:
            List of (template, region) tuples for templates that haven't been simulated
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Get templates that exist in generated_templates but not in backtest_results
            query = '''
                SELECT DISTINCT gt.template, gt.region
                FROM generated_templates gt
                LEFT JOIN backtest_results br ON gt.template = br.template AND gt.region = br.region
                WHERE br.template IS NULL
            '''
            params = []
            
            if region:
                query += ' AND gt.region = ?'
                params.append(region)
            
            query += ' ORDER BY gt.created_at DESC'
            
            if limit:
                query += ' LIMIT ?'
                params.append(limit)
            
            cursor.execute(query, params)
            templates = [(row[0], row[1]) for row in cursor.fetchall()]
            conn.close()
            
            return templates
            
        except Exception as e:
            logger.error(f"Error getting unsimulated templates: {e}")
            return []
    
    def has_been_simulated(self, template: str, region: str) -> bool:
        """
        Check if a template has been simulated (exists in backtest_results)
        
        Args:
            template: Template expression
            region: Region code
            
        Returns:
            True if template has been simulated, False otherwise
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT COUNT(*) FROM backtest_results
                WHERE template = ? AND region = ?
            ''', (template, region))
            
            count = cursor.fetchone()[0]
            conn.close()
            
            return count > 0
            
        except Exception as e:
            logger.error(f"Error checking if template has been simulated: {e}")
            return False
    
    def get_recently_used_fields(self, region: str, limit: int = 50, lookback_hours: int = 24) -> List[str]:
        """
        Get recently used data fields for a region to avoid repetition
        
        Args:
            region: Region code
            limit: Maximum number of recent fields to return
            lookback_hours: How many hours back to look (default: 24 hours)
            
        Returns:
            List of field IDs that were recently used
        """
        try:
            import time
            import re
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            recently_used_fields = set()
            
            # From generated_templates (includes all generated templates)
            cursor.execute('''
                SELECT fields_used FROM generated_templates
                WHERE region = ? AND created_at >= datetime('now', '-' || ? || ' hours')
                ORDER BY created_at DESC
                LIMIT ?
            ''', (region, lookback_hours, limit * 2))  # Get more to account for multiple fields per template
            
            for row in cursor.fetchall():
                if row[0]:
                    try:
                        fields = json.loads(row[0])
                        if isinstance(fields, list):
                            recently_used_fields.update([f.lower() for f in fields if f])
                    except:
                        pass
            
            # From backtest_results (extract fields from templates)
            cutoff_time = time.time() - (lookback_hours * 3600)
            cursor.execute('''
                SELECT template FROM backtest_results
                WHERE region = ? AND timestamp >= ?
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (region, cutoff_time, limit * 2))
            
            # Extract field IDs from templates using regex
            excluded = {
                'ts_rank', 'ts_delta', 'ts_mean', 'ts_std', 'ts_sum', 'ts_min', 'ts_max',
                'winsorize', 'zscore', 'rank', 'delta', 'correlation', 'add', 'subtract',
                'multiply', 'divide', 'power', 'signed_power', 'abs', 'log', 'sqrt', 'inverse',
                'min', 'max', 'sign', 'reverse', 'normalize', 'equal', 'not_equal', 'greater',
                'less', 'greater_equal', 'less_equal', 'and', 'or', 'not', 'if', 'filter',
                'subtract', 'divide', 'multiply', 'add', 'power', 'signed_power'
            }
            
            for row in cursor.fetchall():
                if row[0]:
                    template = row[0]
                    # Extract field IDs (long alphanumeric strings with underscores)
                    field_pattern = r'\b([a-z][a-z0-9_]{10,})\b'
                    matches = re.findall(field_pattern, template, re.IGNORECASE)
                    for match in matches:
                        match_lower = match.lower()
                        if match_lower not in excluded and len(match) > 10:
                            recently_used_fields.add(match_lower)
            
            conn.close()
            
            # Return as list, limited to requested number
            result = list(recently_used_fields)[:limit]
            logger.debug(f"Found {len(result)} recently used fields for {region} in last {lookback_hours} hours")
            return result
            
        except Exception as e:
            logger.error(f"Error getting recently used fields: {e}")
            return []
    
    def check_template_similarity(
        self, 
        new_template: str,
        region: str = None,
        similarity_threshold: float = 0.7,
        max_check: int = 100  # Only check last N templates for performance
    ) -> List[Tuple[str, float]]:
        """
        Check if new template is similar to existing templates (OPTIMIZED: queries only recent templates)
        
        Args:
            new_template: New template to check
            region: Optional region filter
            similarity_threshold: Similarity threshold (0.0-1.0)
            max_check: Maximum number of templates to check (for performance)
            
        Returns:
            List of (template, similarity_score) tuples for similar templates
        """
        try:
            from ..core.template_similarity import TemplateSimilarityChecker
            similarity_checker = TemplateSimilarityChecker(similarity_threshold=similarity_threshold)
            
            # Only fetch recent templates (not all) for performance
            existing_templates = self.get_all_templates(region=region, limit=max_check)
            
            if not existing_templates:
                return []
            
            similar = similarity_checker.find_similar_templates(new_template, existing_templates)
            
            return similar
            
        except Exception as e:
            logger.error(f"Error checking template similarity: {e}")
            return []
    
    def store_batch(self, results: List) -> int:
        """
        Store multiple results
        
        Args:
            results: List of results
            
        Returns:
            Number of successfully stored results
        """
        stored = 0
        for result in results:
            if self.store_result(result):
                stored += 1
        
        logger.info(f"Stored {stored}/{len(results)} backtest results")
        return stored
    
    def get_results(
        self, 
        region: Optional[str] = None,
        min_sharpe: Optional[float] = None,
        success_only: bool = False,
        limit: Optional[int] = None
    ) -> List[BacktestRecord]:
        """
        Retrieve backtest results
        
        Args:
            region: Filter by region
            min_sharpe: Minimum Sharpe ratio
            success_only: Only successful results
            limit: Maximum number of results
            
        Returns:
            List of BacktestRecord objects
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Use specific columns instead of SELECT * for better performance
        # Only select columns we actually need for BacktestRecord
        query = """SELECT id, template, region, sharpe, fitness, turnover, returns, drawdown,
                  margin, longCount, shortCount, pnl, volatility, max_drawdown, win_rate,
                  avg_return, correlations, power_pool_corr, prod_corr, checks, success,
                  alpha_id, error_message, timestamp, raw_data FROM backtest_results WHERE 1=1"""
        params = []
        
        if region:
            query += " AND region = ?"
            params.append(region)
        
        if min_sharpe is not None:
            query += " AND sharpe >= ?"
            params.append(min_sharpe)
        
        if success_only:
            query += " AND success = 1"
        
        query += " ORDER BY timestamp DESC"
        
        if limit:
            query += " LIMIT ?"
            params.append(limit)
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        results = []
        for row in rows:
            results.append(BacktestRecord(
                template=row[1],
                region=row[2],
                sharpe=row[3] or 0.0,
                fitness=row[4] or 0.0,
                turnover=row[5] or 0.0,
                returns=row[6] or 0.0,
                drawdown=row[7] or 0.0,
                margin=row[8] or 0.0,
                longCount=row[9] or 0,
                shortCount=row[10] or 0,
                pnl=row[11] or 0.0 if len(row) > 11 else 0.0,
                volatility=row[12] or 0.0 if len(row) > 12 else 0.0,
                max_drawdown=row[13] or 0.0 if len(row) > 13 else 0.0,
                win_rate=row[14] or 0.0 if len(row) > 14 else 0.0,
                avg_return=row[15] or 0.0 if len(row) > 15 else 0.0,
                correlations=row[16] or '' if len(row) > 16 else '',
                power_pool_corr=row[17] or '' if len(row) > 17 else '',
                prod_corr=row[18] or '' if len(row) > 18 else '',
                checks=row[19] or '' if len(row) > 19 else '',
                success=bool(row[20] if len(row) > 20 else row[11]),
                alpha_id=row[21] or '' if len(row) > 21 else (row[12] or '' if len(row) > 12 else ''),
                error_message=row[22] or '' if len(row) > 22 else (row[13] or '' if len(row) > 13 else ''),
                timestamp=row[23] or 0.0 if len(row) > 23 else (row[14] or 0.0 if len(row) > 14 else 0.0),
                raw_data=row[24] or '' if len(row) > 24 else ''
            ))
        
        return results
    
    def get_top_results(
        self, 
        region: Optional[str] = None,
        limit: int = 10
    ) -> List[BacktestRecord]:
        """
        Get top performing results
        
        Args:
            region: Filter by region
            limit: Number of results
            
        Returns:
            List of top BacktestRecord objects
        """
        return self.get_results(
            region=region,
            min_sharpe=1.0,
            success_only=True,
            limit=limit
        )
    
    def get_statistics(self, region: Optional[str] = None) -> Dict:
        """
        Get statistics about stored results
        
        Args:
            region: Filter by region
            
        Returns:
            Dictionary with statistics
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        query = "SELECT COUNT(*), AVG(sharpe), MAX(sharpe), MIN(sharpe), SUM(success) FROM backtest_results WHERE 1=1"
        params = []
        
        if region:
            query += " AND region = ?"
            params.append(region)
        
        cursor.execute(query, params)
        row = cursor.fetchone()
        conn.close()
        
        total, avg_sharpe, max_sharpe, min_sharpe, successful = row
        
        return {
            'total': total or 0,
            'successful': successful or 0,
            'failed': (total or 0) - (successful or 0),
            'success_rate': (successful or 0) / (total or 1) if total else 0.0,
            'avg_sharpe': avg_sharpe or 0.0,
            'max_sharpe': max_sharpe or 0.0,
            'min_sharpe': min_sharpe or 0.0
        }
    
    def clear_old_results(self, days: int = 30):
        """
        Clear results older than specified days
        
        Args:
            days: Number of days to keep
        """
        import time
        cutoff_time = time.time() - (days * 24 * 3600)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM backtest_results WHERE timestamp < ?', (cutoff_time,))
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        
        logger.info(f"Cleared {deleted} old results (older than {days} days)")
    
    def store_compiler_knowledge(
        self,
        knowledge_type: str,
        operator_name: str = None,
        field_type: str = None,
        compatibility_status: str = None,
        error_message: str = None,
        learned_from_template: str = None,
        learned_from_error: str = None,
        replacement_operator: str = None,
        ast_pattern: str = None,
        compiler_rule: str = None,
        metadata: Dict = None
    ) -> bool:
        """
        Store compiler knowledge learned from errors
        
        Args:
            knowledge_type: Type of knowledge (e.g., 'event_input_incompatible', 'type_mismatch', 'operator_compatibility')
            operator_name: Operator involved
            field_type: Field type involved
            compatibility_status: Compatibility status (e.g., 'incompatible', 'compatible')
            error_message: Original error message
            learned_from_template: Template that caused the error
            learned_from_error: Error that was learned from
            replacement_operator: Replacement operator if applicable
            ast_pattern: AST pattern extracted
            compiler_rule: Compiler rule learned
            metadata: Additional metadata as dict
            
        Returns:
            True if successful
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            metadata_json = json.dumps(metadata) if metadata else None
            
            # Check if knowledge already exists
            cursor.execute('''
                SELECT id FROM compiler_knowledge 
                WHERE knowledge_type = ? AND operator_name = ? AND field_type = ?
            ''', (knowledge_type, operator_name, field_type))
            
            existing = cursor.fetchone()
            
            if existing:
                # Update existing knowledge
                cursor.execute('''
                    UPDATE compiler_knowledge SET
                        compatibility_status = ?,
                        error_message = ?,
                        learned_from_template = ?,
                        learned_from_error = ?,
                        replacement_operator = ?,
                        ast_pattern = ?,
                        compiler_rule = ?,
                        metadata = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (
                    compatibility_status, error_message, learned_from_template,
                    learned_from_error, replacement_operator, ast_pattern,
                    compiler_rule, metadata_json, existing[0]
                ))
            else:
                # Insert new knowledge
                cursor.execute('''
                    INSERT INTO compiler_knowledge 
                    (knowledge_type, operator_name, field_type, compatibility_status,
                     error_message, learned_from_template, learned_from_error,
                     replacement_operator, ast_pattern, compiler_rule, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    knowledge_type, operator_name, field_type, compatibility_status,
                    error_message, learned_from_template, learned_from_error,
                    replacement_operator, ast_pattern, compiler_rule, metadata_json
                ))
            
            conn.commit()
            conn.close()
            
            logger.info(f"✅ Stored compiler knowledge: {knowledge_type} for {operator_name}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error storing compiler knowledge: {e}", exc_info=True)
            return False
    
    def get_compiler_knowledge(
        self,
        knowledge_type: str = None,
        operator_name: str = None,
        limit: int = None
    ) -> List[Dict]:
        """
        Get compiler knowledge (OPTIMIZED: uses targeted queries with optional limit)
        
        Args:
            knowledge_type: Filter by knowledge type
            operator_name: Filter by operator name
            limit: Optional limit on number of records (for performance)
            
        Returns:
            List of knowledge records
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Use targeted query with specific columns (not SELECT *)
            query = """SELECT id, knowledge_type, operator_name, field_type, compatibility_status,
                      error_message, learned_from_template, learned_from_error, replacement_operator,
                      ast_pattern, compiler_rule, metadata, created_at, updated_at
                      FROM compiler_knowledge WHERE 1=1"""
            params = []
            
            if knowledge_type:
                query += " AND knowledge_type = ?"
                params.append(knowledge_type)
            
            if operator_name:
                query += " AND operator_name = ?"
                params.append(operator_name)
            
            query += " ORDER BY updated_at DESC"
            
            if limit:
                query += " LIMIT ?"
                params.append(limit)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            conn.close()
            
            # Convert to dicts
            columns = [desc[0] for desc in cursor.description] if rows else []
            knowledge = []
            for row in rows:
                record = dict(zip(columns, row))
                if record.get('metadata'):
                    try:
                        record['metadata'] = json.loads(record['metadata'])
                    except:
                        pass
                knowledge.append(record)
            
            return knowledge
            
        except Exception as e:
            logger.error(f"Error getting compiler knowledge: {e}")
            return []
    
    def store_ast_pattern(
        self,
        pattern_type: str,
        pattern_structure: str,
        operator_sequence: List[str] = None,
        field_types: List[str] = None,
        example_template: str = None,
        success: bool = True,
        metadata: Dict = None
    ) -> bool:
        """
        Store AST pattern learned from templates
        
        Args:
            pattern_type: Type of pattern (e.g., 'successful', 'failed', 'operator_combination')
            pattern_structure: AST structure as string
            operator_sequence: Sequence of operators
            field_types: Types of fields used
            example_template: Example template using this pattern
            success: Whether pattern is successful
            metadata: Additional metadata
            
        Returns:
            True if successful
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            operator_seq_json = json.dumps(operator_sequence) if operator_sequence else None
            field_types_json = json.dumps(field_types) if field_types else None
            metadata_json = json.dumps(metadata) if metadata else None
            
            # Check if pattern exists
            cursor.execute('''
                SELECT id, success_count, failure_count FROM ast_patterns
                WHERE pattern_structure = ? AND pattern_type = ?
            ''', (pattern_structure, pattern_type))
            
            existing = cursor.fetchone()
            
            if existing:
                # Update existing pattern
                pattern_id, success_count, failure_count = existing
                if success:
                    success_count += 1
                else:
                    failure_count += 1
                
                cursor.execute('''
                    UPDATE ast_patterns SET
                        success_count = ?,
                        failure_count = ?,
                        example_template = ?,
                        metadata = ?,
                        last_used_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (success_count, failure_count, example_template, metadata_json, pattern_id))
            else:
                # Insert new pattern
                cursor.execute('''
                    INSERT INTO ast_patterns
                    (pattern_type, pattern_structure, operator_sequence, field_types,
                     success_count, failure_count, example_template, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    pattern_type, pattern_structure, operator_seq_json, field_types_json,
                    1 if success else 0, 0 if success else 1, example_template, metadata_json
                ))
            
            conn.commit()
            conn.close()
            
            logger.info(f"✅ Stored AST pattern: {pattern_type} (success={success})")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error storing AST pattern: {e}", exc_info=True)
            return False
    
    def get_ast_patterns(
        self,
        pattern_type: str = None,
        min_success_count: int = 0,
        limit: int = None
    ) -> List[Dict]:
        """
        Get AST patterns (OPTIMIZED: uses targeted queries with optional limit)
        
        Args:
            pattern_type: Filter by pattern type
            min_success_count: Minimum success count
            limit: Optional limit on number of records (for performance)
            
        Returns:
            List of pattern records
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Use targeted query with specific columns (not SELECT *)
            query = """SELECT id, pattern_type, pattern_structure, operator_sequence, field_types,
                      success_count, failure_count, example_template, metadata, created_at, last_used_at
                      FROM ast_patterns WHERE 1=1"""
            params = []
            
            if pattern_type:
                query += " AND pattern_type = ?"
                params.append(pattern_type)
            
            if min_success_count > 0:
                query += " AND success_count >= ?"
                params.append(min_success_count)
            
            query += " ORDER BY success_count DESC, last_used_at DESC"
            
            if limit:
                query += " LIMIT ?"
                params.append(limit)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            conn.close()
            
            # Convert to dicts
            columns = [desc[0] for desc in cursor.description] if rows else []
            patterns = []
            for row in rows:
                record = dict(zip(columns, row))
                if record.get('operator_sequence'):
                    try:
                        record['operator_sequence'] = json.loads(record['operator_sequence'])
                    except:
                        pass
                if record.get('field_types'):
                    try:
                        record['field_types'] = json.loads(record['field_types'])
                    except:
                        pass
                if record.get('metadata'):
                    try:
                        record['metadata'] = json.loads(record['metadata'])
                    except:
                        pass
                patterns.append(record)
            
            return patterns
            
        except Exception as e:
            logger.error(f"Error getting AST patterns: {e}")
            return []

