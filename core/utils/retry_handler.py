"""
Reusable Retry Handler with configurable strategies
Supports different retry strategies and can be configured via GUI/config
"""

import time
import logging
from typing import Callable, Optional, Any, Dict
from enum import Enum
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class RetryStrategy(Enum):
    """Retry strategy types"""
    LINEAR = "linear"  # Fixed delay between retries
    EXPONENTIAL = "exponential"  # Exponential backoff
    FIBONACCI = "fibonacci"  # Fibonacci backoff
    CUSTOM = "custom"  # Custom function


@dataclass
class RetryConfig:
    """Configuration for retry behavior"""
    max_retries: int = 3
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL
    base_delay: float = 1.0  # Base delay in seconds
    max_delay: float = 60.0  # Maximum delay in seconds
    multiplier: float = 2.0  # For exponential backoff
    retryable_errors: list = field(default_factory=lambda: [401, 405, 500, 502, 503, 504])
    custom_delay_func: Optional[Callable[[int], float]] = None  # For custom strategy
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization"""
        return {
            'max_retries': self.max_retries,
            'strategy': self.strategy.value,
            'base_delay': self.base_delay,
            'max_delay': self.max_delay,
            'multiplier': self.multiplier,
            'retryable_errors': self.retryable_errors,
            'has_custom_delay': self.custom_delay_func is not None
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'RetryConfig':
        """Create from dictionary"""
        config = cls(
            max_retries=data.get('max_retries', 3),
            strategy=RetryStrategy(data.get('strategy', 'exponential')),
            base_delay=data.get('base_delay', 1.0),
            max_delay=data.get('max_delay', 60.0),
            multiplier=data.get('multiplier', 2.0),
            retryable_errors=data.get('retryable_errors', [401, 405, 500, 502, 503, 504])
        )
        return config


class RetryHandler:
    """
    Reusable retry handler with configurable strategies
    
    Can be configured via config files or GUI in the future
    """
    
    def __init__(self, config: Optional[RetryConfig] = None):
        """
        Initialize retry handler
        
        Args:
            config: Retry configuration (uses default if None)
        """
        self.config = config or RetryConfig()
        self._stats = {
            'total_attempts': 0,
            'successful_retries': 0,
            'failed_retries': 0,
            'total_delay_time': 0.0
        }
    
    def calculate_delay(self, attempt: int) -> float:
        """
        Calculate delay for given attempt number
        
        Args:
            attempt: Current attempt number (0-indexed)
            
        Returns:
            Delay in seconds
        """
        if self.config.strategy == RetryStrategy.LINEAR:
            delay = self.config.base_delay
        elif self.config.strategy == RetryStrategy.EXPONENTIAL:
            delay = self.config.base_delay * (self.config.multiplier ** attempt)
        elif self.config.strategy == RetryStrategy.FIBONACCI:
            # Fibonacci sequence: 1, 1, 2, 3, 5, 8, 13, ...
            fib = [1, 1]
            for i in range(2, attempt + 2):
                fib.append(fib[i-1] + fib[i-2])
            delay = self.config.base_delay * fib[min(attempt, len(fib) - 1)]
        elif self.config.strategy == RetryStrategy.CUSTOM:
            if self.config.custom_delay_func:
                delay = self.config.custom_delay_func(attempt)
            else:
                delay = self.config.base_delay
        else:
            delay = self.config.base_delay
        
        # Cap at max_delay
        delay = min(delay, self.config.max_delay)
        return delay
    
    def should_retry(self, error: Any, attempt: int) -> bool:
        """
        Determine if we should retry based on error and attempt
        
        Args:
            error: The error/response that occurred
            attempt: Current attempt number
            
        Returns:
            True if should retry, False otherwise
        """
        if attempt >= self.config.max_retries:
            return False
        
        # Check if error is retryable
        if hasattr(error, 'status_code'):
            status_code = error.status_code
            return status_code in self.config.retryable_errors
        elif isinstance(error, Exception):
            # For exceptions, retry by default (can be customized)
            return True
        
        return False
    
    def execute_with_retry(
        self,
        func: Callable,
        *args,
        on_retry: Optional[Callable[[int, Any], None]] = None,
        on_success: Optional[Callable[[Any], None]] = None,
        on_failure: Optional[Callable[[Any], None]] = None,
        **kwargs
    ) -> Any:
        """
        Execute a function with retry logic
        
        Args:
            func: Function to execute
            *args: Positional arguments for func
            on_retry: Callback called before each retry (attempt_num, error)
            on_success: Callback called on success (result)
            on_failure: Callback called on final failure (error)
            **kwargs: Keyword arguments for func
            
        Returns:
            Result from func if successful
            
        Raises:
            Last exception if all retries fail
        """
        last_error = None
        
        for attempt in range(self.config.max_retries + 1):
            self._stats['total_attempts'] += 1
            
            try:
                result = func(*args, **kwargs)
                
                # Check if result indicates failure (for response objects)
                if hasattr(result, 'status_code'):
                    status_code = result.status_code
                    if status_code in self.config.retryable_errors:
                        if self.should_retry(result, attempt):
                            if on_retry:
                                on_retry(attempt, result)
                            
                            delay = self.calculate_delay(attempt)
                            self._stats['total_delay_time'] += delay
                            logger.debug(f"Retrying after {delay:.2f}s (attempt {attempt + 1}/{self.config.max_retries + 1})")
                            time.sleep(delay)
                            last_error = result
                            continue
                
                # Success
                if attempt > 0:
                    self._stats['successful_retries'] += 1
                
                if on_success:
                    on_success(result)
                
                return result
                
            except Exception as e:
                last_error = e
                
                if self.should_retry(e, attempt):
                    if on_retry:
                        on_retry(attempt, e)
                    
                    delay = self.calculate_delay(attempt)
                    self._stats['total_delay_time'] += delay
                    logger.debug(f"Retrying after {delay:.2f}s (attempt {attempt + 1}/{self.config.max_retries + 1}): {e}")
                    time.sleep(delay)
                else:
                    break
        
        # All retries failed
        self._stats['failed_retries'] += 1
        
        if on_failure:
            on_failure(last_error)
        
        if last_error:
            raise last_error
        else:
            raise Exception("All retry attempts failed")
    
    def update_config(self, config: RetryConfig):
        """Update retry configuration (for GUI/config changes)"""
        self.config = config
        logger.info(f"Retry config updated: {config.to_dict()}")
    
    def get_stats(self) -> Dict:
        """Get retry statistics"""
        return {
            **self._stats,
            'config': self.config.to_dict()
        }
    
    def reset_stats(self):
        """Reset statistics"""
        self._stats = {
            'total_attempts': 0,
            'successful_retries': 0,
            'failed_retries': 0,
            'total_delay_time': 0.0
        }
