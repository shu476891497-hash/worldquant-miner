"""
Reduce operators for WQ alpha expressions.

All COMBO-only. Operate on multi-alpha matrices.
Implemented as stubs that raise NotImplementedError.
"""

from __future__ import annotations

from typing import Any


def _combo_stub(name: str) -> None:
    raise NotImplementedError(
        f"{name}() is a COMBO-only reduce operator and is not yet implemented."
    )


def reduce_avg(input_data: Any, threshold: Any = 0, **kw: Any) -> Any:
    """reduce_avg(input, threshold=0)"""
    _combo_stub("reduce_avg")


def reduce_sum(input_data: Any, **kw: Any) -> Any:
    """reduce_sum(input)"""
    _combo_stub("reduce_sum")


def reduce_min(input_data: Any, **kw: Any) -> Any:
    """reduce_min(input)"""
    _combo_stub("reduce_min")


def reduce_max(input_data: Any, **kw: Any) -> Any:
    """reduce_max(input)"""
    _combo_stub("reduce_max")


def reduce_stddev(input_data: Any, threshold: Any = 0, **kw: Any) -> Any:
    """reduce_stddev(input, threshold=0)"""
    _combo_stub("reduce_stddev")


def reduce_ir(input_data: Any, **kw: Any) -> Any:
    """reduce_ir(input)"""
    _combo_stub("reduce_ir")


def reduce_skewness(input_data: Any, **kw: Any) -> Any:
    """reduce_skewness(input)"""
    _combo_stub("reduce_skewness")


def reduce_kurtosis(input_data: Any, **kw: Any) -> Any:
    """reduce_kurtosis(input)"""
    _combo_stub("reduce_kurtosis")


def reduce_range(input_data: Any, **kw: Any) -> Any:
    """reduce_range(input)"""
    _combo_stub("reduce_range")


def reduce_norm(input_data: Any, **kw: Any) -> Any:
    """reduce_norm(input)"""
    _combo_stub("reduce_norm")


def reduce_count(input_data: Any, threshold: Any = 0, **kw: Any) -> Any:
    """reduce_count(input, threshold)"""
    _combo_stub("reduce_count")


def reduce_choose(input_data: Any, nth: Any = 1, ignoreNan: Any = True, **kw: Any) -> Any:
    """reduce_choose(input, nth, ignoreNan=true)"""
    _combo_stub("reduce_choose")


def reduce_percentage(input_data: Any, percentage: Any = 0.5, **kw: Any) -> Any:
    """reduce_percentage(input, percentage=0.5)"""
    _combo_stub("reduce_percentage")


def reduce_powersum(input_data: Any, constant: Any = 2, precise: Any = False, **kw: Any) -> Any:
    """reduce_powersum(input, constant=2, precise=false)"""
    _combo_stub("reduce_powersum")
