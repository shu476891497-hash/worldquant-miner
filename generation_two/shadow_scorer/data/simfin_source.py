"""
SimFin data source — downloads quarterly/annual fundamental data for US equities.

Maps to WQ fields: sales, ebitda, operating_income, income, equity, assets,
debt_lt, capex, cashflow_dividends, etc.

Quarterly data is forward-filled to daily frequency (point-in-time, no look-ahead).
Uses the simfin Python package (pip install simfin).
"""

import logging
import os
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from shadow_scorer.config import DATE_END, DATE_START, DEMO_MODE, DEMO_TICKERS, SIMFIN_API_KEY

logger = logging.getLogger(__name__)

# Fields this source can provide
AVAILABLE_FIELDS = {
    'sales', 'ebitda', 'operating_income', 'income', 'gross_profit',
    'net_income_adjusted',
    'equity', 'assets', 'debt_lt',
    'capex', 'cashflow_dividends', 'cashflow', 'cashflow_op',
    'cashflow_fin', 'cashflow_invst',
}

# Mapping from WQ field -> SimFin column name
_SIMFIN_INCOME_MAP = {
    'sales':            'Revenue',
    'ebitda':           'EBITDA',
    'operating_income': 'Operating Income (Loss)',
    'income':           'Net Income',
    'net_income_adjusted': 'Net Income',
    'gross_profit':     'Gross Profit',
}

_SIMFIN_BALANCE_MAP = {
    'equity':  'Total Equity',
    'assets':  'Total Assets',
    'debt_lt': 'Long Term Debt',
}

_SIMFIN_CASHFLOW_MAP = {
    'capex':              'Capital Expenditures',
    'cashflow_dividends': 'Dividends Paid',
    'cashflow':           'Net Cash from Operating Activities',
    'cashflow_op':        'Net Cash from Operating Activities',
    'cashflow_fin':       'Net Cash from Financing Activities',
    'cashflow_invst':     'Net Cash from Investing Activities',
}


def _get_api_key() -> Optional[str]:
    """Get SimFin API key from config or environment."""
    key = SIMFIN_API_KEY or os.environ.get('SIMFIN_API_KEY')
    if not key:
        logger.warning(
            "SimFin API key not configured. Set SIMFIN_API_KEY environment "
            "variable or shadow_scorer.config.SIMFIN_API_KEY. "
            "Register free at https://simfin.com"
        )
    return key


def _try_import_simfin():
    """Try to import simfin, return None if not installed."""
    try:
        import simfin as sf
        return sf
    except ImportError:
        logger.warning(
            "simfin package not installed. Install with: pip install simfin"
        )
        return None


def _fundamental_to_daily_panel(
    quarterly_df: pd.DataFrame,
    column: str,
    dates: pd.DatetimeIndex,
    tickers: List[str],
) -> pd.DataFrame:
    """
    Convert quarterly fundamental data to daily panel by forward-filling.

    Point-in-time: each quarterly value is only available after its report date,
    not before. This prevents look-ahead bias.

    Parameters
    ----------
    quarterly_df : pd.DataFrame
        SimFin quarterly data with 'Ticker', 'Report Date', and the target column.
    column : str
        The SimFin column name to extract.
    dates : pd.DatetimeIndex
        Target daily dates.
    tickers : list of str
        Target tickers.

    Returns
    -------
    pd.DataFrame
        Daily panel (dates × tickers) with forward-filled values.
    """
    panel = pd.DataFrame(index=dates, columns=tickers, dtype=float)

    if column not in quarterly_df.columns:
        logger.debug(f"Column '{column}' not in quarterly data")
        return panel

    for ticker in tickers:
        ticker_data = quarterly_df[quarterly_df['Ticker'] == ticker]
        if ticker_data.empty:
            continue

        # Use Report Date as the point-in-time date
        if 'Report Date' in ticker_data.columns:
            date_col = 'Report Date'
        elif 'Publish Date' in ticker_data.columns:
            date_col = 'Publish Date'
        else:
            # Fallback to fiscal period end date
            date_col = ticker_data.columns[
                ticker_data.columns.str.contains('Date', case=False)
            ]
            if len(date_col) == 0:
                continue
            date_col = date_col[0]

        ts = ticker_data.set_index(pd.to_datetime(ticker_data[date_col]))[column]
        ts = ts.sort_index()
        ts = ts[~ts.index.duplicated(keep='last')]

        # Reindex to daily dates and forward-fill
        ts_daily = ts.reindex(dates, method='ffill')
        panel[ticker] = ts_daily

    return panel


class SimFinSource:
    """
    SimFin data source wrapper.

    Downloads quarterly income statement, balance sheet, and cash flow data
    and converts to daily panel format via forward-fill.
    """

    def __init__(self, tickers: Optional[List[str]] = None,
                 start: str = DATE_START, end: str = DATE_END):
        self.tickers = tickers or (DEMO_TICKERS if DEMO_MODE else [])
        self.start = start
        self.end = end
        self._income_df: Optional[pd.DataFrame] = None
        self._balance_df: Optional[pd.DataFrame] = None
        self._cashflow_df: Optional[pd.DataFrame] = None
        self._dates: Optional[pd.DatetimeIndex] = None
        self._initialized = False

    def _ensure_dates(self) -> pd.DatetimeIndex:
        """Get or create the target date index."""
        if self._dates is None:
            self._dates = pd.bdate_range(self.start, self.end)
        return self._dates

    def _initialize(self):
        """Download all fundamental data from SimFin."""
        if self._initialized:
            return

        sf = _try_import_simfin()
        api_key = _get_api_key()

        if sf is None or api_key is None:
            logger.warning("SimFin not available, returning empty data")
            self._initialized = True
            return

        try:
            sf.set_api_key(api_key)
            sf.set_data_dir('~/.simfin_data/')

            logger.info(f"Downloading SimFin income statements for "
                         f"{len(self.tickers)} tickers...")
            self._income_df = sf.load_income(
                variant='quarterly',
                market='us',
            )

            logger.info("Downloading SimFin balance sheets...")
            self._balance_df = sf.load_balance(
                variant='quarterly',
                market='us',
            )

            logger.info("Downloading SimFin cash flow statements...")
            self._cashflow_df = sf.load_cashflow(
                variant='quarterly',
                market='us',
            )

            self._initialized = True
            logger.info("SimFin data download complete")

        except Exception as e:
            logger.error(f"SimFin download failed: {e}")
            self._initialized = True

    def get_field(self, field: str) -> pd.DataFrame:
        """
        Get a specific fundamental field as daily panel.

        Parameters
        ----------
        field : str
            WQ field name (e.g., 'sales', 'ebitda', 'equity').

        Returns
        -------
        pd.DataFrame
            Panel data (DatetimeIndex × tickers), forward-filled from quarterly.
        """
        self._initialize()
        dates = self._ensure_dates()

        # Determine which SimFin dataset and column to use
        if field in _SIMFIN_INCOME_MAP:
            source_df = self._income_df
            column = _SIMFIN_INCOME_MAP[field]
        elif field in _SIMFIN_BALANCE_MAP:
            source_df = self._balance_df
            column = _SIMFIN_BALANCE_MAP[field]
        elif field in _SIMFIN_CASHFLOW_MAP:
            source_df = self._cashflow_df
            column = _SIMFIN_CASHFLOW_MAP[field]
        else:
            logger.warning(f"SimFin: field '{field}' not mapped")
            return pd.DataFrame(index=dates, columns=self.tickers, dtype=float)

        if source_df is None or source_df.empty:
            logger.debug(f"SimFin: no data available for '{field}'")
            return pd.DataFrame(index=dates, columns=self.tickers, dtype=float)

        # Handle SimFin DataFrame format (may have MultiIndex)
        if isinstance(source_df.index, pd.MultiIndex):
            # SimFin uses (Ticker, Report Date) MultiIndex
            flat_df = source_df.reset_index()
        else:
            flat_df = source_df.copy()

        return _fundamental_to_daily_panel(flat_df, column, dates, self.tickers)

    @property
    def available_fields(self) -> set:
        """Fields this source can provide."""
        return AVAILABLE_FIELDS.copy()
