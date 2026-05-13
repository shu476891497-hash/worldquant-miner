"""
Configuration Manager
Manages all configurable parameters for the system
Supports hot-reloading and GUI integration
"""

import json
import logging
import os
from typing import Dict, Any, Optional
from dataclasses import dataclass, field, asdict
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class ConfigSection:
    """A section of configuration"""
    name: str
    data: Dict[str, Any] = field(default_factory=dict)
    description: str = ""
    editable: bool = True  # Can be changed via GUI
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'name': self.name,
            'data': self.data,
            'description': self.description,
            'editable': self.editable
        }
    
    def update(self, updates: Dict[str, Any]):
        """Update configuration values"""
        self.data.update(updates)
        logger.info(f"Config section '{self.name}' updated: {updates}")


class ConfigManager:
    """
    Central configuration manager
    
    Features:
    - Load/save from JSON files
    - Hot-reload support
    - GUI-ready structure
    - Validation
    - Change tracking
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize config manager
        
        Args:
            config_path: Path to config file (creates default if None)
        """
        self.config_path = config_path or "generation_two_config.json"
        self.sections: Dict[str, ConfigSection] = {}
        self._change_history: list = []
        self._listeners: list = []  # Callbacks for config changes
        
        # Initialize default sections
        self._init_default_config()
        
        # Load from file if exists
        if os.path.exists(self.config_path):
            self.load()
    
    def _init_default_config(self):
        """Initialize default configuration sections"""
        # Retry configuration
        self.add_section('retry', {
            'max_retries': 3,
            'strategy': 'exponential',
            'base_delay': 1.0,
            'max_delay': 60.0,
            'multiplier': 2.0,
            'retryable_errors': [401, 405, 500, 502, 503, 504]
        }, "Retry logic configuration")
        
        # Request configuration
        self.add_section('request', {
            'timeout': 30,
            'verify_ssl': True,
            'default_headers': {}
        }, "HTTP request configuration")
        
        # Simulation configuration
        self.add_section('simulation', {
            'max_wait_time': 300,
            'poll_interval': 10,
            'concurrent_limit': 8,
            'default_test_period': 'P1Y0M0D'
        }, "Simulation testing configuration")
        
        # Evolution configuration
        self.add_section('evolution', {
            'enabled': True,
            'mutation_rate': 0.1,
            'crossover_rate': 0.7,
            'elitism_rate': 0.1,
            'population_size': 50,
            'tournament_size': 5
        }, "Genetic algorithm evolution configuration")
        
        # Template generation configuration
        self.add_section('template_generation', {
            'use_ollama': True,
            'ollama_priority': True,
            'temperature': 0.7,
            'max_tokens': 500,
            'fallback_enabled': True
        }, "Template generation configuration")
        
        # Advanced Bandit System configuration
        self.add_section('advanced_bandits', {
            'enabled': True,
            'hierarchical_levels': ['region', 'strategy', 'persona', 'operator'],
            'use_thompson_sampling': True,
            'use_meta_learning': True,
            'use_adaptive_exploration': True,
            'initial_exploration': 0.3,
            'min_exploration': 0.05,
            'max_exploration': 0.8,
            'exploration_decay_rate': 0.99,
            'context_aware': True,
            'persona_evolution': {
                'enabled': True,
                'population_size': 20,
                'mutation_rate': 0.15,
                'crossover_rate': 0.7,
                'elitism_rate': 0.1,
                'tournament_size': 3,
                'evolution_frequency': 50  # Evolve every N simulations
            },
            'meta_learning': {
                'enabled': True,
                'strategy_switching_frequency': 100,  # Re-evaluate strategies every N decisions
                'performance_window': 50  # Use last N performances for strategy selection
            },
            'hierarchical_weights': {
                'region': 1.0,
                'strategy': 0.8,
                'persona': 0.9,
                'operator': 0.7
            }
        }, "Advanced multi-armed bandit system with hierarchical contextual bandits, Thompson Sampling, neural persona evolution, and meta-learning")
        
        # Recording configuration
        self.add_section('recording', {
            'enabled': True,
            'record_all_decisions': True,
            'record_parameters': True,
            'record_results': True,
            'storage_path': 'generation_two_records.db'
        }, "Recording and audit configuration")
    
    def add_section(
        self,
        name: str,
        data: Dict[str, Any],
        description: str = "",
        editable: bool = True
    ):
        """Add a configuration section"""
        self.sections[name] = ConfigSection(
            name=name,
            data=data,
            description=description,
            editable=editable
        )
    
    def get_section(self, name: str) -> Optional[ConfigSection]:
        """Get a configuration section"""
        return self.sections.get(name)
    
    def get(self, section: str, key: str, default: Any = None) -> Any:
        """Get a configuration value"""
        section_obj = self.get_section(section)
        if section_obj:
            return section_obj.data.get(key, default)
        return default
    
    def set(self, section: str, key: str, value: Any):
        """Set a configuration value"""
        section_obj = self.get_section(section)
        if not section_obj:
            self.add_section(section, {key: value})
            section_obj = self.get_section(section)
        
        old_value = section_obj.data.get(key)
        section_obj.data[key] = value
        
        # Track change
        self._track_change(section, key, old_value, value)
        
        # Notify listeners
        self._notify_listeners(section, key, old_value, value)
    
    def update_section(self, section: str, updates: Dict[str, Any]):
        """Update multiple values in a section"""
        section_obj = self.get_section(section)
        if not section_obj:
            self.add_section(section, updates)
            section_obj = self.get_section(section)
        
        old_values = section_obj.data.copy()
        section_obj.update(updates)
        
        # Track changes
        for key, value in updates.items():
            old_value = old_values.get(key)
            self._track_change(section, key, old_value, value)
            self._notify_listeners(section, key, old_value, value)
    
    def _track_change(self, section: str, key: str, old_value: Any, new_value: Any):
        """Track configuration change"""
        self._change_history.append({
            'timestamp': datetime.now().isoformat(),
            'section': section,
            'key': key,
            'old_value': old_value,
            'new_value': new_value
        })
        
        # Keep only last 1000 changes
        if len(self._change_history) > 1000:
            self._change_history = self._change_history[-1000:]
    
    def add_listener(self, callback: callable):
        """Add a callback for configuration changes"""
        self._listeners.append(callback)
    
    def _notify_listeners(self, section: str, key: str, old_value: Any, new_value: Any):
        """Notify all listeners of configuration change"""
        for listener in self._listeners:
            try:
                listener(section, key, old_value, new_value)
            except Exception as e:
                logger.error(f"Error in config listener: {e}")
    
    def load(self, path: Optional[str] = None):
        """Load configuration from file"""
        load_path = path or self.config_path
        
        if not os.path.exists(load_path):
            logger.warning(f"Config file not found: {load_path}, using defaults")
            return
        
        try:
            with open(load_path, 'r') as f:
                data = json.load(f)
            
            for section_name, section_data in data.items():
                if isinstance(section_data, dict):
                    if 'data' in section_data:
                        # Full section object
                        self.add_section(
                            section_name,
                            section_data['data'],
                            section_data.get('description', ''),
                            section_data.get('editable', True)
                        )
                    else:
                        # Just data dict
                        self.add_section(section_name, section_data)
            
            logger.info(f"Configuration loaded from {load_path}")
        except Exception as e:
            logger.error(f"Error loading config: {e}")
    
    def save(self, path: Optional[str] = None):
        """Save configuration to file"""
        save_path = path or self.config_path
        
        try:
            data = {}
            for name, section in self.sections.items():
                data[name] = section.to_dict()
            
            with open(save_path, 'w') as f:
                json.dump(data, f, indent=2)
            
            logger.info(f"Configuration saved to {save_path}")
        except Exception as e:
            logger.error(f"Error saving config: {e}")
    
    def to_dict(self) -> Dict:
        """Convert entire config to dictionary"""
        return {name: section.to_dict() for name, section in self.sections.items()}
    
    def get_change_history(self, limit: int = 100) -> list:
        """Get recent configuration changes"""
        return self._change_history[-limit:]
    
    def reset_to_defaults(self):
        """Reset configuration to defaults"""
        self.sections.clear()
        self._init_default_config()
        logger.info("Configuration reset to defaults")
