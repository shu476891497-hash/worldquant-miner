#!/usr/bin/env python3
"""Targeted recovery sweep for three near-submit USA/D1 model alphas."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import pp_usa_combo as combo


BASE = Path(__file__).resolve().parent
RESULTS_PATH = BASE / "pp_targeted_optimizer_results.json"

P03 = "mdl211_delta_ebtq_q1_predict"
ESCORE = "mdl141_qes_fleir_escore"
IRR = "mdl141_qes_fleir_irr"


def add(payloads: list[dict[str, Any]], label: str, expression: str, neutralization: str, decay: int = 5) -> None:
    if combo.shape_ok(expression):
        payloads.append(
            {
                "stage": "targeted",
                "label": label,
                "expression": expression,
                "neutralization": neutralization,
                "decay": decay,
                "fields": sorted(combo.expression_fields(expression)),
            }
        )


def single_variants(payloads: list[dict[str, Any]], field: str, prefix: str, original_neutralization: str) -> None:
    base_120 = f"rank(ts_delta({field}, 120))"
    base_63 = f"rank(ts_delta({field}, 63))"
    group_120 = f"group_rank(ts_delta({field}, 120), industry)"

    for neutralization in ("STATISTICAL", "FAST", "SLOW", "CROWDING"):
        if neutralization != original_neutralization:
            add(payloads, f"{prefix}:delta120:{neutralization}", base_120, neutralization)
    for neutralization in ("FAST", "STATISTICAL", "CROWDING"):
        add(payloads, f"{prefix}:delta63:{neutralization}", base_63, neutralization)
    for neutralization in ("STATISTICAL", "CROWDING"):
        add(payloads, f"{prefix}:group120:{neutralization}", group_120, neutralization)


def pair_variants(payloads: list[dict[str, Any]], right: str, label: str) -> None:
    equal = f"rank(ts_delta({P03}, 120)) + rank(ts_delta({right}, 120))"
    p03_weighted = f"0.6*rank(ts_delta({P03}, 120)) + 0.4*rank(ts_delta({right}, 120))"
    right_weighted = f"0.4*rank(ts_delta({P03}, 120)) + 0.6*rank(ts_delta({right}, 120))"
    group = f"group_rank(ts_delta({P03}, 120), industry) + group_rank(ts_delta({right}, 120), industry)"

    for neutralization in ("STATISTICAL", "FAST", "SLOW", "CROWDING"):
        add(payloads, f"{label}:equal:{neutralization}", equal, neutralization)
    add(payloads, f"{label}:p03_weighted:STATISTICAL", p03_weighted, "STATISTICAL")
    add(payloads, f"{label}:right_weighted:STATISTICAL", right_weighted, "STATISTICAL")
    add(payloads, f"{label}:group:STATISTICAL", group, "STATISTICAL")
    add(payloads, f"{label}:group:CROWDING", group, "CROWDING")


def p03_irr_recovery_variants(payloads: list[dict[str, Any]]) -> None:
    """Keep the slow earnings-prediction anchor, make the IRR leg adaptive."""
    p03_slow = f"rank(ts_delta({P03}, 120))"
    for horizon in (20, 40, 63):
        irr_fast = f"rank(ts_delta({IRR}, {horizon}))"
        equal = f"{p03_slow} + {irr_fast}"
        weighted = f"0.6*{p03_slow} + 0.4*{irr_fast}"
        for neutralization in ("FAST", "STATISTICAL"):
            add(payloads, f"p03_irr:mixed{horizon}:equal:{neutralization}", equal, neutralization)
            add(payloads, f"p03_irr:mixed{horizon}:weighted:{neutralization}", weighted, neutralization)

    group_mixed = (
        f"group_rank(ts_delta({P03}, 120), industry) + "
        f"group_rank(ts_delta({IRR}, 40), industry)"
    )
    add(payloads, "p03_irr:mixed40:group:FAST", group_mixed, "FAST")
    add(payloads, "p03_irr:mixed40:group:STATISTICAL", group_mixed, "STATISTICAL")

    slow_pair = f"rank(ts_delta({P03}, 120)) + rank(ts_delta({IRR}, 120))"
    add(payloads, "p03_irr:hump01:FAST", f"hump({slow_pair}, hump=0.01)", "FAST")
    add(payloads, "p03_irr:hump005:STATISTICAL", f"hump({slow_pair}, hump=0.005)", "STATISTICAL")


def p03_irr_expansion_variants(payloads: list[dict[str, Any]]) -> None:
    """Fill the remaining multi-simulation capacity with distinct response regimes."""
    p03_horizons = (63, 90, 120)
    irr_horizons = (10, 20, 40, 63, 90)
    already_tested = {(120, 20), (120, 40), (120, 63)}

    for p03_horizon in p03_horizons:
        for irr_horizon in irr_horizons:
            if (p03_horizon, irr_horizon) in already_tested:
                continue
            p03_leg = f"rank(ts_delta({P03}, {p03_horizon}))"
            irr_leg = f"rank(ts_delta({IRR}, {irr_horizon}))"
            add(payloads, f"expand:{p03_horizon}:{irr_horizon}:equal:FAST", f"{p03_leg} + {irr_leg}", "FAST")
            add(payloads, f"expand:{p03_horizon}:{irr_horizon}:weighted:FAST", f"0.6*{p03_leg} + 0.4*{irr_leg}", "FAST")
            add(payloads, f"expand:{p03_horizon}:{irr_horizon}:equal:STATISTICAL", f"{p03_leg} + {irr_leg}", "STATISTICAL")

    for p03_horizon in p03_horizons:
        for irr_horizon in (10, 20, 40, 63):
            if (p03_horizon, irr_horizon) == (120, 40):
                continue
            expression = (
                f"group_rank(ts_delta({P03}, {p03_horizon}), industry) + "
                f"group_rank(ts_delta({IRR}, {irr_horizon}), industry)"
            )
            add(payloads, f"expand:{p03_horizon}:{irr_horizon}:group:FAST", expression, "FAST")
            add(payloads, f"expand:{p03_horizon}:{irr_horizon}:group:STATISTICAL", expression, "STATISTICAL")

    for p03_horizon, irr_horizon, threshold in ((63, 20, "0.01"), (90, 40, "0.01"), (120, 10, "0.005"), (120, 90, "0.005")):
        expression = (
            f"hump(rank(ts_delta({P03}, {p03_horizon})) + "
            f"rank(ts_delta({IRR}, {irr_horizon})), hump={threshold})"
        )
        add(payloads, f"expand:{p03_horizon}:{irr_horizon}:hump{threshold}:FAST", expression, "FAST")

    for p03_horizon, irr_horizon in ((120, 20), (90, 40)):
        signal = f"rank(ts_delta({P03}, {p03_horizon})) + rank(ts_delta({IRR}, {irr_horizon}))"
        expression = f"trade_when(ts_rank(abs(ts_delta({IRR}, 20)), 252) > 0.6, {signal}, -1)"
        add(payloads, f"expand:{p03_horizon}:{irr_horizon}:material_revision:FAST", expression, "FAST")


def p03_escore_expansion_variants(payloads: list[dict[str, Any]]) -> None:
    """Use the second independent leg to occupy the final two multi-sim slots."""
    pairs = ((63, 20), (63, 40), (90, 20), (90, 40), (90, 63), (120, 20))
    for p03_horizon, escore_horizon in pairs:
        p03_leg = f"rank(ts_delta({P03}, {p03_horizon}))"
        escore_leg = f"rank(ts_delta({ESCORE}, {escore_horizon}))"
        add(payloads, f"escore_expand:{p03_horizon}:{escore_horizon}:equal:FAST", f"{p03_leg} + {escore_leg}", "FAST")
        add(payloads, f"escore_expand:{p03_horizon}:{escore_horizon}:weighted:FAST", f"0.6*{p03_leg} + 0.4*{escore_leg}", "FAST")

    group = (
        f"group_rank(ts_delta({P03}, 90), industry) + "
        f"group_rank(ts_delta({ESCORE}, 40), industry)"
    )
    add(payloads, "escore_expand:90:40:group:FAST", group, "FAST")
    add(payloads, "escore_expand:90:40:group:STATISTICAL", group, "STATISTICAL")
    signal = f"rank(ts_delta({P03}, 120)) + rank(ts_delta({ESCORE}, 20))"
    add(payloads, "escore_expand:120:20:hump01:FAST", f"hump({signal}, hump=0.01)", "FAST")
    material = f"trade_when(ts_rank(abs(ts_delta({ESCORE}, 20)), 252) > 0.6, {signal}, -1)"
    add(payloads, "escore_expand:120:20:material_revision:FAST", material, "FAST")


def build_payloads(
    recovery_only: bool = False,
    expansion_only: bool = False,
    escore_expansion_only: bool = False,
    full_batch: bool = False,
) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    if full_batch:
        p03_irr_recovery_variants(payloads)
        expansion: list[dict[str, Any]] = []
        p03_irr_expansion_variants(expansion)
        payloads.extend(expansion[:48])
        p03_escore_expansion_variants(payloads)
        return payloads
    if expansion_only:
        p03_irr_expansion_variants(payloads)
        return payloads
    if escore_expansion_only:
        p03_escore_expansion_variants(payloads)
        return payloads
    if not recovery_only:
        single_variants(payloads, P03, "p03", "FAST")
        single_variants(payloads, ESCORE, "escore", "SLOW")
        single_variants(payloads, IRR, "irr", "SLOW")
        pair_variants(payloads, ESCORE, "p03_escore")
        pair_variants(payloads, IRR, "p03_irr")
    p03_irr_recovery_variants(payloads)
    return payloads


def serialize(row: dict[str, Any], robust: bool) -> dict[str, Any]:
    return {
        "alpha_id": row.get("alpha_id"),
        "label": row["label"],
        "expression": row["expression"],
        "neutralization": row["neutralization"],
        "fields": row["fields"],
        "sharpe": row.get("sharpe"),
        "turnover": row.get("turnover"),
        "returns": row.get("returns"),
        "fitness": row.get("fitness"),
        "drawdown": row.get("drawdown"),
        "fails": row.get("fails"),
        "robust_years": robust,
        "power_pool_candidate": (
            row.get("sharpe", 0) >= 1.3
            and combo.MIN_TURNOVER <= row.get("turnover", 0) <= combo.MAX_TURNOVER
            and not row.get("fails")
            and robust
        ),
        "regular_submit_candidate": (
            row.get("sharpe", 0) >= 1.58
            and not row.get("fails")
            and robust
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Targeted optimizer for P03/O0/RR model signals")
    parser.add_argument("--credential", default=str(BASE / "credential_4.txt"))
    parser.add_argument("--concurrent-multi", type=int, default=int(os.getenv("PP_TARGET_CONCURRENT_MULTI", "3")))
    parser.add_argument("--multi-size", type=int, default=10)
    parser.add_argument("--poll-sleep", type=int, default=8)
    parser.add_argument("--recovery-only", action="store_true")
    parser.add_argument("--expansion-only", action="store_true")
    parser.add_argument("--escore-expansion-only", action="store_true")
    parser.add_argument("--full-batch", action="store_true")
    parser.add_argument("--results", default=str(RESULTS_PATH))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    payloads = build_payloads(
        args.recovery_only,
        args.expansion_only,
        args.escore_expansion_only,
        args.full_batch,
    )
    print(f"targeted_payloads={len(payloads)}", flush=True)
    if args.dry_run:
        for payload in payloads:
            print(f"{payload['label']} -> {payload['expression']} [{payload['neutralization']}]", flush=True)
        return 0

    session = combo.make_session(Path(args.credential))
    results = combo.run_multi(session, payloads, args.concurrent_multi, args.multi_size, args.poll_sleep)
    serialized: list[dict[str, Any]] = []
    for row in results:
        robust = combo.robust_years(session, row["alpha_id"])
        serialized.append(serialize(row, robust))
    serialized.sort(key=lambda item: (item["regular_submit_candidate"], item["power_pool_candidate"], item["sharpe"], item["returns"]), reverse=True)
    result_path = Path(args.results)
    result_path.write_text(json.dumps(serialized, indent=2, ensure_ascii=False), encoding="utf-8")

    for row in serialized:
        print(
            f"S={row['sharpe']:.2f} TO={row['turnover']:.1%} R={row['returns']:.1%} "
            f"regular={row['regular_submit_candidate']} pp={row['power_pool_candidate']} "
            f"id={row['alpha_id']} {row['label']}",
            flush=True,
        )
    print(f"saved={result_path.name} results={len(serialized)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
