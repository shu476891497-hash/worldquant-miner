"""
Ollama Health Check Utilities
Handles availability checks and model discovery
"""

import logging
from typing import List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


def get_model_names_from_ollama(list_func) -> List[str]:
    """
    Get model names from ollama list() function
    
    Args:
        list_func: The ollama.list function
        
    Returns:
        List of model names
    """
    try:
        models = list_func()
        if isinstance(models, dict):
            return [m.get('name', '') for m in models.get('models', [])]
        else:
            return [m.name if hasattr(m, 'name') else str(m) for m in models.models] if hasattr(models, 'models') else []
    except Exception as e:
        logger.debug(f"Error getting models from ollama.list(): {e}")
        return []


def get_model_names_from_requests(session, base_url: str) -> List[str]:
    """
    Get model names using requests fallback
    
    Args:
        session: requests.Session object
        base_url: Ollama base URL
        
    Returns:
        List of model names
    """
    try:
        response = session.get(f"{base_url}/api/tags", timeout=5)
        if response.status_code == 200:
            models = response.json()
            return [m.get("name", "") for m in models.get("models", [])]
    except Exception as e:
        logger.debug(f"Error getting models from requests: {e}")
    return []


def find_best_model_match(model_names: List[str], requested_model: str) -> tuple:
    """
    Find the best matching model from available models
    
    Args:
        model_names: List of available model names
        requested_model: The requested model name
        
    Returns:
        Tuple of (model_exists, matched_model, base_matches)
    """
    if not model_names:
        return False, None, []
    
    exact_match = None
    base_matches = []
    
    for name in model_names:
        # Prefer exact match
        if name == requested_model:
            exact_match = name
            break
        # Also check base name (e.g., "qwen2.5-coder" matches "qwen2.5-coder:32b")
        if ":" in requested_model:
            base_name = requested_model.split(":")[0]
            if name.startswith(base_name):
                base_matches.append(name)
    
    if exact_match:
        return True, exact_match, []
    
    if base_matches:
        # Use best base match (prefer smaller models: 1.5b < 7b < 32b)
        size_order = {"1.5b": 1, "7b": 2, "32b": 3}
        base_matches.sort(key=lambda x: size_order.get(
            next((k for k in size_order.keys() if k in x.lower()), "99"), 99
        ))
        requested_size = next((k for k in size_order.keys() if k in requested_model.lower()), None)
        if requested_size:
            # Try to match requested size first
            for match in base_matches:
                if requested_size in match.lower():
                    return True, match, base_matches
        # Use smallest available
        return True, base_matches[0], base_matches
    
    return False, None, []


def select_alternative_model(model_names: List[str], preferred_models: List[str]) -> Optional[str]:
    """
    Select an alternative model from preferred list
    
    Args:
        model_names: List of available model names
        preferred_models: List of preferred model names (in order of preference)
        
    Returns:
        Selected model name or None
    """
    for preferred in preferred_models:
        if preferred in model_names:
            return preferred
        # Also check base name matches
        if ":" in preferred:
            base_name = preferred.split(":")[0]
            for name in model_names:
                if name.startswith(base_name):
                    return name
    return None
