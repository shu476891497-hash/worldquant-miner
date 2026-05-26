"""
yfinance data source — downloads daily OHLCV and market cap data for US equities.

Handles batch downloading, WQ field name mapping, and panel construction.
Uses demo mode (~50 tickers) or full mode (~3500 tickers) controlled by config.

Key mappings:
    close, open, high, low, volume -> direct yfinance OHLCV
    vwap -> approximated as (high + low + close) / 3
    returns -> pct_change(close)
    cap -> market_cap from yfinance info
"""

import logging
import time
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from shadow_scorer.config import (
    CACHE_DIR, DATE_END, DATE_START, DEMO_MODE, DEMO_TICKERS,
    YFINANCE_BATCH_SIZE,
)

logger = logging.getLogger(__name__)

# Fields this source can provide
AVAILABLE_FIELDS = {
    'close', 'open', 'high', 'low', 'volume',
    'vwap', 'returns', 'cap',
    'sector', 'industry', 'subindustry',
}

# Mapping from WQ field name to yfinance column
_YF_COLUMN_MAP = {
    'close':  'Close',
    'open':   'Open',
    'high':   'High',
    'low':    'Low',
    'volume': 'Volume',
}


# ============================================================================
# Ticker Lists
# ============================================================================

# Extended S&P 500 + large/mid cap universe (~3500 tickers)
# For full mode, we scrape S&P 500 from Wikipedia + supplement
def get_sp500_tickers() -> List[str]:
    """Get current S&P 500 component tickers."""
    try:
        import urllib.request
        import re

        url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        html = urllib.request.urlopen(req, timeout=15).read().decode('utf-8')

        # Parse the first table for tickers
        # Look for ticker symbols in the table
        tickers = []
        # Find all rows in the first wikitable
        table_match = re.search(r'<table[^>]*class="wikitable[^"]*"[^>]*>(.*?)</table>',
                                html, re.DOTALL)
        if table_match:
            rows = re.findall(r'<tr>(.*?)</tr>', table_match.group(1), re.DOTALL)
            for row in rows[1:]:  # Skip header
                cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
                if cells:
                    # First cell contains the ticker, possibly in an <a> tag
                    ticker_html = cells[0].strip()
                    ticker_match = re.search(r'>([A-Z.]+)<', ticker_html)
                    if ticker_match:
                        ticker = ticker_match.group(1).replace('.', '-')
                        tickers.append(ticker)
                    else:
                        # Plain text
                        ticker = re.sub(r'<[^>]+>', '', ticker_html).strip()
                        if ticker and ticker.replace('-', '').replace('.', '').isalpha():
                            ticker = ticker.replace('.', '-')
                            tickers.append(ticker)

        logger.info(f"Fetched {len(tickers)} S&P 500 tickers from Wikipedia")
        return tickers if tickers else _FALLBACK_SP500

    except Exception as e:
        logger.warning(f"Failed to fetch S&P 500 list: {e}, using fallback")
        return _FALLBACK_SP500


# Fallback S&P 500 tickers (top ~100 by weight as of 2024)
_FALLBACK_SP500 = [
    'AAPL', 'MSFT', 'AMZN', 'NVDA', 'GOOGL', 'GOOG', 'META', 'BRK-B', 'UNH', 'XOM',
    'LLY', 'JPM', 'JNJ', 'V', 'PG', 'MA', 'AVGO', 'HD', 'CVX', 'MRK',
    'ABBV', 'COST', 'PEP', 'KO', 'ADBE', 'WMT', 'BAC', 'CRM', 'MCD', 'CSCO',
    'TMO', 'ACN', 'NFLX', 'LIN', 'AMD', 'ABT', 'ORCL', 'DHR', 'CMCSA', 'TXN',
    'WFC', 'NKE', 'DIS', 'PM', 'INTC', 'VZ', 'NEE', 'UPS', 'QCOM', 'RTX',
    'CAT', 'BA', 'SPGI', 'BMY', 'HON', 'AMGN', 'GE', 'INTU', 'LOW', 'T',
    'SYK', 'ELV', 'BKNG', 'PFE', 'ISRG', 'MDLZ', 'DE', 'GS', 'AMAT', 'MS',
    'ADP', 'BLK', 'GILD', 'CB', 'TJX', 'MMC', 'VRTX', 'LRCX', 'REGN', 'SLB',
    'C', 'SCHW', 'CI', 'ZTS', 'SO', 'DUK', 'BDX', 'MO', 'TMUS', 'PLD',
    'AON', 'CL', 'ITW', 'CME', 'BSX', 'SHW', 'EQIX', 'SNPS', 'PYPL', 'MCK',
]

# Additional mid/large cap tickers to supplement S&P 500 toward ~3500
_SUPPLEMENTAL_TICKERS = [
    'ABNB', 'ACGL', 'AFL', 'AIG', 'AIZ', 'AJG', 'ALGN', 'ALL', 'ALLE', 'ANET',
    'ANSS', 'APD', 'APH', 'ARE', 'ATO', 'ATVI', 'AWK', 'AXP', 'AZO', 'BALL',
    'BAX', 'BBWI', 'BBY', 'BEN', 'BF-B', 'BIIB', 'BIO', 'BR', 'BRO', 'BWA',
    'CAH', 'CARR', 'CBOE', 'CBRE', 'CCI', 'CCL', 'CDNS', 'CDW', 'CE', 'CEG',
    'CF', 'CFG', 'CHD', 'CHRW', 'CHTR', 'CINF', 'CLX', 'CMA', 'CMG', 'CMI',
    'CNC', 'CNP', 'COF', 'COO', 'COP', 'CPB', 'CPRT', 'CPT', 'CRL', 'CSCO',
    'CSGP', 'CSX', 'CTAS', 'CTLT', 'CTRA', 'CTSH', 'CTVA', 'CVS', 'CZR', 'D',
    'DAL', 'DD', 'DDOG', 'DFS', 'DG', 'DGX', 'DHI', 'DISH', 'DLTR', 'DOV',
    'DOW', 'DPZ', 'DRI', 'DTE', 'DVA', 'DVN', 'DXC', 'DXCM', 'EA', 'EBAY',
    'ECL', 'ED', 'EFX', 'EIX', 'EMN', 'EMR', 'ENPH', 'EOG', 'EPAM', 'EQR',
    'ES', 'ESS', 'ETN', 'ETR', 'EVRG', 'EW', 'EXC', 'EXPD', 'EXPE', 'EXR',
    'F', 'FANG', 'FAST', 'FBHS', 'FCX', 'FDS', 'FDX', 'FE', 'FFIV', 'FIS',
    'FISV', 'FITB', 'FLT', 'FMC', 'FOX', 'FOXA', 'FRC', 'FRT', 'FTNT', 'FTV',
    'GD', 'GEN', 'GILD', 'GIS', 'GL', 'GLW', 'GM', 'GNRC', 'GPC', 'GPN',
    'GRMN', 'GWW', 'HAL', 'HAS', 'HBAN', 'HCA', 'HOLX', 'HPE', 'HPQ', 'HRL',
    'HSIC', 'HST', 'HSY', 'HUM', 'HWM', 'IBM', 'ICE', 'IDXX', 'IEX', 'IFF',
    'ILMN', 'INCY', 'IP', 'IPG', 'IQV', 'IR', 'IRM', 'ISRG', 'IT', 'ITW',
    'IVZ', 'J', 'JBHT', 'JCI', 'JKHY', 'JNPR', 'K', 'KDP', 'KEY', 'KEYS',
    'KHC', 'KIM', 'KLAC', 'KMB', 'KMI', 'KMX', 'KR', 'L', 'LDOS', 'LEN',
    'LH', 'LHX', 'LKQ', 'LMT', 'LNT', 'LUMN', 'LUV', 'LVS', 'LW', 'LYB',
]


def get_ticker_list(full_mode: bool = False) -> List[str]:
    """
    Get the ticker list based on mode.

    Parameters
    ----------
    full_mode : bool
        If True, attempt to get ~3500 tickers. If False, use demo list (~50).

    Returns
    -------
    list of str
        Ticker symbols.
    """
    if not full_mode:
        return DEMO_TICKERS.copy()

    # Full mode: S&P 500 + supplements
    tickers = get_sp500_tickers()
    tickers.extend(_SUPPLEMENTAL_TICKERS)

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for t in tickers:
        if t not in seen:
            seen.add(t)
            unique.append(t)

    logger.info(f"Full ticker list: {len(unique)} tickers")
    return unique


# ============================================================================
# Data Download
# ============================================================================

def download_ohlcv(tickers: Optional[List[str]] = None,
                   start: str = DATE_START,
                   end: str = DATE_END,
                   batch_size: int = YFINANCE_BATCH_SIZE) -> Dict[str, pd.DataFrame]:
    """
    Download daily OHLCV data from yfinance in batches.

    Parameters
    ----------
    tickers : list of str, optional
        Ticker symbols. If None, uses config-based list.
    start : str
        Start date.
    end : str
        End date.
    batch_size : int
        Number of tickers per download batch.

    Returns
    -------
    dict
        Maps field name ('close', 'open', etc.) to panel DataFrame
        with DatetimeIndex × ticker columns.
    """
    import yfinance as yf

    if tickers is None:
        tickers = get_ticker_list(full_mode=not DEMO_MODE)

    logger.info(f"Downloading OHLCV for {len(tickers)} tickers "
                 f"({start} to {end}), batch_size={batch_size}")

    all_data = {}
    failed_tickers = []

    # Download in batches
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(tickers) + batch_size - 1) // batch_size

        logger.info(f"Batch {batch_num}/{total_batches}: "
                     f"downloading {len(batch)} tickers...")

        try:
            data = yf.download(
                batch,
                start=start,
                end=end,
                auto_adjust=True,
                group_by='column',
                threads=True,
                progress=False,
            )

            if data.empty:
                logger.warning(f"Batch {batch_num}: no data returned")
                failed_tickers.extend(batch)
                continue

            # yfinance returns MultiIndex columns (field, ticker) for multi-ticker
            if isinstance(data.columns, pd.MultiIndex):
                for field in ['Close', 'Open', 'High', 'Low', 'Volume']:
                    if field in data.columns.get_level_values(0):
                        panel = data[field].copy()
                        panel.index = pd.to_datetime(panel.index).tz_localize(None)
                        wq_field = field.lower()
                        if wq_field not in all_data:
                            all_data[wq_field] = panel
                        else:
                            all_data[wq_field] = pd.concat(
                                [all_data[wq_field], panel], axis=1
                            )
            else:
                # Single ticker case
                ticker = batch[0]
                for field in ['Close', 'Open', 'High', 'Low', 'Volume']:
                    if field in data.columns:
                        panel = data[[field]].copy()
                        panel.columns = [ticker]
                        panel.index = pd.to_datetime(panel.index).tz_localize(None)
                        wq_field = field.lower()
                        if wq_field not in all_data:
                            all_data[wq_field] = panel
                        else:
                            all_data[wq_field] = pd.concat(
                                [all_data[wq_field], panel], axis=1
                            )

        except Exception as e:
            logger.error(f"Batch {batch_num} failed: {e}")
            failed_tickers.extend(batch)

        # Rate limiting pause between batches
        if i + batch_size < len(tickers):
            time.sleep(1)

    if failed_tickers:
        logger.warning(f"{len(failed_tickers)} tickers failed: "
                        f"{failed_tickers[:10]}...")

    # Deduplicate columns in case of overlap
    for field in all_data:
        df = all_data[field]
        if df.columns.duplicated().any():
            all_data[field] = df.loc[:, ~df.columns.duplicated(keep='first')]

    logger.info(f"Downloaded OHLCV: {list(all_data.keys())}, "
                 f"~{len(all_data.get('close', pd.DataFrame()))} trading days")

    return all_data


def compute_derived_fields(ohlcv: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
    """
    Compute derived fields from raw OHLCV data.

    Parameters
    ----------
    ohlcv : dict
        Maps field name to panel DataFrame (from download_ohlcv).

    Returns
    -------
    dict
        Updated dict with additional derived fields.
    """
    result = dict(ohlcv)

    # VWAP approximation: (High + Low + Close) / 3
    if all(f in result for f in ['high', 'low', 'close']):
        result['vwap'] = (result['high'] + result['low'] + result['close']) / 3.0
        logger.info("Computed VWAP approximation: (H+L+C)/3")

    # Returns: percentage change of close prices
    if 'close' in result:
        result['returns'] = result['close'].pct_change()
        logger.info("Computed returns from close prices")

    return result


def download_market_cap(tickers: Optional[List[str]] = None,
                        close_df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """
    Construct market cap panel from yfinance.

    Uses close price × shares outstanding. For efficiency, fetches
    shares outstanding once per ticker and multiplies by daily close.

    Parameters
    ----------
    tickers : list of str, optional
        Ticker symbols.
    close_df : pd.DataFrame, optional
        Pre-downloaded close prices. If None, will download.

    Returns
    -------
    pd.DataFrame
        Market cap panel (DatetimeIndex × tickers).
    """
    import yfinance as yf

    if tickers is None:
        tickers = get_ticker_list(full_mode=not DEMO_MODE)

    if close_df is None:
        logger.info("No close prices provided, downloading for market cap...")
        ohlcv = download_ohlcv(tickers)
        close_df = ohlcv.get('close', pd.DataFrame())

    if close_df.empty:
        logger.warning("Empty close prices, cannot compute market cap")
        return pd.DataFrame()

    # Get shares outstanding for each ticker
    shares = {}
    for ticker in tickers:
        try:
            info = yf.Ticker(ticker).info
            so = info.get('sharesOutstanding', None)
            if so and so > 0:
                shares[ticker] = so
        except Exception:
            pass

    if not shares:
        logger.warning("Could not get shares outstanding for any ticker")
        return pd.DataFrame(index=close_df.index, columns=close_df.columns,
                            data=np.nan)

    # Market cap = close × shares outstanding
    cap_df = pd.DataFrame(index=close_df.index, columns=close_df.columns,
                          dtype=float)
    for ticker, so in shares.items():
        if ticker in close_df.columns:
            cap_df[ticker] = close_df[ticker] * so

    logger.info(f"Computed market cap for {len(shares)}/{len(tickers)} tickers")
    return cap_df


def download_sector_info(tickers: Optional[List[str]] = None) -> Dict[str, pd.Series]:
    """
    Download sector/industry classification for each ticker.

    Returns static series (same value for all dates per ticker).

    Parameters
    ----------
    tickers : list of str, optional
        Ticker symbols.

    Returns
    -------
    dict
        Maps 'sector', 'industry', 'subindustry' to pd.Series (ticker -> value).
    """
    import yfinance as yf

    if tickers is None:
        tickers = get_ticker_list(full_mode=not DEMO_MODE)

    sectors = {}
    industries = {}
    subindustries = {}

    for ticker in tickers:
        try:
            info = yf.Ticker(ticker).info
            sectors[ticker] = info.get('sector', 'Unknown')
            industries[ticker] = info.get('industry', 'Unknown')
            # yfinance doesn't have GICS subindustry; use industry as proxy
            subindustries[ticker] = info.get('industry', 'Unknown')
        except Exception:
            sectors[ticker] = 'Unknown'
            industries[ticker] = 'Unknown'
            subindustries[ticker] = 'Unknown'

    return {
        'sector': pd.Series(sectors, name='sector'),
        'industry': pd.Series(industries, name='industry'),
        'subindustry': pd.Series(subindustries, name='subindustry'),
    }


class YFinanceSource:
    """
    yfinance data source wrapper.

    Provides a unified interface for downloading and accessing
    yfinance data within the pipeline.
    """

    def __init__(self, tickers: Optional[List[str]] = None,
                 start: str = DATE_START, end: str = DATE_END):
        self.tickers = tickers or get_ticker_list(full_mode=not DEMO_MODE)
        self.start = start
        self.end = end
        self._ohlcv: Optional[Dict[str, pd.DataFrame]] = None
        self._cap: Optional[pd.DataFrame] = None
        self._sector_info: Optional[Dict[str, pd.Series]] = None

    def get_field(self, field: str) -> pd.DataFrame:
        """
        Get a specific field's panel data.

        Parameters
        ----------
        field : str
            WQ field name (e.g., 'close', 'vwap', 'returns', 'cap').

        Returns
        -------
        pd.DataFrame
            Panel data (DatetimeIndex × tickers).
        """
        if field in ('sector', 'industry', 'subindustry'):
            return self._get_group_field(field)

        if field == 'cap':
            return self._get_market_cap()

        # OHLCV or derived fields
        if self._ohlcv is None:
            self._ohlcv = download_ohlcv(self.tickers, self.start, self.end)
            self._ohlcv = compute_derived_fields(self._ohlcv)

        if field in self._ohlcv:
            return self._ohlcv[field]

        logger.warning(f"yfinance: field '{field}' not available")
        return pd.DataFrame()

    def _get_market_cap(self) -> pd.DataFrame:
        """Get or compute market cap."""
        if self._cap is None:
            close = self.get_field('close')
            self._cap = download_market_cap(self.tickers, close)
        return self._cap

    def _get_group_field(self, field: str) -> pd.DataFrame:
        """Get sector/industry as a panel (constant across dates)."""
        if self._sector_info is None:
            self._sector_info = download_sector_info(self.tickers)

        if self._ohlcv is None:
            self._ohlcv = download_ohlcv(self.tickers, self.start, self.end)
            self._ohlcv = compute_derived_fields(self._ohlcv)

        # Create panel with constant group values across all dates
        dates = self._ohlcv.get('close', pd.DataFrame()).index
        if dates.empty:
            return pd.DataFrame()

        series = self._sector_info.get(field, pd.Series())
        panel = pd.DataFrame(
            index=dates,
            columns=series.index,
            data=np.tile(series.values, (len(dates), 1)),
        )
        return panel

    @property
    def available_fields(self) -> set:
        """Fields this source can provide."""
        return AVAILABLE_FIELDS.copy()
