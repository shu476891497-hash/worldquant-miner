#!/usr/bin/env python3
"""Consultant-grade WorldQuant BRAIN alpha miner.

This is a quota-aware, hash-deduplicated mining layer inspired by the
consultant documentation. It deliberately starts with small, meaningful probe
queues instead of broad random parameter sweeps.
"""

from __future__ import annotations

import argparse
import heapq
import hashlib
import json
import logging
import math
import os
import random
import re
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

import requests

from official_docs_miner import API_BASE, BASE_DIR, ParamVariant, ResultTracker, SimResult, WQClient


if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

RESULTS_PATH = BASE_DIR / "consultant_miner_results.json"
CACHE_PATH = BASE_DIR / "constants" / "consultant_simulation_cache.json"
SUMMARY_PATH = BASE_DIR / "consultant_tips_summary.md"
CONSULTANT_FIELDS_PATH = BASE_DIR / "constants" / "consultant_fields" / "consultant_expression_fields.json"
CONSULTANT_FIELDS_JSONL_PATH = BASE_DIR / "constants" / "consultant_fields" / "consultant_expression_fields.jsonl"
# Pool of abandoned templates/fields (already submitted or spent -> high self-correlation).
# Any generated variant whose expression contains a banned field or matches a banned
# expression is dropped before submission, so the miner never re-mines a spent idea.
ABANDONED_PATH = BASE_DIR / "constants" / "abandoned_templates.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "consultant_auto_miner.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("consultant")


@dataclass
class QuotaState:
    limit: int | None = None
    remaining: int | None = None
    reset_seconds: int | None = None

    def update(self, headers: requests.structures.CaseInsensitiveDict[str]) -> None:
        def as_int(name: str) -> int | None:
            value = headers.get(name)
            if value is None:
                return None
            try:
                return int(float(value))
            except ValueError:
                return None

        self.limit = as_int("x-ratelimit-limit") or self.limit
        self.remaining = as_int("x-ratelimit-remaining") or self.remaining
        self.reset_seconds = as_int("x-ratelimit-reset") or self.reset_seconds

    def describe(self) -> str:
        return f"limit={self.limit} remaining={self.remaining} reset={self.reset_seconds}s"


class SimulationCache:
    """Local full-config hash cache recommended by consultant docs."""

    def __init__(self, path: Path):
        self.path = path
        self.rows: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return
        if isinstance(data, dict):
            self.rows = {str(k): v for k, v in data.items() if isinstance(v, dict)}

    def save(self) -> None:
        self.path.parent.mkdir(exist_ok=True)
        self.path.write_text(json.dumps(self.rows, indent=2, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def hash_config(config: dict[str, Any]) -> str:
        raw = json.dumps(config, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, config: dict[str, Any]) -> dict[str, Any] | None:
        return self.rows.get(self.hash_config(config))

    def add(self, config: dict[str, Any], **meta: Any) -> str:
        key = self.hash_config(config)
        self.rows[key] = {
            "hash": key,
            "date_created": time.strftime("%Y-%m-%d %H:%M:%S"),
            "config": config,
            **meta,
        }
        self.save()
        return key


class ConsultantClient(WQClient):
    def __init__(self, credential_file: str, quota_reserve: int):
        super().__init__(credential_file)
        self.quota = QuotaState()
        self.quota_reserve = quota_reserve

    def build_simulation_config(
        self,
        expression: str,
        variant: ParamVariant,
        *,
        test_period: str,
        max_trade: str,
        visualization: bool = False,
    ) -> dict[str, Any]:
        return {
            "type": "REGULAR",
            "settings": {
                "instrumentType": "EQUITY",
                "region": "USA",
                "universe": variant.universe,
                "delay": variant.delay,
                "decay": variant.decay,
                "neutralization": variant.neutralization,
                "truncation": variant.truncation,
                "pasteurization": "ON",
                "unitHandling": "VERIFY",
                "nanHandling": "OFF",
                "language": "FASTEXPR",
                "visualization": visualization,
                "testPeriod": test_period,
                "maxTrade": max_trade,
            },
            "regular": expression,
        }

    def can_submit(self) -> bool:
        return self.quota.remaining is None or self.quota.remaining > self.quota_reserve

    def submit_config(self, config: dict[str, Any], retries: int = 5) -> str | None:
        if not self.can_submit():
            log.warning("quota reserve reached before submit: %s", self.quota.describe())
            return None

        for attempt in range(retries):
            try:
                response = self.sess.post(f"{API_BASE}/simulations", json=config, timeout=25)
            except requests.RequestException as exc:
                wait = 10 + 10 * attempt
                log.warning("submit network error: %s; sleep %ss", str(exc)[:160], wait)
                time.sleep(wait)
                continue

            self.quota.update(response.headers)
            if response.status_code == 201:
                log.info("submitted | quota %s", self.quota.describe())
                return response.headers.get("Location", "")

            if response.status_code == 401:
                log.warning("401 auth expired; reauth")
                if not self.authenticate():
                    return None
                continue

            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                if retry_after:
                    wait = max(10.0, float(retry_after))
                elif self.quota.reset_seconds:
                    wait = min(900.0, float(self.quota.reset_seconds))
                else:
                    wait = 20.0 * (attempt + 1) + random.uniform(0, 5)
                log.warning("429 rate limited | quota %s | sleep %.0fs", self.quota.describe(), wait)
                time.sleep(wait)
                continue

            log.error("submit failed: %s %s | quota %s", response.status_code, response.text[:240], self.quota.describe())
            return None

        return None

    def poll_progress(self, url: str, max_wait: int) -> dict[str, Any]:
        start = time.time()
        while time.time() - start < max_wait:
            try:
                response = self.sess.get(url, timeout=25)
            except requests.RequestException as exc:
                log.warning("poll network error: %s", str(exc)[:160])
                time.sleep(15)
                continue

            if response.status_code == 401:
                if not self.authenticate():
                    return {"error": "auth_expired"}
                time.sleep(3)
                continue

            if response.status_code != 200:
                time.sleep(10)
                continue

            retry_after = response.headers.get("Retry-After")
            if retry_after:
                time.sleep(max(1.0, float(retry_after)))
                continue

            data = response.json()
            if "alpha" in data or data.get("status") == "ERROR":
                return data
            time.sleep(8)

        return {"error": "timeout"}

    def poll_batch_progress(self, urls: Iterable[str], max_wait: int) -> dict[str, dict[str, Any]]:
        """Poll a batch without letting one slow simulation block the rest."""
        remaining = set(urls)
        results: dict[str, dict[str, Any]] = {}
        next_check = {url: 0.0 for url in remaining}
        start = time.time()

        while remaining and time.time() - start < max_wait:
            now = time.time()
            touched = False
            for url in list(remaining):
                if now < next_check.get(url, 0.0):
                    continue
                touched = True
                try:
                    response = self.sess.get(url, timeout=25)
                except requests.RequestException as exc:
                    log.warning("batch poll network error: %s", str(exc)[:160])
                    next_check[url] = time.time() + 15
                    continue

                if response.status_code == 401:
                    if not self.authenticate():
                        results[url] = {"error": "auth_expired"}
                        remaining.remove(url)
                    else:
                        next_check[url] = time.time() + 3
                    continue

                if response.status_code != 200:
                    next_check[url] = time.time() + 10
                    continue

                retry_after = response.headers.get("Retry-After")
                if retry_after:
                    next_check[url] = time.time() + max(1.0, float(retry_after))
                    continue

                data = response.json()
                if "alpha" in data or data.get("status") == "ERROR":
                    results[url] = data
                    remaining.remove(url)
                else:
                    next_check[url] = time.time() + 8

            if remaining:
                if touched:
                    sleep_for = 2.0
                else:
                    sleep_for = max(1.0, min(next_check.values()) - time.time())
                time.sleep(min(10.0, sleep_for))

        for url in remaining:
            results[url] = {"error": "timeout"}
        return results

    def fetch_alpha(self, alpha_id: str) -> dict[str, Any]:
        response = self.sess.get(f"{API_BASE}/alphas/{alpha_id}", timeout=25)
        if response.status_code != 200:
            return {"error": f"alpha_fetch_{response.status_code}", "text": response.text[:240]}
        return response.json()

    def fetch_recordsets(self, alpha_id: str, names: Iterable[str]) -> dict[str, Any]:
        output: dict[str, Any] = {}
        for name in names:
            try:
                response = self.sess.get(f"{API_BASE}/alphas/{alpha_id}/recordsets/{name}", timeout=25)
            except requests.RequestException as exc:
                output[name] = {"error": str(exc)[:160]}
                continue
            if response.status_code == 200:
                output[name] = response.json()
            else:
                output[name] = {"error": f"http_{response.status_code}", "text": response.text[:160]}
        return output

    def fetch_self(self) -> dict[str, Any]:
        response = self.sess.get(f"{API_BASE}/users/self", timeout=25)
        if response.status_code != 200:
            return {"error": f"self_{response.status_code}", "text": response.text[:240]}
        return response.json()

    def fetch_diversity(self, grouping: str = "region,delay,dataCategory") -> dict[str, Any]:
        user = self.fetch_self()
        user_id = user.get("id") or user.get("userId")
        if not user_id:
            return {"error": "missing_user_id", "self": user}
        response = self.sess.get(f"{API_BASE}/users/{user_id}/activities/diversity", params={"grouping": grouping}, timeout=30)
        if response.status_code != 200:
            return {"error": f"diversity_{response.status_code}", "text": response.text[:300]}
        return response.json()


def normalize_field_type(raw: str | None) -> str:
    text = str(raw or "").lower()
    if "vector" in text:
        return "VECTOR"
    return "MATRIX"


def normalize_field_row(row: dict[str, Any], dataset_category: str) -> dict[str, Any] | None:
    if not isinstance(row, dict):
        return None
    dataset = row.get("dataset") or {}
    dataset_id = row.get("dataset_id") or (dataset.get("id") if isinstance(dataset, dict) else dataset)
    dataset_name = row.get("dataset_name") or (dataset.get("name") if isinstance(dataset, dict) else "")
    source_category = row.get("category_name") or row.get("category") or dataset_category
    field_id = row.get("id")
    if not field_id:
        return None
    return {
        "id": field_id,
        "description": row.get("description") or "",
        "type": normalize_field_type(row.get("type")),
        "coverage": row.get("coverage"),
        "dateCoverage": row.get("dateCoverage"),
        "alphaCount": row.get("alphaCount"),
        "userCount": row.get("userCount"),
        "region": row.get("region"),
        "delay": row.get("delay"),
        "universe": row.get("universe"),
        "dataset": dataset_id,
        "datasetName": dataset_name,
        "sourceCategory": source_category,
        "category": dataset_category,
    }


def iter_field_rows(path: Path, dataset_category: str) -> Iterable[dict[str, Any]]:
    if not path.exists():
        return
    if path.suffix == ".jsonl":
        with path.open("r", encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, 1):
                text = line.strip()
                if not text:
                    continue
                try:
                    row = json.loads(text)
                except Exception as exc:
                    log.warning("failed to load %s:%d: %s", path, line_no, exc)
                    continue
                normalized = normalize_field_row(row, dataset_category)
                if normalized:
                    yield normalized
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("failed to load %s: %s", path, exc)
        return
    rows = data if isinstance(data, list) else data.get("results", []) if isinstance(data, dict) else []
    for row in rows:
        normalized = normalize_field_row(row, dataset_category)
        if normalized:
            yield normalized


def load_field_rows(path: Path, dataset_category: str) -> list[dict[str, Any]]:
    return list(iter_field_rows(path, dataset_category))


def text_matches(value: Any, wanted: str | None) -> bool:
    if not wanted:
        return True
    return str(value or "").lower() == wanted.lower()


def filter_field_rows(
    rows: list[dict[str, Any]],
    dataset_id: str | None = None,
    category_name: str | None = None,
    field_region: str | None = None,
    field_delay: int | None = None,
    field_universe: str | None = None,
    matrix_only: bool = False,
) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if field_row_matches(
            row,
            dataset_id=dataset_id,
            category_name=category_name,
            field_region=field_region,
            field_delay=field_delay,
            field_universe=field_universe,
            matrix_only=matrix_only,
        )
    ]


def field_row_matches(
    row: dict[str, Any],
    dataset_id: str | None = None,
    category_name: str | None = None,
    field_region: str | None = None,
    field_delay: int | None = None,
    field_universe: str | None = None,
    matrix_only: bool = False,
) -> bool:
    if dataset_id and not text_matches(row.get("dataset"), dataset_id):
        return False
    if category_name and not text_matches(row.get("sourceCategory"), category_name):
        return False
    if field_region and not text_matches(row.get("region"), field_region):
        return False
    if field_delay is not None:
        try:
            if int(row.get("delay")) != int(field_delay):
                return False
        except (TypeError, ValueError):
            return False
    if field_universe and not text_matches(row.get("universe"), field_universe):
        return False
    if matrix_only and row.get("type") != "MATRIX":
        return False
    return True


BAD_FIELD_TOKENS = {
    "date",
    "timestamp",
    "time",
    "isin",
    "cusip",
    "sedol",
    "symbol",
    "ticker",
    "name",
    "identifier",
}

GOOD_DESC_TOKENS = {
    "earning",
    "estimate",
    "revision",
    "surprise",
    "revenue",
    "cash",
    "margin",
    "profit",
    "quality",
    "debt",
    "liabil",
    "inventory",
    "receivable",
    "option",
    "volatility",
    "implied",
    "short",
    "sentiment",
    "analyst",
    "growth",
    "flow",
}


def field_score(row: dict[str, Any]) -> float:
    field_id = str(row.get("id") or "").lower()
    desc = str(row.get("description") or "").lower()
    source_category = str(row.get("sourceCategory") or row.get("category") or "").lower()
    if any(token in field_id or token in desc for token in BAD_FIELD_TOKENS):
        return -1e9

    coverage = row.get("coverage")
    date_coverage = row.get("dateCoverage")
    alpha_count = row.get("alphaCount")
    user_count = row.get("userCount")

    score = 0.0
    if isinstance(coverage, (int, float)):
        score += 2.0 * min(float(coverage), 1.0)
    else:
        score += 0.8
    if isinstance(date_coverage, (int, float)):
        score += 2.0 * min(float(date_coverage), 1.0)
    else:
        score += 0.6
    if isinstance(alpha_count, (int, float)):
        alpha_value = max(float(alpha_count), 1.0)
        score += 2.0 / math.sqrt(alpha_value)
        if alpha_value > 100:
            score -= min(1.5, math.log10(alpha_value / 100.0 + 1.0))
    else:
        score += 0.2
    if isinstance(user_count, (int, float)):
        user_value = max(float(user_count), 1.0)
        score += 0.7 / math.sqrt(user_value)
        if user_value > 75:
            score -= min(0.8, math.log10(user_value / 75.0 + 1.0))
    if any(token in desc or token in field_id for token in GOOD_DESC_TOKENS):
        score += 1.0
    if "earn" in source_category:
        score += 0.7
    return score


def is_expression_safe_field(row: dict[str, Any], allow_raw_earnings_fields: bool = False) -> bool:
    """Keep live queues on field ids that are known to be accepted by Fast Expression.

    Some cached earnings4 rows are Data-page display ids, while the editor autocomplete
    and official examples use ern4_* expression ids. Raw earnings ids can still be
    explored explicitly, but they are too risky as the default live queue.
    """
    fid = str(row.get("id") or "")
    category = str(row.get("category") or "")
    if category == "earnings" and not allow_raw_earnings_fields:
        return fid.startswith("ern4_")
    return bool(re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", fid))


def select_fields(rows: list[dict[str, Any]], max_fields: int, allow_raw_earnings_fields: bool = False) -> list[dict[str, Any]]:
    rows = [row for row in rows if is_expression_safe_field(row, allow_raw_earnings_fields)]
    scored = [(field_score(row), row) for row in rows]
    scored = [(score, row) for score, row in scored if score > 0]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    chosen: list[dict[str, Any]] = []
    seen_desc_roots: set[str] = set()
    for _score, row in scored:
        desc = str(row.get("description") or "").lower()
        root = " ".join(desc.split()[:6])
        if root and root in seen_desc_roots:
            continue
        seen_desc_roots.add(root)
        chosen.append(row)
        if len(chosen) >= max_fields:
            break
    return chosen


def load_ranked_consultant_rows(
    max_fields: int,
    allow_raw_earnings_fields: bool = False,
    dataset_id: str | None = None,
    category_name: str | None = None,
    field_region: str | None = None,
    field_delay: int | None = None,
    field_universe: str | None = None,
    matrix_only: bool = False,
) -> list[dict[str, Any]]:
    source = CONSULTANT_FIELDS_JSONL_PATH if CONSULTANT_FIELDS_JSONL_PATH.exists() else CONSULTANT_FIELDS_PATH
    max_candidates = max(max_fields * 60, 1000)
    heap: list[tuple[float, int, dict[str, Any]]] = []
    seen_ids: set[tuple[Any, ...]] = set()
    scanned = 0
    for idx, row in enumerate(iter_field_rows(source, "consultant")):
        scanned += 1
        if not field_row_matches(
            row,
            dataset_id=dataset_id,
            category_name=category_name,
            field_region=field_region,
            field_delay=field_delay,
            field_universe=field_universe,
            matrix_only=matrix_only,
        ):
            continue
        if not is_expression_safe_field(row, allow_raw_earnings_fields):
            continue
        key = (row.get("id"), row.get("dataset"), row.get("region"), row.get("delay"), row.get("universe"))
        if key in seen_ids:
            continue
        seen_ids.add(key)
        score = field_score(row)
        if score <= 0:
            continue
        entry = (score, idx, row)
        if len(heap) < max_candidates:
            heapq.heappush(heap, entry)
        elif entry > heap[0]:
            heapq.heapreplace(heap, entry)
    rows = [row for _score, _idx, row in sorted(heap, reverse=True)]
    log.info("consultant field stream source=%s scanned=%d matched_candidates=%d", source.name, scanned, len(rows))
    return rows


def field_value(row: dict[str, Any], backfill_days: int) -> str:
    fid = row["id"]
    if row.get("type") == "VECTOR":
        return f"ts_backfill(vec_avg({fid}), {backfill_days})"
    return f"ts_backfill({fid}, {backfill_days})"


def pv(expr: str, decay: int, neutralization: str, universe: str, desc: str, truncation: float = 0.08, delay: int = 1) -> ParamVariant:
    return ParamVariant(expr, decay, neutralization, truncation, universe, delay, desc)


def add_variant(target: list[tuple[str, ParamVariant]], name: str, variant: ParamVariant) -> None:
    target.append((name, variant))


def consultant_seed_variants() -> list[tuple[str, ParamVariant]]:
    """Hand-picked consultant seeds with clear economic rationale."""
    variants: list[tuple[str, ParamVariant]] = []
    add_variant(
        variants,
        "consultant_ern4_tip_hump_90div",
        pv("hump(ts_zscore(ts_backfill(vec_avg(ern4_90div), 252), 5), hump=0.0005)", 0, "SUBINDUSTRY", "TOP3000", "official_tip_hump_earnings4", 0.08),
    )
    add_variant(
        variants,
        "consultant_ern4_iv_earnings_premium",
        pv("hump(group_rank(ts_backfill(vec_avg(ern4_30div), 252) - ts_backfill(vec_avg(ern4_30dexerniv), 252), subindustry), hump=0.001)", 0, "SUBINDUSTRY", "TOP3000", "iv_minus_ex_earnings_iv", 0.08),
    )
    add_variant(
        variants,
        "consultant_ern4_forecast_realized_gap",
        pv("hump(group_rank(ts_backfill(vec_avg(ern4_fcsterneffct), 5) - ts_backfill(vec_avg(ern4_erneffct1), 5), subindustry), hump=0.001)", 0, "SUBINDUSTRY", "TOP3000", "forecast_earnings_effect_minus_realized", 0.08),
    )
    add_variant(
        variants,
        "consultant_ern4_fairvol_gap",
        pv("hump(group_rank(ts_backfill(vec_avg(ern4_fairxieevol90d), 252) - ts_backfill(vec_avg(ern4_90div), 252), subindustry), hump=0.001)", 5, "INDUSTRY", "TOP3000", "fair_ex_earnings_vol_minus_iv", 0.08),
    )
    add_variant(
        variants,
        "consultant_model16_earnings_certainty",
        pv("group_rank(ts_zscore(ts_backfill(earnings_certainty_rank_derivative, 20), 63), subindustry)", 3, "SUBINDUSTRY", "TOP3000", "model_earnings_certainty_quality", 0.08),
    )
    return variants


def generate_field_probe_variants(
    rows: list[dict[str, Any]],
    stage: str,
    max_fields: int,
    allow_raw_earnings_fields: bool = False,
) -> list[tuple[str, ParamVariant]]:
    selected = select_fields(rows, max_fields, allow_raw_earnings_fields)
    variants: list[tuple[str, ParamVariant]] = []
    for row in selected:
        fid = str(row["id"])
        category = str(row.get("category") or "field")
        source_category = str(row.get("sourceCategory") or category or "").lower()
        backfill = 252 if "earn" in source_category else 63 if "fund" in source_category else 20
        x = field_value(row, backfill)
        dataset_tag = str(row.get("dataset") or category or "field")
        tag = f"{dataset_tag}_{fid}".replace("-", "_").replace(".", "_")[:80]

        add_variant(
            variants,
            f"{tag}_level",
            pv(f"group_rank({x}, subindustry)", 0, "SUBINDUSTRY", "TOP3000", f"probe_level_{fid}", 0.08),
        )
        add_variant(
            variants,
            f"{tag}_hump_z",
            pv(f"hump(ts_zscore({x}, 20), hump=0.001)", 0, "SUBINDUSTRY", "TOP3000", f"probe_hump_z20_{fid}", 0.08),
        )

        if stage in {"refine", "exploit"}:
            delta_window = 63 if backfill >= 63 else 10
            add_variant(
                variants,
                f"{tag}_delta",
                pv(f"group_rank(ts_delta({x}, {delta_window}), industry)", 3, "INDUSTRY", "TOP3000", f"refine_delta_{delta_window}_{fid}", 0.08),
            )
            add_variant(
                variants,
                f"{tag}_smooth_rank",
                pv(f"group_rank(ts_mean({x}, 20), subindustry)", 5, "SUBINDUSTRY", "TOP3000", f"refine_smooth20_{fid}", 0.08),
            )
        if stage == "exploit":
            add_variant(
                variants,
                f"{tag}_top2000",
                pv(f"group_rank({x}, subindustry)", 0, "SUBINDUSTRY", "TOP2000", f"exploit_universe_top2000_{fid}", 0.08),
            )
            add_variant(
                variants,
                f"{tag}_sector",
                pv(f"group_rank({x}, sector)", 3, "SECTOR", "TOP3000", f"exploit_sector_{fid}", 0.06),
            )
    return variants


def _load_abandoned_pool() -> tuple[list[str], set[str]]:
    """Return (banned_field_substrings, banned_normalized_expressions)."""
    if not ABANDONED_PATH.exists():
        return [], set()
    try:
        data = json.loads(ABANDONED_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("could not read abandoned pool %s: %s", ABANDONED_PATH, exc)
        return [], set()
    fields = [str(f).replace(" ", "") for f in data.get("banned_fields", []) if str(f).strip()]
    exprs = {str(e).replace(" ", "") for e in data.get("banned_expressions", []) if str(e).strip()}
    return fields, exprs


def filter_abandoned(variants: list[tuple[str, ParamVariant]]) -> list[tuple[str, ParamVariant]]:
    banned_fields, banned_exprs = _load_abandoned_pool()
    if not banned_fields and not banned_exprs:
        return variants
    kept: list[tuple[str, ParamVariant]] = []
    dropped = 0
    for name, variant in variants:
        norm = variant.expression.replace(" ", "")
        if norm in banned_exprs or any(bf in norm for bf in banned_fields):
            dropped += 1
            continue
        kept.append((name, variant))
    if dropped:
        log.info("abandoned pool: dropped %d spent variant(s)", dropped)
    return kept


def dedup_variants(variants: list[tuple[str, ParamVariant]]) -> list[tuple[str, ParamVariant]]:
    seen: set[tuple[Any, ...]] = set()
    unique: list[tuple[str, ParamVariant]] = []
    for name, variant in variants:
        key = (
            variant.expression.strip(),
            variant.decay,
            variant.neutralization,
            variant.truncation,
            variant.universe,
            variant.delay,
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append((name, variant))
    return unique


GROUPING_FIELDS = {"country", "industry", "subindustry", "currency", "market", "sector", "exchange"}
IGNORED_POWER_POOL_OPERATORS = {"ts_backfill", "group_backfill"}
OPERATOR_PATTERN = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")
IDENT_PATTERN = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")


def expression_operators(expression: str) -> list[str]:
    ops = [match.group(1) for match in OPERATOR_PATTERN.finditer(expression)]
    return [op for op in ops if op not in IGNORED_POWER_POOL_OPERATORS]


def expression_fields(expression: str) -> list[str]:
    operators = set(expression_operators(expression)) | IGNORED_POWER_POOL_OPERATORS
    keywords = {
        "and",
        "or",
        "not",
        "if",
        "else",
        "true",
        "false",
        "nan",
        "inf",
        "hump",
        "range",
        "std",
    }
    fields: list[str] = []
    for token in IDENT_PATTERN.findall(expression):
        lower = token.lower()
        if lower in keywords or lower in GROUPING_FIELDS or token in operators:
            continue
        if token.isupper():
            continue
        if re.fullmatch(r"\d+", token):
            continue
        # Keep likely data fields and common PV fields; drop parameter words.
        fields.append(token)
    return sorted(set(fields))


def power_pool_shape(expression: str, sharpe: float | None = None) -> dict[str, Any]:
    ops = expression_operators(expression)
    fields = expression_fields(expression)
    unique_ops = sorted(set(ops))
    shape_pass = len(ops) <= 8 and len(fields) <= 3 and (sharpe is None or sharpe >= 1.0)
    return {
        "operatorCount": len(ops),
        "uniqueOperators": unique_ops,
        "fieldCount": len(fields),
        "fields": fields,
        "shapePass": shape_pass,
    }


def consultant_threshold_note(variant: ParamVariant, row: SimResult) -> str:
    if variant.delay == 0:
        core = row.fitness > 1.5 and row.sharpe > 2.69
        target = "D0 consultant core: Sharpe>2.69 Fitness>1.5"
    else:
        core = row.fitness > 1.0 and row.sharpe > 1.58
        target = "D1 consultant core: Sharpe>1.58 Fitness>1.0"
    turnover_ok = 0.01 < row.turnover < 0.70
    return f"{target}; core={'PASS' if core else 'MISS'}; turnover_1_70={'PASS' if turnover_ok else 'MISS'}"


def build_queue(
    stage: str,
    max_fields: int,
    include_official: bool,
    field_source: str,
    allow_raw_earnings_fields: bool = False,
    dataset_id: str | None = None,
    category_name: str | None = None,
    field_region: str | None = None,
    field_delay: int | None = None,
    field_universe: str | None = None,
    matrix_only: bool = False,
) -> list[tuple[str, ParamVariant]]:
    rows: list[dict[str, Any]] = []
    if field_source in {"all", "earnings"}:
        rows.extend(load_field_rows(BASE_DIR / "constants" / "earnings4_fields.json", "earnings"))
    if field_source in {"all", "general"}:
        rows.extend(load_field_rows(BASE_DIR / "constants" / "data_fields_cache_USA_1_TOP3000.json", "general"))
    if field_source in {"all", "consultant"}:
        rows.extend(
            load_ranked_consultant_rows(
                max_fields=max_fields,
                allow_raw_earnings_fields=allow_raw_earnings_fields,
                dataset_id=dataset_id,
                category_name=category_name,
                field_region=field_region,
                field_delay=field_delay,
                field_universe=field_universe,
                matrix_only=matrix_only,
            )
        )
    rows = filter_field_rows(
        rows,
        dataset_id=dataset_id,
        category_name=category_name,
        field_region=field_region,
        field_delay=field_delay,
        field_universe=field_universe,
        matrix_only=matrix_only,
    )

    variants = consultant_seed_variants()
    variants.extend(generate_field_probe_variants(rows, stage, max_fields, allow_raw_earnings_fields))

    if include_official:
        try:
            from run_ern4_official_docs_miner import make_all_variants

            variants.extend([(f"ern4_official_{name}", variant) for name, variant in make_all_variants()[:100]])
        except Exception as exc:
            log.warning("could not load ern4 official variants: %s", exc)

    return filter_abandoned(dedup_variants(variants))


def result_from_alpha(name: str, variant: ParamVariant, desc: str, alpha_id: str, alpha: dict[str, Any]) -> SimResult:
    is_data = alpha.get("is", {}) if isinstance(alpha, dict) else {}
    checks = is_data.get("checks", []) if isinstance(is_data, dict) else []
    failed = [check for check in checks if isinstance(check, dict) and check.get("result") == "FAIL"]
    note = ""
    if failed:
        note = " fail=" + json.dumps(
            [{"name": c.get("name"), "value": c.get("value"), "limit": c.get("limit")} for c in failed[:4]],
            ensure_ascii=False,
        )

    temp = SimResult(
        name=name,
        expression=variant.expression,
        variant_desc=desc + note,
        sharpe=float(is_data.get("sharpe") or 0),
        fitness=float(is_data.get("fitness") or 0),
        turnover=float(is_data.get("turnover") or 0),
        returns=float(is_data.get("returns") or 0),
        drawdown=float(is_data.get("drawdown") or 0),
        margin=float(is_data.get("margin") or 0),
        long_count=int(is_data.get("longCount") or 0),
        short_count=int(is_data.get("shortCount") or 0),
        passed_checks=not failed,
        alpha_id=alpha_id,
    )
    pp = power_pool_shape(variant.expression, temp.sharpe)
    temp.variant_desc += (
        f" | {consultant_threshold_note(variant, temp)}"
        f" | powerPoolShape ops={pp['operatorCount']} fields={pp['fieldCount']} shapePass={pp['shapePass']}"
    )
    return temp


def print_alpha_diagnostics(client: ConsultantClient, alpha_id: str, fetch_recordsets: bool) -> int:
    alpha = client.fetch_alpha(alpha_id)
    if alpha.get("error"):
        print(json.dumps(alpha, indent=2, ensure_ascii=False))
        return 1
    is_data = alpha.get("is", {})
    checks = is_data.get("checks", []) if isinstance(is_data, dict) else []
    print(f"alpha={alpha_id}")
    print(
        "IS:",
        {
            key: is_data.get(key)
            for key in ["sharpe", "fitness", "turnover", "returns", "drawdown", "margin", "longCount", "shortCount"]
            if key in is_data
        },
    )
    failed = [check for check in checks if isinstance(check, dict) and check.get("result") == "FAIL"]
    if failed:
        print("FAILED CHECKS:")
        for check in failed:
            print(" ", {key: check.get(key) for key in ["name", "value", "limit", "result"]})
    else:
        print("FAILED CHECKS: none")
    expression = ""
    regular = alpha.get("regular")
    if isinstance(regular, dict):
        expression = str(regular.get("code") or regular.get("expression") or "")
    elif isinstance(regular, str):
        expression = regular
    if expression:
        print("POWER POOL SHAPE:", json.dumps(power_pool_shape(expression, is_data.get("sharpe")), ensure_ascii=False))
    if fetch_recordsets:
        recordsets = client.fetch_recordsets(alpha_id, ["pnl", "pnl-by-capitalization", "sharpe-by-capitalization", "average-size-by-capitalization"])
        path = BASE_DIR / "logs" / f"consultant_recordsets_{alpha_id}.json"
        path.write_text(json.dumps(recordsets, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"recordsets saved: {path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Consultant-grade quota-aware WorldQuant alpha miner")
    parser.add_argument("--credential", default=str(BASE_DIR / "credential_4.txt"))
    parser.add_argument("--stage", choices=["probe", "refine", "exploit"], default="probe")
    parser.add_argument("--max-fields", type=int, default=20)
    parser.add_argument("--field-source", choices=["all", "earnings", "general", "consultant"], default="all")
    parser.add_argument("--dataset-id", help="Only use fields from one dataset id, e.g. earnings4 or model77")
    parser.add_argument("--category-name", help="Only use consultant fields from one category name, e.g. Earnings or Fundamental")
    parser.add_argument("--field-region", help="Only use consultant fields from one region, e.g. USA")
    parser.add_argument("--field-delay", type=int, help="Only use consultant fields from one delay")
    parser.add_argument("--field-universe", help="Only use consultant fields from one universe, e.g. TOP3000")
    parser.add_argument("--matrix-only", action="store_true", help="Restrict selected fields to MATRIX fields; useful for Python-alpha compatible research")
    parser.add_argument("--max-variants", type=int, default=50)
    parser.add_argument("--batch-size", type=int, default=3)
    parser.add_argument("--delay", type=float, default=8.0)
    parser.add_argument("--max-poll", type=int, default=720)
    parser.add_argument("--quota-reserve", type=int, default=1000)
    parser.add_argument("--test-period", default="P5Y0M0D")
    parser.add_argument("--max-trade", choices=["ON", "OFF"], default="OFF")
    parser.add_argument("--include-official", action="store_true")
    parser.add_argument(
        "--allow-raw-earnings-fields",
        action="store_true",
        help="Also try non-ern4 earnings4 display ids from the data-page cache. Default keeps live queues on ern4_* ids.",
    )
    parser.add_argument("--fetch-recordsets", action="store_true", help="Fetch cap/PnL recordsets for passing or high-fitness alphas")
    parser.add_argument("--inspect-alpha", help="Fetch one alpha's metrics/checks and optional recordsets, then exit")
    parser.add_argument("--diversity", action="store_true", help="Fetch consultant diversity endpoint, save JSON, then exit")
    parser.add_argument("--diversity-grouping", default="region,delay,dataCategory")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--summary-only", action="store_true")
    args = parser.parse_args()

    if args.summary_only:
        print(SUMMARY_PATH.read_text(encoding="utf-8") if SUMMARY_PATH.exists() else "summary missing")
        return 0

    tracker = ResultTracker(RESULTS_PATH)
    cache = SimulationCache(CACHE_PATH)
    client = ConsultantClient(args.credential, args.quota_reserve)

    if args.inspect_alpha or args.diversity:
        if not client.authenticate():
            log.error("authentication failed")
            return 2
        if args.inspect_alpha:
            return print_alpha_diagnostics(client, args.inspect_alpha, args.fetch_recordsets)
        if args.diversity:
            data = client.fetch_diversity(args.diversity_grouping)
            path = BASE_DIR / "logs" / "consultant_diversity.json"
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            print(json.dumps(data, indent=2, ensure_ascii=False)[:4000])
            print(f"diversity saved: {path}")
            return 0

    queue = build_queue(
        args.stage,
        args.max_fields,
        args.include_official,
        args.field_source,
        args.allow_raw_earnings_fields,
        dataset_id=args.dataset_id,
        category_name=args.category_name,
        field_region=args.field_region,
        field_delay=args.field_delay,
        field_universe=args.field_universe,
        matrix_only=args.matrix_only,
    )
    prepared: list[tuple[str, ParamVariant, dict[str, Any], str]] = []

    for name, variant in queue:
        config = client.build_simulation_config(
            variant.expression,
            variant,
            test_period=args.test_period,
            max_trade=args.max_trade,
        )
        cached = cache.get(config)
        if cached:
            continue
        prepared.append((name, variant, config, SimulationCache.hash_config(config)))
        if len(prepared) >= args.max_variants:
            break

    log.info("stage=%s generated=%d queued_after_hash=%d max_trade=%s", args.stage, len(queue), len(prepared), args.max_trade)

    if args.dry_run:
        for idx, (name, variant, config, digest) in enumerate(prepared[: min(30, len(prepared))], 1):
            print(f"{idx:03d} {name} hash={digest[:10]} d={variant.decay} n={variant.neutralization} u={variant.universe}")
            print(f"    {variant.expression}")
        return 0

    if not client.authenticate():
        log.error("authentication failed")
        return 2

    total_tested = 0
    total_passed = 0
    for start in range(0, len(prepared), args.batch_size):
        batch = prepared[start : start + args.batch_size]
        pending: list[tuple[str, ParamVariant, dict[str, Any], str, str]] = []
        log.info("batch %d/%d size=%d", start // args.batch_size + 1, math.ceil(len(prepared) / args.batch_size), len(batch))

        for name, variant, config, digest in batch:
            if not client.can_submit():
                log.warning("quota reserve hit; stopping run: %s", client.quota.describe())
                tracker.print_summary()
                return 0
            log.info(" -> %s | %s", name, variant.mutation_desc)
            progress_url = client.submit_config(config)
            if not progress_url:
                tracker.add(SimResult(name=name, expression=variant.expression, variant_desc=variant.mutation_desc, error="submit_failed"))
                cache.add(config, status="submit_failed", name=name)
            else:
                cache.add(config, status="submitted", name=name, progress_url=progress_url)
                pending.append((name, variant, config, digest, progress_url))
            time.sleep(args.delay)

        batch_results = client.poll_batch_progress([progress_url for *_rest, progress_url in pending], args.max_poll)

        for name, variant, config, digest, progress_url in pending:
            desc = (
                f"d={variant.decay},n={variant.neutralization},u={variant.universe},"
                f"tr={variant.truncation},maxTrade={args.max_trade},{variant.mutation_desc}"
            )
            data = batch_results.get(progress_url, {"error": "missing_batch_result"})
            total_tested += 1
            if data.get("status") == "ERROR" or data.get("error"):
                err = data.get("message") or data.get("error") or "simulation_error"
                tracker.add(SimResult(name=name, expression=variant.expression, variant_desc=desc, error=str(err)[:240]))
                cache.add(config, status="error", name=name, error=str(err)[:240])
                log.warning(" xx %s error: %s", name, str(err)[:160])
                continue

            raw_alpha = data.get("alpha", "")
            alpha_id = str(raw_alpha[0] if isinstance(raw_alpha, list) else raw_alpha)
            alpha = client.fetch_alpha(alpha_id)
            if alpha.get("error"):
                tracker.add(SimResult(name=name, expression=variant.expression, variant_desc=desc, alpha_id=alpha_id, error=alpha["error"]))
                cache.add(config, status="alpha_fetch_error", name=name, alpha_id=alpha_id, error=alpha["error"])
                continue

            row = result_from_alpha(name, variant, desc, alpha_id, alpha)
            tracker.add(row)
            cache.add(config, status="done", name=name, alpha_id=alpha_id, result=asdict(row))
            if row.passed_checks:
                total_passed += 1

            if args.fetch_recordsets and (row.passed_checks or row.fitness >= 1.0):
                recordsets = client.fetch_recordsets(alpha_id, ["pnl", "pnl-by-capitalization", "sharpe-by-capitalization"])
                record_path = BASE_DIR / "logs" / f"consultant_recordsets_{alpha_id}.json"
                record_path.write_text(json.dumps(recordsets, indent=2, ensure_ascii=False), encoding="utf-8")

            status = "PASS" if row.passed_checks else "FAIL"
            log.info(
                " %s %s | S=%.3f F=%.3f TO=%.1f%% R=%.2f%% DD=%.1f%% id=%s",
                status,
                name,
                row.sharpe,
                row.fitness,
                row.turnover * 100,
                row.returns * 100,
                row.drawdown * 100,
                row.alpha_id,
            )

    log.info("final tested=%d passed=%d quota=%s", total_tested, total_passed, client.quota.describe())
    tracker.print_summary()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
