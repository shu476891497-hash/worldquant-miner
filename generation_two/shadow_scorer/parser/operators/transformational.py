"""
Transformational operators for WQ alpha expressions.

trade_when, bucket, and generate_stats.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def op_trade_when(cond: Any, alpha: pd.DataFrame, fallback: Any = None) -> pd.DataFrame:
    """Conditional trading: update alpha only when cond is true; hold otherwise.

    If fallback is provided and cond is NaN, use fallback value.
    Otherwise, carry the previous alpha value forward.
    """
    if isinstance(cond, pd.DataFrame):
        mask = (cond != 0) & cond.notna()
    elif isinstance(cond, (int, float)):
        if isinstance(alpha, pd.DataFrame):
            mask = pd.DataFrame(bool(cond), index=alpha.index, columns=alpha.columns)
        else:
            return alpha if cond else (fallback if fallback is not None else alpha)
    else:
        mask = cond

    result = alpha.copy() if isinstance(alpha, pd.DataFrame) else alpha
    if isinstance(result, pd.DataFrame):
        # Where mask is False, forward-fill from last True row
        for i in range(1, len(result)):
            carry = ~mask.iloc[i]
            if carry.any():
                result.iloc[i] = np.where(carry, result.iloc[i - 1], result.iloc[i])
        if fallback is not None:
            # Where cond is NaN, use fallback
            nan_mask = cond.isna() if isinstance(cond, pd.DataFrame) else False
            if isinstance(nan_mask, pd.DataFrame) and nan_mask.any().any():
                if isinstance(fallback, pd.DataFrame):
                    result[nan_mask] = fallback[nan_mask]
                else:
                    result[nan_mask] = fallback
    return result


def op_bucket(x: pd.DataFrame, range: Any = None, buckets: Any = None, **kwargs) -> pd.DataFrame:
    """Discretize values into buckets.

    Either range="start, end, step" or buckets="val1,val2,..." can be
    specified.
    """
    # Handle WQ-style arguments that may come as keyword args
    range_str = range or kwargs.get("range")
    buckets_str = buckets or kwargs.get("buckets")

    if isinstance(x, pd.DataFrame):
        if range_str is not None:
            if isinstance(range_str, str):
                parts = [float(p.strip()) for p in range_str.split(",")]
            else:
                parts = [float(range_str)]
            if len(parts) >= 3:
                bins = np.arange(parts[0], parts[1] + parts[2], parts[2])
            else:
                bins = 10
            return x.apply(lambda col: pd.cut(col, bins=bins if isinstance(bins, int) else bins, labels=False))
        elif buckets_str is not None:
            if isinstance(buckets_str, str):
                bucket_edges = [float(p.strip()) for p in buckets_str.split(",")]
            else:
                bucket_edges = [float(buckets_str)]
            return x.apply(lambda col: pd.cut(col, bins=bucket_edges, labels=False))
        else:
            # Default: 10 equal-width buckets
            return x.apply(lambda col: pd.cut(col, bins=10, labels=False))
    return x


def op_generate_stats(alpha: Any) -> Any:
    """Stub: COMBO-only — generate alpha statistics."""
    if isinstance(alpha, pd.DataFrame):
        return alpha * np.nan
    return np.nan
