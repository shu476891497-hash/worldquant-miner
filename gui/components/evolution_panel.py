"""
Evolution Panel
Control self-evolution cycles
"""

import tkinter as tk
from tkinter import ttk, scrolledtext
from typing import Optional, Callable

from ..theme import COLORS, FONTS, STYLES


class EvolutionPanel:
    """Panel for controlling self-evolution"""
    
    def __init__(self, parent, evolution_callback: Optional[Callable] = None):
        """
        Initialize evolution panel
        
        Args:
            parent: Parent widget
            evolution_callback: Callback to trigger evolution
        """
        self.parent = parent
        self.evolution_callback = evolution_callback
        
        self.frame = tk.Frame(parent, **STYLES['frame'])
        self.frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self._create_widgets()
    
    def _create_widgets(self):
        """Create evolution control widgets"""
        # Title
        title = tk.Label(
            self.frame,
            text="🧬 SELF-EVOLUTION ENGINE 🧬",
            font=FONTS['heading'],
            fg=COLORS['accent_pink'],
            bg=COLORS['bg_panel']
        )
        title.pack(pady=10)
        
        # Objectives input
        obj_frame = tk.Frame(self.frame, bg=COLORS['bg_panel'])
        obj_frame.pack(fill=tk.X, padx=10, pady=5)
        
        tk.Label(
            obj_frame,
            text="Evolution Objectives:",
            font=FONTS['default'],
            fg=COLORS['text_primary'],
            bg=COLORS['bg_panel']
        ).pack(anchor=tk.W)
        
        self.objectives_text = scrolledtext.ScrolledText(
            obj_frame,
            height=4,
            bg=COLORS['bg_secondary'],
            fg=COLORS['text_primary'],
            insertbackground=COLORS['accent_cyan'],
            font=FONTS['mono'],
            relief=tk.FLAT,
            borderwidth=1
        )
        self.objectives_text.pack(fill=tk.X, pady=5)
        self.objectives_text.insert('1.0', "Optimize retry strategy\nImprove template generation\nEnhance evaluation metrics")
        
        # Parameters
        param_frame = tk.Frame(self.frame, bg=COLORS['bg_panel'])
        param_frame.pack(fill=tk.X, padx=10, pady=5)
        
        tk.Label(
            param_frame,
            text="Modules per Cycle:",
            font=FONTS['default'],
            fg=COLORS['text_primary'],
            bg=COLORS['bg_panel']
        ).pack(side=tk.LEFT, padx=5)
        
        self.num_modules = tk.StringVar(value="3")
        modules_entry = tk.Entry(
            param_frame,
            textvariable=self.num_modules,
            width=5,
            **STYLES['entry']
        )
        modules_entry.pack(side=tk.LEFT, padx=5)
        
        # Control buttons
        button_frame = tk.Frame(self.frame, bg=COLORS['bg_panel'])
        button_frame.pack(fill=tk.X, padx=10, pady=10)
        
        start_button_style = STYLES['button'].copy()
        start_button_style['font'] = FONTS['heading']
        self.start_button = tk.Button(
            button_frame,
            text="▶ START EVOLUTION",
            command=self._start_evolution,
            **start_button_style
        )
        self.start_button.pack(side=tk.LEFT, padx=5)
        
        stop_button_style = STYLES['button'].copy()
        stop_button_style['fg'] = COLORS['error']
        self.stop_button = tk.Button(
            button_frame,
            text="⏹ STOP",
            command=self._stop_evolution,
            **stop_button_style
        )
        self.stop_button.pack(side=tk.LEFT, padx=5)
        
        # Status
        self.status_label = tk.Label(
            self.frame,
            text="Status: Ready",
            font=FONTS['default'],
            fg=COLORS['accent_green'],
            bg=COLORS['bg_panel']
        )
        self.status_label.pack(pady=5)
        
        # Evolution log
        log_frame = tk.Frame(self.frame, bg=COLORS['bg_panel'])
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        tk.Label(
            log_frame,
            text="Evolution Log:",
            font=FONTS['default'],
            fg=COLORS['text_primary'],
            bg=COLORS['bg_panel']
        ).pack(anchor=tk.W)
        
        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            height=10,
            bg=COLORS['bg_secondary'],
            fg=COLORS['accent_green'],
            insertbackground=COLORS['accent_cyan'],
            font=FONTS['mono'],
            relief=tk.FLAT,
            borderwidth=1
        )
        self.log_text.pack(fill=tk.BOTH, expand=True, pady=5)
        
        self.evolution_running = False
    
    def _start_evolution(self):
        """Start evolution cycle"""
        if self.evolution_callback:
            objectives = self.objectives_text.get('1.0', tk.END).strip().split('\n')
            objectives = [obj for obj in objectives if obj.strip()]
            
            num_modules = int(self.num_modules.get())
            
            self.evolution_running = True
            self.status_label.config(text="Status: Evolving...", fg=COLORS['accent_pink'])
            self.log_text.insert(tk.END, f"[EVOLUTION] Starting cycle with {len(objectives)} objectives\n")
            
            try:
                if self.evolution_callback:
                    result = self.evolution_callback(objectives, num_modules)
                    if result:
                        self.log_text.insert(tk.END, f"[SUCCESS] Evolution cycle completed\n")
                        self.log_text.insert(tk.END, f"  Best module: {result.best_module}\n")
                        self.log_text.insert(tk.END, f"  Score: {result.improvement_score:.3f}\n")
            except Exception as e:
                self.log_text.insert(tk.END, f"[ERROR] {str(e)}\n")
            
            self.evolution_running = False
            self.status_label.config(text="Status: Complete", fg=COLORS['accent_green'])
        
        self.log_text.see(tk.END)
    
    def _stop_evolution(self):
        """Stop evolution"""
        self.evolution_running = False
        self.status_label.config(text="Status: Stopped", fg=COLORS['error'])
        self.log_text.insert(tk.END, "[STOP] Evolution stopped by user\n")
        self.log_text.see(tk.END)
