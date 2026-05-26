"""
Central operator registry for WQ alpha expressions.

Maps lowercase WQ operator names to their Python implementations.
Handles Python reserved words (and, or, not, in) via explicit mapping.
"""

from __future__ import annotations

from typing import Any, Callable, Dict

# -- Arithmetic --
from .arithmetic import (
    op_abs,
    op_add,
    op_densify,
    op_divide,
    op_inverse,
    op_log,
    op_max,
    op_min,
    op_multiply,
    op_power,
    op_reverse,
    op_sign,
    op_signed_power,
    op_sqrt,
    op_subtract,
    op_to_nan,
)

# -- Logical --
from .logical import (
    op_and,
    op_equal,
    op_greater,
    op_greater_equal,
    op_if_else,
    op_is_nan,
    op_less,
    op_less_equal,
    op_not,
    op_not_equal,
    op_or,
)

# -- Time Series --
from .time_series import (
    days_from_last_change,
    hump,
    jump_decay,
    kth_element,
    last_diff_value,
    ts_arg_max,
    ts_arg_min,
    ts_av_diff,
    ts_backfill,
    ts_corr,
    ts_count_nans,
    ts_covariance,
    ts_decay_linear,
    ts_delay,
    ts_delta,
    ts_max,
    ts_mean,
    ts_min,
    ts_product,
    ts_quantile,
    ts_rank,
    ts_regression,
    ts_scale,
    ts_std_dev,
    ts_step,
    ts_sum,
    ts_target_tvr_decay,
    ts_target_tvr_delta_limit,
    ts_zscore,
)

# -- Cross Sectional --
from .cross_sectional import (
    normalize,
    quantile,
    rank,
    scale,
    scale_down,
    vector_neut,
    winsorize,
    zscore,
)

# -- Vector --
from .vector import vec_avg, vec_max, vec_min, vec_sum

# -- Transformational --
from .transformational import bucket, generate_stats, trade_when

# -- Group --
from .group import (
    combo_a,
    group_backfill,
    group_cartesian_product,
    group_max,
    group_mean,
    group_min,
    group_neutralize,
    group_rank,
    group_scale,
    group_zscore,
)

# -- Special --
from .special import op_in, self_corr, universe_size

# -- Reduce --
from .reduce import (
    reduce_avg,
    reduce_choose,
    reduce_count,
    reduce_ir,
    reduce_kurtosis,
    reduce_max,
    reduce_min,
    reduce_norm,
    reduce_percentage,
    reduce_powersum,
    reduce_range,
    reduce_skewness,
    reduce_stddev,
    reduce_sum,
)


# ===========================================================================
# OPERATOR_REGISTRY
# ===========================================================================

OPERATOR_REGISTRY: Dict[str, Callable] = {
    # ---- Arithmetic (16) ----
    "add": op_add,
    "subtract": op_subtract,
    "multiply": op_multiply,
    "divide": op_divide,
    "abs": op_abs,
    "log": op_log,
    "sqrt": op_sqrt,
    "sign": op_sign,
    "signed_power": op_signed_power,
    "power": op_power,
    "inverse": op_inverse,
    "reverse": op_reverse,
    "min": op_min,
    "max": op_max,
    "to_nan": op_to_nan,
    "densify": op_densify,

    # ---- Logical (11) ----
    "and": op_and,           # Python reserved word — mapped explicitly
    "or": op_or,             # Python reserved word
    "not": op_not,           # Python reserved word
    "equal": op_equal,
    "not_equal": op_not_equal,
    "greater": op_greater,
    "greater_equal": op_greater_equal,
    "less": op_less,
    "less_equal": op_less_equal,
    "is_nan": op_is_nan,
    "if_else": op_if_else,

    # ---- Time Series (28+) ----
    "ts_mean": ts_mean,
    "ts_std_dev": ts_std_dev,
    "ts_sum": ts_sum,
    "ts_rank": ts_rank,
    "ts_zscore": ts_zscore,
    "ts_delta": ts_delta,
    "ts_delay": ts_delay,
    "ts_backfill": ts_backfill,
    "ts_count_nans": ts_count_nans,
    "ts_product": ts_product,
    "ts_decay_linear": ts_decay_linear,
    "ts_covariance": ts_covariance,
    "ts_corr": ts_corr,
    "ts_regression": ts_regression,
    "ts_step": ts_step,
    "ts_arg_max": ts_arg_max,
    "ts_arg_min": ts_arg_min,
    "ts_av_diff": ts_av_diff,
    "ts_quantile": ts_quantile,
    "ts_scale": ts_scale,
    "ts_max": ts_max,
    "ts_min": ts_min,
    "kth_element": kth_element,
    "hump": hump,
    "last_diff_value": last_diff_value,
    "days_from_last_change": days_from_last_change,
    "jump_decay": jump_decay,
    "ts_target_tvr_decay": ts_target_tvr_decay,
    "ts_target_tvr_delta_limit": ts_target_tvr_delta_limit,

    # ---- Cross Sectional (8) ----
    "rank": rank,
    "normalize": normalize,
    "zscore": zscore,
    "winsorize": winsorize,
    "quantile": quantile,
    "scale": scale,
    "scale_down": scale_down,
    "vector_neut": vector_neut,

    # ---- Vector (4) ----
    "vec_min": vec_min,
    "vec_avg": vec_avg,
    "vec_sum": vec_sum,
    "vec_max": vec_max,

    # ---- Transformational (3) ----
    "trade_when": trade_when,
    "bucket": bucket,
    "generate_stats": generate_stats,

    # ---- Group (10) ----
    "group_neutralize": group_neutralize,
    "group_rank": group_rank,
    "group_zscore": group_zscore,
    "group_mean": group_mean,
    "group_min": group_min,
    "group_max": group_max,
    "group_scale": group_scale,
    "group_backfill": group_backfill,
    "group_cartesian_product": group_cartesian_product,
    "combo_a": combo_a,

    # ---- Special (3) ----
    "universe_size": universe_size,
    "self_corr": self_corr,
    "in": op_in,             # Python reserved word

    # ---- Reduce (14) ----
    "reduce_avg": reduce_avg,
    "reduce_sum": reduce_sum,
    "reduce_min": reduce_min,
    "reduce_max": reduce_max,
    "reduce_stddev": reduce_stddev,
    "reduce_ir": reduce_ir,
    "reduce_skewness": reduce_skewness,
    "reduce_kurtosis": reduce_kurtosis,
    "reduce_range": reduce_range,
    "reduce_norm": reduce_norm,
    "reduce_count": reduce_count,
    "reduce_choose": reduce_choose,
    "reduce_percentage": reduce_percentage,
    "reduce_powersum": reduce_powersum,
}

# Also add a "pasteurize" alias — commonly used in WQ expressions.
# pasteurize(x) ≡ to_nan(x, value=0, reverse=false)  (strips zeros)
OPERATOR_REGISTRY["pasteurize"] = op_to_nan


def get_operator(name: str) -> Callable:
    """Look up an operator by WQ name (case-insensitive).

    Raises KeyError if not found.
    """
    return OPERATOR_REGISTRY[name.lower()]
