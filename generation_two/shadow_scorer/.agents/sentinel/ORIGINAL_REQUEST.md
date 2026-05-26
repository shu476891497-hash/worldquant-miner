# Original User Request

## Initial Request — 2026-05-26T16:22:49+08:00

Build a local Out-of-Sample (OOS) backtesting engine ("WQ Shadow Scorer") that evaluates WorldQuant Brain alpha expressions against 2018–2026 US equity data, approximating WQ's multi-metric scoring (Sharpe, Turnover, Fitness, Drawdown, Weight Concentration) with ~70% rank-correlation accuracy. The system serves as a pre-submission filter for IQC Stage 2 and a long-term independent alpha research platform. It must support CLI single/batch evaluation, auto-integration with the existing mining engine (`continuous_evolution.py`), and team sharing via deployment.

Working directory: c:\Users\22637\OneDrive\Desktop\antigravity\worldquant_iqc\worldquant-miner\generation_two\shadow_scorer
Integrity mode: development

## Reference Materials

The project has access to the following critical reference files that define the exact semantics of WQ's expression language:

- **Operator definitions** (90 operators with name, category, definition, description): `generation_two/constants/operatorRAW.json`
- **Datafield catalog** (7,600+ fields with id, description, category, subcategory, coverage, userCount): `generation_two/constants/data_fields_cache_USA_1_TOP3000.json`
- **D0 datafield catalog** (2,095+ fields): `generation_two/constants/data_fields_cache_USA_0_TOP1000.json`
- **D0 fields whitelist** (1,225 field IDs): `generation_two/constants/d0_fields_whitelist.json`
- **Existing alpha templates** (2,200+ skeleton templates): `generation_two/skeleton_factory.py`
- **Existing mining engine** (for integration): `generation_two/continuous_evolution.py`

## Requirements

### R1. Alpha Expression Parser & Operator Engine

Build a complete expression parser and evaluation engine that can take any WorldQuant Brain alpha expression string (e.g., `group_neutralize(ts_zscore(pasteurize(sales), 60), subindustry)`) and evaluate it against a panel of stock data (dates × instruments). 

The engine must implement all ~90 operators defined in `operatorRAW.json`, organized by category: Arithmetic (16), Logical (11), Time Series (24), Cross Sectional (8), Vector (3), Transformational (3), Group (10), Special (3), Reduce (12). Each operator's exact semantics (parameters, NaN handling, edge cases) must follow the descriptions in the reference file. 

Performance-critical operators (time series rolling functions, group operations) should use Numba/Cython acceleration where possible, since evaluation runs over 3000 stocks × 1500+ trading days.

### R2. Multi-Source Data Pipeline

Build a data ingestion pipeline that downloads, normalizes, and caches US equity data from multiple sources into a unified local Parquet store. The pipeline must:

- Map WQ's 7,600+ field names to available data source equivalents. Not all fields will have mappings — unmapped fields should be tracked and reported.
- Data sources (in priority order):
  1. **yfinance**: Daily OHLCV, market cap, basic fundamentals (free, immediate)
  2. **SimFin**: Quarterly/annual fundamentals — income statement, balance sheet, cash flow (free)
  3. **Wind API** (key: `ak_TZiXoYVbwmgTPa3TeUqP61_FEY9pk3be`): Chinese broker data, some US coverage
  4. **Tushare** (token: `ddd1b26b20ff085ac9b60c9bd902ae76bbff60910863e8cc0168da53`, highest tier): US equity data if available
  5. **WRDS** (manual): Generate a list of exact tables/fields needed for the user to manually download CSVs from the WRDS web interface
- Date range: 2018-01-01 to 2026-04-30 (2018 for warmup, 2019-2022 IS, 2023-2026.04 OOS)
- Storage: Local Parquet files, organized by data category, with incremental update support
- Must construct dynamic universe membership lists: TOP500, TOP1000, TOP2000, TOP3000 by daily market cap ranking

### R3. Scoring Engine

Implement a multi-metric scoring engine that computes WQ-compatible performance metrics for evaluated alpha signals:

- **Sharpe Ratio**: Annualized, computed from daily PnL of the dollar-neutral long-short portfolio
- **Turnover**: Daily average fraction of portfolio that changes
- **Fitness**: Sharpe × sqrt(abs(returns)) / max(1, turnover_ratio) (WQ's approximate formula)
- **Drawdown**: Maximum peak-to-trough decline
- **Weight Concentration**: Measure of how concentrated positions are (top-N weight share)
- **Sub-Universe Sharpe**: Sharpe computed separately for sub-universes (TOP500, TOP1000)
- Support configurable quality thresholds:
  - D1 factors: Sharpe > 1.25, Fitness > 1.0
  - D0 factors: Sharpe > 2.0, Fitness > 1.25
- The scoring must split results into IS period (2019-2022) and OOS period (2023-2026.04) to allow cross-validation against WQ's known IS scores.

### R4. CLI Interface & Batch Evaluation

Provide a command-line interface for:
- **Single evaluation**: `python evaluate.py --expr "rank(ts_delta(close, 5))" --universe TOP3000 --delay 1`
- **Batch evaluation**: `python evaluate.py --batch alphas.txt --universe TOP3000` (one expression per line)
- **Integration mode**: Callable from `continuous_evolution.py` to pre-screen alphas before WQ submission
- Output format: JSON with IS metrics, OOS metrics, pass/fail flags against thresholds, and field mapping coverage report (what % of referenced fields had real data vs. NaN fallback)

### R5. WQ Field Mapping Coverage Report

Generate a comprehensive report mapping WQ field names to available data source equivalents. For each of the 7,600+ fields, report:
- WQ field ID and category
- Mapped data source and field (if available)
- Coverage quality (exact match / proxy / unavailable)
- For unmapped fields needed by the user's active factors, generate a WRDS download guide (exact database, table, and column names) so the user can manually pull the data.

## Acceptance Criteria

### Expression Parser Correctness
- [ ] All 90 operators from `operatorRAW.json` are implemented and pass unit tests with the example inputs/outputs from the operator descriptions
- [ ] The parser correctly handles nested expressions with 5+ levels of nesting (e.g., `group_neutralize(ts_zscore(pasteurize(ts_delta(close, 5)), 60), subindustry)`)
- [ ] The parser correctly handles multi-statement expressions with semicolons and variable assignments (e.g., `iv = ts_backfill(implied_volatility_call_30, 5); rank(iv)`)
- [ ] NaN propagation matches WQ semantics (operators that ignore NaN vs. propagate NaN)

### Data Pipeline Reliability
- [ ] Successfully downloads and caches at least 3000 US stocks' daily OHLCV data for 2018-2026 from yfinance
- [ ] Successfully ingests SimFin fundamental data for at least the TOP1000 US stocks
- [ ] Universe construction produces correct daily TOP500/TOP1000/TOP2000/TOP3000 membership lists verified against a known reference (e.g., S&P 500 overlap check for TOP500)
- [ ] Data pipeline completes full download in under 2 hours and subsequent loads from cache in under 30 seconds

### Scoring Accuracy
- [ ] For at least 10 well-known alpha expressions (e.g., `rank(ts_delta(close, 5))`, `group_neutralize(ts_zscore(volume, 20), sector)`), the local IS Sharpe is within 0.3 of the WQ-reported IS Sharpe (user will manually verify against WQ platform)
- [ ] Turnover calculation is within 20% of WQ-reported turnover for the same 10 test alphas
- [ ] The scoring engine processes a single alpha expression in under 10 seconds on a standard laptop

### Integration & Usability
- [ ] CLI single-eval mode works end-to-end: expression in → JSON metrics out
- [ ] CLI batch mode evaluates 50+ expressions in a single run
- [ ] Python API is importable from `continuous_evolution.py` for automated pre-screening
- [ ] Field mapping report correctly identifies at least 200+ WQ fields that map to available yfinance/SimFin data
