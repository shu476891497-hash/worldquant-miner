#!/usr/bin/env python3
"""Small, evidence-first probe for the GLB High Turnover Power Pool theme.

GLB simulations occupy two account slots, so this script deliberately submits
one simulation at a time. It focuses on short-horizon model signals, records
the platform's MATCHES_THEMES check, and does not submit alpha requests.
"""

from __future__ import annotations

import argparse
import json
import random
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import pp_usa_combo as base


ROOT = Path(__file__).resolve().parent
FIELDS = ROOT / "constants" / "consultant_fields" / "consultant_expression_fields.jsonl"
RESULTS = ROOT / "pp_glb_high_turnover_probe_results.json"

PRIORITY_DATASETS = {
    "predictive_starmine",
    "global_seasonal_model",
    "tech_chart_model",
    "chart_cnn_alpha",
    "analyst_revision_horizons",
    "model77",
    "model219",
    "model264",
}


def stream_glb_fields(max_fields: int, per_dataset: int) -> list[dict[str, str]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    with FIELDS.open(encoding="utf-8") as handle:
        for line in handle:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("region") != "GLB" or row.get("delay") != 1 or row.get("type") != "MATRIX":
                continue
            dataset = str(row.get("dataset_id") or row.get("dataset") or "").lower()
            field = str(row.get("id") or "")
            if not field or dataset not in PRIORITY_DATASETS or len(grouped[dataset]) >= per_dataset:
                continue
            grouped[dataset].append({"id": field, "dataset": dataset})

    selected: list[dict[str, str]] = []
    for dataset in sorted(PRIORITY_DATASETS):
        selected.extend(grouped[dataset])
    return selected[:max_fields]


def glb_config(
    expression: str,
    neutralization: str,
    decay: int = 0,
    universe: str = "TOP3000",
    truncation: float = 0.08,
    nan_handling: str = "OFF",
) -> dict[str, Any]:
    return {
        "type": "REGULAR",
        "settings": {
            "instrumentType": "EQUITY",
            "region": "GLB",
            "universe": universe,
            "delay": 1,
            "decay": decay,
            "neutralization": neutralization,
            "truncation": truncation,
            "pasteurization": "ON",
            "unitHandling": "VERIFY",
            "nanHandling": nan_handling,
            "language": "FASTEXPR",
            "visualization": False,
            "testPeriod": "P5Y0M0D",
        },
        "regular": expression,
    }


def build_probe_payloads(fields: list[dict[str, str]], maximum: int) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for item in fields:
        field = item["id"]
        dataset = item["dataset"]
        candidates = [
            ("delta5", f"rank(ts_delta({field}, 5))", "COUNTRY", 0),
            ("delta20", f"rank(ts_delta({field}, 20))", "COUNTRY", 0),
            ("z20", f"group_rank(ts_zscore({field}, 20), country)", "COUNTRY", 0),
            ("rank20", f"group_rank(ts_rank({field}, 20), country)", "COUNTRY", 1),
        ]
        for label, expression, neutralization, decay in candidates:
            if base.shape_ok(expression):
                payloads.append(
                    {
                        "stage": "glb_high_turnover_probe",
                        "label": f"{label}:{field}",
                        "expression": expression,
                        "neutralization": neutralization,
                        "decay": decay,
                        "fields": [field],
                        "datasets": [dataset],
                    }
                )
    random.shuffle(payloads)
    return payloads[:maximum]


def build_kp9_rescue_payloads() -> list[dict[str, Any]]:
    growth = "mdl110_growth"
    sentiment = "mdl110_analyst_sentiment"
    windows = [(90, 90), (60, 60), (40, 40), (20, 20), (60, 120), (120, 60)]
    payloads: list[dict[str, Any]] = []
    for left, right in windows:
        payloads.append(
            {
                "stage": "glb_kp9_high_turnover_rescue",
                "label": f"kp9_delta_{left}_{right}",
                "expression": f"rank(ts_delta({growth},{left}))+rank(ts_delta({sentiment},{right}))",
                "neutralization": "INDUSTRY",
                "decay": 0,
                "universe": "MINVOL1M",
                "truncation": 0.01,
                "nan_handling": "ON",
                "fields": [growth, sentiment],
                "datasets": ["model110"],
            }
        )
    return payloads


def theme_checks(session: Any, alpha_id: str) -> list[dict[str, Any]]:
    response = session.get(f"{base.API}/alphas/{alpha_id}", timeout=30)
    if response.status_code != 200:
        return []
    alpha = response.json()
    checks = (alpha.get("is") or {}).get("checks") or []
    return [
        check
        for check in checks
        if check.get("name") == "MATCHES_THEMES" or str(check.get("name") or "").startswith("HT_")
    ]


def run_single_probe(session: Any, payload: dict[str, Any], poll_sleep: int) -> dict[str, Any] | None:
    """Run one ordinary GLB simulation and retain its alpha result.

    GLB probes use the normal single-simulation endpoint. Its completion body
    contains `alpha`, unlike multi-simulation responses which contain
    `children`, so it cannot reuse pp_usa_combo.run_multi unchanged.
    """
    response = session.post(
        f"{base.API}/simulations",
        json=glb_config(
            payload["expression"],
            payload["neutralization"],
            payload["decay"],
            universe=payload.get("universe", "TOP3000"),
            truncation=payload.get("truncation", 0.08),
            nan_handling=payload.get("nan_handling", "OFF"),
        ),
        timeout=45,
    )
    if response.status_code != 201:
        print(f"submit_failed label={payload['label']} HTTP={response.status_code} {response.text[:300]}", flush=True)
        return None
    location = response.headers.get("Location")
    if not location:
        return None

    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        progress = session.get(location, timeout=30)
        if progress.status_code != 200:
            time.sleep(poll_sleep)
            continue
        retry_after = float(progress.headers.get("Retry-After", "0") or 0)
        data = progress.json()
        alpha_id = data.get("alpha")
        if alpha_id:
            alpha_response = session.get(f"{base.API}/alphas/{alpha_id}", timeout=30)
            if alpha_response.status_code != 200:
                return None
            return {**payload, **base.alpha_metrics(alpha_response.json())}
        time.sleep(max(poll_sleep, retry_after))
    print(f"simulation_timeout label={payload['label']}", flush=True)
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="GLB High Turnover theme probe")
    parser.add_argument("--credential", default=str(ROOT / "credential_4.txt"))
    parser.add_argument("--max-fields", type=int, default=8)
    parser.add_argument("--fields-per-dataset", type=int, default=1)
    parser.add_argument("--max-payloads", type=int, default=12)
    parser.add_argument("--poll-sleep", type=int, default=12)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--kp9-rescue", action="store_true")
    args = parser.parse_args()

    random.seed(713)
    fields = [] if args.kp9_rescue else stream_glb_fields(args.max_fields, args.fields_per_dataset)
    payloads = build_kp9_rescue_payloads() if args.kp9_rescue else build_probe_payloads(fields, args.max_payloads)
    print(f"glb_fields={len(fields)} payloads={len(payloads)}", flush=True)
    if args.dry_run:
        for item in payloads:
            print(f"{item['label']} -> {item['expression']}", flush=True)
        return 0

    session = base.make_session(Path(args.credential))
    results = []
    for payload in payloads:
        result = run_single_probe(session, payload, args.poll_sleep)
        if result:
            results.append(result)

    for row in results:
        alpha_id = row.get("alpha_id")
        row["theme_checks"] = theme_checks(session, alpha_id) if alpha_id else []
        print(
            f"id={alpha_id} S={row.get('sharpe', 0):.2f} TO={row.get('turnover', 0):.1%} "
            f"F={row.get('fitness', 0):.2f} themes={row['theme_checks']}",
            flush=True,
        )
    RESULTS.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"saved={RESULTS.name} results={len(results)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
