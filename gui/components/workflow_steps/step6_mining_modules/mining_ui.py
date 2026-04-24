"""
Mining UI Module
Handles UI components for continuous mining
"""

import tkinter as tk
from tkinter import ttk, scrolledtext
from typing import Dict
from generation_two.gui.theme import COLORS, FONTS, STYLES


class MiningUI:
    """UI components for continuous mining"""
    
    def __init__(self, parent_frame):
        """
        Initialize mining UI
        
        Args:
            parent_frame: Parent frame to pack into
        """
        self.frame = tk.Frame(parent_frame, bg=COLORS['bg_panel'])
        self.mining_slot_widgets: Dict = {}
        self.mining_log = None
        self.start_mining_button = None
        self.stop_mining_button = None
        self.sim_counter_label = None
        self.mining_status_label = None
        
        self._create_widgets()
    
    def _create_widgets(self):
        """Create mining UI widgets"""
        # Title
        tk.Label(
            self.frame,
            text="Step 6: Continuous Alpha Mining",
            font=FONTS['heading'],
            fg=COLORS['accent_cyan'],
            bg=COLORS['bg_panel']
        ).pack(pady=10)
        
        # Description
        tk.Label(
            self.frame,
            text="Start mining alphas indefinitely across all regions. System will automatically:\n"
                 "• Generate templates for each region\n"
                 "• Simulate and test alphas (target: 5,000/day)\n"
                 "• Save all results to database\n"
                 "• Prioritize low-correlation alphas\n"
                 "• Filter duplicates\n"
                 "• Support BFS and DFS strategies",
            font=FONTS['default'],
            fg=COLORS['text_primary'],
            bg=COLORS['bg_panel'],
            justify=tk.LEFT
        ).pack(pady=5, padx=10)
        
        # Main container
        main_container = tk.Frame(self.frame, bg=COLORS['bg_panel'])
        main_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Left column
        left_column = tk.Frame(main_container, bg=COLORS['bg_panel'])
        left_column.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        # Right column (log)
        right_column = tk.Frame(main_container, bg=COLORS['bg_panel'])
        right_column.pack(side=tk.RIGHT, fill=tk.BOTH, expand=False, padx=(5, 0))
        right_column.config(width=450)
        
        # Controls
        self._create_controls(left_column)
        
        # Mining slots
        self._create_mining_slots(left_column)
        
        # Mining log
        self._create_mining_log(right_column)
    
    def _create_controls(self, parent):
        """Create control buttons and status"""
        mining_frame = tk.Frame(parent, bg=COLORS['bg_secondary'], relief=tk.RAISED, bd=2)
        mining_frame.pack(fill=tk.X, padx=5, pady=5)
        
        controls_frame = tk.Frame(mining_frame, bg=COLORS['bg_secondary'])
        controls_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # Start button
        start_button_style = STYLES['button'].copy()
        start_button_style.pop('bg', None)
        start_button_style.pop('fg', None)
        start_button_style.pop('font', None)
        
        self.start_mining_button = tk.Button(
            controls_frame,
            text="🚀 START MINING",
            **start_button_style,
            bg=COLORS['accent_green'],
            fg='white',
            font=('Arial', 12, 'bold')
        )
        self.start_mining_button.pack(side=tk.LEFT, padx=5)
        
        # Stop button
        stop_button_style = STYLES['button'].copy()
        stop_button_style.pop('bg', None)
        stop_button_style.pop('fg', None)
        stop_button_style.pop('font', None)
        
        self.stop_mining_button = tk.Button(
            controls_frame,
            text="⏹ STOP MINING",
            **stop_button_style,
            bg=COLORS['error'],
            fg='white',
            state=tk.DISABLED
        )
        self.stop_mining_button.pack(side=tk.LEFT, padx=5)
        
        # Status
        status_frame = tk.Frame(mining_frame, bg=COLORS['bg_secondary'])
        status_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.sim_counter_label = tk.Label(
            status_frame,
            text="Today's Simulations: 0 / 5,000 (EST)",
            font=FONTS['default'],
            fg=COLORS['text_primary'],
            bg=COLORS['bg_secondary']
        )
        self.sim_counter_label.pack(side=tk.LEFT, padx=5)
        
        self.mining_status_label = tk.Label(
            status_frame,
            text="Status: Idle",
            font=FONTS['default'],
            fg=COLORS['accent_yellow'],
            bg=COLORS['bg_secondary']
        )
        self.mining_status_label.pack(side=tk.LEFT, padx=20)
    
    def _create_mining_slots(self, parent):
        """Create mining slot widgets"""
        mining_slots_frame = tk.Frame(parent, bg=COLORS['bg_secondary'], relief=tk.RAISED, bd=2)
        mining_slots_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        tk.Label(
            mining_slots_frame,
            text="Mining Slots (8 concurrent, GLB uses 2 slots)",
            font=FONTS['heading'],
            fg=COLORS['accent_cyan'],
            bg=COLORS['bg_secondary']
        ).pack(pady=5)
        
        # Create 2x4 grid
        slots_grid = tk.Frame(mining_slots_frame, bg=COLORS['bg_secondary'])
        slots_grid.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        for row in range(2):
            for col in range(4):
                slot_id = row * 4 + col
                slot_frame = tk.Frame(slots_grid, bg=COLORS['bg_panel'], relief=tk.RAISED, bd=2)
                slot_frame.grid(row=row, column=col, padx=5, pady=5, sticky='nsew')
                slots_grid.grid_columnconfigure(col, weight=1)
                slots_grid.grid_rowconfigure(row, weight=1)
                
                # Header
                header = tk.Frame(slot_frame, bg=COLORS['bg_panel'])
                header.pack(fill=tk.X, padx=2, pady=2)
                
                slot_num_label = tk.Label(
                    header,
                    text=f"[{slot_id + 1}]",
                    font=FONTS['default'],
                    fg=COLORS['accent_cyan'],
                    bg=COLORS['bg_panel']
                )
                slot_num_label.pack(side=tk.LEFT)
                
                status_label = tk.Label(
                    header,
                    text="IDLE",
                    font=FONTS['default'],
                    fg=COLORS['accent_green'],
                    bg=COLORS['bg_panel']
                )
                status_label.pack(side=tk.RIGHT)
                
                # Template preview
                template_label = tk.Label(
                    slot_frame,
                    text="",
                    font=FONTS['mono'],
                    fg=COLORS['text_secondary'],
                    bg=COLORS['bg_panel'],
                    wraplength=150,
                    justify=tk.LEFT
                )
                template_label.pack(fill=tk.X, padx=2, pady=2)
                
                # Region info
                region_label = tk.Label(
                    slot_frame,
                    text="",
                    font=('Arial', 7),
                    fg=COLORS['text_secondary'],
                    bg=COLORS['bg_panel']
                )
                region_label.pack(fill=tk.X, padx=2)
                
                # Progress bar
                progress_frame = tk.Frame(slot_frame, bg=COLORS['bg_panel'])
                progress_frame.pack(fill=tk.X, padx=2, pady=2)
                
                progress_label = tk.Label(
                    progress_frame,
                    text="0%",
                    font=('Courier', 7),
                    fg=COLORS['accent_cyan'],
                    bg=COLORS['bg_panel'],
                    width=5
                )
                progress_label.pack(side=tk.LEFT, padx=2)
                
                progress_bar = ttk.Progressbar(
                    progress_frame,
                    mode='determinate',
                    length=120
                )
                progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
                
                progress_text = tk.Label(
                    progress_frame,
                    text="",
                    font=('Courier', 6),
                    fg=COLORS['text_secondary'],
                    bg=COLORS['bg_panel'],
                    wraplength=120
                )
                progress_text.pack(fill=tk.X, padx=2)
                
                # Log
                log_text = scrolledtext.ScrolledText(
                    slot_frame,
                    height=6,
                    width=25,
                    bg=COLORS['bg_secondary'],
                    fg=COLORS['accent_green'],
                    font=('Courier', 8),
                    wrap=tk.WORD,
                    state=tk.DISABLED
                )
                log_text.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
                
                self.mining_slot_widgets[slot_id] = {
                    'frame': slot_frame,
                    'status_label': status_label,
                    'template_label': template_label,
                    'region_label': region_label,
                    'progress_label': progress_label,
                    'progress_bar': progress_bar,
                    'progress_text': progress_text,
                    'log_text': log_text
                }
    
    def _create_mining_log(self, parent):
        """Create mining log widget"""
        log_frame = tk.Frame(parent, bg=COLORS['bg_secondary'], relief=tk.RAISED, bd=2)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        tk.Label(
            log_frame,
            text="📋 MINING LOG",
            font=FONTS['heading'],
            fg=COLORS['accent_cyan'],
            bg=COLORS['bg_secondary']
        ).pack(pady=5)
        
        self.mining_log = scrolledtext.ScrolledText(
            log_frame,
            width=50,
            height=40,
            font=('Courier', 9),
            bg=COLORS['bg_panel'],
            fg=COLORS['text_primary'],
            wrap=tk.WORD,
            relief=tk.SUNKEN,
            bd=2
        )
        self.mining_log.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
    
    def update_slot_display(self, slot_id, status, template, region_info, progress, message, logs=None):
        """Update mining slot display"""
        if slot_id not in self.mining_slot_widgets:
            return
        
        widget = self.mining_slot_widgets[slot_id]
        
        # Status colors
        status_colors = {
            'IDLE': COLORS.get('text_secondary', '#666666'),
            'RUNNING': COLORS.get('accent_yellow', '#ffff00'),
            'SUCCESS': COLORS.get('accent_green', '#00ff41'),
            'COMPLETED': COLORS.get('accent_green', '#00ff41'),
            'FAILED': COLORS.get('error', '#ff0000')
        }
        widget['status_label'].config(
            text=status,
            fg=status_colors.get(status, COLORS['text_primary'])
        )
        
        widget['template_label'].config(text=template if template else "")
        widget['region_label'].config(text=region_info if region_info else "")
        widget['progress_label'].config(text=f"{int(progress)}%")
        widget['progress_bar']['value'] = progress
        widget['progress_text'].config(text=message if message else "")
        
        if logs:
            widget['log_text'].config(state=tk.NORMAL)
            widget['log_text'].delete(1.0, tk.END)
            for log_line in logs:
                widget['log_text'].insert(tk.END, str(log_line) + "\n")
            widget['log_text'].see(tk.END)
            widget['log_text'].config(state=tk.DISABLED)
    
    def log_message(self, message: str):
        """Log message to mining log"""
        self.mining_log.insert(tk.END, message)
        self.mining_log.see(tk.END)
