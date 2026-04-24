"""
Step 2: Operator Visualization
Handles operator browsing and details display
"""

import tkinter as tk
from tkinter import ttk, scrolledtext
import logging

from ...theme import COLORS, FONTS, STYLES

logger = logging.getLogger(__name__)


class Step2Operators:
    """Step 2: Operator Visualization"""
    
    def __init__(self, parent_frame, workflow_panel):
        """
        Initialize Step 2
        
        Args:
            parent_frame: Parent frame to pack into
            workflow_panel: Reference to main WorkflowPanel for callbacks
        """
        self.parent_frame = parent_frame
        self.workflow = workflow_panel
        self.frame = tk.Frame(parent_frame, bg=COLORS['bg_panel'])
        
        self._create_widgets()
    
    def _create_widgets(self):
        """Create Step 2 widgets"""
        tk.Label(
            self.frame,
            text="Step 2: Operator Visualization",
            font=FONTS['heading'],
            fg=COLORS['accent_cyan'],
            bg=COLORS['bg_panel']
        ).pack(pady=10)
        
        tk.Label(
            self.frame,
            text="Operators are loaded and ready. Browse by category:",
            font=FONTS['default'],
            fg=COLORS['text_primary'],
            bg=COLORS['bg_panel']
        ).pack(pady=5)
        
        # Operator browser
        op_browser_frame = tk.Frame(self.frame, bg=COLORS['bg_panel'])
        op_browser_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Category selector
        cat_frame = tk.Frame(op_browser_frame, bg=COLORS['bg_panel'])
        cat_frame.pack(fill=tk.X, pady=5)
        
        tk.Label(
            cat_frame,
            text="Category:",
            font=FONTS['default'],
            fg=COLORS['text_primary'],
            bg=COLORS['bg_panel']
        ).pack(side=tk.LEFT, padx=5)
        
        self.category_var = tk.StringVar(value="All")
        category_combo = ttk.Combobox(
            cat_frame,
            textvariable=self.category_var,
            values=["All", "Arithmetic", "Time Series", "Cross Sectional", "Vector", "Logical"],
            state="readonly",
            width=20
        )
        category_combo.pack(side=tk.LEFT, padx=5)
        category_combo.bind('<<ComboboxSelected>>', lambda e: self.workflow._update_operator_list())
        
        # Operator list
        op_list_frame = tk.Frame(op_browser_frame, bg=COLORS['bg_panel'])
        op_list_frame.pack(fill=tk.BOTH, expand=True)
        
        self.operator_listbox = tk.Listbox(
            op_list_frame,
            bg=COLORS['bg_secondary'],
            fg=COLORS['accent_cyan'],
            font=FONTS['mono'],
            selectbackground=COLORS['accent_cyan'],
            selectforeground=COLORS['bg_primary']
        )
        self.operator_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        op_scrollbar = tk.Scrollbar(op_list_frame, orient=tk.VERTICAL, command=self.operator_listbox.yview)
        op_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.operator_listbox.config(yscrollcommand=op_scrollbar.set)
        
        # Operator details
        op_details_frame = tk.Frame(self.frame, bg=COLORS['bg_panel'])
        op_details_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        self.operator_details = scrolledtext.ScrolledText(
            op_details_frame,
            height=8,
            bg=COLORS['bg_secondary'],
            fg=COLORS['accent_green'],
            font=FONTS['mono'],
            wrap=tk.WORD
        )
        self.operator_details.pack(fill=tk.BOTH, expand=True)
        
        self.operator_listbox.bind('<<ListboxSelect>>', self.workflow._show_operator_details)
        
        # Store references in workflow for backward compatibility
        self.workflow.category_var = self.category_var
        self.workflow.operator_listbox = self.operator_listbox
        self.workflow.operator_details = self.operator_details
