"""
Configuration Panel
Edit system configuration in real-time
"""

import tkinter as tk
from tkinter import ttk, scrolledtext
from typing import Optional, Dict, Callable
import json

from ..theme import COLORS, FONTS, STYLES


class ConfigPanel:
    """Panel for editing configuration"""
    
    def __init__(self, parent, config_manager=None, update_callback: Optional[Callable] = None):
        """
        Initialize config panel
        
        Args:
            parent: Parent widget
            config_manager: ConfigManager instance
            update_callback: Callback when config changes
        """
        self.parent = parent
        self.config_manager = config_manager
        self.update_callback = update_callback
        
        self.frame = tk.Frame(parent, **STYLES['frame'])
        self.frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self._create_widgets()
        self._load_config()
    
    def _create_widgets(self):
        """Create config editing widgets"""
        # Title
        title = tk.Label(
            self.frame,
            text="⚙️ CONFIGURATION CONTROL ⚙️",
            font=FONTS['heading'],
            fg=COLORS['accent_yellow'],
            bg=COLORS['bg_panel']
        )
        title.pack(pady=10)
        
        # Section selector
        selector_frame = tk.Frame(self.frame, bg=COLORS['bg_panel'])
        selector_frame.pack(fill=tk.X, padx=10, pady=5)
        
        tk.Label(
            selector_frame,
            text="Section:",
            font=FONTS['default'],
            fg=COLORS['text_primary'],
            bg=COLORS['bg_panel']
        ).pack(side=tk.LEFT, padx=5)
        
        self.section_var = tk.StringVar(value="retry")
        section_combo = ttk.Combobox(
            selector_frame,
            textvariable=self.section_var,
            values=["retry", "request", "simulation", "evolution", "template_generation", "recording"],
            state="readonly",
            width=20
        )
        section_combo.pack(side=tk.LEFT, padx=5)
        section_combo.bind('<<ComboboxSelected>>', self._on_section_change)
        
        # Config editor
        editor_frame = tk.Frame(self.frame, bg=COLORS['bg_panel'])
        editor_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        tk.Label(
            editor_frame,
            text="Configuration (JSON):",
            font=FONTS['default'],
            fg=COLORS['text_primary'],
            bg=COLORS['bg_panel']
        ).pack(anchor=tk.W)
        
        self.config_text = scrolledtext.ScrolledText(
            editor_frame,
            height=15,
            bg=COLORS['bg_secondary'],
            fg=COLORS['accent_cyan'],
            insertbackground=COLORS['accent_cyan'],
            font=FONTS['mono'],
            relief=tk.FLAT,
            borderwidth=1
        )
        self.config_text.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Buttons
        button_frame = tk.Frame(self.frame, bg=COLORS['bg_panel'])
        button_frame.pack(fill=tk.X, padx=10, pady=5)
        
        tk.Button(
            button_frame,
            text="💾 SAVE",
            command=self._save_config,
            **STYLES['button']
        ).pack(side=tk.LEFT, padx=5)
        
        tk.Button(
            button_frame,
            text="🔄 RELOAD",
            command=self._load_config,
            **STYLES['button']
        ).pack(side=tk.LEFT, padx=5)
        
        tk.Button(
            button_frame,
            text="↩️ RESET",
            command=self._reset_config,
            **STYLES['button']
        ).pack(side=tk.LEFT, padx=5)
        
        # Status
        self.status_label = tk.Label(
            self.frame,
            text="",
            font=FONTS['default'],
            fg=COLORS['accent_green'],
            bg=COLORS['bg_panel']
        )
        self.status_label.pack(pady=5)
    
    def _on_section_change(self, event=None):
        """Handle section change"""
        self._load_config()
    
    def set_section(self, section_key: str):
        """Set the current section (called from outside)"""
        if section_key in ["retry", "request", "simulation", "evolution", "template_generation", "recording"]:
            self.section_var.set(section_key)
            self._load_config()
            return True
        return False
    
    def _load_config(self):
        """Load configuration for current section"""
        if not self.config_manager:
            return
        
        section = self.section_var.get()
        section_obj = self.config_manager.get_section(section)
        
        if section_obj:
            config_dict = section_obj.data
            self.config_text.delete('1.0', tk.END)
            self.config_text.insert('1.0', json.dumps(config_dict, indent=2))
    
    def _save_config(self):
        """Save configuration"""
        if not self.config_manager:
            self.status_label.config(text="No config manager", fg=COLORS['error'])
            return
        
        try:
            config_json = self.config_text.get('1.0', tk.END).strip()
            config_dict = json.loads(config_json)
            
            section = self.section_var.get()
            self.config_manager.update_section(section, config_dict)
            
            if self.update_callback:
                self.update_callback(section, config_dict)
            
            self.status_label.config(text="✓ Configuration saved", fg=COLORS['accent_green'])
            
        except json.JSONDecodeError as e:
            self.status_label.config(text=f"Invalid JSON: {e}", fg=COLORS['error'])
        except Exception as e:
            self.status_label.config(text=f"Error: {e}", fg=COLORS['error'])
    
    def _reset_config(self):
        """Reset to defaults"""
        if self.config_manager:
            self.config_manager.reset_to_defaults()
            self._load_config()
            self.status_label.config(text="✓ Reset to defaults", fg=COLORS['accent_green'])
