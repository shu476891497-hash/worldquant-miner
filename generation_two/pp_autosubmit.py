#!/usr/bin/env python3
"""Submit only WQ-classified Power Pool eligible alphas.

This guard never submits an alpha unless WQ already marks it as
POWER_POOL_ELIGIBLE. It keeps a local state file so a submit request is not
triggered repeatedly while WQ is still checking the alpha.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Any

import requests


BASE = Path(__file__).resolve().parent
API = "https://api.worldquantbrain.com"
STATE_PATH = BASE / "pp_autosubmit_state.json"
WINNERS_PATH = BASE / "pp_combo_winners.json"

THEME_NEUTS = {"STATISTICAL", "CROWDING", "FAST", "SLOW", "SLOW_AND_FAST"}
MIN_TURNOVER = 0.01
MAX_TURNOVER = 0.30
MAX_OPERATORS = 8
MAX_FIELDS = 3
GROUP_FIELDS = {"country", "industry", "subindustry", "currency", "market", "sector", "exchange"}
NON_FIELD_IDENTIFIERS = GROUP_FIELDS | {
    "abs",
    "and",
    "bucket",
    "densify",
    "divide",
    "false",
    "filter",
    "group_backfill",
    "group_mean",
    "group_neutralize",
    "group_rank",
    "group_zscore",
    "if_else",
    "is_nan",
    "log",
    "max",
    "min",
    "not",
    "or",
    "rank",
    "signed_power",
    "sqrt",
    "subtract",
    "sum",
    "trade_when",
    "true",
    "ts_arg_max",
    "ts_arg_min",
    "ts_backfill",
    "ts_corr",
    "ts_delta",
    "ts_mean",
    "ts_rank",
    "ts_std_dev",
    "ts_sum",
    "ts_zscore",
    "vec_avg",
    "winsorize",
    "zscore",
}


class AuthExpired(RuntimeError):
    pass


def read_cookie(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="ignore").strip()
    if "COOKIE:" in text:
        return text.split("COOKIE:", 1)[1].strip()
    return text.strip()


def make_session(cookie_path: Path) -> requests.Session:
    session = requests.Session()
    session.cookies.set("t", read_cookie(cookie_path), domain=".worldquantbrain.com")
    response = session.get(f"{API}/users/self", timeout=20)
    if response.status_code == 401:
        raise AuthExpired("cookie expired")
    response.raise_for_status()
    return session


def expression_operators(expression: str) -> set[str]:
    return set(re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", expression))


def expression_fields(expression: str) -> set[str]:
    operators = expression_operators(expression)
    identifiers = set(re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", expression))
    return {
        item
        for item in identifiers
        if item not in operators and item.lower() not in NON_FIELD_IDENTIFIERS and not item.isupper()
    }


def shape_ok(expression: str) -> bool:
    return len(expression_operators(expression)) <= MAX_OPERATORS and len(expression_fields(expression)) <= MAX_FIELDS


def to_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_recordset(payload: dict[str, Any]) -> list[dict[str, Any]]:
    records = payload.get("records") or []
    schema = payload.get("schema") or {}
    properties = schema.get("properties") or payload.get("columns") or []
    if isinstance(properties, dict):
        columns = list(properties)
    else:
        columns = [item.get("name") if isinstance(item, dict) else str(item) for item in properties]
    if not columns and records and isinstance(records[0], dict):
        return records
    rows: list[dict[str, Any]] = []
    for record in records:
        if isinstance(record, dict):
            rows.append(record)
        else:
            rows.append({columns[index]: value for index, value in enumerate(record) if index < len(columns)})
    return rows


def get_recordset(session: requests.Session, alpha_id: str, name: str) -> list[dict[str, Any]]:
    response = session.get(f"{API}/alphas/{alpha_id}/recordsets/{name}", timeout=30)
    if response.status_code == 401:
        raise AuthExpired("cookie expired")
    if response.status_code != 200 or not response.text.strip():
        return []
    return parse_recordset(response.json())


def robust_years(session: requests.Session, alpha_id: str) -> bool:
    rows = get_recordset(session, alpha_id, "yearly-stats")
    if not rows:
        return True
    for row in rows:
        split = row_split_label(row)
        if split != "TEST":
            continue
        returns = row_metric(row, ("returns", "return"))
        sharpe = row_metric(row, ("sharpe",))
        if returns is not None and returns < -0.15:
            return False
        if sharpe is not None and sharpe < -1.0:
            return False
    return True


def row_split_label(row: dict[str, Any]) -> str:
    for value in row.values():
        label = str(value).strip().upper()
        if label in {"TRAIN", "TEST"}:
            return label
    return ""


def row_metric(row: dict[str, Any], names: tuple[str, ...]) -> float | None:
    for key, value in row.items():
        normalized = re.sub(r"[^a-z0-9]+", "", str(key).lower())
        if any(name in normalized for name in names):
            parsed = to_float(value)
            if parsed is not None:
                return parsed
    return None


def classifications_text(alpha: dict[str, Any]) -> str:
    return json.dumps(alpha.get("classifications") or [], ensure_ascii=False)


def is_power_pool_eligible(alpha: dict[str, Any]) -> bool:
    return "POWER_POOL_ELIGIBLE" in classifications_text(alpha)


def alpha_expression(alpha: dict[str, Any]) -> str:
    regular = alpha.get("regular")
    if isinstance(regular, str):
        return regular
    if isinstance(regular, dict):
        return str(regular.get("code") or regular.get("expression") or regular.get("regular") or "")
    return str(alpha.get("expression") or "")


def alpha_settings(alpha: dict[str, Any]) -> dict[str, Any]:
    return alpha.get("settings") or alpha.get("simulationSettings") or {}


def theme_ok(alpha: dict[str, Any]) -> bool:
    settings = alpha_settings(alpha)
    expression = alpha_expression(alpha).lower()
    if "pv1" in expression:
        return False
    return (
        str(settings.get("region") or "").upper() == "USA"
        and str(settings.get("universe") or "").upper() == "TOP1000"
        and int(settings.get("delay") or -1) == 1
        and str(settings.get("neutralization") or "").upper() in THEME_NEUTS
    )


def alpha_quality_ok(alpha: dict[str, Any]) -> bool:
    is_data = alpha.get("is") or {}
    turnover = to_float(is_data.get("turnover"))
    expression = alpha_expression(alpha)
    return turnover is not None and MIN_TURNOVER <= turnover <= MAX_TURNOVER and shape_ok(expression)


def load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {"submitted": {}}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"submitted": {}}


def save_state(state: dict[str, Any]) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def fetch_alpha(session: requests.Session, alpha_id: str) -> dict[str, Any] | None:
    response = session.get(f"{API}/alphas/{alpha_id}", timeout=30)
    if response.status_code == 401:
        raise AuthExpired("cookie expired")
    if response.status_code != 200:
        return None
    return response.json()


def fetch_self_alphas(session: requests.Session, max_pages: int = 20, limit: int = 100) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for page in range(max_pages):
        response = session.get(f"{API}/users/self/alphas", params={"limit": limit, "offset": page * limit}, timeout=30)
        if response.status_code == 401:
            raise AuthExpired("cookie expired")
        if response.status_code != 200:
            break
        payload = response.json()
        page_rows = payload if isinstance(payload, list) else payload.get("results") or payload.get("alphas") or []
        if not page_rows:
            break
        rows.extend(page_rows)
    return rows


def winner_ids(path: Path) -> list[str]:
    if not path.exists():
        return []
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    ids = []
    for row in rows:
        alpha_id = row.get("alpha_id") or row.get("id")
        if alpha_id:
            ids.append(str(alpha_id))
    return ids


def discover_candidates(session: requests.Session, winners_path: Path) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for alpha_id in winner_ids(winners_path):
        alpha = fetch_alpha(session, alpha_id)
        if alpha:
            seen.add(str(alpha.get("id") or alpha_id))
            candidates.append(alpha)

    for alpha in fetch_self_alphas(session):
        alpha_id = str(alpha.get("id") or "")
        if not alpha_id or alpha_id in seen:
            continue
        seen.add(alpha_id)
        candidates.append(alpha)
    return candidates


def description_for(alpha: dict[str, Any]) -> str:
    expression = alpha_expression(alpha)
    fields = sorted(expression_fields(expression))
    return (
        "Power Pool candidate selected by the correlation-aware consultant miner. "
        "The alpha is theme-compliant for USA TOP1000 delay-1, uses a compact low-field expression, "
        "has WQ POWER_POOL_ELIGIBLE classification before submission, and passed turnover and yearly "
        f"robustness guards. Core fields: {', '.join(fields[:3])}."
    )


def patch_alpha(session: requests.Session, alpha: dict[str, Any]) -> bool:
    alpha_id = alpha.get("id")
    payload = {
        "tags": ["PowerPoolSelected", "AutoSubmitGuard"],
        "regular": {"description": description_for(alpha)},
    }
    response = session.patch(f"{API}/alphas/{alpha_id}", json=payload, timeout=30)
    if response.status_code == 401:
        raise AuthExpired("cookie expired")
    return response.status_code in {200, 201, 202, 204}


def submit_alpha(session: requests.Session, alpha_id: str) -> bool:
    response = session.post(f"{API}/alphas/{alpha_id}/submit", timeout=30)
    if response.status_code == 401:
        raise AuthExpired("cookie expired")
    return response.status_code in {200, 201, 202}


def select_submit_ready(session: requests.Session, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ready = []
    for alpha in candidates:
        alpha_id = alpha.get("id")
        if not alpha_id:
            continue
        full_alpha = fetch_alpha(session, str(alpha_id)) or alpha
        status = str(full_alpha.get("status") or "").upper()
        if status not in {"UNSUBMITTED", ""}:
            continue
        if not is_power_pool_eligible(full_alpha):
            continue
        if not theme_ok(full_alpha):
            continue
        if not alpha_quality_ok(full_alpha):
            continue
        if not robust_years(session, str(alpha_id)):
            continue
        ready.append(full_alpha)
    ready.sort(
        key=lambda item: (
            to_float((item.get("is") or {}).get("sharpe")) or 0,
            to_float((item.get("is") or {}).get("returns")) or 0,
        ),
        reverse=True,
    )
    return ready


def run_once(args: argparse.Namespace, session: requests.Session, state: dict[str, Any]) -> int:
    candidates = discover_candidates(session, Path(args.winners))
    print(f"candidates={len(candidates)}", flush=True)
    ready = select_submit_ready(session, candidates)
    print(f"power_pool_ready={len(ready)}", flush=True)

    submitted = 0
    for alpha in ready:
        alpha_id = str(alpha.get("id"))
        if alpha_id in state.get("submitted", {}):
            print(f"skip already submitted/tracked {alpha_id}", flush=True)
            continue
        is_data = alpha.get("is") or {}
        print(
            f"READY id={alpha_id} S={is_data.get('sharpe')} TO={is_data.get('turnover')} R={is_data.get('returns')}",
            flush=True,
        )
        if args.dry_run:
            continue
        if not patch_alpha(session, alpha):
            print(f"patch failed {alpha_id}", flush=True)
            continue
        if not submit_alpha(session, alpha_id):
            print(f"submit failed {alpha_id}", flush=True)
            continue
        state.setdefault("submitted", {})[alpha_id] = {"ts": time.time(), "status": "SUBMITTED"}
        save_state(state)
        print(f"AUTO-SUBMITTED {alpha_id}", flush=True)
        submitted += 1
        if submitted >= args.max_submit:
            break
    return submitted


def main() -> int:
    parser = argparse.ArgumentParser(description="Power Pool eligible-only submit guard")
    parser.add_argument("--credential", default=str(BASE / "credential_4.txt"))
    parser.add_argument("--winners", default=str(WINNERS_PATH))
    parser.add_argument("--max-submit", type=int, default=1)
    parser.add_argument("--interval", type=int, default=300)
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    session = make_session(Path(args.credential))
    state = load_state()
    while True:
        run_once(args, session, state)
        if not args.loop:
            break
        time.sleep(args.interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
