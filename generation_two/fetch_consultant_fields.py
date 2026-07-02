#!/usr/bin/env python3
"""Fetch broad consultant data-field catalogs from WorldQuant BRAIN.

The miner should later choose one dataset/category family to run. This crawler's
job is just to maintain a wide JSON field inventory.
"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import requests

from official_docs_miner import API_BASE, BASE_DIR, WQClient


OUT_DIR = BASE_DIR / "constants" / "consultant_fields"
RAW_DIR = OUT_DIR / "raw"
DATASET_DIR = OUT_DIR / "datasets"
COMBINED_PATH = OUT_DIR / "consultant_data_fields_combined.json"
SUMMARY_PATH = OUT_DIR / "consultant_data_fields_summary.json"
EXPRESSION_PATH = OUT_DIR / "consultant_expression_fields.json"
EXPRESSION_JSONL_PATH = OUT_DIR / "consultant_expression_fields.jsonl"


DEFAULT_SCOPES = {
    "USA": ["TOP3000", "TOP1000"],
    "GLB": ["TOP3000"],
    "EUR": ["TOP2500"],
    "ASI": ["MINVOL1M"],
    "CHN": ["TOP2000U"],
    "JPN": ["TOP1600"],
    "IND": ["TOP500"],
    "MEA": ["TOP600"],
}


def field_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row.get("id"),
        row.get("region"),
        row.get("delay"),
        row.get("universe"),
        (row.get("dataset") or {}).get("id") if isinstance(row.get("dataset"), dict) else row.get("dataset_id"),
    )


def normalize(row: dict[str, Any]) -> dict[str, Any]:
    dataset = row.get("dataset")
    category = row.get("category")
    subcategory = row.get("subcategory")
    return {
        "id": row.get("id"),
        "description": row.get("description"),
        "type": str(row.get("type") or "").upper(),
        "dataset": dataset,
        "dataset_id": dataset.get("id") if isinstance(dataset, dict) else row.get("dataset_id"),
        "dataset_name": dataset.get("name") if isinstance(dataset, dict) else row.get("dataset_name"),
        "category": category,
        "category_id": category.get("id") if isinstance(category, dict) else row.get("category_id"),
        "category_name": category.get("name") if isinstance(category, dict) else row.get("category_name"),
        "subcategory": subcategory,
        "subcategory_id": subcategory.get("id") if isinstance(subcategory, dict) else row.get("subcategory_id"),
        "subcategory_name": subcategory.get("name") if isinstance(subcategory, dict) else row.get("subcategory_name"),
        "region": row.get("region"),
        "delay": row.get("delay"),
        "universe": row.get("universe"),
        "coverage": row.get("coverage"),
        "dateCoverage": row.get("dateCoverage"),
        "userCount": row.get("userCount"),
        "alphaCount": row.get("alphaCount"),
        "themes": row.get("themes", []),
    }


def fetch_scope(
    client: WQClient,
    region: str,
    delay: int,
    universe: str,
    limit: int,
    dataset_id: str | None = None,
    category_id: str | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        params: dict[str, Any] = {
            "instrumentType": "EQUITY",
            "region": region,
            "delay": delay,
            "universe": universe,
            "limit": limit,
            "offset": offset,
        }
        if dataset_id:
            params["dataset.id"] = dataset_id
        if category_id:
            params["category.id"] = category_id

        try:
            response = client.sess.get(f"{API_BASE}/data-fields", params=params, timeout=60)
        except requests.RequestException as exc:
            print(f"network error {region} D{delay} {universe} offset={offset}: {str(exc)[:180]}; sleep 15s")
            time.sleep(15)
            continue
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            wait = float(retry_after) if retry_after else 60.0
            print(f"429 {region} D{delay} {universe}; sleep {wait:.0f}s")
            time.sleep(wait)
            continue
        if response.status_code != 200:
            raise RuntimeError(f"{region} D{delay} {universe} HTTP {response.status_code}: {response.text[:500]}")

        data = response.json()
        page = data.get("results")
        if page is None:
            raise RuntimeError(f"unexpected data-fields response: {str(data)[:500]}")
        rows.extend(page)
        total = data.get("count")
        print(f"{region} D{delay} {universe} offset={offset} page={len(page)} total={len(rows)} count={total}")
        if len(page) < limit or (isinstance(total, int) and len(rows) >= total):
            break
        offset += limit
    return rows


def fetch_datasets(client: WQClient, region: str, delay: int, universe: str, limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        params = {
            "instrumentType": "EQUITY",
            "region": region,
            "delay": delay,
            "universe": universe,
            "limit": limit,
            "offset": offset,
        }
        try:
            response = client.sess.get(f"{API_BASE}/data-sets", params=params, timeout=60)
        except requests.RequestException as exc:
            print(f"network error datasets {region} D{delay} {universe} offset={offset}: {str(exc)[:180]}; sleep 15s")
            time.sleep(15)
            continue
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            wait = float(retry_after) if retry_after else 60.0
            print(f"429 datasets {region} D{delay} {universe}; sleep {wait:.0f}s")
            time.sleep(wait)
            continue
        if response.status_code != 200:
            raise RuntimeError(f"datasets {region} D{delay} {universe} HTTP {response.status_code}: {response.text[:500]}")
        data = response.json()
        page = data.get("results")
        if page is None:
            raise RuntimeError(f"unexpected data-sets response: {str(data)[:500]}")
        rows.extend(page)
        total = data.get("count")
        print(f"datasets {region} D{delay} {universe} offset={offset} page={len(page)} total={len(rows)} count={total}")
        if len(page) < limit or (isinstance(total, int) and len(rows) >= total):
            break
        offset += limit
    return rows


def fetch_scope_by_dataset(client: WQClient, region: str, delay: int, universe: str, limit: int, skip_existing: bool = False) -> list[dict[str, Any]]:
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    datasets = fetch_datasets(client, region, delay, universe, limit)
    dataset_path = DATASET_DIR / f"datasets_{region}_D{delay}_{universe}.json"
    dataset_path.write_text(json.dumps(datasets, indent=2, ensure_ascii=False), encoding="utf-8")

    all_rows: list[dict[str, Any]] = []
    for idx, dataset in enumerate(datasets, 1):
        dataset_id = dataset.get("id")
        if not dataset_id:
            continue
        fields_count = dataset.get("fields")
        raw_name = f"data_fields_{region}_D{delay}_{universe}_{dataset_id}.json".replace("/", "_")
        raw_path = RAW_DIR / raw_name
        if skip_existing and raw_path.exists():
            try:
                cached = json.loads(raw_path.read_text(encoding="utf-8"))
                if isinstance(cached, list):
                    print(f"skip existing {idx}/{len(datasets)} {region} D{delay} {universe} {dataset_id} rows={len(cached)}")
                    all_rows.extend(cached)
                    continue
            except Exception:
                pass
        print(f"dataset {idx}/{len(datasets)} {region} D{delay} {universe} {dataset_id} fields={fields_count}")
        rows = fetch_scope(client, region, delay, universe, limit, dataset_id=str(dataset_id))
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
        all_rows.extend(rows)
    return all_rows


def load_existing_caches() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted((BASE_DIR / "constants").glob("data_fields_cache_*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"skip {path.name}: {exc}")
            continue
        if isinstance(data, list):
            print(f"loaded cache {path.name}: {len(data)}")
            rows.extend(data)
    return rows


def load_raw_shards() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not RAW_DIR.exists():
        return rows
    for path in sorted(RAW_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"skip raw shard {path.name}: {exc}")
            continue
        if isinstance(data, list):
            print(f"loaded raw shard {path.name}: {len(data)}")
            rows.extend(data)
        elif isinstance(data, dict):
            results = data.get("results")
            if isinstance(results, list):
                print(f"loaded raw shard {path.name}: {len(results)}")
                rows.extend(results)
    return rows


def write_outputs(rows: list[dict[str, Any]]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    clean_map: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in rows:
        item = normalize(row)
        clean_map[field_key(item)] = item

    clean = sorted(clean_map.values(), key=lambda x: (str(x.get("region")), str(x.get("delay")), str(x.get("universe")), str(x.get("id"))))
    expression = [row for row in clean if row.get("id") and row.get("type") in {"MATRIX", "VECTOR", "GROUP"}]

    by_category = Counter(str(row.get("category_name") or row.get("category_id") or "unknown") for row in clean)
    by_dataset = Counter(str(row.get("dataset_id") or "unknown") for row in clean)
    by_scope = Counter(f"{row.get('region')}_D{row.get('delay')}_{row.get('universe')}" for row in clean)
    dataset_detail: dict[str, dict[str, Any]] = defaultdict(lambda: {"count": 0, "name": None, "categories": Counter(), "regions": Counter()})
    for row in clean:
        ds = str(row.get("dataset_id") or "unknown")
        detail = dataset_detail[ds]
        detail["count"] += 1
        detail["name"] = detail["name"] or row.get("dataset_name")
        detail["categories"][str(row.get("category_name") or row.get("category_id") or "unknown")] += 1
        detail["regions"][str(row.get("region") or "unknown")] += 1

    summary = {
        "total_rows": len(rows),
        "unique_fields_by_scope_dataset": len(clean),
        "expression_candidates": len(expression),
        "by_category": dict(by_category.most_common()),
        "by_dataset_top100": dict(by_dataset.most_common(100)),
        "by_scope": dict(by_scope.most_common()),
        "datasets": {
            ds: {
                "count": detail["count"],
                "name": detail["name"],
                "categories": dict(detail["categories"].most_common()),
                "regions": dict(detail["regions"].most_common()),
            }
            for ds, detail in sorted(dataset_detail.items(), key=lambda item: item[0])
        },
    }

    with EXPRESSION_JSONL_PATH.open("w", encoding="utf-8") as handle:
        for row in expression:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    try:
        COMBINED_PATH.write_text(json.dumps(clean, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        print(f"warning: failed to write {COMBINED_PATH}: {exc}")
    try:
        EXPRESSION_PATH.write_text(json.dumps(expression, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        print(f"warning: failed to write {EXPRESSION_PATH}: {exc}")
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"saved combined={len(clean)} -> {COMBINED_PATH}")
    print(f"saved expression={len(expression)} -> {EXPRESSION_PATH}")
    print(f"saved expression jsonl={len(expression)} -> {EXPRESSION_JSONL_PATH}")
    print(f"saved summary -> {SUMMARY_PATH}")


def parse_scopes(text: str) -> list[tuple[str, int, str]]:
    scopes: list[tuple[str, int, str]] = []
    if text == "default":
        for region, universes in DEFAULT_SCOPES.items():
            for universe in universes:
                for delay in (0, 1):
                    scopes.append((region, delay, universe))
        return scopes
    for part in text.split(","):
        region, delay, universe = part.split(":")
        scopes.append((region.upper(), int(delay), universe.upper()))
    return scopes


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch broad consultant data-field JSON inventory")
    parser.add_argument("--credential", default=str(BASE_DIR / "credential_4.txt"))
    parser.add_argument("--scopes", default="default", help="default or comma list REGION:DELAY:UNIVERSE")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--dataset-id", help="Optional dataset.id filter for focused refresh")
    parser.add_argument("--category-id", help="Optional category.id filter")
    parser.add_argument("--by-dataset", action="store_true", help="Discover datasets first, then fetch fields per dataset to avoid broad 10000 caps")
    parser.add_argument("--datasets-only", action="store_true", help="Only fetch dataset catalogs for the selected scopes")
    parser.add_argument("--skip-existing", action="store_true", help="Reuse already fetched raw dataset shards")
    parser.add_argument("--from-existing-caches", action="store_true")
    parser.add_argument("--from-raw-shards", action="store_true", help="Merge constants/consultant_fields/raw/*.json without hitting the API")
    args = parser.parse_args()

    if args.from_existing_caches:
        write_outputs(load_existing_caches())
        return 0
    if args.from_raw_shards:
        write_outputs(load_raw_shards())
        return 0

    client = WQClient(args.credential)
    if not client.authenticate():
        raise SystemExit("authentication failed; update credential_4.txt COOKIE first")

    all_rows: list[dict[str, Any]] = []
    for region, delay, universe in parse_scopes(args.scopes):
        if args.datasets_only:
            datasets = fetch_datasets(client, region, delay, universe, args.limit)
            DATASET_DIR.mkdir(parents=True, exist_ok=True)
            (DATASET_DIR / f"datasets_{region}_D{delay}_{universe}.json").write_text(
                json.dumps(datasets, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            continue
        if args.by_dataset and not args.dataset_id and not args.category_id:
            rows = fetch_scope_by_dataset(client, region, delay, universe, args.limit, args.skip_existing)
        else:
            rows = fetch_scope(client, region, delay, universe, args.limit, args.dataset_id, args.category_id)
            raw_name = f"data_fields_{region}_D{delay}_{universe}.json"
            RAW_DIR.mkdir(parents=True, exist_ok=True)
            (RAW_DIR / raw_name).write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
        all_rows.extend(rows)
    if not args.datasets_only:
        write_outputs(all_rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
