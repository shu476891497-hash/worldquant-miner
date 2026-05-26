"""
Arithmetic operators for WQ alpha expressions.

All functions operate element-wise on pd.DataFrame / scalar inputs.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def op_add(x: Any, y: Any, *extra: Any, filter: Any = False) -> Any:
    """add(x, y, ..., filter=false): sum of all inputs.

    If filter=true, NaN values are replaced with 0 before adding.
    """
    # Normalise filter to bool
    filt = _to_bool(filter)
    items = [x, y, *extra]
    if filt:
        items = [_fill_nan(i, 0) for i in items]
    result = items[0]
    for item in items[1:]:
        result = result + item
    return result


def op_subtract(x: Any, y: Any, filter: Any = False) -> Any:
    """subtract(x, y, filter=false): x - y."""
    filt = _to_bool(filter)
    if filt:
        x, y = _fill_nan(x, 0), _fill_nan(y, 0)
    return x - y


def op_multiply(x: Any, y: Any, *extra: Any, filter: Any = False) -> Any:
    """multiply(x, y, ..., filter=false): product of all inputs.

    If filter=true, NaN values are replaced with 1.
    """
    filt = _to_bool(filter)
    items = [x, y, *extra]
    if filt:
        items = [_fill_nan(i, 1) for i in items]
    result = items[0]
    for item in items[1:]:
        result = result * item
    return result


def op_divide(x: Any, y: Any) -> Any:
    """divide(x, y): x / y, safe (NaN on divide-by-zero)."""
    if isinstance(y, pd.DataFrame):
        y_safe = y.replace(0, np.nan)
    elif isinstance(y, (int, float)):
        y_safe = y if y != 0 else np.nan
    else:
        y_safe = y
    return x / y_safe


def op_abs(x: Any) -> Any:
    """abs(x): absolute value."""
    if isinstance(x, pd.DataFrame):
        return x.abs()
    return np.abs(x)


def op_log(x: Any) -> Any:
    """log(x): natural logarithm."""
    if isinstance(x, pd.DataFrame):
        return np.log(x.where(x > 0, np.nan))
    return np.log(x) if x > 0 else np.nan


def op_sqrt(x: Any) -> Any:
    """sqrt(x): square root."""
    if isinstance(x, pd.DataFrame):
        return np.sqrt(x.where(x >= 0, np.nan))
    return np.sqrt(x) if x >= 0 else np.nan


def op_sign(x: Any) -> Any:
    """sign(x): 1 / -1 / 0 / NaN."""
    if isinstance(x, pd.DataFrame):
        return np.sign(x)
    return np.sign(x)


def op_signed_power(x: Any, y: Any) -> Any:
    """signed_power(x, y): sign(x) * abs(x)^y."""
    if isinstance(x, pd.DataFrame):
        return np.sign(x) * np.power(np.abs(x), y)
    return np.sign(x) * np.power(np.abs(x), y)


def op_power(x: Any, y: Any) -> Any:
    """power(x, y): x^y."""
    return np.power(x, y)


def op_inverse(x: Any) -> Any:
    """inverse(x): 1/x."""
    return op_divide(1.0, x)


def op_reverse(x: Any) -> Any:
    """reverse(x): -x."""
    return -x


def op_min(x: Any, y: Any, *extra: Any) -> Any:
    """min(x, y, ...): element-wise minimum of all inputs."""
    items = [x, y, *extra]
    result = items[0]
    for item in items[1:]:
        if isinstance(result, pd.DataFrame) or isinstance(item, pd.DataFrame):
            # Ensure both are DataFrames for proper comparison
            r = result if isinstance(result, pd.DataFrame) else result
            i = item if isinstance(item, pd.DataFrame) else item
            result = pd.DataFrame(
                np.fmin(r, i),
                index=result.index if isinstance(result, pd.DataFrame) else item.index,
                columns=result.columns if isinstance(result, pd.DataFrame) else item.columns,
            )
        else:
            result = np.fmin(result, item)
    return result


def op_max(x: Any, y: Any, *extra: Any) -> Any:
    """max(x, y, ...): element-wise maximum of all inputs."""
    items = [x, y, *extra]
    result = items[0]
    for item in items[1:]:
        if isinstance(result, pd.DataFrame) or isinstance(item, pd.DataFrame):
            r = result if isinstance(result, pd.DataFrame) else result
            i = item if isinstance(item, pd.DataFrame) else item
            result = pd.DataFrame(
                np.fmax(r, i),
                index=result.index if isinstance(result, pd.DataFrame) else item.index,
                columns=result.columns if isinstance(result, pd.DataFrame) else item.columns,
            )
        else:
            result = np.fmax(result, item)
    return result


def op_to_nan(x: Any, value: Any = 0, reverse: Any = False) -> Any:
    """to_nan(x, value=0, reverse=false).

    If reverse=false: convert *value* to NaN.
    If reverse=true:  convert NaN to *value*.
    """
    rev = _to_bool(reverse)
    val = float(value) if not isinstance(value, (int, float)) else value
    if isinstance(x, pd.DataFrame):
        if rev:
            return x.fillna(val)
        else:
            return x.where(x != val, np.nan)
    else:
        if rev:
            return val if np.isnan(x) else x
        else:
            return np.nan if x == val else x


def op_densify(x: Any) -> Any:
    """densify(x): re-map group labels to dense integer buckets."""
    if isinstance(x, pd.DataFrame):
        # Each column independently
        result = x.copy()
        for col in result.columns:
            uniq = result[col].dropna().unique()
            mapping = {v: i for i, v in enumerate(sorted(uniq))}
            result[col] = result[col].map(mapping)
        return result
    if isinstance(x, pd.Series):
        uniq = x.dropna().unique()
        mapping = {v: i for i, v in enumerate(sorted(uniq))}
        return x.map(mapping)
    return x


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.lower() in ("true", "1", "yes")
    return bool(v)


def _fill_nan(x: Any, fill: float) -> Any:
    if isinstance(x, pd.DataFrame):
        return x.fillna(fill)
    if isinstance(x, (int, float)) and np.isnan(x):
        return fill
    return x
