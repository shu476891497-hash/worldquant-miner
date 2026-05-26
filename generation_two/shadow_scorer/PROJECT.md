# Project: WQ Shadow Scorer

## Overview
Local Out-of-Sample backtesting engine that evaluates WorldQuant Brain alpha expressions against 2018–2026 US equity data, approximating WQ's multi-metric scoring with ~70% rank-correlation accuracy.

## Architecture

```
shadow_scorer/
├── parser/              # M1: Expression Parser & Operator Engine
│   ├── __init__.py
│   ├── lexer.py         # Tokenizer for WQ expressions
│   ├── ast_nodes.py     # AST node definitions
│   ├── parser.py        # Recursive descent parser
│   ├── evaluator.py     # AST evaluation engine
│   └── operators/       # Operator implementations by category
│       ├── __init__.py
│       ├── arithmetic.py    # 16 operators: add, subtract, multiply, divide, etc.
│       ├── logical.py       # 11 operators: and, or, not, if_else, etc.
│       ├── time_series.py   # 24 operators: ts_mean, ts_rank, ts_zscore, etc.
│       ├── cross_sectional.py # 8 operators: rank, normalize, zscore, etc.
│       ├── vector.py        # 3 operators: vec_min, vec_avg, vec_sum, vec_max
│       ├── transformational.py # 3 operators: trade_when, bucket, generate_stats
│       ├── group.py         # 10 operators: group_neutralize, group_rank, etc.
│       ├── special.py       # 3 operators: universe_size, self_corr, in
│       └── reduce.py        # 12 operators: reduce_avg, reduce_sum, etc.
├── data/                # M2: Multi-Source Data Pipeline
│   ├── __init__.py
│   ├── pipeline.py      # Orchestrates data download & caching
│   ├── yfinance_source.py   # yfinance OHLCV + fundamentals
│   ├── simfin_source.py     # SimFin quarterly/annual fundamentals
│   ├── wind_source.py       # Wind API stub
│   ├── tushare_source.py    # Tushare stub
│   ├── universe.py      # TOP500/1000/2000/3000 construction
│   ├── field_mapper.py  # WQ field name → data source mapping
│   └── storage.py       # Parquet read/write with incremental updates
├── scoring/             # M3: Scoring Engine
│   ├── __init__.py
│   ├── portfolio.py     # Dollar-neutral long-short portfolio
│   ├── metrics.py       # Sharpe, Turnover, Fitness, Drawdown, etc.
│   ├── periods.py       # IS/OOS period splitting
│   └── thresholds.py    # D0/D1 quality thresholds
├── cli/                 # M4: CLI & Integration
│   ├── __init__.py
│   └── evaluate.py      # CLI entry point
├── reports/             # M5: Field Mapping Coverage Report
│   ├── __init__.py
│   └── field_coverage.py    # Coverage analysis and WRDS guide
├── tests/               # Unit tests for all modules
│   ├── __init__.py
│   ├── test_parser.py
│   ├── test_operators.py
│   ├── test_data_pipeline.py
│   ├── test_scoring.py
│   ├── test_cli.py
│   └── test_field_mapping.py
├── evaluate.py          # Top-level CLI entry point
├── __init__.py
├── config.py            # Global configuration
└── requirements.txt     # Python dependencies
```

## Milestones

| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | Expression Parser & Operator Engine | parser/, tests/test_parser.py, tests/test_operators.py | none | PLANNED |
| 2 | Multi-Source Data Pipeline | data/, tests/test_data_pipeline.py | none | PLANNED |
| 3 | Scoring Engine | scoring/, tests/test_scoring.py | M1, M2 | PLANNED |
| 4 | CLI & Integration | cli/, evaluate.py, tests/test_cli.py | M1, M2, M3 | PLANNED |
| 5 | Field Mapping Coverage Report | reports/, tests/test_field_mapping.py | M2 (partial) | PLANNED |

## Interface Contracts

### parser ↔ data
- `evaluator.evaluate(expr: str, data: Dict[str, pd.DataFrame]) -> pd.DataFrame`
  - `data` keys are WQ field names (e.g., "close", "volume", "sales")
  - Each value is a DataFrame with DatetimeIndex (dates) × columns (instrument IDs)
  - Returns a DataFrame of same shape: alpha weights per stock per day

### parser ↔ scoring
- Parser output (DataFrame of weights) feeds directly into scoring engine
- `scoring.compute_metrics(weights: pd.DataFrame, returns: pd.DataFrame, universe_mask: pd.DataFrame) -> dict`

### data ↔ scoring
- `data.pipeline.load_panel(fields: List[str], universe: str, start: str, end: str) -> Dict[str, pd.DataFrame]`
- `data.universe.get_membership(universe: str, dates: pd.DatetimeIndex) -> pd.DataFrame` (bool mask)
- `data.storage.load_returns() -> pd.DataFrame` (daily returns for PnL calculation)

### cli ↔ all
- CLI imports parser.evaluator, data.pipeline, scoring.metrics
- `evaluate_alpha(expr: str, universe: str = "TOP3000", delay: int = 1) -> dict`
  - Returns JSON-serializable dict with IS/OOS metrics, pass/fail flags, field coverage

### continuous_evolution.py integration
- `from shadow_scorer import evaluate_alpha` — must work as import
- Returns dict with keys: sharpe_is, sharpe_oos, fitness_is, fitness_oos, turnover, drawdown, pass_d0, pass_d1, field_coverage_pct

## Code Layout

### Source code location
All source files in: `c:\Users\22637\OneDrive\Desktop\antigravity\worldquant_iqc\worldquant-miner\generation_two\shadow_scorer\`

### Reference files (READ-ONLY)
- Operators: `generation_two/constants/operatorRAW.json`
- D1 Fields: `generation_two/constants/data_fields_cache_USA_1_TOP3000.json`
- D0 Fields: `generation_two/constants/data_fields_cache_USA_0_TOP1000.json`
- D0 Whitelist: `generation_two/constants/d0_fields_whitelist.json`
- Skeleton Factory: `generation_two/skeleton_factory.py`
- Mining Engine: `generation_two/continuous_evolution.py`

### Data storage location
Downloaded data cached in: `shadow_scorer/cache/` (Parquet files)

## Technology Stack
- Python 3.10+
- pandas, numpy — core data manipulation
- numba — JIT compilation for performance-critical operators
- yfinance — free stock data
- simfin — fundamental data
- pyarrow/fastparquet — Parquet I/O
- pytest — testing
