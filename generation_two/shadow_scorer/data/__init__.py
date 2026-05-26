"""
Data pipeline package for WQ Shadow Scorer.

Provides multi-source data download, normalization, and caching
for US equity data used in alpha expression evaluation.

Public API:
    load_panel(fields, universe, start, end) -> dict[str, pd.DataFrame]
    get_universe_membership(universe, dates) -> pd.DataFrame
"""

from shadow_scorer.data.pipeline import load_panel
from shadow_scorer.data.universe import get_membership as get_universe_membership

__all__ = ['load_panel', 'get_universe_membership']
