"""
Logical operators for WQ alpha expressions.

Operates element-wise.  WQ convention: 1.0 = true, 0.0 = false, NaN = NaN.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def op_and(x: Any, y: Any) -> Any:
    """and(x, y): logical AND — true if both non-zero."""
    a = _as_bool_df(x)
    b = _as_bool_df(y)
    return (a & b).astype(float)


def op_or(x: Any, y: Any) -> Any:
    """or(x, y): logical OR — true if either non-zero."""
    a = _as_bool_df(x)
    b = _as_bool_df(y)
    return (a | b).astype(float)


def op_not(x: Any) -> Any:
    """not(x): logical NOT — 1→0, 0→1, NaN→NaN."""
    if isinstance(x, pd.DataFrame):
        result = pd.DataFrame(np.nan, index=x.index, columns=x.columns)
        mask_zero = x == 0
        mask_nonzero = (x != 0) & x.notna()
        result[mask_zero] = 1.0
        result[mask_nonzero] = 0.0
        return result
    if isinstance(x, (int, float)):
        if np.isnan(x):
            return np.nan
        return 0.0 if x != 0 else 1.0
    return (~(x.astype(bool))).astype(float)


def op_equal(x: Any, y: Any) -> Any:
    """equal: x == y → 1.0 / 0.0."""
    return _cmp(x, y, "eq")


def op_not_equal(x: Any, y: Any) -> Any:
    """not_equal: x != y."""
    return _cmp(x, y, "ne")


def op_greater(x: Any, y: Any) -> Any:
    """greater: x > y."""
    return _cmp(x, y, "gt")


def op_greater_equal(x: Any, y: Any) -> Any:
    """greater_equal: x >= y."""
    return _cmp(x, y, "ge")


def op_less(x: Any, y: Any) -> Any:
    """less: x < y."""
    return _cmp(x, y, "lt")


def op_less_equal(x: Any, y: Any) -> Any:
    """less_equal: x <= y."""
    return _cmp(x, y, "le")


def op_is_nan(x: Any) -> Any:
    """is_nan(x): 1 if NaN, else 0."""
    if isinstance(x, pd.DataFrame):
        return x.isna().astype(float)
    return float(np.isnan(x))


def op_if_else(cond: Any, true_val: Any, false_val: Any) -> Any:
    """if_else(cond, true_val, false_val): where cond is true, use true_val; else false_val."""
    if isinstance(cond, pd.DataFrame):
        mask = (cond != 0) & cond.notna()
        # Use np.where for broadcasting
        if isinstance(true_val, pd.DataFrame) and isinstance(false_val, pd.DataFrame):
            result = pd.DataFrame(
                np.where(mask.values, true_val.values, false_val.values),
                index=cond.index,
                columns=cond.columns,
            )
        elif isinstance(true_val, pd.DataFrame):
            result = pd.DataFrame(
                np.where(mask.values, true_val.values, false_val),
                index=cond.index,
                columns=cond.columns,
            )
        elif isinstance(false_val, pd.DataFrame):
            result = pd.DataFrame(
                np.where(mask.values, true_val, false_val.values),
                index=cond.index,
                columns=cond.columns,
            )
        else:
            result = pd.DataFrame(
                np.where(mask.values, true_val, false_val),
                index=cond.index,
                columns=cond.columns,
            )
        # Where cond is NaN, result is NaN
        result[cond.isna()] = np.nan
        return result
    # Scalar
    if np.isnan(cond) if isinstance(cond, float) else False:
        return np.nan
    return true_val if cond != 0 else false_val


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _as_bool_df(x: Any) -> Any:
    """Convert to boolean-like, preserving NaN."""
    if isinstance(x, pd.DataFrame):
        return (x != 0) & x.notna()
    return x != 0 if not (isinstance(x, float) and np.isnan(x)) else False


def _cmp(x: Any, y: Any, method: str) -> Any:
    """Generic comparison returning float 1/0."""
    if isinstance(x, pd.DataFrame) or isinstance(y, pd.DataFrame):
        result = getattr(x if isinstance(x, pd.DataFrame) else pd.DataFrame(x), f"__{method}__")(y)
        if isinstance(result, pd.DataFrame):
            return result.astype(float)
        # Fallback for non-DataFrame comparison result
        return pd.DataFrame(result).astype(float)
    return float(getattr(x, f"__{method}__")(y))
