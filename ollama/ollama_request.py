"""
Ollama Request Handler
Handles actual API calls to Ollama (both library and requests fallback)
"""

import logging
import time
import threading
from typing import Optional, List, Dict, Callable

logger = logging.getLogger(__name__)


def call_ollama_library(
    chat_func: Callable,
    model: str,
    messages: List[Dict],
    temperature: float,
    max_tokens: int,
    timeout: int
) -> Optional[str]:
    """
    Call Ollama using the library
    
    Args:
        chat_func: The ollama.chat function
        model: Model name
        messages: List of message dicts
        temperature: Sampling temperature
        max_tokens: Maximum tokens
        timeout: Request timeout
        
    Returns:
        Generated text or None
    """
    try:
        response = chat_func(
            model=model,
            messages=messages,
            options={
                'temperature': temperature,
                'num_predict': max_tokens,
                'timeout': timeout
            }
        )
        
        # Extract content from response
        if isinstance(response, dict):
            if 'message' in response:
                return response.get('message', {}).get('content', '').strip()
            elif 'response' in response:
                return response.get('response', '').strip()
        else:
            # ChatResponse object
            try:
                if hasattr(response, 'message') and hasattr(response.message, 'content'):
                    return response.message.content.strip()
                elif hasattr(response, 'get'):
                    return response.get('message', {}).get('content', '').strip()
            except Exception:
                pass
        
        return None
    except Exception as e:
        logger.error(f"Ollama library call failed: {type(e).__name__}: {str(e)}")
        return None


def call_ollama_requests(
    session,
    base_url: str,
    model: str,
    messages: List[Dict],
    temperature: float,
    max_tokens: int,
    timeout: int
) -> Optional[str]:
    """
    Call Ollama using requests fallback
    
    Args:
        session: requests.Session object
        base_url: Ollama base URL
        model: Model name
        messages: List of message dicts
        temperature: Sampling temperature
        max_tokens: Maximum tokens
        timeout: Request timeout
        
    Returns:
        Generated text or None
    """
    try:
        response = session.post(
            f"{base_url}/api/chat",
            json={
                'model': model,
                'messages': messages,
                'options': {
                    'temperature': temperature,
                    'num_predict': max_tokens
                },
                'stream': False
            },
            timeout=timeout
        )
        
        if response.status_code == 200:
            result = response.json()
            return result.get('message', {}).get('content', '').strip()
        else:
            logger.warning(f"Requests fallback returned status {response.status_code}")
            return None
    except Exception as e:
        logger.warning(f"Requests fallback failed: {type(e).__name__}: {str(e)[:200]}")
        return None


def create_progress_monitor(
    progress_callback: Optional[Callable[[str], None]],
    request_start_time: float,
    timeout: int
) -> Optional[threading.Thread]:
    """
    Create a progress monitoring thread
    
    Args:
        progress_callback: Callback function for progress updates
        request_start_time: Start time of the request
        timeout: Request timeout
        
    Returns:
        Thread object or None
    """
    if not progress_callback:
        return None
    
    def monitor_progress():
        elapsed = 0
        last_update = 0
        update_intervals = [10, 20, 30, 45, 60]
        next_update_index = 0
        
        while elapsed < timeout:
            time.sleep(5)
            elapsed = time.time() - request_start_time
            
            if next_update_index < len(update_intervals):
                next_interval = update_intervals[next_update_index]
                if elapsed >= next_interval and elapsed - last_update >= 5:
                    try:
                        progress_callback(f"Waiting... ({int(elapsed)}s)")
                        last_update = elapsed
                        next_update_index += 1
                    except Exception:
                        break
            elif elapsed - last_update >= 30:
                try:
                    progress_callback(f"Waiting... ({int(elapsed)}s)")
                    last_update = elapsed
                except Exception:
                    break
    
    thread = threading.Thread(target=monitor_progress, daemon=True)
    thread.start()
    return thread
