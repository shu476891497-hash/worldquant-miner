"""
Main Cyberpunk GUI Window
"""

import logging
import sys
import os

# Use print for immediate visibility (before logging is configured)
print("[main_window] Starting imports...", flush=True)

logger = logging.getLogger(__name__)

print("[main_window] Importing tkinter...", flush=True)
import tkinter as tk
print("[main_window]   ✓ tkinter", flush=True)
from tkinter import ttk, messagebox
print("[main_window]   ✓ tkinter.ttk, messagebox", flush=True)
import json
from pathlib import Path
from typing import Optional
print("[main_window]   ✓ Standard library imports", flush=True)

print("[main_window] Importing GUI components...", flush=True)
from .components.dashboard import DashboardPanel
print("[main_window]   ✓ DashboardPanel", flush=True)
from .components.evolution_panel import EvolutionPanel
print("[main_window]   ✓ EvolutionPanel", flush=True)
from .components.config_panel import ConfigPanel
print("[main_window]   ✓ ConfigPanel", flush=True)
from .components.monitor_panel import MonitorPanel
print("[main_window]   ✓ MonitorPanel", flush=True)
from .components.database_panel import DatabasePanel
print("[main_window]   ✓ DatabasePanel", flush=True)
from .components.workflow_panel import WorkflowPanel
print("[main_window]   ✓ WorkflowPanel", flush=True)
from .components.log_terminal import LogTerminal
print("[main_window]   ✓ LogTerminal", flush=True)
from .theme import COLORS, FONTS, STYLES
print("[main_window]   ✓ Theme", flush=True)

# Import generation_two components
print("[main_window] Setting up paths for generation_two...", flush=True)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

print("[main_window] Importing generation_two core components...", flush=True)
try:
    from generation_two import (
        EnhancedTemplateGeneratorV3,
        ConfigManager,
        EvolutionExecutor,
        CodeGenerator,
        CodeEvaluator
    )
    print("[main_window]   ✓ generation_two core components", flush=True)
except Exception as e:
    print(f"[main_window]   ✗ ERROR importing generation_two: {e}", flush=True)
    import traceback
    traceback.print_exc()
    raise

print("[main_window] All imports completed!", flush=True)


class CyberpunkGUI:
    """Main cyberpunk-themed GUI application"""
    
    def __init__(self, credentials_path: str = None):
        """
        Initialize GUI
        
        Args:
            credentials_path: Path to credentials file (optional, will prompt if not provided)
        """
        self.root = tk.Tk()
        self.root.title("⚡ GENERATION TWO ⚡")
        self.root.configure(bg=COLORS['bg_primary'])
        self.root.geometry("1400x900")
        
        # Initialize credential manager
        from ..core.credential_manager import CredentialManager
        self.credential_manager = CredentialManager(base_path=credentials_path)
        
        # Initialize system (will be set after authentication)
        self.config_manager = ConfigManager()
        self.generator = None
        self.evolution_executor = None
        self.authenticated = False
        
        # Authenticate before allowing access
        if not self._authenticate(credentials_path):
            # Authentication failed - show error and exit
            self._show_auth_error()
            return
        
        # Initialize evolution components
        if self.generator:
            code_gen = CodeGenerator(ollama_manager=self.generator.template_generator.ollama_manager)
            code_eval = CodeEvaluator()
            self.evolution_executor = EvolutionExecutor(
                code_gen,
                code_eval,
                integration_callback=self._integrate_module
            )
        
        self._create_widgets()
        # Setup logging after widgets are created (needs log_terminal)
        self._setup_logging()
    
    def _authenticate(self, credentials_path: str = None) -> bool:
        """
        Authenticate user before allowing access
        
        Returns:
            True if authenticated, False otherwise
        """
        logger.info("🔐 Starting authentication process...")
        
        # Try to load from file first
        if credentials_path:
            if os.path.exists(credentials_path):
                logger.info(f"Loading credentials from: {credentials_path}")
                if self.credential_manager.load_from_file(Path(credentials_path)):
                    if self.credential_manager.validate_credentials():
                        logger.info("✅ Authentication successful from file")
                        self.authenticated = True
                        self._initialize_generator()
                        return True
                    else:
                        logger.warning("Credentials from file failed validation")
        
        # Try auto-load from standard locations
        if self.credential_manager.load_from_file():
            if self.credential_manager.validate_credentials():
                logger.info("✅ Authentication successful from auto-detected file")
                self.authenticated = True
                self._initialize_generator()
                return True
        
        # Show login dialog
        logger.info("No valid credentials found, showing login dialog...")
        from .components.login_dialog import LoginDialog
        
        def validate_login(username: str, password: str) -> bool:
            """Validate login credentials"""
            from ..core.credential_manager import Credentials
            temp_creds = Credentials(username=username, password=password)
            self.credential_manager.credentials = temp_creds
            
            if self.credential_manager.validate_credentials():
                logger.info("✅ Authentication successful from dialog")
                self.authenticated = True
                self._initialize_generator()
                return True
            else:
                logger.error("❌ Authentication failed from dialog")
                return False
        
        # Show login dialog (modal)
        login_dialog = LoginDialog(self.root, callback=validate_login)
        credentials = login_dialog.show()
        
        if credentials and self.authenticated:
            return True
        
        return False
    
    def _initialize_generator(self):
        """Initialize generator with authenticated credentials"""
        try:
            # Get authenticated session
            session = self.credential_manager.get_session()
            if not session:
                logger.error("No authenticated session available")
                return
            
            # Pass credentials directly to avoid temp file issues with re-authentication
            creds = self.credential_manager.get_credentials()
            credentials = [creds.username, creds.password]
            
            # Pass credentials directly (no temp file needed)
            self.generator = EnhancedTemplateGeneratorV3(credentials=credentials)
                
        except Exception as e:
            logger.error(f"Failed to initialize generator: {e}", exc_info=True)
            self.generator = None
    
    def _show_auth_error(self):
        """Show authentication error and exit"""
        error_window = tk.Toplevel(self.root)
        error_window.title("❌ Authentication Required")
        error_window.geometry("500x200")
        error_window.configure(bg=COLORS['bg_primary'])
        error_window.transient(self.root)
        error_window.grab_set()
        
        tk.Label(
            error_window,
            text="❌ AUTHENTICATION REQUIRED",
            font=FONTS['heading'],
            fg=COLORS['error'],
            bg=COLORS['bg_primary']
        ).pack(pady=20)
        
        tk.Label(
            error_window,
            text="Cannot access the system without valid credentials.\n\nPlease provide credentials to continue.",
            font=FONTS['default'],
            fg=COLORS['text_primary'],
            bg=COLORS['bg_primary'],
            justify=tk.CENTER
        ).pack(pady=10)
        
        tk.Button(
            error_window,
            text="Exit",
            command=lambda: self.root.quit(),
            **STYLES['button']
        ).pack(pady=20)
        
        # Close main window
        self.root.after(100, lambda: self.root.withdraw())
    
    def _create_widgets(self):
        """Create main window widgets"""
        # Create notebook for tabs
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TNotebook', background=COLORS['bg_primary'], borderwidth=0)
        style.configure('TNotebook.Tab', background=COLORS['bg_panel'], foreground=COLORS['accent_cyan'])
        style.map('TNotebook.Tab', background=[('selected', COLORS['bg_secondary'])])
        
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Workflow tab (first - guided experience)
        self.workflow_panel = WorkflowPanel(
            self.notebook,
            generator=self.generator
        )
        self.notebook.add(self.workflow_panel.frame, text="🚀 WORKFLOW")
        
        # Dashboard tab
        self.dashboard = DashboardPanel(
            self.notebook,
            update_callback=self._get_system_stats
        )
        self.notebook.add(self.dashboard.frame, text="📊 DASHBOARD")
        
        # Evolution tab
        self.evolution_panel = EvolutionPanel(
            self.notebook,
            evolution_callback=self._run_evolution
        )
        self.notebook.add(self.evolution_panel.frame, text="🧬 EVOLUTION")
        
        # Config tab
        self.config_panel = ConfigPanel(
            self.notebook,
            config_manager=self.config_manager,
            update_callback=self._on_config_change
        )
        self.notebook.add(self.config_panel.frame, text="⚙️ CONFIG")
        
        # Monitor tab
        self.monitor_panel = MonitorPanel(self.notebook)
        self.notebook.add(self.monitor_panel.frame, text="📡 MONITOR")
        
        # Database tab
        self.database_panel = DatabasePanel(
            self.notebook,
            db_config_callback=self._on_db_config_change
        )
        self.notebook.add(self.database_panel.frame, text="💾 DATABASE")
        
        # Create omnipresent log terminal (at bottom of window)
        self.log_terminal = LogTerminal(self.root)
        self.log_terminal.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=2)
    
    def _setup_logging(self):
        """Setup logging to GUI (both monitor panel and log terminal)"""
        class GUILogHandler(logging.Handler):
            def __init__(self, monitor_panel, log_terminal):
                super().__init__()
                self.monitor_panel = monitor_panel
                self.log_terminal = log_terminal
            
            def emit(self, record):
                level = record.levelname
                message = self.format(record)
                # Send to both monitor panel and log terminal
                if self.monitor_panel:
                    self.monitor_panel.add_log(level, message)
                if self.log_terminal:
                    self.log_terminal.add_log(level, message)
        
        handler = GUILogHandler(self.monitor_panel, self.log_terminal)
        handler.setFormatter(logging.Formatter('%(name)s - %(message)s'))
        logging.getLogger().addHandler(handler)
        logging.getLogger().setLevel(logging.DEBUG)  # Changed to DEBUG for more trace logs
    
    def _get_system_stats(self) -> dict:
        """Get system statistics"""
        if self.generator:
            stats = self.generator.get_system_stats()
            if self.evolution_executor:
                evo_stats = self.evolution_executor.get_evolution_stats()
                stats.update(evo_stats)
            return stats
        return {}
    
    def _run_evolution(self, objectives: list, num_modules: int) -> Optional:
        """Run evolution cycle"""
        if self.evolution_executor:
            return self.evolution_executor.execute_evolution_cycle(objectives, num_modules)
        return None
    
    def _on_config_change(self, section: str, config: dict):
        """Handle configuration change"""
        logging.info(f"Configuration updated: {section}")
        # Could trigger system reconfiguration here
    
    def _integrate_module(self, module, module_name: str):
        """Integrate evolved module into system"""
        logging.info(f"Integrating module: {module_name}")
        # Integration logic here
    
    def _on_db_config_change(self, config: dict):
        """Handle database configuration change"""
        logging.info(f"Database configuration changed: {config}")
        # Could reload database connection here
    
    def run(self):
        """Start GUI main loop"""
        self.root.mainloop()


def main():
    """Main entry point"""
    import sys
    
    credentials_path = None
    if len(sys.argv) > 1:
        credentials_path = sys.argv[1]
    else:
        # Try default location
        default_path = os.path.join(os.path.dirname(__file__), '..', 'credential.txt')
        if os.path.exists(default_path):
            credentials_path = default_path
    
    app = CyberpunkGUI(credentials_path)
    app.run()


if __name__ == "__main__":
    main()
