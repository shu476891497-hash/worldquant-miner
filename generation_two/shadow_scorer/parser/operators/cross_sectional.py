"""
Cross-sectional operators for WQ alpha expressions.

Operate across instruments (columns) for each date (row).
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def op_rank(x: pd.DataFrame, rate: Any = 2) -> pd.DataFrame:
    """Percentile rank across instruments (0 to 1).

    rate=0 for precise sort, rate=2 for default average ranking.
    """
    rate = int(rate)
    method = "average" if rate != 0 else "first"
    return x.rank(axis=1, method=method, pct=True, na_option="keep")


def op_normalize(x: pd.DataFrame, useStd: Any = False, limit: Any = 0.0) -> pd.DataFrame:
    """Demean across instruments for each date.

    If useStd=true, also divide by standard deviation.
    limit > 0: clip to ±limit after normalisation.
    """
    use_std = _to_bool(useStd)
    limit_val = float(limit)

    mean = x.mean(axis=1)
    result = x.sub(mean, axis=0)

    if use_std:
        std = x.std(axis=1).replace(0, np.nan)
        result = result.div(std, axis=0)

    if limit_val > 0:
        result = result.clip(-limit_val, limit_val)

    return result


def op_zscore(x: pd.DataFrame) -> pd.DataFrame:
    """Cross-sectional z-score: (x - mean) / std across instruments."""
    mean = x.mean(axis=1)
    std = x.std(axis=1).replace(0, np.nan)
    return x.sub(mean, axis=0).div(std, axis=0)


def op_winsorize(x: pd.DataFrame, std: Any = 4) -> pd.DataFrame:
    """Clip values to mean ± std * stdev across instruments per row."""
    std_mult = float(std)
    mean = x.mean(axis=1)
    stdev = x.std(axis=1)
    lower = mean - std_mult * stdev
    upper = mean + std_mult * stdev
    return x.clip(lower, upper, axis=0)


def op_quantile(
    x: pd.DataFrame, driver: Any = "gaussian", sigma: Any = 1.0,
) -> pd.DataFrame:
    """Rank then apply inverse CDF across instruments.

    driver: 'gaussian', 'uniform', 'cauchy'.
    """
    from scipy import stats as _stats

    driver = str(driver).lower() if not isinstance(driver, str) else driver.lower()
    sigma_val = float(sigma)

    ranked = x.rank(axis=1, pct=True, na_option="keep")
    # Clip to avoid infinities at 0 and 1
    ranked = ranked.clip(0.001, 0.999)

    if driver == "gaussian":
        result = ranked.applymap(lambda v: _stats.norm.ppf(v) * sigma_val if not np.isnan(v) else np.nan)
    elif driver == "cauchy":
        result = ranked.applymap(lambda v: _stats.cauchy.ppf(v) * sigma_val if not np.isnan(v) else np.nan)
    else:
        # uniform: shift by mean
        result = ranked - ranked.mean(axis=1).values[:, np.newaxis]

    return result


def op_scale(
    x: pd.DataFrame, scale: Any = 1, longscale: Any = 1, shortscale: Any = 1,
) -> pd.DataFrame:
    """Scale to booksize.

    Scales so that sum(abs(x)) = *scale* per row.
    longscale/shortscale allow separate scaling of long/short positions.
    """
    scale_val = float(scale)
    longscale_val = float(longscale)
    shortscale_val = float(shortscale)

    abs_sum = x.abs().sum(axis=1).replace(0, np.nan)
    result = x.div(abs_sum, axis=0) * scale_val

    if longscale_val != 1 or shortscale_val != 1:
        long_mask = result > 0
        short_mask = result < 0
        result = result.where(~long_mask, result * longscale_val)
        result = result.where(~short_mask, result * shortscale_val)

    return result


def op_scale_down(x: pd.DataFrame, constant: Any = 0) -> pd.DataFrame:
    """Min-max normalize to [0, 1] - constant across instruments per row."""
    constant_val = float(constant)
    row_min = x.min(axis=1)
    row_max = x.max(axis=1)
    rng = (row_max - row_min).replace(0, np.nan)
    return x.sub(row_min, axis=0).div(rng, axis=0) - constant_val


def op_vector_neut(x: pd.DataFrame, y: pd.DataFrame) -> pd.DataFrame:
    """Make x orthogonal to y: x* = x - (dot(x,y)/dot(y,y)) * y per row."""
    result = x.copy()
    for i in range(len(x)):
        xr = x.iloc[i].values.astype(float)
        yr = y.iloc[i].values.astype(float)
        mask = ~(np.isnan(xr) | np.isnan(yr))
        if mask.sum() == 0:
            continue
        xm = xr[mask]
        ym = yr[mask]
        dot_yy = np.dot(ym, ym)
        if dot_yy == 0:
            continue
        beta = np.dot(xm, ym) / dot_yy
        new_row = xr.copy()
        new_row[mask] = xm - beta * ym
        result.iloc[i] = new_row
    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.lower() in ("true", "1", "yes")
    return bool(v)
