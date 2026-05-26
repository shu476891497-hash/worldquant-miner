"""
WQ Shadow Scorer — Scoring Engine (M3)

Computes WQ-compatible performance metrics:
- Sharpe Ratio (annualized, dollar-neutral L/S)
- Turnover (daily avg portfolio change)
- Fitness (Sharpe × sqrt(|returns|) / max(1, turnover))
- Max Drawdown
- Weight Concentration (top-N weight share)
- Sub-Universe Sharpe
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TRADING_DAYS_PER_YEAR = 252

# Default quality thresholds
DEFAULT_THRESHOLDS = {
    "D1": {"sharpe": 1.25, "fitness": 1.0, "turnover_max": 0.70},
    "D0": {"sharpe": 2.0, "fitness": 1.25, "turnover_max": 0.50},
}


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class ScoringResult:
    """Container for all scoring metrics."""
    sharpe: float = np.nan
    annualized_return: float = np.nan
    turnover: float = np.nan
    fitness: float = np.nan
    max_drawdown: float = np.nan
    weight_concentration_top10: float = np.nan
    weight_concentration_top50: float = np.nan
    daily_pnl: Optional[pd.Series] = None
    cumulative_pnl: Optional[pd.Series] = None

    # IS/OOS split
    is_sharpe: float = np.nan
    is_fitness: float = np.nan
    is_turnover: float = np.nan
    is_return: float = np.nan
    oos_sharpe: float = np.nan
    oos_fitness: float = np.nan
    oos_turnover: float = np.nan
    oos_return: float = np.nan

    # Sub-universe
    sub_universe_sharpe: Dict[str, float] = field(default_factory=dict)

    # Pass/fail
    passes_threshold: bool = False
    threshold_details: Dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict."""
        d = {
            "sharpe": _round(self.sharpe),
            "annualized_return": _round(self.annualized_return),
            "turnover": _round(self.turnover),
            "fitness": _round(self.fitness),
            "max_drawdown": _round(self.max_drawdown),
            "weight_concentration_top10": _round(self.weight_concentration_top10),
            "weight_concentration_top50": _round(self.weight_concentration_top50),
            "is_sharpe": _round(self.is_sharpe),
            "is_fitness": _round(self.is_fitness),
            "is_turnover": _round(self.is_turnover),
            "is_return": _round(self.is_return),
            "oos_sharpe": _round(self.oos_sharpe),
            "oos_fitness": _round(self.oos_fitness),
            "oos_turnover": _round(self.oos_turnover),
            "oos_return": _round(self.oos_return),
            "sub_universe_sharpe": {k: _round(v) for k, v in self.sub_universe_sharpe.items()},
            "passes_threshold": self.passes_threshold,
            "threshold_details": self.threshold_details,
        }
        return d


def _round(v: float, decimals: int = 4) -> Optional[float]:
    if v is None or np.isnan(v):
        return None
    return round(float(v), decimals)


# ---------------------------------------------------------------------------
# Core scoring functions
# ---------------------------------------------------------------------------

def neutralize_weights(weights: pd.DataFrame) -> pd.DataFrame:
    """Dollar-neutralize: demean cross-sectionally so long = short exposure."""
    row_mean = weights.mean(axis=1)
    return weights.sub(row_mean, axis=0)


def normalize_weights(weights: pd.DataFrame) -> pd.DataFrame:
    """Normalize so abs(weights).sum(axis=1) == 1 each day (booksize = 1)."""
    abs_sum = weights.abs().sum(axis=1).replace(0, np.nan)
    return weights.div(abs_sum, axis=0)


def compute_pnl(
    weights: pd.DataFrame,
    returns: pd.DataFrame,
) -> pd.Series:
    """Compute daily PnL from weights and forward returns.
    
    weights[t] are the positions taken at end of day t.
    returns[t+1] are the returns earned from day t to t+1.
    So PnL[t+1] = sum(weights[t] * returns[t+1]).
    """
    # Shift weights by 1 day (positions from yesterday)
    shifted_w = weights.shift(1)
    # Daily PnL = sum of (position × return) across stocks
    pnl = (shifted_w * returns).sum(axis=1)
    return pnl


def compute_turnover(weights: pd.DataFrame) -> float:
    """Average daily turnover: mean of abs(weight_change).sum(axis=1) / 2."""
    weight_diff = weights.diff()
    daily_tvr = weight_diff.abs().sum(axis=1) / 2.0
    # Skip first row (NaN from diff)
    return float(daily_tvr.iloc[1:].mean())


def compute_sharpe(pnl: pd.Series) -> float:
    """Annualized Sharpe ratio from daily PnL series."""
    pnl_clean = pnl.dropna()
    if len(pnl_clean) < 10:
        return np.nan
    mean_daily = pnl_clean.mean()
    std_daily = pnl_clean.std()
    if std_daily == 0 or np.isnan(std_daily):
        return np.nan
    return float(mean_daily / std_daily * np.sqrt(TRADING_DAYS_PER_YEAR))


def compute_fitness(sharpe: float, ann_return: float, turnover: float) -> float:
    """WQ approximate fitness: sharpe * sqrt(|returns|) / max(1, turnover/target).
    
    Simplified version. WQ's actual formula is proprietary.
    """
    if np.isnan(sharpe) or np.isnan(ann_return):
        return np.nan
    ret_factor = np.sqrt(abs(ann_return)) if abs(ann_return) > 0 else 0
    tvr_penalty = max(1.0, turnover / 0.15)  # Penalize turnover > 15%
    if tvr_penalty == 0:
        return np.nan
    return float(sharpe * ret_factor / tvr_penalty)


def compute_max_drawdown(cumulative_pnl: pd.Series) -> float:
    """Maximum peak-to-trough drawdown."""
    if len(cumulative_pnl) < 2:
        return np.nan
    running_max = cumulative_pnl.cummax()
    drawdown = cumulative_pnl - running_max
    return float(drawdown.min())


def compute_weight_concentration(
    weights: pd.DataFrame, top_n: int = 10,
) -> float:
    """Average daily fraction of total abs weight held by top-N positions."""
    def _top_n_share(row):
        abs_row = row.abs()
        total = abs_row.sum()
        if total == 0:
            return np.nan
        top = abs_row.nlargest(min(top_n, len(abs_row))).sum()
        return top / total
    
    shares = weights.apply(_top_n_share, axis=1)
    return float(shares.mean())


# ---------------------------------------------------------------------------
# Main scoring entry point
# ---------------------------------------------------------------------------

def score_alpha(
    alpha_weights: pd.DataFrame,
    stock_returns: pd.DataFrame,
    delay: int = 1,
    is_start: str = "2019-01-01",
    is_end: str = "2022-12-31",
    oos_start: str = "2023-01-01",
    oos_end: str = "2026-04-30",
    thresholds: Optional[Dict] = None,
    sub_universe_masks: Optional[Dict[str, pd.DataFrame]] = None,
) -> ScoringResult:
    """Score an alpha signal end-to-end.
    
    Parameters
    ----------
    alpha_weights : pd.DataFrame
        Raw alpha weights (dates × stocks). Output of expression evaluator.
    stock_returns : pd.DataFrame
        Daily stock returns (dates × stocks). Same shape/columns as weights.
    delay : int
        Signal delay (1 = D1, 0 = D0). D1 means extra 1-day shift.
    is_start, is_end : str
        In-sample date range.
    oos_start, oos_end : str
        Out-of-sample date range.
    thresholds : dict, optional
        Quality thresholds. If None, uses D1 defaults.
    sub_universe_masks : dict, optional
        {name: bool DataFrame} for sub-universe Sharpe.
    """
    result = ScoringResult()
    
    if thresholds is None:
        thresholds = DEFAULT_THRESHOLDS["D1"] if delay >= 1 else DEFAULT_THRESHOLDS["D0"]
    
    # 1. Neutralize and normalize weights
    weights = alpha_weights.copy()
    weights = neutralize_weights(weights)
    weights = normalize_weights(weights)
    
    # 2. Apply delay
    if delay > 0:
        weights = weights.shift(delay)
    
    # 3. Align indices
    common_idx = weights.index.intersection(stock_returns.index)
    common_cols = weights.columns.intersection(stock_returns.columns)
    weights = weights.loc[common_idx, common_cols]
    returns = stock_returns.loc[common_idx, common_cols]
    
    # 4. Compute PnL
    pnl = compute_pnl(weights, returns)
    pnl = pnl.dropna()
    
    if len(pnl) < 20:
        return result
    
    cumulative = pnl.cumsum()
    
    result.daily_pnl = pnl
    result.cumulative_pnl = cumulative
    
    # 5. Full-period metrics
    result.sharpe = compute_sharpe(pnl)
    result.annualized_return = float(pnl.mean() * TRADING_DAYS_PER_YEAR)
    result.turnover = compute_turnover(weights)
    result.fitness = compute_fitness(result.sharpe, result.annualized_return, result.turnover)
    result.max_drawdown = compute_max_drawdown(cumulative)
    result.weight_concentration_top10 = compute_weight_concentration(weights, 10)
    result.weight_concentration_top50 = compute_weight_concentration(weights, 50)
    
    # 6. IS / OOS split
    is_mask = (pnl.index >= is_start) & (pnl.index <= is_end)
    oos_mask = (pnl.index >= oos_start) & (pnl.index <= oos_end)
    
    is_pnl = pnl[is_mask]
    oos_pnl = pnl[oos_mask]
    
    if len(is_pnl) > 10:
        result.is_sharpe = compute_sharpe(is_pnl)
        result.is_return = float(is_pnl.mean() * TRADING_DAYS_PER_YEAR)
        is_weights = weights.loc[is_pnl.index] if is_pnl.index.isin(weights.index).all() else weights[is_mask[:len(weights)]]
        result.is_turnover = compute_turnover(is_weights) if len(is_weights) > 1 else np.nan
        result.is_fitness = compute_fitness(result.is_sharpe, result.is_return, result.is_turnover)
    
    if len(oos_pnl) > 10:
        result.oos_sharpe = compute_sharpe(oos_pnl)
        result.oos_return = float(oos_pnl.mean() * TRADING_DAYS_PER_YEAR)
        oos_weights = weights.loc[oos_pnl.index] if oos_pnl.index.isin(weights.index).all() else weights[oos_mask[:len(weights)]]
        result.oos_turnover = compute_turnover(oos_weights) if len(oos_weights) > 1 else np.nan
        result.oos_fitness = compute_fitness(result.oos_sharpe, result.oos_return, result.oos_turnover)
    
    # 7. Sub-universe Sharpe
    if sub_universe_masks:
        for uni_name, mask_df in sub_universe_masks.items():
            try:
                masked_weights = weights * mask_df.reindex_like(weights).fillna(0)
                masked_weights = normalize_weights(masked_weights)
                sub_pnl = compute_pnl(masked_weights, returns)
                result.sub_universe_sharpe[uni_name] = compute_sharpe(sub_pnl.dropna())
            except Exception:
                result.sub_universe_sharpe[uni_name] = np.nan
    
    # 8. Threshold check
    result.threshold_details = {
        "sharpe_pass": result.is_sharpe >= thresholds.get("sharpe", 1.25),
        "fitness_pass": result.is_fitness >= thresholds.get("fitness", 1.0),
        "turnover_pass": result.turnover <= thresholds.get("turnover_max", 0.70),
    }
    result.passes_threshold = all(result.threshold_details.values())
    
    return result
