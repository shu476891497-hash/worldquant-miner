#!/usr/bin/env python3
"""Fetch and normalize earnings4 data fields from BRAIN."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from official_docs_miner import API_BASE, BASE_DIR, WQClient


OUT_RAW = BASE_DIR / "constants" / "earnings4_fields_raw.json"
OUT_CLEAN = BASE_DIR / "constants" / "earnings4_fields.json"
OUT_EXPR = BASE_DIR / "constants" / "earnings4_expression_fields.json"


def normalize_field(row: dict[str, Any]) -> dict[str, Any]:
    dataset = row.get("dataset")
    category = row.get("category")
    subcategory = row.get("subcategory")
    return {
        "id": row.get("id"),
        "description": row.get("description"),
        "type": str(row.get("type") or "").upper(),
        "dataset": dataset,
        "dataset_id": dataset.get("id") if isinstance(dataset, dict) else None,
        "dataset_name": dataset.get("name") if isinstance(dataset, dict) else None,
        "category": category,
        "category_id": category.get("id") if isinstance(category, dict) else None,
        "category_name": category.get("name") if isinstance(category, dict) else None,
        "subcategory": subcategory,
        "subcategory_id": subcategory.get("id") if isinstance(subcategory, dict) else None,
        "subcategory_name": subcategory.get("name") if isinstance(subcategory, dict) else None,
        "region": row.get("region"),
        "delay": row.get("delay"),
        "universe": row.get("universe"),
        "coverage": row.get("coverage"),
        "dateCoverage": row.get("dateCoverage"),
        "userCount": row.get("userCount"),
        "alphaCount": row.get("alphaCount"),
        "alphas": row.get("alphas"),
        "date_added": row.get("date_added") or row.get("dateAdded"),
        "themes": row.get("themes", []),
    }


def fetch_all(client: WQClient, dataset_id: str, region: str, delay: int, universe: str, limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        params = {
            "instrumentType": "EQUITY",
            "region": region,
            "delay": delay,
            "universe": universe,
            "dataset.id": dataset_id,
            "limit": limit,
            "offset": offset,
        }
        response = client.sess.get(f"{API_BASE}/data-fields", params=params, timeout=40)
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            wait = float(retry_after) if retry_after else 60.0
            print(f"429 rate limited; sleep {wait:.0f}s")
            time.sleep(wait)
            continue
        if response.status_code != 200:
            raise RuntimeError(f"data-fields HTTP {response.status_code}: {response.text[:500]}")
        data = response.json()
        page = data.get("results")
        if page is None:
            raise RuntimeError(f"unexpected response: {str(data)[:500]}")
        rows.extend(page)
        print(f"fetched offset={offset} page={len(page)} total={len(rows)}")
        total = data.get("count")
        if len(page) < limit or (isinstance(total, int) and len(rows) >= total):
            break
        offset += limit
    return rows


def write_outputs(rows: list[dict[str, Any]]) -> None:
    clean = [normalize_field(row) for row in rows]
    clean.sort(key=lambda item: str(item.get("id") or ""))
    expr = [row for row in clean if str(row.get("id") or "").startswith("ern4_")]
    OUT_RAW.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    OUT_CLEAN.write_text(json.dumps(clean, indent=2, ensure_ascii=False), encoding="utf-8")
    OUT_EXPR.write_text(json.dumps(expr, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"saved raw={len(rows)} -> {OUT_RAW}")
    print(f"saved clean={len(clean)} -> {OUT_CLEAN}")
    print(f"saved expression={len(expr)} -> {OUT_EXPR}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch earnings4 data fields from BRAIN")
    parser.add_argument("--credential", default=str(BASE_DIR / "credential_4.txt"))
    parser.add_argument("--dataset-id", default="earnings4")
    parser.add_argument("--region", default="USA")
    parser.add_argument("--delay", type=int, default=1)
    parser.add_argument("--universe", default="TOP3000")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--from-cache", action="store_true", help="Normalize existing constants/earnings4_fields.json without API")
    args = parser.parse_args()

    if args.from_cache:
        cached = json.loads((BASE_DIR / "constants" / "earnings4_fields.json").read_text(encoding="utf-8"))
        write_outputs(cached)
        return 0

    client = WQClient(args.credential)
    if not client.authenticate():
        raise SystemExit("authentication failed; update credential_4.txt COOKIE first")
    rows = fetch_all(client, args.dataset_id, args.region, args.delay, args.universe, args.limit)
    write_outputs(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
