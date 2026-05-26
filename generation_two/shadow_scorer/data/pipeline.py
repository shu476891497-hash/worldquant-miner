"""
Main data pipeline orchestrator for WQ Shadow Scorer.

Coordinates data download from multiple sources, normalizes to a common
panel format (DatetimeIndex × instrument columns), and manages the
Parquet cache layer.

Public API:
    load_panel(fields, universe, start, end) -> dict[str, pd.DataFrame]
"""

import logging
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from shadow_scorer.config import DATE_END, DATE_START, DEMO_MODE
from shadow_scorer.data.field_mapper import (
    get_field_mapping, group_fields_by_source, UNAVAILABLE,
)
from shadow_scorer.data.storage import load_cached_panel, save_panel
from shadow_scorer.data.yfinance_source import YFinanceSource
from shadow_scorer.data.simfin_source import SimFinSource
from shadow_scorer.data.wind_source import WindSource
from shadow_scorer.data.tushare_source import TushareSource

logger = logging.getLogger(__name__)


def load_panel(
    fields: List[str],
    universe: str = 'TOP3000',
    start: str = DATE_START,
    end: str = DATE_END,
) -> Dict[str, pd.DataFrame]:
    """
    Load panel data for given fields.

    Checks cache first, downloads from appropriate source if missing,
    normalizes all data to the same date index and instrument columns.

    Parameters
    ----------
    fields : list of str
        WQ field names (e.g., ['close', 'volume', 'sales']).
    universe : str
        Universe name (e.g., 'TOP3000').
    start : str
        Start date (YYYY-MM-DD).
    end : str
        End date (YYYY-MM-DD).

    Returns
    -------
    dict
        Maps field name to pd.DataFrame (DatetimeIndex × instrument columns).
        Missing/unavailable fields return NaN-filled DataFrame with log warning.
    """
    logger.info(f"load_panel: {len(fields)} fields, universe={universe}, "
                 f"{start} to {end}, demo={DEMO_MODE}")

    result: Dict[str, pd.DataFrame] = {}
    fields_to_download: Dict[str, List[str]] = {}  # source -> [field_ids]

    # Phase 1: Check cache for each field
    for field in fields:
        source, local_col, quality = get_field_mapping(field)
        cached = load_cached_panel(source, field, start, end)

        if cached is not None:
            result[field] = cached
            logger.debug(f"Cache hit: {field} ({source})")
        elif quality == UNAVAILABLE:
            # Field is unmapped — create NaN placeholder
            logger.warning(f"Field '{field}' is unavailable (no data source mapped)")
            result[field] = _create_nan_panel(start, end)
        else:
            # Need to download from source
            fields_to_download.setdefault(source, []).append(field)

    # Phase 2: Download missing fields grouped by source
    if fields_to_download:
        downloaded = _download_from_sources(fields_to_download, start, end)
        result.update(downloaded)

    # Phase 3: Normalize all panels to same date index and columns
    result = _normalize_panels(result, start, end)

    logger.info(f"load_panel complete: {len(result)} fields loaded, "
                 f"{sum(1 for v in result.values() if v.notna().any().any())} "
                 f"have data")

    return result


def _download_from_sources(
    fields_by_source: Dict[str, List[str]],
    start: str,
    end: str,
) -> Dict[str, pd.DataFrame]:
    """
    Download fields from their respective data sources.

    Parameters
    ----------
    fields_by_source : dict
        source_name -> list of field_ids to download.
    start : str
        Start date.
    end : str
        End date.

    Returns
    -------
    dict
        field_id -> pd.DataFrame.
    """
    result = {}
    sources = _get_sources(start, end)

    for source_name, field_ids in fields_by_source.items():
        source = sources.get(source_name)
        if source is None:
            logger.warning(f"Unknown data source: {source_name}")
            for fid in field_ids:
                result[fid] = _create_nan_panel(start, end)
            continue

        logger.info(f"Downloading from {source_name}: {field_ids}")

        for fid in field_ids:
            try:
                df = source.get_field(fid)
                if df is not None and not df.empty:
                    result[fid] = df
                    # Cache the result
                    try:
                        save_panel(df, source_name, fid, start, end)
                    except Exception as e:
                        logger.warning(f"Failed to cache {fid}: {e}")
                else:
                    logger.warning(f"No data returned for {fid} from {source_name}")
                    result[fid] = _create_nan_panel(start, end)
            except Exception as e:
                logger.error(f"Failed to download {fid} from {source_name}: {e}")
                result[fid] = _create_nan_panel(start, end)

    return result


# Source singletons (created lazily)
_SOURCE_INSTANCES: Dict[str, object] = {}


def _get_sources(start: str, end: str) -> Dict[str, object]:
    """Get or create data source instances."""
    global _SOURCE_INSTANCES

    if not _SOURCE_INSTANCES:
        _SOURCE_INSTANCES = {
            'yfinance': YFinanceSource(start=start, end=end),
            'simfin': SimFinSource(start=start, end=end),
            'wind': WindSource(start=start, end=end),
            'tushare': TushareSource(start=start, end=end),
        }

    return _SOURCE_INSTANCES


def reset_sources():
    """Reset source instances (useful for testing)."""
    global _SOURCE_INSTANCES
    _SOURCE_INSTANCES = {}


def _create_nan_panel(start: str, end: str) -> pd.DataFrame:
    """Create an empty NaN DataFrame with business day index."""
    dates = pd.bdate_range(start, end)
    return pd.DataFrame(index=dates, dtype=float)


def _normalize_panels(
    panels: Dict[str, pd.DataFrame],
    start: str,
    end: str,
) -> Dict[str, pd.DataFrame]:
    """
    Normalize all panels to the same date index and column set.

    Uses the union of all dates (within start/end) and the union of
    all instrument columns.

    Parameters
    ----------
    panels : dict
        field_id -> pd.DataFrame.
    start : str
        Start date.
    end : str
        End date.

    Returns
    -------
    dict
        Normalized panels.
    """
    if not panels:
        return panels

    # Find common date range (business days)
    target_dates = pd.bdate_range(start, end)

    # Find union of all columns (tickers)
    all_columns = set()
    for df in panels.values():
        if isinstance(df, pd.DataFrame) and not df.empty:
            all_columns.update(df.columns)

    if not all_columns:
        return panels

    all_columns = sorted(all_columns)

    # Normalize each panel
    normalized = {}
    for field, df in panels.items():
        if not isinstance(df, pd.DataFrame) or df.empty:
            normalized[field] = pd.DataFrame(
                index=target_dates, columns=all_columns, dtype=float
            )
            continue

        # Ensure DatetimeIndex without timezone
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)
        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)

        # Reindex to target dates and columns
        normalized[field] = df.reindex(index=target_dates, columns=all_columns)

    return normalized


# ============================================================================
# CLI entry point
# ============================================================================

if __name__ == '__main__':
    import argparse
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    )

    parser = argparse.ArgumentParser(
        description='WQ Shadow Scorer Data Pipeline',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download demo data (50 tickers)
  python -m shadow_scorer.data.pipeline --demo

  # Download specific fields
  python -m shadow_scorer.data.pipeline --fields close volume returns

  # Full download (3500+ tickers) — takes hours!
  python -m shadow_scorer.data.pipeline --full

  # Check cache status
  python -m shadow_scorer.data.pipeline --status
        """,
    )

    parser.add_argument('--demo', action='store_true', default=True,
                        help='Use demo mode (~50 tickers)')
    parser.add_argument('--full', action='store_true',
                        help='Full download (~3500 tickers) — SLOW')
    parser.add_argument('--fields', nargs='+', default=None,
                        help='Specific fields to download')
    parser.add_argument('--start', default=DATE_START,
                        help=f'Start date (default: {DATE_START})')
    parser.add_argument('--end', default=DATE_END,
                        help=f'End date (default: {DATE_END})')
    parser.add_argument('--universe', default='TOP3000',
                        help='Universe (default: TOP3000)')
    parser.add_argument('--status', action='store_true',
                        help='Show cache status and exit')

    args = parser.parse_args()

    if args.status:
        from shadow_scorer.data.storage import list_cache
        entries = list_cache()
        if not entries:
            print("Cache is empty.")
        else:
            print(f"Cache: {len(entries)} files")
            for e in entries:
                print(f"  {e['name']:50s} {e['size_mb']:>8.2f} MB  "
                      f"age={e['age_hours']:.1f}h  source={e['source']}")
        sys.exit(0)

    # Set demo mode
    import shadow_scorer.config as cfg
    if args.full:
        cfg.DEMO_MODE = False
        print("=== FULL MODE: ~3500 tickers ===")
        print("WARNING: This will take a long time and use significant bandwidth.")
        response = input("Continue? [y/N]: ")
        if response.lower() != 'y':
            print("Aborted.")
            sys.exit(0)
    else:
        cfg.DEMO_MODE = True
        print("=== DEMO MODE: ~50 tickers ===")

    # Default fields to download
    if args.fields is None:
        default_fields = [
            'close', 'open', 'high', 'low', 'volume',
            'vwap', 'returns', 'cap',
        ]
    else:
        default_fields = args.fields

    print(f"\nDownloading: {default_fields}")
    print(f"Date range: {args.start} to {args.end}")
    print(f"Universe: {args.universe}\n")

    # Reset sources to pick up new config
    reset_sources()

    # Run the pipeline
    data = load_panel(
        fields=default_fields,
        universe=args.universe,
        start=args.start,
        end=args.end,
    )

    # Report results
    print("\n=== Download Complete ===")
    for field, df in data.items():
        n_rows = len(df)
        n_cols = len(df.columns)
        pct_filled = (df.notna().sum().sum() / max(df.size, 1) * 100)
        print(f"  {field:20s}: {n_rows:5d} dates × {n_cols:4d} tickers "
              f"({pct_filled:.1f}% filled)")

    # Show cache status
    from shadow_scorer.data.storage import list_cache
    entries = list_cache()
    total_mb = sum(e['size_mb'] for e in entries)
    print(f"\nCache: {len(entries)} files, {total_mb:.1f} MB total")
