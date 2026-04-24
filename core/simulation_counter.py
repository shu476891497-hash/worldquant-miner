"""
Simulation Counter Module
Tracks daily simulation count and enforces 5000/day limit
"""

import logging
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict
from pathlib import Path

logger = logging.getLogger(__name__)

# EST timezone (UTC-5)
EST = timezone(timedelta(hours=-5))


class SimulationCounter:
    """
    Tracks simulation count per day and enforces limits
    
    WorldQuant Brain limit: 5,000 simulations per 24-hour period (EST timezone)
    Warning at 4,000 simulations
    """
    
    def __init__(self, db_path: str = "generation_two_backtests.db"):
        """
        Initialize simulation counter
        
        Args:
            db_path: Path to SQLite database
        """
        self.db_path = db_path
        self.create_tables()
    
    def create_tables(self):
        """Create simulation tracking table"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS simulation_count (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date_est TEXT NOT NULL,
                count INTEGER DEFAULT 0,
                last_warning_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(date_est)
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("Simulation counter table created")
    
    def get_est_date(self) -> str:
        """Get current date in EST timezone (YYYY-MM-DD)"""
        now_est = datetime.now(EST)
        return now_est.strftime('%Y-%m-%d')
    
    def get_today_count(self) -> int:
        """Get simulation count for today (EST)"""
        today = self.get_est_date()
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT count FROM simulation_count 
            WHERE date_est = ?
        ''', (today,))
        
        row = cursor.fetchone()
        conn.close()
        
        return row[0] if row else 0
    
    def increment_count(self) -> Dict[str, any]:
        """
        Increment simulation count for today
        
        Returns:
            Dict with:
                - count: Current count
                - limit_reached: True if >= 5000
                - warning_needed: True if >= 4000 and not warned yet
                - can_simulate: True if < 5000
        """
        today = self.get_est_date()
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Insert or update count
        cursor.execute('''
            INSERT INTO simulation_count (date_est, count, updated_at)
            VALUES (?, 1, CURRENT_TIMESTAMP)
            ON CONFLICT(date_est) DO UPDATE SET
                count = count + 1,
                updated_at = CURRENT_TIMESTAMP
        ''', (today,))
        
        # Get updated count
        cursor.execute('''
            SELECT count, last_warning_count 
            FROM simulation_count 
            WHERE date_est = ?
        ''', (today,))
        
        row = cursor.fetchone()
        conn.commit()
        conn.close()
        
        count = row[0] if row else 0
        last_warning = row[1] if row and len(row) > 1 else 0
        
        limit_reached = count >= 5000
        warning_needed = count >= 4000 and last_warning < 4000
        can_simulate = count < 5000
        
        # Mark warning as sent if needed
        if warning_needed:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE simulation_count 
                SET last_warning_count = ?
                WHERE date_est = ?
            ''', (count, today))
            conn.commit()
            conn.close()
        
        return {
            'count': count,
            'limit_reached': limit_reached,
            'warning_needed': warning_needed,
            'can_simulate': can_simulate
        }
    
    def can_simulate(self) -> bool:
        """Check if we can submit more simulations today"""
        count = self.get_today_count()
        return count < 5000
    
    def get_status(self) -> Dict[str, any]:
        """Get current simulation status"""
        count = self.get_today_count()
        return {
            'count': count,
            'limit': 5000,
            'remaining': max(0, 5000 - count),
            'warning_threshold': 4000,
            'can_simulate': count < 5000,
            'limit_reached': count >= 5000,
            'warning_needed': count >= 4000
        }
