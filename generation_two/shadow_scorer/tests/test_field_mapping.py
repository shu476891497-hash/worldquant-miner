"""Tests for WQ field mapping coverage report.

Validates that:
1. At least 200+ fields map to available data sources
2. All core OHLCV fields are mapped with exact matches
3. WRDS guide generation produces valid entries for unmapped fields
4. Category breakdowns are consistent with totals
5. Report output files are created correctly
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

# ── import the module under test ──────────────────────────────────────────
from reports.field_coverage import (
    PROXY_MAPPINGS,
    SIMFIN_EXACT,
    WRDS_GUIDES,
    YFINANCE_EXACT,
    generate_coverage_report,
    _classify_field,
    _load_field_catalog,
)


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def report() -> dict:
    """Generate the report once for all tests in this module."""
    with tempfile.TemporaryDirectory() as tmpdir:
        return generate_coverage_report(output_dir=tmpdir)


@pytest.fixture(scope="module")
def report_with_files() -> tuple[dict, str]:
    """Generate report and keep the output directory for file checks."""
    tmpdir = tempfile.mkdtemp(prefix="wq_coverage_")
    result = generate_coverage_report(output_dir=tmpdir)
    return result, tmpdir


# ═══════════════════════════════════════════════════════════════════════════
# Test: Minimum mapping coverage threshold
# ═══════════════════════════════════════════════════════════════════════════

class TestMinimumCoverage:
    """At least 200+ fields must map to an available data source."""

    def test_at_least_200_mapped_fields(self, report: dict) -> None:
        mapped = report["mapped_exact"] + report["mapped_proxy"]
        assert mapped >= 200, (
            f"Expected at least 200 mapped fields, got {mapped} "
            f"(exact={report['mapped_exact']}, proxy={report['mapped_proxy']})"
        )

    def test_coverage_percentage_positive(self, report: dict) -> None:
        assert report["coverage_pct"] > 0, "Coverage percentage should be > 0"

    def test_total_fields_exceeds_1000(self, report: dict) -> None:
        """Sanity check: the WQ catalog has 7,000+ fields."""
        assert report["total_fields"] > 1000, (
            f"Expected 1000+ total fields, got {report['total_fields']}"
        )

    def test_counts_sum_to_total(self, report: dict) -> None:
        total = report["mapped_exact"] + report["mapped_proxy"] + report["unavailable"]
        assert total == report["total_fields"], (
            f"exact({report['mapped_exact']}) + proxy({report['mapped_proxy']}) + "
            f"unavail({report['unavailable']}) = {total} != total({report['total_fields']})"
        )


# ═══════════════════════════════════════════════════════════════════════════
# Test: Core fields must be exact-mapped
# ═══════════════════════════════════════════════════════════════════════════

class TestCoreFieldMappings:
    """All core OHLCV + fundamental fields must be mapped."""

    CORE_PRICE_FIELDS = ["close", "open", "high", "low", "volume", "returns"]
    CORE_MARKET_FIELDS = ["cap", "sharesout"]
    CORE_FUNDAMENTAL_FIELDS = [
        "sales", "revenue", "ebitda", "operating_income",
        "equity", "assets", "debt_lt", "capex", "cashflow_dividends",
    ]

    def _find_field(self, report: dict, field_id: str) -> dict | None:
        for f in report["field_details"]:
            if f["field_id"] == field_id:
                return f
        return None

    @pytest.mark.parametrize("field_id", CORE_PRICE_FIELDS)
    def test_core_price_field_mapped(self, report: dict, field_id: str) -> None:
        f = self._find_field(report, field_id)
        assert f is not None, f"Core field '{field_id}' not found in report"
        assert f["status"] == "exact", (
            f"Core price field '{field_id}' should be exact-mapped, "
            f"got status='{f['status']}'"
        )

    @pytest.mark.parametrize("field_id", CORE_MARKET_FIELDS)
    def test_core_market_field_mapped(self, report: dict, field_id: str) -> None:
        f = self._find_field(report, field_id)
        assert f is not None, f"Core field '{field_id}' not found in report"
        assert f["status"] == "exact", (
            f"Core market field '{field_id}' should be exact-mapped, "
            f"got status='{f['status']}'"
        )

    @pytest.mark.parametrize("field_id", CORE_FUNDAMENTAL_FIELDS)
    def test_core_fundamental_field_mapped(self, report: dict, field_id: str) -> None:
        f = self._find_field(report, field_id)
        assert f is not None, f"Core field '{field_id}' not found in report"
        assert f["status"] in ("exact", "proxy"), (
            f"Core fundamental field '{field_id}' should be mapped, "
            f"got status='{f['status']}'"
        )

    def test_vwap_is_proxy(self, report: dict) -> None:
        f = self._find_field(report, "vwap")
        assert f is not None, "vwap not found in report"
        assert f["status"] == "proxy", f"vwap should be proxy, got {f['status']}"

    def test_adv20_is_proxy(self, report: dict) -> None:
        f = self._find_field(report, "adv20")
        assert f is not None, "adv20 not found in report"
        assert f["status"] == "proxy", f"adv20 should be proxy, got {f['status']}"


# ═══════════════════════════════════════════════════════════════════════════
# Test: WRDS guide generation
# ═══════════════════════════════════════════════════════════════════════════

class TestWRDSGuide:
    """WRDS download guide should be populated for unmapped categories."""

    def test_wrds_guide_not_empty(self, report: dict) -> None:
        assert len(report["wrds_guide"]) > 0, "WRDS guide should have entries"

    def test_wrds_guide_has_required_keys(self, report: dict) -> None:
        required = {"name", "database", "table", "key_columns", "sql_template"}
        for entry in report["wrds_guide"]:
            missing = required - set(entry.keys())
            assert not missing, (
                f"WRDS guide entry '{entry.get('name', '?')}' "
                f"missing keys: {missing}"
            )

    def test_wrds_guide_covers_crsp(self, report: dict) -> None:
        crsp_entries = [g for g in report["wrds_guide"]
                        if g["database"] == "crsp"]
        assert len(crsp_entries) > 0, "WRDS guide should include CRSP entries"

    def test_wrds_guide_covers_compustat(self, report: dict) -> None:
        comp_entries = [g for g in report["wrds_guide"]
                        if g["database"] == "comp"]
        assert len(comp_entries) > 0, "WRDS guide should include Compustat entries"

    def test_wrds_guide_covers_ibes(self, report: dict) -> None:
        ibes_entries = [g for g in report["wrds_guide"]
                        if g["database"] == "ibes"]
        assert len(ibes_entries) > 0, "WRDS guide should include IBES entries"

    def test_wrds_guide_covers_optionmetrics(self, report: dict) -> None:
        om_entries = [g for g in report["wrds_guide"]
                      if g["database"] == "optionm"]
        assert len(om_entries) > 0, "WRDS guide should include OptionMetrics"

    def test_wrds_sql_templates_have_placeholders(self, report: dict) -> None:
        for entry in report["wrds_guide"]:
            sql = entry["sql_template"]
            assert "{start_date}" in sql or "start_date" in sql, (
                f"SQL template for '{entry['name']}' missing date placeholder"
            )

    def test_wrds_guide_has_unmapped_field_counts(self, report: dict) -> None:
        for entry in report["wrds_guide"]:
            count = entry.get("unmapped_field_count", 0)
            assert count > 0, (
                f"WRDS entry '{entry['name']}' should have "
                f"unmapped_field_count > 0, got {count}"
            )


# ═══════════════════════════════════════════════════════════════════════════
# Test: Category breakdown consistency
# ═══════════════════════════════════════════════════════════════════════════

class TestCategoryBreakdown:
    """Per-category stats must be consistent with field-level data."""

    def test_all_categories_present(self, report: dict) -> None:
        expected_cats = {"pv", "fundamental", "model", "analyst"}
        actual_cats = set(report["by_category"].keys())
        missing = expected_cats - actual_cats
        assert not missing, f"Missing expected categories: {missing}"

    def test_category_totals_sum_to_overall(self, report: dict) -> None:
        cat_total = sum(info["total"]
                        for info in report["by_category"].values())
        assert cat_total == report["total_fields"], (
            f"Category totals ({cat_total}) != overall total "
            f"({report['total_fields']})"
        )

    def test_each_category_consistent(self, report: dict) -> None:
        for cat, info in report["by_category"].items():
            subtotal = info["exact"] + info["proxy"] + info["unavailable"]
            assert subtotal == info["total"], (
                f"Category '{cat}': exact({info['exact']}) + "
                f"proxy({info['proxy']}) + unavail({info['unavailable']}) "
                f"= {subtotal} != total({info['total']})"
            )

    def test_pv_category_has_exact_matches(self, report: dict) -> None:
        pv = report["by_category"].get("pv")
        assert pv is not None, "pv category not found"
        assert pv["exact"] > 0, "pv category should have exact matches"

    def test_model_category_mostly_unavailable(self, report: dict) -> None:
        model = report["by_category"].get("model")
        assert model is not None, "model category not found"
        # WQ proprietary models – most should be unavailable
        assert model["unavailable"] > model["exact"] + model["proxy"], (
            "model category should be mostly unavailable"
        )


# ═══════════════════════════════════════════════════════════════════════════
# Test: Report output file generation
# ═══════════════════════════════════════════════════════════════════════════

class TestReportOutput:
    """Report files (JSON + Markdown) must be created and valid."""

    def test_json_file_created(self, report_with_files: tuple) -> None:
        _, tmpdir = report_with_files
        json_path = os.path.join(tmpdir, "field_coverage_report.json")
        assert os.path.isfile(json_path), f"JSON report not found at {json_path}"

    def test_json_file_valid(self, report_with_files: tuple) -> None:
        _, tmpdir = report_with_files
        json_path = os.path.join(tmpdir, "field_coverage_report.json")
        with open(json_path, encoding="utf-8") as fh:
            data = json.load(fh)
        assert "total_fields" in data
        assert "field_details" in data

    def test_markdown_file_created(self, report_with_files: tuple) -> None:
        _, tmpdir = report_with_files
        md_path = os.path.join(tmpdir, "field_coverage_report.md")
        assert os.path.isfile(md_path), f"Markdown report not found at {md_path}"

    def test_markdown_contains_summary(self, report_with_files: tuple) -> None:
        _, tmpdir = report_with_files
        md_path = os.path.join(tmpdir, "field_coverage_report.md")
        with open(md_path, encoding="utf-8") as fh:
            content = fh.read()
        assert "## Summary" in content
        assert "Coverage" in content

    def test_markdown_contains_wrds_guide(self, report_with_files: tuple) -> None:
        _, tmpdir = report_with_files
        md_path = os.path.join(tmpdir, "field_coverage_report.md")
        with open(md_path, encoding="utf-8") as fh:
            content = fh.read()
        assert "WRDS Download Guide" in content
        assert "crsp" in content.lower()


# ═══════════════════════════════════════════════════════════════════════════
# Test: Field classification unit tests
# ═══════════════════════════════════════════════════════════════════════════

class TestFieldClassification:
    """Unit tests for individual field classification logic."""

    @staticmethod
    def _make_field(field_id: str, category: str = "pv",
                    dataset: str = "Price Volume") -> dict:
        return {
            "id": field_id,
            "category": {"id": category, "name": category.title()},
            "subcategory": {"id": f"{category}-test", "name": "Test"},
            "dataset": {"id": "test", "name": dataset},
        }

    def test_close_classified_as_exact_yfinance(self) -> None:
        f = _classify_field(self._make_field("close"))
        assert f["status"] == "exact"
        assert f["source"] == "yfinance"

    def test_ebitda_classified_as_exact_simfin(self) -> None:
        f = _classify_field(
            self._make_field("ebitda", category="fundamental",
                             dataset="Company Fundamental Data")
        )
        assert f["status"] == "exact"
        assert f["source"] == "simfin"

    def test_vwap_classified_as_proxy(self) -> None:
        f = _classify_field(self._make_field("vwap"))
        assert f["status"] == "proxy"
        assert "(High + Low + Close) / 3" in f["target"]

    def test_unknown_model_field_classified_unavailable(self) -> None:
        f = _classify_field(
            self._make_field("wq_proprietary_xyz_model", category="model",
                             dataset="Analysts' Factor Model")
        )
        assert f["status"] == "unavailable"

    def test_beta_pattern_match(self) -> None:
        f = _classify_field(
            self._make_field("beta_last_60_days_spy", category="model",
                             dataset="Systematic Risk Metrics")
        )
        assert f["status"] == "proxy"
        assert "60" in f["target"]

    def test_historical_volatility_pattern_match(self) -> None:
        f = _classify_field(
            self._make_field("historical_volatility_30", category="option",
                             dataset="Volatility Data")
        )
        assert f["status"] == "proxy"
        assert "30" in f["target"]

    def test_ticker_classified_as_exact(self) -> None:
        f = _classify_field(self._make_field("ticker"))
        assert f["status"] == "exact"
        assert f["source"] == "yfinance"


# ═══════════════════════════════════════════════════════════════════════════
# Test: Mapping dictionaries are well-formed
# ═══════════════════════════════════════════════════════════════════════════

class TestMappingDictionaries:
    """Verify integrity of the mapping lookup tables."""

    def test_yfinance_exact_not_empty(self) -> None:
        assert len(YFINANCE_EXACT) >= 5

    def test_simfin_exact_not_empty(self) -> None:
        assert len(SIMFIN_EXACT) >= 5

    def test_proxy_mappings_not_empty(self) -> None:
        assert len(PROXY_MAPPINGS) >= 3

    def test_no_overlap_yfinance_simfin(self) -> None:
        overlap = set(YFINANCE_EXACT.keys()) & set(SIMFIN_EXACT.keys())
        assert not overlap, f"Fields mapped in both yfinance and SimFin: {overlap}"

    def test_wrds_guides_have_valid_databases(self) -> None:
        valid_dbs = {"crsp", "comp", "ibes", "optionm", "ravenpack"}
        for guide in WRDS_GUIDES:
            assert guide["database"] in valid_dbs, (
                f"Unknown WRDS database: {guide['database']}"
            )


# ═══════════════════════════════════════════════════════════════════════════
# Test: Field catalog loading
# ═══════════════════════════════════════════════════════════════════════════

class TestFieldCatalogLoading:
    """Verify the field catalog loads correctly."""

    def test_catalog_loads(self) -> None:
        catalog = _load_field_catalog()
        assert len(catalog) > 0, "Field catalog should not be empty"

    def test_catalog_has_expected_size(self) -> None:
        catalog = _load_field_catalog()
        assert len(catalog) > 5000, (
            f"Expected 5000+ fields, got {len(catalog)}"
        )

    def test_catalog_fields_have_required_keys(self) -> None:
        catalog = _load_field_catalog()
        required = {"id", "category", "dataset"}
        for f in catalog[:100]:  # Sample first 100
            missing = required - set(f.keys())
            assert not missing, (
                f"Field '{f.get('id', '?')}' missing keys: {missing}"
            )

    def test_catalog_deduplicates(self) -> None:
        catalog = _load_field_catalog()
        ids = [f["id"] for f in catalog]
        assert len(ids) == len(set(ids)), "Catalog should deduplicate field IDs"
