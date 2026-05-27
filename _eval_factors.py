"""
Factor evaluation — loads from Parquet cache, NO download needed.
Run _pipeline.py first to populate cache.
"""
import sys, time, json, warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, 'generation_two')

import numpy as np
import pandas as pd
from pathlib import Path

CACHE_DIR = Path('generation_two/shadow_scorer/cache/top3000')

print("=" * 70)
print("WQ SHADOW SCORER - FACTOR EVALUATION (FROM CACHE)")
print("=" * 70)

# ============================================================
# 1. Load from Parquet cache
# ============================================================
print("\n[1/3] Loading data from Parquet cache...")
t0 = time.time()

data = {}
for field in ['close', 'volume', 'high', 'low', 'open', 'returns', 'vwap', 'cap']:
    path = CACHE_DIR / f"{field}.parquet"
    if path.exists():
        data[field] = pd.read_parquet(path)
        print(f"    {field:10s}: {data[field].shape[0]:5d} days x {data[field].shape[1]:4d} stocks")
    else:
        print(f"    {field:10s}: NOT FOUND — run _pipeline.py first!")

# Load group data
group_data = {}
for gname in ['sector', 'subindustry']:
    path = CACHE_DIR / f"group_{gname}.parquet"
    if path.exists():
        gdf = pd.read_parquet(path)
        # Convert to Series (ticker -> group label) from first row
        group_data[gname] = gdf.iloc[0]
        print(f"    {gname:10s}: {gdf.shape[1]:4d} stocks")

elapsed_load = time.time() - t0
print(f"\n    Loaded in {elapsed_load:.1f}s (no download!)")

n_stocks = data['close'].shape[1]
n_days = data['close'].shape[0]
print(f"    Universe: {n_stocks} stocks x {n_days} trading days")
print(f"    Date range: {data['close'].index[0].date()} to {data['close'].index[-1].date()}")

# ============================================================
# 2. Evaluate factors
# ============================================================
from shadow_scorer.parser.evaluator import evaluate_expression
from shadow_scorer.scoring import score_alpha

FACTORS = [
    # -- Simple momentum/reversal --
    ("Momentum 5d",         "rank(ts_delta(close, 5))"),
    ("Momentum 20d",        "rank(ts_delta(close, 20))"),
    ("Mean Reversion 5d",   "-rank(ts_delta(close, 5))"),
    ("Mean Reversion 20d",  "-rank(ts_delta(close, 20))"),
    
    # -- Volume-based --
    ("Volume Surprise",     "rank(volume / ts_mean(volume, 20))"),
    ("Vol-Price Corr",      "-ts_corr(close, volume, 20)"),
    ("Vol Zscore",          "rank(ts_zscore(volume, 60))"),
    
    # -- Price patterns --
    ("Price/MA 20",         "rank(close / ts_mean(close, 20))"),
    ("Price/MA 60",         "rank(close / ts_mean(close, 60))"),
    ("VWAP Deviation",      "rank(close - vwap)"),
    ("Range Ratio",         "rank((high - low) / close)"),
    
    # -- Volatility --
    ("Realized Vol",        "-rank(ts_std_dev(returns, 20))"),
    ("Vol Regime",          "rank(ts_std_dev(returns, 5) / ts_std_dev(returns, 60))"),
    
    # -- Time-series decay/score --
    ("TS Zscore 60d",       "ts_zscore(close, 60)"),
    ("Decay Linear 10d",    "rank(ts_decay_linear(close, 10))"),
    ("Decay Linear 20d",    "rank(ts_decay_linear(close, 20))"),
    
    # -- Advanced compositions --
    ("Arg Max 20d",         "rank(ts_arg_max(close, 20))"),
    ("Arg Min 20d",         "-rank(ts_arg_min(close, 20))"),
    ("TS Scale 60d",        "rank(ts_scale(close, 60))"),
    ("Covar Close-Vol",     "rank(ts_covariance(close, volume, 20))"),
    
    # -- Group-based (if sector data available) --
    ("Sector Neutral Mom",  "group_neutralize(rank(ts_delta(close, 5)), sector)"),
    ("Sector Zscore Price", "group_zscore(close, sector)"),
    
    # -- Complex combos --
    ("Combined: ZS-Vol",    "rank(ts_zscore(close, 60)) - rank(ts_std_dev(returns, 20))"),
    ("Combo: Decay+Rank",   "rank(ts_decay_linear(rank(close), 10))"),
    ("Combo: Norm+Winsor",  "winsorize(normalize(ts_decay_linear(rank(close), 10)))"),
]

print(f"\n[2/3] Evaluating {len(FACTORS)} factors on {n_stocks} stocks...")
print("-" * 90)
print(f"{'Factor':<24s} {'IS Sharpe':>10s} {'OOS Sharpe':>10s} {'Turnover':>10s} {'Fitness':>10s} {'Pass':>6s}  {'Time':>5s}")
print("-" * 90)

results = []
for name, expr in FACTORS:
    t1 = time.time()
    try:
        alpha = evaluate_expression(expr, data, group_data)
        sr = score_alpha(
            alpha_weights=alpha,
            stock_returns=data['returns'],
            delay=1,
            # WQ-aligned dates (from database audit)
            is_start="2019-01-01",
            is_end="2023-12-31",
            oos_start="2024-01-01",
            oos_end="2026-04-30",
            truncation=0.08,       # WQ default
            pasteurization=True,   # WQ default
        )
        m = sr.to_dict()
        elapsed = time.time() - t1
        
        is_sh  = m['is_sharpe'] if m['is_sharpe'] is not None else float('nan')
        oos_sh = m['oos_sharpe'] if m['oos_sharpe'] is not None else float('nan')
        tvr    = m['turnover'] if m['turnover'] is not None else float('nan')
        fit    = m['fitness'] if m['fitness'] is not None else float('nan')
        pas    = m['passes_threshold']
        
        flag = " YES" if pas else "  no"
        print(f"{name:<24s} {is_sh:>10.3f} {oos_sh:>10.3f} {tvr:>10.3f} {fit:>10.4f} {flag:>6s}  {elapsed:.1f}s")
        
        results.append({
            "name": name, "expression": expr,
            "sharpe": m['sharpe'], "is_sharpe": is_sh, "oos_sharpe": oos_sh,
            "turnover": tvr, "fitness": fit, "passes": pas,
        })
    except Exception as e:
        elapsed = time.time() - t1
        print(f"{name:<24s} {'ERROR':>10s}  {str(e)[:55]}  {elapsed:.1f}s")
        results.append({"name": name, "expression": expr, "error": str(e)[:200]})

# ============================================================
# 3. Summary
# ============================================================
print("\n" + "=" * 90)
print("SUMMARY")
print("=" * 90)

ok = [r for r in results if 'error' not in r]
if ok:
    # Sort by OOS Sharpe
    ok_sorted = sorted(ok, key=lambda r: abs(r.get('oos_sharpe', 0)), reverse=True)
    passed = [r for r in ok if r.get('passes', False)]
    
    print(f"  Universe:          {n_stocks} stocks (TOP3000)")
    print(f"  IS period:         2019-01-01 to 2023-12-31 (WQ-aligned)")
    print(f"  OOS period:        2024-01-01 to 2026-04-30")
    print(f"  Truncation:        0.08 (WQ default)")
    print(f"  Pasteurization:    ON (WQ default)")
    print(f"  Factors evaluated: {len(ok)}/{len(FACTORS)}")
    print(f"  Passed threshold:  {len(passed)}")
    
    print(f"\n  TOP 5 by |OOS Sharpe|:")
    for i, r in enumerate(ok_sorted[:5]):
        print(f"    {i+1}. {r['name']:<24s} OOS={r['oos_sharpe']:+.3f}  IS={r['is_sharpe']:+.3f}  TVR={r['turnover']:.3f}")
    
    print(f"\n  TOP 5 by |IS Sharpe|:")
    is_sorted = sorted(ok, key=lambda r: abs(r.get('is_sharpe', 0)), reverse=True)
    for i, r in enumerate(is_sorted[:5]):
        print(f"    {i+1}. {r['name']:<24s} IS={r['is_sharpe']:+.3f}  OOS={r['oos_sharpe']:+.3f}  TVR={r['turnover']:.3f}")

# Save
output_path = 'generation_two/shadow_scorer/factor_results_sp500.json'
with open(output_path, 'w', encoding='utf-8') as f:
    json.dump(results, f, indent=2, ensure_ascii=False, default=str)
print(f"\n  Results saved: {output_path}")
print("=" * 90)
