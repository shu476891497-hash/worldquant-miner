"""
Step 6: Continuous Alpha Mining
Handles continuous mining that combines generation and simulation
Uses modular components for maintainability
"""

import tkinter as tk
from tkinter import messagebox
import logging
import time
import threading

from generation_two.gui.theme import COLORS
from .step6_mining_modules import MiningUI, MiningEngine
from generation_two.core.mining import CorrelationTracker, MiningDuplicateDetector, SearchStrategyManager, SearchStrategy
from generation_two.core.simulation_counter import SimulationCounter
from generation_two.core.slot_manager import SlotManager
from generation_two.core.simulator_tester import SimulationSettings
from generation_two.core.region_config import REGION_DEFAULT_UNIVERSE, REGION_DEFAULT_NEUTRALIZATION

logger = logging.getLogger(__name__)


class Step6Mining:
    """Step 6: Continuous Alpha Mining"""
    
    def __init__(self, parent_frame, workflow_panel):
        """
        Initialize Step 6
        
        Args:
            parent_frame: Parent frame to pack into
            workflow_panel: Reference to main WorkflowPanel for callbacks
        """
        self.parent_frame = parent_frame
        self.workflow = workflow_panel
        
        # Initialize UI module
        self.ui = MiningUI(parent_frame)
        self.frame = self.ui.frame
        
        # Mining state
        self.mining_active = False
        self.stop_mining_flag = False
        self.mining_thread = None
        self.mining_engine = None
        
        # Core components
        self.mining_slot_manager = None
        self.sim_counter = None
        self.correlation_tracker = None
        self.duplicate_detector = None
        self.search_strategy = None
        
        # Regions
        self.mining_regions = ['USA', 'EUR', 'CHN', 'ASI', 'GLB', 'IND']
        
        # Hook up UI callbacks
        self.ui.start_mining_button.config(command=self._start_continuous_mining)
        self.ui.stop_mining_button.config(command=self._stop_continuous_mining)
    
    def _start_continuous_mining(self):
        """Start continuous alpha mining across all regions"""
        if not self.workflow.generator or not self.workflow.generator.template_generator:
            messagebox.showerror("Error", "Generator not initialized")
            return
        
        # Check authentication
        if not self.workflow.generator.template_generator.sess or not self.workflow.generator.template_generator.sess.cookies:
            messagebox.showerror("Error", "Not authenticated. Please complete Step 1 first.")
            return
        
        # Navigate to Step 6 if not already there
        if self.workflow.current_step != 5:  # Step 6 is index 5
            self.workflow._show_step(5)
        
        self.mining_active = True
        self.stop_mining_flag = False
        self.ui.start_mining_button.config(state=tk.DISABLED)
        self.ui.stop_mining_button.config(state=tk.NORMAL)
        self.ui.mining_log.delete(1.0, tk.END)
        self._log_mining("🚀 STARTING CONTINUOUS MINING\n")
        self._log_mining("=" * 80 + "\n")
        
        # Initialize core components
        self.sim_counter = SimulationCounter()
        self.mining_slot_manager = SlotManager(max_slots=8)
        self.correlation_tracker = CorrelationTracker()
        self.duplicate_detector = MiningDuplicateDetector()
        self.search_strategy = SearchStrategyManager(SearchStrategy.BFS)  # Can be changed to DFS
        
        # Load seen templates
        self.duplicate_detector.load_seen_templates(limit=1000)
        
        # Initialize search strategy
        self.search_strategy.initialize(self.mining_regions)
        
        # Update UI
        self._update_sim_counter_display()
        self.ui.mining_status_label.config(text="Status: Starting...", fg=COLORS['accent_yellow'])
        
        # Initialize mining engine
        self.mining_engine = MiningEngine(
            generator=self.workflow.generator,
            simulator_tester=self.workflow.generator.simulator_tester,
            backtest_storage=self.workflow.generator.backtest_storage,
            slot_manager=self.mining_slot_manager,
            correlation_tracker=self.correlation_tracker,
            duplicate_detector=self.duplicate_detector,
            search_strategy_manager=self.search_strategy,
            sim_counter=self.sim_counter,
            log_callback=self._log_mining,
            update_slot_callback=self._update_mining_slot_display
        )
        
        # Start mining engine
        self.mining_engine.start()
        
        # Start slot update thread
        self._start_slot_update_thread()
        
        logger.info("✅ Continuous mining started with modular components")
    
    def _stop_continuous_mining(self):
        """Stop continuous mining"""
        self.mining_active = False
        self.stop_mining_flag = True
        
        if self.mining_engine:
            self.mining_engine.stop()
        
        self.ui.mining_status_label.config(text="Status: Stopping...", fg=COLORS['accent_yellow'])
        self.ui.start_mining_button.config(state=tk.NORMAL)
        self.ui.stop_mining_button.config(state=tk.DISABLED)
        self._log_mining("⚠️ Stopping mining...\n")
    
    def _update_sim_counter_display(self):
        """Update simulation counter display"""
        if hasattr(self, 'sim_counter') and self.sim_counter:
            status = self.sim_counter.get_status()
            self.workflow.frame.after(0, lambda: self.ui.sim_counter_label.config(
                text=f"Today's Simulations: {status['count']} / {status['limit']} (EST) - "
                     f"{status['remaining']} remaining"
            ))
    
    def _update_mining_slot_display(self, slot_id, status, template, region_info, progress, message, logs=None):
        """Update mining slot display - delegates to UI module"""
        self.workflow.frame.after(0, lambda: self.ui.update_slot_display(
            slot_id, status, template, region_info, progress, message, logs
        ))
    
    def _start_slot_update_thread(self):
        """Start thread to periodically update slot displays"""
        def update_slots():
            from generation_two.core.slot_manager import SlotStatus
            while self.mining_active and not self.stop_mining_flag:
                try:
                    if self.mining_slot_manager:
                        for slot_id in range(8):
                            slot = self.mining_slot_manager.get_slot_status(slot_id)
                            if slot.status != SlotStatus.IDLE:
                                logs = slot.get_logs()[-50:] if len(slot.get_logs()) > 50 else slot.get_logs()
                                self._update_mining_slot_display(
                                    slot_id,
                                    slot.status.value.upper(),
                                    slot.template[:40] + "..." if slot.template else "",
                                    f"Region: {slot.region}" if slot.region else "",
                                    slot.progress_percent,
                                    slot.progress_message,
                                    logs
                                )
                    time.sleep(2)  # Update every 2 seconds
                except Exception as e:
                    logger.debug(f"Slot update error: {e}")
                    time.sleep(1)
        
        thread = threading.Thread(target=update_slots, daemon=True, name="SlotUpdater")
        thread.start()
    
    def _log_mining(self, message):
        """Log message to mining log"""
        self.workflow.frame.after(0, lambda: self.ui.log_message(message))
