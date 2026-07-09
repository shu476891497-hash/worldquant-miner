#!/usr/bin/env python3
"""Power Pool USA combo miner.

Builds theme-compliant, correlation-aware two-signal combinations from the
consultant field cache. The script streams the large JSONL field file, tests
diverse single model/prediction signals, measures PnL correlation between good
singles, then only simulates low-correlation pairs.
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import os
import random
import re
import time
from pathlib import Path
from typing import Any

import requests


BASE = Path(__file__).resolve().parent
API = "https://api.worldquantbrain.com"
JSONL = BASE / "constants" / "consultant_fields" / "consultant_expression_fields.jsonl"
SINGLES_PATH = BASE / "pp_combo_singles.json"
WINNERS_PATH = BASE / "pp_combo_winners.json"

THEME_NEUTS = ["STATISTICAL", "CROWDING", "FAST", "SLOW", "SLOW_AND_FAST"]
MIN_TURNOVER = 0.01
MAX_TURNOVER = 0.30
MIN_SINGLE_SHARPE = 1.0
MIN_COMBO_SHARPE = 1.3
MAX_OPERATORS = 8
MAX_FIELDS = 3
MAX_PAIR_CORR = 0.30

PRIORITY_DATASETS = [
    "multifactor_return_pred",
    "predictive_starmine",
    "ai_equity_alpha",
    "analyst_revision_horizons",
    "global_seasonal_model",
    "tech_chart_model",
]

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
    token = read_cookie(cookie_path)
    session = requests.Session()
    session.cookies.set("t", token, domain=".worldquantbrain.com")
    response = session.get(f"{API}/users/self", timeout=20)
    if response.status_code == 401:
        raise AuthExpired("cookie expired")
    response.raise_for_status()
    return session


def api_url(location: str) -> str:
    if location.startswith("http"):
        return location
    return API + location


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
    operators = expression_operators(expression)
    fields = expression_fields(expression)
    return len(operators) <= MAX_OPERATORS and len(fields) <= MAX_FIELDS


def is_priority_dataset(dataset: str, category: str, name: str) -> bool:
    haystack = f"{dataset} {category} {name}".lower()
    if dataset in PRIORITY_DATASETS:
        return True
    blocked = ("analyst_", "earnings", "option", "fundamental", "board", "news", "social")
    if any(token in haystack for token in blocked):
        return False
    return any(token in haystack for token in ("model", "predictive", "predict", "return_pred", "alpha", "cnn", "technical", "chart"))


def stream_candidate_fields(
    max_fields: int,
    fields_per_dataset: int,
    used_fields: set[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    used_fields = used_fields or set()
    by_dataset: dict[str, list[dict[str, Any]]] = {}

    with JSONL.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("region") != "USA" or row.get("delay") != 1 or row.get("type") != "MATRIX":
                continue
            dataset = str(row.get("dataset_id") or row.get("dataset") or "").lower()
            if not dataset or dataset.startswith("pv1"):
                continue
            category = str(row.get("category_name") or row.get("category") or "").lower()
            field_id = str(row.get("id") or "")
            if not field_id or field_id in used_fields:
                continue
            field_lower = field_id.lower()
            if "dividend" in field_lower:
                continue
            if dataset not in PRIORITY_DATASETS and any(
                token in field_lower for token in ("earnings", "ebit", "eps", "revenue", "sales")
            ):
                continue
            if not is_priority_dataset(dataset, category, str(row.get("name") or "")):
                continue

            bucket = by_dataset.setdefault(dataset, [])
            if len(bucket) < fields_per_dataset:
                bucket.append(
                    {
                        "id": field_id,
                        "dataset": dataset,
                        "category": category,
                        "name": row.get("name") or "",
                    }
                )

    selected: list[dict[str, Any]] = []
    for dataset in PRIORITY_DATASETS:
        selected.extend(by_dataset.get(dataset, [])[:fields_per_dataset])
    for dataset in sorted(by_dataset):
        if dataset not in PRIORITY_DATASETS:
            selected.extend(by_dataset[dataset][:1])
        if len(selected) >= max_fields:
            break
    selected = selected[:max_fields]
    field_dataset = {item["id"]: item["dataset"] for item in selected}
    return selected, field_dataset


def get_alpha_list_page(session: requests.Session, offset: int, limit: int) -> list[dict[str, Any]]:
    params = {"limit": limit, "offset": offset}
    response = session.get(f"{API}/users/self/alphas", params=params, timeout=30)
    if response.status_code == 401:
        raise AuthExpired("cookie expired")
    if response.status_code != 200:
        return []
    payload = response.json()
    if isinstance(payload, list):
        return payload
    return payload.get("results") or payload.get("alphas") or []


def fetch_used_fields(session: requests.Session, max_pages: int = 20, limit: int = 100) -> set[str]:
    used: set[str] = set()
    for page in range(max_pages):
        rows = get_alpha_list_page(session, page * limit, limit)
        if not rows:
            break
        for alpha in rows:
            expression = str(alpha.get("regular") or alpha.get("expression") or "")
            used.update(expression_fields(expression))
    return used


def make_config(expression: str, neutralization: str, decay: int = 5) -> dict[str, Any]:
    return {
        "type": "REGULAR",
        "settings": {
            "instrumentType": "EQUITY",
            "region": "USA",
            "universe": "TOP1000",
            "delay": 1,
            "decay": decay,
            "neutralization": neutralization,
            "truncation": 0.05,
            "pasteurization": "ON",
            "unitHandling": "VERIFY",
            "nanHandling": "OFF",
            "language": "FASTEXPR",
            "visualization": False,
            "testPeriod": "P5Y0M0D",
        },
        "regular": expression,
    }


def alpha_metrics(alpha: dict[str, Any]) -> dict[str, Any]:
    is_data = alpha.get("is") or {}
    checks = is_data.get("checks") or []
    fails = [
        check.get("name")
        for check in checks
        if check.get("result") == "FAIL" and check.get("name") != "OLD_SIMULATION"
    ]
    return {
        "alpha_id": alpha.get("id"),
        "sharpe": float(is_data.get("sharpe") or 0),
        "turnover": float(is_data.get("turnover") or 0),
        "returns": float(is_data.get("returns") or 0),
        "fitness": float(is_data.get("fitness") or 0),
        "margin": float(is_data.get("margin") or 0),
        "drawdown": float(is_data.get("drawdown") or 0),
        "fails": fails,
        "classifications": alpha.get("classifications") or [],
        "status": alpha.get("status"),
    }


def run_multi(
    session: requests.Session,
    payloads: list[dict[str, Any]],
    concurrent_multi: int,
    multi_size: int,
    poll_sleep: int,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    batches = [payloads[i : i + multi_size] for i in range(0, len(payloads), multi_size)]
    inflight: dict[str, list[dict[str, Any]]] = {}
    batch_index = 0

    while batch_index < len(batches) or inflight:
        while len(inflight) < concurrent_multi and batch_index < len(batches):
            batch = batches[batch_index]
            batch_index += 1
            request_payload = [make_config(item["expression"], item["neutralization"], item.get("decay", 5)) for item in batch]
            location = None
            for _ in range(5):
                response = session.post(f"{API}/simulations", json=request_payload, timeout=45)
                if response.status_code == 401:
                    raise AuthExpired("cookie expired")
                if response.status_code == 201:
                    location = response.headers.get("Location")
                    break
                if response.status_code == 429:
                    time.sleep(20)
                    continue
                if response.status_code == 400:
                    break
                time.sleep(8)
            if location:
                inflight[api_url(location)] = batch
            time.sleep(2)

        for location in list(inflight):
            response = session.get(location, timeout=30)
            if response.status_code == 401:
                raise AuthExpired("cookie expired")
            if response.status_code != 200:
                continue
            retry_after = float(response.headers.get("Retry-After", 0) or 0)
            if retry_after > 0:
                continue

            children = response.json().get("children") or []
            batch = inflight.pop(location)
            for index, child in enumerate(children):
                if index >= len(batch):
                    continue
                item = batch[index]
                try:
                    simulation = session.get(f"{API}/simulations/{child}", timeout=30).json()
                    alpha_id = simulation.get("alpha")
                    if not alpha_id:
                        continue
                    alpha_response = session.get(f"{API}/alphas/{alpha_id}", timeout=30)
                    if alpha_response.status_code == 401:
                        raise AuthExpired("cookie expired")
                    alpha = alpha_response.json()
                    metrics = alpha_metrics(alpha)
                    results.append({**item, **metrics})
                except AuthExpired:
                    raise
                except Exception:
                    continue
        time.sleep(poll_sleep)
    return results


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
            rows.append({columns[i]: value for i, value in enumerate(record) if i < len(columns)})
    return rows


def get_recordset(session: requests.Session, alpha_id: str, name: str) -> list[dict[str, Any]]:
    for _ in range(3):
        response = session.get(f"{API}/alphas/{alpha_id}/recordsets/{name}", timeout=30)
        if response.status_code == 401:
            raise AuthExpired("cookie expired")
        if response.status_code == 200 and response.text.strip():
            return parse_recordset(response.json())
        time.sleep(2)
    return []


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


def to_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def pnl_series(session: requests.Session, alpha_id: str) -> dict[str, float]:
    rows = get_recordset(session, alpha_id, "pnl")
    if not rows:
        return {}
    first = rows[0]
    date_keys = [key for key in first if "date" in key.lower()]
    numeric_keys = [
        key
        for key in first
        if key not in date_keys and to_float(first.get(key)) is not None and "count" not in key.lower()
    ]
    if not date_keys or not numeric_keys:
        return {}
    date_key = date_keys[0]
    pnl_keys = [key for key in numeric_keys if "pnl" in key.lower()]
    value_key = pnl_keys[0] if pnl_keys else numeric_keys[0]
    series: dict[str, float] = {}
    for row in rows:
        value = to_float(row.get(value_key))
        date = row.get(date_key)
        if date is not None and value is not None:
            series[str(date)] = value
    return series


def pearson_from_series(left: dict[str, float], right: dict[str, float]) -> float | None:
    common = sorted(set(left) & set(right))
    if len(common) < 51:
        return None
    xs = [left[common[index]] - left[common[index - 1]] for index in range(1, len(common))]
    ys = [right[common[index]] - right[common[index - 1]] for index in range(1, len(common))]
    if len(xs) < 50:
        return None
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    dx = [value - mean_x for value in xs]
    dy = [value - mean_y for value in ys]
    denom = math.sqrt(sum(value * value for value in dx) * sum(value * value for value in dy))
    if denom == 0:
        return None
    return sum(a * b for a, b in zip(dx, dy)) / denom


def passes_basic_quality(row: dict[str, Any], min_sharpe: float) -> bool:
    return (
        row.get("sharpe", 0) >= min_sharpe
        and MIN_TURNOVER <= row.get("turnover", 0) <= MAX_TURNOVER
        and not row.get("fails")
        and shape_ok(row["expression"])
    )


def keep_best_per_field(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for row in rows:
        fields = list(expression_fields(row["expression"]))
        key = fields[0] if fields else row["label"]
        current = best.get(key)
        if current is None or (row["sharpe"], row["returns"]) > (current["sharpe"], current["returns"]):
            best[key] = row
    return sorted(best.values(), key=lambda item: (item["sharpe"], item["returns"]), reverse=True)


def build_single_payloads(fields: list[dict[str, Any]], max_payloads: int) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for item in fields:
        field = item["id"]
        dataset = item["dataset"]
        templates = [
            (f"delta120:{field}", f"rank(ts_delta({field}, 120))", "STATISTICAL", 5),
            (f"grp_delta120:{field}", f"group_rank(ts_delta({field}, 120), industry)", "SLOW", 5),
            (f"z60:{field}", f"group_rank(ts_zscore({field}, 60), industry)", "FAST", 0),
        ]
        for label, expression, neutralization, decay in templates:
            if shape_ok(expression):
                payloads.append(
                    {
                        "stage": "single",
                        "label": label,
                        "expression": expression,
                        "neutralization": neutralization,
                        "decay": decay,
                        "fields": [field],
                        "datasets": [dataset],
                    }
                )
    random.shuffle(payloads)
    return payloads[:max_payloads]


def build_combo_expression(template: str, left_field: str, right_field: str) -> str:
    if template == "delta_equal":
        return f"rank(ts_delta({left_field}, 120)) + rank(ts_delta({right_field}, 120))"
    if template == "delta_left":
        return f"0.6*rank(ts_delta({left_field}, 120)) + 0.4*rank(ts_delta({right_field}, 120))"
    if template == "delta_right":
        return f"0.4*rank(ts_delta({left_field}, 120)) + 0.6*rank(ts_delta({right_field}, 120))"
    if template == "zscore_group":
        return f"group_rank(ts_zscore({left_field}, 60), industry) + group_rank(ts_zscore({right_field}, 60), industry)"
    raise ValueError(template)


def build_combo_payloads(
    singles: list[dict[str, Any]],
    pnl_by_alpha: dict[str, dict[str, float]],
    max_combos: int,
    corr_threshold: float,
    allow_missing_pnl: bool,
) -> list[dict[str, Any]]:
    candidates: list[tuple[float, dict[str, Any], dict[str, Any], float | None]] = []
    fallback: list[tuple[float, dict[str, Any], dict[str, Any], float | None]] = []

    for left, right in itertools.combinations(singles, 2):
        left_field = left["fields"][0]
        right_field = right["fields"][0]
        if left_field == right_field:
            continue
        if set(left["fields"]) & set(right["fields"]):
            continue
        if set(left["datasets"]) & set(right["datasets"]):
            continue

        corr = pearson_from_series(
            pnl_by_alpha.get(left["alpha_id"], {}),
            pnl_by_alpha.get(right["alpha_id"], {}),
        )
        score = left["sharpe"] + right["sharpe"]
        row = (score, left, right, corr)
        if corr is not None and abs(corr) < corr_threshold:
            candidates.append(row)
        elif corr is None and allow_missing_pnl:
            fallback.append(row)

    candidates.sort(key=lambda item: (-(abs(item[3]) if item[3] is not None else 9), item[0]), reverse=True)
    fallback.sort(key=lambda item: item[0], reverse=True)
    selected_pairs = candidates + fallback

    payloads: list[dict[str, Any]] = []
    templates = ["delta_equal", "delta_left", "delta_right", "zscore_group"]
    for _, left, right, corr in selected_pairs:
        left_field = left["fields"][0]
        right_field = right["fields"][0]
        for template in templates:
            expression = build_combo_expression(template, left_field, right_field)
            if not shape_ok(expression):
                continue
            payloads.append(
                {
                    "stage": "combo",
                    "label": f"{template}:{left_field}+{right_field}",
                    "expression": expression,
                    "neutralization": "STATISTICAL",
                    "decay": 5 if template != "zscore_group" else 0,
                    "fields": [left_field, right_field],
                    "datasets": list({left["datasets"][0], right["datasets"][0]}),
                    "pair_corr": corr,
                    "single_alpha_ids": [left["alpha_id"], right["alpha_id"]],
                    "single_sharpes": [left["sharpe"], right["sharpe"]],
                }
            )
            if len(payloads) >= max_combos:
                return payloads
    return payloads[:max_combos]


def save_json(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Power Pool USA correlation-aware combo miner")
    parser.add_argument("--credential", default=str(BASE / "credential_4.txt"))
    parser.add_argument("--max-fields", type=int, default=int(os.getenv("PP_COMBO_MAX_FIELDS", "120")))
    parser.add_argument("--fields-per-dataset", type=int, default=2)
    parser.add_argument("--max-single-payloads", type=int, default=int(os.getenv("PP_COMBO_MAX_SINGLE_PAYLOADS", "240")))
    parser.add_argument("--top-singles", type=int, default=int(os.getenv("PP_COMBO_TOP_SINGLES", "24")))
    parser.add_argument("--max-combos", type=int, default=int(os.getenv("PP_COMBO_MAX_COMBOS", "160")))
    parser.add_argument("--concurrent-multi", type=int, default=int(os.getenv("PP_COMBO_CONCURRENT_MULTI", "8")))
    parser.add_argument("--multi-size", type=int, default=int(os.getenv("PP_COMBO_MULTI_SIZE", "10")))
    parser.add_argument("--poll-sleep", type=int, default=int(os.getenv("PP_COMBO_POLL_SLEEP", "8")))
    parser.add_argument("--corr-threshold", type=float, default=MAX_PAIR_CORR)
    parser.add_argument("--single-sharpe", type=float, default=MIN_SINGLE_SHARPE)
    parser.add_argument("--combo-sharpe", type=float, default=MIN_COMBO_SHARPE)
    parser.add_argument("--fetch-used-fields", action="store_true")
    parser.add_argument("--allow-missing-pnl", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    random.seed(23)
    used_fields: set[str] = set()
    session: requests.Session | None = None
    if not args.dry_run:
        session = make_session(Path(args.credential))
        if args.fetch_used_fields:
            used_fields = fetch_used_fields(session)
            print(f"loaded used_fields={len(used_fields)}", flush=True)

    fields, field_dataset = stream_candidate_fields(args.max_fields, args.fields_per_dataset, used_fields)
    print(f"candidate_fields={len(fields)} datasets={len(set(field_dataset.values()))}", flush=True)

    single_payloads = build_single_payloads(fields, args.max_single_payloads)
    print(f"single_payloads={len(single_payloads)}", flush=True)
    if args.dry_run:
        for item in single_payloads[:10]:
            print(f"  {item['label']} -> {item['expression']}", flush=True)
        print("dry-run only: no API simulation submitted", flush=True)
        return 0

    assert session is not None
    print("stage1 simulate singles", flush=True)
    single_results = run_multi(session, single_payloads, args.concurrent_multi, args.multi_size, args.poll_sleep)
    good_singles = [row for row in single_results if passes_basic_quality(row, args.single_sharpe)]
    good_singles = [row for row in good_singles if robust_years(session, row["alpha_id"])]
    good_singles = keep_best_per_field(good_singles)
    top_singles = good_singles[: args.top_singles]
    save_json(SINGLES_PATH, good_singles)
    print(f"good_singles={len(good_singles)} top_singles={len(top_singles)} saved={SINGLES_PATH.name}", flush=True)
    for row in top_singles[:12]:
        print(
            f"  single S={row['sharpe']:.2f} TO={row['turnover']:.1%} R={row['returns']:.1%} id={row['alpha_id']} {row['fields'][0]}",
            flush=True,
        )

    print("fetch pnl for correlation-aware pairing", flush=True)
    pnl_by_alpha = {row["alpha_id"]: pnl_series(session, row["alpha_id"]) for row in top_singles}
    with_pnl = sum(1 for series in pnl_by_alpha.values() if series)
    print(f"pnl_series_loaded={with_pnl}/{len(top_singles)}", flush=True)

    combo_payloads = build_combo_payloads(
        top_singles,
        pnl_by_alpha,
        args.max_combos,
        args.corr_threshold,
        args.allow_missing_pnl,
    )
    print(f"combo_payloads={len(combo_payloads)}", flush=True)
    if not combo_payloads:
        print("no combos passed pair filter; rerun with --allow-missing-pnl if recordsets are unavailable", flush=True)
        return 0

    print("stage2 simulate combos", flush=True)
    combo_results = run_multi(session, combo_payloads, args.concurrent_multi, args.multi_size, args.poll_sleep)
    winners = [row for row in combo_results if passes_basic_quality(row, args.combo_sharpe)]
    winners = [row for row in winners if robust_years(session, row["alpha_id"])]
    winners.sort(key=lambda item: (item["sharpe"], item["returns"], -item["turnover"]), reverse=True)
    save_json(WINNERS_PATH, winners)

    print("=== POWER POOL COMBO WINNERS ===", flush=True)
    for row in winners[:25]:
        corr = row.get("pair_corr")
        corr_text = "NA" if corr is None else f"{corr:.2f}"
        print(
            f"  S={row['sharpe']:.2f} TO={row['turnover']:.1%} R={row['returns']:.1%} corr={corr_text} id={row['alpha_id']} {row['fields']}",
            flush=True,
        )
    print(f"finished good_singles={len(good_singles)} winners={len(winners)} saved={WINNERS_PATH.name}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
