"""
Evolution Executor
Executes and manages self-evolution cycles
"""

import logging
import time
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass
from datetime import datetime

from .code_generator import CodeGenerator
from .code_evaluator import CodeEvaluator, EvaluationResult

logger = logging.getLogger(__name__)


@dataclass
class EvolutionCycle:
    """A single evolution cycle"""
    cycle_id: int
    timestamp: float
    generated_modules: List[str]
    evaluated_modules: List[EvaluationResult]
    best_module: Optional[str] = None
    improvement_score: float = 0.0


class EvolutionExecutor:
    """
    Executes self-evolution cycles
    
    Manages:
    - Code generation
    - Evaluation
    - Selection of best modules
    - Integration into system
    """
    
    def __init__(
        self,
        code_generator: CodeGenerator,
        code_evaluator: CodeEvaluator,
        integration_callback: Optional[Callable] = None
    ):
        """
        Initialize evolution executor
        
        Args:
            code_generator: CodeGenerator instance
            code_evaluator: CodeEvaluator instance
            integration_callback: Callback to integrate successful modules
        """
        self.code_generator = code_generator
        self.code_evaluator = code_evaluator
        self.integration_callback = integration_callback
        
        self.evolution_history: List[EvolutionCycle] = []
        self.active_modules: Dict[str, Any] = {}
        self.cycle_count = 0
    
    def execute_evolution_cycle(
        self,
        objectives: List[str],
        num_modules: int = 3
    ) -> EvolutionCycle:
        """
        Execute a single evolution cycle
        
        Args:
            objectives: List of objectives for code generation
            num_modules: Number of modules to generate
            
        Returns:
            EvolutionCycle result
        """
        self.cycle_count += 1
        cycle = EvolutionCycle(
            cycle_id=self.cycle_count,
            timestamp=time.time(),
            generated_modules=[],
            evaluated_modules=[]
        )
        
        logger.info(f"Starting evolution cycle {self.cycle_count}")
        
        # 1. Generate modules
        for i, objective in enumerate(objectives[:num_modules]):
            logger.info(f"Generating module {i+1}/{num_modules} for: {objective}")
            
            # Generate code
            if self.code_generator.ollama_manager:
                code = self.code_generator.generate_with_ollama(
                    f"Create an optimization strategy: {objective}",
                    module_type="strategy"
                )
            else:
                code = self.code_generator.generate_optimization_strategy(
                    strategy_name=f"Strategy_{self.cycle_count}_{i}",
                    objective=objective,
                    constraints=[],
                    parameters={'learning_rate': 0.01, 'exploration': 0.1}
                )
            
            if code:
                module_name = f"evolved_{self.cycle_count}_{i}"
                module_path = self.code_generator.save_module(code, module_name)
                cycle.generated_modules.append(module_path)
        
        # 2. Evaluate modules
        for module_path in cycle.generated_modules:
            with open(module_path, 'r') as f:
                code = f.read()
            
            result = self.code_evaluator.evaluate_module(
                code,
                os.path.basename(module_path).replace('.py', '')
            )
            
            cycle.evaluated_modules.append(result)
            
            if result.success:
                logger.info(f"Module {module_path} evaluated successfully")
            else:
                logger.warning(f"Module {module_path} failed: {result.error_message}")
        
        # 3. Select best module
        successful = [r for r in cycle.evaluated_modules if r.success]
        if successful:
            best = max(successful, key=lambda r: r.performance_score + r.safety_score)
            cycle.best_module = best.module_name
            cycle.improvement_score = best.performance_score + best.safety_score
            
            logger.info(f"Best module: {best.module_name} (score: {cycle.improvement_score:.3f})")
            
            # 4. Integrate best module
            if self.integration_callback and best.success:
                try:
                    module = self.code_evaluator.load_module(
                        cycle.generated_modules[successful.index(best)]
                    )
                    if module:
                        self.integration_callback(module, best.module_name)
                        self.active_modules[best.module_name] = module
                except Exception as e:
                    logger.error(f"Error integrating module: {e}")
        
        self.evolution_history.append(cycle)
        
        return cycle
    
    def get_evolution_stats(self) -> Dict:
        """Get evolution statistics"""
        if not self.evolution_history:
            return {}
        
        total_cycles = len(self.evolution_history)
        total_modules = sum(len(c.generated_modules) for c in self.evolution_history)
        successful_modules = sum(
            len([r for r in c.evaluated_modules if r.success])
            for c in self.evolution_history
        )
        
        avg_improvement = sum(c.improvement_score for c in self.evolution_history) / total_cycles
        
        return {
            'total_cycles': total_cycles,
            'total_modules_generated': total_modules,
            'successful_modules': successful_modules,
            'success_rate': successful_modules / total_modules if total_modules > 0 else 0.0,
            'avg_improvement_score': avg_improvement,
            'active_modules': len(self.active_modules)
        }
