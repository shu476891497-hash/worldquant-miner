"""
Special operators for WQ alpha expressions.

Mostly SELECTION / COMBO only — implemented as stubs.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def universe_size(*args: Any, **kwargs: Any) -> Any:
    """universe_size: return universe count.

    SELECTION-only operator. Stub implementation.
    """
    raise NotImplementedError(
        "universe_size is a SELECTION-only operator and is not yet implemented."
    )


def self_corr(input_data: Any, **kwargs: Any) -> Any:
    """self_corr(input): autocorrelation matrix.

    COMBO-only operator. Stub implementation.
    """
    raise NotImplementedError(
        "self_corr() is a COMBO-only operator and is not yet implemented."
    )


def op_in(*args: Any, **kwargs: Any) -> Any:
    """in: membership check.

    SELECTION-only operator. Stub implementation.
    """
    raise NotImplementedError(
        "in is a SELECTION-only operator and is not yet implemented."
    )
