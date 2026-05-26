#!/usr/bin/env python3
"""
WQ Shadow Scorer — CLI Interface (M4)

Usage:
  # Single alpha evaluation
  python evaluate.py --expr "rank(ts_delta(close, 5))" --universe TOP3000 --delay 1

  # Batch evaluation (one expression per line in file)
  python evaluate.py --batch alphas.txt --universe TOP3000

  # With custom IS/OOS dates
  python evaluate.py --expr "..." --is-end 2022-12-31 --oos-start 2023-01-01
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

# Ensure shadow_scorer package is importable
_SHADOW_DIR = Path(__file__).resolve().parent
_GEN2_DIR = _SHADOW_DIR.parent
sys.path.insert(0, str(_GEN2_DIR))

from shadow_scorer.parser.evaluator import evaluate_expression
from shadow_scorer.scoring import score_alpha, ScoringResult, DEFAULT_THRESHOLDS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("shadow_scorer")


# ---------------------------------------------------------------------------
# Data loading (thin wrapper around data pipeline)
# ---------------------------------------------------------------------------

class DataManager:
    """Loads and caches market data for evaluation."""

    def __init__(self, data_dir: Optional[str] = None, universe: str = "TOP3000"):
        self.data_dir = Path(data_dir) if data_dir else _SHADOW_DIR / "cache"
        self.universe = universe
        self._data: Dict[str, pd.DataFrame] = {}
        self._returns: Optional[pd.DataFrame] = None
        self._group_data: Dict[str, pd.Series] = {}
        self._loaded = False

    def load(self):
        """Load data from Parquet cache or download if needed."""
        if self._loaded:
            return

        cache_dir = self.data_dir / self.universe.lower()

        if (cache_dir / "close.parquet").exists():
            logger.info(f"Loading cached data from {cache_dir}")
            self._load_from_cache(cache_dir)
        else:
            logger.info("No cached data found. Running data pipeline...")
            self._download_and_cache(cache_dir)

        self._loaded = True
        logger.info(
            f"Data loaded: {len(self._data)} fields, "
            f"{self._returns.shape if self._returns is not None else 'N/A'} returns matrix"
        )

    def _load_from_cache(self, cache_dir: Path):
        """Load all parquet files from cache."""
        for pq_file in cache_dir.glob("*.parquet"):
            field_name = pq_file.stem
            df = pd.read_parquet(pq_file)
            df.index = pd.to_datetime(df.index)
            self._data[field_name] = df

        if "returns" in self._data:
            self._returns = self._data["returns"]
        elif "close" in self._data:
            self._returns = self._data["close"].pct_change()

        # Load group data if available
        for group_name in ["sector", "industry", "subindustry"]:
            gf = cache_dir / f"group_{group_name}.parquet"
            if gf.exists():
                self._group_data[group_name] = pd.read_parquet(gf).iloc[-1]

    def _download_and_cache(self, cache_dir: Path):
        """Download data via pipeline and save to cache."""
        try:
            from shadow_scorer.data.pipeline import DataPipeline
            pipeline = DataPipeline(
                universe=self.universe,
                cache_dir=str(cache_dir),
            )
            pipeline.run()
            self._load_from_cache(cache_dir)
        except Exception as e:
            logger.error(f"Pipeline failed: {e}")
            logger.info("Falling back to minimal yfinance data...")
            self._download_minimal(cache_dir)

    def _download_minimal(self, cache_dir: Path):
        """Minimal fallback: download basic PV data via yfinance."""
        try:
            import yfinance as yf

            # Get S&P 500 tickers as proxy for TOP3000
            logger.info("Downloading S&P 500 tickers as proxy universe...")
            sp500_url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
            try:
                tables = pd.read_html(sp500_url)
                tickers = tables[0]["Symbol"].str.replace(".", "-", regex=False).tolist()
            except Exception:
                # Fallback: hardcoded top tickers
                tickers = [
                    "AAPL", "MSFT", "AMZN", "GOOGL", "META", "TSLA", "NVDA",
                    "BRK-B", "JPM", "JNJ", "V", "PG", "UNH", "HD", "MA",
                    "DIS", "BAC", "XOM", "CSCO", "VZ", "INTC", "KO", "PFE",
                    "MRK", "T", "PEP", "ABT", "ABBV", "CVX", "WMT",
                ]

            logger.info(f"Downloading {len(tickers)} tickers from yfinance...")
            data = yf.download(
                tickers, start="2018-01-01", end="2026-05-01",
                auto_adjust=True, threads=True, progress=True,
            )

            cache_dir.mkdir(parents=True, exist_ok=True)

            # Save OHLCV fields
            for field in ["Open", "High", "Low", "Close", "Volume"]:
                if field in data.columns.get_level_values(0):
                    df = data[field]
                    wq_name = field.lower()
                    df.to_parquet(cache_dir / f"{wq_name}.parquet")
                    self._data[wq_name] = df

            # Compute and save returns
            if "close" in self._data:
                self._returns = self._data["close"].pct_change()
                self._returns.to_parquet(cache_dir / "returns.parquet")
                self._data["returns"] = self._returns

            # Compute vwap proxy: (high + low + close) / 3
            if all(k in self._data for k in ["high", "low", "close"]):
                vwap = (self._data["high"] + self._data["low"] + self._data["close"]) / 3
                vwap.to_parquet(cache_dir / "vwap.parquet")
                self._data["vwap"] = vwap

            # Market cap proxy for universe construction
            if "close" in self._data and "volume" in self._data:
                # Very rough proxy: close * volume as liquidity measure
                cap = self._data["close"] * self._data["volume"]
                cap.to_parquet(cache_dir / "cap.parquet")
                self._data["cap"] = cap

            logger.info(f"Saved {len(self._data)} fields to {cache_dir}")

        except ImportError:
            logger.error("yfinance not installed! Run: pip install yfinance")
            raise

    @property
    def fields(self) -> Dict[str, pd.DataFrame]:
        self.load()
        return self._data

    @property
    def returns(self) -> pd.DataFrame:
        self.load()
        return self._returns

    @property
    def group_data(self) -> Dict[str, pd.Series]:
        self.load()
        return self._group_data


# ---------------------------------------------------------------------------
# Single alpha evaluation
# ---------------------------------------------------------------------------

def evaluate_single(
    expr: str,
    data_mgr: DataManager,
    delay: int = 1,
    is_start: str = "2019-01-01",
    is_end: str = "2022-12-31",
    oos_start: str = "2023-01-01",
    oos_end: str = "2026-04-30",
) -> dict:
    """Evaluate a single alpha expression and return metrics."""
    t0 = time.time()

    # 1. Parse + evaluate expression
    try:
        alpha_weights = evaluate_expression(
            expr,
            data=data_mgr.fields,
            group_data=data_mgr.group_data,
        )
    except Exception as e:
        return {
            "expression": expr,
            "status": "PARSE_ERROR",
            "error": str(e),
            "elapsed_seconds": round(time.time() - t0, 2),
        }

    # 2. Extract referenced fields for coverage report
    import re
    referenced_fields = set(re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*', expr))
    # Remove operator names
    from shadow_scorer.parser.operators import OPERATOR_REGISTRY
    op_names = set(OPERATOR_REGISTRY.keys())
    referenced_fields -= op_names
    # Remove keywords/numbers
    referenced_fields -= {"true", "false", "nan", "sector", "industry", "subindustry"}

    available_fields = set(data_mgr.fields.keys())
    mapped = referenced_fields & available_fields
    unmapped = referenced_fields - available_fields

    # 3. Score
    try:
        result = score_alpha(
            alpha_weights=alpha_weights,
            stock_returns=data_mgr.returns,
            delay=delay,
            is_start=is_start,
            is_end=is_end,
            oos_start=oos_start,
            oos_end=oos_end,
        )
    except Exception as e:
        return {
            "expression": expr,
            "status": "SCORING_ERROR",
            "error": str(e),
            "elapsed_seconds": round(time.time() - t0, 2),
        }

    elapsed = round(time.time() - t0, 2)

    return {
        "expression": expr,
        "status": "OK",
        "delay": delay,
        "elapsed_seconds": elapsed,
        "metrics": result.to_dict(),
        "field_coverage": {
            "total_referenced": len(referenced_fields),
            "mapped": len(mapped),
            "unmapped": sorted(unmapped),
            "coverage_pct": round(100 * len(mapped) / max(1, len(referenced_fields)), 1),
        },
    }


# ---------------------------------------------------------------------------
# Batch evaluation
# ---------------------------------------------------------------------------

def evaluate_batch(
    exprs: List[str],
    data_mgr: DataManager,
    delay: int = 1,
    **kwargs,
) -> List[dict]:
    """Evaluate a batch of alpha expressions."""
    results = []
    for i, expr in enumerate(exprs):
        logger.info(f"[{i+1}/{len(exprs)}] Evaluating: {expr[:80]}...")
        r = evaluate_single(expr, data_mgr, delay=delay, **kwargs)
        results.append(r)

        status = r["status"]
        if status == "OK":
            m = r["metrics"]
            logger.info(
                f"  → IS Sharpe={m.get('is_sharpe', 'N/A')}, "
                f"OOS Sharpe={m.get('oos_sharpe', 'N/A')}, "
                f"Fitness={m.get('fitness', 'N/A')}, "
                f"Pass={m.get('passes_threshold', False)}"
            )
        else:
            logger.warning(f"  → {status}: {r.get('error', '')[:100]}")

    # Summary
    ok_count = sum(1 for r in results if r["status"] == "OK")
    pass_count = sum(
        1 for r in results
        if r["status"] == "OK" and r["metrics"].get("passes_threshold", False)
    )
    logger.info(
        f"\nBatch complete: {ok_count}/{len(exprs)} evaluated, "
        f"{pass_count} passed thresholds"
    )

    return results


# ---------------------------------------------------------------------------
# Integration API (for continuous_evolution.py)
# ---------------------------------------------------------------------------

# Singleton data manager for reuse
_SHARED_DATA_MGR: Optional[DataManager] = None


def quick_score(
    expr: str,
    delay: int = 1,
    universe: str = "TOP3000",
) -> Optional[dict]:
    """Quick-score an alpha for integration with continuous_evolution.py.
    
    Returns None if scoring fails, otherwise a dict with key metrics.
    
    Usage from continuous_evolution.py:
        from shadow_scorer.evaluate import quick_score
        result = quick_score("rank(ts_delta(close, 5))", delay=1)
        if result and result["oos_sharpe"] > 1.0:
            # Submit to WQ
    """
    global _SHARED_DATA_MGR
    if _SHARED_DATA_MGR is None or _SHARED_DATA_MGR.universe != universe:
        _SHARED_DATA_MGR = DataManager(universe=universe)

    try:
        r = evaluate_single(expr, _SHARED_DATA_MGR, delay=delay)
        if r["status"] != "OK":
            return None
        m = r["metrics"]
        return {
            "is_sharpe": m.get("is_sharpe"),
            "oos_sharpe": m.get("oos_sharpe"),
            "is_fitness": m.get("is_fitness"),
            "oos_fitness": m.get("oos_fitness"),
            "turnover": m.get("turnover"),
            "max_drawdown": m.get("max_drawdown"),
            "passes": m.get("passes_threshold", False),
            "coverage_pct": r["field_coverage"]["coverage_pct"],
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="WQ Shadow Scorer — Local OOS Alpha Evaluator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python evaluate.py --expr "rank(ts_delta(close, 5))" --universe TOP3000 --delay 1
  python evaluate.py --batch alphas.txt --universe TOP3000
  python evaluate.py --expr "group_neutralize(ts_zscore(volume, 20), sector)" --delay 0
        """,
    )

    # Input
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--expr", type=str, help="Single alpha expression to evaluate")
    group.add_argument("--batch", type=str, help="File with one expression per line")

    # Configuration
    parser.add_argument("--universe", type=str, default="TOP3000",
                        choices=["TOP500", "TOP1000", "TOP2000", "TOP3000"],
                        help="Stock universe (default: TOP3000)")
    parser.add_argument("--delay", type=int, default=1,
                        help="Signal delay in days (default: 1)")
    parser.add_argument("--data-dir", type=str, default=None,
                        help="Data cache directory")

    # Date ranges
    parser.add_argument("--is-start", type=str, default="2019-01-01")
    parser.add_argument("--is-end", type=str, default="2022-12-31")
    parser.add_argument("--oos-start", type=str, default="2023-01-01")
    parser.add_argument("--oos-end", type=str, default="2026-04-30")

    # Output
    parser.add_argument("--output", type=str, default=None,
                        help="Output JSON file (default: stdout)")
    parser.add_argument("--verbose", "-v", action="store_true")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Initialize data manager
    data_mgr = DataManager(data_dir=args.data_dir, universe=args.universe)

    date_kwargs = {
        "is_start": args.is_start,
        "is_end": args.is_end,
        "oos_start": args.oos_start,
        "oos_end": args.oos_end,
    }

    # Execute
    if args.expr:
        logger.info(f"Evaluating: {args.expr}")
        result = evaluate_single(
            args.expr, data_mgr, delay=args.delay, **date_kwargs,
        )
        output = result
    else:
        # Batch mode
        batch_file = Path(args.batch)
        if not batch_file.exists():
            logger.error(f"Batch file not found: {batch_file}")
            sys.exit(1)

        exprs = [
            line.strip()
            for line in batch_file.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        logger.info(f"Loaded {len(exprs)} expressions from {batch_file}")

        results = evaluate_batch(exprs, data_mgr, delay=args.delay, **date_kwargs)
        output = {"batch_size": len(exprs), "results": results}

    # Output
    output_json = json.dumps(output, indent=2, ensure_ascii=False, default=str)

    if args.output:
        Path(args.output).write_text(output_json, encoding="utf-8")
        logger.info(f"Results saved to {args.output}")
    else:
        print(output_json)


if __name__ == "__main__":
    main()
