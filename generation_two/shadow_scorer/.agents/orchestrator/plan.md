# Implementation Plan — WQ Shadow Scorer

## Architecture Overview
See PROJECT.md for full directory structure and interface contracts.

## Milestone Breakdown

### M1: Expression Parser & Operator Engine
**Scope**: parser/ directory + tests
**Files**:
- parser/__init__.py
- parser/lexer.py — Tokenizer (numbers, strings, identifiers, operators, parens, commas, semicolons, comparisons)
- parser/ast_nodes.py — AST nodes: Number, String, Identifier, FunctionCall, BinaryOp, UnaryOp, Assignment, ExpressionList
- parser/parser.py — Recursive descent parser supporting nested expressions, multi-statement, variable assignment
- parser/evaluator.py — AST walker that evaluates over DataFrames (dates × instruments)
- parser/operators/__init__.py — Registry mapping operator names to implementations
- parser/operators/arithmetic.py — 16 ops: add, subtract, multiply, divide, abs, log, sqrt, sign, signed_power, power, inverse, reverse, min, max, to_nan, densify
- parser/operators/logical.py — 11 ops: and, or, not, equal, not_equal, greater, greater_equal, less, less_equal, is_nan, if_else
- parser/operators/time_series.py — 24 ops: ts_mean, ts_rank, ts_zscore, ts_delta, ts_delay, ts_std_dev, ts_sum, ts_backfill, ts_count_nans, ts_product, ts_decay_linear, ts_covariance, ts_corr, ts_regression, ts_step, ts_arg_max, ts_arg_min, ts_av_diff, ts_quantile, ts_scale, ts_max, ts_min, kth_element, hump, last_diff_value, days_from_last_change, jump_decay, ts_target_tvr_decay, ts_target_tvr_delta_limit
- parser/operators/cross_sectional.py — 8 ops: rank, normalize, zscore, winsorize, quantile, scale, scale_down, vector_neut
- parser/operators/vector.py — 4 ops: vec_min, vec_avg, vec_sum, vec_max
- parser/operators/transformational.py — 3 ops: trade_when, bucket, generate_stats
- parser/operators/group.py — 10 ops: group_neutralize, group_rank, group_zscore, group_mean, group_min, group_max, group_scale, group_backfill, group_cartesian_product, combo_a
- parser/operators/special.py — 3 ops: universe_size, self_corr, in
- parser/operators/reduce.py — 12 ops: reduce_avg, reduce_sum, reduce_min, reduce_max, reduce_stddev, reduce_ir, reduce_skewness, reduce_kurtosis, reduce_range, reduce_norm, reduce_count, reduce_choose, reduce_percentage, reduce_powersum
- tests/test_parser.py
- tests/test_operators.py

**Key Design Decisions**:
- All operators work on pd.DataFrame (dates × instruments) or scalars
- Time series ops use rolling windows with min_periods=1 for partial data
- Group ops take a group Series (sector/industry/subindustry per instrument)
- NaN handling follows WQ semantics per operator description
- Performance: Numba JIT for hot loops in time_series ops

### M2: Multi-Source Data Pipeline
**Scope**: data/ directory + tests
**Files**:
- data/__init__.py
- data/pipeline.py — load_panel() orchestrator
- data/yfinance_source.py — Download OHLCV + market cap for US stocks
- data/simfin_source.py — SimFin fundamentals
- data/wind_source.py — Wind API stub (future)
- data/tushare_source.py — Tushare stub (future)
- data/universe.py — TOP500/1000/2000/3000 by daily market cap ranking
- data/field_mapper.py — Maps WQ field names to local data columns
- data/storage.py — Parquet cache with incremental updates

### M3: Scoring Engine
**Scope**: scoring/ directory + tests
**Depends on**: M1 (parser output format), M2 (returns data)
**Files**:
- scoring/__init__.py
- scoring/portfolio.py — Dollar-neutral long-short from alpha weights
- scoring/metrics.py — Sharpe, Turnover, Fitness, Drawdown, Weight Concentration
- scoring/periods.py — IS (2019-2022) / OOS (2023-2026.04) splitting
- scoring/thresholds.py — D0/D1 pass/fail thresholds
- tests/test_scoring.py

### M4: CLI & Integration
**Scope**: cli/ + evaluate.py + integration
**Depends on**: M1, M2, M3
**Files**:
- cli/__init__.py
- cli/evaluate.py
- evaluate.py — Top-level CLI entry
- config.py — Global configuration
- __init__.py — Package init with evaluate_alpha() export
- requirements.txt
- tests/test_cli.py

### M5: Field Mapping Coverage Report
**Scope**: reports/ + tests
**Depends on**: M2 (partial — field_mapper.py)
**Files**:
- reports/__init__.py
- reports/field_coverage.py — Coverage analysis, WRDS guide generation
- tests/test_field_mapping.py

## Dispatch Strategy
- M1 and M2 run in parallel (no dependencies)
- M5 runs in parallel (only reads field catalog JSON, not full M2)
- M3 dispatches after M1+M2 complete (needs interface contracts)
- M4 dispatches after M1+M2+M3 complete
- Each worker gets detailed specs + reference file paths
