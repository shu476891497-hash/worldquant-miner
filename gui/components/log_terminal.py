"""
Log Terminal Component
Omnipresent mini terminal for trace logs
"""

import tkinter as tk
from tkinter import scrolledtext
import logging
import queue
import threading
from typing import Optional

from ..theme import COLORS, FONTS


class LogTerminal:
    """Floating mini terminal for trace logs"""
    
    def __init__(self, parent):
        """
        Initialize log terminal
        
        Args:
            parent: Parent widget (main window)
        """
        self.parent = parent
        self.log_queue = queue.Queue()
        self.max_lines = 500
        
        # Create floating frame
        self.frame = tk.Frame(parent, bg=COLORS['bg_primary'], relief=tk.RAISED, bd=2)
        
        # Title bar
        title_frame = tk.Frame(self.frame, bg=COLORS['bg_secondary'], height=25)
        title_frame.pack(fill=tk.X)
        title_frame.pack_propagate(False)
        
        tk.Label(
            title_frame,
            text="📟 TRACE LOGS",
            font=FONTS['default'],
            fg=COLORS['accent_cyan'],
            bg=COLORS['bg_secondary']
        ).pack(side=tk.LEFT, padx=5)
        
        # Clear button
        clear_btn = tk.Button(
            title_frame,
            text="Clear",
            command=self._clear_logs,
            font=FONTS['default'],
            fg=COLORS['text_primary'],
            bg=COLORS['bg_secondary'],
            relief=tk.FLAT,
            bd=0,
            padx=5,
            pady=2
        )
        clear_btn.pack(side=tk.RIGHT, padx=2)
        
        # Toggle button
        self.collapsed = False
        self.toggle_btn = tk.Button(
            title_frame,
            text="▼",
            command=self._toggle,
            font=FONTS['default'],
            fg=COLORS['text_primary'],
            bg=COLORS['bg_secondary'],
            relief=tk.FLAT,
            bd=0,
            padx=5,
            pady=2
        )
        self.toggle_btn.pack(side=tk.RIGHT, padx=2)
        
        # Log text area
        self.log_text = scrolledtext.ScrolledText(
            self.frame,
            height=8,
            bg=COLORS['bg_secondary'],
            fg=COLORS['accent_green'],
            font=FONTS['mono'],
            wrap=tk.WORD,
            relief=tk.FLAT,
            bd=0,
            padx=5,
            pady=5
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # Configure text tags for different log levels
        self.log_text.tag_config('DEBUG', foreground=COLORS['text_secondary'])
        self.log_text.tag_config('INFO', foreground=COLORS['accent_green'])
        self.log_text.tag_config('WARNING', foreground=COLORS['accent_yellow'])
        self.log_text.tag_config('ERROR', foreground=COLORS['error'])
        self.log_text.tag_config('CRITICAL', foreground=COLORS['error'], background=COLORS['bg_primary'])
        
        # Start processing log queue
        self._process_log_queue()
    
    def _toggle(self):
        """Toggle terminal collapse/expand"""
        self.collapsed = not self.collapsed
        if self.collapsed:
            self.log_text.pack_forget()
            self.toggle_btn.config(text="▲")
        else:
            self.log_text.pack(fill=tk.BOTH, expand=True)
            self.toggle_btn.config(text="▼")
    
    def _clear_logs(self):
        """Clear log display"""
        self.log_text.delete('1.0', tk.END)
    
    def _process_log_queue(self):
        """Process log messages from queue (thread-safe)"""
        try:
            while True:
                log_entry = self.log_queue.get_nowait()
                self._add_log(log_entry['level'], log_entry['text'])
        except queue.Empty:
            pass
        
        # Schedule next check
        self.frame.after(100, self._process_log_queue)
    
    def _add_log(self, level: str, text: str):
        """Add log message to display"""
        # Truncate if too long
        if len(text) > 500:
            text = text[:497] + "..."
        
        # Add timestamp
        import datetime
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        
        # Insert log with appropriate tag
        log_line = f"[{timestamp}] [{level}] {text}\n"
        self.log_text.insert(tk.END, log_line, level)
        self.log_text.see(tk.END)
        
        # Limit log size
        lines = int(self.log_text.index('end-1c').split('.')[0])
        if lines > self.max_lines:
            # Remove oldest 100 lines
            self.log_text.delete('1.0', f'{100}.0')
    
    def add_log(self, level: str, text: str):
        """Add log message (thread-safe)"""
        self.log_queue.put({'level': level, 'text': text})
    
    def pack(self, **kwargs):
        """Pack the terminal frame"""
        self.frame.pack(**kwargs)
    
    def pack_forget(self):
        """Hide the terminal"""
        self.frame.pack_forget()
