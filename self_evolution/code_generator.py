"""
Code Generator
Dynamically generates modular code for self-evolution
"""

import logging
import os
import ast
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class ModuleTemplate:
    """Template for generating code modules"""
    name: str
    purpose: str
    imports: List[str]
    functions: List[Dict]  # List of function definitions
    classes: List[Dict]  # List of class definitions
    code_structure: str  # Overall structure description


class CodeGenerator:
    """
    Generates modular Python code dynamically
    
    Can generate:
    - Optimization strategies
    - Evaluation functions
    - Custom algorithms
    - Integration modules
    """
    
    def __init__(self, ollama_manager=None):
        """
        Initialize code generator
        
        Args:
            ollama_manager: OllamaManager for AI-assisted code generation
        """
        self.ollama_manager = ollama_manager
        self.generated_modules = []
        self.module_templates = []
    
    def generate_optimization_strategy(
        self,
        strategy_name: str,
        objective: str,
        constraints: List[str],
        parameters: Dict
    ) -> str:
        """
        Generate an optimization strategy module
        
        Args:
            strategy_name: Name of the strategy
            objective: Objective function description
            constraints: List of constraints
            parameters: Strategy parameters
            
        Returns:
            Generated Python code as string
        """
        code = f'''"""
Auto-generated optimization strategy: {strategy_name}
Generated: {datetime.now().isoformat()}
Objective: {objective}
"""

import numpy as np
from typing import Dict, List, Optional
from dataclasses import dataclass

@dataclass
class StrategyConfig:
    """Configuration for {strategy_name}"""
'''
        
        # Add parameters
        for key, value in parameters.items():
            code += f"    {key}: {type(value).__name__} = {repr(value)}\n"
        
        code += f'''
class {strategy_name}Strategy:
    """
    Optimization strategy: {strategy_name}
    Objective: {objective}
    """
    
    def __init__(self, config: StrategyConfig = None):
        self.config = config or StrategyConfig()
'''
        
        # Add constraints
        if constraints:
            code += "        self.constraints = [\n"
            for constraint in constraints:
                code += f"            '{constraint}',\n"
            code += "        ]\n"
        
        code += f'''
    def optimize(self, data: Dict, current_params: Dict) -> Dict:
        """
        Optimize parameters based on data
        
        Args:
            data: Performance data
            current_params: Current parameters
            
        Returns:
            Optimized parameters
        """
        # TODO: Implement optimization logic
        # This is a template - replace with actual optimization algorithm
        
        optimized = current_params.copy()
        
        # Example: Simple gradient-based optimization
        if 'sharpe' in data and data['sharpe'] > 0:
            # Increase exploration if performance is good
            if 'exploration_rate' in optimized:
                optimized['exploration_rate'] = min(
                    optimized['exploration_rate'] * 1.1,
                    0.9
                )
        
        return optimized
    
    def evaluate(self, params: Dict, results: List[Dict]) -> float:
        """
        Evaluate strategy performance
        
        Args:
            params: Strategy parameters
            results: Historical results
            
        Returns:
            Performance score
        """
        if not results:
            return 0.0
        
        # Calculate average performance
        scores = [r.get('sharpe', 0) for r in results if r.get('success', False)]
        return sum(scores) / len(scores) if scores else 0.0
'''
        
        return code
    
    def generate_evaluation_function(
        self,
        function_name: str,
        criteria: List[str],
        weights: Dict[str, float]
    ) -> str:
        """
        Generate an evaluation function
        
        Args:
            function_name: Name of the function
            criteria: List of evaluation criteria
            weights: Weights for each criterion
            
        Returns:
            Generated Python code
        """
        code = f'''"""
Auto-generated evaluation function: {function_name}
Generated: {datetime.now().isoformat()}
"""

def {function_name}(result: Dict) -> float:
    """
    Evaluate a result based on multiple criteria
    
    Args:
        result: Result dictionary with metrics
        
    Returns:
        Evaluation score (0-1)
    """
    scores = {{}}
'''
        
        # Add criteria evaluation
        for criterion in criteria:
            code += f'''
    # Evaluate: {criterion}
    if '{criterion}' in result:
        scores['{criterion}'] = min(result['{criterion}'] / 2.0, 1.0)  # Normalize to 0-1
    else:
        scores['{criterion}'] = 0.0
'''
        
        code += "\n    # Weighted sum\n    total_score = 0.0\n"
        for criterion, weight in weights.items():
            code += f"    total_score += scores.get('{criterion}', 0.0) * {weight}\n"
        
        code += "\n    return min(total_score, 1.0)\n"
        
        return code
    
    def generate_with_ollama(
        self,
        prompt: str,
        module_type: str = "strategy"
    ) -> Optional[str]:
        """
        Generate code using Ollama
        
        Args:
            prompt: Description of what to generate
            module_type: Type of module (strategy, evaluator, etc.)
            
        Returns:
            Generated code or None
        """
        if not self.ollama_manager or not self.ollama_manager.is_available:
            logger.warning("Ollama not available for code generation")
            return None
        
        system_prompt = """You are an expert Python developer specializing in quantitative finance and optimization.
Generate clean, modular Python code following best practices.
Return only the code, no explanations."""
        
        user_prompt = f"""Generate a Python {module_type} module with the following requirements:

{prompt}

Requirements:
- Use type hints
- Include docstrings
- Follow PEP 8 style
- Make it modular and reusable
- Include error handling

Return only the Python code:"""
        
        code = self.ollama_manager.generate(user_prompt, system_prompt, temperature=0.3, max_tokens=1000)
        
        if code:
            # Validate syntax
            try:
                ast.parse(code)
                logger.info(f"Generated valid {module_type} code")
                return code
            except SyntaxError as e:
                logger.error(f"Generated code has syntax errors: {e}")
                return None
        
        return None
    
    def save_module(self, code: str, module_name: str, output_dir: str = "generated_modules"):
        """
        Save generated module to file
        
        Args:
            code: Generated code
            module_name: Name of the module
            output_dir: Output directory
        """
        os.makedirs(output_dir, exist_ok=True)
        
        file_path = os.path.join(output_dir, f"{module_name}.py")
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(code)
        
        logger.info(f"Saved generated module: {file_path}")
        self.generated_modules.append(file_path)
        
        return file_path
    
    def validate_code(self, code: str) -> tuple[bool, Optional[str]]:
        """
        Validate generated code
        
        Args:
            code: Code to validate
            
        Returns:
            (is_valid, error_message)
        """
        try:
            ast.parse(code)
            return True, None
        except SyntaxError as e:
            return False, str(e)
