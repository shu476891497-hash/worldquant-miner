"""
On-the-Fly Testing System for Generation Two
Tests evolved alphas immediately during generation
"""

import time
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from concurrent.futures import Future

logger = logging.getLogger(__name__)


@dataclass
class TestResult:
    """Result from on-the-fly test"""
    expression: str
    sharpe: float
    fitness: float
    success: bool
    region: str = ""
    error: Optional[str] = None


class OnTheFlyTester:
    """
    On-the-fly testing system for evolved alphas
    
    Tests evolved alpha expressions immediately during generation
    to provide fast feedback for the evolution process.
    """
    
    def __init__(self, generator: Any):
        """
        Initialize on-the-fly tester
        
        Args:
            generator: Reference to EnhancedTemplateGeneratorV3
        """
        self.generator = generator
        self.test_queue: List[Dict] = []
        self.test_results: Dict[str, TestResult] = {}
        
    def validate_expression(self, alpha_expression: str) -> bool:
        """
        Quick validation of alpha expression
        
        Args:
            alpha_expression: Alpha expression to validate
            
        Returns:
            True if valid, False otherwise
        """
        if not alpha_expression or len(alpha_expression.strip()) == 0:
            return False
        
        # Basic validation: check for common syntax issues
        # This is simplified; full validation would parse the expression
        if alpha_expression.count('(') != alpha_expression.count(')'):
            logger.warning(f"Unbalanced parentheses in expression: {alpha_expression}")
            return False
        
        # Check for basic operators/fields
        valid_chars = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789()+-*/=<>.,[]_')
        if not all(c in valid_chars or c.isspace() for c in alpha_expression):
            logger.warning(f"Invalid characters in expression: {alpha_expression}")
            return False
        
        return True
    
    def test_evolved_alpha(
        self, 
        alpha_expression: str, 
        region: str
    ) -> Optional[Future]:
        """
        Test an evolved alpha immediately
        
        Args:
            alpha_expression: Alpha expression to test
            region: Region to test in
            
        Returns:
            Future object for the test, or None if invalid
        """
        # Quick validation
        if not self.validate_expression(alpha_expression):
            logger.warning(f"Invalid expression: {alpha_expression}")
            return None
        
        # Check if generator has simulator_tester
        if not hasattr(self.generator, 'simulator_tester'):
            logger.error("Generator does not have simulator_tester")
            return None
        
        try:
            # Submit quick test (shorter time period for speed)
            from ..core import SimulationSettings
            settings = SimulationSettings(
                region=region,
                testPeriod="P1Y0M0D"  # 1 year instead of 5 years for speed
            )
            
            # Submit to test queue
            future = self.generator.simulator_tester.simulate_template_concurrent(
                alpha_expression, region, settings
            )
            
            self.test_queue.append({
                'expression': alpha_expression,
                'region': region,
                'future': future,
                'timestamp': time.time()
            })
            
            logger.debug(
                f"Queued on-the-fly test for expression: {alpha_expression[:50]}..."
            )
            
            return future
            
        except Exception as e:
            logger.error(f"Failed to queue test: {e}")
            return None
    
    def process_test_results(self) -> int:
        """
        Process completed test results
        
        Returns:
            Number of completed tests
        """
        completed = []
        
        for test in self.test_queue:
            if test['future'].done():
                try:
                    result = test['future'].result()
                    
                    # Convert result to TestResult
                    test_result = TestResult(
                        expression=test['expression'],
                        sharpe=getattr(result, 'sharpe', 0.0),
                        fitness=getattr(result, 'fitness', 0.0),
                        success=getattr(result, 'success', False),
                        region=test['region']
                    )
                    
                    self.test_results[test['expression']] = test_result
                    completed.append(test)
                    
                    logger.debug(
                        f"Test completed: {test['expression'][:50]}... "
                        f"sharpe={test_result.sharpe:.3f}, "
                        f"success={test_result.success}"
                    )
                    
                except Exception as e:
                    logger.error(f"Test failed: {e}")
                    # Store failed result
                    self.test_results[test['expression']] = TestResult(
                        expression=test['expression'],
                        sharpe=0.0,
                        fitness=0.0,
                        success=False,
                        region=test['region'],
                        error=str(e)
                    )
                    completed.append(test)
        
        # Remove completed tests
        for test in completed:
            self.test_queue.remove(test)
        
        return len(completed)
    
    def get_fast_feedback(self, alpha_expression: str) -> Optional[Dict]:
        """
        Get quick feedback on alpha quality
        
        Args:
            alpha_expression: Alpha expression to check
            
        Returns:
            Dictionary with feedback or None if not tested yet
        """
        if alpha_expression in self.test_results:
            result = self.test_results[alpha_expression]
            return {
                'sharpe': result.sharpe,
                'fitness': result.fitness,
                'success': result.success,
                'quality': (
                    'high' if result.sharpe > 1.5 else
                    'medium' if result.sharpe > 1.25 else 'low'
                ),
                'error': result.error
            }
        return None
    
    def get_pending_tests_count(self) -> int:
        """Get number of pending tests"""
        return len(self.test_queue)
    
    def clear_results(self):
        """Clear all test results"""
        self.test_results.clear()
        self.test_queue.clear()
        logger.info("Cleared all test results")

