"""
Group operators for WQ alpha expressions.

Operate within groups (sector/industry/subindustry). The ``group``
parameter is a pd.Series mapping instrument → group label, or a
pd.DataFrame where each column matches an instrument and each row has
the group label for that date.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def op_group_neutralize(x: pd.DataFrame, group: Any) -> pd.DataFrame:
    """Demean within each group for each date.

    group: pd.Series(instrument → label) or a string (resolved by evaluator).
    """
    groups = _resolve_group(x, group)
    result = x.copy()
    for date_idx in range(len(x)):
        row = x.iloc[date_idx]
        g = _get_group_labels(groups, date_idx, x.columns)
        for label in g.dropna().unique():
            mask = g == label
            group_vals = row[mask]
            if group_vals.notna().sum() > 0:
                result.iloc[date_idx, mask.values] = group_vals - group_vals.mean()
    return result


def op_group_rank(x: pd.DataFrame, group: Any) -> pd.DataFrame:
    """Rank within each group for each date."""
    groups = _resolve_group(x, group)
    result = x.copy()
    for date_idx in range(len(x)):
        row = x.iloc[date_idx]
        g = _get_group_labels(groups, date_idx, x.columns)
        for label in g.dropna().unique():
            mask = g == label
            group_vals = row[mask]
            ranked = group_vals.rank(pct=True, na_option="keep")
            result.iloc[date_idx, mask.values] = ranked.values
    return result


def op_group_zscore(x: pd.DataFrame, group: Any) -> pd.DataFrame:
    """Z-score within each group for each date."""
    groups = _resolve_group(x, group)
    result = x.copy()
    for date_idx in range(len(x)):
        row = x.iloc[date_idx]
        g = _get_group_labels(groups, date_idx, x.columns)
        for label in g.dropna().unique():
            mask = g == label
            group_vals = row[mask]
            m = group_vals.mean()
            s = group_vals.std()
            if s != 0 and not np.isnan(s):
                result.iloc[date_idx, mask.values] = ((group_vals - m) / s).values
            else:
                result.iloc[date_idx, mask.values] = 0.0
    return result


def op_group_mean(x: pd.DataFrame, weight: Any, group: Any) -> pd.DataFrame:
    """Weighted mean within each group for each date.

    All elements in a group are set to the (weighted) mean of the group.
    """
    groups = _resolve_group(x, group)
    result = x.copy()
    for date_idx in range(len(x)):
        row = x.iloc[date_idx]
        g = _get_group_labels(groups, date_idx, x.columns)
        if isinstance(weight, pd.DataFrame):
            w_row = weight.iloc[date_idx]
        else:
            w_row = None
        for label in g.dropna().unique():
            mask = g == label
            group_vals = row[mask]
            if w_row is not None:
                wt = w_row[mask]
                wt_sum = wt.sum()
                if wt_sum != 0:
                    wmean = (group_vals * wt).sum() / wt_sum
                else:
                    wmean = group_vals.mean()
            else:
                wmean = group_vals.mean()
            result.iloc[date_idx, mask.values] = wmean
    return result


def op_group_min(x: pd.DataFrame, group: Any) -> pd.DataFrame:
    """Min within each group for each date."""
    groups = _resolve_group(x, group)
    result = x.copy()
    for date_idx in range(len(x)):
        row = x.iloc[date_idx]
        g = _get_group_labels(groups, date_idx, x.columns)
        for label in g.dropna().unique():
            mask = g == label
            group_vals = row[mask]
            result.iloc[date_idx, mask.values] = group_vals.min()
    return result


def op_group_max(x: pd.DataFrame, group: Any) -> pd.DataFrame:
    """Max within each group for each date."""
    groups = _resolve_group(x, group)
    result = x.copy()
    for date_idx in range(len(x)):
        row = x.iloc[date_idx]
        g = _get_group_labels(groups, date_idx, x.columns)
        for label in g.dropna().unique():
            mask = g == label
            group_vals = row[mask]
            result.iloc[date_idx, mask.values] = group_vals.max()
    return result


def op_group_scale(x: pd.DataFrame, group: Any) -> pd.DataFrame:
    """Min-max scale within each group: (x - gmin)/(gmax - gmin)."""
    groups = _resolve_group(x, group)
    result = x.copy()
    for date_idx in range(len(x)):
        row = x.iloc[date_idx]
        g = _get_group_labels(groups, date_idx, x.columns)
        for label in g.dropna().unique():
            mask = g == label
            group_vals = row[mask]
            gmin = group_vals.min()
            gmax = group_vals.max()
            rng = gmax - gmin
            if rng != 0 and not np.isnan(rng):
                result.iloc[date_idx, mask.values] = ((group_vals - gmin) / rng).values
            else:
                result.iloc[date_idx, mask.values] = 0.0
    return result


def op_group_backfill(
    x: pd.DataFrame, group: Any, d: Any, std: Any = 4.0,
) -> pd.DataFrame:
    """Fill NaN from group peers using winsorized mean over last *d* days."""
    d = int(d)
    std_val = float(std)
    groups = _resolve_group(x, group)
    result = x.copy()

    for date_idx in range(len(x)):
        row = result.iloc[date_idx]
        g = _get_group_labels(groups, date_idx, x.columns)
        nan_mask = row.isna()
        if not nan_mask.any():
            continue
        for label in g.dropna().unique():
            group_mask = g == label
            group_nan = nan_mask & group_mask
            if not group_nan.any():
                continue
            # Get group values over last d days
            start = max(0, date_idx - d + 1)
            window = x.iloc[start:date_idx + 1]
            group_cols = x.columns[group_mask]
            pool = window[group_cols].values.flatten()
            pool = pool[~np.isnan(pool)]
            if len(pool) == 0:
                continue
            # Winsorize
            m = np.mean(pool)
            s = np.std(pool)
            if s > 0:
                pool = np.clip(pool, m - std_val * s, m + std_val * s)
            fill_val = np.mean(pool)
            result.iloc[date_idx, group_nan.values] = fill_val
    return result


def op_group_cartesian_product(g1: Any, g2: Any) -> Any:
    """Merge two groupings: new_group = g1 * len_g2 + g2.

    Creates a combined grouping from two input groupings.
    """
    if isinstance(g1, pd.Series) and isinstance(g2, pd.Series):
        return g1.astype(str) + "_" + g2.astype(str)
    if isinstance(g1, pd.DataFrame) and isinstance(g2, pd.DataFrame):
        return g1.astype(str) + "_" + g2.astype(str)
    return g1


def op_combo_a(alpha: Any, nlength: Any = 250, mode: Any = "algo1") -> Any:
    """Stub: COMBO-only — combine multiple alpha signals."""
    if isinstance(alpha, pd.DataFrame):
        return alpha * np.nan
    return np.nan


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_group(x: pd.DataFrame, group: Any) -> Any:
    """Resolve the group argument to usable labels.

    group can be:
    - pd.Series (instrument → label)
    - pd.DataFrame (date × instrument)
    - str / other → generate a constant group so every instrument
      is in the same group (useful when the evaluator passes a
      string like 'subindustry' and the data isn't available).
    """
    if isinstance(group, (pd.Series, pd.DataFrame)):
        return group
    # If it's a string or other constant, put all instruments in one group
    return pd.Series(1, index=x.columns)


def _get_group_labels(groups: Any, date_idx: int, columns: pd.Index) -> pd.Series:
    """Get group labels for a specific date row."""
    if isinstance(groups, pd.DataFrame):
        return groups.iloc[date_idx]
    if isinstance(groups, pd.Series):
        return groups.reindex(columns)
    return pd.Series(1, index=columns)
