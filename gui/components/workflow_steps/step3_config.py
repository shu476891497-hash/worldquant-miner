"""
Step 3: Configuration
Handles system configuration navigation
"""

import tkinter as tk
import logging

from ...theme import COLORS, FONTS, STYLES

logger = logging.getLogger(__name__)


class Step3Config:
    """Step 3: Configure System"""
    
    def __init__(self, parent_frame, workflow_panel):
        """
        Initialize Step 3
        
        Args:
            parent_frame: Parent frame to pack into
            workflow_panel: Reference to main WorkflowPanel for callbacks
        """
        self.parent_frame = parent_frame
        self.workflow = workflow_panel
        self.frame = tk.Frame(parent_frame, bg=COLORS['bg_panel'])
        
        self._create_widgets()
    
    def _create_widgets(self):
        """Create Step 3 widgets"""
        tk.Label(
            self.frame,
            text="Step 3: Configure System",
            font=FONTS['heading'],
            fg=COLORS['accent_cyan'],
            bg=COLORS['bg_panel']
        ).pack(pady=10)
        
        tk.Label(
            self.frame,
            text="Configure reusable functionalities and changeable logic:",
            font=FONTS['default'],
            fg=COLORS['text_primary'],
            bg=COLORS['bg_panel']
        ).pack(pady=5)
        
        # Config sections
        config_sections = [
            ("Retry Strategy", "retry", "Configure retry logic (Linear, Exponential, Fibonacci)"),
            ("Request Settings", "request", "HTTP request timeout and retry settings"),
            ("Simulation", "simulation", "Simulation parameters and limits"),
            ("Evolution", "evolution", "Genetic algorithm parameters"),
            ("Template Generation", "template_generation", "Template generation strategy")
        ]
        
        for section_name, section_key, description in config_sections:
            section_frame = tk.Frame(self.frame, bg=COLORS['bg_secondary'], relief=tk.RAISED, bd=2)
            section_frame.pack(fill=tk.X, padx=10, pady=5)
            
            tk.Label(
                section_frame,
                text=f"⚙️ {section_name}",
                font=FONTS['default'],
                fg=COLORS['accent_yellow'],
                bg=COLORS['bg_secondary']
            ).pack(anchor=tk.W, padx=5, pady=2)
            
            tk.Label(
                section_frame,
                text=description,
                font=FONTS['default'],
                fg=COLORS['text_secondary'],
                bg=COLORS['bg_secondary']
            ).pack(anchor=tk.W, padx=5, pady=2)
            
            tk.Button(
                section_frame,
                text="Configure",
                command=lambda k=section_key: self.workflow._open_config_section(k),
                **STYLES['button']
            ).pack(anchor=tk.E, padx=5, pady=5)
