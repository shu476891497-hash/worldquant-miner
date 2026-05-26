"""Reports package for WQ Shadow Scorer.

Provides field coverage analysis and mapping reports that compare WQ's
~7,800 data fields against available local data sources (yfinance, SimFin)
and generate WRDS download guides for unmapped fields.
"""

from .field_coverage import generate_coverage_report

__all__ = ["generate_coverage_report"]
