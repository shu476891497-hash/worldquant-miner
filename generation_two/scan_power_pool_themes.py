#!/usr/bin/env python3
"""Scan self alphas for concrete Power Pool theme checks via the BRAIN API."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import time
from pathlib import Path
from typing import Any

import requests


API = "https://api.worldquantbrain.com"
BASE = Path(__file__).resolve().parent
THEMES = {
    "myzqOo4": "GLB High Turnover Theme",
    "lyvRddy": "USA/D1 Power Pool July'26",
}


def read_cookie(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="ignore")
    return text.split("COOKIE:", 1)[1].strip() if "COOKIE:" in text else text.strip()


def get_with_retry(session: requests.Session, url: str, params: dict[str, Any]) -> requests.Response:
    for attempt in range(6):
        try:
            response = session.get(url, params=params, timeout=45)
        except requests.RequestException:
            time.sleep(min(30, 3 * (attempt + 1)))
            continue
        if response.status_code == 429:
            wait = float(response.headers.get("Retry-After", 15) or 15)
            time.sleep(max(5, wait))
            continue
        return response
    raise RuntimeError(f"API page failed after retries: {url} {params}")


def theme_rows(alpha: dict[str, Any]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    checks = ((alpha.get("is") or {}).get("checks") or [])
    for check in checks:
        if check.get("name") != "MATCHES_THEMES":
            continue
        raw = json.dumps(check, ensure_ascii=False)
        for theme_id, theme_name in THEMES.items():
            if theme_id not in raw:
                continue
            settings = alpha.get("settings") or {}
            is_data = alpha.get("is") or {}
            output.append(
                {
                    "theme_id": theme_id,
                    "theme_name": theme_name,
                    "id": alpha.get("id"),
                    "status": alpha.get("status"),
                    "region": settings.get("region"),
                    "universe": settings.get("universe"),
                    "delay": settings.get("delay"),
                    "neutralization": settings.get("neutralization"),
                    "decay": settings.get("decay"),
                    "truncation": settings.get("truncation"),
                    "sharpe": is_data.get("sharpe"),
                    "turnover": is_data.get("turnover"),
                    "fitness": is_data.get("fitness"),
                    "theme_result": check.get("result"),
                    "theme_check": check,
                }
            )
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--credential", default=str(BASE / "credential_4.txt"))
    parser.add_argument("--output", default=str(BASE / "theme_api_scan_2026-07-13.json"))
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--max-alphas", type=int, default=10000)
    parser.add_argument("--start-offset", type=int, default=0)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    session = requests.Session()
    session.cookies.set("t", read_cookie(Path(args.credential)), domain=".worldquantbrain.com")
    auth = session.get(f"{API}/users/self", timeout=30)
    print(f"auth={auth.status_code}", flush=True)
    auth.raise_for_status()

    output_path = Path(args.output)
    def fetch(offset: int) -> tuple[int, list[dict[str, Any]]]:
        response = get_with_retry(
            session,
            f"{API}/users/self/alphas",
            {"limit": args.limit, "offset": offset},
        )
        if response.status_code != 200:
            return offset, []
        return offset, response.json().get("results") or []

    pages: list[tuple[int, list[dict[str, Any]]]] = []
    offsets = list(range(args.start_offset, args.start_offset + args.max_alphas, args.limit))
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(fetch, offset) for offset in offsets]
        for completed, future in enumerate(concurrent.futures.as_completed(futures), 1):
            pages.append(future.result())
            if completed % args.workers == 0 or completed == len(futures):
                print(f"pages={completed}/{len(futures)}", flush=True)

    matches: list[dict[str, Any]] = []
    scanned = 0
    for _, rows in sorted(pages):
        scanned += len(rows)
        for alpha in rows:
            matches.extend(theme_rows(alpha))
    output_path.write_text(
        json.dumps({"scanned": scanned, "matches": matches}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    for theme_id, theme_name in THEMES.items():
        rows = [row for row in matches if row["theme_id"] == theme_id]
        counts: dict[str, int] = {}
        for row in rows:
            result = str(row.get("theme_result") or "UNKNOWN")
            counts[result] = counts.get(result, 0) + 1
        print(f"theme={theme_id} name={theme_name} rows={len(rows)} results={counts}", flush=True)
        for row in sorted(rows, key=lambda item: float(item.get("turnover") or 0), reverse=True)[:10]:
            print(
                f"  id={row['id']} status={row['status']} region={row['region']} "
                f"universe={row['universe']} delay={row['delay']} TO={row['turnover']} "
                f"S={row['sharpe']} result={row['theme_result']}",
                flush=True,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
