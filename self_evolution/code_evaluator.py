"""
Code Evaluator
Evaluates dynamically generated code for safety and performance
"""

import logging
import importlib.util
import sys
import os
import time
from typing import Dict, Optional, Any, List
from dataclasses import dataclass
import traceback

logger = logging.getLogger(__name__)


@dataclass
class EvaluationResult:
    """Result of code evaluation"""
    module_name: str
    success: bool
    syntax_valid: bool
    import_success: bool
    execution_success: bool
    performance_score: float = 0.0
    safety_score: float = 0.0
    error_message: str = ""
    execution_time: float = 0.0
    memory_usage: float = 0.0


class CodeEvaluator:
    """
    Evaluates dynamically generated code
    
    Checks:
    - Syntax validity
    - Import success
    - Execution safety
    - Performance
    """
    
    def __init__(self):
        """Initialize code evaluator"""
        self.evaluation_history = []
        self.sandbox_modules = {}  # Track loaded modules
    
    def evaluate_module(
        self,
        code: str,
        module_name: str,
        test_cases: Optional[List[Dict]] = None
    ) -> EvaluationResult:
        """
        Evaluate a generated module
        
        Args:
            code: Module code
            module_name: Name of the module
            test_cases: Optional test cases to run
            
        Returns:
            EvaluationResult
        """
        result = EvaluationResult(
            module_name=module_name,
            success=False,
            syntax_valid=False,
            import_success=False,
            execution_success=False
        )
        
        start_time = time.time()
        
        # 1. Syntax validation
        try:
            compile(code, module_name, 'exec')
            result.syntax_valid = True
        except SyntaxError as e:
            result.error_message = f"Syntax error: {e}"
            result.execution_time = time.time() - start_time
            return result
        
        # 2. Import validation
        try:
            spec = importlib.util.spec_from_loader(module_name, loader=None)
            module = importlib.util.module_from_spec(spec)
            
            # Execute in isolated namespace
            exec_globals = {
                '__name__': module_name,
                '__file__': f'<generated:{module_name}>',
                '__package__': None
            }
            
            exec(code, exec_globals)
            result.import_success = True
            self.sandbox_modules[module_name] = exec_globals
            
        except Exception as e:
            result.error_message = f"Import error: {e}"
            result.execution_time = time.time() - start_time
            return result
        
        # 3. Execution validation (if test cases provided)
        if test_cases:
            try:
                for test_case in test_cases:
                    # Run test case in sandbox
                    test_func = exec_globals.get(test_case.get('function'))
                    if test_func:
                        test_func(*test_case.get('args', []), **test_case.get('kwargs', {}))
                
                result.execution_success = True
            except Exception as e:
                result.error_message = f"Execution error: {e}"
                result.execution_time = time.time() - start_time
                return result
        else:
            result.execution_success = True
        
        # 4. Safety checks
        result.safety_score = self._check_safety(code)
        
        # 5. Performance estimation
        result.performance_score = self._estimate_performance(code)
        
        result.execution_time = time.time() - start_time
        result.success = result.syntax_valid and result.import_success and result.execution_success
        
        self.evaluation_history.append(result)
        
        return result
    
    def _check_safety(self, code: str) -> float:
        """
        Check code safety
        
        Returns:
            Safety score (0-1)
        """
        score = 1.0
        
        # Dangerous operations
        dangerous_patterns = [
            ('import os', -0.2),
            ('import subprocess', -0.3),
            ('eval(', -0.5),
            ('exec(', -0.5),
            ('__import__', -0.4),
            ('open(', -0.1),
            ('file(', -0.1),
        ]
        
        code_lower = code.lower()
        for pattern, penalty in dangerous_patterns:
            if pattern.lower() in code_lower:
                score += penalty
        
        return max(0.0, min(1.0, score))
    
    def _estimate_performance(self, code: str) -> float:
        """
        Estimate code performance
        
        Returns:
            Performance score (0-1)
        """
        # Simple heuristic based on code complexity
        lines = len(code.split('\n'))
        complexity = code.count('for ') + code.count('while ') + code.count('if ')
        
        # Lower complexity = higher score
        if lines == 0:
            return 0.0
        
        complexity_ratio = complexity / lines
        performance_score = 1.0 - min(complexity_ratio * 0.5, 0.8)
        
        return max(0.0, min(1.0, performance_score))
    
    def load_module(self, module_path: str) -> Optional[Any]:
        """
        Load an evaluated module
        
        Args:
            module_path: Path to module file
            
        Returns:
            Loaded module or None
        """
        try:
            spec = importlib.util.spec_from_file_location(
                os.path.basename(module_path).replace('.py', ''),
                module_path
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
        except Exception as e:
            logger.error(f"Error loading module {module_path}: {e}")
            return None
