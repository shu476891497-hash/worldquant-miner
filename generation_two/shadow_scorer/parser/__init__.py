"""
WQ Alpha Expression Parser & Evaluation Engine.

Parses WorldQuant Brain alpha expression strings and evaluates them
against panel data (dates × instruments as pd.DataFrame).
"""

from .parser import parse_expression
from .evaluator import evaluate_expression

__all__ = ["parse_expression", "evaluate_expression"]
