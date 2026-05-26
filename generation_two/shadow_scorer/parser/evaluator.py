"""
AST evaluation engine for WQ alpha expressions.

Takes an AST produced by ``parser.parse_expression`` together with a data
dictionary and evaluates the expression to produce a DataFrame of alpha
weights.
"""

from __future__ import annotations

import operator as _op
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

from .ast_nodes import (
    ASTNode,
    Assignment,
    BinaryOp,
    ExpressionList,
    FunctionCall,
    Identifier,
    NumberLiteral,
    StringLiteral,
    UnaryOp,
)
from .operators import OPERATOR_REGISTRY
from .parser import parse_expression as _parse


class EvalError(Exception):
    """Raised when expression evaluation fails at runtime."""
    pass


# ---------------------------------------------------------------------------
# Binary-op dispatch
# ---------------------------------------------------------------------------

_BINARY_OPS = {
    "+": _op.add,
    "-": _op.sub,
    "*": _op.mul,
    "/": _op.truediv,
    "^": _op.pow,
    ">": _op.gt,
    "<": _op.lt,
    ">=": _op.ge,
    "<=": _op.le,
    "==": _op.eq,
    "!=": _op.ne,
}


def _binary_op(op: str, left: Any, right: Any) -> Any:
    """Apply a binary operation, handling DataFrames gracefully."""
    if op == "&":
        # Logical AND
        l = left.astype(float) if isinstance(left, pd.DataFrame) else left
        r = right.astype(float) if isinstance(right, pd.DataFrame) else right
        return ((l != 0) & (r != 0)).astype(float)
    if op == "|":
        # Logical OR
        l = left.astype(float) if isinstance(left, pd.DataFrame) else left
        r = right.astype(float) if isinstance(right, pd.DataFrame) else right
        return ((l != 0) | (r != 0)).astype(float)
    if op == "/":
        # Safe division
        if isinstance(right, pd.DataFrame):
            result = left / right.replace(0, np.nan)
        elif isinstance(right, (int, float)):
            result = left / right if right != 0 else left * np.nan
        else:
            result = left / right
        return result
    fn = _BINARY_OPS.get(op)
    if fn is None:
        raise EvalError(f"Unknown binary operator: {op!r}")
    result = fn(left, right)
    # Comparison results → float 0/1
    if op in (">", "<", ">=", "<=", "==", "!="):
        if isinstance(result, pd.DataFrame):
            result = result.astype(float)
    return result


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------

class _Evaluator:
    """Walks an AST and produces results."""

    def __init__(
        self,
        data: Dict[str, pd.DataFrame],
        group_data: Optional[Dict[str, pd.Series]] = None,
    ):
        self.data = data
        self.group_data = group_data or {}
        self.variables: Dict[str, Any] = {}

    def eval(self, node: ASTNode) -> Any:
        method = f"_eval_{type(node).__name__}"
        fn = getattr(self, method, None)
        if fn is None:
            raise EvalError(f"Cannot evaluate AST node type: {type(node).__name__}")
        return fn(node)

    # -- literals --

    def _eval_NumberLiteral(self, node: NumberLiteral) -> float:
        return node.value

    def _eval_StringLiteral(self, node: StringLiteral) -> str:
        return node.value

    # -- identifier --

    def _eval_Identifier(self, node: Identifier) -> Any:
        name = node.name

        # 1. Check variables first
        if name in self.variables:
            return self.variables[name]

        # 2. Check data fields
        if name in self.data:
            return self.data[name]

        # 3. Check group data (sector, industry, subindustry, …)
        if name in self.group_data:
            return self.group_data[name]

        # 4. Common boolean-ish identifiers
        lower = name.lower()
        if lower == "true":
            return True
        if lower == "false":
            return False

        # 5. Unknown — might be used later as a string label (e.g. 'gaussian')
        return name

    # -- operations --

    def _eval_BinaryOp(self, node: BinaryOp) -> Any:
        left = self.eval(node.left)
        right = self.eval(node.right)
        return _binary_op(node.op, left, right)

    def _eval_UnaryOp(self, node: UnaryOp) -> Any:
        operand = self.eval(node.operand)
        if node.op == "-":
            return -operand
        return operand  # '+' is identity

    # -- function call --

    def _eval_FunctionCall(self, node: FunctionCall) -> Any:
        name = node.name.lower()  # WQ operators are case-insensitive

        # Look up in operator registry
        func = OPERATOR_REGISTRY.get(name)
        if func is None:
            raise EvalError(
                f"Unknown operator/function: {node.name!r}. "
                f"Available: {sorted(OPERATOR_REGISTRY.keys())}"
            )

        # Evaluate positional args
        args = [self.eval(a) for a in node.args]

        # Evaluate keyword args
        kwargs: dict = {}
        for kw_name, kw_node in node.kwargs:
            kwargs[kw_name] = self.eval(kw_node)

        # Call the operator
        try:
            return func(*args, **kwargs)
        except TypeError as exc:
            raise EvalError(
                f"Error calling operator {node.name!r} with "
                f"{len(args)} positional and {list(kwargs)} keyword args: {exc}"
            ) from exc

    # -- assignment --

    def _eval_Assignment(self, node: Assignment) -> Any:
        value = self.eval(node.value)
        self.variables[node.name] = value
        return value

    # -- expression list --

    def _eval_ExpressionList(self, node: ExpressionList) -> Any:
        result = None
        for expr in node.expressions:
            result = self.eval(expr)
        return result


def evaluate_expression(
    expr: str,
    data: Dict[str, pd.DataFrame],
    group_data: Optional[Dict[str, pd.Series]] = None,
) -> pd.DataFrame:
    """Evaluate a WQ alpha expression.

    Parameters
    ----------
    expr : str
        WQ expression string.
    data : dict
        Mapping of field names to ``pd.DataFrame`` (DatetimeIndex × instrument
        columns).
    group_data : dict, optional
        Mapping of group names (``sector``, ``industry``, ``subindustry``) to
        ``pd.Series`` (instrument → group label).

    Returns
    -------
    pd.DataFrame
        Alpha weights with the same shape as the input DataFrames.
    """
    ast = _parse(expr)
    evaluator = _Evaluator(data, group_data)
    result = evaluator.eval(ast)

    # Ensure we always return a DataFrame
    if isinstance(result, pd.DataFrame):
        return result
    if isinstance(result, pd.Series):
        # Broadcast to DataFrame using any available reference
        ref = next(iter(data.values()))
        return pd.DataFrame(
            np.tile(result.values, (len(ref.index), 1)),
            index=ref.index,
            columns=ref.columns,
        )
    if isinstance(result, (int, float, np.number)):
        ref = next(iter(data.values()))
        return pd.DataFrame(result, index=ref.index, columns=ref.columns)

    raise EvalError(f"Expression evaluated to unexpected type: {type(result).__name__}")
