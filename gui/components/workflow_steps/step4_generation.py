"""
Step 4: Alpha Ideation & Generation
Handles template generation with concurrent slot-based execution
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from typing import List, Dict
import logging
import time
import threading

from ...theme import COLORS, FONTS, STYLES

logger = logging.getLogger(__name__)


class Step4Generation:
    """Step 4: Alpha Ideation & Generation"""
    
    def __init__(self, parent_frame, workflow_panel):
        """
        Initialize Step 4
        
        Args:
            parent_frame: Parent frame to pack into
            workflow_panel: Reference to main WorkflowPanel for callbacks
        """
        self.parent_frame = parent_frame
        self.workflow = workflow_panel
        self.frame = tk.Frame(parent_frame, bg=COLORS['bg_panel'])
        
        # Generation state
        self.generation_running = False
        self.generation_threads = []
        self.gen_slot_manager = None
        self.generated_templates = []
        
        self._create_widgets()
    
    def _create_widgets(self):
        """Create Step 4 widgets"""
        tk.Label(
            self.frame,
            text="Step 4: Alpha Ideation & Generation",
            font=FONTS['heading'],
            fg=COLORS['accent_cyan'],
            bg=COLORS['bg_panel']
        ).pack(pady=10)
        
        tk.Label(
            self.frame,
            text="Generate alpha ideas and templates (like v2):",
            font=FONTS['default'],
            fg=COLORS['text_primary'],
            bg=COLORS['bg_panel']
        ).pack(pady=5)
        
        # Ideation controls
        ideation_frame = tk.Frame(self.frame, bg=COLORS['bg_panel'])
        ideation_frame.pack(fill=tk.X, padx=10, pady=5)
        
        tk.Label(
            ideation_frame,
            text="Region:",
            font=FONTS['default'],
            fg=COLORS['text_primary'],
            bg=COLORS['bg_panel']
        ).pack(side=tk.LEFT, padx=5)
        
        self.ideation_region = tk.StringVar(value="USA")
        region_combo = ttk.Combobox(
            ideation_frame,
            textvariable=self.ideation_region,
            values=["USA", "EUR", "CHN", "ASI", "GLB", "IND"],
            state="readonly",
            width=10
        )
        region_combo.pack(side=tk.LEFT, padx=5)
        
        tk.Label(
            ideation_frame,
            text="Templates:",
            font=FONTS['default'],
            fg=COLORS['text_primary'],
            bg=COLORS['bg_panel']
        ).pack(side=tk.LEFT, padx=5)
        
        self.template_count = tk.StringVar(value="10")
        count_entry = tk.Entry(
            ideation_frame,
            textvariable=self.template_count,
            width=5,
            **STYLES['entry']
        )
        count_entry.pack(side=tk.LEFT, padx=5)
        
        self.generate_button = tk.Button(
            ideation_frame,
            text="🎯 GENERATE ALPHAS",
            command=self._generate_alphas,
            **STYLES['button']
        )
        self.generate_button.pack(side=tk.LEFT, padx=5)
        
        self.stop_generation_button = tk.Button(
            ideation_frame,
            text="⏹️ STOP",
            command=self._stop_generation,
            **STYLES['button'],
            state=tk.DISABLED
        )
        self.stop_generation_button.pack(side=tk.LEFT, padx=5)
        
        # Generation progress
        self.gen_progress_label = tk.Label(
            ideation_frame,
            text="",
            font=FONTS['default'],
            fg=COLORS['accent_yellow'],
            bg=COLORS['bg_panel']
        )
        self.gen_progress_label.pack(side=tk.LEFT, padx=10)
        
        # Generation slots visualization
        gen_slots_frame = tk.Frame(self.frame, bg=COLORS['bg_secondary'], relief=tk.RAISED, bd=2)
        gen_slots_frame.pack(fill=tk.X, padx=10, pady=5)
        
        tk.Label(
            gen_slots_frame,
            text="📊 Generation Slots (8 concurrent):",
            font=FONTS['heading'],
            fg=COLORS['accent_cyan'],
            bg=COLORS['bg_secondary']
        ).pack(anchor=tk.W, padx=5, pady=5)
        
        # Create generation slot display grid (2 rows x 4 columns)
        gen_slots_grid = tk.Frame(gen_slots_frame, bg=COLORS['bg_secondary'])
        gen_slots_grid.pack(fill=tk.X, padx=5, pady=5)
        
        self.gen_slot_widgets = {}  # {slot_id: {frame, status_label, template_label, progress_bar, log_text}}
        for row in range(2):
            for col in range(4):
                slot_id = row * 4 + col
                slot_frame = tk.Frame(gen_slots_grid, bg=COLORS['bg_panel'], relief=tk.RAISED, bd=1)
                slot_frame.grid(row=row, column=col, padx=2, pady=2, sticky=tk.NSEW)
                gen_slots_grid.columnconfigure(col, weight=1)
                gen_slots_grid.rowconfigure(row, weight=1)
                
                # Slot header
                header = tk.Frame(slot_frame, bg=COLORS['bg_panel'])
                header.pack(fill=tk.X, padx=2, pady=2)
                
                slot_num_label = tk.Label(
                    header,
                    text=f"Slot {slot_id + 1}",
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
                
                progress_bar = tk.Canvas(
                    progress_frame,
                    height=12,
                    bg=COLORS['bg_secondary'],
                    highlightthickness=0
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
                
                # Slot log (small terminal)
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
                
                self.gen_slot_widgets[slot_id] = {
                    'frame': slot_frame,
                    'status_label': status_label,
                    'template_label': template_label,
                    'progress_label': progress_label,
                    'progress_bar': progress_bar,
                    'progress_text': progress_text,
                    'log_text': log_text
                }
        
        # Generated templates display
        templates_frame = tk.Frame(self.frame, bg=COLORS['bg_panel'])
        templates_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        tk.Label(
            templates_frame,
            text="📋 Generated Templates:",
            font=FONTS['heading'],
            fg=COLORS['accent_cyan'],
            bg=COLORS['bg_panel']
        ).pack(anchor=tk.W, pady=5)
        
        self.templates_listbox = tk.Listbox(
            templates_frame,
            bg=COLORS['bg_secondary'],
            fg=COLORS['accent_green'],
            font=FONTS['mono'],
            selectbackground=COLORS['accent_cyan']
        )
        self.templates_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        templates_scrollbar = tk.Scrollbar(templates_frame, orient=tk.VERTICAL, command=self.templates_listbox.yview)
        templates_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.templates_listbox.config(yscrollcommand=templates_scrollbar.set)
    
    def _generate_alphas(self):
        """Generate alpha templates with concurrent slot-based generation"""
        if not self.workflow.generator:
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
        self.templates_listbox.delete(0, tk.END)
        self.templates_listbox.insert(0, f"Generating {count} templates with 8 concurrent slots...")
        
        # Clear all generation slot displays
        for slot_id in range(8):
            self._update_gen_slot_display(slot_id, "IDLE", "", "", [], 0.0, "")
        
        # Import slot manager
        try:
            from ....core.slot_manager import SlotManager, SlotStatus
            
            # Initialize generation slot manager
            self.gen_slot_manager = SlotManager(max_slots=8)
            
            # Get data fields for region (needed for generation)
            data_fields = self.workflow.generator.template_generator.get_data_fields_for_region(region)
            if not data_fields:
                messagebox.showerror("Error", f"No data fields available for {region}")
                self.generation_running = False
                self.generate_button.config(state=tk.NORMAL)
                self.stop_generation_button.config(state=tk.DISABLED)
                return
            
            # Update validator with operators and fields
            if self.workflow.generator.template_generator.template_validator:
                validator = self.workflow.generator.template_generator.template_validator
                if self.workflow.generator.template_generator.operator_fetcher:
                    operators = self.workflow.generator.template_generator.operator_fetcher.operators
                    if operators:
                        # Update parser if AST is enabled, otherwise update stored operators list
                        if validator.use_ast and validator.parser:
                            validator.parser.add_operators(operators)
                        else:
                            validator.operators = operators
                # Update data fields
                if validator.use_ast and validator.parser:
                    validator.parser.add_data_fields(data_fields)
                else:
                    validator.data_fields = data_fields
            
            # Get available operators and successful patterns
            available_operators = None
            if self.workflow.generator.template_generator.operator_fetcher:
                available_operators = self.workflow.generator.template_generator.operator_fetcher.operators
            
            successful_patterns = None
            if self.workflow.generator.template_generator.template_validator and self.workflow.generator.template_generator.template_validator.corrector:
                successful_patterns = self.workflow.generator.template_generator.template_validator.corrector.get_successful_patterns(limit=5)
            
            # Queue for templates to generate
            template_queue = list(range(count))
            generated_templates = []
            completed_count = {'successful': 0, 'failed': 0, 'total': count}
            
            # Shared operator pool for exclusive selection across slots
            import threading
            operator_pool_lock = threading.Lock()
            used_operator_indices = set()  # Track which operator indices are currently in use OR have been used in this batch
            operator_usage_count = {}  # Track how many times each operator has been used (for diversity)
            max_operator_reuse = 3  # Maximum times an operator can be reused before being temporarily excluded
            # No batch tracking needed - algorithmic generation uses placeholders
            
            def generate_template_in_slot(template_index: int, slot_ids: List[int], retry_count: int = 0):
                """Generate a single template in assigned slot"""
                try:
                    primary_slot_id = slot_ids[0]
                    
                    # Update slot progress in manager (batch updates)
                    if self.gen_slot_manager:
                        slot = self.gen_slot_manager.get_slot_status(primary_slot_id)
                        slot.update_progress(10.0, "Starting generation...", "")
                    self._log_to_gen_slot(primary_slot_id, f"[{template_index+1}/{count}] Starting generation...")
                    # Reduced logging - only log first template and every 5th
                    if template_index == 0 or (template_index + 1) % 5 == 0:
                        logger.info(f"[Step 4] Slot {primary_slot_id+1}: Starting template {template_index+1}/{count} for {region}")
                    
                    # Create generation prompt
                    prompt = f"""Generate a WorldQuant Brain FASTEXPR alpha expression for {region} region.

The expression should combine OPERATORS (functions like ts_rank, ts_delta, rank) with DATA FIELDS (variables).

Generate a valid FASTEXPR expression that uses operator(data_field, parameters) syntax."""
                    
                    # Update progress ONCE before Ollama call (no updates during call to prevent freeze)
                    if self.gen_slot_manager:
                        slot = self.gen_slot_manager.get_slot_status(primary_slot_id)
                        slot.update_progress(25.0, "Calling Ollama API...", "")
                        slot.add_log("Calling Ollama API...")
                    # Reduced logging frequency - only log important events
                    if template_index == 0 or (template_index + 1) % 5 == 0:
                        logger.info(f"[Step 4] Slot {primary_slot_id+1}: Generating template {template_index+1}/{count}")
                    
                    # V2 approach: NO progress callback during Ollama - prevents GUI freeze with concurrent requests
                    # The update thread will periodically show status, no need for real-time callbacks
                    # Multiple concurrent callbacks cause lock contention and GUI freezing
                    
                    # V2 Approach: Select fields and operators by index, use placeholders to avoid misspelling
                    import random
                    selected_field_indices = self.workflow.generator.template_generator._select_fields_v2(
                        data_fields, num_fields=random.randint(2, 4)
                    )
                    selected_fields = [data_fields[i] for i in selected_field_indices if i < len(data_fields)]
                    
                    # Exclusive operator selection: select operators that aren't in use and haven't been overused
                    selected_operator_indices = []
                    selected_operators_list = available_operators
                    if available_operators:
                        # V2 approach: Select 2-4 operators (not more) to keep expressions simple
                        # Use exclusive selection with usage-based diversity
                        with operator_pool_lock:
                            # First, filter out operators that are currently in use OR have been used in this batch
                            available_indices = [
                                i for i in range(len(available_operators)) 
                                if i not in used_operator_indices
                            ]
                            
                            # Then, prioritize operators with lower usage counts (for diversity)
                            # Filter out operators that have been used too many times
                            diverse_indices = [
                                i for i in available_indices 
                                if operator_usage_count.get(i, 0) < max_operator_reuse
                            ]
                            
                            # If we have enough diverse operators, use them; otherwise use all available
                            if len(diverse_indices) >= 2:
                                candidate_indices = diverse_indices
                            else:
                                # Not enough diverse operators - reset usage counts to allow reuse
                                logger.debug(f"[Step 4] Slot {primary_slot_id+1}: Not enough diverse operators, resetting usage counts...")
                                operator_usage_count.clear()
                                candidate_indices = available_indices
                            
                            if len(candidate_indices) < 2:
                                # If still too few, reset everything
                                logger.debug(f"[Step 4] Slot {primary_slot_id+1}: Not enough available operators, resetting usage counts...")
                                used_operator_indices.clear()
                                operator_usage_count.clear()
                                candidate_indices = list(range(len(available_operators)))
                                if len(candidate_indices) < 2:
                                    # If still not enough, we have to use batch-used operators (shouldn't happen with 79 operators)
                                    logger.warning(f"[Step 4] Slot {primary_slot_id+1}: Very few operators available, allowing batch-used operators")
                                    candidate_indices = list(range(len(available_operators)))
                            
                            # Sort by usage count (ascending) to prefer less-used operators
                            candidate_indices.sort(key=lambda i: operator_usage_count.get(i, 0))
                            
                            # Select from the least-used operators (prefer bottom 50% of usage)
                            num_operators = min(random.randint(2, 4), len(candidate_indices))
                            # Take from the least-used half, then random sample
                            half_point = max(1, len(candidate_indices) // 2)
                            least_used_pool = candidate_indices[:half_point]
                            if len(least_used_pool) >= num_operators:
                                selected_operator_indices = random.sample(least_used_pool, num_operators)
                            else:
                                # Not enough in least-used pool, sample from all candidates
                                selected_operator_indices = random.sample(candidate_indices, num_operators)
                            
                            # Mark selected operators as in use
                            used_operator_indices.update(selected_operator_indices)
                            
                            # Track operator names for logging
                            operator_names = [available_operators[i].get('name', '?') for i in selected_operator_indices]
                            
                            for idx in selected_operator_indices:
                                operator_usage_count[idx] = operator_usage_count.get(idx, 0) + 1
                            
                            usage_counts = [operator_usage_count.get(i, 0) for i in selected_operator_indices]
                            logger.debug(f"[Step 4] Slot {primary_slot_id+1}: Selected diverse operators: {operator_names} (usage: {usage_counts})")
                        
                        selected_operators_list = [available_operators[i] for i in selected_operator_indices if i < len(available_operators)]
                    
                    # Generate template algorithmically (NO Ollama calls in Step 4)
                    if self.gen_slot_manager:
                        slot = self.gen_slot_manager.get_slot_status(primary_slot_id)
                        slot.update_progress(30.0, "Generating algorithmically...", "")
                        slot.add_log("🔄 Generating placeholder expression...")
                    
                    from generation_two.core.algorithmic_template_generator import AlgorithmicTemplateGenerator
                    import random
                    
                    generator = AlgorithmicTemplateGenerator(selected_operators_list, selected_fields)
                    
                    # Try to generate unique template (check duplicates)
                    max_duplicate_retries = 10
                    template = None
                    for attempt in range(max_duplicate_retries):
                        # Choose generation method randomly
                        methods = ["random_walk", "brownian", "tree", "linear"]
                        method = random.choice(methods)
                        
                        placeholder_expr = generator.generate_placeholder_expression(
                            max_operators=5,
                            method=method
                        )
                        
                        # Check for duplicates in database
                        if hasattr(self.workflow.generator, 'backtest_storage') and self.workflow.generator.backtest_storage:
                            from generation_two.core import template_similarity
                            similarity_checker = template_similarity.TemplateSimilarityChecker()
                            template_hash = similarity_checker.get_template_hash(placeholder_expr)
                            
                            # Check if this template exists
                            existing_templates = self.workflow.generator.backtest_storage.get_all_templates(region=region, limit=1000)
                            is_duplicate = False
                            
                            for existing_template in existing_templates:
                                existing_hash = similarity_checker.get_template_hash(existing_template)
                                if existing_hash == template_hash:
                                    is_duplicate = True
                                    logger.debug(f"[Step 4] Slot {primary_slot_id+1}: Duplicate template detected, retrying...")
                                    break
                            
                            if not is_duplicate:
                                template = placeholder_expr
                                break
                        else:
                            # No database, just use the generated template
                            template = placeholder_expr
                            break
                    
                    if not template:
                        completed_count['failed'] += 1
                        self.gen_slot_manager.release_slots(slot_ids, success=False, error="Could not generate unique template")
                        self._update_gen_slot_display(primary_slot_id, "FAILED", "Duplicate check failed", f"❌ Failed", ["❌ Could not generate unique template"], 100.0, "")
                        self._log_to_gen_slot(primary_slot_id, "❌ Could not generate unique template after retries")
                        return
                    
                    # Update status
                    if self.gen_slot_manager:
                        slot = self.gen_slot_manager.get_slot_status(primary_slot_id)
                        slot.update_progress(50.0, "✅ Generated", "")
                        slot.add_log(f"✅ Generated: {template[:50]}...")
                    
                    # Template is already generated algorithmically with placeholders
                    # Clean template - preserve commas for operator parameters!
                    import re
                    template = template.replace('`', '').strip()
                    # Fix missing commas: ) number -> ), number
                    template = re.sub(r'\)\s+(\d)', r'), \1', template)
                    
                    # Store template with placeholders for display in Step 4
                    template_with_placeholders = template
                    
                    # For validation, we need to replace placeholders temporarily
                    # But we'll store the template WITH placeholders for display
                    template_for_validation = template
                    if template and selected_operators_list and 'OPERATOR' in template.upper():
                        template_for_validation = self.workflow.generator.template_generator._replace_operator_placeholders(
                            template, selected_operators_list
                        )
                    if template_for_validation and selected_fields and 'DATA_FIELD' in template_for_validation.upper():
                        template_for_validation = self.workflow.generator.template_generator._replace_field_placeholders(
                            template_for_validation, selected_fields, region
                        )
                    
                    # Use template_for_validation for all validation checks
                    template = template_for_validation
                    
                    # No forbidden operators check - algorithmic generation uses placeholders, so no operator reuse issues
                    
                    # Validate operator count (max 5 operators) - retry if too many
                    operator_count = self._count_operators_in_template(template, available_operators)
                    if operator_count > 5:
                        # Release operators from "in use" set
                        with operator_pool_lock:
                            used_operator_indices.difference_update(selected_operator_indices)
                            # Decrement usage count since this attempt failed
                            for idx in selected_operator_indices:
                                if idx in operator_usage_count:
                                    operator_usage_count[idx] = max(0, operator_usage_count[idx] - 1)
                        
                        max_retries = 3
                        if retry_count < max_retries:
                            logger.warning(f"[Step 4] Slot {primary_slot_id+1}: Template {template_index+1} has {operator_count} operators (max 5), retrying ({retry_count+1}/{max_retries})...")
                            self._log_to_gen_slot(primary_slot_id, f"⚠️ Too many operators ({operator_count} > 5), retrying...")
                            # Retry with new operator selection
                            return generate_template_in_slot(template_index, slot_ids, retry_count + 1)
                        else:
                            logger.warning(f"[Step 4] Slot {primary_slot_id+1}: Template {template_index+1} has {operator_count} operators (max 5), max retries reached, rejecting...")
                            self._log_to_gen_slot(primary_slot_id, f"❌ Too many operators ({operator_count} > 5), max retries reached")
                            completed_count['failed'] += 1
                            self.gen_slot_manager.release_slots(slot_ids, success=False, error=f"Too many operators: {operator_count} > 5 (max retries)")
                            self._update_gen_slot_display(primary_slot_id, "FAILED", "Too many operators", f"❌ {operator_count} ops", [f"❌ {operator_count} operators (max 5)"], 100.0, "")
                            return
                    
                    # Validate no consecutive duplicate operators (e.g., ts_step(ts_step(ts_step(...))))
                    # If found, try to deduplicate first before retrying
                    has_duplicates, duplicate_info = self._has_consecutive_duplicate_operators(template, available_operators)
                    if has_duplicates:
                        logger.warning(f"[Step 4] Slot {primary_slot_id+1}: Template {template_index+1} has consecutive duplicate operators: {duplicate_info}, attempting deduplication...")
                        self._log_to_gen_slot(primary_slot_id, f"⚠️ Consecutive duplicate operators: {duplicate_info}, deduplicating...")
                        
                        # Try to deduplicate
                        original_template = template
                        template = self._deduplicate_consecutive_operators(template, available_operators)
                        
                        if template != original_template:
                            # Check if deduplication fixed the issue
                            has_duplicates_after, duplicate_info_after = self._has_consecutive_duplicate_operators(template, available_operators)
                            if not has_duplicates_after:
                                logger.info(f"[Step 4] Slot {primary_slot_id+1}: ✅ Successfully deduplicated consecutive operators: {duplicate_info}")
                                self._log_to_gen_slot(primary_slot_id, f"✅ Deduplicated: {duplicate_info}")
                                # Continue with the deduplicated template
                            else:
                                # Deduplication didn't fully fix it, retry generation
                                logger.warning(f"[Step 4] Slot {primary_slot_id+1}: Deduplication didn't fully fix duplicates: {duplicate_info_after}, retrying...")
                                self._log_to_gen_slot(primary_slot_id, f"⚠️ Deduplication incomplete, retrying...")
                                # Release operators from "in use" set
                                with operator_pool_lock:
                                    used_operator_indices.difference_update(selected_operator_indices)
                                    # Decrement usage count since this attempt failed
                                    for idx in selected_operator_indices:
                                        if idx in operator_usage_count:
                                            operator_usage_count[idx] = max(0, operator_usage_count[idx] - 1)

                                max_retries = 3
                                if retry_count < max_retries:
                                    return generate_template_in_slot(template_index, slot_ids, retry_count + 1)
                                else:
                                    logger.warning(f"[Step 4] Slot {primary_slot_id+1}: Template {template_index+1} has consecutive duplicate operators: {duplicate_info_after}, max retries reached, rejecting...")
                                    completed_count['failed'] += 1
                                    self.gen_slot_manager.release_slots(slot_ids, success=False, error=f"Consecutive duplicate operators: {duplicate_info_after}")
                                    self._update_gen_slot_display(primary_slot_id, "FAILED", "Duplicate operators", f"❌ {duplicate_info_after}", [f"❌ Consecutive duplicates: {duplicate_info_after}"], 100.0, "")
                                    return
                        else:
                            # Deduplication didn't change anything, retry generation
                            logger.warning(f"[Step 4] Slot {primary_slot_id+1}: Could not deduplicate, retrying...")
                            self._log_to_gen_slot(primary_slot_id, f"⚠️ Could not deduplicate, retrying...")
                            # Release operators from "in use" set
                            with operator_pool_lock:
                                used_operator_indices.difference_update(selected_operator_indices)
                                # Decrement usage count since this attempt failed
                                for idx in selected_operator_indices:
                                    if idx in operator_usage_count:
                                        operator_usage_count[idx] = max(0, operator_usage_count[idx] - 1)

                            max_retries = 3
                            if retry_count < max_retries:
                                return generate_template_in_slot(template_index, slot_ids, retry_count + 1)
                            else:
                                logger.warning(f"[Step 4] Slot {primary_slot_id+1}: Template {template_index+1} has consecutive duplicate operators: {duplicate_info}, max retries reached, rejecting...")
                                completed_count['failed'] += 1
                                self.gen_slot_manager.release_slots(slot_ids, success=False, error=f"Consecutive duplicate operators: {duplicate_info}")
                                self._update_gen_slot_display(primary_slot_id, "FAILED", "Duplicate operators", f"❌ {duplicate_info}", [f"❌ Consecutive duplicates: {duplicate_info}"], 100.0, "")
                                return
                    
                    # Update progress
                    if self.gen_slot_manager:
                        slot = self.gen_slot_manager.get_slot_status(primary_slot_id)
                        slot.update_progress(80.0, "✅ Generated", "")
                        slot.add_log(f"Generated: {template[:50]}...")
                    self._log_to_gen_slot(primary_slot_id, f"Generated: {template[:50]}...")
                    # Only log important events (successful generation)
                    if (template_index + 1) % 3 == 0:  # Log every 3rd successful generation
                        logger.info(f"[Step 4] Slot {primary_slot_id+1}: ✅ Template {template_index+1} generated")
                    
                    # No WorldQuant testing in Step 4 - templates are generated with placeholders
                    # WorldQuant validation will happen in Step 5 during simulation
                    
                    # Success! Release operators from "in use" set
                    # No need to track batch_used_operator_names since we're using placeholders
                    if 'selected_operator_indices' in locals():
                        with operator_pool_lock:
                            used_operator_indices.difference_update(selected_operator_indices)
                            logger.debug(f"[Step 4] Slot {primary_slot_id+1}: Released operators {selected_operator_indices} from active use")
                    
                    completed_count['successful'] += 1
                    # Store template WITH placeholders for display in Step 4
                    # Placeholders will be replaced in Step 5 before simulation
                    generated_templates.append({'template': template_with_placeholders, 'region': region})
                    
                    # Store template with placeholders in database
                    if hasattr(self.workflow.generator, 'backtest_storage') and self.workflow.generator.backtest_storage:
                        try:
                            from generation_two.core import template_similarity
                            similarity_checker = template_similarity.TemplateSimilarityChecker()
                            operators_used = list(similarity_checker.extract_operators(template_with_placeholders))
                            fields_used = list(similarity_checker.extract_fields(template_with_placeholders))
                            
                            self.workflow.generator.backtest_storage.store_template(
                                template=template_with_placeholders,
                                region=region,
                                operators_used=operators_used,
                                fields_used=fields_used
                            )
                            logger.debug(f"[Step 4] Stored template with placeholders in database: {template_with_placeholders[:50]}...")
                        except Exception as e:
                            logger.warning(f"[Step 4] Failed to store template in database: {e}")
                    self.gen_slot_manager.release_slots(slot_ids, success=True, result={'template': template})
                    # Update slot display with consistent status
                    stored_msg = "✅ Stored" if hasattr(self.workflow.generator, 'backtest_storage') and self.workflow.generator.backtest_storage else ""
                    status_messages = ["✅ Generated"]
                    if stored_msg:
                        status_messages.append(stored_msg)
                    
                    self._update_gen_slot_display(primary_slot_id, "COMPLETED", template_with_placeholders[:40] + "...", f"✅ Generated", status_messages, 100.0, "")
                    self._log_to_gen_slot(primary_slot_id, f"✅ Generated: {template_with_placeholders[:50]}...")
                    # Only log every 3rd successful template to reduce spew
                    if (template_index + 1) % 3 == 0:
                        logger.info(f"[Step 4] Slot {primary_slot_id+1}: ✅ Template {template_index+1} completed")
                    
                    # Update templates list (throttled - only update every few templates)
                    if len(generated_templates) % 3 == 0 or len(generated_templates) == completed_count['total']:
                        self.workflow.frame.after_idle(lambda: self._update_templates_list(generated_templates))
                
                except Exception as e:
                    # Release operators back to pool on error
                    if 'selected_operator_indices' in locals():
                        with operator_pool_lock:
                            used_operator_indices.difference_update(selected_operator_indices)
                    
                    logger.error(f"[Step 4] Slot {primary_slot_id+1}: Generation error for template {template_index+1}: {e}", exc_info=True)
                    completed_count['failed'] += 1
                    error_msg = str(e)
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
                        
                        # Update progress (throttled - only update every 2 seconds)
                        if not hasattr(update_gen_slots_display, '_last_progress_update'):
                            update_gen_slots_display._last_progress_update = 0
                        
                        current_time_progress = time.time()
                        if current_time_progress - update_gen_slots_display._last_progress_update >= 2.0:
                            remaining = len(template_queue)
                            completed = completed_count['successful'] + completed_count['failed']
                            self.workflow.frame.after_idle(lambda: self.gen_progress_label.config(
                                text=f"Queue: {remaining}, Completed: {completed}/{completed_count['total']}"
                            ))
                            update_gen_slots_display._last_progress_update = current_time_progress
                    
                    # Wait for all generations to complete (non-blocking check)
                    # Don't use join() as it can block - just check if threads are alive
                    max_wait_time = 600  # 10 minutes max
                    start_wait = time.time()
                    while self.generation_running and (time.time() - start_wait) < max_wait_time:
                        alive_threads = [t for t in self.generation_threads if t.is_alive()]
                        if not alive_threads:
                            break
                        time.sleep(1)  # Check every second
                    
                    # Final update (batched to reduce GUI calls)
                    def final_updates():
                        self.gen_progress_label.config(text="")
                        self._update_templates_list(generated_templates)
                        self.generate_button.config(state=tk.NORMAL)
                        self.stop_generation_button.config(state=tk.DISABLED)
                    
                    self.workflow.frame.after_idle(final_updates)
                    
                except Exception as e:
                    logger.error(f"Generation coordinator error: {e}", exc_info=True)
                finally:
                    self.generation_running = False
                    # Clear batch-used operators when batch completes
                    with operator_pool_lock:
                        # Batch complete - no cleanup needed since we don't track batch operators
                        logger.debug(f"[Step 4] Batch complete")
                    # Batch final state updates
                    def cleanup_updates():
                        self.generate_button.config(state=tk.NORMAL)
                        self.stop_generation_button.config(state=tk.DISABLED)
                        self.gen_progress_label.config(text="")
                    
                    self.workflow.frame.after_idle(cleanup_updates)
            
            # Start coordinator thread
            coordinator_thread = threading.Thread(target=generation_coordinator, daemon=True)
            coordinator_thread.start()
            self.generation_threads.append(coordinator_thread)
            
            # Start slot update thread - HEAVILY OPTIMIZED to prevent GUI freezing
            def update_gen_slots_display():
                """Periodically update generation slot displays with aggressive throttling"""
                last_update_time = {}
                last_status = {}  # Track last status to detect changes
                update_interval = 2.0  # Update every 2 seconds (increased to reduce load)
                max_updates_per_cycle = 4  # Limit updates per cycle to prevent overwhelming GUI
                
                while self.generation_running:
                    try:
                        if self.gen_slot_manager:
                            current_time = time.time()
                            updates = []
                            
                            for slot_id in range(8):
                                slot = self.gen_slot_manager.get_slot_status(slot_id)
                                if slot.status != SlotStatus.IDLE:
                                    last_time = last_update_time.get(slot_id, 0)
                                    last_slot_status = last_status.get(slot_id, SlotStatus.IDLE)
                                    # Track last progress to detect significant changes (like Ollama completion)
                                    last_progress_key = f'_last_progress_{slot_id}'
                                    last_progress = getattr(update_gen_slots_display, last_progress_key, 0.0)
                                    
                                    # Only update if:
                                    # 1. Enough time has passed (2 seconds)
                                    # 2. Status actually changed (not just time-based)
                                    # 3. Progress changed significantly (10% threshold to catch Ollama completion)
                                    time_elapsed = current_time - last_time >= update_interval
                                    status_changed = slot.status != last_slot_status
                                    progress_changed = abs(slot.progress_percent - last_progress) >= 10.0
                                    
                                    if time_elapsed or status_changed or progress_changed:
                                        updates.append((slot_id, slot))
                                        last_update_time[slot_id] = current_time
                                        last_status[slot_id] = slot.status
                                        setattr(update_gen_slots_display, last_progress_key, slot.progress_percent)
                                        
                                        # Limit updates per cycle to prevent GUI overload
                                        if len(updates) >= max_updates_per_cycle:
                                            break
                            
                            # Batch all GUI updates in a single after() call (more efficient)
                            if updates:
                                def batch_update():
                                    try:
                                        for slot_id, slot in updates:
                                            # Limit to last 5 log lines for display performance
                                            all_logs = slot.get_logs()
                                            display_logs = all_logs[-5:] if len(all_logs) > 5 else all_logs
                                            
                                            # Direct update (no nested frame.after calls)
                                            self._update_gen_slot_display_direct(
                                                slot_id,
                                                slot.status.value.upper(),
                                                slot.template[:40] + "..." if slot.template else "",
                                                f"Region: {slot.region}" if slot.region else "",
                                                display_logs,
                                                slot.progress_percent,
                                                slot.progress_message
                                            )
                                    except Exception as e:
                                        logger.debug(f"Batch update error: {e}")
                                
                                # Use after_idle instead of after(0) to reduce priority
                                self.workflow.frame.after_idle(batch_update)
                        
                        time.sleep(update_interval)  # Sleep longer to reduce CPU usage
                    except Exception as e:
                        logger.debug(f"Gen slot update error: {e}")
                        time.sleep(2)  # Longer sleep on error
            
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
        """Log message to a specific generation slot - OPTIMIZED to avoid immediate GUI update"""
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
            # Don't immediately update display - let the update thread handle it (more efficient)
    
    def _update_gen_slot_display(self, slot_id: int, status: str, template: str, info: str, logs: List[str], progress: float = 0.0, progress_msg: str = ""):
        """Update generation slot display widget - schedules update on main thread"""
        if slot_id not in self.gen_slot_widgets:
            return
        
        def update():
            self._update_gen_slot_display_direct(slot_id, status, template, info, logs, progress, progress_msg)
        
        self.workflow.frame.after(0, update)
    
    def _update_gen_slot_display_direct(self, slot_id: int, status: str, template: str, info: str, logs: List[str], progress: float = 0.0, progress_msg: str = ""):
        """Update generation slot display widget directly (no frame.after nesting) - OPTIMIZED for performance"""
        if slot_id not in self.gen_slot_widgets:
            return
        
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
        
        # Update progress directly (no nested frame.after)
        if progress > 0:
            self._update_gen_slot_progress_direct(slot_id, progress, progress_msg, "")
        
        # Update log - only if content changed (save resources)
        if logs:
            widget['log_text'].config(state=tk.NORMAL)
            # Only update if logs actually changed (save resources)
            current_content = widget['log_text'].get(1.0, tk.END).strip()
            new_content = '\n'.join(str(log_line) for log_line in logs)
            
            if current_content != new_content:
                try:
                    widget['log_text'].delete(1.0, tk.END)
                    # Insert all logs at once (limit to last 5 lines for display performance)
                    log_text = '\n'.join(str(log_line) for log_line in logs[-5:])
                    widget['log_text'].insert(1.0, log_text + "\n")
                    # Auto-scroll to end
                    widget['log_text'].see(tk.END)
                except Exception as e:
                    logger.debug(f"Log update error for slot {slot_id}: {e}")
            widget['log_text'].config(state=tk.DISABLED)
    
    def _update_gen_slot_progress(self, slot_id: int, percent: float, message: str, api_status: str):
        """Update generation slot progress bar and message - schedules update on main thread"""
        if slot_id not in self.gen_slot_widgets:
            return
        
        def update():
            self._update_gen_slot_progress_direct(slot_id, percent, message, api_status)
        
        self.workflow.frame.after(0, update)
    
    def _update_gen_slot_progress_direct(self, slot_id: int, percent: float, message: str, api_status: str):
        """Update generation slot progress bar and message directly (no frame.after nesting) - OPTIMIZED for performance"""
        if slot_id not in self.gen_slot_widgets:
            return
        
        # Ensure percent is a float (handle string inputs from API)
        try:
            percent = float(percent)
        except (ValueError, TypeError):
            logger.warning(f"Invalid percent value: {percent}, using 0.0")
            percent = 0.0
        
        # Clamp percent to valid range [0, 100]
        percent = max(0.0, min(100.0, percent))
        
        # Cache last progress to avoid unnecessary updates
        if not hasattr(self, '_last_progress'):
            self._last_progress = {}
        
        last_progress = self._last_progress.get(slot_id, -1)
        # Only update if progress changed significantly (save resources) - increased threshold
        if abs(percent - last_progress) < 5.0 and percent < 100:
            return
        
        self._last_progress[slot_id] = percent
        
        try:
            widget = self.gen_slot_widgets[slot_id]
            
            # Update progress label
            widget['progress_label'].config(text=f"{int(percent)}%")
            
            # Update progress bar (simplified to reduce canvas operations)
            canvas = widget['progress_bar']
            
            # Get canvas dimensions (avoid update_idletasks if possible)
            width = canvas.winfo_width()
            height = canvas.winfo_height()
            
            # Avoid update_idletasks() - it creates DIBSECTION bitmaps and consumes memory
            # Use cached dimensions or defaults instead
            if width <= 1 or height <= 1:
                # Try to get dimensions without update_idletasks first
                try:
                    # Use winfo_reqwidth/reqheight which don't require update_idletasks
                    width = canvas.winfo_reqwidth()
                    height = canvas.winfo_reqheight()
                    if width <= 1 or height <= 1:
                        width = 100
                        height = 12
                except:
                    width = 100
                    height = 12
            
            if width <= 1:
                width = 100
            if height <= 1:
                height = 12
            
            # Draw progress bar - avoid frequent delete/create to reduce memory usage
            # Only redraw if dimensions are valid and significant change
            try:
                # Check if canvas has items before deleting (reduces unnecessary operations)
                existing_items = canvas.find_all()
                if existing_items:
                    canvas.delete("all")
                
                # Use simpler drawing - single rectangle instead of two
                progress_width = int((percent / 100.0) * width)
                if progress_width > 0:
                    # Color based on status
                    if percent >= 100:
                        color = COLORS.get('accent_green', '#00ff41')
                    elif percent >= 50:
                        color = COLORS.get('accent_yellow', '#ffff00')
                    else:
                        color = COLORS.get('accent_cyan', '#00ffff')
                    
                    # Draw only progress bar, background is handled by canvas bg color
                    canvas.create_rectangle(0, 0, progress_width, height, fill=color, outline="")
            except Exception as e:
                logger.debug(f"Canvas draw error: {e}")
                pass  # Silently fail to prevent memory issues
            
            # Update progress message
            widget['progress_text'].config(text=message[:25] if message else "")
        except Exception as e:
            # Silently fail progress updates to prevent GUI freezing
            logger.debug(f"Progress update error for slot {slot_id}: {e}")
    
    def _update_templates_list(self, templates: List[Dict]):
        """Update templates listbox with generated templates"""
        self.templates_listbox.delete(0, tk.END)
        
        if not templates:
            self.templates_listbox.insert(0, "No templates generated")
            self.generate_button.config(state=tk.NORMAL)
            return
        
        # Clean templates (remove backticks, fix common errors)
        cleaned_templates = []
        for template in templates:
            template_str = template.get('template', '')
            # Remove backticks and clean
            template_str = template_str.replace('`', '').strip()
            # Update template dict
            template['template'] = template_str
            cleaned_templates.append(template)
        
        for i, template in enumerate(cleaned_templates, 1):
            template_str = template.get('template', '')
            region_str = template.get('region', '')
            # Show full template (no truncation)
            display_text = f"{i}. [{region_str}] {template_str}"
            self.templates_listbox.insert(tk.END, display_text)
        
        # Store templates for simulation
        self.generated_templates = cleaned_templates
        self.workflow.generated_templates = cleaned_templates  # Also store in workflow for Step 5
        
        self.generate_button.config(state=tk.NORMAL)
    
    def _count_operators_in_template(self, template: str, available_operators: List[Dict] = None) -> int:
        """Count the number of operators used in a template"""
        if not template:
            return 0
        
        import re
        
        # Get operator names from available_operators if provided
        operator_names = set()
        if available_operators:
            for op in available_operators:
                name = op.get('name', '')
                if name:
                    operator_names.add(name)
        
        # Also count arithmetic operators
        arithmetic_ops = {'+', '-', '*', '/', '^', '%', '>', '<', '>=', '<=', '==', '!=', '&&', '||'}
        
        operator_count = 0
        
        # Count function-style operators (operator_name(...)
        # Pattern: word followed by opening parenthesis (but not field names)
        function_pattern = r'\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\('
        matches = re.finditer(function_pattern, template)
        
        for match in matches:
            function_name = match.group(1)
            # Check if it's a known operator (not a field name)
            if operator_names and function_name in operator_names:
                operator_count += 1
            elif not operator_names:
                # If we don't have operator list, count common operator patterns
                common_operators = {
                    'ts_rank', 'ts_max', 'ts_min', 'ts_sum', 'ts_mean', 'ts_std_dev', 'ts_skewness', 'ts_kurtosis',
                    'ts_corr', 'ts_regression', 'ts_delta', 'ts_ratio', 'ts_product', 'ts_scale', 'ts_zscore',
                    'ts_lag', 'ts_lead', 'ts_arg_max', 'ts_arg_min', 'ts_step', 'ts_bucket', 'ts_hump',
                    'rank', 'add', 'subtract', 'multiply', 'divide', 'power', 'abs', 'sign', 'sqrt', 'log', 'exp',
                    'max', 'min', 'sum', 'mean', 'std', 'std_dev', 'corr', 'regression', 'delta', 'ratio', 'product', 'scale', 'zscore', 'lag', 'lead',
                    'normalize', 'winsorize', 'signed_power', 'inverse', 'inverse_sqrt',
                    'group_neutralize', 'group_zscore', 'group_rank', 'group_max', 'group_min', 'group_mean', 'group_backfill',
                    'vec_avg', 'vec_sum', 'vec_max', 'vec_min',
                    'if_else', 'greater', 'less', 'greater_equal', 'less_equal', 'equal', 'not_equal',
                    'and', 'or', 'not', 'is_nan', 'is_finite', 'is_infinite', 'fill_na', 'forward_fill',
                    'backward_fill', 'clip', 'clip_lower', 'clip_upper', 'bucket', 'step', 'hump'
                }
                if function_name.startswith('ts_') or function_name in common_operators:
                    operator_count += 1
        
        # Count arithmetic operators (but not inside function calls)
        # Simple heuristic: count standalone arithmetic operators
        for op in arithmetic_ops:
            # Count operators that are not part of function names
            pattern = r'(?<![a-zA-Z0-9_])' + re.escape(op) + r'(?![a-zA-Z0-9_])'
            operator_count += len(re.findall(pattern, template))
        
        return operator_count
    
    def _replace_forbidden_operators(self, template: str, forbidden_operators: List[str], available_operator_names: List[str], available_operators: List[Dict]) -> str:
        """
        Mechanically replace forbidden operators with available ones
        
        Args:
            template: Template with forbidden operators
            forbidden_operators: List of forbidden operator names
            available_operator_names: List of available operator names for this slot
            available_operators: Full list of available operators (for finding replacements)
            
        Returns:
            Template with forbidden operators replaced, or original if replacement failed
        """
        import re
        fixed_template = template
        
        # Create operator replacement map (forbidden -> available)
        # Try to find similar operators (same category/type)
        replacement_map = {}
        
        for forbidden_op in forbidden_operators:
            # Try to find a replacement from available operators
            # First, try to find similar operators (same prefix, same category)
            best_replacement = None
            
            # Strategy 1: Find operator with same prefix (e.g., ts_rank -> ts_max, ts_min)
            forbidden_prefix = forbidden_op.split('_')[0] if '_' in forbidden_op else forbidden_op
            for available_op_dict in available_operators:
                available_name = available_op_dict.get('name', '')
                if available_name in available_operator_names:
                    # Check if it has similar prefix or is in same category
                    available_prefix = available_name.split('_')[0] if '_' in available_name else available_name
                    if available_prefix == forbidden_prefix or available_name.startswith(forbidden_prefix + '_'):
                        best_replacement = available_name
                        break
            
            # Strategy 2: If no prefix match, try to find by category
            if not best_replacement:
                forbidden_category = None
                for op_dict in available_operators:
                    if op_dict.get('name', '') == forbidden_op:
                        forbidden_category = op_dict.get('category', '')
                        break
                
                if forbidden_category:
                    for available_op_dict in available_operators:
                        available_name = available_op_dict.get('name', '')
                        if (available_name in available_operator_names and 
                            available_op_dict.get('category', '') == forbidden_category):
                            best_replacement = available_name
                            break
            
            # Strategy 3: Just use first available operator if no match found
            if not best_replacement and available_operator_names:
                best_replacement = available_operator_names[0]
            
            if best_replacement:
                replacement_map[forbidden_op] = best_replacement
                logger.debug(f"🔧 Replacement map: {forbidden_op} -> {best_replacement}")
        
        # Replace forbidden operators in template
        for forbidden_op, replacement in replacement_map.items():
            # Pattern: operator_name( or operator_name (with space)
            pattern = r'\b' + re.escape(forbidden_op) + r'\s*\('
            if re.search(pattern, fixed_template, re.IGNORECASE):
                fixed_template = re.sub(pattern, replacement + '(', fixed_template, flags=re.IGNORECASE)
                logger.info(f"🔧 Replaced {forbidden_op} -> {replacement} in template")
        
        return fixed_template
    
    def _has_consecutive_duplicate_operators(self, template: str, available_operators: List[Dict] = None) -> tuple:
        """
        Check if template has consecutive duplicate operators (e.g., ts_step(ts_step(ts_step(...))))
        
        Returns:
            (has_duplicates: bool, duplicate_info: str)
        """
        if not template:
            return False, ""
        
        import re
        
        # Get operator names from available_operators if provided
        operator_names = set()
        if available_operators:
            for op in available_operators:
                name = op.get('name', '')
                if name:
                    operator_names.add(name)
        
        # Also include common operators even if not in available_operators
        common_operators = {
            'ts_rank', 'ts_max', 'ts_min', 'ts_sum', 'ts_mean', 'ts_std_dev', 'ts_skewness', 'ts_kurtosis',
            'ts_corr', 'ts_regression', 'ts_delta', 'ts_ratio', 'ts_product', 'ts_scale', 'ts_zscore',
            'ts_lag', 'ts_lead', 'ts_arg_max', 'ts_arg_min', 'ts_step', 'ts_bucket', 'ts_hump',
            'ts_count_nans', 'ts_count_infs', 'ts_count_finites',
            'rank', 'add', 'subtract', 'multiply', 'divide', 'power', 'abs', 'sign', 'sqrt', 'log', 'exp',
            'max', 'min', 'sum', 'mean', 'std', 'std_dev', 'corr', 'regression', 'delta', 'ratio', 'product', 'scale', 'zscore', 'lag', 'lead',
            'normalize', 'winsorize', 'signed_power', 'inverse', 'inverse_sqrt',
            'group_neutralize', 'group_zscore', 'group_rank', 'group_max', 'group_min', 'group_mean', 'group_backfill',
            'vec_avg', 'vec_sum', 'vec_max', 'vec_min',
            'if_else', 'greater', 'less', 'greater_equal', 'less_equal', 'equal', 'not_equal',
            'and', 'or', 'not', 'is_nan', 'is_finite', 'is_infinite', 'fill_na', 'forward_fill',
            'backward_fill', 'clip', 'clip_lower', 'clip_upper', 'bucket', 'step', 'hump'
        }
        
        all_operators = operator_names if operator_names else common_operators
        
        # Pattern to find function-style operators: operator_name(...)
        function_pattern = r'\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\('
        
        # Find all operator occurrences with their positions
        operator_positions = []
        for match in re.finditer(function_pattern, template):
            function_name = match.group(1)
            if function_name in all_operators:
                operator_positions.append((match.start(), function_name))
        
        # Check for consecutive duplicates (same operator appearing 2+ times in a row, nested)
        # Pattern: operator(operator(operator(...))) - same operator nested multiple times
        consecutive_duplicates = []
        if len(operator_positions) >= 2:
            i = 0
            while i < len(operator_positions) - 1:
                current_op = operator_positions[i][1]
                next_op = operator_positions[i + 1][1]
                
                # Check if they're the same operator
                if current_op == next_op:
                    # Extract the substring between the two operators to check if they're nested
                    start_pos = operator_positions[i][0]
                    next_start_pos = operator_positions[i + 1][0]
                    between = template[start_pos:next_start_pos]
                    
                    # Check if they're nested: the next operator should appear right after the current one's opening paren
                    # Pattern: "operator(" followed by "operator(" means nested
                    # The between text should be exactly "operator(" or contain "operator("
                    expected_between = current_op + '('
                    if expected_between in between or between.strip() == expected_between.strip():
                        # Count how many consecutive duplicates (nested)
                        count = 2
                        for j in range(i + 2, len(operator_positions)):
                            if operator_positions[j][1] == current_op:
                                # Check if it's nested (immediately after previous one)
                                prev_pos = operator_positions[j - 1][0]
                                curr_pos = operator_positions[j][0]
                                between_nested = template[prev_pos:curr_pos]
                                expected_nested = current_op + '('
                                if expected_nested in between_nested or between_nested.strip() == expected_nested.strip():
                                    count += 1
                                else:
                                    break
                            else:
                                break
                        
                        if count >= 2:  # At least 2 consecutive duplicates
                            consecutive_duplicates.append(f"{current_op} (x{count})")
                            # Skip the rest of this sequence
                            i += count
                            continue
                
                i += 1
        
        if consecutive_duplicates:
            return True, ", ".join(consecutive_duplicates)
        
        return False, ""
    
    def _deduplicate_consecutive_operators(self, template: str, available_operators: List[Dict] = None) -> str:
        """
        Remove consecutive duplicate operators from template
        e.g., ts_step(ts_step(ts_step(field))) -> ts_step(field)
        e.g., days_from_last_change(days_from_last_change(field)) -> days_from_last_change(field)
        
        Returns:
            Fixed template with duplicates removed
        """
        if not template:
            return template
        
        import re
        
        # Get operator names from available_operators if provided
        operator_names = set()
        if available_operators:
            for op in available_operators:
                name = op.get('name', '')
                if name:
                    operator_names.add(name)
        
        # Also include common operators even if not in available_operators
        common_operators = {
            'ts_rank', 'ts_max', 'ts_min', 'ts_sum', 'ts_mean', 'ts_std_dev', 'ts_skewness', 'ts_kurtosis',
            'ts_corr', 'ts_regression', 'ts_delta', 'ts_ratio', 'ts_product', 'ts_scale', 'ts_zscore',
            'ts_lag', 'ts_lead', 'ts_arg_max', 'ts_arg_min', 'ts_step', 'ts_bucket', 'ts_hump',
            'ts_count_nans', 'ts_count_infs', 'ts_count_finites',
            'rank', 'add', 'subtract', 'multiply', 'divide', 'power', 'abs', 'sign', 'sqrt', 'log', 'exp',
            'max', 'min', 'sum', 'mean', 'std', 'std_dev', 'corr', 'regression', 'delta', 'ratio', 'product', 'scale', 'zscore', 'lag', 'lead',
            'normalize', 'winsorize', 'signed_power', 'inverse', 'inverse_sqrt',
            'group_neutralize', 'group_zscore', 'group_rank', 'group_max', 'group_min', 'group_mean', 'group_backfill',
            'vec_avg', 'vec_sum', 'vec_max', 'vec_min',
            'if_else', 'greater', 'less', 'greater_equal', 'less_equal', 'equal', 'not_equal',
            'and', 'or', 'not', 'is_nan', 'is_finite', 'is_infinite', 'fill_na', 'forward_fill',
            'backward_fill', 'clip', 'clip_lower', 'clip_upper', 'bucket', 'step', 'hump',
            'days_from_last_change'  # Add this operator
        }
        
        all_operators = operator_names if operator_names else common_operators
        
        # Improved approach: Match nested duplicate operators and remove them while maintaining parenthesis balance
        # Pattern: operator(operator(...)) -> operator(...)
        # We need to match the full nested pattern and extract the inner content
        
        fixed_template = template
        max_iterations = 10  # Prevent infinite loops
        iteration = 0
        
        while iteration < max_iterations:
            iteration += 1
            changed = False
            
            # For each known operator, check for nested duplicates
            for op_name in all_operators:
                # Pattern: operator(operator(...)) - we need to match the full nested call
                # Match: operator(operator( and then find the matching closing parentheses
                pattern = r'\b(' + re.escape(op_name) + r')\s*\(\s*\1\s*\('
                
                # Find all matches and process them in reverse order (to maintain positions)
                matches = list(re.finditer(pattern, fixed_template))
                if matches:
                    # Process in reverse order to maintain string positions
                    for match in reversed(matches):
                        start_pos = match.start()
                        # Find the position after the second opening parenthesis
                        after_second_open = match.end()
                        
                        # Now we need to find the matching closing parenthesis for the inner operator
                        # Count parentheses to find the matching closing paren
                        paren_count = 2  # We have two opening parens
                        inner_end = after_second_open
                        
                        # Find the matching closing parenthesis for the inner operator
                        while inner_end < len(fixed_template) and paren_count > 1:
                            if fixed_template[inner_end] == '(':
                                paren_count += 1
                            elif fixed_template[inner_end] == ')':
                                paren_count -= 1
                            inner_end += 1
                        
                        # inner_end now points to the character AFTER the closing paren of the inner operator
                        # At this point, paren_count should be 1 (one outer opening paren remains)
                        
                        # Extract the inner content (between the second opening paren and the matching closing paren)
                        inner_start = after_second_open
                        inner_content = fixed_template[inner_start:inner_end-1]  # -1 to exclude the closing paren
                        
                        # Find the outer closing parenthesis (for the outer operator)
                        # Start from inner_end (which is after the inner closing paren)
                        # We still have one open paren (the outer one), so we need to find its closing paren
                        outer_end = inner_end
                        outer_paren_count = 1  # We still have one open paren (the outer one)
                        while outer_end < len(fixed_template) and outer_paren_count > 0:
                            if fixed_template[outer_end] == '(':
                                outer_paren_count += 1
                            elif fixed_template[outer_end] == ')':
                                outer_paren_count -= 1
                            if outer_paren_count > 0:
                                outer_end += 1
                            else:
                                # Found the matching closing paren, include it in outer_end
                                outer_end += 1
                                break
                        
                        # Now replace: operator(operator(inner_content)) with operator(inner_content)
                        replacement = match.group(1) + '(' + inner_content + ')'
                        
                        # Replace the entire nested pattern (from start_pos to outer_end)
                        fixed_template = fixed_template[:start_pos] + replacement + fixed_template[outer_end:]
                        changed = True
                        logger.debug(f"🔧 Deduplicated nested {op_name}: removed one level")
            
            # If no changes were made, we're done
            if not changed:
                break
        
        return fixed_template
    
    def _extract_operators_from_template(self, template: str, available_operators: List[Dict] = None) -> List[str]:
        """Extract operator names used in a template"""
        if not template:
            return []
        
        import re
        
        # Get operator names from available_operators if provided
        operator_names = set()
        if available_operators:
            for op in available_operators:
                name = op.get('name', '')
                if name:
                    operator_names.add(name)
        
        found_operators = []
        
        # Find function-style operators (operator_name(...)
        function_pattern = r'\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\('
        matches = re.finditer(function_pattern, template)
        
        for match in matches:
            function_name = match.group(1)
            # Check if it's a known operator
            if operator_names and function_name in operator_names:
                found_operators.append(function_name)
            elif not operator_names:
                # If we don't have operator list, check common operator patterns
                common_operators = {
                    'ts_rank', 'ts_max', 'ts_min', 'ts_sum', 'ts_mean', 'ts_std_dev', 'ts_skewness', 'ts_kurtosis',
                    'ts_corr', 'ts_regression', 'ts_delta', 'ts_ratio', 'ts_product', 'ts_scale', 'ts_zscore',
                    'ts_lag', 'ts_lead', 'ts_arg_max', 'ts_arg_min', 'ts_step', 'ts_bucket', 'ts_hump',
                    'rank', 'add', 'subtract', 'multiply', 'divide', 'power', 'abs', 'sign', 'sqrt', 'log', 'exp',
                    'max', 'min', 'sum', 'mean', 'std', 'std_dev', 'corr', 'regression', 'delta', 'ratio', 'product', 'scale', 'zscore', 'lag', 'lead',
                    'normalize', 'winsorize', 'signed_power', 'inverse', 'inverse_sqrt',
                    'group_neutralize', 'group_zscore', 'group_rank', 'group_max', 'group_min', 'group_mean', 'group_backfill',
                    'vec_avg', 'vec_sum', 'vec_max', 'vec_min',
                    'if_else', 'greater', 'less', 'greater_equal', 'less_equal', 'equal', 'not_equal',
                    'and', 'or', 'not', 'is_nan', 'is_finite', 'is_infinite', 'fill_na', 'forward_fill',
                    'backward_fill', 'clip', 'clip_lower', 'clip_upper', 'bucket', 'step', 'hump'
                }
                if function_name.startswith('ts_') or function_name in common_operators:
                    found_operators.append(function_name)
        
        return list(set(found_operators))  # Return unique operators