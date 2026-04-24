"""
Self-Evolution Engine
Dynamically writes, evaluates, and executes modular code for self-improvement
"""

from .code_generator import CodeGenerator, ModuleTemplate
from .code_evaluator import CodeEvaluator, EvaluationResult
from .evolution_executor import EvolutionExecutor

__all__ = [
    'CodeGenerator',
    'ModuleTemplate',
    'CodeEvaluator',
    'EvaluationResult',
    'EvolutionExecutor'
]
