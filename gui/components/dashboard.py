"""
Dashboard Panel
Main overview with key metrics
"""

import tkinter as tk
from tkinter import ttk
from typing import Dict, Optional
import threading
import time

from ..theme import COLORS, FONTS, STYLES


class DashboardPanel:
    """Main dashboard showing system overview"""
    
    def __init__(self, parent, update_callback=None):
        """
        Initialize dashboard panel
        
        Args:
            parent: Parent widget
            update_callback: Callback to get system stats
        """
        self.parent = parent
        self.update_callback = update_callback
        
        self.frame = tk.Frame(parent, **STYLES['frame'])
        self.frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self._create_widgets()
        self._start_updates()
    
    def _create_widgets(self):
        """Create dashboard widgets"""
        # Title
        title = tk.Label(
            self.frame,
            text="⚡ GENERATION TWO CONTROL CENTER ⚡",
            font=FONTS['title'],
            fg=COLORS['accent_cyan'],
            bg=COLORS['bg_panel']
        )
        title.pack(pady=10)
        
        # Stats grid
        self.stats_frame = tk.Frame(self.frame, bg=COLORS['bg_panel'])
        self.stats_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Create stat labels
        self.stat_labels = {}
        stats = [
            ('Total Results', 'total_results', COLORS['accent_cyan']),
            ('Successful Alphas', 'successful_alphas', COLORS['accent_green']),
            ('Evolution Cycles', 'evolution_cycles', COLORS['accent_pink']),
            ('Active Modules', 'active_modules', COLORS['accent_yellow']),
            ('Success Rate', 'success_rate', COLORS['accent_green']),
            ('Avg Sharpe', 'avg_sharpe', COLORS['accent_cyan']),
        ]
        
        row = 0
        col = 0
        for label_text, key, color in stats:
            frame = tk.Frame(self.stats_frame, bg=COLORS['bg_secondary'], relief=tk.RAISED, bd=2)
            frame.grid(row=row, column=col, padx=5, pady=5, sticky='nsew')
            
            label = tk.Label(
                frame,
                text=label_text,
                font=FONTS['default'],
                fg=COLORS['text_secondary'],
                bg=COLORS['bg_secondary']
            )
            label.pack(pady=5)
            
            value_label = tk.Label(
                frame,
                text="--",
                font=FONTS['heading'],
                fg=color,
                bg=COLORS['bg_secondary']
            )
            value_label.pack(pady=5)
            
            self.stat_labels[key] = value_label
            
            col += 1
            if col >= 3:
                col = 0
                row += 1
        
        # Configure grid weights
        for i in range(3):
            self.stats_frame.columnconfigure(i, weight=1)
    
    def _start_updates(self):
        """Start periodic updates"""
        self._update_stats()
        self.frame.after(2000, self._start_updates)  # Update every 2 seconds
    
    def _update_stats(self):
        """Update dashboard statistics"""
        if self.update_callback:
            try:
                stats = self.update_callback()
                self._display_stats(stats)
            except Exception as e:
                print(f"Error updating stats: {e}")
    
    def _display_stats(self, stats: Dict):
        """Display statistics"""
        # Update stat labels
        if 'total_results' in stats:
            self.stat_labels['total_results'].config(text=str(stats['total_results']))
        
        if 'successful_alphas' in stats:
            self.stat_labels['successful_alphas'].config(text=str(stats['successful_alphas']))
        
        if 'evolution_cycles' in stats:
            self.stat_labels['evolution_cycles'].config(text=str(stats.get('evolution_cycles', 0)))
        
        if 'active_modules' in stats:
            self.stat_labels['active_modules'].config(text=str(stats.get('active_modules', 0)))
        
        # Calculate success rate
        if 'total_results' in stats and 'successful_alphas' in stats:
            total = stats['total_results']
            successful = stats['successful_alphas']
            if total > 0:
                rate = (successful / total) * 100
                self.stat_labels['success_rate'].config(text=f"{rate:.1f}%")
        
        # Avg Sharpe
        if 'avg_sharpe' in stats:
            self.stat_labels['avg_sharpe'].config(text=f"{stats['avg_sharpe']:.3f}")
