"""
WQ field name mapper — maps WorldQuant Brain field IDs to local data sources.

Reads the field catalog from the constants directory and provides a mapping
from each WQ field to (data_source, local_column, quality_level).

Quality levels:
- 'exact':        Direct one-to-one match with high fidelity
- 'proxy':        Approximate mapping (e.g., VWAP approximated from HLC)
- 'unavailable':  No local data source available
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from shadow_scorer.config import FIELD_CATALOG_PATH

logger = logging.getLogger(__name__)

# Quality level enum-like constants
EXACT = 'exact'
PROXY = 'proxy'
UNAVAILABLE = 'unavailable'

# Type alias for mapping entries
# (data_source, local_column_or_computation, quality)
FieldMapping = Tuple[str, str, str]


# ============================================================================
# Core field mappings — these MUST work
# ============================================================================

# yfinance price/volume fields
_YFINANCE_PRICE_FIELDS = {
    'close':   ('yfinance', 'Close',  EXACT),
    'open':    ('yfinance', 'Open',   EXACT),
    'high':    ('yfinance', 'High',   EXACT),
    'low':     ('yfinance', 'Low',    EXACT),
    'volume':  ('yfinance', 'Volume', EXACT),
    'vwap':    ('yfinance', 'vwap_approx', PROXY),   # (H+L+C)/3 approximation
    'returns': ('yfinance', 'returns', EXACT),         # pct_change(close)
    'cap':     ('yfinance', 'market_cap', EXACT),      # close * shares_outstanding
}

# SimFin income statement fields
_SIMFIN_INCOME_FIELDS = {
    'sales':             ('simfin', 'Revenue',           EXACT),
    'ebitda':            ('simfin', 'EBITDA',             EXACT),
    'operating_income':  ('simfin', 'Operating Income',   EXACT),
    'income':            ('simfin', 'Net Income',         EXACT),
    'net_income_adjusted': ('simfin', 'Net Income',       PROXY),
    'gross_profit':      ('simfin', 'Gross Profit',       EXACT),
}

# SimFin balance sheet fields
_SIMFIN_BALANCE_FIELDS = {
    'equity':    ('simfin', 'Total Equity',             EXACT),
    'assets':    ('simfin', 'Total Assets',             EXACT),
    'debt_lt':   ('simfin', 'Long Term Debt',           EXACT),
}

# SimFin cash flow fields
_SIMFIN_CASHFLOW_FIELDS = {
    'capex':              ('simfin', 'Capital Expenditures',       EXACT),
    'cashflow_dividends': ('simfin', 'Dividends Paid',             EXACT),
    'cashflow':           ('simfin', 'Net Cash from Operations',   EXACT),
    'cashflow_op':        ('simfin', 'Net Cash from Operations',   EXACT),
    'cashflow_fin':       ('simfin', 'Net Cash from Financing',    EXACT),
    'cashflow_invst':     ('simfin', 'Net Cash from Investing',    EXACT),
}

# Group / classification fields
_GROUP_FIELDS = {
    'sector':       ('yfinance', 'sector',       EXACT),
    'industry':     ('yfinance', 'industry',     EXACT),
    'subindustry':  ('yfinance', 'subindustry',  PROXY),  # yfinance doesn't have GICS subindustry
}

# Additional yfinance-derivable price fields (proxies)
_YFINANCE_DERIVED_FIELDS = {
    'return_on_equity':   ('yfinance', 'roe_derived', PROXY),
    'return_assets':      ('yfinance', 'roa_derived', PROXY),
    'dividend':           ('yfinance', 'dividends',   PROXY),
    'annual_dividend_yield': ('yfinance', 'dividend_yield', PROXY),
}


def _build_core_mapping() -> Dict[str, FieldMapping]:
    """Assemble the complete core mapping from all source maps."""
    mapping = {}
    mapping.update(_YFINANCE_PRICE_FIELDS)
    mapping.update(_SIMFIN_INCOME_FIELDS)
    mapping.update(_SIMFIN_BALANCE_FIELDS)
    mapping.update(_SIMFIN_CASHFLOW_FIELDS)
    mapping.update(_GROUP_FIELDS)
    mapping.update(_YFINANCE_DERIVED_FIELDS)
    return mapping


# Cached singleton
_CORE_MAPPING: Optional[Dict[str, FieldMapping]] = None
_FIELD_CATALOG: Optional[List[dict]] = None


def _load_field_catalog() -> List[dict]:
    """Load the WQ field catalog JSON."""
    global _FIELD_CATALOG
    if _FIELD_CATALOG is not None:
        return _FIELD_CATALOG

    catalog_path = Path(FIELD_CATALOG_PATH)
    if not catalog_path.exists():
        logger.warning(f"Field catalog not found: {catalog_path}")
        _FIELD_CATALOG = []
        return _FIELD_CATALOG

    try:
        with open(catalog_path, 'r', encoding='utf-8') as f:
            _FIELD_CATALOG = json.load(f)
        logger.info(f"Loaded field catalog: {len(_FIELD_CATALOG)} fields")
    except Exception as e:
        logger.error(f"Failed to load field catalog: {e}")
        _FIELD_CATALOG = []

    return _FIELD_CATALOG


def get_core_mapping() -> Dict[str, FieldMapping]:
    """Get the core field mapping (cached singleton)."""
    global _CORE_MAPPING
    if _CORE_MAPPING is None:
        _CORE_MAPPING = _build_core_mapping()
    return _CORE_MAPPING


def get_field_mapping(field_id: str) -> FieldMapping:
    """
    Look up a single WQ field and return its mapping.

    Parameters
    ----------
    field_id : str
        WQ field identifier (e.g., 'close', 'sales').

    Returns
    -------
    tuple
        (data_source, local_column, quality_level)
    """
    mapping = get_core_mapping()

    if field_id in mapping:
        return mapping[field_id]

    # Not in core mapping — mark as unavailable
    return ('none', field_id, UNAVAILABLE)


def get_field_source(field_id: str) -> str:
    """Return the data source for a field ('yfinance', 'simfin', 'none')."""
    source, _, _ = get_field_mapping(field_id)
    return source


def get_field_quality(field_id: str) -> str:
    """Return the quality level for a field mapping."""
    _, _, quality = get_field_mapping(field_id)
    return quality


def map_fields(field_ids: List[str]) -> Dict[str, FieldMapping]:
    """
    Map a list of WQ field IDs to their data source mappings.

    Parameters
    ----------
    field_ids : list of str
        WQ field identifiers.

    Returns
    -------
    dict
        field_id -> (data_source, local_column, quality)
    """
    return {fid: get_field_mapping(fid) for fid in field_ids}


def group_fields_by_source(field_ids: List[str]) -> Dict[str, List[str]]:
    """
    Group field IDs by their data source.

    Parameters
    ----------
    field_ids : list of str
        WQ field identifiers.

    Returns
    -------
    dict
        source_name -> list of field_ids from that source
    """
    groups: Dict[str, List[str]] = {}
    for fid in field_ids:
        source = get_field_source(fid)
        groups.setdefault(source, []).append(fid)
    return groups


def get_unmapped_fields() -> List[dict]:
    """
    Return all WQ catalog fields that are not mapped to any local source.

    Useful for generating a WRDS guide of missing fields.

    Returns
    -------
    list of dict
        Each dict contains 'id', 'description', 'dataset', 'category'.
    """
    catalog = _load_field_catalog()
    core = get_core_mapping()

    unmapped = []
    for entry in catalog:
        fid = entry.get('id', '')
        if fid not in core:
            unmapped.append({
                'id': fid,
                'description': entry.get('description', ''),
                'dataset': entry.get('dataset', {}).get('name', ''),
                'category': entry.get('category', {}).get('name', ''),
            })

    return unmapped


def get_coverage_stats() -> dict:
    """
    Compute coverage statistics for the field mapping.

    Returns
    -------
    dict
        {total_wq_fields, mapped_exact, mapped_proxy, unmapped, coverage_pct}
    """
    catalog = _load_field_catalog()
    core = get_core_mapping()

    total = len(catalog)
    exact_count = 0
    proxy_count = 0
    unmapped_count = 0

    catalog_ids = {entry.get('id', '') for entry in catalog}

    for fid in catalog_ids:
        if fid in core:
            _, _, quality = core[fid]
            if quality == EXACT:
                exact_count += 1
            elif quality == PROXY:
                proxy_count += 1
            else:
                unmapped_count += 1
        else:
            unmapped_count += 1

    mapped = exact_count + proxy_count
    coverage_pct = (mapped / total * 100) if total > 0 else 0.0

    return {
        'total_wq_fields': total,
        'mapped_exact': exact_count,
        'mapped_proxy': proxy_count,
        'unmapped': unmapped_count,
        'coverage_pct': round(coverage_pct, 2),
    }


def get_all_catalog_ids() -> List[str]:
    """Return sorted list of all WQ field IDs from the catalog."""
    catalog = _load_field_catalog()
    return sorted(entry.get('id', '') for entry in catalog)
