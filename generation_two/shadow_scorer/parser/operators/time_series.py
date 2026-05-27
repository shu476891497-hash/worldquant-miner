"""
Time-series operators for WQ alpha expressions.

All operators work on pd.DataFrame (dates × instruments). Rolling
operations use ``min_periods=1`` for partial-window calculations.

Performance: inner loops use Numba JIT when available (~30x speedup).
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

try:
    from numba import njit
    _HAS_NUMBA = True
except ImportError:
    _HAS_NUMBA = False
    # Fallback: njit is a no-op decorator
    def njit(func=None, **kwargs):
        if func is not None:
            return func
        return lambda f: f


# ---------------------------------------------------------------------------
# Numba-accelerated kernels (compiled to machine code)
# ---------------------------------------------------------------------------

@njit(cache=True)
def _nb_arg_max(arr, d):
    """Numba kernel: days since max in d-day window."""
    T, N = arr.shape
    out = np.empty((T, N), dtype=np.float64)
    for col in range(N):
        for t in range(T):
            win_start = max(0, t - d + 1)
            best_val = -np.inf
            best_idx = -1
            all_nan = True
            for i in range(win_start, t + 1):
                v = arr[i, col]
                if not np.isnan(v):
                    all_nan = False
                    if v > best_val:
                        best_val = v
                        best_idx = i
            if all_nan:
                out[t, col] = np.nan
            else:
                out[t, col] = t - best_idx
    return out


@njit(cache=True)
def _nb_arg_min(arr, d):
    """Numba kernel: days since min in d-day window."""
    T, N = arr.shape
    out = np.empty((T, N), dtype=np.float64)
    for col in range(N):
        for t in range(T):
            win_start = max(0, t - d + 1)
            best_val = np.inf
            best_idx = -1
            all_nan = True
            for i in range(win_start, t + 1):
                v = arr[i, col]
                if not np.isnan(v):
                    all_nan = False
                    if v < best_val:
                        best_val = v
                        best_idx = i
            if all_nan:
                out[t, col] = np.nan
            else:
                out[t, col] = t - best_idx
    return out


@njit(cache=True)
def _nb_decay_linear(arr, d, weights):
    """Numba kernel: linearly-weighted moving average (sparse mode)."""
    T, N = arr.shape
    out = np.empty((T, N), dtype=np.float64)
    for col in range(N):
        for t in range(T):
            win_start = max(0, t - d + 1)
            n = t - win_start + 1
            ws = 0.0
            dot = 0.0
            has_valid = False
            for i in range(n):
                v = arr[win_start + i, col]
                w = weights[d - n + i]
                if not np.isnan(v):
                    has_valid = True
                    dot += v * w
                # sparse mode: NaN contributes 0 to dot but w still counted
                ws += w
            if not has_valid:
                out[t, col] = np.nan
            else:
                out[t, col] = dot / ws
    return out


@njit(cache=True)
def _nb_ts_rank(arr, d):
    """Numba kernel: time-series percentile rank."""
    T, N = arr.shape
    out = np.empty((T, N), dtype=np.float64)
    for col in range(N):
        for t in range(T):
            v = arr[t, col]
            if np.isnan(v):
                out[t, col] = np.nan
                continue
            win_start = max(0, t - d + 1)
            count_le = 0
            count_valid = 0
            for i in range(win_start, t + 1):
                w = arr[i, col]
                if not np.isnan(w):
                    count_valid += 1
                    if w <= v:
                        count_le += 1
            if count_valid == 0:
                out[t, col] = np.nan
            else:
                out[t, col] = count_le / count_valid
    return out


# ---------------------------------------------------------------------------
# Core rolling operators
# ---------------------------------------------------------------------------

def op_ts_mean(x: pd.DataFrame, d: Any) -> pd.DataFrame:
    """Rolling mean over *d* days."""
    d = int(d)
    return x.rolling(window=d, min_periods=1).mean()


def op_ts_std_dev(x: pd.DataFrame, d: Any) -> pd.DataFrame:
    """Rolling standard deviation over *d* days."""
    d = int(d)
    return x.rolling(window=d, min_periods=1).std()


def op_ts_sum(x: pd.DataFrame, d: Any) -> pd.DataFrame:
    """Rolling sum over *d* days."""
    d = int(d)
    return x.rolling(window=d, min_periods=1).sum()


def op_ts_product(x: pd.DataFrame, d: Any) -> pd.DataFrame:
    """Rolling product over *d* days.

    Vectorized via log-cumsum-exp trick for ~20x speedup.
    """
    d = int(d)
    # For product, use log-sum-exp: prod(x) = exp(sum(log(x)))
    # Handle negatives and zeros carefully
    with np.errstate(divide='ignore', invalid='ignore'):
        log_abs = np.log(x.abs().replace(0, np.nan))
        sign = np.sign(x)

    log_sum = log_abs.rolling(window=d, min_periods=1).sum()
    # Count negatives in window to determine final sign
    neg_count = (sign < 0).astype(float).rolling(window=d, min_periods=1).sum()
    final_sign = np.where(neg_count % 2 == 0, 1.0, -1.0)

    result = np.exp(log_sum) * final_sign
    # Where original had NaN, propagate NaN
    nan_count = x.isna().astype(float).rolling(window=d, min_periods=1).sum()
    result = result.where(nan_count < d)  # all-NaN window -> NaN
    return result


def op_ts_max(x: pd.DataFrame, d: Any) -> pd.DataFrame:
    """Rolling max over *d* days."""
    d = int(d)
    return x.rolling(window=d, min_periods=1).max()


def op_ts_min(x: pd.DataFrame, d: Any) -> pd.DataFrame:
    """Rolling min over *d* days."""
    d = int(d)
    return x.rolling(window=d, min_periods=1).min()


# ---------------------------------------------------------------------------
# Shift / delta
# ---------------------------------------------------------------------------

def op_ts_delay(x: pd.DataFrame, d: Any) -> pd.DataFrame:
    """Value *d* days ago (shift)."""
    d = int(d)
    return x.shift(d)


def op_ts_delta(x: pd.DataFrame, d: Any) -> pd.DataFrame:
    """x - ts_delay(x, d)."""
    d = int(d)
    return x - x.shift(d)


# ---------------------------------------------------------------------------
# Rank / z-score
# ---------------------------------------------------------------------------

def op_ts_rank(x: pd.DataFrame, d: Any, constant: Any = 0) -> pd.DataFrame:
    """Time-series percentile rank (0 to 1) over *d* days, + constant."""
    d = int(d)
    constant = float(constant)
    arr = x.values.astype(np.float64)
    out = _nb_ts_rank(arr, d)
    return pd.DataFrame(out, index=x.index, columns=x.columns) + constant


def op_ts_zscore(x: pd.DataFrame, d: Any) -> pd.DataFrame:
    """Time-series z-score: (x - ts_mean) / ts_std_dev."""
    d = int(d)
    m = x.rolling(window=d, min_periods=1).mean()
    s = x.rolling(window=d, min_periods=1).std()
    return (x - m) / s.replace(0, np.nan)


# ---------------------------------------------------------------------------
# Backfill / NaN handling
# ---------------------------------------------------------------------------

def op_ts_backfill(x: pd.DataFrame, d: Any) -> pd.DataFrame:
    """Forward-fill NaN using last valid value within *d*-day window."""
    d = int(d)
    return x.ffill(limit=d)


def op_ts_count_nans(x: pd.DataFrame, d: Any) -> pd.DataFrame:
    """Count NaN values in *d*-day rolling window."""
    d = int(d)
    return x.isna().astype(float).rolling(window=d, min_periods=1).sum()


# ---------------------------------------------------------------------------
# Weighted / decay
# ---------------------------------------------------------------------------

def op_ts_decay_linear(x: pd.DataFrame, d: Any, dense: Any = False) -> pd.DataFrame:
    """Linearly-weighted average: recent data weighted more.

    Weights: [1, 2, 3, ..., d] normalised to sum to 1.
    If dense=false (default, sparse mode), NaN treated as 0 in weight computation.
    """
    d = int(d)
    is_dense = _to_bool(dense)
    weights = np.arange(1, d + 1, dtype=np.float64)
    arr = x.values.astype(np.float64)

    if not is_dense:
        # Fast path: Numba-accelerated sparse mode
        out = _nb_decay_linear(arr, d, weights)
    else:
        # Dense mode: keep Python loop (rare usage)
        T, N = arr.shape
        out = np.empty_like(arr, dtype=np.float64)
        out[:] = np.nan
        for col in range(N):
            c = arr[:, col]
            for t in range(T):
                win_start = max(0, t - d + 1)
                window = c[win_start:t+1]
                n = len(window)
                w = weights[-n:]
                valid_mask = ~np.isnan(window)
                if valid_mask.sum() == 0:
                    continue
                w_masked = w * valid_mask
                ws = w_masked.sum()
                if ws == 0:
                    continue
                vals = np.where(np.isnan(window), 0.0, window)
                out[t, col] = np.dot(vals, w_masked) / ws

    return pd.DataFrame(out, index=x.index, columns=x.columns)


# ---------------------------------------------------------------------------
# Covariance / correlation / regression
# ---------------------------------------------------------------------------

def op_ts_covariance(y: pd.DataFrame, x: pd.DataFrame, d: Any) -> pd.DataFrame:
    """Rolling covariance of y and x over *d* days."""
    d = int(d)
    # Use manual computation: cov(y,x) = E[xy] - E[x]*E[y]
    xy = x * y
    ex = x.rolling(window=d, min_periods=1).mean()
    ey = y.rolling(window=d, min_periods=1).mean()
    exy = xy.rolling(window=d, min_periods=1).mean()
    return exy - ex * ey


def op_ts_corr(x: pd.DataFrame, y: pd.DataFrame, d: Any) -> pd.DataFrame:
    """Rolling correlation of x and y over *d* days."""
    d = int(d)
    return x.rolling(window=d, min_periods=1).corr(y)


def op_ts_regression(
    y: pd.DataFrame, x: pd.DataFrame, d: Any,
    lag: Any = 0, rettype: Any = 0,
) -> pd.DataFrame:
    """Rolling OLS regression: y = a + b*x.

    rettype: 0 = slope (b), 1 = intercept (a), 2 = residual (y - yhat).
    """
    d = int(d)
    lag = int(lag)
    rettype = int(rettype)

    if lag > 0:
        x = x.shift(lag)

    cov_xy = op_ts_covariance(y, x, d)
    var_x = x.rolling(window=d, min_periods=1).var()
    slope = cov_xy / var_x.replace(0, np.nan)

    if rettype == 0:
        return slope

    mean_y = y.rolling(window=d, min_periods=1).mean()
    mean_x = x.rolling(window=d, min_periods=1).mean()
    intercept = mean_y - slope * mean_x

    if rettype == 1:
        return intercept

    # rettype == 2 → residual
    yhat = slope * x + intercept
    return y - yhat


# ---------------------------------------------------------------------------
# Arg-max / arg-min
# ---------------------------------------------------------------------------

def op_ts_arg_max(x: pd.DataFrame, d: Any) -> pd.DataFrame:
    """Days since max in *d*-day window (0 = today is max)."""
    d = int(d)
    arr = x.values.astype(np.float64)
    out = _nb_arg_max(arr, d)
    return pd.DataFrame(out, index=x.index, columns=x.columns)


def op_ts_arg_min(x: pd.DataFrame, d: Any) -> pd.DataFrame:
    """Days since min in *d*-day window (0 = today is min)."""
    d = int(d)
    arr = x.values.astype(np.float64)
    out = _nb_arg_min(arr, d)
    return pd.DataFrame(out, index=x.index, columns=x.columns)


# ---------------------------------------------------------------------------
# Average diff, scale, quantile
# ---------------------------------------------------------------------------

def op_ts_av_diff(x: pd.DataFrame, d: Any) -> pd.DataFrame:
    """x - ts_mean(x, d), ignoring NaN during mean computation."""
    d = int(d)
    m = x.rolling(window=d, min_periods=1).mean()
    return x - m


def op_ts_scale(x: pd.DataFrame, d: Any, constant: Any = 0) -> pd.DataFrame:
    """(x - ts_min) / (ts_max - ts_min) + constant."""
    d = int(d)
    constant = float(constant)
    ts_min_val = x.rolling(window=d, min_periods=1).min()
    ts_max_val = x.rolling(window=d, min_periods=1).max()
    rng = (ts_max_val - ts_min_val).replace(0, np.nan)
    return (x - ts_min_val) / rng + constant


def op_ts_quantile(x: pd.DataFrame, d: Any, driver: Any = "gaussian") -> pd.DataFrame:
    """Quantile transform: ts_rank then apply inverse CDF.

    driver: 'gaussian', 'uniform', or 'cauchy'.
    """
    from scipy import stats as _stats

    d = int(d)
    driver = str(driver).lower() if not isinstance(driver, str) else driver.lower()

    # First compute ts_rank as percentile
    ranked = op_ts_rank(x, d)
    # Clip to avoid infinities at 0 and 1
    ranked = ranked.clip(0.001, 0.999)

    if driver == "gaussian":
        return ranked.apply(lambda col: col.apply(lambda v: _stats.norm.ppf(v) if not np.isnan(v) else np.nan))
    elif driver == "cauchy":
        return ranked.apply(lambda col: col.apply(lambda v: _stats.cauchy.ppf(v) if not np.isnan(v) else np.nan))
    else:
        # uniform → just shift by mean
        return ranked - ranked.mean(axis=0)


# ---------------------------------------------------------------------------
# Step, kth_element
# ---------------------------------------------------------------------------

def op_ts_step(n: Any) -> pd.DataFrame:
    """Day counter starting from 1.

    Since we don't have access to the data shape here, return the constant.
    The evaluator will broadcast this to a DataFrame.
    """
    # ts_step normally returns a running day counter.
    # Without data context, we return a placeholder.  The actual counter
    # is created during evaluation when we have a DataFrame shape.
    return float(n)


def op_kth_element(x: pd.DataFrame, d: Any, k: Any) -> pd.DataFrame:
    """Return the k-th valid value looking back through *d* days."""
    d = int(d)
    k = int(k)

    def _kth(arr):
        valid = arr[~np.isnan(arr)]
        if len(valid) < k:
            return np.nan
        return valid[-k]  # k-th from the end (most recent)

    return x.rolling(window=d, min_periods=1).apply(_kth, raw=True)


# ---------------------------------------------------------------------------
# Hump, last_diff_value, days_from_last_change, jump_decay
# ---------------------------------------------------------------------------

def op_hump(x: pd.DataFrame, hump: Any = 0.01) -> pd.DataFrame:
    """Limits changes to reduce turnover.

    If the change from previous value is less than hump proportion
    of the previous value, keep the previous value.
    """
    hump = float(hump)
    result = x.copy()
    for i in range(1, len(result)):
        prev = result.iloc[i - 1]
        curr = result.iloc[i]
        change_ratio = (curr - prev).abs() / prev.abs().replace(0, np.nan)
        keep_mask = change_ratio < hump
        result.iloc[i] = np.where(keep_mask & prev.notna(), prev, curr)
    return result


def op_last_diff_value(x: pd.DataFrame, d: Any) -> pd.DataFrame:
    """Last value != current in *d*-day lookback window."""
    d = int(d)

    def _last_diff(arr):
        current = arr[-1]
        if np.isnan(current):
            return np.nan
        for i in range(len(arr) - 2, -1, -1):
            if not np.isnan(arr[i]) and arr[i] != current:
                return arr[i]
        return np.nan

    return x.rolling(window=d, min_periods=1).apply(_last_diff, raw=True)


def op_days_from_last_change(x: pd.DataFrame) -> pd.DataFrame:
    """Number of days since the value last changed."""
    result = pd.DataFrame(0.0, index=x.index, columns=x.columns)
    for i in range(1, len(x)):
        same = (x.iloc[i] == x.iloc[i - 1]) | (x.iloc[i].isna() & x.iloc[i - 1].isna())
        result.iloc[i] = np.where(same, result.iloc[i - 1] + 1, 0)
    return result


def op_jump_decay(
    x: pd.DataFrame, d: Any, sensitivity: Any = 0.5, force: Any = 0.1,
) -> pd.DataFrame:
    """Decay after large jumps.

    If the jump (abs change) > sensitivity * rolling_std, apply exponential
    decay with factor *force* over *d* days.
    """
    d = int(d)
    sensitivity = float(sensitivity)
    force = float(force)

    delta = x.diff()
    rolling_std = x.rolling(window=d, min_periods=1).std()
    threshold = sensitivity * rolling_std

    result = x.copy()
    for i in range(1, len(result)):
        jump = delta.iloc[i].abs()
        is_jump = jump > threshold.iloc[i]
        # For jump instruments, decay towards previous value
        prev = result.iloc[i - 1]
        curr = result.iloc[i]
        decayed = prev + force * (curr - prev)
        result.iloc[i] = np.where(is_jump, decayed, curr)
    return result


# ---------------------------------------------------------------------------
# Stubs for advanced time-series operators
# ---------------------------------------------------------------------------

def op_ts_target_tvr_decay(
    x: pd.DataFrame,
    lambda_min: Any = 0, lambda_max: Any = 1, target_tvr: Any = 0.1,
) -> pd.DataFrame:
    """Stub: tune ts_decay to match target turnover."""
    return x


def op_ts_target_tvr_delta_limit(
    x: pd.DataFrame, y: Any = None,
    lambda_min: Any = 0, lambda_max: Any = 1, target_tvr: Any = 0.1,
) -> pd.DataFrame:
    """Stub: tune ts_delta_limit to match target turnover."""
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
