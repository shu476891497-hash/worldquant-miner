"""
Reusable Request Handler with configurable retry logic
Wraps requests with retry handler for consistent behavior
"""

import logging
import requests
from typing import Optional, Dict, Any
from dataclasses import dataclass

from .retry_handler import RetryHandler, RetryConfig

logger = logging.getLogger(__name__)


@dataclass
class RequestConfig:
    """Configuration for request handling"""
    timeout: int = 30
    retry_config: Optional[RetryConfig] = None
    headers: Dict[str, str] = None
    verify_ssl: bool = True
    
    def __post_init__(self):
        if self.headers is None:
            self.headers = {}
        if self.retry_config is None:
            self.retry_config = RetryConfig()


class RequestHandler:
    """
    Reusable request handler with built-in retry logic
    
    Can be configured via config files or GUI
    """
    
    def __init__(
        self,
        session: Optional[requests.Session] = None,
        config: Optional[RequestConfig] = None
    ):
        """
        Initialize request handler
        
        Args:
            session: Requests session (creates new if None)
            config: Request configuration
        """
        self.sess = session or requests.Session()
        self.config = config or RequestConfig()
        self.retry_handler = RetryHandler(self.config.retry_config)
        self._stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0
        }
    
    def request(
        self,
        method: str,
        url: str,
        retry_config: Optional[RetryConfig] = None,
        **kwargs
    ) -> requests.Response:
        """
        Make HTTP request with retry logic
        
        Args:
            method: HTTP method (GET, POST, etc.)
            url: Request URL
            retry_config: Override retry config for this request
            **kwargs: Additional arguments for requests
        
        Returns:
            Response object
        """
        # Merge config
        kwargs.setdefault('timeout', self.config.timeout)
        kwargs.setdefault('headers', self.config.headers.copy())
        kwargs.setdefault('verify', self.config.verify_ssl)
        
        # Use override retry config if provided
        original_retry_config = self.retry_handler.config
        if retry_config:
            self.retry_handler.update_config(retry_config)
        
        try:
            self._stats['total_requests'] += 1
            
            def make_request():
                return self.sess.request(method, url, **kwargs)
            
            def on_retry(attempt, error):
                logger.warning(f"Request failed (attempt {attempt + 1}): {error}")
                if hasattr(error, 'status_code'):
                    # Re-authenticate on 401
                    if error.status_code == 401:
                        logger.info("401 error - may need re-authentication")
            
            response = self.retry_handler.execute_with_retry(
                make_request,
                on_retry=on_retry
            )
            
            self._stats['successful_requests'] += 1
            return response
            
        except Exception as e:
            self._stats['failed_requests'] += 1
            logger.error(f"Request failed after retries: {e}")
            raise
        finally:
            # Restore original retry config
            if retry_config:
                self.retry_handler.update_config(original_retry_config)
    
    def get(self, url: str, **kwargs) -> requests.Response:
        """GET request"""
        return self.request('GET', url, **kwargs)
    
    def post(self, url: str, **kwargs) -> requests.Response:
        """POST request"""
        return self.request('POST', url, **kwargs)
    
    def put(self, url: str, **kwargs) -> requests.Response:
        """PUT request"""
        return self.request('PUT', url, **kwargs)
    
    def patch(self, url: str, **kwargs) -> requests.Response:
        """PATCH request"""
        return self.request('PATCH', url, **kwargs)
    
    def delete(self, url: str, **kwargs) -> requests.Response:
        """DELETE request"""
        return self.request('DELETE', url, **kwargs)
    
    def update_config(self, config: RequestConfig):
        """Update request configuration (for GUI/config changes)"""
        self.config = config
        self.retry_handler.update_config(config.retry_config)
        logger.info("Request config updated")
    
    def get_stats(self) -> Dict:
        """Get request statistics"""
        return {
            **self._stats,
            'retry_stats': self.retry_handler.get_stats()
        }
