"""
Tests for WQ operator implementations.

Uses small synthetic DataFrames to verify correctness, NaN propagation,
and edge cases for each operator category.
"""

import numpy as np
import pandas as pd
import pytest

# ---- Operator imports ----
from shadow_scorer.parser.operators.arithmetic import (
    op_abs,
    op_add,
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
from shadow_scorer.parser.operators.logical import (
    op_and,
    op_if_else,
    op_is_nan,
    op_not,
    op_or,
)
from shadow_scorer.parser.operators.time_series import (
    days_from_last_change,
    ts_arg_max,
    ts_arg_min,
    ts_av_diff,
    ts_backfill,
    ts_corr,
    ts_count_nans,
    ts_decay_linear,
    ts_delay,
    ts_delta,
    ts_max,
    ts_mean,
    ts_min,
    ts_rank,
    ts_std_dev,
    ts_sum,
    ts_zscore,
)
from shadow_scorer.parser.operators.cross_sectional import (
    normalize,
    rank,
    scale,
    scale_down,
    winsorize,
    zscore,
)
from shadow_scorer.parser.operators.group import (
    group_max,
    group_min,
    group_neutralize,
    group_rank,
    group_zscore,
)
from shadow_scorer.parser.operators.vector import vec_avg, vec_max, vec_min, vec_sum
from shadow_scorer.parser.evaluator import evaluate_expression


# ====================================================================
# Test fixtures
# ====================================================================

@pytest.fixture
def sample_df():
    """5 days × 4 instruments."""
    data = np.array([
        [1.0, 2.0, 3.0, 4.0],
        [2.0, 4.0, 6.0, 8.0],
        [3.0, 6.0, 9.0, 12.0],
        [4.0, 8.0, 12.0, 16.0],
        [5.0, 10.0, 15.0, 20.0],
    ])
    dates = pd.date_range("2024-01-01", periods=5)
    instruments = ["A", "B", "C", "D"]
    return pd.DataFrame(data, index=dates, columns=instruments)


@pytest.fixture
def sample_df_with_nan():
    """5 days × 3 instruments with NaN values."""
    data = np.array([
        [1.0, np.nan, 3.0],
        [np.nan, 4.0, 6.0],
        [3.0, 6.0, np.nan],
        [4.0, np.nan, 12.0],
        [5.0, 10.0, 15.0],
    ])
    dates = pd.date_range("2024-01-01", periods=5)
    instruments = ["X", "Y", "Z"]
    return pd.DataFrame(data, index=dates, columns=instruments)


@pytest.fixture
def all_nan_df():
    """All NaN DataFrame."""
    dates = pd.date_range("2024-01-01", periods=3)
    return pd.DataFrame(np.nan, index=dates, columns=["A", "B"])


@pytest.fixture
def group_series():
    """Group assignments: A,B in group 0; C,D in group 1."""
    return pd.Series({"A": 0, "B": 0, "C": 1, "D": 1})


# ====================================================================
# Arithmetic operators
# ====================================================================

class TestArithmetic:
    def test_add(self, sample_df):
        result = op_add(sample_df, sample_df)
        expected = sample_df * 2
        pd.testing.assert_frame_equal(result, expected)

    def test_add_filter(self, sample_df_with_nan):
        result = op_add(sample_df_with_nan, sample_df_with_nan, filter=True)
        # NaN→0 before adding, so NaN positions become 0+0=0
        assert not result.isna().any().any()

    def test_subtract(self, sample_df):
        result = op_subtract(sample_df, sample_df)
        expected = pd.DataFrame(0.0, index=sample_df.index, columns=sample_df.columns)
        pd.testing.assert_frame_equal(result, expected)

    def test_multiply(self, sample_df):
        result = op_multiply(sample_df, sample_df)
        expected = sample_df ** 2
        pd.testing.assert_frame_equal(result, expected)

    def test_divide_safe(self, sample_df):
        zeros = pd.DataFrame(0.0, index=sample_df.index, columns=sample_df.columns)
        result = op_divide(sample_df, zeros)
        assert result.isna().all().all()  # all NaN due to div-by-zero

    def test_abs(self):
        df = pd.DataFrame([[-1, 2], [-3, 4]])
        result = op_abs(df)
        expected = pd.DataFrame([[1, 2], [3, 4]])
        pd.testing.assert_frame_equal(result, expected)

    def test_log(self, sample_df):
        result = op_log(sample_df)
        expected = np.log(sample_df)
        pd.testing.assert_frame_equal(result, expected)

    def test_sqrt(self, sample_df):
        result = op_sqrt(sample_df)
        expected = np.sqrt(sample_df)
        pd.testing.assert_frame_equal(result, expected)

    def test_sign(self):
        df = pd.DataFrame([[1, -2, 0, np.nan]])
        result = op_sign(df)
        assert result.iloc[0, 0] == 1.0
        assert result.iloc[0, 1] == -1.0
        assert result.iloc[0, 2] == 0.0
        assert np.isnan(result.iloc[0, 3])

    def test_signed_power(self):
        df = pd.DataFrame([[-2, 3]])
        result = op_signed_power(df, 2)
        assert result.iloc[0, 0] == -4.0  # sign(-2) * |-2|^2 = -1 * 4
        assert result.iloc[0, 1] == 9.0   # sign(3) * |3|^2 = 1 * 9

    def test_inverse(self):
        df = pd.DataFrame([[2.0, 4.0]])
        result = op_inverse(df)
        assert result.iloc[0, 0] == 0.5
        assert result.iloc[0, 1] == 0.25

    def test_reverse(self, sample_df):
        result = op_reverse(sample_df)
        expected = -sample_df
        pd.testing.assert_frame_equal(result, expected)

    def test_min_max(self):
        df1 = pd.DataFrame([[1, 5], [3, 7]])
        df2 = pd.DataFrame([[2, 4], [6, 8]])
        min_result = op_min(df1, df2)
        assert min_result.iloc[0, 0] == 1
        assert min_result.iloc[0, 1] == 4
        max_result = op_max(df1, df2)
        assert max_result.iloc[0, 0] == 2
        assert max_result.iloc[0, 1] == 5

    def test_to_nan(self):
        df = pd.DataFrame([[0, 1, 2]])
        result = op_to_nan(df, value=0)
        assert np.isnan(result.iloc[0, 0])
        assert result.iloc[0, 1] == 1.0

    def test_to_nan_reverse(self):
        df = pd.DataFrame([[np.nan, 1, 2]])
        result = op_to_nan(df, value=0, reverse=True)
        assert result.iloc[0, 0] == 0.0
        assert result.iloc[0, 1] == 1.0


# ====================================================================
# Logical operators
# ====================================================================

class TestLogical:
    def test_and(self):
        df1 = pd.DataFrame([[1, 0, 1]])
        df2 = pd.DataFrame([[1, 1, 0]])
        result = op_and(df1, df2)
        assert result.iloc[0, 0] == 1.0
        assert result.iloc[0, 1] == 0.0
        assert result.iloc[0, 2] == 0.0

    def test_or(self):
        df1 = pd.DataFrame([[1, 0, 0]])
        df2 = pd.DataFrame([[0, 0, 1]])
        result = op_or(df1, df2)
        assert result.iloc[0, 0] == 1.0
        assert result.iloc[0, 1] == 0.0
        assert result.iloc[0, 2] == 1.0

    def test_not(self):
        df = pd.DataFrame([[1, 0, np.nan]])
        result = op_not(df)
        assert result.iloc[0, 0] == 0.0
        assert result.iloc[0, 1] == 1.0
        assert np.isnan(result.iloc[0, 2])

    def test_is_nan(self, sample_df_with_nan):
        result = op_is_nan(sample_df_with_nan)
        assert result.iloc[0, 1] == 1.0  # Y day 0 is NaN
        assert result.iloc[0, 0] == 0.0  # X day 0 is 1.0

    def test_if_else(self):
        cond = pd.DataFrame([[1, 0, np.nan]])
        true_val = pd.DataFrame([[10, 20, 30]])
        false_val = pd.DataFrame([[100, 200, 300]])
        result = op_if_else(cond, true_val, false_val)
        assert result.iloc[0, 0] == 10.0
        assert result.iloc[0, 1] == 200.0
        assert np.isnan(result.iloc[0, 2])


# ====================================================================
# Time Series operators
# ====================================================================

class TestTimeSeries:
    def test_ts_mean(self, sample_df):
        result = ts_mean(sample_df, 3)
        # Day 3 (idx 2): mean of [1,2,3] for col A = 2.0
        assert result.iloc[2, 0] == pytest.approx(2.0)

    def test_ts_std_dev(self, sample_df):
        result = ts_std_dev(sample_df, 3)
        # Day 3: std of [1,2,3] = 1.0
        assert result.iloc[2, 0] == pytest.approx(1.0)

    def test_ts_sum(self, sample_df):
        result = ts_sum(sample_df, 3)
        # Day 3: sum of [1,2,3] for col A = 6.0
        assert result.iloc[2, 0] == pytest.approx(6.0)

    def test_ts_delta(self, sample_df):
        result = ts_delta(sample_df, 1)
        # Day 2: 2 - 1 = 1 for col A
        assert result.iloc[1, 0] == pytest.approx(1.0)
        # Day 1: NaN (no previous value at lag 1)
        assert np.isnan(result.iloc[0, 0])

    def test_ts_delay(self, sample_df):
        result = ts_delay(sample_df, 2)
        # Day 3 (idx 2): value from day 1 (idx 0) = 1 for col A
        assert result.iloc[2, 0] == pytest.approx(1.0)

    def test_ts_backfill(self, sample_df_with_nan):
        result = ts_backfill(sample_df_with_nan, 3)
        # Day 2 (idx 1), col X is NaN. Look back 3 days → day 1 has 1.0
        assert result.iloc[1, 0] == pytest.approx(1.0)

    def test_ts_count_nans(self, sample_df_with_nan):
        result = ts_count_nans(sample_df_with_nan, 3)
        # Day 3 (idx 2), col Y: values are [NaN, 4.0, 6.0] → 1 NaN
        assert result.iloc[2, 1] == pytest.approx(1.0)

    def test_ts_zscore(self, sample_df):
        result = ts_zscore(sample_df, 3)
        # Day 3 (idx 2), col A: mean=2, std=1 → zscore=(3-2)/1=1
        assert result.iloc[2, 0] == pytest.approx(1.0)

    def test_ts_arg_max(self, sample_df):
        result = ts_arg_max(sample_df, 3)
        # Day 3 (idx 2), col A: values [1,2,3], max is 3 at position 0 (today)
        assert result.iloc[2, 0] == pytest.approx(0.0)

    def test_ts_arg_min(self, sample_df):
        result = ts_arg_min(sample_df, 3)
        # Day 3 (idx 2), col A: values [1,2,3], min is 1 at position 2 (2 days ago)
        assert result.iloc[2, 0] == pytest.approx(2.0)

    def test_ts_max_min(self, sample_df):
        max_result = ts_max(sample_df, 3)
        min_result = ts_min(sample_df, 3)
        assert max_result.iloc[2, 0] == pytest.approx(3.0)
        assert min_result.iloc[2, 0] == pytest.approx(1.0)

    def test_ts_av_diff(self, sample_df):
        result = ts_av_diff(sample_df, 3)
        # Day 3 (idx 2): x=3, mean=2 → diff=1
        assert result.iloc[2, 0] == pytest.approx(1.0)

    def test_ts_corr(self, sample_df):
        # Correlation of identical signals should be ~1
        result = ts_corr(sample_df, sample_df, 5)
        # At day 5 (idx 4), should be ~1 for each col
        assert result.iloc[4, 0] == pytest.approx(1.0, abs=0.01)

    def test_days_from_last_change(self):
        df = pd.DataFrame([[1], [1], [2], [2], [2]], columns=["A"])
        result = days_from_last_change(df)
        assert result.iloc[0, 0] == 0  # first day
        assert result.iloc[1, 0] == 1  # same as prev
        assert result.iloc[2, 0] == 0  # changed
        assert result.iloc[3, 0] == 1  # same as prev
        assert result.iloc[4, 0] == 2  # same for 2 days

    def test_nan_propagation(self, all_nan_df):
        result = ts_mean(all_nan_df, 3)
        assert result.isna().all().all()


# ====================================================================
# Cross-sectional operators
# ====================================================================

class TestCrossSectional:
    def test_rank(self, sample_df):
        result = rank(sample_df)
        # All columns are proportional (1:2:3:4), so ranks should be 0.25, 0.5, 0.75, 1.0
        row0 = result.iloc[0]
        assert row0.min() == pytest.approx(0.25)
        assert row0.max() == pytest.approx(1.0)

    def test_normalize(self, sample_df):
        result = normalize(sample_df)
        # Each row should have mean ≈ 0
        row_means = result.mean(axis=1)
        for m in row_means:
            assert m == pytest.approx(0.0, abs=1e-10)

    def test_zscore_cross(self, sample_df):
        result = zscore(sample_df)
        # Each row should have mean ≈ 0 and std ≈ 1
        row_means = result.mean(axis=1)
        row_stds = result.std(axis=1, ddof=1)
        for m, s in zip(row_means, row_stds):
            assert m == pytest.approx(0.0, abs=1e-10)
            assert s == pytest.approx(1.0, abs=1e-10)

    def test_winsorize(self):
        df = pd.DataFrame([[1, 2, 3, 4, 5, 6, 100.0]])
        result = winsorize(df, std=1)
        # 100 should be clipped down
        assert result.iloc[0, -1] < 100.0

    def test_scale(self):
        df = pd.DataFrame([[1.0, -1.0, 2.0, -2.0]])
        result = scale(df, scale_val=1)
        # Sum of abs should be 1
        assert result.abs().sum(axis=1).iloc[0] == pytest.approx(1.0)

    def test_scale_down(self, sample_df):
        result = scale_down(sample_df)
        # Each row should be in [0, 1]
        assert result.min().min() >= -1e-10
        assert result.max().max() <= 1 + 1e-10


# ====================================================================
# Group operators
# ====================================================================

class TestGroup:
    def test_group_neutralize(self, sample_df, group_series):
        result = group_neutralize(sample_df, group_series)
        # Within each group, mean should be ~0
        for i in range(len(result)):
            g0 = result.iloc[i][["A", "B"]]
            assert g0.mean() == pytest.approx(0.0, abs=1e-10)

    def test_group_rank(self, sample_df, group_series):
        result = group_rank(sample_df, group_series)
        # Group 0 has A, B. A < B always. So rank(A) = 0, rank(B) = 1
        assert result.iloc[0, 0] == pytest.approx(0.0)  # A in group 0
        assert result.iloc[0, 1] == pytest.approx(1.0)  # B in group 0

    def test_group_min_max(self, sample_df, group_series):
        gmin = group_min(sample_df, group_series)
        gmax = group_max(sample_df, group_series)
        # Group 0 (A, B): min=A, max=B
        assert gmin.iloc[0, 0] == sample_df.iloc[0, 0]
        assert gmin.iloc[0, 1] == sample_df.iloc[0, 0]
        assert gmax.iloc[0, 0] == sample_df.iloc[0, 1]
        assert gmax.iloc[0, 1] == sample_df.iloc[0, 1]

    def test_group_zscore(self, sample_df, group_series):
        result = group_zscore(sample_df, group_series)
        # Within each group, should be z-scored
        for i in range(len(result)):
            g0 = result.iloc[i][["A", "B"]]
            assert g0.mean() == pytest.approx(0.0, abs=1e-10)


# ====================================================================
# Vector operators
# ====================================================================

class TestVector:
    def test_vec_ops(self, sample_df):
        vmin = vec_min(sample_df)
        vmax = vec_max(sample_df)
        vavg = vec_avg(sample_df)
        vsum = vec_sum(sample_df)

        # Day 1: min=1, max=4, avg=2.5, sum=10
        assert vmin.iloc[0] == 1.0
        assert vmax.iloc[0] == 4.0
        assert vavg.iloc[0] == 2.5
        assert vsum.iloc[0] == 10.0


# ====================================================================
# End-to-end evaluator tests
# ====================================================================

class TestEvaluator:
    def _make_data(self):
        dates = pd.date_range("2024-01-01", periods=10)
        instruments = ["A", "B", "C"]
        np.random.seed(42)
        close = pd.DataFrame(
            np.random.randn(10, 3) * 10 + 100,
            index=dates,
            columns=instruments,
        )
        volume = pd.DataFrame(
            np.random.rand(10, 3) * 1e6,
            index=dates,
            columns=instruments,
        )
        return {"close": close, "volume": volume}

    def test_simple_rank(self):
        data = self._make_data()
        result = evaluate_expression("rank(close)", data)
        assert result.shape == data["close"].shape
        # Ranks should be in [0, 1]
        assert result.min().min() >= 0
        assert result.max().max() <= 1

    def test_binary_expression(self):
        data = self._make_data()
        result = evaluate_expression("close / volume", data)
        assert result.shape == data["close"].shape

    def test_nested_expression(self):
        data = self._make_data()
        result = evaluate_expression("rank(ts_mean(close, 5))", data)
        assert result.shape == data["close"].shape

    def test_multi_statement(self):
        data = self._make_data()
        result = evaluate_expression("x = close / volume; rank(x)", data)
        assert result.shape == data["close"].shape

    def test_constant_expression(self):
        data = self._make_data()
        result = evaluate_expression("42", data)
        assert result.shape == data["close"].shape
        assert (result == 42).all().all()

    def test_group_expression(self):
        data = self._make_data()
        group_data = {"subindustry": pd.Series({"A": 0, "B": 0, "C": 1})}
        result = evaluate_expression(
            "group_neutralize(close, subindustry)", data, group_data
        )
        assert result.shape == data["close"].shape

    def test_kwargs_expression(self):
        data = self._make_data()
        result = evaluate_expression("winsorize(close, std=3)", data)
        assert result.shape == data["close"].shape

    def test_comparison_expression(self):
        data = self._make_data()
        result = evaluate_expression("close > 100", data)
        assert result.shape == data["close"].shape
        # Result should be 0.0 or 1.0
        assert set(result.values.flatten()) <= {0.0, 1.0, np.nan}


# ====================================================================
# Edge cases
# ====================================================================

class TestEdgeCases:
    def test_empty_df(self):
        df = pd.DataFrame(dtype=float)
        result = op_add(df, df)
        assert result.empty

    def test_single_element_df(self):
        df = pd.DataFrame([[42.0]])
        result = op_abs(df)
        assert result.iloc[0, 0] == 42.0

    def test_all_nan_arithmetic(self, all_nan_df):
        result = op_add(all_nan_df, all_nan_df)
        assert result.isna().all().all()

    def test_all_nan_rank(self, all_nan_df):
        result = rank(all_nan_df)
        assert result.isna().all().all()
