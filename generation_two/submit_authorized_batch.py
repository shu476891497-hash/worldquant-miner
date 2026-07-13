#!/usr/bin/env python3
"""Submit an explicitly user-authorized list of WorldQuant alpha IDs once.

This is deliberately separate from pp_autosubmit.py: it does not require the
POWER_POOL_ELIGIBLE label. It only acts on the IDs passed on the command line,
records every API response, and stops on platform throttling.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import requests


BASE = Path(__file__).resolve().parent
API = "https://api.worldquantbrain.com"


def read_cookie(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="ignore").strip()
    return text.split("COOKIE:", 1)[1].strip() if "COOKIE:" in text else text


def session_from(path: Path) -> requests.Session:
    session = requests.Session()
    session.cookies.set("t", read_cookie(path), domain=".worldquantbrain.com")
    response = session.get(f"{API}/users/self", timeout=30)
    response.raise_for_status()
    return session


def body(response: requests.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text[:1000]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ids", required=True, help="Comma-separated, explicitly authorized alpha IDs")
    parser.add_argument("--credential", default=str(BASE / "credential_4.txt"))
    parser.add_argument("--results", default=str(BASE / "authorized_submission_results.json"))
    parser.add_argument("--delay", type=float, default=2.0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    ids = list(dict.fromkeys(item.strip() for item in args.ids.split(",") if item.strip()))
    session = session_from(Path(args.credential))
    results: list[dict[str, Any]] = []

    for alpha_id in ids:
        try:
            detail = session.get(f"{API}/alphas/{alpha_id}", timeout=30)
        except requests.RequestException as error:
            results.append({"id": alpha_id, "checked_at": time.time(), "result": "detail_request_error", "error": str(error)})
            print(f"{alpha_id}: detail request failed: {error}", flush=True)
            continue
        row: dict[str, Any] = {"id": alpha_id, "checked_at": time.time(), "detail_status": detail.status_code}
        if detail.status_code != 200:
            row["result"] = "detail_failed"
            row["body"] = body(detail)
            results.append(row)
            print(f"{alpha_id}: detail HTTP {detail.status_code}", flush=True)
            continue
        status = str(detail.json().get("status") or "").upper()
        row["platform_status"] = status
        if status not in {"UNSUBMITTED", ""}:
            row["result"] = "skip_not_unsubmitted"
            results.append(row)
            print(f"{alpha_id}: skip status={status}", flush=True)
            continue
        if args.dry_run:
            row["result"] = "dry_run_ready"
            results.append(row)
            print(f"{alpha_id}: ready", flush=True)
            continue
        try:
            response = session.post(f"{API}/alphas/{alpha_id}/submit", timeout=30)
        except requests.RequestException as error:
            row["result"] = "submit_request_error"
            row["error"] = str(error)
            results.append(row)
            Path(args.results).write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"{alpha_id}: submit request failed: {error}", flush=True)
            continue
        row["submit_status"] = response.status_code
        row["body"] = body(response)
        if response.status_code in {200, 201, 202}:
            row["result"] = "request_accepted_not_verified_active"
        elif response.status_code == 429:
            row["result"] = "throttled"
        else:
            row["result"] = "rejected"
        results.append(row)
        print(f"{alpha_id}: {row['result']} HTTP {response.status_code}", flush=True)
        Path(args.results).write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
        if response.status_code == 429:
            print("platform throttled: stopping without retries", flush=True)
            break
        time.sleep(args.delay)

    Path(args.results).write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
