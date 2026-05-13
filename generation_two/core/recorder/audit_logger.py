"""
Audit Logger
Provides high-level audit logging for system operations
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class AuditLogger:
    """
    Audit logger for system operations
    
    Logs important system events for audit and optimization purposes
    """
    
    def __init__(self, recorder=None):
        """
        Initialize audit logger
        
        Args:
            recorder: DecisionRecorder instance (optional)
        """
        self.recorder = recorder
        self.audit_logger = logging.getLogger('audit')
    
    def log_operation(
        self,
        operation: str,
        details: Dict[str, Any],
        success: Optional[bool] = None
    ):
        """
        Log an operation
        
        Args:
            operation: Operation name
            details: Operation details
            success: Whether operation was successful
        """
        log_data = {
            'operation': operation,
            'details': details,
            'success': success,
            'timestamp': datetime.now().isoformat()
        }
        
        # Log to audit logger
        if success is True:
            self.audit_logger.info(f"Operation: {operation} - SUCCESS", extra=log_data)
        elif success is False:
            self.audit_logger.warning(f"Operation: {operation} - FAILED", extra=log_data)
        else:
            self.audit_logger.info(f"Operation: {operation}", extra=log_data)
        
        # Record if recorder is available
        if self.recorder:
            self.recorder.record(
                decision_type=f'audit_{operation}',
                context={'operation': operation},
                parameters=details,
                success=success
            )
    
    def log_config_change(
        self,
        section: str,
        key: str,
        old_value: Any,
        new_value: Any
    ):
        """Log configuration change"""
        self.log_operation(
            'config_change',
            {
                'section': section,
                'key': key,
                'old_value': str(old_value),
                'new_value': str(new_value)
            },
            success=True
        )
    
    def log_decision(
        self,
        decision_type: str,
        context: Dict[str, Any],
        parameters: Dict[str, Any],
        result: Optional[Dict[str, Any]] = None,
        success: Optional[bool] = None
    ):
        """Log a decision"""
        self.log_operation(
            f'decision_{decision_type}',
            {
                'context': context,
                'parameters': parameters,
                'result': result
            },
            success=success
        )
