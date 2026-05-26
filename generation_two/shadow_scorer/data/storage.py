"""
Parquet-based cache storage for panel data.

Handles save/load of DataFrames to/from Parquet files with:
- Incremental update support (append new dates)
- Cache invalidation by age (default: 7 days)
- Structured file naming: {source}_{field}_{start}_{end}.parquet
"""

import logging
import time
from pathlib import Path
from typing import Optional

import pandas as pd

from shadow_scorer.config import CACHE_DIR, CACHE_MAX_AGE_SECONDS

logger = logging.getLogger(__name__)


def _cache_path(source: str, field: str, start: str, end: str) -> Path:
    """Build cache file path for a given source/field/date range."""
    safe_field = field.replace('/', '_').replace('\\', '_')
    fname = f"{source}_{safe_field}_{start}_{end}.parquet"
    return CACHE_DIR / fname


def _find_cached_file(source: str, field: str) -> Optional[Path]:
    """Find any cached file for this source+field, regardless of date range."""
    pattern = f"{source}_{field}_*.parquet"
    matches = list(CACHE_DIR.glob(pattern))
    if matches:
        # Return the most recently modified one
        return max(matches, key=lambda p: p.stat().st_mtime)
    return None


def is_cache_valid(path: Path, max_age_seconds: int = CACHE_MAX_AGE_SECONDS) -> bool:
    """Check if a cache file exists and is not too old."""
    if not path.exists():
        return False
    age = time.time() - path.stat().st_mtime
    return age < max_age_seconds


def save_panel(df: pd.DataFrame, source: str, field: str,
               start: str, end: str) -> Path:
    """
    Save a panel DataFrame to Parquet cache.

    Parameters
    ----------
    df : pd.DataFrame
        Panel data with DatetimeIndex rows and ticker columns.
    source : str
        Data source name (e.g., 'yfinance', 'simfin').
    field : str
        Field name (e.g., 'close', 'volume').
    start : str
        Start date string.
    end : str
        End date string.

    Returns
    -------
    Path
        Path to the saved Parquet file.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _cache_path(source, field, start, end)

    try:
        df.to_parquet(path, engine='pyarrow')
        logger.info(f"Cached {source}/{field} -> {path.name} "
                     f"({len(df)} rows, {len(df.columns)} cols)")
    except Exception as e:
        logger.error(f"Failed to save cache {path}: {e}")
        raise

    return path


def load_cached_panel(source: str, field: str,
                      start: str, end: str,
                      max_age_seconds: int = CACHE_MAX_AGE_SECONDS) -> Optional[pd.DataFrame]:
    """
    Load a panel DataFrame from Parquet cache if valid.

    Parameters
    ----------
    source : str
        Data source name.
    field : str
        Field name.
    start : str
        Start date string.
    end : str
        End date string.
    max_age_seconds : int
        Maximum cache age before invalidation.

    Returns
    -------
    pd.DataFrame or None
        Cached data, or None if cache miss / expired.
    """
    # First try exact match
    path = _cache_path(source, field, start, end)
    if is_cache_valid(path, max_age_seconds):
        try:
            df = pd.read_parquet(path, engine='pyarrow')
            logger.debug(f"Cache hit: {path.name}")
            return df
        except Exception as e:
            logger.warning(f"Cache file corrupted, will re-download: {e}")
            path.unlink(missing_ok=True)
            return None

    # Try any cached file for this source+field (may have different date range)
    alt_path = _find_cached_file(source, field)
    if alt_path and is_cache_valid(alt_path, max_age_seconds):
        try:
            df = pd.read_parquet(alt_path, engine='pyarrow')
            # Filter to requested date range
            df.index = pd.to_datetime(df.index)
            mask = (df.index >= start) & (df.index <= end)
            filtered = df.loc[mask]
            if len(filtered) > 0:
                logger.debug(f"Cache partial hit: {alt_path.name} "
                              f"(filtered {len(df)}->{len(filtered)} rows)")
                return filtered
        except Exception as e:
            logger.warning(f"Failed to read alt cache {alt_path}: {e}")

    return None


def append_to_cache(new_df: pd.DataFrame, source: str, field: str,
                    start: str, end: str) -> Path:
    """
    Append new dates to an existing cache file (incremental update).

    If no existing cache, creates a new one. Deduplicates by index.

    Parameters
    ----------
    new_df : pd.DataFrame
        New data to append.
    source : str
        Data source name.
    field : str
        Field name.
    start : str
        Overall start date.
    end : str
        Overall end date.

    Returns
    -------
    Path
        Path to the updated Parquet file.
    """
    path = _cache_path(source, field, start, end)

    if path.exists():
        try:
            existing = pd.read_parquet(path, engine='pyarrow')
            existing.index = pd.to_datetime(existing.index)
            new_df.index = pd.to_datetime(new_df.index)

            # Combine columns (union of tickers)
            all_cols = list(set(existing.columns) | set(new_df.columns))

            # Concat and deduplicate
            combined = pd.concat([existing, new_df], axis=0)
            combined = combined[~combined.index.duplicated(keep='last')]
            combined = combined.sort_index()

            # Ensure all columns present
            for col in all_cols:
                if col not in combined.columns:
                    combined[col] = float('nan')

            logger.info(f"Incremental update: {path.name} "
                         f"({len(existing)}->{len(combined)} rows)")
            return save_panel(combined, source, field, start, end)
        except Exception as e:
            logger.warning(f"Failed incremental update, overwriting: {e}")

    return save_panel(new_df, source, field, start, end)


def clear_cache(source: Optional[str] = None, field: Optional[str] = None):
    """
    Clear cache files, optionally filtered by source and/or field.

    Parameters
    ----------
    source : str, optional
        If given, only clear files from this source.
    field : str, optional
        If given, only clear files for this field.
    """
    if source and field:
        pattern = f"{source}_{field}_*.parquet"
    elif source:
        pattern = f"{source}_*.parquet"
    elif field:
        pattern = f"*_{field}_*.parquet"
    else:
        pattern = "*.parquet"

    count = 0
    for f in CACHE_DIR.glob(pattern):
        f.unlink()
        count += 1

    logger.info(f"Cleared {count} cache files (pattern: {pattern})")


def list_cache() -> list:
    """List all cached files with their metadata."""
    entries = []
    for f in sorted(CACHE_DIR.glob("*.parquet")):
        stat = f.stat()
        parts = f.stem.split('_', 2)
        entries.append({
            'path': str(f),
            'name': f.name,
            'source': parts[0] if len(parts) > 0 else 'unknown',
            'field': parts[1] if len(parts) > 1 else 'unknown',
            'size_mb': round(stat.st_size / (1024 * 1024), 2),
            'age_hours': round((time.time() - stat.st_mtime) / 3600, 1),
        })
    return entries
