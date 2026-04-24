"""
Mining Engine Module
Core mining logic with self-sustaining operation
"""

import logging
import time
import threading
from typing import Optional, Callable
from generation_two.core.mining import MiningCoordinator, SearchStrategy
from generation_two.core.slot_manager import SlotManager, SlotStatus
from generation_two.core.simulator_tester import SimulatorTester, SimulationSettings
from generation_two.core.region_config import REGION_DEFAULT_UNIVERSE, REGION_DEFAULT_NEUTRALIZATION

logger = logging.getLogger(__name__)


class MiningEngine:
    """
    Core mining engine with self-sustaining operation
    Handles generation, simulation, and error recovery
    """
    
    def __init__(
        self,
        generator,
        simulator_tester,
        backtest_storage,
        slot_manager: SlotManager,
        correlation_tracker,
        duplicate_detector,
        search_strategy_manager,
        sim_counter,
        log_callback: Optional[Callable[[str], None]] = None,
        update_slot_callback: Optional[Callable] = None
    ):
        """
        Initialize mining engine
        
        Args:
            generator: Template generator
            simulator_tester: Simulator tester
            backtest_storage: Backtest storage
            slot_manager: Slot manager
            correlation_tracker: Correlation tracker
            duplicate_detector: Duplicate detector
            search_strategy_manager: Search strategy manager
            sim_counter: Simulation counter
            log_callback: Log callback
            update_slot_callback: Slot update callback
        """
        self.generator = generator
        self.simulator_tester = simulator_tester
        self.backtest_storage = backtest_storage
        self.slot_manager = slot_manager
        self.correlation_tracker = correlation_tracker
        self.duplicate_detector = duplicate_detector
        self.search_strategy = search_strategy_manager
        self.sim_counter = sim_counter
        self.log_callback = log_callback
        self.update_slot_callback = update_slot_callback
        
        self.mining_active = False
        self.stop_flag = False
        self.generated_templates_queue = []
        self.error_recovery_count = 0
        self.max_error_recovery = 10  # Max consecutive errors before pause
        
        # Long-term operation: memory management
        self.max_queue_size = 100  # Max templates in queue
        self.cleanup_interval = 3600  # Cleanup every hour
        self.last_cleanup_time = time.time()
        self.operation_start_time = time.time()
        self.templates_generated_count = 0
        self.simulations_completed_count = 0
    
    def start(self):
        """Start mining engine"""
        if self.mining_active:
            return
        
        self.mining_active = True
        self.stop_flag = False
        self.error_recovery_count = 0
        
        # Start main loop
        thread = threading.Thread(target=self._main_loop, daemon=True, name="MiningEngine")
        thread.start()
        
        self._log("✅ Mining engine started")
    
    def stop(self):
        """Stop mining engine"""
        self.mining_active = False
        self.stop_flag = True
        self._log("⏹ Mining engine stopping...")
    
    def _main_loop(self):
        """Main mining loop with error recovery and long-term operation support"""
        while self.mining_active and not self.stop_flag:
            try:
                # Periodic cleanup for long-term operation
                current_time = time.time()
                if current_time - self.last_cleanup_time > self.cleanup_interval:
                    self._periodic_cleanup()
                    self.last_cleanup_time = current_time
                
                # Check simulation limit
                if not self.sim_counter.can_simulate():
                    self._log("⚠️ Daily simulation limit reached. Waiting...")
                    time.sleep(3600)
                    continue
                
                # Process simulations (now handles generation internally with 20/80 logic)
                self._process_simulations()
                
                # Reset error recovery on success
                self.error_recovery_count = 0
                
                time.sleep(1)
                
            except Exception as e:
                self.error_recovery_count += 1
                logger.error(f"Mining engine error (recovery {self.error_recovery_count}): {e}", exc_info=True)
                self._log(f"❌ Error: {str(e)[:100]} (recovery {self.error_recovery_count}/{self.max_error_recovery})")
                
                # Exponential backoff for long-term stability
                backoff_time = min(5 * (2 ** min(self.error_recovery_count, 5)), 300)  # Max 5 minutes
                
                if self.error_recovery_count >= self.max_error_recovery:
                    self._log(f"⚠️ Too many errors, pausing for {backoff_time} seconds...")
                    time.sleep(backoff_time)
                    self.error_recovery_count = 0
                else:
                    time.sleep(backoff_time)
    
    def _generate_new_template_for_mining(self) -> tuple:
        """
        Generate a new placeholder template that's different from database
        
        Returns:
            (template, region) tuple or (None, None) if failed
        """
        try:
            region = self.search_strategy.get_next_region()
            if not region:
                return (None, None)
            
            # Use algorithmic generation (like Step 4) - generates placeholders
            from generation_two.core.algorithmic_template_generator import AlgorithmicTemplateGenerator
            
            available_operators = self.generator.template_generator.operator_fetcher.operators if self.generator.template_generator.operator_fetcher else None
            available_fields = self.generator.template_generator.get_data_fields_for_region(region)
            
            if not available_operators or not available_fields:
                logger.warning(f"No operators or fields available for {region}")
                return (None, None)
            
            # Generate placeholder template algorithmically
            generator = AlgorithmicTemplateGenerator(available_operators, available_fields)
            
            # Try up to 10 times to generate a template different from database
            max_retries = 10
            for retry in range(max_retries):
                template_with_placeholders = generator.generate_placeholder_expression(
                    max_operators=5,
                    method='random'  # Can be 'random', 'brownian', 'tree', 'linear'
                )
                
                if not template_with_placeholders:
                    continue
                
                # Check if different from database
                if self.backtest_storage:
                    existing_templates = self.backtest_storage.get_all_templates(region=region, limit=1000)
                    if template_with_placeholders not in existing_templates:
                        # Check duplicates
                        is_dup, reason = self.duplicate_detector.is_duplicate(template_with_placeholders, region)
                        if not is_dup:
                            # Store in database
                            from generation_two.core import template_similarity
                            similarity_checker = template_similarity.TemplateSimilarityChecker()
                            operators_used = list(similarity_checker.extract_operators(template_with_placeholders))
                            fields_used = list(similarity_checker.extract_fields(template_with_placeholders))
                            
                            self.backtest_storage.store_template(
                                template=template_with_placeholders,
                                region=region,
                                operators_used=operators_used,
                                fields_used=fields_used
                            )
                            
                            self.templates_generated_count += 1
                            return (template_with_placeholders, region)
                    else:
                        logger.debug(f"Generated template already exists in database, retrying...")
                else:
                    # No database, just check duplicates
                    is_dup, reason = self.duplicate_detector.is_duplicate(template_with_placeholders, region)
                    if not is_dup:
                        self.templates_generated_count += 1
                        return (template_with_placeholders, region)
            
            logger.debug(f"Could not generate unique template after {max_retries} retries")
            return (None, None)
                    
        except Exception as e:
            logger.debug(f"Error generating template: {e}")
            return (None, None)
    
    def _pick_unsimulated_template_from_db(self) -> tuple:
        """
        Pick a random unsimulated template from database
        
        Returns:
            (template, region) tuple or (None, None) if none available
        """
        try:
            if not self.backtest_storage:
                return (None, None)
            
            # Get unsimulated templates from all regions or specific region
            region = self.search_strategy.get_next_region()
            unsimulated = self.backtest_storage.get_unsimulated_templates(region=region, limit=200)
            
            if not unsimulated:
                # Try all regions if specific region has none
                if region:
                    unsimulated = self.backtest_storage.get_unsimulated_templates(region=None, limit=200)
            
            if unsimulated:
                import random
                # Filter out templates currently being simulated (check slot manager)
                available_templates = []
                for template, template_region in unsimulated:
                    # Check if this template is currently in any slot
                    is_in_use = False
                    for slot_id in range(8):
                        slot = self.slot_manager.get_slot_status(slot_id)
                        if slot and slot.template == template and slot.region == template_region:
                            is_in_use = True
                            break
                    
                    if not is_in_use:
                        # Double-check it hasn't been simulated (race condition protection)
                        if not self.backtest_storage.has_been_simulated(template, template_region):
                            available_templates.append((template, template_region))
                
                if available_templates:
                    template, template_region = random.choice(available_templates)
                    return (template, template_region)
            
            return (None, None)
            
        except Exception as e:
            logger.debug(f"Error picking unsimulated template: {e}")
            return (None, None)
    
    def _generate_templates_batch(self, batch_size: int = 5):
        """Generate a batch of templates using algorithmic generation with placeholders (legacy method, kept for compatibility)"""
        # This method is now mostly unused since we generate on-demand in _process_simulations
        # But keeping it for backward compatibility
        pass
    
    def _process_simulations(self):
        """Process pending simulations with 20/80 logic: 20% new generation, 80% reuse from database"""
        import random
        
        # Determine how many slots we need to fill (up to 8)
        available_slots = 8 - len([s for s in range(8) if self.slot_manager.get_slot_status(s).status != SlotStatus.IDLE])
        if available_slots <= 0:
            return
        
        selected_templates = []
        
        # 20% chance to generate new, 80% chance to reuse from database
        for _ in range(available_slots):
            if self.stop_flag:
                break
            
            # 20% chance: Generate new placeholder template
            if random.random() < 0.2:
                template, region = self._generate_new_template_for_mining()
                if template and region:
                    selected_templates.append((template, region))
                    self._log(f"🆕 Generated new template for {region}")
            else:
                # 80% chance: Pick unsimulated template from database
                template, region = self._pick_unsimulated_template_from_db()
                if template and region:
                    selected_templates.append((template, region))
                    self._log(f"♻️ Reusing unsimulated template for {region}")
                else:
                    # Fallback: Generate new if no unsimulated templates available
                    template, region = self._generate_new_template_for_mining()
                    if template and region:
                        selected_templates.append((template, region))
                        self._log(f"🆕 Fallback: Generated new template for {region}")
        
        if not selected_templates:
            return
        
        # Select low-correlation templates from selected batch
        if len(selected_templates) > 1:
            low_corr_templates = self.correlation_tracker.get_low_correlation_templates(
                selected_templates,
                max_correlation=0.3,
                limit=len(selected_templates)
            )
            if low_corr_templates:
                selected_templates = [(t, r) for t, r, _ in low_corr_templates]
        
        # Submit simulations
        for template, region in selected_templates:
            if self.stop_flag:
                break
            
            # Check simulation limit
            status = self.sim_counter.increment_count()
            if not status['can_simulate']:
                self._log("⚠️ Daily simulation limit reached")
                break
            
            # Assign slot (GLB uses 2 slots)
            slot_count = 2 if region == 'GLB' else 1
            slot_ids = self.slot_manager.find_available_slots(slot_count)
            
            if not slot_ids:
                # Wait for slots
                wait_count = 0
                while wait_count < 10 and not self.stop_flag:
                    time.sleep(2)
                    wait_count += 1
                    slot_ids = self.slot_manager.find_available_slots(slot_count)
                    if slot_ids:
                        break
                
                if not slot_ids:
                    self._log(f"⚠️ No slots available for {region}")
                    continue
            
            # Assign slots
            assigned_slots = self.slot_manager.assign_slot(template, region, 0)
            if not assigned_slots:
                continue
            
            # Start simulation in thread
            for slot_id in assigned_slots:
                thread = threading.Thread(
                    target=self._run_simulation,
                    args=(slot_id, template, region),
                    daemon=True
                )
                thread.start()
            
            time.sleep(0.5)  # Brief pause between submissions
    
    def _run_simulation(self, slot_id: int, template: str, region: str):
        """Run a single simulation with placeholder replacement"""
        try:
            # Replace placeholders using Ollama selection (like Step 5)
            template_with_placeholders = template
            if self.generator and self.generator.template_generator:
                available_operators = None
                if hasattr(self.generator.template_generator, 'operator_fetcher'):
                    available_operators = self.generator.template_generator.operator_fetcher.operators if self.generator.template_generator.operator_fetcher else None
                
                available_fields = self.generator.template_generator.get_data_fields_for_region(region)
                
                # Check if template has placeholders
                has_operator_placeholders = template and ('OPERATOR' in template.upper() or 'operator' in template.lower())
                has_field_placeholders = template and ('DATA_FIELD' in template.upper() or 'data_field' in template.lower())
                
                if (has_operator_placeholders or has_field_placeholders) and available_operators and available_fields:
                    slot = self.slot_manager.get_slot_status(slot_id)
                    if slot:
                        slot.add_log("🤖 Asking Ollama to select operators and fields...")
                    
                    def progress_callback(msg):
                        slot = self.slot_manager.get_slot_status(slot_id)
                        if slot:
                            slot.add_log(f"🤖 {msg}")
                    
                    # Use Ollama to select and replace
                    if hasattr(self.generator.template_generator, 'ollama_manager'):
                        # Get backtest_storage for field usage tracking
                        backtest_storage = None
                        if hasattr(self.generator, 'backtest_storage'):
                            backtest_storage = self.generator.backtest_storage
                        
                        replaced = self.generator.template_generator.ollama_manager.replace_placeholders_with_selection(
                            template,
                            available_operators,
                            available_fields,
                            progress_callback=progress_callback,
                            region=region,
                            backtest_storage=backtest_storage
                        )
                        if replaced:
                            template = replaced
                            # Verify all placeholders were actually replaced
                            import re
                            remaining_ops = re.findall(r'\b(OPERATOR\d+|operator\d+|Operator\d+)\b', template, re.IGNORECASE)
                            remaining_fields = re.findall(r'\b(DATA_FIELD\d+|data_field\d+|Data_Field\d+)\b', template, re.IGNORECASE)
                            
                            if remaining_ops or remaining_fields:
                                slot = self.slot_manager.get_slot_status(slot_id)
                                if slot:
                                    slot.add_log(f"⚠️ Some placeholders not replaced! Remaining: {remaining_ops + remaining_fields}")
                                    slot.add_log("🔄 Retrying placeholder replacement...")
                                # Retry once more
                                # Get backtest_storage for field usage tracking
                                backtest_storage = None
                                if hasattr(self.generator, 'backtest_storage'):
                                    backtest_storage = self.generator.backtest_storage
                                
                                replaced_retry = self.generator.template_generator.ollama_manager.replace_placeholders_with_selection(
                                    template,
                                    available_operators,
                                    available_fields,
                                    progress_callback=progress_callback,
                                    region=region,
                                    backtest_storage=backtest_storage
                                )
                                if replaced_retry:
                                    template = replaced_retry
                                    # Check again
                                    remaining_ops = re.findall(r'\b(OPERATOR\d+|operator\d+|Operator\d+)\b', template, re.IGNORECASE)
                                    remaining_fields = re.findall(r'\b(DATA_FIELD\d+|data_field\d+|Data_Field\d+)\b', template, re.IGNORECASE)
                                    if remaining_ops or remaining_fields:
                                        slot = self.slot_manager.get_slot_status(slot_id)
                                        if slot:
                                            slot.add_log(f"❌ FAILED: Still has placeholders after retry: {remaining_ops + remaining_fields}")
                                            slot.add_log(f"❌ Skipping submission - template: {template[:100]}...")
                                        self.slot_manager.release_slot(slot_id, success=False, error=f"Placeholders not replaced: {remaining_ops + remaining_fields}")
                                        return
                                    else:
                                        slot = self.slot_manager.get_slot_status(slot_id)
                                        if slot:
                                            slot.add_log("✅ All placeholders replaced after retry")
                                else:
                                    slot = self.slot_manager.get_slot_status(slot_id)
                                    if slot:
                                        slot.add_log("❌ Retry replacement failed, skipping submission")
                                    self.slot_manager.release_slot(slot_id, success=False, error="Placeholder replacement failed")
                                    return
                            else:
                                slot = self.slot_manager.get_slot_status(slot_id)
                                if slot:
                                    slot.add_log("✅ Ollama selection completed, all placeholders replaced")
                        else:
                            slot = self.slot_manager.get_slot_status(slot_id)
                            if slot:
                                slot.add_log("⚠️ Ollama selection failed, using fallback replacement")
                            # Fallback to old method
                            if has_operator_placeholders:
                                template = self.generator.template_generator._replace_operator_placeholders(
                                    template, available_operators
                                )
                            if has_field_placeholders:
                                template = self.generator.template_generator._replace_field_placeholders(
                                    template, available_fields, region
                                )
                            # Verify fallback worked
                            import re
                            remaining_ops = re.findall(r'\b(OPERATOR\d+|operator\d+|Operator\d+)\b', template, re.IGNORECASE)
                            remaining_fields = re.findall(r'\b(DATA_FIELD\d+|data_field\d+|Data_Field\d+)\b', template, re.IGNORECASE)
                            if remaining_ops or remaining_fields:
                                slot = self.slot_manager.get_slot_status(slot_id)
                                if slot:
                                    slot.add_log(f"❌ FAILED: Fallback replacement incomplete. Remaining: {remaining_ops + remaining_fields}")
                                self.slot_manager.release_slot(slot_id, success=False, error=f"Placeholders not replaced: {remaining_ops + remaining_fields}")
                                return
                    else:
                        # Fallback to old method
                        if has_operator_placeholders:
                            template = self.generator.template_generator._replace_operator_placeholders(
                                template, available_operators
                            )
                        if has_field_placeholders:
                            template = self.generator.template_generator._replace_field_placeholders(
                                template, available_fields, region
                            )
                        # Verify fallback worked
                        import re
                        remaining_ops = re.findall(r'\b(OPERATOR\d+|operator\d+|Operator\d+)\b', template, re.IGNORECASE)
                        remaining_fields = re.findall(r'\b(DATA_FIELD\d+|data_field\d+|Data_Field\d+)\b', template, re.IGNORECASE)
                        if remaining_ops or remaining_fields:
                            slot = self.slot_manager.get_slot_status(slot_id)
                            if slot:
                                slot.add_log(f"❌ FAILED: Fallback replacement incomplete. Remaining: {remaining_ops + remaining_fields}")
                            self.slot_manager.release_slot(slot_id, success=False, error=f"Placeholders not replaced: {remaining_ops + remaining_fields}")
                            return
            
            settings = SimulationSettings(
                universe=REGION_DEFAULT_UNIVERSE.get(region, 'TOP3000'),
                neutralization=REGION_DEFAULT_NEUTRALIZATION.get(region, 'INDUSTRY'),
                delay=1,
                testPeriod="P5Y0M0D"
            )
            
            # Final check: Ensure NO placeholders remain before submission
            import re
            remaining_ops = re.findall(r'\b(OPERATOR\d+|operator\d+|Operator\d+)\b', template, re.IGNORECASE)
            remaining_fields = re.findall(r'\b(DATA_FIELD\d+|data_field\d+|Data_Field\d+)\b', template, re.IGNORECASE)
            
            if remaining_ops or remaining_fields:
                slot = self.slot_manager.get_slot_status(slot_id)
                if slot:
                    slot.add_log(f"❌ CRITICAL: Template still has placeholders before submission!")
                    slot.add_log(f"   Remaining operators: {remaining_ops}")
                    slot.add_log(f"   Remaining fields: {remaining_fields}")
                    slot.add_log(f"   Template: {template[:100]}...")
                self.slot_manager.release_slot(slot_id, success=False, error=f"Cannot submit: placeholders remain ({remaining_ops + remaining_fields})")
                slot = self.slot_manager.get_slot_status(slot_id)
                if slot:
                    slot.add_log("❌ Skipping submission - template has unreplaced placeholders")
                return
            
            # Update slot
            slot = self.slot_manager.get_slot_status(slot_id)
            if slot:
                slot.add_log(f"[{region}] Submitting...")
            self.slot_manager.update_slot_progress(slot_id, percent=10, message="Submitting...", api_status="PENDING")
            self._update_slot(slot_id, template, region, 10, "Submitting...")

            # Submit
            progress_url = self.simulator_tester.submit_simulation(template, region, settings)
            if not progress_url:
                self.slot_manager.release_slot(slot_id, success=False, error="Failed to submit")
                return
            
            # Monitor
            def progress_callback(percent, message, api_status):
                self.slot_manager.update_slot_progress(slot_id, percent=percent, message=message, api_status=api_status)
                slot = self.slot_manager.get_slot_status(slot_id)
                if slot:
                    slot.add_log(f"[{api_status}] {message}")
                self._update_slot(slot_id, template, region, percent, message)
            
            result = self.simulator_tester.monitor_simulation(
                progress_url, template, region, settings,
                progress_callback=progress_callback
            )
            
            # Handle refeed if failed
            if result and not result.success:
                result = self._handle_refeed(slot_id, template, region, result.error_message, settings)
            
            # Check if result is None (simulation failed completely)
            if result is None:
                self.slot_manager.release_slot(slot_id, success=False, error="Simulation failed")
                self._update_slot(slot_id, template, region, 0, "Simulation failed", "FAILED")
                self._log(f"❌ {region}: Simulation failed (no result)")
                return
            
            # Save result
            if self.backtest_storage:
                self.backtest_storage.store_result(result)
            
            # Update correlation tracker
            if result.success and result.alpha_id:
                self.correlation_tracker.update_template_alpha_mapping(template, str(result.alpha_id))
                self.search_strategy.add_successful_template(template, region)
            
            # Release slot
            self.slot_manager.release_slot(
                slot_id,
                success=result.success,
                result={
                    'sharpe': result.sharpe,
                    'fitness': result.fitness,
                    'alpha_id': str(result.alpha_id) if result.alpha_id else ""
                } if result.success else None,
                error=result.error_message if not result.success else None
            )
            
            # Update display
            status = "SUCCESS" if result.success else "FAILED"
            message = f"Sharpe: {result.sharpe:.2f}" if result.success else (result.error_message[:30] if result.error_message else "Failed")
            self._update_slot(slot_id, template, region, 100 if result.success else 0, message, status)
            
            # Log
            if result.success:
                self.simulations_completed_count += 1
                self._log(f"✅ {region}: Sharpe={result.sharpe:.2f}, Fitness={result.fitness:.2f} (Total: {self.simulations_completed_count})")
            else:
                self._log(f"❌ {region}: {result.error_message[:50] if result.error_message else 'Unknown error'}")
                
        except Exception as e:
            logger.error(f"Simulation error: {e}", exc_info=True)
            self.slot_manager.release_slot(slot_id, success=False, error=str(e))
            self._update_slot(slot_id, template, region, 0, str(e)[:30], "FAILED")
    
    def _handle_refeed(self, slot_id: int, template: str, region: str, error_message: str, settings: SimulationSettings):
        """Handle refeed correction"""
        if not self.generator.template_generator.template_validator:
            return None

        slot = self.slot_manager.get_slot_status(slot_id)
        if slot:
            slot.add_log("🔄 Attempting refeed correction...")
        self._update_slot(slot_id, template, region, 50, "Fixing template...")

        # Check if template still has placeholders - replace them first before refeed
        import re
        has_operator_placeholders = template and ('OPERATOR' in template.upper() or 'operator' in template.lower())
        has_field_placeholders = template and ('DATA_FIELD' in template.upper() or 'data_field' in template.lower())

        if (has_operator_placeholders or has_field_placeholders) and self.generator and self.generator.template_generator:
            slot = self.slot_manager.get_slot_status(slot_id)
            if slot:
                slot.add_log("⚠️ Template still has placeholders, replacing before refeed...")
            available_operators = None
            if hasattr(self.generator.template_generator, 'operator_fetcher'):
                available_operators = self.generator.template_generator.operator_fetcher.operators if self.generator.template_generator.operator_fetcher else None

            available_fields = self.generator.template_generator.get_data_fields_for_region(region)

            if available_operators and available_fields and hasattr(self.generator.template_generator, 'ollama_manager'):
                def progress_callback_refeed(msg):
                    slot = self.slot_manager.get_slot_status(slot_id)
                    if slot:
                        slot.add_log(f"🤖 {msg}")

                # Get backtest_storage for field usage tracking
                backtest_storage = None
                if hasattr(self.generator, 'backtest_storage'):
                    backtest_storage = self.generator.backtest_storage
                
                replaced = self.generator.template_generator.ollama_manager.replace_placeholders_with_selection(
                    template,
                    available_operators,
                    available_fields,
                    progress_callback=progress_callback_refeed,
                    region=region,
                    backtest_storage=backtest_storage
                )
                if replaced:
                    template = replaced
                    slot = self.slot_manager.get_slot_status(slot_id)
                    if slot:
                        slot.add_log("✅ Placeholders replaced before refeed")
                else:
                    slot = self.slot_manager.get_slot_status(slot_id)
                    if slot:
                        slot.add_log("⚠️ Placeholder replacement failed, using fallback")
                    # Fallback to old method
                    if has_operator_placeholders:
                        template = self.generator.template_generator._replace_operator_placeholders(
                            template, available_operators
                        )
                    if has_field_placeholders:
                        template = self.generator.template_generator._replace_field_placeholders(
                            template, available_fields, region
                        )

        # Check if event input error (unlimited retries)
        is_event_input_error = 'does not support event inputs' in error_message.lower()
        max_attempts = 999 if is_event_input_error else 3

        fixed_template, fixes = self.generator.template_generator.template_validator.refeed_with_correction(
            template, error_message, region, max_attempts=max_attempts
        )

        if fixed_template and fixed_template != template:
            # Check if fixed template has placeholders - replace them
            has_op_ph = fixed_template and ('OPERATOR' in fixed_template.upper() or 'operator' in fixed_template.lower())
            has_field_ph = fixed_template and ('DATA_FIELD' in fixed_template.upper() or 'data_field' in fixed_template.lower())

            if (has_op_ph or has_field_ph) and self.generator and self.generator.template_generator:
                available_operators = None
                if hasattr(self.generator.template_generator, 'operator_fetcher'):
                    available_operators = self.generator.template_generator.operator_fetcher.operators if self.generator.template_generator.operator_fetcher else None

                available_fields = self.generator.template_generator.get_data_fields_for_region(region)

                if available_operators and available_fields and hasattr(self.generator.template_generator, 'ollama_manager'):
                    # Get backtest_storage for field usage tracking
                    backtest_storage = None
                    if hasattr(self.generator, 'backtest_storage'):
                        backtest_storage = self.generator.backtest_storage
                    
                    replaced_again = self.generator.template_generator.ollama_manager.replace_placeholders_with_selection(
                        fixed_template,
                        available_operators,
                        available_fields,
                        region=region,
                        backtest_storage=backtest_storage
                    )
                    if replaced_again:
                        fixed_template = replaced_again
                    else:
                        # Fallback
                        if has_op_ph and available_operators:
                            fixed_template = self.generator.template_generator._replace_operator_placeholders(
                                fixed_template, available_operators
                            )
                        if has_field_ph and available_fields:
                            fixed_template = self.generator.template_generator._replace_field_placeholders(
                                fixed_template, available_fields, region
                            )
            
            # Final check: Ensure NO placeholders remain before resubmission
            remaining_ops = re.findall(r'\b(OPERATOR\d+|operator\d+|Operator\d+)\b', fixed_template, re.IGNORECASE)
            remaining_fields = re.findall(r'\b(DATA_FIELD\d+|data_field\d+|Data_Field\d+)\b', fixed_template, re.IGNORECASE)
            
            if remaining_ops or remaining_fields:
                slot = self.slot_manager.get_slot_status(slot_id)
                if slot:
                    slot.add_log(f"❌ CRITICAL: Fixed template still has placeholders! Remaining: {remaining_ops + remaining_fields}")
                return None  # Cannot proceed with placeholders
            
            # Retry with fixed template
            slot = self.slot_manager.get_slot_status(slot_id)
            if slot:
                slot.add_log(f"✅ Fixed with {len(fixes)} corrections, retrying...")
            progress_url = self.simulator_tester.submit_simulation(fixed_template, region, settings)
            
            if progress_url:
                def progress_callback(percent, message, api_status):
                    self.slot_manager.update_slot_progress(slot_id, percent=percent, message=message, api_status=api_status)
                    slot = self.slot_manager.get_slot_status(slot_id)
                    if slot:
                        slot.add_log(f"[{api_status}] {message}")
                    self._update_slot(slot_id, fixed_template, region, percent, message)
                
                result = self.simulator_tester.monitor_simulation(
                    progress_url, fixed_template, region, settings,
                    progress_callback=progress_callback
                )
                return result
        
        return None
    
    def _update_slot(self, slot_id: int, template: str, region: str, progress: float, message: str, status: str = "RUNNING"):
        """Update slot display"""
        if self.update_slot_callback:
            slot = self.slot_manager.get_slot_status(slot_id)
            logs = slot.get_logs()[-5:] if slot else []
            self.update_slot_callback(
                slot_id, status, template[:40] + "..." if len(template) > 40 else template,
                f"Region: {region}", progress, message, logs
            )
    
    def _periodic_cleanup(self):
        """Periodic cleanup for long-term operation"""
        try:
            # Log operation statistics
            uptime_hours = (time.time() - self.operation_start_time) / 3600
            self._log(f"🧹 Cleanup: Uptime={uptime_hours:.1f}h, Generated={self.templates_generated_count}, Completed={self.simulations_completed_count}")
            
            # Trim queue if too large
            if len(self.generated_templates_queue) > self.max_queue_size:
                old_size = len(self.generated_templates_queue)
                self.generated_templates_queue = self.generated_templates_queue[-self.max_queue_size//2:]
                self._log(f"🧹 Trimmed queue from {old_size} to {len(self.generated_templates_queue)} templates")
            
            # Force garbage collection periodically
            import gc
            gc.collect()
            
        except Exception as e:
            logger.debug(f"Cleanup error: {e}")
    
    def _log(self, message: str):
        """Log message"""
        logger.info(message)
        if self.log_callback:
            self.log_callback(message)
