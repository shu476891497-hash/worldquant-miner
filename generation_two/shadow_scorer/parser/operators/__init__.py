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
    op_days_from_last_change,
    op_hump,
    op_jump_decay,
    op_kth_element,
    op_last_diff_value,
    op_ts_arg_max,
    op_ts_arg_min,
    op_ts_av_diff,
    op_ts_backfill,
    op_ts_corr,
    op_ts_count_nans,
    op_ts_covariance,
    op_ts_decay_linear,
    op_ts_delay,
    op_ts_delta,
    op_ts_max,
    op_ts_mean,
    op_ts_min,
    op_ts_product,
    op_ts_quantile,
    op_ts_rank,
    op_ts_regression,
    op_ts_scale,
    op_ts_std_dev,
    op_ts_step,
    op_ts_sum,
    op_ts_target_tvr_decay,
    op_ts_target_tvr_delta_limit,
    op_ts_zscore,
)

# -- Cross Sectional --
from .cross_sectional import (
    op_normalize,
    op_quantile,
    op_rank,
    op_scale,
    op_scale_down,
    op_vector_neut,
    op_winsorize,
    op_zscore,
)

# -- Vector --
from .vector import op_vec_avg, op_vec_max, op_vec_min, op_vec_sum

# -- Transformational --
from .transformational import op_bucket, op_generate_stats, op_trade_when

# -- Group --
from .group import (
    op_combo_a,
    op_group_backfill,
    op_group_cartesian_product,
    op_group_max,
    op_group_mean,
    op_group_min,
    op_group_neutralize,
    op_group_rank,
    op_group_scale,
    op_group_zscore,
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
    "ts_mean": op_ts_mean,
    "ts_std_dev": op_ts_std_dev,
    "ts_sum": op_ts_sum,
    "ts_rank": op_ts_rank,
    "ts_zscore": op_ts_zscore,
    "ts_delta": op_ts_delta,
    "ts_delay": op_ts_delay,
    "ts_backfill": op_ts_backfill,
    "ts_count_nans": op_ts_count_nans,
    "ts_product": op_ts_product,
    "ts_decay_linear": op_ts_decay_linear,
    "ts_covariance": op_ts_covariance,
    "ts_corr": op_ts_corr,
    "ts_regression": op_ts_regression,
    "ts_step": op_ts_step,
    "ts_arg_max": op_ts_arg_max,
    "ts_arg_min": op_ts_arg_min,
    "ts_av_diff": op_ts_av_diff,
    "ts_quantile": op_ts_quantile,
    "ts_scale": op_ts_scale,
    "ts_max": op_ts_max,
    "ts_min": op_ts_min,
    "kth_element": op_kth_element,
    "hump": op_hump,
    "last_diff_value": op_last_diff_value,
    "days_from_last_change": op_days_from_last_change,
    "jump_decay": op_jump_decay,
    "ts_target_tvr_decay": op_ts_target_tvr_decay,
    "ts_target_tvr_delta_limit": op_ts_target_tvr_delta_limit,

    # ---- Cross Sectional (8) ----
    "rank": op_rank,
    "normalize": op_normalize,
    "zscore": op_zscore,
    "winsorize": op_winsorize,
    "quantile": op_quantile,
    "scale": op_scale,
    "scale_down": op_scale_down,
    "vector_neut": op_vector_neut,

    # ---- Vector (4) ----
    "vec_min": op_vec_min,
    "vec_avg": op_vec_avg,
    "vec_sum": op_vec_sum,
    "vec_max": op_vec_max,

    # ---- Transformational (3) ----
    "trade_when": op_trade_when,
    "bucket": op_bucket,
    "generate_stats": op_generate_stats,

    # ---- Group (10) ----
    "group_neutralize": op_group_neutralize,
    "group_rank": op_group_rank,
    "group_zscore": op_group_zscore,
    "group_mean": op_group_mean,
    "group_min": op_group_min,
    "group_max": op_group_max,
    "group_scale": op_group_scale,
    "group_backfill": op_group_backfill,
    "group_cartesian_product": op_group_cartesian_product,
    "combo_a": op_combo_a,

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
