"""
Workflow Panel
Guided workflow for seamless user experience
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
from typing import Optional, Callable, List, Dict
import logging
import json
import time
import threading
import os
from pathlib import Path

from ..theme import COLORS, FONTS, STYLES

logger = logging.getLogger(__name__)


class WorkflowPanel:
    """Guided workflow panel for seamless UX"""
    
    def __init__(self, parent, generator=None):
        """
        Initialize workflow panel
        
        Args:
            parent: Parent widget
            generator: EnhancedTemplateGeneratorV3 instance
        """
        self.parent = parent
        self.generator = generator
        
        self.frame = tk.Frame(parent, **STYLES['frame'])
        self.frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.current_step = 0
        self.steps_completed = set()
        self.operators_loaded = False  # Track if operators are loaded
        
        # Configuration file for saving/loading last settings
        self.config_file = Path.home() / ".generation_two" / "workflow_config.json"
        self.config_file.parent.mkdir(exist_ok=True)
        
        self._create_widgets()
        self._check_initial_state()
        # Load config asynchronously to avoid blocking GUI startup
        self._load_last_config_async()
    
    def _create_widgets(self):
        """Create workflow widgets"""
        # Title
        title = tk.Label(
            self.frame,
            text="🚀 GENERATION TWO WORKFLOW 🚀",
            font=FONTS['title'],
            fg=COLORS['accent_cyan'],
            bg=COLORS['bg_panel']
        )
        title.pack(pady=10)
        
        # Progress indicator
        self.progress_frame = tk.Frame(self.frame, bg=COLORS['bg_panel'])
        self.progress_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.progress_label = tk.Label(
            self.progress_frame,
            text="Step 1 of 6: Initialize",
            font=FONTS['heading'],
            fg=COLORS['accent_green'],
            bg=COLORS['bg_panel']
        )
        self.progress_label.pack()
        
        # Navigation buttons (create first so _show_step can access them)
        nav_frame = tk.Frame(self.frame, bg=COLORS['bg_panel'])
        nav_frame.pack(fill=tk.X, padx=10, pady=10)
        
        self.prev_button = tk.Button(
            nav_frame,
            text="◀ PREVIOUS",
            command=self._previous_step,
            **STYLES['button'],
            state=tk.DISABLED
        )
        self.prev_button.pack(side=tk.LEFT, padx=5)
        
        self.next_button = tk.Button(
            nav_frame,
            text="NEXT ▶",
            command=self._next_step,
            **STYLES['button']
        )
        self.next_button.pack(side=tk.LEFT, padx=5)
        
        self.complete_button = tk.Button(
            nav_frame,
            text="✅ COMPLETE",
            command=self._complete_workflow,
            **STYLES['button'],
            state=tk.DISABLED
        )
        self.complete_button.pack(side=tk.LEFT, padx=5)
        
        # Main content area
        self.content_frame = tk.Frame(self.frame, bg=COLORS['bg_panel'])
        self.content_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Step content will be dynamically created
        self.step_widgets = {}
        self._create_step_widgets()
    
    def _create_step_widgets(self):
        """Create widgets for each workflow step"""
        # Import step modules
        from .workflow_steps.step1_data_fields import Step1DataFields
        
        # Step 1: Data Fields Setup (modularized)
        step1 = Step1DataFields(self.content_frame, self)
        self.step_widgets[0] = step1.frame
        
        # Store step1 reference for access to its widgets
        self.step1 = step1
        
        # Step 2: Operator Visualization (modularized)
        from .workflow_steps.step2_operators import Step2Operators
        step2 = Step2Operators(self.content_frame, self)
        self.step_widgets[1] = step2.frame
        self.step2 = step2
        
        # Step 3: Configuration (modularized)
        from .workflow_steps.step3_config import Step3Config
        step3 = Step3Config(self.content_frame, self)
        self.step_widgets[2] = step3.frame
        self.step3 = step3
        
        # Step 4: Alpha Ideation & Generation (modularized)
        from .workflow_steps.step4_generation import Step4Generation
        step4 = Step4Generation(self.content_frame, self)
        self.step_widgets[3] = step4.frame
        self.step4 = step4
        
        # Step 5: Simulation & Testing (modularized)
        from .workflow_steps.step5_simulation import Step5Simulation
        step5 = Step5Simulation(self.content_frame, self)
        self.step_widgets[4] = step5.frame
        self.step5 = step5
        
        # Debug: Verify step5 frame was created
        logger.debug(f"Step 5 frame created: {step5.frame}, widgets: {len(step5.frame.winfo_children())} children")
        
        # Step 6: Continuous Mining (modularized)
        from .workflow_steps.step6_mining import Step6Mining
        step6 = Step6Mining(self.content_frame, self)
        self.step_widgets[5] = step6.frame
        self.step6 = step6
        
        # Mining state
        self.mining_active = False
        self.mining_thread = None
        self.stop_mining_flag = False
    
    # Wrapper methods for Step 1 (delegate to modular step1 if available)
    def _update_storage_config_visibility(self):
        """Update visibility of storage configuration inputs"""
        if hasattr(self, 'step1'):
            self.step1._update_storage_config_visibility()
    
    def _browse_operator_file(self):
        """Browse for operatorRAW.json file"""
        if hasattr(self, 'step1'):
            self.step1._browse_operator_file()
    
    def _load_operator_file(self):
        """Load operators from user-specified file"""
        if hasattr(self, 'step1'):
            self.step1._load_operator_file()
    
    def _browse_storage_path(self):
        """Browse for SQLite database file"""
        if hasattr(self, 'step1'):
            self.step1._browse_storage_path()
    
    def _check_initial_state(self):
        """Check what's already done"""
        # Check if operators are loaded
        if self.generator and self.generator.template_generator:
            if self.generator.template_generator.operator_fetcher:
                operators = self.generator.template_generator.operator_fetcher.operators
                if operators:
                    self.steps_completed.add(1)  # Operators loaded
                    # Store operators for later use (widgets not ready yet)
                    # Will be loaded into UI after widgets are created in _create_step_widgets()
                    self.operators = operators
    
    def _show_step(self, step: int):
        """Show a specific workflow step"""
        # Hide all steps
        for widget in self.step_widgets.values():
            widget.pack_forget()
        
        # Show current step
        if step in self.step_widgets:
            self.step_widgets[step].pack(fill=tk.BOTH, expand=True)
        
        self.current_step = step
        
        # Update progress
        step_names = [
            "Initialize & Fetch Data",
            "View Operators",
            "Configure System",
            "Generate Alphas",
            "Simulate & Test",
            "Continuous Mining"
        ]
        self.progress_label.config(text=f"Step {step + 1} of 6: {step_names[step]}")
        
        # Update navigation buttons
        self.prev_button.config(state=tk.DISABLED if step == 0 else tk.NORMAL)
        self.next_button.config(state=tk.DISABLED if step == 5 else tk.NORMAL)
        self.complete_button.config(state=tk.NORMAL if len(self.steps_completed) >= 5 else tk.DISABLED)
        
        # Step-specific updates
        if step == 1:  # Step 2: View Operators
            # Schedule operator update after widgets are fully displayed
            # This ensures category_var and operator_listbox are ready
            self.frame.after(50, self._update_step2_operators)
    
    def _update_step2_operators(self):
        """Update operators for Step 2 (called after widgets are ready)"""
        logger.debug("=== _update_step2_operators called ===")
        
        # Try to load operators if not already loaded
        if not hasattr(self, 'operators') or not self.operators:
            logger.debug("Operators not in self.operators, checking generator...")
            # Try to get operators from generator
            if self.generator and self.generator.template_generator:
                logger.debug("Generator and template_generator exist")
                if self.generator.template_generator.operator_fetcher:
                    logger.debug("operator_fetcher exists")
                    operators = self.generator.template_generator.operator_fetcher.operators
                    logger.debug(f"operator_fetcher.operators: {len(operators) if operators else 0} operators")
                    if operators:
                        self.operators = operators
                        logger.info(f"✅ Loaded {len(operators)} operators from generator for Step 2")
                    else:
                        logger.warning("⚠️ operator_fetcher.operators is empty")
                else:
                    logger.warning("⚠️ operator_fetcher does not exist")
            else:
                logger.warning("⚠️ Generator or template_generator does not exist")
        else:
            logger.debug(f"Operators already loaded: {len(self.operators)} operators")
        
        # Update operator list if operators are available
        if hasattr(self, 'operators') and self.operators:
            logger.debug(f"Updating operator list with {len(self.operators)} operators")
            self._update_operator_list()
        else:
            logger.warning("⚠️ No operators available for Step 2")
            # Show message if no operators
            if hasattr(self, 'operator_listbox'):
                self.operator_listbox.delete(0, tk.END)
                self.operator_listbox.insert(0, "⚠️ No operators loaded. Please load operators in Step 1.")
            if hasattr(self, 'operator_details'):
                self.operator_details.delete('1.0', tk.END)
                self.operator_details.insert('1.0', "Please go back to Step 1 and load operators from operatorRAW.json file.")
        
        logger.debug("=== _update_step2_operators complete ===")
    
    def _update_step_indicators(self):
        """Update step progress indicators based on completed steps"""
        try:
            # Update progress label
            step_names = {
                0: "Load Data Fields",
                1: "Load Operators",
                2: "View Operators",
                3: "Configure System",
                4: "Generate Alphas"
            }
            
            completed_count = len(self.steps_completed)
            current_step = self.current_step + 1
            
            # Determine current step name
            if completed_count == 0:
                step_name = "Initialize"
            elif self.current_step < len(step_names):
                step_name = step_names.get(self.current_step, f"Step {current_step}")
            else:
                step_name = f"Step {current_step}"
            
            # Update progress label
            if hasattr(self, 'progress_label'):
                self.progress_label.config(
                    text=f"Step {current_step} of 6: {step_name} ({completed_count} completed)"
                )
            
            # Update navigation buttons
            if hasattr(self, 'next_button'):
                self.next_button.config(state=tk.DISABLED if self.current_step == 5 else tk.NORMAL)
            
            if hasattr(self, 'prev_button'):
                self.prev_button.config(state=tk.DISABLED if self.current_step == 0 else tk.NORMAL)
            
            if hasattr(self, 'complete_button'):
                self.complete_button.config(state=tk.NORMAL if completed_count >= 4 else tk.DISABLED)
            
        except Exception as e:
            logger.error(f"Error updating step indicators: {e}", exc_info=True)
    
    def _previous_step(self):
        """Go to previous step"""
        if self.current_step > 0:
            self._show_step(self.current_step - 1)
    
    def _next_step(self):
        """Go to next step"""
        if self.current_step < 5:
            self._show_step(self.current_step + 1)
    
    def _fetch_data_fields(self):
        """Fetch data fields for selected regions"""
        logger.info("=== Starting data field fetch ===")
        
        if not self.generator:
            error_msg = "Generator not initialized"
            logger.error(error_msg)
            messagebox.showerror("Error", error_msg)
            return
        
        if not self.generator.template_generator:
            error_msg = "Template generator not initialized"
            logger.error(error_msg)
            messagebox.showerror("Error", error_msg)
            return
        
        # Delegate to Step 1 module
        if hasattr(self, 'step1'):
            self.step1._fetch_data_fields()
            return
        
        # Fallback (should not be reached if step1 exists)
        messagebox.showerror("Error", "Step 1 not initialized")
    
    def _load_data_fields(self):
        """Load data fields from cache/storage instead of fetching"""
        # Delegate to Step 1 module
        if hasattr(self, 'step1'):
            self.step1._load_data_fields()
            return
        
        # Fallback (should not be reached if step1 exists)
        messagebox.showerror("Error", "Step 1 not initialized")
    
    def _save_config(self):
        """Save current configuration for 'Proceed as last time'"""
        try:
            # Access Step 1 widgets through step1 reference if available
            if hasattr(self, 'step1'):
                operator_path = self.step1.operator_path_var.get()
                storage_type = self.step1.storage_type.get()
                storage_path = self.step1.storage_path_var.get()
                storage_url = self.step1.storage_url_var.get()
                regions = {region: var.get() for region, var in self.step1.region_vars.items()}
            else:
                # Fallback to old direct access (for backward compatibility during migration)
                operator_path = getattr(self, 'operator_path_var', tk.StringVar()).get() if hasattr(self, 'operator_path_var') else ""
                storage_type = getattr(self, 'storage_type', tk.StringVar(value='json')).get() if hasattr(self, 'storage_type') else "json"
                storage_path = getattr(self, 'storage_path_var', tk.StringVar()).get() if hasattr(self, 'storage_path_var') else ""
                storage_url = getattr(self, 'storage_url_var', tk.StringVar()).get() if hasattr(self, 'storage_url_var') else ""
                regions = {region: var.get() for region, var in getattr(self, 'region_vars', {}).items()}
            
            config = {
                'operator_path': operator_path,
                'storage_type': storage_type,
                'storage_path': storage_path,
                'storage_url': storage_url,
                'regions': regions,
                'operators_loaded': self.operators_loaded
            }
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2)
            
            logger.info(f"Configuration saved to {self.config_file}")
            
        except Exception as e:
            logger.error(f"Error saving configuration: {e}", exc_info=True)
    
    def _load_last_config_async(self):
        """Load last configuration asynchronously to avoid blocking GUI startup"""
        def load_config():
            if not self.config_file.exists():
                return
            
            try:
                # Quick file read (minimal I/O)
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                # Schedule GUI updates on main thread (non-blocking)
                def update_gui():
                    try:
                        # Access Step 1 widgets through step1 reference if available
                        if hasattr(self, 'step1'):
                            if 'operator_path' in config and config['operator_path']:
                                self.step1.operator_path_var.set(config['operator_path'])
                            if 'storage_type' in config:
                                self.step1.storage_type.set(config['storage_type'])
                            if 'storage_path' in config:
                                self.step1.storage_path_var.set(config['storage_path'])
                            if 'storage_url' in config:
                                self.step1.storage_url_var.set(config['storage_url'])
                            if 'regions' in config:
                                for region, selected in config['regions'].items():
                                    if region in self.step1.region_vars:
                                        self.step1.region_vars[region].set(selected)
                            self.step1._update_storage_config_visibility()
                        else:
                            # Fallback to old direct access
                            if 'operator_path' in config and config['operator_path']:
                                if hasattr(self, 'operator_path_var'):
                                    self.operator_path_var.set(config['operator_path'])
                            if 'storage_type' in config and hasattr(self, 'storage_type'):
                                self.storage_type.set(config['storage_type'])
                            if 'storage_path' in config and hasattr(self, 'storage_path_var'):
                                self.storage_path_var.set(config['storage_path'])
                            if 'storage_url' in config and hasattr(self, 'storage_url_var'):
                                self.storage_url_var.set(config['storage_url'])
                            if 'regions' in config and hasattr(self, 'region_vars'):
                                for region, selected in config['regions'].items():
                                    if region in self.region_vars:
                                        self.region_vars[region].set(selected)
                                        if hasattr(self, '_update_storage_config_visibility'):
                                            self._update_storage_config_visibility()
                        
                        # Update storage visibility
                        self._update_storage_config_visibility()
                        
                        # Enable proceed button (access through step1 if available)
                        if 'operators_loaded' in config and config['operators_loaded']:
                            if hasattr(self, 'step1') and hasattr(self.step1, 'proceed_last_button'):
                                self.step1.proceed_last_button.config(state=tk.NORMAL)
                            elif hasattr(self, 'proceed_last_button'):
                                self.proceed_last_button.config(state=tk.NORMAL)
                        
                        logger.debug("Last configuration loaded (async)")
                    except Exception as e:
                        logger.warning(f"Error updating GUI from config: {e}")
                
                # Schedule on main thread
                self.frame.after(0, update_gui)
            
            except Exception as e:
                logger.debug(f"Error loading last configuration: {e}")
        
        # Load in background thread
        threading.Thread(target=load_config, daemon=True).start()
    
    def _load_last_config(self):
        """Load last configuration if exists (synchronous version for explicit calls)"""
        if not self.config_file.exists():
            return
        
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # Load operator path
            if 'operator_path' in config and config['operator_path']:
                self.operator_path_var.set(config['operator_path'])
            
            # Load storage configuration
            if 'storage_type' in config:
                self.storage_type.set(config['storage_type'])
            if 'storage_path' in config:
                self.storage_path_var.set(config['storage_path'])
            if 'storage_url' in config:
                self.storage_url_var.set(config['storage_url'])
            
            # Load regions
            if 'regions' in config:
                for region, selected in config['regions'].items():
                    if region in self.region_vars:
                        self.region_vars[region].set(selected)
            
            # Update storage visibility
            self._update_storage_config_visibility()
            
            # Enable proceed button
            if 'operators_loaded' in config and config['operators_loaded']:
                self.proceed_last_button.config(state=tk.NORMAL)
            
            logger.info("Last configuration loaded")
            
        except Exception as e:
            logger.warning(f"Error loading last configuration: {e}")
    
    def _proceed_as_last_time(self):
        """Load last configuration and proceed automatically"""
        # Delegate to Step 1 module
        if hasattr(self, 'step1'):
            self.step1._proceed_as_last_time()
            return
        
        # Fallback (should not be reached if step1 exists)
        messagebox.showerror("Error", "Step 1 not initialized")
    
    def _load_operators(self, operators: List[Dict]):
        """Load operators into the listbox"""
        logger.debug(f"=== _load_operators called with {len(operators) if operators else 0} operators ===")
        self.operators = operators
        # Only update if we're on Step 2 and widgets are ready
        if self.current_step == 1:
            try:
                if hasattr(self, 'operator_listbox') and hasattr(self, 'category_var'):
                    # Verify widgets are accessible
                    _ = self.operator_listbox
                    _ = self.category_var.get()
                    logger.debug("Widgets verified, calling _update_operator_list")
                    self._update_operator_list()
                else:
                    logger.debug("Widgets not ready, will update when Step 2 is shown")
            except Exception as e:
                logger.debug(f"Widgets not ready for operator update: {e}")
        else:
            logger.debug(f"Not on Step 2 (current_step={self.current_step}), will update when Step 2 is shown")
    
    def _update_operator_list(self):
        """Update operator list based on category filter"""
        logger.debug("=== _update_operator_list called ===")
        
        if not hasattr(self, 'operators'):
            logger.warning("⚠️ No operators attribute found")
            return
        
        logger.debug(f"Operators attribute exists, count: {len(self.operators) if self.operators else 0}")
        
        # Check if widgets are ready - be more defensive
        # Only check if we're on Step 2, otherwise it's expected that widgets don't exist
        if self.current_step != 1:
            logger.debug(f"Not on Step 2 (current_step={self.current_step}), skipping operator list update")
            return
        
        # Check if widgets exist and are accessible
        if not hasattr(self, 'category_var'):
            logger.warning("⚠️ category_var does not exist - Step 2 widgets may not be created yet")
            logger.debug(f"Available attributes: {[attr for attr in dir(self) if not attr.startswith('_')]}")
            return
        
        if not hasattr(self, 'operator_listbox'):
            logger.warning("⚠️ operator_listbox does not exist - Step 2 widgets may not be created yet")
            return
        
        try:
            # Try to access widgets to ensure they're actually created and accessible
            category = self.category_var.get()
            logger.debug(f"Successfully accessed category_var: {category}")
            _ = self.operator_listbox
            logger.debug("Successfully accessed operator_listbox")
            
        except AttributeError as e:
            logger.error(f"❌ Widgets exist but not accessible: {e}")
            return
        except Exception as e:
            logger.error(f"❌ Error accessing widgets: {e}", exc_info=True)
            return
        
        logger.debug("Widgets are ready")
        
        try:
            category = self.category_var.get()
            logger.debug(f"Selected category: {category}")
            
            self.operator_listbox.delete(0, tk.END)
            logger.debug("Cleared operator listbox")
            
            filtered_count = 0
            for op in self.operators:
                op_category = op.get('category', '')
                if category == "All" or op_category == category:
                    name = op.get('name', 'Unknown')
                    self.operator_listbox.insert(tk.END, name)
                    filtered_count += 1
            
            logger.info(f"✅ Updated operator list: {filtered_count} operators shown (category: {category})")
        except Exception as e:
            logger.error(f"❌ Error updating operator list: {e}", exc_info=True)
    
    def _show_operator_details(self, event):
        """Show details of selected operator"""
        selection = self.operator_listbox.curselection()
        if not selection:
            return
        
        op_name = self.operator_listbox.get(selection[0])
        op = next((o for o in self.operators if o.get('name') == op_name), None)
        
        if op:
            details = f"Name: {op.get('name', 'N/A')}\n"
            details += f"Category: {op.get('category', 'N/A')}\n"
            details += f"Definition: {op.get('definition', 'N/A')}\n"
            details += f"Description: {op.get('description', 'N/A')}\n"
            details += f"Scope: {', '.join(op.get('scope', []))}\n"
            details += f"Level: {op.get('level', 'N/A')}\n"
            
            self.operator_details.delete('1.0', tk.END)
            self.operator_details.insert('1.0', details)
    
    def _open_config_section(self, section_key: str):
        """Open configuration section by switching to CONFIG tab"""
        try:
            # Find the parent notebook (ttk.Notebook)
            widget = self.frame
            notebook = None
            while widget:
                widget = widget.master
                if isinstance(widget, ttk.Notebook):
                    notebook = widget
                    break
            
            if not notebook:
                messagebox.showinfo("Info", f"Please navigate to the ⚙️ CONFIG tab manually and select section: {section_key}")
                return
            
            # Find the CONFIG tab index
            tab_count = notebook.index(tk.END)
            config_tab_index = None
            for i in range(tab_count):
                tab_text = notebook.tab(i, "text")
                if "⚙️ CONFIG" in tab_text or "CONFIG" in tab_text:
                    config_tab_index = i
                    break
            
            if config_tab_index is None:
                messagebox.showinfo("Info", f"Please navigate to the ⚙️ CONFIG tab manually and select section: {section_key}")
                return
            
            # Switch to CONFIG tab
            notebook.select(config_tab_index)
            
            # Get the config panel frame
            config_frame = notebook.nametowidget(notebook.tabs()[config_tab_index])
            
            # Find the ConfigPanel instance by searching for set_section method
            def find_config_panel(widget):
                """Recursively find ConfigPanel instance"""
                # Check if this widget has the set_section method (ConfigPanel instance)
                if hasattr(widget, 'set_section'):
                    return widget
                # Also check if it's the frame and has section_var
                if hasattr(widget, 'section_var'):
                    # This might be the ConfigPanel's frame, try to find parent
                    parent = widget.master
                    while parent:
                        if hasattr(parent, 'set_section'):
                            return parent
                        parent = getattr(parent, 'master', None)
                for child in widget.winfo_children():
                    result = find_config_panel(child)
                    if result:
                        return result
                return None
            
            config_panel = find_config_panel(config_frame)
            
            if config_panel and hasattr(config_panel, 'set_section'):
                # Use the set_section method
                if config_panel.set_section(section_key):
                    logger.info(f"✅ Switched to CONFIG tab with section: {section_key}")
                else:
                    logger.warning(f"Invalid section key: {section_key}")
                    messagebox.showwarning("Warning", f"Invalid section: {section_key}")
            else:
                # Fallback: try to find section_var directly
                def find_section_var(widget):
                    """Recursively find section_var StringVar"""
                    if hasattr(widget, 'section_var'):
                        return widget.section_var
                    for child in widget.winfo_children():
                        result = find_section_var(child)
                        if result:
                            return result
                    return None
                
                section_var = find_section_var(config_frame)
                if section_var:
                    section_var.set(section_key)
                    # Find and trigger combobox
                    def find_and_trigger_combobox(widget):
                        if isinstance(widget, ttk.Combobox):
                            var = widget.cget('textvariable')
                            if var and str(var) == str(section_var):
                                widget.event_generate('<<ComboboxSelected>>')
                                return True
                        for child in widget.winfo_children():
                            if find_and_trigger_combobox(child):
                                return True
                        return False
                    find_and_trigger_combobox(config_frame)
                    logger.info(f"✅ Switched to CONFIG tab with section: {section_key}")
                else:
                    logger.warning(f"Could not find ConfigPanel instance, but switched to CONFIG tab")
                    messagebox.showinfo("Info", f"Switched to CONFIG tab. Please select section: {section_key}")
            
        except Exception as e:
            logger.error(f"Error opening config section: {e}", exc_info=True)
            messagebox.showwarning("Warning", f"Could not switch to config tab automatically.\nPlease navigate to ⚙️ CONFIG tab and select section: {section_key}")
    
    def _generate_alphas(self):
        """Generate alpha templates with concurrent slot-based generation"""
        if not self.generator:
            messagebox.showerror("Error", "Generator not initialized")
            return
        
        region = self.ideation_region.get()
        try:
            count = int(self.template_count.get())
        except ValueError:
            messagebox.showerror("Error", "Invalid template count")
            return
        
        if self.generation_running:
            messagebox.showwarning("Warning", "Generation already running. Please wait or stop current generation.")
            return
        
        self.generation_running = True
        self.generate_button.config(state=tk.DISABLED)
        self.stop_generation_button.config(state=tk.NORMAL)
        # Update templates listbox via Step 4
        if hasattr(self, 'step4') and hasattr(self.step4, 'templates_listbox'):
            self.step4.templates_listbox.delete(0, tk.END)
            self.step4.templates_listbox.insert(0, f"Generating {count} templates with 8 concurrent slots...")
        
        # Clear all generation slot displays
        for slot_id in range(8):
            self._update_gen_slot_display(slot_id, "IDLE", "", "", [], 0.0, "")
        
        # Import slot manager
        try:
            from ...core.slot_manager import SlotManager, SlotStatus
            
            # Initialize generation slot manager
            self.gen_slot_manager = SlotManager(max_slots=8)
            
            # Get data fields for region (needed for generation)
            data_fields = self.generator.template_generator.get_data_fields_for_region(region)
            if not data_fields:
                messagebox.showerror("Error", f"No data fields available for {region}")
                self.generation_running = False
                self.generate_button.config(state=tk.NORMAL)
                self.stop_generation_button.config(state=tk.DISABLED)
                return
            
            # Update validator with operators and fields
            if self.generator.template_generator.template_validator:
                if self.generator.template_generator.operator_fetcher:
                    operators = self.generator.template_generator.operator_fetcher.operators
                    if operators:
                        self.generator.template_generator.template_validator.parser.add_operators(operators)
                self.generator.template_generator.template_validator.parser.add_data_fields(data_fields)
        
            # Get available operators and successful patterns
            available_operators = None
            if self.generator.template_generator.operator_fetcher:
                available_operators = self.generator.template_generator.operator_fetcher.operators
            
            successful_patterns = None
            if self.generator.template_generator.template_validator and self.generator.template_generator.template_validator.corrector:
                successful_patterns = self.generator.template_generator.template_validator.corrector.get_successful_patterns(limit=5)
            
            # Queue for templates to generate
            template_queue = list(range(count))
            generated_templates = []
            completed_count = {'successful': 0, 'failed': 0, 'total': count}
            
            def generate_template_in_slot(template_index: int, slot_ids: List[int]):
                """Generate a single template in assigned slot"""
                try:
                    primary_slot_id = slot_ids[0]
                    
                    # Update slot display
                    self._update_gen_slot_display(primary_slot_id, "RUNNING", "Generating...", f"Region: {region}", ["Starting generation..."], 10.0, "Starting...")
                    self._log_to_gen_slot(primary_slot_id, f"[{template_index+1}/{count}] Starting generation...")
                    logger.info(f"[Step 4] Slot {primary_slot_id+1}: Starting template {template_index+1}/{count} generation for {region}")
                    
                    # Update slot progress in manager
                    if self.gen_slot_manager:
                        slot = self.gen_slot_manager.get_slot_status(primary_slot_id)
                        slot.update_progress(10.0, "Starting generation...", "")
                    
                    # Create generation prompt
                    prompt = f"""Generate a WorldQuant Brain FASTEXPR alpha expression for {region} region.

The expression should combine OPERATORS (functions like ts_rank, ts_delta, rank) with DATA FIELDS (variables).

Generate a valid FASTEXPR expression that uses operator(data_field, parameters) syntax."""
                    
                    # Update progress
                    self._update_gen_slot_progress(primary_slot_id, 20.0, "Calling Ollama...", "")
                    self._log_to_gen_slot(primary_slot_id, "Calling Ollama API...")
                    logger.debug(f"[Step 4] Slot {primary_slot_id+1}: Calling Ollama API for template {template_index+1}")
                    
                    # Generate template using Ollama
                    avoidance_context = self.generator.template_generator.duplicate_detector.get_avoidance_context(limit=10)
                    template = self.generator.template_generator.ollama_manager.generate_template(
                        prompt,
                        region=region,
                        avoid_duplicates_context=avoidance_context,
                        available_operators=available_operators,
                        available_fields=data_fields,
                        successful_patterns=successful_patterns
                    )
                    
                    if not template:
                        # Try fallback
                        self._update_gen_slot_progress(primary_slot_id, 40.0, "Trying fallback...", "")
                        template = self.generator.template_generator.generate_template_from_prompt(prompt, region=region, use_ollama=True)
                    
                    if not template:
                        completed_count['failed'] += 1
                        self.gen_slot_manager.release_slots(slot_ids, success=False, error="Generation failed")
                        self._update_gen_slot_display(primary_slot_id, "FAILED", "Generation failed", f"❌ Failed", ["❌ Generation failed"], 100.0, "")
                        self._log_to_gen_slot(primary_slot_id, "❌ Generation failed")
                        return
                    
                    # Clean template
                    template = template.replace('`', '').strip()
                    
                    # Update progress
                    self._update_gen_slot_progress(primary_slot_id, 60.0, "Validating...", "")
                    self._log_to_gen_slot(primary_slot_id, f"Generated: {template[:50]}...")
                    logger.info(f"[Step 4] Slot {primary_slot_id+1}: Generated template {template_index+1}: {template[:80]}...")
                    
                    # Validate and fix
                    if self.generator.template_generator.template_validator:
                        self._update_gen_slot_progress(primary_slot_id, 80.0, "Compiling...", "")
                        logger.debug(f"[Step 4] Slot {primary_slot_id+1}: Compiling template {template_index+1}")
                        compile_result = self.generator.template_generator.template_validator.compile_template(template, optimize=False)
                        
                        if compile_result.success:
                            if compile_result.final_expression and compile_result.final_expression != template:
                                template = compile_result.final_expression
                            self.generator.template_generator.template_validator.learn_from_success(template)
                            self._log_to_gen_slot(primary_slot_id, "✅ Compilation successful")
                            logger.info(f"[Step 4] Slot {primary_slot_id+1}: Template {template_index+1} compiled successfully")
                        else:
                            # Try traditional validation
                            is_valid, error_msg, suggested_fix = self.generator.template_generator.template_validator.validate_template(template, region)
                            if not is_valid:
                                fixed_template, fixes = self.generator.template_generator.template_validator.fix_template(template, error_msg, region)
                                if fixed_template and fixed_template != template:
                                    template = fixed_template
                                    logger.info(f"[Step 4] Slot {primary_slot_id+1}: Fixed template {template_index+1} with {len(fixes)} corrections: {fixes}")
                                    self._log_to_gen_slot(primary_slot_id, f"✅ Fixed and validated ({len(fixes)} fixes)")
                                else:
                                    completed_count['failed'] += 1
                                    self.gen_slot_manager.release_slots(slot_ids, success=False, error=error_msg)
                                    self._update_gen_slot_display(primary_slot_id, "FAILED", template[:40] + "...", f"❌ {error_msg[:30]}", [f"❌ {error_msg[:50]}"], 100.0, "")
                                    self._log_to_gen_slot(primary_slot_id, f"❌ Validation failed: {error_msg}")
                                    logger.warning(f"[Step 4] Slot {primary_slot_id+1}: Template {template_index+1} validation failed: {error_msg}")
                                    return
                    
                    # Success!
                    completed_count['successful'] += 1
                    generated_templates.append({'template': template, 'region': region})
                    self.gen_slot_manager.release_slots(slot_ids, success=True, result={'template': template})
                    self._update_gen_slot_display(primary_slot_id, "COMPLETED", template[:40] + "...", f"✅ Valid", ["✅ Generated", "✅ Validated"], 100.0, "")
                    self._log_to_gen_slot(primary_slot_id, f"✅ SUCCESS: {template[:50]}...")
                    logger.info(f"[Step 4] Slot {primary_slot_id+1}: Template {template_index+1} generated successfully: {template[:80]}...")
                    
                    # Update templates list
                    self.frame.after(0, lambda: self._update_templates_list(generated_templates))
                
                except Exception as e:
                    logger.error(f"[Step 4] Slot {primary_slot_id+1}: Generation error for template {template_index+1}: {e}", exc_info=True)
                    completed_count['failed'] += 1
                    error_msg = str(e)
                    if self.gen_slot_manager:
                        self.gen_slot_manager.release_slots(slot_ids, success=False, error=error_msg)
                    self._update_gen_slot_display(primary_slot_id, "FAILED", "Error", f"❌ Error", [f"❌ ERROR: {error_msg[:50]}"], 100.0, "")
                    self._log_to_gen_slot(primary_slot_id, f"❌ ERROR: {error_msg}")
            
            def generation_coordinator():
                """Coordinate concurrent template generation using slots"""
                try:
                    while template_queue and self.generation_running:
                        # Try to assign slots to queued templates
                        assigned = False
                        for template_index in list(template_queue):
                            if not self.generation_running:
                                break
                            
                            # All generations take 1 slot (no special region handling for generation)
                            slot_ids = self.gen_slot_manager.find_available_slots(1)
                            
                            if slot_ids:
                                # Assign slots and start generation
                                assigned_slots = self.gen_slot_manager.assign_slot(
                                    f"Template {template_index + 1}",
                                    region,
                                    template_index
                                )
                                
                                if assigned_slots:
                                    # Remove from queue
                                    template_queue.remove(template_index)
                                    
                                    # Start generation in thread
                                    thread = threading.Thread(
                                        target=generate_template_in_slot,
                                        args=(template_index, assigned_slots),
                                        daemon=True
                                    )
                                    thread.start()
                                    self.generation_threads.append(thread)
                                    assigned = True
                        
                        if not assigned:
                            # No slots available, wait a bit
                            time.sleep(0.5)
                        
                        # Update progress
                        remaining = len(template_queue)
                        completed = completed_count['successful'] + completed_count['failed']
                        self.frame.after(0, lambda: self.gen_progress_label.config(
                            text=f"Queue: {remaining}, Completed: {completed}/{completed_count['total']}"
                        ))
                    
                    # Wait for all generations to complete
                    for thread in self.generation_threads:
                        thread.join(timeout=300)  # Max 5 minutes per generation
                    
                    # Final update
                    self.frame.after(0, lambda: self.gen_progress_label.config(text=""))
                    self.frame.after(0, lambda: self._update_templates_list(generated_templates))
                    
                except Exception as e:
                    logger.error(f"Generation coordinator error: {e}", exc_info=True)
                finally:
                    self.generation_running = False
                    self.frame.after(0, lambda: self.generate_button.config(state=tk.NORMAL))
                    self.frame.after(0, lambda: self.stop_generation_button.config(state=tk.DISABLED))
                    self.frame.after(0, lambda: self.gen_progress_label.config(text=""))
            
            # Start coordinator thread
            coordinator_thread = threading.Thread(target=generation_coordinator, daemon=True)
            coordinator_thread.start()
            self.generation_threads.append(coordinator_thread)
            
            # Start slot update thread - USE frame.after() for GUI updates
            def update_gen_slots_display():
                """Periodically update generation slot displays"""
                while self.generation_running:
                    try:
                        if self.gen_slot_manager:
                            for slot_id in range(8):
                                slot = self.gen_slot_manager.get_slot_status(slot_id)
                                if slot.status != SlotStatus.IDLE:
                                    # Schedule GUI updates on main thread
                                    self.frame.after(0, lambda sid=slot_id, s=slot: self._update_gen_slot_display(
                                        sid,
                                        s.status.value.upper(),
                                        s.template[:40] + "..." if s.template else "",
                                        f"Region: {s.region}" if s.region else "",
                                        s.get_logs()[-5:],
                                        s.progress_percent,
                                        s.progress_message
                                    ))
                        time.sleep(0.5)
                    except Exception as e:
                        logger.debug(f"Gen slot update error: {e}")
                        time.sleep(1)
            
            update_thread = threading.Thread(target=update_gen_slots_display, daemon=True)
            update_thread.start()
            
        except ImportError as e:
            messagebox.showerror("Error", f"Failed to import modules: {e}")
            self.generation_running = False
            self.generate_button.config(state=tk.NORMAL)
            self.stop_generation_button.config(state=tk.DISABLED)
    
    def _stop_generation(self):
        """Stop running template generation"""
        self.generation_running = False
        self.gen_progress_label.config(text="Stopping generation...")
        self.stop_generation_button.config(state=tk.DISABLED)
    
    def _log_to_gen_slot(self, slot_id: int, message: str):
        """Log message to a specific generation slot"""
        if slot_id in self.gen_slot_widgets and self.gen_slot_manager:
            slot = self.gen_slot_manager.get_slot_status(slot_id)
            # Ensure message is a string, not a tuple
            if isinstance(message, (tuple, list)):
                message = ' '.join(str(m) for m in message) if message else ''
            elif message is None:
                message = ''
            else:
                message = str(message)
            slot.add_log(message)
            # Update display
            self._update_gen_slot_display(slot_id, slot.status.value.upper(), 
                                         slot.template[:40] + "..." if slot.template else "",
                                         f"Region: {slot.region}" if slot.region else "",
                                         slot.get_logs()[-5:],
                                         slot.progress_percent,
                                         slot.progress_message)
    
    def _update_gen_slot_display(self, slot_id: int, status: str, template: str, info: str, logs: List[str], progress: float = 0.0, progress_msg: str = ""):
        """Update generation slot display widget"""
        if slot_id not in self.gen_slot_widgets:
            return
        
        def update():
            widget = self.gen_slot_widgets[slot_id]
            
            # Update status
            status_colors = {
                'IDLE': COLORS.get('text_secondary', '#666666'),
                'RUNNING': COLORS.get('accent_yellow', '#ffff00'),
                'COMPLETED': COLORS.get('accent_green', '#00ff41'),
                'FAILED': '#ff0000'
            }
            widget['status_label'].config(
                text=status,
                fg=status_colors.get(status, COLORS['text_primary'])
            )
            
            # Update template
            widget['template_label'].config(text=template if template else "")
            
            # Update progress
            if progress > 0:
                self._update_gen_slot_progress(slot_id, progress, progress_msg, "")
            
            # Update log
            widget['log_text'].config(state=tk.NORMAL)
            widget['log_text'].delete(1.0, tk.END)
            for log_line in logs:
                widget['log_text'].insert(tk.END, log_line + "\n")
            widget['log_text'].config(state=tk.DISABLED)
            widget['log_text'].see(tk.END)
        
        self.frame.after(0, update)
    
    def _update_gen_slot_progress(self, slot_id: int, percent: float, message: str, api_status: str):
        """Update generation slot progress bar and message"""
        if slot_id not in self.gen_slot_widgets:
            return
        
        def update():
            widget = self.gen_slot_widgets[slot_id]
            
            # Update progress label
            widget['progress_label'].config(text=f"{int(percent)}%")
            
            # Update progress bar
            canvas = widget['progress_bar']
            canvas.delete("all")
            
            # Get canvas dimensions
            canvas.update_idletasks()
            width = canvas.winfo_width()
            height = canvas.winfo_height()
            
            if width <= 1:
                width = 100
            if height <= 1:
                height = 12
            
            # Draw background
            canvas.create_rectangle(0, 0, width, height, fill=COLORS['bg_secondary'], outline=COLORS.get('text_secondary', '#666666'))
            
            # Draw progress bar
            progress_width = int((percent / 100.0) * width)
            if progress_width > 0:
                # Color based on status
                if percent >= 100:
                    color = COLORS.get('accent_green', '#00ff41')
                elif percent >= 50:
                    color = COLORS.get('accent_yellow', '#ffff00')
                else:
                    color = COLORS.get('accent_cyan', '#00ffff')
                
                canvas.create_rectangle(0, 0, progress_width, height, fill=color, outline="")
            
            # Update progress message
            widget['progress_text'].config(text=message[:30] if message else "")
        
        self.frame.after(0, update)
    
    def _update_templates_list(self, templates: List[Dict]):
        """Update templates listbox with generated templates"""
        # Delegate to Step 4 if it exists
        if hasattr(self, 'step4') and hasattr(self.step4, '_update_templates_list'):
            self.step4._update_templates_list(templates)
        else:
            # Fallback: log warning
            logger.warning("Step 4 not initialized, cannot update templates list")
    
    
    # Step 6 methods moved to step6_mining.py
    
    def _store_fields_to_database(self, region: str, fields: List[Dict], storage_config: Dict):
        """Store data fields to configured storage"""
        storage_type = storage_config['type']
        
        try:
            if storage_type == "sqlite":
                import sqlite3
                db_path = storage_config['path'] or "generation_two_backtests.db"
                logger.info(f"Storing to SQLite: {db_path}")
                
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                
                # Create table if not exists
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS data_fields (
                        id TEXT PRIMARY KEY,
                        region TEXT,
                        universe TEXT,
                        delay INTEGER,
                        field_data TEXT,
                        timestamp REAL
                    )
                """)
                
                # Insert or replace fields
                for field in fields:
                    cursor.execute("""
                        INSERT OR REPLACE INTO data_fields 
                        (id, region, universe, delay, field_data, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        field.get('id', ''),
                        region,
                        field.get('universe', ''),
                        field.get('delay', 1),
                        json.dumps(field),
                        time.time()
                    ))
                
                conn.commit()
                conn.close()
                logger.info(f"✓ Stored {len(fields)} fields to SQLite database")
                
            elif storage_type == "remote":
                url = storage_config['url']
                if not url:
                    logger.warning("Remote URL not specified, skipping storage")
                    return
                
                logger.info(f"Storing to remote URL: {url}")
                # TODO: Implement remote storage API call
                import requests
                try:
                    response = requests.post(
                        url,
                        json={
                            'region': region,
                            'fields': fields,
                            'timestamp': time.time()
                        },
                        timeout=30
                    )
                    if response.status_code == 200:
                        logger.info(f"✓ Stored {len(fields)} fields to remote database")
                    else:
                        logger.error(f"✗ Remote storage failed: {response.status_code} - {response.text}")
                except Exception as e:
                    logger.error(f"✗ Error storing to remote: {e}", exc_info=True)
            
            # JSON storage is handled automatically by the fetcher (default behavior)
            
        except Exception as e:
            logger.error(f"Error storing fields to {storage_type}: {e}", exc_info=True)
            raise
    
    def _complete_workflow(self):
        """Complete workflow"""
        messagebox.showinfo("Complete", "Workflow completed! You can now use all features.")
        self.steps_completed.add(4)
