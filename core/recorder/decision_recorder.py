"""
Decision Recorder
Records all decisions, parameters, and results for optimization analysis
"""

import sqlite3
import json
import logging
import time
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class DecisionRecord:
    """Record of a decision made by the system"""
    timestamp: float
    decision_type: str  # e.g., 'template_generation', 'simulation_submission', 'retry_decision'
    context: Dict[str, Any]  # Context in which decision was made
    parameters: Dict[str, Any]  # Parameters used
    result: Optional[Dict[str, Any]] = None  # Result of the decision
    success: Optional[bool] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'timestamp': self.timestamp,
            'decision_type': self.decision_type,
            'context': self.context,
            'parameters': self.parameters,
            'result': self.result,
            'success': self.success,
            'metadata': self.metadata
        }


class DecisionRecorder:
    """
    Records all system decisions for optimization analysis
    
    Features:
    - Records all decisions with full context
    - Stores parameters and results
    - Queryable database for analysis
    - Export capabilities
    """
    
    def __init__(self, db_path: str = "generation_two_decisions.db"):
        """
        Initialize decision recorder
        
        Args:
            db_path: Path to SQLite database
        """
        self.db_path = db_path
        self._init_database()
        self._stats = {
            'total_records': 0,
            'by_type': {},
            'successful': 0,
            'failed': 0
        }
    
    def _init_database(self):
        """Initialize SQLite database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                decision_type TEXT NOT NULL,
                context TEXT NOT NULL,
                parameters TEXT NOT NULL,
                result TEXT,
                success INTEGER,
                metadata TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create indexes for faster queries
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON decisions(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_decision_type ON decisions(decision_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_success ON decisions(success)")
        
        conn.commit()
        conn.close()
    
    def record(
        self,
        decision_type: str,
        context: Dict[str, Any],
        parameters: Dict[str, Any],
        result: Optional[Dict[str, Any]] = None,
        success: Optional[bool] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Record a decision
        
        Args:
            decision_type: Type of decision (e.g., 'template_generation')
            context: Context in which decision was made
            parameters: Parameters used for the decision
            result: Result of the decision
            success: Whether the decision was successful
            metadata: Additional metadata
        """
        record = DecisionRecord(
            timestamp=time.time(),
            decision_type=decision_type,
            context=context,
            parameters=parameters,
            result=result,
            success=success,
            metadata=metadata or {}
        )
        
        self._save_record(record)
        
        # Update stats
        self._stats['total_records'] += 1
        self._stats['by_type'][decision_type] = self._stats['by_type'].get(decision_type, 0) + 1
        if success is True:
            self._stats['successful'] += 1
        elif success is False:
            self._stats['failed'] += 1
    
    def _save_record(self, record: DecisionRecord):
        """Save record to database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO decisions (
                    timestamp, decision_type, context, parameters,
                    result, success, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                record.timestamp,
                record.decision_type,
                json.dumps(record.context),
                json.dumps(record.parameters),
                json.dumps(record.result) if record.result else None,
                1 if record.success is True else (0 if record.success is False else None),
                json.dumps(record.metadata)
            ))
            
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error saving decision record: {e}")
    
    def query(
        self,
        decision_type: Optional[str] = None,
        success: Optional[bool] = None,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        limit: int = 1000
    ) -> List[DecisionRecord]:
        """
        Query decision records
        
        Args:
            decision_type: Filter by decision type
            success: Filter by success status
            start_time: Filter by start timestamp
            end_time: Filter by end timestamp
            limit: Maximum number of records to return
            
        Returns:
            List of DecisionRecord objects
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        query = "SELECT * FROM decisions WHERE 1=1"
        params = []
        
        if decision_type:
            query += " AND decision_type = ?"
            params.append(decision_type)
        
        if success is not None:
            query += " AND success = ?"
            params.append(1 if success else 0)
        
        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time)
        
        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time)
        
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        records = []
        for row in rows:
            records.append(DecisionRecord(
                timestamp=row['timestamp'],
                decision_type=row['decision_type'],
                context=json.loads(row['context']),
                parameters=json.loads(row['parameters']),
                result=json.loads(row['result']) if row['result'] else None,
                success=bool(row['success']) if row['success'] is not None else None,
                metadata=json.loads(row['metadata']) if row['metadata'] else {}
            ))
        
        return records
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get recording statistics"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get total count
        cursor.execute("SELECT COUNT(*) FROM decisions")
        total = cursor.fetchone()[0]
        
        # Get counts by type
        cursor.execute("""
            SELECT decision_type, COUNT(*) as count
            FROM decisions
            GROUP BY decision_type
        """)
        by_type = {row[0]: row[1] for row in cursor.fetchall()}
        
        # Get success rate
        cursor.execute("SELECT COUNT(*) FROM decisions WHERE success = 1")
        successful = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM decisions WHERE success = 0")
        failed = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            'total_records': total,
            'by_type': by_type,
            'successful': successful,
            'failed': failed,
            'success_rate': successful / total if total > 0 else 0.0
        }
    
    def export_to_json(self, output_path: str, **query_kwargs):
        """Export records to JSON file"""
        records = self.query(**query_kwargs)
        data = [record.to_dict() for record in records]
        
        with open(output_path, 'w') as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"Exported {len(records)} records to {output_path}")
