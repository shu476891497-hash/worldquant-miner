"""
Wind API data source — stub implementation.

The Wind Information API is a premium data service used in China/Asia.
This module provides a stub interface that logs warnings and returns
empty DataFrames, allowing the pipeline to gracefully degrade.

API key placeholder: ak_TZiXoYVbwmgTPa3TeUqP61_FEY9pk3be
"""

import logging
from typing import List, Optional

import pandas as pd

from shadow_scorer.config import DATE_END, DATE_START, WIND_API_KEY

logger = logging.getLogger(__name__)

# Placeholder — Wind fields that could be mapped
AVAILABLE_FIELDS: set = set()  # No fields available until configured


class WindSource:
    """
    Wind API data source stub.

    Returns empty DataFrames for all requests. When the Wind API is properly
    configured, this class should be replaced with actual API calls.

    Configuration:
        Set WIND_API_KEY in shadow_scorer/config.py or via environment variable.
        Currently set to: {WIND_API_KEY}
    """

    def __init__(self, tickers: Optional[List[str]] = None,
                 start: str = DATE_START, end: str = DATE_END):
        self.tickers = tickers or []
        self.start = start
        self.end = end
        self._warned = False

    def _warn_once(self):
        """Log a warning about Wind API not being configured."""
        if not self._warned:
            logger.warning(
                "Wind API not configured. This is a stub implementation. "
                f"API key placeholder: {WIND_API_KEY}. "
                "To use Wind data, implement WindSource.get_field() with "
                "actual Wind API calls (e.g., w.wsd for daily data)."
            )
            self._warned = True

    def get_field(self, field: str) -> pd.DataFrame:
        """
        Get a field from Wind API (stub — returns empty DataFrame).

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
        logger.debug(f"Wind stub: returning empty DataFrame for '{field}'")
        return pd.DataFrame(index=dates, columns=self.tickers, dtype=float)

    @property
    def available_fields(self) -> set:
        """No fields available in stub mode."""
        return AVAILABLE_FIELDS.copy()

    def is_configured(self) -> bool:
        """Check if Wind API is actually configured and usable."""
        return False

    # === Future implementation notes ===
    # When implementing Wind API integration:
    #
    # from WindPy import w
    # w.start()
    #
    # def get_field(self, field: str) -> pd.DataFrame:
    #     wind_code = self._map_to_wind_code(field)
    #     data = w.wsd(
    #         self.tickers,
    #         wind_code,
    #         self.start,
    #         self.end,
    #         "Fill=Previous"
    #     )
    #     return pd.DataFrame(
    #         data.Data,
    #         index=data.Times,
    #         columns=data.Codes
    #     ).T
