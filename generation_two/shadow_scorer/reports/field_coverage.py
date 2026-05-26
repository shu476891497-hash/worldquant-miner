"""WQ Field Mapping Coverage Report.

Reads WQ's full field catalog (~7,600+ fields across D0/D1 universes) and
determines which fields can be mapped to local data sources (yfinance,
SimFin) as exact matches or computed proxies, and which are unavailable.

For unmapped but important fields, generates WRDS download guides with
exact database names, table names, column names, and SQL templates.
"""

from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import pandas as pd
    _HAS_PANDAS = True
except ImportError:
    _HAS_PANDAS = False

# ---------------------------------------------------------------------------
# Path constants – data-field cache locations
# ---------------------------------------------------------------------------
_BASE = Path(__file__).resolve().parent.parent.parent  # generation_two/
_D1_PATH = _BASE / "constants" / "data_fields_cache_USA_1_TOP3000.json"
_D0_PATH = _BASE / "constants" / "data_fields_cache_USA_0_TOP1000.json"
_D0_WHITELIST_PATH = _BASE / "constants" / "d0_fields_whitelist.json"

# ---------------------------------------------------------------------------
# Exact-match mappings: WQ field ID → (source, target column/expression)
# ---------------------------------------------------------------------------
YFINANCE_EXACT: Dict[str, str] = {
    "close": "Adj Close",
    "open": "Open",
    "high": "High",
    "low": "Low",
    "volume": "Volume",
    "returns": "pct_change(Adj Close)",
    "cap": "marketCap (yfinance info)",
    "sharesout": "sharesOutstanding (yfinance info)",
    "split": "Stock Splits",
    "dividend": "Dividends",
    "currency": "currency (yfinance info)",
    "country": "country (yfinance info)",
    "exchange": "exchange (yfinance info)",
    "industry": "industry (yfinance info)",
    "sector": "sector (yfinance info)",
    "market": "market (yfinance info)",
    "ticker": "symbol (yfinance info)",
}

SIMFIN_EXACT: Dict[str, str] = {
    # Income statement
    "sales": "Revenue",
    "revenue": "Revenue",
    "cogs": "Cost of Goods Sold",
    "gross_profit": "Gross Profit",
    "operating_income": "Operating Income (Loss)",
    "operating_expense": "Operating Expenses",
    "ebit": "EBIT",
    "ebitda": "EBITDA",
    "income": "Net Income",
    "income_beforeextra": "Net Income from Continuing Operations",
    "pretax_income": "Pretax Income (Loss)",
    "income_tax": "Income Tax (Expense) Benefit, Net",
    "interest_expense": "Interest Expense, Net",
    "rd_expense": "Research & Development",
    "sga_expense": "Selling, General & Administrative",
    "depre_amort": "Depreciation & Amortization",
    "eps": "Earnings Per Share, Diluted",
    # Balance sheet
    "assets": "Total Assets",
    "assets_curr": "Total Current Assets",
    "liabilities": "Total Liabilities",
    "liabilities_curr": "Total Current Liabilities",
    "equity": "Total Equity",
    "debt": "Total Debt",
    "debt_lt": "Long Term Debt",
    "debt_st": "Short Term Debt",
    "cash": "Cash & Cash Equivalents",
    "inventory": "Inventories",
    "receivable": "Accounts Receivable, Net",
    "goodwill": "Goodwill",
    "ppent": "Property, Plant & Equipment, Net",
    "retained_earnings": "Retained Earnings",
    "bookvalue_ps": "Book Value per Share (derived)",
    "working_capital": "Working Capital (derived: Current Assets - Current Liabilities)",
    # Cash flow
    "capex": "Capital Expenditures",
    "cashflow": "Net Cash from Operating Activities",
    "cashflow_op": "Net Cash from Operating Activities",
    "cashflow_fin": "Net Cash from Financing Activities",
    "cashflow_invst": "Net Cash from Investing Activities",
    "cashflow_dividends": "Dividends Paid",
    # Ratios
    "current_ratio": "Current Ratio (derived: Current Assets / Current Liabilities)",
    "return_assets": "Return on Assets (derived: Net Income / Total Assets)",
    "return_equity": "Return on Equity (derived: Net Income / Total Equity)",
    "inventory_turnover": "Inventory Turnover (derived: COGS / Avg Inventory)",
    "invested_capital": "Invested Capital (derived: Equity + Debt - Cash)",
    "enterprise_value": "Enterprise Value (derived: Market Cap + Debt - Cash)",
    "sales_growth": "Revenue Growth (derived: pct_change Revenue)",
    "sales_ps": "Revenue per Share (derived: Revenue / Shares Outstanding)",
    "employee": "Number of Employees",
    # Additional fundamental fields matching SimFin data
    "common_shares_outstanding_total": "Shares (Basic)",
    "shares_basic": "Shares (Basic)",
    "shares_diluted": "Shares (Diluted)",
    "eps_basic": "Earnings Per Share, Basic",
    "eps_diluted": "Earnings Per Share, Diluted",
    "net_income": "Net Income",
    "net_income_cont": "Net Income from Continuing Operations",
    "cash_st": "Cash & Cash Equivalents",
    "depreciation_amortization": "Depreciation & Amortization",
    "tax_expense": "Income Tax (Expense) Benefit, Net",
}

# ---------------------------------------------------------------------------
# Proxy mappings: WQ field ID → (source, computation expression)
# ---------------------------------------------------------------------------
PROXY_MAPPINGS: Dict[str, Tuple[str, str]] = {
    "vwap": ("yfinance", "(High + Low + Close) / 3"),
    "adv5": ("yfinance", "rolling_mean(Volume, 5)"),
    "adv10": ("yfinance", "rolling_mean(Volume, 10)"),
    "adv15": ("yfinance", "rolling_mean(Volume, 15)"),
    "adv20": ("yfinance", "rolling_mean(Volume, 20)"),
    "adv30": ("yfinance", "rolling_mean(Volume, 30)"),
    "adv60": ("yfinance", "rolling_mean(Volume, 60)"),
    "adv120": ("yfinance", "rolling_mean(Volume, 120)"),
    "adv180": ("yfinance", "rolling_mean(Volume, 180)"),
    "adjfactor": ("yfinance", "Close / Adj Close"),
    "cusip": ("yfinance", "yfinance info['cusip'] (limited)"),
    "isin": ("yfinance", "yfinance info['isin'] (limited)"),
    "subindustry": ("yfinance", "yfinance info['industryKey']"),
    # Fundamental proxies computable from SimFin
    "sustainable_growth_rate": ("simfin", "ROE * (1 - Dividend Payout Ratio)"),
    "tobins_q_ratio": ("simfin", "(Market Cap + Total Liabilities) / Total Assets"),
}

# Pattern-based proxy rules: (regex_pattern, source, expression_template)
_PROXY_PATTERNS: List[Tuple[str, str, str]] = [
    # ADV fields with various windows
    (r"^adv(\d+)$", "yfinance", "rolling_mean(Volume, {0})"),
    # Beta fields → computed from returns regression
    (r"^beta_last_(\d+)_days_spy$", "yfinance",
     "regression_beta(returns, SPY returns, window={0})"),
    # Correlation fields → computed from returns
    (r"^correlation_last_(\d+)_days_spy$", "yfinance",
     "rolling_corr(returns, SPY returns, window={0})"),
    # Historical volatility → std of returns
    (r"^historical_volatility_(\d+)$", "yfinance",
     "rolling_std(returns, {0}) * sqrt(252)"),
    # Parkinson volatility → from high/low
    (r"^parkinson_volatility_(\d+)$", "yfinance",
     "parkinson_volatility(High, Low, window={0})"),
    # Implied volatility fields (call, put, mean, skew)
    (r"^implied_volatility_(call|put|mean)_(\d+)$", "yfinance",
     "yfinance options chain: {0} IV at {1}d tenor"),
    (r"^implied_volatility_mean_skew_(\d+)$", "yfinance",
     "yfinance options chain: IV skew at {0}d tenor"),
    # Returns variants
    (r"^return_(\d+)d$", "yfinance", "pct_change(close, {0})"),
    # Relative returns
    (r"^rel_ret_(all|comp|cust|part)$", "yfinance",
     "relative returns vs {0} peers (computed from close)"),
    # Systematic/unsystematic risk
    (r"^systematic_risk_last_(\d+)_days$", "yfinance",
     "beta^2 * var(SPY) over {0} days"),
    (r"^unsystematic_risk_last_(\d+)_days$", "yfinance",
     "var(returns) - systematic_risk over {0} days"),
]

# ---------------------------------------------------------------------------
# WRDS download guide definitions
# ---------------------------------------------------------------------------
WRDS_GUIDES: List[Dict[str, Any]] = [
    {
        "name": "CRSP Daily Stock File",
        "description": "Stock prices, returns, market cap, shares outstanding",
        "database": "crsp",
        "table": "crsp.dsf",
        "key_columns": ["permno", "date", "prc", "ret", "shrout", "vol",
                        "cfacpr", "cfacshr", "bidlo", "askhi"],
        "relevant_wq_categories": ["pv"],
        "sql_template": (
            "SELECT permno, date, prc, ret, retx, shrout, vol, "
            "cfacpr, cfacshr, bidlo, askhi\n"
            "FROM crsp.dsf\n"
            "WHERE date BETWEEN '{start_date}' AND '{end_date}'\n"
            "  AND permno IN (SELECT permno FROM crsp.dsenames\n"
            "                 WHERE ticker IN ({tickers}))\n"
            "ORDER BY permno, date;"
        ),
        "unmapped_fields_served": [
            "prc", "ret", "shrout", "vol", "cfacpr", "cfacshr",
        ],
    },
    {
        "name": "CRSP Monthly Stock File",
        "description": "Monthly returns and delisting info",
        "database": "crsp",
        "table": "crsp.msf",
        "key_columns": ["permno", "date", "prc", "ret", "shrout", "vol"],
        "relevant_wq_categories": ["pv"],
        "sql_template": (
            "SELECT permno, date, prc, ret, retx, shrout, vol\n"
            "FROM crsp.msf\n"
            "WHERE date BETWEEN '{start_date}' AND '{end_date}'\n"
            "ORDER BY permno, date;"
        ),
        "unmapped_fields_served": [],
    },
    {
        "name": "Compustat Annual Fundamentals",
        "description": "Annual fundamental data (income statement, balance sheet, cash flow)",
        "database": "comp",
        "table": "comp.funda",
        "key_columns": ["gvkey", "datadate", "sale", "ebitda", "ni",
                        "oibdp", "at", "lt", "ceq", "capx", "dp",
                        "xsga", "xrd", "revt", "cogs", "txt", "oiadp",
                        "csho", "prcc_f", "epspx", "epsfi"],
        "relevant_wq_categories": ["fundamental"],
        "sql_template": (
            "SELECT gvkey, datadate, fyear, sale, ebitda, ni, oibdp,\n"
            "       at, lt, ceq, capx, dp, xsga, xrd, revt, cogs,\n"
            "       txt, oiadp, csho, prcc_f, epspx, epsfi\n"
            "FROM comp.funda\n"
            "WHERE indfmt = 'INDL'\n"
            "  AND datafmt = 'STD'\n"
            "  AND popsrc = 'D'\n"
            "  AND consol = 'C'\n"
            "  AND datadate BETWEEN '{start_date}' AND '{end_date}'\n"
            "ORDER BY gvkey, datadate;"
        ),
        "unmapped_fields_served": [
            "pretax_income", "interest_expense", "depreciation_amortization",
            "rd_expense", "sga_expense", "tax_expense",
        ],
    },
    {
        "name": "Compustat Quarterly Fundamentals",
        "description": "Quarterly fundamental data",
        "database": "comp",
        "table": "comp.fundq",
        "key_columns": ["gvkey", "datadate", "rdq", "saleq", "niq",
                        "oibdpq", "atq", "ltq", "ceqq", "capxq",
                        "cshoq", "epspxq"],
        "relevant_wq_categories": ["fundamental"],
        "sql_template": (
            "SELECT gvkey, datadate, rdq, fqtr, fyearq,\n"
            "       saleq, niq, oibdpq, atq, ltq, ceqq, capxq,\n"
            "       cshoq, epspxq\n"
            "FROM comp.fundq\n"
            "WHERE indfmt = 'INDL'\n"
            "  AND datafmt = 'STD'\n"
            "  AND popsrc = 'D'\n"
            "  AND consol = 'C'\n"
            "  AND datadate BETWEEN '{start_date}' AND '{end_date}'\n"
            "ORDER BY gvkey, datadate;"
        ),
        "unmapped_fields_served": [],
    },
    {
        "name": "Compustat Events",
        "description": "Compustat event-driven fundamental data (fnd6_eventv110* fields)",
        "database": "comp",
        "table": "comp.funda / comp.fundq (event-linked)",
        "key_columns": ["gvkey", "datadate", "rdq"],
        "relevant_wq_categories": ["fundamental"],
        "sql_template": (
            "-- Event-linked Compustat data for fnd6_eventv110 fields\n"
            "SELECT a.gvkey, a.datadate, a.rdq, a.saleq, a.niq\n"
            "FROM comp.fundq a\n"
            "WHERE a.indfmt = 'INDL'\n"
            "  AND a.datafmt = 'STD'\n"
            "  AND a.popsrc = 'D'\n"
            "  AND a.consol = 'C'\n"
            "  AND a.rdq BETWEEN '{start_date}' AND '{end_date}'\n"
            "ORDER BY a.gvkey, a.rdq;"
        ),
        "unmapped_fields_served": [
            "fnd6_eventv110 fields (event-dated fundamentals)",
        ],
    },
    {
        "name": "IBES Detail Estimates",
        "description": "Individual analyst EPS estimates",
        "database": "ibes",
        "table": "ibes.det_epsus",
        "key_columns": ["ticker", "analys", "fpedats", "estimator",
                        "value", "estcur", "pdf"],
        "relevant_wq_categories": ["analyst"],
        "sql_template": (
            "SELECT ticker, analys, fpedats, estimator, value,\n"
            "       estcur, pdf, fpi\n"
            "FROM ibes.det_epsus\n"
            "WHERE fpedats BETWEEN '{start_date}' AND '{end_date}'\n"
            "ORDER BY ticker, fpedats;"
        ),
        "unmapped_fields_served": [
            "analyst estimate detail",
        ],
    },
    {
        "name": "IBES Summary Statistics",
        "description": "Consensus analyst estimates (mean, median, high, low, count)",
        "database": "ibes",
        "table": "ibes.statsum_epsus",
        "key_columns": ["ticker", "statpers", "fpedats", "meanest",
                        "medest", "highest", "lowest", "numest",
                        "actual", "stdev"],
        "relevant_wq_categories": ["analyst"],
        "sql_template": (
            "SELECT ticker, statpers, fpedats, fpi,\n"
            "       meanest, medest, highest, lowest,\n"
            "       numest, actual, stdev\n"
            "FROM ibes.statsum_epsus\n"
            "WHERE statpers BETWEEN '{start_date}' AND '{end_date}'\n"
            "ORDER BY ticker, statpers;"
        ),
        "unmapped_fields_served": [
            "consensus_mean", "consensus_median", "consensus_high",
            "consensus_low", "num_estimates",
        ],
    },
    {
        "name": "IBES Actuals",
        "description": "Actual reported earnings for surprise calculations",
        "database": "ibes",
        "table": "ibes.actu_epsus",
        "key_columns": ["ticker", "pends", "value", "pdicity", "anndats"],
        "relevant_wq_categories": ["analyst"],
        "sql_template": (
            "SELECT ticker, pends, value, pdicity, anndats, curr_act\n"
            "FROM ibes.actu_epsus\n"
            "WHERE pends BETWEEN '{start_date}' AND '{end_date}'\n"
            "ORDER BY ticker, pends;"
        ),
        "unmapped_fields_served": [
            "earnings surprise", "actual EPS",
        ],
    },
    {
        "name": "OptionMetrics Option Prices",
        "description": "Options prices, implied volatility, and Greeks",
        "database": "optionm",
        "table": "optionm.opprcd",
        "key_columns": ["secid", "date", "exdate", "cp_flag",
                        "strike_price", "impl_volatility",
                        "delta", "gamma", "vega", "theta",
                        "best_bid", "best_offer", "volume",
                        "open_interest"],
        "relevant_wq_categories": ["option"],
        "sql_template": (
            "SELECT secid, date, exdate, cp_flag,\n"
            "       strike_price / 1000 AS strike,\n"
            "       impl_volatility, delta, gamma, vega, theta,\n"
            "       best_bid, best_offer, volume, open_interest\n"
            "FROM optionm.opprcd\n"
            "WHERE date BETWEEN '{start_date}' AND '{end_date}'\n"
            "ORDER BY secid, date, exdate, strike_price;"
        ),
        "unmapped_fields_served": [
            "implied_volatility", "option_delta", "option_gamma",
            "option_vega", "option_theta",
        ],
    },
    {
        "name": "OptionMetrics Volatility Surface",
        "description": "Standardized implied volatility surface by delta and maturity",
        "database": "optionm",
        "table": "optionm.vsurfd",
        "key_columns": ["secid", "date", "days", "delta", "impl_volatility",
                        "impl_strike", "dispersion", "cp_flag"],
        "relevant_wq_categories": ["option"],
        "sql_template": (
            "SELECT secid, date, days, delta,\n"
            "       impl_volatility, impl_strike, dispersion, cp_flag\n"
            "FROM optionm.vsurfd\n"
            "WHERE date BETWEEN '{start_date}' AND '{end_date}'\n"
            "ORDER BY secid, date, days, delta;"
        ),
        "unmapped_fields_served": [
            "implied_volatility_surface", "vol_skew", "vol_term_structure",
        ],
    },
    {
        "name": "RavenPack News Analytics",
        "description": "News sentiment scores and event data",
        "database": "ravenpack",
        "table": "ravenpack.rp_entity_news_v3",
        "key_columns": ["rp_entity_id", "event_sentiment_score",
                        "relevance", "novelty", "timestamp_utc",
                        "event_type", "topic"],
        "relevant_wq_categories": ["news", "sentiment"],
        "sql_template": (
            "SELECT rp_entity_id, timestamp_utc,\n"
            "       event_sentiment_score, relevance, novelty,\n"
            "       event_type, topic, headline\n"
            "FROM ravenpack.rp_entity_news_v3\n"
            "WHERE timestamp_utc BETWEEN '{start_date}' AND '{end_date}'\n"
            "  AND relevance >= 75\n"
            "ORDER BY timestamp_utc;"
        ),
        "unmapped_fields_served": [
            "news_sentiment", "event_type", "news_relevance",
        ],
    },
]

# ---------------------------------------------------------------------------
# WRDS category-to-table mapping for guide generation
# ---------------------------------------------------------------------------
_WRDS_CATEGORY_TABLE_MAP: Dict[str, Dict[str, str]] = {
    "pv": {
        "wrds_db": "crsp",
        "wrds_table": "crsp.dsf",
        "wrds_columns": "permno, date, prc, ret, vol, shrout, cfacpr",
    },
    "fundamental": {
        "wrds_db": "comp",
        "wrds_table": "comp.funda / comp.fundq",
        "wrds_columns": "gvkey, datadate, sale, ni, at, lt, ceq, capx",
    },
    "analyst": {
        "wrds_db": "ibes",
        "wrds_table": "ibes.statsum_epsus / ibes.det_epsus",
        "wrds_columns": "ticker, fpedats, meanest, medest, numest, actual",
    },
    "option": {
        "wrds_db": "optionm",
        "wrds_table": "optionm.opprcd / optionm.vsurfd",
        "wrds_columns": "secid, date, impl_volatility, delta, gamma, vega",
    },
    "news": {
        "wrds_db": "ravenpack",
        "wrds_table": "ravenpack.rp_entity_news_v3",
        "wrds_columns": "rp_entity_id, event_sentiment_score, relevance",
    },
    "sentiment": {
        "wrds_db": "ravenpack",
        "wrds_table": "ravenpack.rp_entity_news_v3",
        "wrds_columns": "rp_entity_id, event_sentiment_score, topic",
    },
    "model": {
        "wrds_db": "N/A",
        "wrds_table": "N/A (WQ proprietary models)",
        "wrds_columns": "N/A",
    },
    "socialmedia": {
        "wrds_db": "N/A",
        "wrds_table": "N/A (no WRDS equivalent)",
        "wrds_columns": "N/A",
    },
}


# ============================================================================
# Internal helpers
# ============================================================================

def _load_field_catalog(
    d1_path: Optional[str] = None,
    d0_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Load and deduplicate fields from D0 + D1 caches.

    Returns a list of unique field dicts (by ``id``), preserving D1 entry
    when a field appears in both universes.
    """
    d1 = Path(d1_path) if d1_path else _D1_PATH
    d0 = Path(d0_path) if d0_path else _D0_PATH

    seen: Dict[str, Dict[str, Any]] = {}

    for path in [d1, d0]:
        if not path.exists():
            continue
        with open(path, encoding="utf-8") as fh:
            fields = json.load(fh)
        for f in fields:
            fid = f["id"]
            if fid not in seen:
                seen[fid] = f

    return list(seen.values())


def _load_d0_whitelist(path: Optional[str] = None) -> Dict[str, Any]:
    """Load D0 whitelist file."""
    p = Path(path) if path else _D0_WHITELIST_PATH
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def _classify_field(field: Dict[str, Any]) -> Dict[str, Any]:
    """Classify a single WQ field into exact / proxy / unavailable."""
    fid: str = field["id"]
    category_id: str = field["category"]["id"]
    category_name: str = field["category"]["name"]
    subcategory_id: str = field.get("subcategory", {}).get("id", "")
    subcategory_name: str = field.get("subcategory", {}).get("name", "")
    dataset_name: str = field["dataset"]["name"]
    coverage = field.get("coverage", 0.0)
    user_count = field.get("userCount", 0)
    alpha_count = field.get("alphaCount", 0)

    base_result = {
        "field_id": fid,
        "category": category_id,
        "category_name": category_name,
        "subcategory": subcategory_id,
        "subcategory_name": subcategory_name,
        "dataset": dataset_name,
        "coverage": coverage,
        "user_count": user_count,
        "alpha_count": alpha_count,
        "wrds_table": None,
        "wrds_column": None,
    }

    # 1. Check explicit exact mappings
    if fid in YFINANCE_EXACT:
        return {
            **base_result,
            "status": "exact",
            "source": "yfinance",
            "target": YFINANCE_EXACT[fid],
        }
    if fid in SIMFIN_EXACT:
        return {
            **base_result,
            "status": "exact",
            "source": "simfin",
            "target": SIMFIN_EXACT[fid],
        }

    # 2. Check explicit proxy mappings
    if fid in PROXY_MAPPINGS:
        source, expr = PROXY_MAPPINGS[fid]
        return {
            **base_result,
            "status": "proxy",
            "source": source,
            "target": expr,
        }

    # 3. Check regex-based proxy patterns
    for pattern, source, expr_template in _PROXY_PATTERNS:
        m = re.match(pattern, fid)
        if m:
            expr = expr_template.format(*m.groups())
            return {
                **base_result,
                "status": "proxy",
                "source": source,
                "target": expr,
            }

    # 4. Category-level heuristics for partial matches
    #    PV fields with known prefixes
    if category_id == "pv":
        # Universe membership flags
        if fid.startswith("top") or fid.startswith("topsp"):
            return {
                **base_result,
                "status": "proxy",
                "source": "yfinance",
                "target": "market_cap rank filter",
            }
        # Relationship/sector/hierarchy fields (pv13_*)
        if fid.startswith("pv13_") or fid.startswith("rel_"):
            wrds_info = _WRDS_CATEGORY_TABLE_MAP.get(category_id, {})
            return {
                **base_result,
                "status": "unavailable",
                "source": None,
                "target": None,
                "wrds_table": wrds_info.get("wrds_table"),
                "wrds_column": wrds_info.get("wrds_columns"),
            }
        # primary_sector_focused_company_count
        if "company_count" in fid or "pureplay" in fid:
            return {
                **base_result,
                "status": "unavailable",
                "source": None,
                "target": None,
            }

    # 5. Fundamental fields – try SimFin fuzzy heuristics
    if category_id == "fundamental":
        # Common fundamental field name fragments that SimFin covers
        _simfin_fragments = [
            "revenue", "sales", "income", "profit", "loss", "ebitda",
            "equity", "asset", "liabilit", "debt", "cash", "capex",
            "depreciation", "amortization", "dividend", "eps", "share",
            "tax", "interest", "expense", "margin", "roe", "roa",
            "book_value", "bookvalue", "working_capital", "inventory",
            "receivable", "payable",
        ]
        fid_lower = fid.lower()
        for frag in _simfin_fragments:
            if frag in fid_lower:
                return {
                    **base_result,
                    "status": "proxy",
                    "source": "simfin",
                    "target": f"SimFin approximate: {fid} (heuristic match on '{frag}')",
                }

        # fnd6_ fields → Compustat annual/quarterly
        if fid.startswith("fnd6_"):
            return {
                **base_result,
                "status": "unavailable",
                "source": None,
                "target": None,
                "wrds_table": "comp.funda / comp.fundq",
                "wrds_column": f"Compustat variable: {fid.replace('fnd6_', '')}",
            }

        # fnd2_ fields → detailed fundamentals from Compustat
        if fid.startswith("fnd2_"):
            return {
                **base_result,
                "status": "unavailable",
                "source": None,
                "target": None,
                "wrds_table": "comp.funda / comp.fundq",
                "wrds_column": f"Compustat detailed: {fid.replace('fnd2_', '')}",
            }

        # fn_ fields → SEC filing data
        if fid.startswith("fn_"):
            return {
                **base_result,
                "status": "unavailable",
                "source": None,
                "target": None,
                "wrds_table": "comp.funda / comp.fundq",
                "wrds_column": f"Compustat/SEC: {fid.replace('fn_', '')}",
            }

        # est_* fields → analyst estimate fundamentals (IBES)
        if fid.startswith("est_"):
            return {
                **base_result,
                "status": "unavailable",
                "source": None,
                "target": None,
                "wrds_table": "ibes.statsum_epsus",
                "wrds_column": f"IBES estimate: {fid.replace('est_', '')}",
            }

    # 6. Analyst fields – IBES heuristics
    if category_id == "analyst":
        if any(kw in fid.lower() for kw in [
            "eps", "estimate", "consensus", "mean", "median",
            "numest", "actual", "guidance", "revision", "forecast",
            "high", "low", "down", "pu", "item", "preest",
        ]):
            return {
                **base_result,
                "status": "proxy",
                "source": "WRDS/IBES",
                "target": f"IBES approximate: {fid}",
                "wrds_table": "ibes.statsum_epsus / ibes.det_epsus",
                "wrds_column": f"IBES: {fid}",
            }
        # anl4_ fields are all analyst estimates
        if fid.startswith("anl4_"):
            return {
                **base_result,
                "status": "proxy",
                "source": "WRDS/IBES",
                "target": f"IBES: {fid}",
                "wrds_table": "ibes.statsum_epsus / ibes.det_epsus",
                "wrds_column": f"IBES: {fid}",
            }

    # 7. Option fields
    if category_id == "option":
        if any(kw in fid.lower() for kw in [
            "volatility", "iv", "delta", "gamma", "vega", "theta",
            "skew", "put", "call", "option",
        ]):
            return {
                **base_result,
                "status": "proxy",
                "source": "yfinance/OptionMetrics",
                "target": f"Options approximate: {fid}",
                "wrds_table": "optionm.opprcd / optionm.vsurfd",
                "wrds_column": f"OptionMetrics: {fid}",
            }

    # 8. News fields
    if category_id == "news":
        wrds_info = _WRDS_CATEGORY_TABLE_MAP.get("news", {})
        return {
            **base_result,
            "status": "unavailable",
            "source": None,
            "target": None,
            "wrds_table": wrds_info.get("wrds_table"),
            "wrds_column": wrds_info.get("wrds_columns"),
        }

    # 9. Sentiment fields
    if category_id == "sentiment":
        wrds_info = _WRDS_CATEGORY_TABLE_MAP.get("sentiment", {})
        return {
            **base_result,
            "status": "unavailable",
            "source": None,
            "target": None,
            "wrds_table": wrds_info.get("wrds_table"),
            "wrds_column": wrds_info.get("wrds_columns"),
        }

    # 10. Default: unavailable
    wrds_info = _WRDS_CATEGORY_TABLE_MAP.get(category_id, {})
    return {
        **base_result,
        "status": "unavailable",
        "source": None,
        "target": None,
        "wrds_table": wrds_info.get("wrds_table"),
        "wrds_column": wrds_info.get("wrds_columns"),
    }


def _build_wrds_guide(
    classified_fields: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Build WRDS download guide entries for important unmapped fields."""
    # Identify unmapped categories and match to WRDS guides
    unavailable_by_cat: Dict[str, int] = defaultdict(int)
    for f in classified_fields:
        if f["status"] == "unavailable":
            unavailable_by_cat[f["category"]] += 1

    guide_entries = []
    for guide in WRDS_GUIDES:
        relevant_cats = guide["relevant_wq_categories"]
        unmapped_count = sum(unavailable_by_cat.get(c, 0) for c in relevant_cats)
        if unmapped_count > 0:
            entry = {**guide, "unmapped_field_count": unmapped_count}
            guide_entries.append(entry)

    return guide_entries


# ============================================================================
# Markdown report generation
# ============================================================================

def _render_markdown(report: Dict[str, Any]) -> str:
    """Render the coverage report as a Markdown document."""
    lines: List[str] = []
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines.append("# WQ Field Mapping Coverage Report")
    lines.append("")
    lines.append(f"Generated: {ts}")
    lines.append("")

    # ---- Summary ----
    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Total WQ fields | {report['total_fields']:,} |")
    lines.append(f"| Exact matches | {report['mapped_exact']:,} |")
    lines.append(f"| Proxy matches | {report['mapped_proxy']:,} |")
    lines.append(f"| Unavailable | {report['unavailable']:,} |")
    lines.append(f"| **Coverage %** | **{report['coverage_pct']:.1f}%** |")
    lines.append("")

    # ---- By Category ----
    lines.append("## Coverage by Category")
    lines.append("")
    lines.append("| Category | Total | Exact | Proxy | Unavailable | Coverage % |")
    lines.append("|----------|-------|-------|-------|-------------|------------|")
    for cat_id, info in sorted(report["by_category"].items(),
                                key=lambda x: -x[1]["total"]):
        cov = info["coverage_pct"]
        lines.append(
            f"| {cat_id} | {info['total']:,} | {info['exact']:,} | "
            f"{info['proxy']:,} | {info['unavailable']:,} | {cov:.1f}% |"
        )
    lines.append("")

    # ---- Exact Matches Detail ----
    lines.append("## Exact Match Fields")
    lines.append("")
    exact_fields = [f for f in report["field_details"] if f["status"] == "exact"]
    if exact_fields:
        lines.append("| WQ Field | Source | Maps To |")
        lines.append("|----------|--------|---------|")
        for f in sorted(exact_fields, key=lambda x: x["field_id"]):
            lines.append(f"| `{f['field_id']}` | {f['source']} | {f['target']} |")
    lines.append("")

    # ---- Proxy Matches Detail ----
    lines.append("## Proxy Match Fields (sample)")
    lines.append("")
    proxy_fields = [f for f in report["field_details"] if f["status"] == "proxy"]
    if proxy_fields:
        lines.append("| WQ Field | Source | Computation |")
        lines.append("|----------|--------|-------------|")
        # Show first 50 proxies to keep report manageable
        for f in sorted(proxy_fields, key=lambda x: x["field_id"])[:50]:
            target = f.get("target") or "—"
            lines.append(f"| `{f['field_id']}` | {f.get('source', '—')} | {target} |")
        if len(proxy_fields) > 50:
            lines.append(f"| ... | ... | *({len(proxy_fields) - 50} more proxy fields)* |")
    lines.append("")

    # ---- WRDS Guide ----
    lines.append("## WRDS Download Guide")
    lines.append("")
    lines.append(
        "For fields that cannot be sourced from yfinance or SimFin, the "
        "following WRDS databases provide equivalent data:"
    )
    lines.append("")
    for guide in report["wrds_guide"]:
        lines.append(f"### {guide['name']}")
        lines.append("")
        lines.append(f"**Description:** {guide['description']}")
        lines.append("")
        lines.append(f"**Database:** `{guide['database']}`")
        lines.append("")
        lines.append(f"**Table:** `{guide['table']}`")
        lines.append("")
        lines.append(f"**Key columns:** `{'`, `'.join(guide['key_columns'])}`")
        lines.append("")
        lines.append(f"**Unmapped WQ fields served:** ~{guide.get('unmapped_field_count', '?')}")
        lines.append("")
        lines.append("**SQL template:**")
        lines.append("```sql")
        lines.append(guide["sql_template"])
        lines.append("```")
        lines.append("")

    return "\n".join(lines)


def _render_wrds_guide_markdown(
    wrds_entries: List[Dict[str, Any]],
    unmapped_fields: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Render WRDS download guide as a standalone Markdown document."""
    lines: List[str] = []
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines.append("# WRDS Download Guide for WQ Shadow Scorer")
    lines.append("")
    lines.append(f"Generated: {ts}")
    lines.append("")
    lines.append("This guide provides instructions for downloading data from WRDS")
    lines.append("to fill gaps in local data coverage for WQ alpha replication.")
    lines.append("")

    # Summary of unmapped fields by category
    if unmapped_fields:
        cat_counts: Dict[str, int] = defaultdict(int)
        for f in unmapped_fields:
            cat_counts[f["category"]] += 1
        lines.append("## Unmapped Fields by Category")
        lines.append("")
        lines.append("| Category | Unmapped Count |")
        lines.append("|----------|---------------|")
        for cat, cnt in sorted(cat_counts.items(), key=lambda x: -x[1]):
            lines.append(f"| {cat} | {cnt:,} |")
        lines.append("")

    # Detailed guide for each WRDS database
    for guide in wrds_entries:
        lines.append(f"## {guide['name']}")
        lines.append("")
        lines.append(f"**Description:** {guide['description']}")
        lines.append("")
        lines.append(f"**WRDS Database:** `{guide['database']}`")
        lines.append("")
        lines.append(f"**Table:** `{guide['table']}`")
        lines.append("")
        lines.append(f"**Key columns:** `{'`, `'.join(guide['key_columns'])}`")
        lines.append("")
        lines.append(f"**Estimated unmapped WQ fields served:** ~{guide.get('unmapped_field_count', '?')}")
        lines.append("")
        lines.append("### Download Instructions")
        lines.append("")
        lines.append("1. Log into WRDS at https://wrds-www.wharton.upenn.edu/")
        lines.append(f"2. Navigate to **{guide['database'].upper()}** in the left menu")
        lines.append(f"3. Select the **{guide['table']}** table")
        lines.append("4. Set your date range and ticker/identifier filters")
        lines.append("5. Select the columns listed above")
        lines.append("6. Download as CSV or submit via the WRDS Python API")
        lines.append("")
        lines.append("### SQL Template")
        lines.append("")
        lines.append("```sql")
        lines.append(guide["sql_template"])
        lines.append("```")
        lines.append("")
        lines.append("### Python (wrds library)")
        lines.append("")
        lines.append("```python")
        lines.append("import wrds")
        lines.append("conn = wrds.Connection()")
        lines.append(f'df = conn.raw_sql("""')
        lines.append(guide["sql_template"])
        lines.append('""")')
        lines.append("```")
        lines.append("")

    return "\n".join(lines)


# ============================================================================
# FieldCoverageAnalyzer class
# ============================================================================

class FieldCoverageAnalyzer:
    """Analyzes WQ field catalog and maps to available data sources."""

    def __init__(
        self,
        d1_fields_path: Optional[str] = None,
        d0_fields_path: Optional[str] = None,
        d0_whitelist_path: Optional[str] = None,
    ):
        """Load WQ field catalogs.

        Parameters
        ----------
        d1_fields_path : str, optional
            Path to data_fields_cache_USA_1_TOP3000.json
        d0_fields_path : str, optional
            Path to data_fields_cache_USA_0_TOP1000.json
        d0_whitelist_path : str, optional
            Path to d0_fields_whitelist.json
        """
        self._d1_path = d1_fields_path
        self._d0_path = d0_fields_path
        self._d0_whitelist_path = d0_whitelist_path

        # Load catalogs
        self._catalog = _load_field_catalog(d1_fields_path, d0_fields_path)
        self._whitelist = _load_d0_whitelist(d0_whitelist_path)

        # Classify all fields (lazy, computed once)
        self._classified: Optional[List[Dict[str, Any]]] = None

    def _ensure_classified(self) -> List[Dict[str, Any]]:
        """Classify all fields if not yet done."""
        if self._classified is None:
            self._classified = [_classify_field(f) for f in self._catalog]
        return self._classified

    def analyze_all_fields(self):
        """Analyze all 7600+ WQ fields and return mapping status.

        Returns a DataFrame (if pandas available) or list of dicts with columns:
        - field_id: WQ field name
        - category: field category from WQ
        - subcategory: field subcategory
        - source: mapped data source ('yfinance', 'simfin', 'wrds', 'unavailable')
        - local_field: mapped field name in local data
        - match_quality: 'exact', 'proxy', 'unavailable'
        - coverage: coverage percentage from WQ catalog
        - user_count: how many WQ users use this field
        - alpha_count: how many WQ alphas use this field
        - wrds_table: WRDS table name if applicable
        - wrds_column: WRDS column name if applicable
        """
        classified = self._ensure_classified()

        rows = []
        for f in classified:
            # Normalize source for unavailable
            source = f.get("source") or "unavailable"
            # Normalize WRDS/IBES etc. to "wrds" for simplified grouping
            if source.startswith("WRDS"):
                source_normalized = "wrds"
            elif source in ("yfinance", "simfin"):
                source_normalized = source
            elif "OptionMetrics" in source:
                source_normalized = "wrds"
            else:
                source_normalized = source if source != "unavailable" else "unavailable"

            rows.append({
                "field_id": f["field_id"],
                "category": f["category"],
                "subcategory": f.get("subcategory", ""),
                "source": source_normalized,
                "local_field": f.get("target"),
                "match_quality": f["status"],
                "coverage": f.get("coverage", 0.0),
                "user_count": f.get("user_count", 0),
                "alpha_count": f.get("alpha_count", 0),
                "wrds_table": f.get("wrds_table"),
                "wrds_column": f.get("wrds_column"),
            })

        if _HAS_PANDAS:
            return pd.DataFrame(rows)
        return rows

    def get_mapped_fields(self) -> List[str]:
        """Return list of WQ fields that have local data mappings."""
        classified = self._ensure_classified()
        return [
            f["field_id"] for f in classified
            if f["status"] in ("exact", "proxy")
        ]

    def get_unmapped_fields(self) -> List[str]:
        """Return list of WQ fields without local data."""
        classified = self._ensure_classified()
        return [
            f["field_id"] for f in classified
            if f["status"] == "unavailable"
        ]

    def generate_coverage_summary(self) -> dict:
        """Generate summary statistics.

        Returns dict with:
        - total_fields, mapped_count, unmapped_count
        - coverage_by_category
        - coverage_by_source
        - top_unmapped_by_usage (most used fields we don't have)
        """
        classified = self._ensure_classified()

        total = len(classified)
        mapped = [f for f in classified if f["status"] in ("exact", "proxy")]
        unmapped = [f for f in classified if f["status"] == "unavailable"]

        # Coverage by category
        by_category: Dict[str, Dict[str, Any]] = {}
        for f in classified:
            cat = f["category"]
            if cat not in by_category:
                by_category[cat] = {
                    "total": 0, "exact": 0, "proxy": 0, "unavailable": 0,
                }
            by_category[cat]["total"] += 1
            by_category[cat][f["status"]] += 1
        for cat, info in by_category.items():
            m = info["exact"] + info["proxy"]
            info["coverage_pct"] = round(
                (m / info["total"] * 100) if info["total"] else 0.0, 2
            )

        # Coverage by source
        by_source: Dict[str, int] = defaultdict(int)
        for f in classified:
            src = f.get("source") or "unavailable"
            by_source[src] += 1

        # Top unmapped by usage (sort by user_count + alpha_count)
        top_unmapped = sorted(
            unmapped,
            key=lambda x: -(x.get("user_count", 0) + x.get("alpha_count", 0)),
        )[:50]
        top_unmapped_list = [
            {
                "field_id": f["field_id"],
                "category": f["category"],
                "user_count": f.get("user_count", 0),
                "alpha_count": f.get("alpha_count", 0),
            }
            for f in top_unmapped
        ]

        return {
            "total_fields": total,
            "mapped_count": len(mapped),
            "unmapped_count": len(unmapped),
            "coverage_pct": round(
                (len(mapped) / total * 100) if total else 0.0, 2
            ),
            "coverage_by_category": by_category,
            "coverage_by_source": dict(by_source),
            "top_unmapped_by_usage": top_unmapped_list,
        }

    def generate_wrds_guide(self, fields: Optional[List[str]] = None) -> str:
        """Generate markdown guide for downloading data from WRDS.

        Parameters
        ----------
        fields : list of str, optional
            Specific field IDs to include. If None, includes all unmapped.

        Returns
        -------
        str
            Markdown-formatted WRDS download guide.
        """
        classified = self._ensure_classified()

        if fields is not None:
            field_set = set(fields)
            relevant = [f for f in classified if f["field_id"] in field_set]
        else:
            relevant = [f for f in classified if f["status"] == "unavailable"]

        wrds_entries = _build_wrds_guide(classified)
        return _render_wrds_guide_markdown(wrds_entries, relevant)


# ============================================================================
# Public API – top-level functions
# ============================================================================

def generate_coverage_report(
    output_path: Optional[str] = None,
    d1_fields_path: Optional[str] = None,
    d0_fields_path: Optional[str] = None,
) -> dict:
    """Top-level function to generate the full coverage report.

    Parameters
    ----------
    output_path : str, optional
        Directory to write report files into. If None, reports are written
        to ``shadow_scorer/reports/output/``.
    d1_fields_path : str, optional
        Path to D1 fields JSON.
    d0_fields_path : str, optional
        Path to D0 fields JSON.

    Returns
    -------
    dict
        Report dictionary with keys: total_fields, mapped_exact,
        mapped_proxy, unavailable, coverage_pct, by_category,
        field_details, wrds_guide.
    """
    analyzer = FieldCoverageAnalyzer(
        d1_fields_path=d1_fields_path,
        d0_fields_path=d0_fields_path,
    )

    classified = analyzer._ensure_classified()

    # Aggregate stats
    exact_count = sum(1 for f in classified if f["status"] == "exact")
    proxy_count = sum(1 for f in classified if f["status"] == "proxy")
    unavail_count = sum(1 for f in classified if f["status"] == "unavailable")
    total = len(classified)
    coverage = ((exact_count + proxy_count) / total * 100) if total else 0.0

    # Per-category breakdown
    by_category: Dict[str, Dict[str, Any]] = {}
    for f in classified:
        cat = f["category"]
        if cat not in by_category:
            by_category[cat] = {"total": 0, "exact": 0, "proxy": 0, "unavailable": 0}
        by_category[cat]["total"] += 1
        by_category[cat][f["status"]] += 1
    for cat, info in by_category.items():
        mapped = info["exact"] + info["proxy"]
        info["coverage_pct"] = (mapped / info["total"] * 100) if info["total"] else 0.0

    # WRDS guide
    wrds_guide = _build_wrds_guide(classified)

    report: Dict[str, Any] = {
        "total_fields": total,
        "mapped_exact": exact_count,
        "mapped_proxy": proxy_count,
        "unavailable": unavail_count,
        "coverage_pct": round(coverage, 2),
        "by_category": by_category,
        "field_details": classified,
        "wrds_guide": wrds_guide,
    }

    # Write output files
    output_dir = output_path
    if output_dir is None:
        output_dir = str(Path(__file__).resolve().parent / "output")
    os.makedirs(output_dir, exist_ok=True)

    # JSON report
    json_path = os.path.join(output_dir, "field_coverage_report.json")
    with open(json_path, "w", encoding="utf-8") as fh:
        # Serialize only what's JSON-safe (exclude DataFrame)
        json.dump(report, fh, indent=2, ensure_ascii=False)

    # Markdown report
    md_path = os.path.join(output_dir, "field_coverage_report.md")
    md_content = _render_markdown(report)
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(md_content)

    return report


def generate_wrds_guide(
    output_path: Optional[str] = None,
    fields: Optional[List[str]] = None,
    d1_fields_path: Optional[str] = None,
    d0_fields_path: Optional[str] = None,
) -> str:
    """Top-level function to generate WRDS download guide.

    Parameters
    ----------
    output_path : str, optional
        File path to write the guide. If None, returns the markdown string
        without writing.
    fields : list of str, optional
        Specific field IDs to cover. If None, covers all unmapped fields.
    d1_fields_path : str, optional
        Path to D1 fields JSON.
    d0_fields_path : str, optional
        Path to D0 fields JSON.

    Returns
    -------
    str
        Markdown-formatted WRDS download guide.
    """
    analyzer = FieldCoverageAnalyzer(
        d1_fields_path=d1_fields_path,
        d0_fields_path=d0_fields_path,
    )
    md = analyzer.generate_wrds_guide(fields=fields)

    if output_path:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as fh:
            fh.write(md)

    return md


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    out = sys.argv[1] if len(sys.argv) > 1 else None
    result = generate_coverage_report(out)
    print(f"Total fields:    {result['total_fields']:,}")
    print(f"Exact matches:   {result['mapped_exact']:,}")
    print(f"Proxy matches:   {result['mapped_proxy']:,}")
    print(f"Unavailable:     {result['unavailable']:,}")
    print(f"Coverage:        {result['coverage_pct']:.1f}%")
    print()
    print("By category:")
    for cat, info in sorted(result["by_category"].items(),
                             key=lambda x: -x[1]["total"]):
        print(f"  {cat:15s}  total={info['total']:>5,}  "
              f"exact={info['exact']:>4,}  proxy={info['proxy']:>4,}  "
              f"unavail={info['unavailable']:>5,}  cov={info['coverage_pct']:.1f}%")
