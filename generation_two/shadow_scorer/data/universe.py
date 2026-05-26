"""
Dynamic universe construction for WQ Shadow Scorer.

Constructs TOP500, TOP1000, TOP2000, TOP3000 universes by daily market cap ranking.
Handles additions/removals over time with caching.

A universe membership is a boolean mask DataFrame (dates × instruments) indicating
which stocks are in the universe on each date.
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd

from shadow_scorer.config import CACHE_DIR, UNIVERSE_SIZES
from shadow_scorer.data.storage import load_cached_panel, save_panel

logger = logging.getLogger(__name__)


def get_membership(universe: str, dates: pd.DatetimeIndex,
                   cap_df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """
    Return boolean mask DataFrame for universe membership.

    Stocks are ranked by market cap on each date. The top N stocks
    (where N = universe size) are marked True.

    Parameters
    ----------
    universe : str
        Universe name (e.g., 'TOP500', 'TOP1000', 'TOP2000', 'TOP3000').
    dates : pd.DatetimeIndex
        Target dates.
    cap_df : pd.DataFrame, optional
        Market cap panel (dates × tickers). If None, will try to load from cache.

    Returns
    -------
    pd.DataFrame
        Boolean mask (dates × tickers). True = in universe.
    """
    universe = universe.upper()

    if universe not in UNIVERSE_SIZES:
        logger.warning(f"Unknown universe '{universe}', defaulting to TOP3000")
        universe = 'TOP3000'

    target_size = UNIVERSE_SIZES[universe]

    # Try cache first
    cached = load_cached_panel('universe', universe, str(dates[0].date()),
                                str(dates[-1].date()))
    if cached is not None:
        # Filter to requested dates
        common_dates = cached.index.intersection(dates)
        if len(common_dates) >= len(dates) * 0.9:  # 90% coverage
            logger.info(f"Universe '{universe}' loaded from cache")
            return cached.reindex(dates).fillna(False).astype(bool)

    # Build from market cap data
    if cap_df is None:
        cap_df = _load_market_cap(dates)

    if cap_df.empty:
        logger.warning(f"No market cap data available for universe construction. "
                        f"Returning all-True mask for {universe}.")
        return _all_true_mask(dates, cap_df.columns if not cap_df.empty else [])

    # Align cap_df to requested dates
    cap_aligned = cap_df.reindex(dates)

    # Rank by market cap on each date (descending: largest = rank 1)
    mask = _rank_membership(cap_aligned, target_size)

    # Cache the result
    try:
        start_str = str(dates[0].date())
        end_str = str(dates[-1].date())
        # Convert bool to int for parquet storage
        save_panel(mask.astype(int), 'universe', universe, start_str, end_str)
    except Exception as e:
        logger.warning(f"Failed to cache universe membership: {e}")

    return mask


def _rank_membership(cap_df: pd.DataFrame, target_size: int) -> pd.DataFrame:
    """
    Rank stocks by market cap and return boolean membership mask.

    Parameters
    ----------
    cap_df : pd.DataFrame
        Market cap panel (dates × tickers).
    target_size : int
        Number of stocks to include in universe.

    Returns
    -------
    pd.DataFrame
        Boolean mask (dates × tickers).
    """
    # Rank each row (date) by market cap, descending
    # rank method 'first' breaks ties by order of appearance
    ranks = cap_df.rank(axis=1, ascending=False, method='first', na_option='bottom')

    # Stocks with rank <= target_size are in the universe
    mask = ranks <= target_size

    # Also exclude stocks with NaN market cap (no data)
    mask = mask & cap_df.notna()

    # Log stats
    avg_members = mask.sum(axis=1).mean()
    logger.info(f"Universe target={target_size}, avg members/day={avg_members:.0f}")

    return mask


def _load_market_cap(dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Try to load market cap from cache."""
    start = str(dates[0].date())
    end = str(dates[-1].date())
    cap = load_cached_panel('yfinance', 'cap', start, end)
    if cap is not None:
        return cap

    # Also try 'market_cap' key
    cap = load_cached_panel('yfinance', 'market_cap', start, end)
    if cap is not None:
        return cap

    logger.warning("Market cap data not in cache. "
                    "Run pipeline.load_panel(['cap']) first to populate.")
    return pd.DataFrame()


def _all_true_mask(dates: pd.DatetimeIndex, tickers) -> pd.DataFrame:
    """Create an all-True membership mask (fallback when no cap data)."""
    if len(tickers) == 0:
        return pd.DataFrame(index=dates, dtype=bool)
    return pd.DataFrame(True, index=dates, columns=tickers)


def get_universe_tickers(universe: str, date: str,
                         cap_df: Optional[pd.DataFrame] = None) -> list:
    """
    Get the list of tickers in a universe on a specific date.

    Parameters
    ----------
    universe : str
        Universe name.
    date : str
        Target date.
    cap_df : pd.DataFrame, optional
        Market cap panel.

    Returns
    -------
    list of str
        Ticker symbols in the universe on that date.
    """
    date_idx = pd.DatetimeIndex([pd.Timestamp(date)])
    mask = get_membership(universe, date_idx, cap_df)

    if mask.empty:
        return []

    row = mask.iloc[0]
    return list(row[row].index)
