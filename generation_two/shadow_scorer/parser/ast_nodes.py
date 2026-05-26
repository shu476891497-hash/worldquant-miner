"""
AST node types for WQ alpha expressions.

Each node is a frozen dataclass for immutability and easy hashing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ASTNode:
    """Abstract base for all AST nodes."""
    pass


# ---------------------------------------------------------------------------
# Literals
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class NumberLiteral(ASTNode):
    """A numeric constant (int or float)."""
    value: float


@dataclass(frozen=True)
class StringLiteral(ASTNode):
    """A quoted string constant."""
    value: str


@dataclass(frozen=True)
class Identifier(ASTNode):
    """A bare name — could be a data field (close, volume) or a variable."""
    name: str


# ---------------------------------------------------------------------------
# Expressions
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FunctionCall(ASTNode):
    """A function / operator invocation.

    Attributes
    ----------
    name : str
        Operator name (e.g. ``ts_mean``, ``rank``).
    args : tuple[ASTNode, ...]
        Positional arguments.
    kwargs : tuple[tuple[str, ASTNode], ...]
        Keyword arguments as (name, value) pairs.
    """
    name: str
    args: tuple  # tuple[ASTNode, ...]
    kwargs: tuple = ()  # tuple[tuple[str, ASTNode], ...]


@dataclass(frozen=True)
class BinaryOp(ASTNode):
    """Binary infix operation (``+``, ``-``, ``*``, ``/``, ``^``, comparisons)."""
    op: str
    left: ASTNode
    right: ASTNode


@dataclass(frozen=True)
class UnaryOp(ASTNode):
    """Unary prefix operation (``-``, ``+``)."""
    op: str
    operand: ASTNode


@dataclass(frozen=True)
class Assignment(ASTNode):
    """Variable assignment: ``name = expr``."""
    name: str
    value: ASTNode


@dataclass(frozen=True)
class ExpressionList(ASTNode):
    """Semicolon-separated multi-statement expression list.

    The last expression's value is the overall result.
    """
    expressions: tuple  # tuple[ASTNode, ...]
