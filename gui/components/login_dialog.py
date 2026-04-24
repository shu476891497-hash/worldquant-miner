"""
Login Dialog Component
Secure credential entry for GUI
"""

import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Callable
import logging

from ..theme import COLORS, FONTS, STYLES

logger = logging.getLogger(__name__)


class LoginDialog:
    """Modal login dialog for credential entry"""
    
    def __init__(self, parent, callback: Optional[Callable] = None):
        """
        Initialize login dialog
        
        Args:
            parent: Parent window
            callback: Callback function(username, password) -> bool
                     Returns True if login successful, False otherwise
        """
        self.parent = parent
        self.callback = callback
        self.result = None
        self.credentials = None
        
        # Create modal dialog
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("🔐 Authentication Required")
        self.dialog.geometry("500x350")
        self.dialog.configure(bg=COLORS['bg_primary'])
        self.dialog.resizable(False, False)
        
        # Make dialog modal
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        # Center dialog
        self._center_dialog()
        
        # Prevent closing without credentials
        self.dialog.protocol("WM_DELETE_WINDOW", self._on_close_attempt)
        
        self._create_widgets()
        
        # Focus on username field
        self.username_entry.focus_set()
        
        # Bind Enter key
        self.dialog.bind('<Return>', lambda e: self._handle_login())
    
    def _center_dialog(self):
        """Center dialog on parent window"""
        self.dialog.update_idletasks()
        parent_x = self.parent.winfo_x()
        parent_y = self.parent.winfo_y()
        parent_width = self.parent.winfo_width()
        parent_height = self.parent.winfo_height()
        
        dialog_width = self.dialog.winfo_width()
        dialog_height = self.dialog.winfo_height()
        
        x = parent_x + (parent_width - dialog_width) // 2
        y = parent_y + (parent_height - dialog_height) // 2
        
        self.dialog.geometry(f"+{x}+{y}")
    
    def _create_widgets(self):
        """Create dialog widgets"""
        # Title
        title_frame = tk.Frame(self.dialog, bg=COLORS['bg_primary'])
        title_frame.pack(pady=20)
        
        tk.Label(
            title_frame,
            text="🔐 WORLDQUANT BRAIN AUTHENTICATION",
            font=FONTS['heading'],
            fg=COLORS['accent_cyan'],
            bg=COLORS['bg_primary']
        ).pack()
        
        tk.Label(
            title_frame,
            text="Credentials required to access the system",
            font=FONTS['default'],
            fg=COLORS['text_secondary'],
            bg=COLORS['bg_primary']
        ).pack(pady=5)
        
        # Credential input frame
        input_frame = tk.Frame(self.dialog, bg=COLORS['bg_panel'], relief=tk.RAISED, bd=2)
        input_frame.pack(padx=30, pady=20, fill=tk.BOTH, expand=True)
        
        # Username
        tk.Label(
            input_frame,
            text="Username (Email):",
            font=FONTS['default'],
            fg=COLORS['text_primary'],
            bg=COLORS['bg_panel']
        ).pack(anchor=tk.W, padx=20, pady=(20, 5))
        
        self.username_entry = tk.Entry(
            input_frame,
            font=FONTS['default'],
            bg=COLORS['bg_secondary'],
            fg=COLORS['accent_cyan'],
            insertbackground=COLORS['accent_cyan'],
            width=40
        )
        self.username_entry.pack(padx=20, pady=(0, 15), fill=tk.X)
        
        # Password
        tk.Label(
            input_frame,
            text="Password:",
            font=FONTS['default'],
            fg=COLORS['text_primary'],
            bg=COLORS['bg_panel']
        ).pack(anchor=tk.W, padx=20, pady=(0, 5))
        
        self.password_entry = tk.Entry(
            input_frame,
            font=FONTS['default'],
            bg=COLORS['bg_secondary'],
            fg=COLORS['accent_cyan'],
            insertbackground=COLORS['accent_cyan'],
            show="*",  # Hide password
            width=40
        )
        self.password_entry.pack(padx=20, pady=(0, 20), fill=tk.X)
        
        # Info label
        info_label = tk.Label(
            input_frame,
            text="💡 Tip: You can also create credential.txt or credentials.txt file",
            font=FONTS['small'],
            fg=COLORS['text_secondary'],
            bg=COLORS['bg_panel'],
            wraplength=400
        )
        info_label.pack(padx=20, pady=(0, 10))
        
        # Buttons
        button_frame = tk.Frame(self.dialog, bg=COLORS['bg_primary'])
        button_frame.pack(pady=20)
        
        login_button = tk.Button(
            button_frame,
            text="🔐 LOGIN",
            command=self._handle_login,
            font=FONTS['default'],
            fg=COLORS['bg_primary'],
            bg=COLORS['accent_cyan'],
            relief=tk.RAISED,
            bd=2,
            padx=30,
            pady=10,
            cursor="hand2"
        )
        login_button.pack(side=tk.LEFT, padx=10)
        
        cancel_button = tk.Button(
            button_frame,
            text="❌ CANCEL",
            command=self._handle_cancel,
            font=FONTS['default'],
            fg=COLORS['text_primary'],
            bg=COLORS['bg_secondary'],
            relief=tk.RAISED,
            bd=2,
            padx=30,
            pady=10,
            cursor="hand2"
        )
        cancel_button.pack(side=tk.LEFT, padx=10)
        
        # Status label
        self.status_label = tk.Label(
            self.dialog,
            text="",
            font=FONTS['default'],
            fg=COLORS['error'],
            bg=COLORS['bg_primary']
        )
        self.status_label.pack(pady=5)
    
    def _handle_login(self):
        """Handle login button click"""
        username = self.username_entry.get().strip()
        password = self.password_entry.get().strip()
        
        if not username:
            self.status_label.config(text="❌ Please enter username", fg=COLORS['error'])
            self.username_entry.focus_set()
            return
        
        if not password:
            self.status_label.config(text="❌ Please enter password", fg=COLORS['error'])
            self.password_entry.focus_set()
            return
        
        # Show validating message
        self.status_label.config(text="⏳ Validating credentials...", fg=COLORS['accent_yellow'])
        self.dialog.update()
        
        # Call callback if provided
        if self.callback:
            try:
                success = self.callback(username, password)
                if success:
                    self.credentials = {'username': username, 'password': password}
                    self.result = True
                    self.dialog.destroy()
                else:
                    self.status_label.config(
                        text="❌ Authentication failed. Please check your credentials.",
                        fg=COLORS['error']
                    )
                    self.password_entry.delete(0, tk.END)
                    self.password_entry.focus_set()
            except Exception as e:
                logger.error(f"Error in login callback: {e}", exc_info=True)
                self.status_label.config(
                    text=f"❌ Error: {str(e)[:100]}",
                    fg=COLORS['error']
                )
        else:
            # No callback - just store credentials
            self.credentials = {'username': username, 'password': password}
            self.result = True
            self.dialog.destroy()
    
    def _handle_cancel(self):
        """Handle cancel button click"""
        self.result = False
        self.credentials = None
        self.dialog.destroy()
    
    def _on_close_attempt(self):
        """Handle window close attempt"""
        # Prevent closing without credentials
        if messagebox.askokcancel(
            "Exit Application",
            "Authentication is required to use this application.\n\nExit anyway?",
            parent=self.dialog
        ):
            self._handle_cancel()
    
    def show(self) -> Optional[dict]:
        """
        Show dialog and wait for result
        
        Returns:
            Dictionary with 'username' and 'password' if login successful, None otherwise
        """
        self.dialog.wait_window()
        return self.credentials
