"""
Tushare data source — stub implementation.

Tushare is a Chinese financial data platform. This module provides
a stub interface that logs warnings and returns empty DataFrames.

Token placeholder: ddd1b26b20ff085ac9b60c9bd902ae76bbff60910863e8cc0168da53
"""

import logging
from typing import List, Optional

import pandas as pd

from shadow_scorer.config import DATE_END, DATE_START, TUSHARE_TOKEN

logger = logging.getLogger(__name__)

# Placeholder — Tushare fields that could be mapped
AVAILABLE_FIELDS: set = set()  # No fields available until configured


class TushareSource:
    """
    Tushare data source stub.

    Returns empty DataFrames for all requests. When Tushare is properly
    configured, this class should be replaced with actual API calls.

    Configuration:
        Set TUSHARE_TOKEN in shadow_scorer/config.py or via environment variable.
        Currently set to: {TUSHARE_TOKEN}
    """

    def __init__(self, tickers: Optional[List[str]] = None,
                 start: str = DATE_START, end: str = DATE_END):
        self.tickers = tickers or []
        self.start = start
        self.end = end
        self._warned = False

    def _warn_once(self):
        """Log a warning about Tushare not being configured."""
        if not self._warned:
            logger.warning(
                "Tushare API not configured. This is a stub implementation. "
                f"Token placeholder: {TUSHARE_TOKEN}. "
                "To use Tushare data, implement TushareSource.get_field() "
                "with actual Tushare pro API calls."
            )
            self._warned = True

    def get_field(self, field: str) -> pd.DataFrame:
        """
        Get a field from Tushare (stub — returns empty DataFrame).

        Parameters
        ----------
        field : str
            WQ field name.

        Returns
        -------
        pd.DataFrame
            Empty DataFrame with business day index.
        """
        self._warn_once()
        dates = pd.bdate_range(self.start, self.end)
        logger.debug(f"Tushare stub: returning empty DataFrame for '{field}'")
        return pd.DataFrame(index=dates, columns=self.tickers, dtype=float)

    @property
    def available_fields(self) -> set:
        """No fields available in stub mode."""
        return AVAILABLE_FIELDS.copy()

    def is_configured(self) -> bool:
        """Check if Tushare is actually configured and usable."""
        return False

    # === Future implementation notes ===
    # When implementing Tushare integration:
    #
    # import tushare as ts
    # pro = ts.pro_api(TUSHARE_TOKEN)
    #
    # def get_field(self, field: str) -> pd.DataFrame:
    #     ts_code = self._map_to_tushare_code(field)
    #     df = pro.daily(
    #         ts_code=','.join(self.tickers),
    #         start_date=self.start.replace('-', ''),
    #         end_date=self.end.replace('-', ''),
    #         fields=f'trade_date,ts_code,{ts_code}'
    #     )
    #     return df.pivot(index='trade_date', columns='ts_code', values=ts_code)
