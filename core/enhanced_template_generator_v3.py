"""
Generation Two: Enhanced Template Generator V3
Modular implementation using separate components
"""

import logging
import time
from typing import List, Dict, Optional, Any
import sys
import os

from ..evolution import SelfOptimizer, AlphaQualityMonitor, AlphaEvolutionEngine, AlphaResult, OnTheFlyTester
from .template_generator import TemplateGenerator
from .simulator_tester import SimulatorTester, SimulationSettings, SimulationResult
from ..storage import BacktestStorage, AlphaRegrouper, AlphaRetrospect
from ..ollama import RegionThemeManager, OllamaManager
from ..self_evolution import EvolutionExecutor, CodeGenerator, CodeEvaluator

logger = logging.getLogger(__name__)


class EnhancedTemplateGeneratorV3:
    """
    Generation Two: Modular implementation
    
    Features:
    - Self-optimization of parameters
    - Genetic algorithm-based alpha evolution
    - On-the-fly testing for immediate feedback
    - Quality monitoring over time
    - Modular components for template generation, simulation, storage, regroup, and retrospect
    """
    
    def __init__(
        self, 
        credentials_path: str = None,
        credentials: List[str] = None,  # New: allow passing credentials directly
        deepseek_api_key: str = None,
        db_path: str = "generation_two_backtests.db",
        ollama_url: str = "http://localhost:11434",
        ollama_model: str = "qwen2.5-coder:1.5b"
    ):
        """
        Initialize Generation Two system
        
        Args:
            credentials_path: Path to WorldQuant Brain credentials file
            credentials: Direct credentials as [username, password] (takes precedence over credentials_path)
            deepseek_api_key: DeepSeek API key for template generation
            db_path: Path to backtest storage database
            ollama_url: Ollama server URL
            ollama_model: Ollama model name
        """
        # Initialize modular components with Ollama support
        self.template_generator = TemplateGenerator(
            credentials_path=credentials_path,
            credentials=credentials,  # Pass credentials directly
            deepseek_api_key=deepseek_api_key,
            ollama_url=ollama_url,
            ollama_model=ollama_model,
            db_path=db_path  # Pass database path to template generator
        )
        
        # Theme manager
        self.theme_manager = RegionThemeManager()
        self.backtest_storage = BacktestStorage(db_path)
        self.regrouper = AlphaRegrouper()
        self.retrospect = AlphaRetrospect()
        
        # Setup simulator tester (needs session and region configs)
        import requests
        # Use the same session from template_generator to maintain authentication cookies
        # setup_auth() was already called in TemplateGenerator.__init__, but call again to ensure session is ready
        if credentials_path or credentials:
            self.template_generator.setup_auth()
        self.session = self.template_generator.sess  # Reuse authenticated session
        
        # Region configurations
        self.region_configs = self._get_region_configs()
        # Pass template_generator reference for re-authentication support
        self.simulator_tester = SimulatorTester(self.session, self.region_configs, self.template_generator)
        
        # Generation Two components
        self.self_optimizer = SelfOptimizer()
        self.evolution_engine = AlphaEvolutionEngine()
        self.quality_monitor = AlphaQualityMonitor()
        self.on_the_fly_tester = OnTheFlyTester(self)
        
        # Evolution parameters
        self.evolution_enabled = True
        self.evolution_interval = 50
        self.evolution_count = 0
        
        # Performance tracking
        self.all_results: List[SimulationResult] = []
        self.successful_alphas: List[AlphaResult] = []
        
        logger.info("Generation Two V3 initialized with modular components")
    
    def _get_region_configs(self) -> Dict:
        """Get region configurations with all universes and neutralizations"""
        from dataclasses import dataclass
        from .region_config import get_region_config
        
        @dataclass
        class RegionConfig:
            region: str
            universe: str
            delay: int = 1
            neutralization: str = "INDUSTRY"  # Always risk neutralized
        
        configs = {}
        for region in ['USA', 'EUR', 'CHN', 'ASI', 'GLB', 'IND']:
            try:
                region_cfg = get_region_config(region, delay=1)
                # Use default universe and neutralization
                configs[region] = RegionConfig(
                    region=region,
                    universe=region_cfg.default_universe,
                    delay=1,
                    neutralization=region_cfg.default_neutralization
                )
            except Exception as e:
                logger.warning(f"Failed to load config for {region}, using defaults: {e}")
                # Fallback defaults
                fallback_universes = {
                    'USA': 'TOP3000',
                    'EUR': 'TOP2500',
                    'CHN': 'TOP2000U',
                    'ASI': 'MINVOL1M',
                    'GLB': 'TOP3000',
                    'IND': 'TOP500'
                }
                configs[region] = RegionConfig(
                    region=region,
                    universe=fallback_universes.get(region, 'TOP3000'),
                    delay=1,
                    neutralization='INDUSTRY'
                )
        
        return configs
    
    def generate_alpha_id(self, template: str, region: str) -> str:
        """Generate unique ID for alpha"""
        import hashlib
        combined = f"{template}_{region}"
        return hashlib.md5(combined.encode()).hexdigest()[:16]
    
    def calculate_performance_metrics(self, results: List[SimulationResult]) -> Dict:
        """Calculate performance metrics from results"""
        if len(results) == 0:
            return {
                'success_rate': 0.0,
                'avg_sharpe': 0.0,
                'exploration_rate': 0.3,
                'temperature': 0.7,
                'mutation_rate': 0.1
            }
        
        successful = [r for r in results if r.success]
        success_rate = len(successful) / len(results) if results else 0.0
        
        sharpe_values = [r.sharpe for r in successful if r.sharpe > 0]
        avg_sharpe = sum(sharpe_values) / len(sharpe_values) if sharpe_values else 0.0
        
        return {
            'success_rate': success_rate,
            'avg_sharpe': avg_sharpe,
            'exploration_rate': self.self_optimizer.get_current_parameters()['exploration_rate'],
            'temperature': self.self_optimizer.get_current_parameters()['temperature'],
            'mutation_rate': self.self_optimizer.get_current_parameters()['mutation_rate']
        }
    
    def apply_parameters(self, optimized_params: Dict):
        """Apply optimized parameters to system"""
        if optimized_params:
            logger.info(f"Applying optimized parameters: {optimized_params}")
            if 'mutation_rate' in optimized_params:
                self.evolution_engine.mutation_rate = optimized_params['mutation_rate']
    
    def generate_and_evolve(
        self, 
        regions: List[str] = None,
        templates_per_region: int = 5,
        max_iterations: int = 10
    ):
        """
        Generate templates with evolution
        
        Args:
            regions: List of regions to test
            templates_per_region: Number of templates per region
            max_iterations: Maximum number of iterations
        """
        if regions is None:
            regions = ['USA', 'EUR']
        
        logger.info(
            f"Starting Generation Two evolution: "
            f"{len(regions)} regions, {templates_per_region} templates/region"
        )
        
        iteration = 0
        while iteration < max_iterations:
            iteration += 1
            logger.info(f"=== Iteration {iteration}/{max_iterations} ===")
            
            # Generate templates with theme awareness
            prompts = []
            for region in regions:
                # Check if theme is active
                if self.theme_manager.is_theme_active(region):
                    categories = self.theme_manager.get_required_categories(region)
                    theme_info = f" (Theme active: {', '.join(categories) if categories else 'Special requirements'})"
                else:
                    theme_info = ""
                
                for _ in range(templates_per_region):
                    prompts.append(f"Generate a momentum-based alpha for {region}{theme_info}")
            
            templates = []
            for i, prompt in enumerate(prompts):
                region = regions[i % len(regions)]
                template = self.template_generator.generate_template_from_prompt(
                    prompt,
                    region=region,
                    use_ollama=True  # Smart Ollama with fallback
                )
                if template:
                    templates.append(template)
            
            # Test templates
            new_results = []
            for i, template in enumerate(templates):
                region = regions[i % len(regions)]
                settings = SimulationSettings(region=region, testPeriod="P1Y0M0D")
                
                future = self.simulator_tester.simulate_template_concurrent(
                    template, region, settings
                )
                
                # Wait for result (simplified - in production would be async)
                try:
                    result = future.result(timeout=300)
                    new_results.append(result)
                    
                    # Store result
                    if result.success:
                        self.backtest_storage.store_result(result)
                except Exception as e:
                    logger.error(f"Error getting result: {e}")
            
            self.all_results.extend(new_results)
            
            # Track successful alphas
            for result in new_results:
                if result.success and result.sharpe > 1.25:
                    alpha_result = AlphaResult(
                        template=result.template,
                        sharpe=result.sharpe,
                        fitness=result.fitness,
                        turnover=result.turnover,
                        region=result.region,
                        success=True
                    )
                    self.successful_alphas.append(alpha_result)
            
            # Self-optimization
            if len(self.all_results) % 50 == 0:
                performance = self.calculate_performance_metrics(self.all_results)
                optimized_params = self.self_optimizer.optimize_parameters(performance)
                if optimized_params:
                    self.apply_parameters(optimized_params)
            
            # Evolution
            if self.evolution_enabled and len(self.successful_alphas) >= self.evolution_interval:
                if len(self.successful_alphas) >= 10:
                    if len(self.evolution_engine.population) == 0:
                        self.evolution_engine.initialize_population(self.successful_alphas)
                    else:
                        evolved_expressions = self.evolution_engine.evolve_generation()
                        logger.info(f"Evolved {len(evolved_expressions)} alphas")
                        
                        # Test evolved alphas
                        for expr in evolved_expressions[:5]:
                            for region in regions:
                                self.on_the_fly_tester.test_evolved_alpha(expr, region)
                        
                        self.evolution_count += 1
            
            # Process on-the-fly test results
            self.on_the_fly_tester.process_test_results()
            
            # Quality monitoring
            for result in new_results:
                if result.success:
                    alpha_id = self.generate_alpha_id(result.template, result.region)
                    self.quality_monitor.track_alpha(alpha_id, {
                        'sharpe': result.sharpe,
                        'fitness': result.fitness,
                        'returns': result.returns
                    })
            
            logger.info(
                f"Total results: {len(self.all_results)}, "
                f"Successful: {len(self.successful_alphas)}, "
                f"Evolution cycles: {self.evolution_count}"
            )
            
            time.sleep(2)  # Small delay
        
        return self.all_results
    
    def regroup_results(self, by: str = 'region') -> Dict:
        """
        Regroup results by various criteria
        
        Args:
            by: Criteria ('region', 'sharpe_tier', 'operator', 'performance_metric', 'time_period')
            
        Returns:
            Dictionary of regrouped results
        """
        # Use limit for performance (only get recent results)
        results = self.backtest_storage.get_results(limit=1000)  # Reasonable limit for analysis
        
        if by == 'region':
            return self.regrouper.regroup_by_region(results)
        elif by == 'sharpe_tier':
            return self.regrouper.regroup_by_sharpe_tier(results)
        elif by == 'operator':
            return self.regrouper.regroup_by_operator(results)
        elif by == 'performance_metric':
            return self.regrouper.regroup_by_performance_metric(results, metric='fitness')
        elif by == 'time_period':
            return self.regrouper.regroup_by_time_period(results)
        else:
            return {}
    
    def analyze_retrospect(self) -> Dict:
        """
        Perform retrospective analysis
        
        Returns:
            Dictionary with insights
        """
        # Use limit for performance (only get recent results for insights)
        results = self.backtest_storage.get_results(limit=500)  # Reasonable limit for insights
        return self.retrospect.generate_insights(results)
    
    def get_system_stats(self) -> Dict:
        """Get overall system statistics"""
        stats = {
            'total_results': len(self.all_results),
            'successful_alphas': len(self.successful_alphas),
            'evolution_cycles': self.evolution_count,
            'pending_tests': self.on_the_fly_tester.get_pending_tests_count(),
            'tracked_alphas': len(self.quality_monitor.get_all_alpha_ids()),
            'storage_stats': self.backtest_storage.get_statistics(),
            'ollama_stats': self.template_generator.ollama_manager.get_stats(),
            'active_themes': {
                region: self.theme_manager.is_theme_active(region)
                for region in ['IND', 'ATOM']
            }
        }
        
        if self.evolution_engine.population:
            stats['evolution_stats'] = self.evolution_engine.get_population_stats()
        
        stats['optimization_params'] = self.self_optimizer.get_current_parameters()
        
        return stats
    
    def _integrate_evolved_module(self, module, module_name: str):
        """Integrate an evolved module into the system"""
        logger.info(f"Integrating evolved module: {module_name}")
        # Store module for potential use
        if not hasattr(self, 'evolved_modules'):
            self.evolved_modules = {}
        self.evolved_modules[module_name] = module
    
    def run_self_evolution(self, objectives: List[str], num_modules: int = 3):
        """
        Run a self-evolution cycle
        
        Args:
            objectives: List of evolution objectives
            num_modules: Number of modules to generate
            
        Returns:
            EvolutionCycle result
        """
        return self.evolution_executor.execute_evolution_cycle(objectives, num_modules)