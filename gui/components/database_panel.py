"""
Database Panel
Configure database connections and visualize data
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
from typing import Optional, Dict, Callable
import json
import sqlite3
import os
import logging
from pathlib import Path

from ..theme import COLORS, FONTS, STYLES

logger = logging.getLogger(__name__)


class DatabasePanel:
    """Panel for database configuration and visualization"""
    
    def __init__(self, parent, db_config_callback: Optional[Callable] = None):
        """
        Initialize database panel
        
        Args:
            parent: Parent widget
            db_config_callback: Callback when database config changes
        """
        self.parent = parent
        self.db_config_callback = db_config_callback
        
        self.frame = tk.Frame(parent, **STYLES['frame'])
        self.frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.current_db_type = tk.StringVar(value="local_sqlite")
        self.current_db_path = tk.StringVar(value="")
        self.current_db_url = tk.StringVar(value="")
        
        self._create_widgets()
        self._load_config()
    
    def _create_widgets(self):
        """Create database configuration widgets"""
        # Title
        title = tk.Label(
            self.frame,
            text="💾 DATABASE CONFIGURATION 💾",
            font=FONTS['heading'],
            fg=COLORS['accent_cyan'],
            bg=COLORS['bg_panel']
        )
        title.pack(pady=10)
        
        # Database type selection
        type_frame = tk.Frame(self.frame, bg=COLORS['bg_panel'])
        type_frame.pack(fill=tk.X, padx=10, pady=5)
        
        tk.Label(
            type_frame,
            text="Database Type:",
            font=FONTS['default'],
            fg=COLORS['text_primary'],
            bg=COLORS['bg_panel']
        ).pack(side=tk.LEFT, padx=5)
        
        db_types = [
            ("Local SQLite", "local_sqlite"),
            ("Local JSON", "local_json"),
            ("Remote URL", "remote_url")
        ]
        
        for text, value in db_types:
            rb = tk.Radiobutton(
                type_frame,
                text=text,
                variable=self.current_db_type,
                value=value,
                command=self._on_db_type_change,
                font=FONTS['default'],
                fg=COLORS['text_primary'],
                bg=COLORS['bg_panel'],
                selectcolor=COLORS['bg_secondary'],
                activebackground=COLORS['bg_panel'],
                activeforeground=COLORS['accent_cyan']
            )
            rb.pack(side=tk.LEFT, padx=10)
        
        # Configuration frame
        self.config_frame = tk.Frame(self.frame, bg=COLORS['bg_panel'])
        self.config_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self._create_config_widgets()
        
        # Buttons
        button_frame = tk.Frame(self.frame, bg=COLORS['bg_panel'])
        button_frame.pack(fill=tk.X, padx=10, pady=5)
        
        tk.Button(
            button_frame,
            text="💾 SAVE CONFIG",
            command=self._save_config,
            **STYLES['button']
        ).pack(side=tk.LEFT, padx=5)
        
        tk.Button(
            button_frame,
            text="🔄 TEST CONNECTION",
            command=self._test_connection,
            **STYLES['button']
        ).pack(side=tk.LEFT, padx=5)
        
        tk.Button(
            button_frame,
            text="📊 VIEW DATA",
            command=self._show_visualization,
            **STYLES['button']
        ).pack(side=tk.LEFT, padx=5)
        
        # Status
        self.status_label = tk.Label(
            self.frame,
            text="",
            font=FONTS['default'],
            fg=COLORS['accent_green'],
            bg=COLORS['bg_panel']
        )
        self.status_label.pack(pady=5)
    
    def _create_config_widgets(self):
        """Create configuration widgets based on database type"""
        # Clear existing widgets
        for widget in self.config_frame.winfo_children():
            widget.destroy()
        
        db_type = self.current_db_type.get()
        
        if db_type == "local_sqlite":
            # SQLite path
            path_frame = tk.Frame(self.config_frame, bg=COLORS['bg_panel'])
            path_frame.pack(fill=tk.X, pady=5)
            
            tk.Label(
                path_frame,
                text="Database Path:",
                font=FONTS['default'],
                fg=COLORS['text_primary'],
                bg=COLORS['bg_panel']
            ).pack(side=tk.LEFT, padx=5)
            
            path_entry = tk.Entry(
                path_frame,
                textvariable=self.current_db_path,
                width=40,
                **STYLES['entry']
            )
            path_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
            
            tk.Button(
                path_frame,
                text="Browse...",
                command=self._browse_sqlite_file,
                **STYLES['button']
            ).pack(side=tk.LEFT, padx=5)
        
        elif db_type == "local_json":
            # JSON path
            path_frame = tk.Frame(self.config_frame, bg=COLORS['bg_panel'])
            path_frame.pack(fill=tk.X, pady=5)
            
            tk.Label(
                path_frame,
                text="JSON File Path:",
                font=FONTS['default'],
                fg=COLORS['text_primary'],
                bg=COLORS['bg_panel']
            ).pack(side=tk.LEFT, padx=5)
            
            path_entry = tk.Entry(
                path_frame,
                textvariable=self.current_db_path,
                width=40,
                **STYLES['entry']
            )
            path_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
            
            tk.Button(
                path_frame,
                text="Browse...",
                command=self._browse_json_file,
                **STYLES['button']
            ).pack(side=tk.LEFT, padx=5)
        
        elif db_type == "remote_url":
            # URL
            url_frame = tk.Frame(self.config_frame, bg=COLORS['bg_panel'])
            url_frame.pack(fill=tk.X, pady=5)
            
            tk.Label(
                url_frame,
                text="Database URL:",
                font=FONTS['default'],
                fg=COLORS['text_primary'],
                bg=COLORS['bg_panel']
            ).pack(side=tk.LEFT, padx=5)
            
            url_entry = tk.Entry(
                url_frame,
                textvariable=self.current_db_url,
                width=50,
                **STYLES['entry']
            )
            url_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
    
    def _on_db_type_change(self):
        """Handle database type change"""
        self._create_config_widgets()
    
    def _browse_sqlite_file(self):
        """Browse for SQLite database file"""
        filename = filedialog.askopenfilename(
            title="Select SQLite Database",
            filetypes=[("SQLite Database", "*.db"), ("All Files", "*.*")]
        )
        if filename:
            self.current_db_path.set(filename)
    
    def _browse_json_file(self):
        """Browse for JSON file"""
        filename = filedialog.askopenfilename(
            title="Select JSON File",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")]
        )
        if filename:
            self.current_db_path.set(filename)
    
    def _save_config(self):
        """Save database configuration"""
        config = {
            'type': self.current_db_type.get(),
            'path': self.current_db_path.get(),
            'url': self.current_db_url.get()
        }
        
        # Save to file
        config_file = Path.home() / ".generation_two" / "db_config.json"
        config_file.parent.mkdir(exist_ok=True)
        
        try:
            with open(config_file, 'w') as f:
                json.dump(config, f, indent=2)
            
            if self.db_config_callback:
                self.db_config_callback(config)
            
            self.status_label.config(text="✓ Configuration saved", fg=COLORS['accent_green'])
        except Exception as e:
            self.status_label.config(text=f"Error: {e}", fg=COLORS['error'])
    
    def _load_config(self):
        """Load database configuration"""
        config_file = Path.home() / ".generation_two" / "db_config.json"
        
        if config_file.exists():
            try:
                with open(config_file, 'r') as f:
                    config = json.load(f)
                
                self.current_db_type.set(config.get('type', 'local_sqlite'))
                self.current_db_path.set(config.get('path', ''))
                self.current_db_url.set(config.get('url', ''))
                
                self._create_config_widgets()
            except Exception as e:
                logger.warning(f"Error loading config: {e}")
    
    def _test_connection(self):
        """Test database connection"""
        db_type = self.current_db_type.get()
        
        try:
            if db_type == "local_sqlite":
                path = self.current_db_path.get()
                if not path:
                    self.status_label.config(text="Please specify database path", fg=COLORS['error'])
                    return
                
                if not os.path.exists(path):
                    self.status_label.config(text="Database file not found", fg=COLORS['error'])
                    return
                
                conn = sqlite3.connect(path)
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = cursor.fetchall()
                conn.close()
                
                self.status_label.config(
                    text=f"✓ Connected! Found {len(tables)} tables",
                    fg=COLORS['accent_green']
                )
            
            elif db_type == "local_json":
                path = self.current_db_path.get()
                if not path:
                    self.status_label.config(text="Please specify JSON file path", fg=COLORS['error'])
                    return
                
                if not os.path.exists(path):
                    self.status_label.config(text="JSON file not found", fg=COLORS['error'])
                    return
                
                with open(path, 'r') as f:
                    data = json.load(f)
                
                self.status_label.config(
                    text=f"✓ Loaded! Found {len(data)} entries",
                    fg=COLORS['accent_green']
                )
            
            elif db_type == "remote_url":
                url = self.current_db_url.get()
                if not url:
                    self.status_label.config(text="Please specify database URL", fg=COLORS['error'])
                    return
                
                # Test URL connection (simplified)
                import requests
                try:
                    response = requests.get(url, timeout=5)
                    self.status_label.config(
                        text=f"✓ URL accessible (Status: {response.status_code})",
                        fg=COLORS['accent_green']
                    )
                except Exception as e:
                    self.status_label.config(text=f"Connection error: {e}", fg=COLORS['error'])
        
        except Exception as e:
            self.status_label.config(text=f"Error: {e}", fg=COLORS['error'])
    
    def _show_visualization(self):
        """Show database visualization window"""
        db_type = self.current_db_type.get()
        
        if db_type == "local_sqlite":
            path = self.current_db_path.get()
            if not path or not os.path.exists(path):
                messagebox.showerror("Error", "Please specify a valid database path")
                return
            
            self._show_sqlite_visualization(path)
        
        elif db_type == "local_json":
            path = self.current_db_path.get()
            if not path or not os.path.exists(path):
                messagebox.showerror("Error", "Please specify a valid JSON file path")
                return
            
            self._show_json_visualization(path)
        
        elif db_type == "remote_url":
            messagebox.showinfo("Info", "Remote URL visualization not yet implemented")
    
    def _show_sqlite_visualization(self, db_path: str):
        """Show SQLite database visualization"""
        viz_window = tk.Toplevel(self.frame)
        viz_window.title("Database Visualization")
        viz_window.geometry("1000x700")
        viz_window.configure(bg=COLORS['bg_primary'])
        
        # Open connection and keep it open while window is open
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get table list
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        
        # Table selector
        selector_frame = tk.Frame(viz_window, bg=COLORS['bg_panel'])
        selector_frame.pack(fill=tk.X, padx=10, pady=10)
        
        tk.Label(
            selector_frame,
            text="Table:",
            font=FONTS['default'],
            fg=COLORS['text_primary'],
            bg=COLORS['bg_panel']
        ).pack(side=tk.LEFT, padx=5)
        
        table_var = tk.StringVar(value=tables[0] if tables else "")
        table_combo = ttk.Combobox(selector_frame, textvariable=table_var, values=tables, state="readonly")
        table_combo.pack(side=tk.LEFT, padx=5)
        
        # Data display
        data_frame = tk.Frame(viz_window, bg=COLORS['bg_panel'])
        data_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Treeview for data
        tree = ttk.Treeview(data_frame)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(data_frame, orient=tk.VERTICAL, command=tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        tree.configure(yscrollcommand=scrollbar.set)
        
        def load_table_data():
            """Load data from selected table"""
            # Clear existing data
            for item in tree.get_children():
                tree.delete(item)
            
            table_name = table_var.get()
            if not table_name:
                return
            
            try:
                # First, get column names to check if we have JSON data
                cursor.execute(f"PRAGMA table_info({table_name})")
                table_info = cursor.fetchall()
                column_names = [col[1] for col in table_info]
                
                # Check if this is a data_fields table with JSON field_data
                has_json_data = 'field_data' in column_names or 'data' in column_names
                
                if has_json_data:
                    # Parse JSON and extract all fields as columns
                    json_column = 'field_data' if 'field_data' in column_names else 'data'
                    cursor.execute(f"SELECT * FROM {table_name} LIMIT 100")
                    rows = cursor.fetchall()
                    
                    if rows:
                        # Parse first row to get all possible fields
                        first_row_dict = dict(zip(column_names, rows[0]))
                        json_data = first_row_dict.get(json_column)
                        
                        if json_data:
                            try:
                                if isinstance(json_data, str):
                                    field_obj = json.loads(json_data)
                                else:
                                    field_obj = json_data
                                
                                # Flatten nested objects
                                def flatten_field(field):
                                    """Flatten a data field object into a dictionary"""
                                    flat = {}
                                    for key, value in field.items():
                                        if key == 'dataset' and isinstance(value, dict):
                                            flat['dataset_id'] = value.get('id', '')
                                            flat['dataset_name'] = value.get('name', '')
                                        elif key == 'category' and isinstance(value, dict):
                                            flat['category_id'] = value.get('id', '')
                                            flat['category_name'] = value.get('name', '')
                                        elif key == 'subcategory' and isinstance(value, dict):
                                            flat['subcategory_id'] = value.get('id', '')
                                            flat['subcategory_name'] = value.get('name', '')
                                        elif key == 'themes' and isinstance(value, list):
                                            flat['themes'] = ', '.join(value) if value else ''
                                        else:
                                            flat[key] = value
                                    return flat
                                
                                # Get all possible columns from all rows
                                all_columns = set()
                                flattened_rows = []
                                
                                for row in rows:
                                    row_dict = dict(zip(column_names, row))
                                    json_data = row_dict.get(json_column)
                                    if json_data:
                                        try:
                                            if isinstance(json_data, str):
                                                field_obj = json.loads(json_data)
                                            else:
                                                field_obj = json_data
                                            
                                            flat_field = flatten_field(field_obj)
                                            all_columns.update(flat_field.keys())
                                            flattened_rows.append((row, flat_field))
                                        except:
                                            pass
                                
                                # Define column order (important fields first)
                                column_order = [
                                    'id', 'description', 'region', 'universe', 'delay', 'type',
                                    'dataset_name', 'category_name', 'subcategory_name',
                                    'coverage', 'userCount', 'alphaCount', 'pyramidMultiplier',
                                    'themes', 'dataset_id', 'category_id', 'subcategory_id'
                                ]
                                
                                # Add any remaining columns
                                for col in sorted(all_columns):
                                    if col not in column_order:
                                        column_order.append(col)
                                
                                # Filter to only columns that exist
                                columns = [col for col in column_order if col in all_columns]
                                
                                # Configure treeview
                                tree['columns'] = columns
                                tree['show'] = 'headings'
                                
                                # Clear existing columns first
                                for col in tree['columns']:
                                    tree.heading(col, text="")
                                    tree.column(col, width=0)
                                
                                # Set column widths based on content
                                column_widths = {
                                    'id': 200, 'description': 300, 'region': 60, 'universe': 100,
                                    'delay': 60, 'type': 80, 'dataset_name': 150, 'category_name': 100,
                                    'subcategory_name': 150, 'coverage': 80, 'userCount': 80,
                                    'alphaCount': 80, 'pyramidMultiplier': 100, 'themes': 150
                                }
                                
                                for col in columns:
                                    tree.heading(col, text=col.replace('_', ' ').title())
                                    tree.column(col, width=column_widths.get(col, 120))
                                
                                # Insert rows
                                for row, flat_field in flattened_rows:
                                    values = [str(flat_field.get(col, '')) for col in columns]
                                    tree.insert('', tk.END, values=values)
                                
                            except Exception as e:
                                logger.error(f"Error parsing JSON data: {e}", exc_info=True)
                                # Fall back to regular display
                                has_json_data = False
                
                if not has_json_data:
                    # Regular table display
                    cursor.execute(f"SELECT * FROM {table_name} LIMIT 100")
                    columns = [description[0] for description in cursor.description]
                    
                    # Configure columns
                    tree['columns'] = columns
                    tree['show'] = 'headings'
                    
                    # Clear existing columns first
                    for col in tree['columns']:
                        tree.heading(col, text="")
                        tree.column(col, width=0)
                    
                    for col in columns:
                        tree.heading(col, text=col)
                        tree.column(col, width=120)
                    
                    # Load data
                    rows = cursor.fetchall()
                    for row in rows:
                        tree.insert('', tk.END, values=row)
            
            except sqlite3.OperationalError as e:
                if "closed database" in str(e).lower():
                    messagebox.showerror("Error", "Database connection was closed. Please reopen the visualization.")
                else:
                    messagebox.showerror("Error", f"Error loading table: {e}")
            except Exception as e:
                messagebox.showerror("Error", f"Error loading table: {e}")
                logger.error(f"Error loading table data: {e}", exc_info=True)
        
        def on_window_close():
            """Close database connection when window is closed"""
            try:
                cursor.close()
                conn.close()
            except:
                pass
            viz_window.destroy()
        
        # Bind window close event
        viz_window.protocol("WM_DELETE_WINDOW", on_window_close)
        
        # Bind table selection change
        table_combo.bind('<<ComboboxSelected>>', lambda e: load_table_data())
        
        # Load initial table data
        if tables:
            load_table_data()
    
    def _show_json_visualization(self, json_path: str):
        """Show JSON file visualization"""
        viz_window = tk.Toplevel(self.frame)
        viz_window.title("JSON Visualization")
        viz_window.geometry("1000x700")
        viz_window.configure(bg=COLORS['bg_primary'])
        
        # Load JSON
        try:
            with open(json_path, 'r') as f:
                data = json.load(f)
        except Exception as e:
            messagebox.showerror("Error", f"Error loading JSON: {e}")
            return
        
        # Display as formatted JSON
        text_widget = scrolledtext.ScrolledText(
            viz_window,
            bg=COLORS['bg_secondary'],
            fg=COLORS['accent_cyan'],
            font=FONTS['mono'],
            wrap=tk.WORD
        )
        text_widget.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        text_widget.insert('1.0', json.dumps(data, indent=2))
        text_widget.config(state=tk.DISABLED)
