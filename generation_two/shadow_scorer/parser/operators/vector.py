"""
Vector operators for WQ alpha expressions.

These collapse a vector field (e.g. multiple price points per instrument/day)
into a single scalar.  For our DataFrame representation they operate
column-wise per row.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def op_vec_min(x: Any) -> Any:
    """Minimum of vector field x per row."""
    if isinstance(x, pd.DataFrame):
        return pd.DataFrame(
            x.min(axis=1).values[:, np.newaxis],
            index=x.index,
            columns=x.columns,
        ).reindex(columns=x.columns, fill_value=np.nan).pipe(
            lambda df: pd.DataFrame(
                np.tile(x.min(axis=1).values.reshape(-1, 1), (1, len(x.columns))),
                index=x.index,
                columns=x.columns,
            )
        )
    return np.nanmin(x)


def op_vec_avg(x: Any) -> Any:
    """Mean of vector field x per row."""
    if isinstance(x, pd.DataFrame):
        vals = x.mean(axis=1).values
        return pd.DataFrame(
            np.tile(vals.reshape(-1, 1), (1, len(x.columns))),
            index=x.index,
            columns=x.columns,
        )
    return np.nanmean(x)


def op_vec_sum(x: Any) -> Any:
    """Sum of vector field x per row."""
    if isinstance(x, pd.DataFrame):
        vals = x.sum(axis=1).values
        return pd.DataFrame(
            np.tile(vals.reshape(-1, 1), (1, len(x.columns))),
            index=x.index,
            columns=x.columns,
        )
    return np.nansum(x)


def op_vec_max(x: Any) -> Any:
    """Maximum of vector field x per row."""
    if isinstance(x, pd.DataFrame):
        vals = x.max(axis=1).values
        return pd.DataFrame(
            np.tile(vals.reshape(-1, 1), (1, len(x.columns))),
            index=x.index,
            columns=x.columns,
        )
    return np.nanmax(x)
