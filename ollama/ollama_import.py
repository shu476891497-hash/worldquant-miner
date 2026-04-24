"""
Ollama Library Import Utilities
Handles importing the ollama library from site-packages, bypassing local modules
"""

import logging
import importlib.util
import sys
import site
import os
from typing import Optional, Tuple, Callable

logger = logging.getLogger(__name__)


def import_ollama_library() -> Tuple[Optional[object], Optional[Callable], Optional[Callable]]:
    """
    Import ollama library from site-packages, bypassing local generation_two/ollama module
    
    Returns:
        Tuple of (ollama_pkg, chat_func, list_func) or (None, None, None) if import fails
    """
    # Temporarily remove local generation_two/ollama from modules to prevent shadowing
    original_ollama = sys.modules.pop('ollama', None)
    original_generation_two_ollama = sys.modules.pop('generation_two.ollama', None)
    
    try:
        # Simple approach: Try direct import after removing local modules
        # This allows ollama's internal imports (like _client) to work correctly
        try:
            import ollama
            chat_func = getattr(ollama, 'chat', None)
            list_func = getattr(ollama, 'list', None)
            if chat_func or list_func:
                # Verify it's from site-packages, not local
                if hasattr(ollama, '__file__') and ollama.__file__:
                    ollama_path = ollama.__file__.lower()
                    if 'site-packages' in ollama_path or 'dist-packages' in ollama_path:
                        logger.debug(f"✅ Loaded ollama library from {ollama.__file__}")
                        return ollama, chat_func, list_func
                    else:
                        logger.debug(f"⚠️ Ollama found but not in site-packages: {ollama.__file__}")
                        # Still return it, but log warning
                        return ollama, chat_func, list_func
                else:
                    # No __file__ attribute, assume it's correct
                    logger.debug("✅ Loaded ollama library (no __file__ attribute)")
                    return ollama, chat_func, list_func
        except ImportError as import_err:
            logger.debug(f"Direct import failed: {import_err}")
        except Exception as import_err:
            logger.debug(f"Error during direct import: {import_err}")
        
        # Fallback: Try to find and import from site-packages manually
        site_packages_dirs = site.getsitepackages()
        if hasattr(site, 'getusersitepackages'):
            user_site = site.getusersitepackages()
            if user_site:
                site_packages_dirs.append(user_site)
        
        ollama_pkg = None
        chat_func = None
        list_func = None
        
        for site_dir in site_packages_dirs:
            ollama_path = os.path.join(site_dir, 'ollama')
            if os.path.exists(ollama_path) or os.path.exists(ollama_path + '.py'):
                try:
                    # Add site_dir to sys.path temporarily to allow proper imports
                    original_path = sys.path[:]
                    if site_dir not in sys.path:
                        sys.path.insert(0, site_dir)
                    
                    try:
                        # Now try direct import - this should work with proper sys.path
                        import ollama
                        chat_func = getattr(ollama, 'chat', None)
                        list_func = getattr(ollama, 'list', None)
                        if chat_func or list_func:
                            ollama_pkg = ollama
                            logger.debug(f"✅ Loaded ollama library from {site_dir} (via sys.path)")
                            break
                    finally:
                        # Restore original sys.path
                        sys.path[:] = original_path
                        
                except Exception as e:
                    logger.debug(f"Error loading ollama from {site_dir}: {e}")
                    continue
        
        return ollama_pkg, chat_func, list_func
        
    finally:
        # Restore original modules if they existed
        if original_ollama:
            sys.modules['ollama'] = original_ollama
        if original_generation_two_ollama:
            sys.modules['generation_two.ollama'] = original_generation_two_ollama


def get_ollama_chat_function() -> Optional[Callable]:
    """
    Get the chat function from ollama library
    
    Returns:
        chat function or None if not available
    """
    _, chat_func, _ = import_ollama_library()
    return chat_func


def get_ollama_list_function() -> Optional[Callable]:
    """
    Get the list function from ollama library
    
    Returns:
        list function or None if not available
    """
    _, _, list_func = import_ollama_library()
    return list_func
