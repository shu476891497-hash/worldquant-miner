"""
Monitor Panel
Real-time monitoring of system operations
"""

import tkinter as tk
from tkinter import scrolledtext
from typing import Optional, Callable
import threading
import queue

from ..theme import COLORS, FONTS, STYLES


class MonitorPanel:
    """Panel for monitoring system operations"""
    
    def __init__(self, parent, log_callback: Optional[Callable] = None):
        """
        Initialize monitor panel
        
        Args:
            parent: Parent widget
            log_callback: Callback to get logs
        """
        self.parent = parent
        self.log_callback = log_callback
        
        self.frame = tk.Frame(parent, **STYLES['frame'])
        self.frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.log_queue = queue.Queue()
        self._create_widgets()
        self._start_monitoring()
    
    def _create_widgets(self):
        """Create monitoring widgets"""
        # Title
        title = tk.Label(
            self.frame,
            text="📊 SYSTEM MONITOR 📊",
            font=FONTS['heading'],
            fg=COLORS['accent_cyan'],
            bg=COLORS['bg_panel']
        )
        title.pack(pady=10)
        
        # Log display
        self.log_text = scrolledtext.ScrolledText(
            self.frame,
            height=20,
            bg=COLORS['bg_secondary'],
            fg=COLORS['accent_green'],
            insertbackground=COLORS['accent_cyan'],
            font=FONTS['mono'],
            relief=tk.FLAT,
            borderwidth=1,
            wrap=tk.WORD
        )
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Configure tags for different log levels
        self.log_text.tag_config('INFO', foreground=COLORS['accent_cyan'])
        self.log_text.tag_config('WARNING', foreground=COLORS['accent_yellow'])
        self.log_text.tag_config('ERROR', foreground=COLORS['error'])
        self.log_text.tag_config('SUCCESS', foreground=COLORS['accent_green'])
        
        # Clear button
        clear_button = tk.Button(
            self.frame,
            text="🗑️ CLEAR",
            command=self._clear_logs,
            **STYLES['button']
        )
        clear_button.pack(pady=5)
    
    def _start_monitoring(self):
        """Start monitoring loop"""
        self._process_log_queue()
        self.frame.after(100, self._start_monitoring)
    
    def _process_log_queue(self):
        """Process queued log messages"""
        try:
            while True:
                message = self.log_queue.get_nowait()
                self._add_log(message['level'], message['text'])
        except queue.Empty:
            pass
    
    def _add_log(self, level: str, text: str):
        """Add log message"""
        self.log_text.insert(tk.END, f"[{level}] {text}\n", level)
        self.log_text.see(tk.END)
        
        # Limit log size
        lines = int(self.log_text.index('end-1c').split('.')[0])
        if lines > 1000:
            self.log_text.delete('1.0', '100.0')
    
    def _clear_logs(self):
        """Clear log display"""
        self.log_text.delete('1.0', tk.END)
    
    def add_log(self, level: str, text: str):
        """Add log message (thread-safe)"""
        self.log_queue.put({'level': level, 'text': text})
