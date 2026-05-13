"""
Mining Coordinator for Continuous Mining
Orchestrates the continuous mining process with 5000 simulation target
"""

import logging
import time
import threading
from typing import List, Dict, Optional, Tuple, Callable
from ..simulation_counter import SimulationCounter
from ..slot_manager import SlotManager
from .correlation_tracker import CorrelationTracker
from .duplicate_detector import MiningDuplicateDetector
from .search_strategy import SearchStrategyManager, SearchStrategy

logger = logging.getLogger(__name__)


class MiningCoordinator:
    """
    Coordinates continuous mining with:
    - 5000 simulation target
    - GLB 2-slot support
    - Low-correlation prioritization
    - Duplicate filtering
    - BFS/DFS strategies
    - Self-sustaining operation
    """
    
    def __init__(
        self,
        db_path: str = "generation_two_backtests.db",
        max_simulations: int = 5000,
        search_strategy: SearchStrategy = SearchStrategy.BFS,
        log_callback: Optional[Callable[[str], None]] = None
    ):
        """
        Initialize mining coordinator
        
        Args:
            db_path: Path to database
            max_simulations: Maximum simulations per day (default: 5000)
            search_strategy: Search strategy to use
            log_callback: Optional callback for logging
        """
        self.db_path = db_path
        self.max_simulations = max_simulations
        self.log_callback = log_callback
        
        # Initialize components
        self.sim_counter = SimulationCounter()
        self.slot_manager = SlotManager(max_slots=8)
        self.correlation_tracker = CorrelationTracker(db_path)
        self.duplicate_detector = MiningDuplicateDetector(db_path)
        self.search_strategy = SearchStrategyManager(search_strategy)
        
        # Mining state
        self.mining_active = False
        self.stop_flag = False
        self.generated_templates_queue: List[Tuple[str, str]] = []  # (template, region)
        self.pending_simulations: List[Tuple[str, str]] = []  # (template, region)
        
        # Statistics
        self.stats = {
            'templates_generated': 0,
            'templates_simulated': 0,
            'simulations_successful': 0,
            'simulations_failed': 0,
            'duplicates_filtered': 0,
            'low_correlation_selected': 0
        }
        
        # Load seen templates into cache
        self.duplicate_detector.load_seen_templates(limit=1000)
    
    def start_mining(
        self,
        generator,
        simulator_tester,
        backtest_storage,
        regions: List[str] = None
    ):
        """
        Start continuous mining
        
        Args:
            generator: Template generator instance
            simulator_tester: Simulator tester instance
            backtest_storage: Backtest storage instance
            regions: List of regions to mine (default: all)
        """
        if self.mining_active:
            logger.warning("Mining already active")
            return
        
        self.mining_active = True
        self.stop_flag = False
        
        # Initialize search strategy
        if regions:
            self.search_strategy.initialize(regions)
        else:
            self.search_strategy.initialize()
        
        # Start mining thread
        mining_thread = threading.Thread(
            target=self._mining_loop,
            args=(generator, simulator_tester, backtest_storage),
            daemon=True,
            name="MiningCoordinator"
        )
        mining_thread.start()
        
        logger.info("✅ Mining coordinator started")
        self._log("🚀 Mining coordinator started")
    
    def stop_mining(self):
        """Stop continuous mining"""
        self.mining_active = False
        self.stop_flag = True
        self._log("⚠️ Stopping mining...")
    
    def _mining_loop(self, generator, simulator_tester, backtest_storage):
        """Main mining loop"""
        try:
            while self.mining_active and not self.stop_flag:
                # Check simulation limit
                if not self.sim_counter.can_simulate():
                    self._log("⚠️ Daily simulation limit reached. Waiting...")
                    time.sleep(3600)  # Check every hour
                    continue
                
                # Get current status
                status = self.sim_counter.get_status()
                remaining = status['remaining']
                
                if remaining <= 0:
                    self._log("⚠️ No simulations remaining for today")
                    time.sleep(3600)
                    continue
                
                # Generate templates if queue is low
                if len(self.generated_templates_queue) < 10:
                    self._generate_templates_batch(generator, batch_size=5)
                
                # Process simulations
                self._process_simulations(simulator_tester, backtest_storage)
                
                # Brief pause
                time.sleep(1)
                
        except Exception as e:
            logger.error(f"Mining loop error: {e}", exc_info=True)
            self._log(f"❌ Mining error: {str(e)}")
        finally:
            self.mining_active = False
            self._log("⏹ Mining coordinator stopped")
    
    def _generate_templates_batch(self, generator, batch_size: int = 5):
        """Generate a batch of templates"""
        try:
            # Get next region from strategy
            region = self.search_strategy.get_next_region()
            if not region:
                return
            
            # Generate templates for this region
            templates_generated = 0
            for _ in range(batch_size):
                if self.stop_flag:
                    break
                
                # Generate template
                try:
                    template = generator.template_generator.ollama_manager.generate_template(
                        prompt=f"Generate a WorldQuant Brain FASTEXPR alpha expression for {region} region.",
                        region=region,
                        available_operators=generator.template_generator.operator_fetcher.operators if generator.template_generator.operator_fetcher else None,
                        available_fields=generator.template_generator.get_data_fields_for_region(region)
                    )
                    
                    if template:
                        template = template.replace('`', '').strip()
                        
                        # Check for duplicates
                        is_dup, reason = self.duplicate_detector.is_duplicate(template, region)
                        if is_dup:
                            self.stats['duplicates_filtered'] += 1
                            self._log(f"⚠️ Duplicate filtered: {reason}")
                            continue
                        
                        # Add to queue
                        self.generated_templates_queue.append((template, region))
                        self.stats['templates_generated'] += 1
                        templates_generated += 1
                        
                except Exception as e:
                    logger.debug(f"Error generating template: {e}")
                    continue
            
            if templates_generated > 0:
                self._log(f"✅ Generated {templates_generated} templates for {region}")
                
        except Exception as e:
            logger.error(f"Error in template generation batch: {e}", exc_info=True)
    
    def _process_simulations(self, simulator_tester, backtest_storage):
        """Process pending simulations"""
        # Select templates for simulation (prioritize low correlation)
        if not self.generated_templates_queue:
            return
        
        # Get low-correlation templates
        candidates = self.generated_templates_queue[:20]  # Check up to 20
        low_corr_templates = self.correlation_tracker.get_low_correlation_templates(
            candidates,
            max_correlation=0.3,
            limit=8  # Match slot count
        )
        
        if low_corr_templates:
            self.stats['low_correlation_selected'] += len(low_corr_templates)
            # Remove selected templates from queue
            selected_templates = [(t, r) for t, r, _ in low_corr_templates]
            for template, region in selected_templates:
                if (template, region) in self.generated_templates_queue:
                    self.generated_templates_queue.remove((template, region))
                    self.pending_simulations.append((template, region))
        else:
            # Fall back to regular selection
            batch = self.generated_templates_queue[:8]
            for template, region in batch:
                self.generated_templates_queue.remove((template, region))
                self.pending_simulations.append((template, region))
        
        # Process simulations (this would be handled by the main mining loop in step6)
        # The coordinator just prepares the queue
    
    def get_stats(self) -> Dict:
        """Get mining statistics"""
        status = self.sim_counter.get_status()
        strategy_info = self.search_strategy.get_strategy_info()
        
        return {
            **self.stats,
            'simulations_remaining': status['remaining'],
            'simulations_used': status['count'],
            'queue_size': len(self.generated_templates_queue),
            'pending_simulations': len(self.pending_simulations),
            'strategy': strategy_info
        }
    
    def _log(self, message: str):
        """Log message"""
        logger.info(message)
        if self.log_callback:
            self.log_callback(message)
