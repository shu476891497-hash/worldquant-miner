"""
Step 1: Data Fields Setup
Handles operator loading and data field fetching/loading
"""

import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path
import json
import os
import threading
import logging

from ...theme import COLORS, FONTS, STYLES

logger = logging.getLogger(__name__)


class Step1DataFields:
    """Step 1: Load Operators & Data Fields"""
    
    def __init__(self, parent_frame, workflow_panel):
        """
        Initialize Step 1
        
        Args:
            parent_frame: Parent frame to pack into
            workflow_panel: Reference to main WorkflowPanel for callbacks
        """
        self.parent_frame = parent_frame
        self.workflow = workflow_panel
        self.frame = tk.Frame(parent_frame, bg=COLORS['bg_panel'])
        self.frame.pack(fill=tk.BOTH, expand=True)
        
        self._create_widgets()
    
    def _create_widgets(self):
        """Create Step 1 widgets"""
        tk.Label(
            self.frame,
            text="Step 1: Load Operators & Data Fields",
            font=FONTS['heading'],
            fg=COLORS['accent_cyan'],
            bg=COLORS['bg_panel']
        ).pack(pady=10)
        
        tk.Label(
            self.frame,
            text="First, load operators from operatorRAW.json (download from WorldQuant Brain website).",
            font=FONTS['default'],
            fg=COLORS['text_primary'],
            bg=COLORS['bg_panel']
        ).pack(pady=5)
        
        # Operator file input
        operator_frame = tk.Frame(self.frame, bg=COLORS['bg_secondary'], relief=tk.RAISED, bd=2)
        operator_frame.pack(fill=tk.X, padx=10, pady=10)
        
        tk.Label(
            operator_frame,
            text="⚙️ Operator File (Required):",
            font=FONTS['default'],
            fg=COLORS['accent_yellow'],
            bg=COLORS['bg_secondary']
        ).pack(anchor=tk.W, padx=5, pady=5)
        
        operator_path_frame = tk.Frame(operator_frame, bg=COLORS['bg_secondary'])
        operator_path_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.operator_path_var = tk.StringVar(value="")
        tk.Label(
            operator_path_frame,
            text="operatorRAW.json:",
            font=FONTS['default'],
            fg=COLORS['text_primary'],
            bg=COLORS['bg_secondary']
        ).pack(side=tk.LEFT, padx=5)
        
        operator_entry = tk.Entry(
            operator_path_frame,
            textvariable=self.operator_path_var,
            width=50,
            **STYLES['entry']
        )
        operator_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        tk.Button(
            operator_path_frame,
            text="Browse...",
            command=self._browse_operator_file,
            **STYLES['button']
        ).pack(side=tk.LEFT, padx=5)
        
        self.load_operator_button = tk.Button(
            operator_path_frame,
            text="📂 LOAD OPERATORS",
            command=self._load_operator_file,
            **STYLES['button']
        )
        self.load_operator_button.pack(side=tk.LEFT, padx=5)
        
        self.operator_status = tk.Label(
            operator_frame,
            text="⚠️ Operators not loaded",
            font=FONTS['default'],
            fg=COLORS['error'],
            bg=COLORS['bg_secondary']
        )
        self.operator_status.pack(pady=5)
        
        tk.Label(
            self.frame,
            text="Then, fetch or load data fields for your regions:",
            font=FONTS['default'],
            fg=COLORS['text_primary'],
            bg=COLORS['bg_panel']
        ).pack(pady=5)
        
        # Storage configuration
        storage_frame = tk.Frame(self.frame, bg=COLORS['bg_secondary'], relief=tk.RAISED, bd=2)
        storage_frame.pack(fill=tk.X, padx=10, pady=10)
        
        tk.Label(
            storage_frame,
            text="💾 Storage Configuration:",
            font=FONTS['default'],
            fg=COLORS['accent_yellow'],
            bg=COLORS['bg_secondary']
        ).pack(anchor=tk.W, padx=5, pady=5)
        
        self.storage_type = tk.StringVar(value="json")
        
        storage_options_frame = tk.Frame(storage_frame, bg=COLORS['bg_secondary'])
        storage_options_frame.pack(fill=tk.X, padx=5, pady=5)
        
        for text, value in [
            ("JSON Files (Default - cached per region)", "json"),
            ("Local SQLite Database", "sqlite"),
            ("Remote Database URL", "remote")
        ]:
            tk.Radiobutton(
                storage_options_frame,
                text=text,
                variable=self.storage_type,
                value=value,
                font=FONTS['default'],
                fg=COLORS['text_primary'],
                bg=COLORS['bg_secondary'],
                selectcolor=COLORS['bg_panel'],
                activebackground=COLORS['bg_secondary'],
                activeforeground=COLORS['accent_cyan']
            ).pack(anchor=tk.W, padx=5)
        
        # Database path/URL input
        self.storage_config_frame = tk.Frame(storage_frame, bg=COLORS['bg_secondary'])
        self.storage_config_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.storage_path_var = tk.StringVar(value="")
        self.storage_url_var = tk.StringVar(value="")
        
        self.storage_path_label = tk.Label(
            self.storage_config_frame,
            text="Database Path:",
            font=FONTS['default'],
            fg=COLORS['text_primary'],
            bg=COLORS['bg_secondary']
        )
        
        self.storage_path_entry = tk.Entry(
            self.storage_config_frame,
            textvariable=self.storage_path_var,
            width=40,
            **STYLES['entry']
        )
        
        self.storage_browse_button = tk.Button(
            self.storage_config_frame,
            text="Browse...",
            command=self._browse_storage_path,
            **STYLES['button']
        )
        
        self.storage_url_label = tk.Label(
            self.storage_config_frame,
            text="Database URL:",
            font=FONTS['default'],
            fg=COLORS['text_primary'],
            bg=COLORS['bg_secondary']
        )
        
        self.storage_url_entry = tk.Entry(
            self.storage_config_frame,
            textvariable=self.storage_url_var,
            width=50,
            **STYLES['entry']
        )
        
        self.storage_type.trace('w', lambda *args: self._update_storage_config_visibility())
        self._update_storage_config_visibility()
        
        # Region selection
        region_frame = tk.Frame(self.frame, bg=COLORS['bg_panel'])
        region_frame.pack(fill=tk.X, pady=5)
        
        tk.Label(
            region_frame,
            text="Regions:",
            font=FONTS['default'],
            fg=COLORS['text_primary'],
            bg=COLORS['bg_panel']
        ).pack(side=tk.LEFT, padx=5)
        
        self.region_vars = {}
        regions = ['USA', 'EUR', 'CHN', 'ASI', 'GLB', 'IND']
        for region in regions:
            var = tk.BooleanVar(value=True)
            self.region_vars[region] = var
            tk.Checkbutton(
                region_frame,
                text=region,
                variable=var,
                font=FONTS['default'],
                fg=COLORS['text_primary'],
                bg=COLORS['bg_panel'],
                selectcolor=COLORS['bg_secondary'],
                activebackground=COLORS['bg_panel'],
                activeforeground=COLORS['accent_cyan']
            ).pack(side=tk.LEFT, padx=5)
        
        # Action buttons
        action_frame = tk.Frame(self.frame, bg=COLORS['bg_panel'])
        action_frame.pack(pady=10)
        
        self.load_button = tk.Button(
            action_frame,
            text="📂 LOAD DATA FIELDS",
            command=self._load_data_fields,
            **STYLES['button']
        )
        self.load_button.pack(side=tk.LEFT, padx=5)
        
        self.fetch_button = tk.Button(
            action_frame,
            text="📥 FETCH DATA FIELDS",
            command=self._fetch_data_fields,
            **STYLES['button']
        )
        self.fetch_button.pack(side=tk.LEFT, padx=5)
        
        self.fetch_status = tk.Label(
            self.frame,
            text="",
            font=FONTS['default'],
            fg=COLORS['accent_green'],
            bg=COLORS['bg_panel']
        )
        self.fetch_status.pack(pady=5)
        
        # "Proceed as last time" button
        proceed_frame = tk.Frame(self.frame, bg=COLORS['bg_panel'])
        proceed_frame.pack(pady=10)
        
        self.proceed_last_button = tk.Button(
            proceed_frame,
            text="⚡ PROCEED AS LAST TIME",
            command=self._proceed_as_last_time,
            font=FONTS['default'],
            fg=COLORS['accent_cyan'],
            bg=COLORS['bg_secondary'],
            relief=tk.RAISED,
            bd=2,
            padx=20,
            pady=5
        )
        self.proceed_last_button.pack(pady=5)
        
        # Check if last config exists
        config_file = Path.home() / ".generation_two" / "workflow_config.json"
        if config_file.exists():
            self.proceed_last_button.config(state=tk.NORMAL)
        else:
            self.proceed_last_button.config(state=tk.DISABLED)
    
    def _update_storage_config_visibility(self):
        """Update visibility of storage configuration inputs"""
        for widget in self.storage_config_frame.winfo_children():
            widget.pack_forget()
        
        storage_type = self.storage_type.get()
        
        if storage_type == "sqlite":
            self.storage_path_label.pack(side=tk.LEFT, padx=5)
            self.storage_path_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
            self.storage_browse_button.pack(side=tk.LEFT, padx=5)
            if not self.storage_path_var.get():
                self.storage_path_var.set("generation_two_backtests.db")
        elif storage_type == "remote":
            self.storage_url_label.pack(side=tk.LEFT, padx=5)
            self.storage_url_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
    
    def _browse_operator_file(self):
        """Browse for operatorRAW.json file"""
        filename = filedialog.askopenfilename(
            title="Select operatorRAW.json File",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")]
        )
        if filename:
            self.operator_path_var.set(filename)
    
    def _load_operator_file(self):
        """Load operators from user-specified file"""
        operator_path = self.operator_path_var.get()
        if not operator_path:
            messagebox.showwarning("Warning", "Please select operatorRAW.json file")
            return
        
        if not os.path.exists(operator_path):
            messagebox.showerror("Error", f"File not found: {operator_path}")
            return
        
        try:
            with open(operator_path, 'r', encoding='utf-8') as f:
                operators = json.load(f)
            
            if not operators or not isinstance(operators, list):
                messagebox.showerror("Error", "Invalid operator file format")
                return
            
            # Update operator fetcher
            if self.workflow.generator and self.workflow.generator.template_generator:
                if self.workflow.generator.template_generator.operator_fetcher:
                    self.workflow.generator.template_generator.operator_fetcher.cache_file = Path(operator_path)
                    self.workflow.generator.template_generator.operator_fetcher.operators = operators
                    if self.workflow.generator.template_generator.search_engine:
                        self.workflow.generator.template_generator.search_engine.operators = operators
                        self.workflow.generator.template_generator.search_engine._build_indices()
                    else:
                        from ...data_fetcher import SmartSearchEngine
                        self.workflow.generator.template_generator.search_engine = SmartSearchEngine(
                            operators=operators,
                            data_fields={}
                        )
            
            self.workflow.operators_loaded = True
            self.operator_status.config(
                text=f"✅ Loaded {len(operators)} operators",
                fg=COLORS['accent_green']
            )
            
            self.workflow.operators = operators
            self.workflow.steps_completed.add(1)
            self.workflow._update_step_indicators()
            self.workflow._save_config()
            
            logger.info(f"Loaded {len(operators)} operators from {operator_path}")
            
        except json.JSONDecodeError as e:
            messagebox.showerror("Error", f"Invalid JSON file: {e}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load operators: {e}")
            logger.error(f"Error loading operators: {e}", exc_info=True)
    
    def _browse_storage_path(self):
        """Browse for SQLite database file"""
        filename = filedialog.asksaveasfilename(
            title="Select SQLite Database",
            defaultextension=".db",
            filetypes=[("SQLite Database", "*.db"), ("All Files", "*.*")]
        )
        if filename:
            self.storage_path_var.set(filename)
    
    def _fetch_data_fields(self):
        """Fetch data fields for selected regions"""
        if not self.workflow.generator or not self.workflow.generator.template_generator:
            messagebox.showerror("Error", "Generator not initialized")
            return
        
        selected_regions = [r for r, var in self.region_vars.items() if var.get()]
        if not selected_regions:
            messagebox.showwarning("Warning", "Please select at least one region")
            return
        
        self.fetch_button.config(state=tk.DISABLED)
        self.fetch_status.config(text="Fetching data fields...", fg=COLORS['accent_yellow'])
        
        def fetch_thread():
            try:
                total_fields = 0
                successful_regions = []
                failed_regions = []
                
                for i, region in enumerate(selected_regions, 1):
                    try:
                        self.workflow.frame.after(0, lambda r=region, idx=i, total=len(selected_regions): 
                            self.fetch_status.config(
                                text=f"Fetching {r}... ({idx}/{total})",
                                fg=COLORS['accent_yellow']
                            ))
                        
                        storage_config = {
                            'type': self.storage_type.get(),
                            'path': self.storage_path_var.get() if self.storage_type.get() == 'sqlite' else None,
                            'url': self.storage_url_var.get() if self.storage_type.get() == 'remote' else None
                        }
                        
                        fields = self.workflow.generator.template_generator.get_data_fields_for_region(region)
                        
                        if not fields or len(fields) == 0:
                            try:
                                from ...core.region_config import get_all_universes
                                all_universes = get_all_universes(region)
                                for universe in all_universes:
                                    fields = self.workflow.generator.template_generator.get_data_fields_for_region(
                                        region, delay=1, universe=universe
                                    )
                                    if fields and len(fields) > 0:
                                        break
                            except Exception as e:
                                logger.error(f"[{region}] Error trying all universes: {e}", exc_info=True)
                        
                        if fields and storage_config['type'] != "json":
                            self.workflow._store_fields_to_database(region, fields, storage_config)
                        
                        if fields:
                            total_fields += len(fields)
                            successful_regions.append((region, len(fields)))
                            self.workflow.frame.after(0, lambda r=region, count=len(fields): 
                                self.fetch_status.config(
                                    text=f"✓ Fetched {count} fields for {r}",
                                    fg=COLORS['accent_green']
                                ))
                        else:
                            failed_regions.append((region, "No fields returned"))
                            
                    except Exception as e:
                        failed_regions.append((region, str(e)))
                        self.workflow.frame.after(0, lambda r=region, err=str(e): 
                            self.fetch_status.config(
                                text=f"✗ Error for {r}: {err[:50]}",
                                fg=COLORS['error']
                            ))
                
                if successful_regions:
                    summary = f"Successfully fetched data fields:\n"
                    for region, count in successful_regions:
                        summary += f"  {region}: {count} fields\n"
                    summary += f"\nTotal: {total_fields} fields"
                    
                    if failed_regions:
                        summary += f"\n\nFailed regions:\n"
                        for region, error in failed_regions:
                            summary += f"  {region}: {error}\n"
                    
                    self.workflow.frame.after(0, lambda: self.fetch_status.config(
                        text=f"✓ Complete: {total_fields} fields from {len(successful_regions)} region(s)",
                        fg=COLORS['accent_green']
                    ))
                    self.workflow.frame.after(0, lambda: messagebox.showinfo("Success", summary))
                    self.workflow.frame.after(0, lambda: self.workflow.steps_completed.add(0))
                    self.workflow.frame.after(0, self.workflow._save_config)
                else:
                    error_summary = "Failed to fetch data fields for all regions:\n"
                    for region, error in failed_regions:
                        error_summary += f"  {region}: {error}\n"
                    
                    self.workflow.frame.after(0, lambda: self.fetch_status.config(
                        text="✗ All fetches failed",
                        fg=COLORS['error']
                    ))
                    self.workflow.frame.after(0, lambda: messagebox.showerror("Error", error_summary))
                
            except Exception as e:
                error_msg = f"Unexpected error during fetch: {str(e)}"
                logger.error(error_msg, exc_info=True)
                self.workflow.frame.after(0, lambda: self.fetch_status.config(
                    text=f"✗ Error: {str(e)[:50]}",
                    fg=COLORS['error']
                ))
                self.workflow.frame.after(0, lambda: messagebox.showerror("Error", error_msg))
            finally:
                self.workflow.frame.after(0, lambda: self.fetch_button.config(state=tk.NORMAL))
        
        threading.Thread(target=fetch_thread, daemon=True).start()
    
    def _load_data_fields(self):
        """Load data fields from cache/storage"""
        if not self.workflow.generator or not self.workflow.generator.template_generator:
            messagebox.showerror("Error", "Generator not initialized")
            return
        
        selected_regions = [r for r, var in self.region_vars.items() if var.get()]
        if not selected_regions:
            messagebox.showwarning("Warning", "Please select at least one region")
            return
        
        self.load_button.config(state=tk.DISABLED)
        self.fetch_button.config(state=tk.DISABLED)
        self.fetch_status.config(text="Loading data fields from cache...", fg=COLORS['accent_yellow'])
        
        def load_thread():
            try:
                successful_regions = []
                failed_regions = []
                
                for i, region in enumerate(selected_regions, 1):
                    try:
                        self.workflow.frame.after(0, lambda r=region, idx=i, total=len(selected_regions): 
                            self.fetch_status.config(
                                text=f"Loading {r}... ({idx}/{total})",
                                fg=COLORS['accent_yellow']
                            ))
                        
                        # Check cache or database
                        cache_file = None
                        if self.workflow.generator.template_generator.data_field_fetcher:
                            cache_dir = self.workflow.generator.template_generator.data_field_fetcher.cache_dir
                            import glob
                            for pattern in [f"data_fields_cache_{region}_1.json", f"data_fields_cache_{region}_1_*.json"]:
                                matches = glob.glob(str(cache_dir / pattern))
                                if matches:
                                    cache_file = matches[0]
                                    break
                        
                        if cache_file and os.path.exists(cache_file):
                            try:
                                with open(cache_file, 'r', encoding='utf-8') as f:
                                    sample = f.read(5000)
                                    if sample.strip().startswith('['):
                                        file_size = os.path.getsize(cache_file)
                                        estimated_count = max(1, file_size // 200)
                                        if self.workflow.generator.template_generator.data_field_fetcher:
                                            if region not in self.workflow.generator.template_generator.data_field_fetcher.data_fields:
                                                self.workflow.generator.template_generator.data_field_fetcher.data_fields[region] = []
                                        successful_regions.append(region)
                            except Exception:
                                fields = self.workflow.generator.template_generator.get_data_fields_for_region(region, delay=1)
                                if fields and len(fields) > 0:
                                    successful_regions.append(region)
                                else:
                                    failed_regions.append(region)
                        else:
                            storage_type = self.storage_type.get()
                            if storage_type == "sqlite":
                                db_path = self.storage_path_var.get() or "generation_two_backtests.db"
                                if os.path.exists(db_path):
                                    try:
                                        import sqlite3
                                        conn = sqlite3.connect(db_path)
                                        cursor = conn.cursor()
                                        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='data_fields' LIMIT 1")
                                        if cursor.fetchone():
                                            cursor.execute("SELECT COUNT(*) FROM data_fields WHERE region=? LIMIT 1", (region,))
                                            count = cursor.fetchone()[0]
                                            if count > 0:
                                                if self.workflow.generator.template_generator.data_field_fetcher:
                                                    if region not in self.workflow.generator.template_generator.data_field_fetcher.data_fields:
                                                        self.workflow.generator.template_generator.data_field_fetcher.data_fields[region] = []
                                                successful_regions.append(region)
                                        conn.close()
                                    except Exception:
                                        failed_regions.append(region)
                                else:
                                    failed_regions.append(region)
                            else:
                                fields = self.workflow.generator.template_generator.get_data_fields_for_region(region, delay=1)
                                if fields and len(fields) > 0:
                                    successful_regions.append(region)
                                else:
                                    failed_regions.append(region)
                            
                    except Exception as e:
                        logger.error(f"Error loading fields for {region}: {e}", exc_info=True)
                        failed_regions.append(region)
                
                if successful_regions:
                    status_msg = f"✅ Loaded fields for: {', '.join(successful_regions)}"
                    if failed_regions:
                        status_msg += f"\n⚠️ Not found: {', '.join(failed_regions)}"
                    self.workflow.frame.after(0, lambda msg=status_msg: self.fetch_status.config(
                        text=msg,
                        fg=COLORS['accent_green'] if not failed_regions else COLORS['accent_yellow']
                    ))
                    if successful_regions:
                        self.workflow.steps_completed.add(0)
                        self.workflow.frame.after(0, self.workflow._update_step_indicators)
                else:
                    error_msg = f"❌ No cached fields found for any region.\nPlease use 'Fetch Data Fields' first."
                    self.workflow.frame.after(0, lambda msg=error_msg: self.fetch_status.config(
                        text=msg,
                        fg=COLORS['error']
                    ))
                
            except Exception as e:
                error_msg = f"Error loading data fields: {str(e)[:100]}"
                logger.error(error_msg, exc_info=True)
                self.workflow.frame.after(0, lambda msg=error_msg: self.fetch_status.config(
                    text=msg,
                    fg=COLORS['error']
                ))
                self.workflow.frame.after(0, lambda: messagebox.showerror("Error", error_msg))
            finally:
                self.workflow.frame.after(0, lambda: self.load_button.config(state=tk.NORMAL))
                self.workflow.frame.after(0, lambda: self.fetch_button.config(state=tk.NORMAL))
        
        threading.Thread(target=load_thread, daemon=True).start()
    
    def _proceed_as_last_time(self):
        """Load last configuration and proceed automatically"""
        config_file = Path.home() / ".generation_two" / "workflow_config.json"
        if not config_file.exists():
            messagebox.showwarning("Warning", "No previous configuration found")
            return
        
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            if 'operator_path' in config and config['operator_path']:
                self.operator_path_var.set(config['operator_path'])
                if os.path.exists(config['operator_path']):
                    self._load_operator_file()
            
            if 'storage_type' in config:
                self.storage_type.set(config['storage_type'])
            if 'storage_path' in config:
                self.storage_path_var.set(config['storage_path'])
            if 'storage_url' in config:
                self.storage_url_var.set(config['storage_url'])
            
            if 'regions' in config:
                for region, selected in config['regions'].items():
                    if region in self.region_vars:
                        self.region_vars[region].set(selected)
            
            self._update_storage_config_visibility()
            
            if self.workflow.operators_loaded:
                self._load_data_fields()
            
            messagebox.showinfo("Success", "Last configuration loaded! You can proceed to next steps.")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load last configuration: {e}")
            logger.error(f"Error in proceed as last time: {e}", exc_info=True)
