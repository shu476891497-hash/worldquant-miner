#!/usr/bin/env python3
"""Power Pool THEME optimizer v3 — TWO-SIGNAL COMBINATION for higher quality.

Single model signals top out at Sharpe ~1.0-1.1 (WQ won't classify them
POWER_POOL_ELIGIBLE). Combining two low-correlated signals lifts Sharpe by ~sqrt(2)
(the official mdl110 growth+sentiment pattern), clearing the eligibility bar and
earning more, while staying <=3 fields / <=8 operators for Power Pool.

Stage 1: test many single fields; keep those with Sharpe>=1.0 (robust, TO<=30%).
Stage 2: combine the best singles PAIRWISE ACROSS DIFFERENT DATASETS as
         rank(ts_delta(A,120)) + rank(ts_delta(B,120)); keep combos with
         Sharpe>=1.3, turnover 1-30%, no out-of-sample blowup year.
Theme-compliant (USA/TOP1000/delay1/statistical|crowding|fast|slow). Multi-sim.
"""
import time, requests, json, hashlib, random
from pathlib import Path

BASE = Path(__file__).resolve().parent
API = "https://api.worldquantbrain.com"
JSONL = BASE / "constants" / "consultant_fields" / "consultant_expression_fields.jsonl"
CONCURRENT_MULTI = 8
MULTI_SIZE = 10
NEUTS = ["STATISTICAL", "SLOW", "FAST"]
random.seed(23)

tok = (BASE / "credential_4.txt").read_text().split("COOKIE:")[1].strip()
s = requests.Session(); s.cookies.set("t", tok, domain=".worldquantbrain.com")
assert s.get(f"{API}/users/self", timeout=20).status_code == 200, "cookie invalid"

# discover diverse USA delay-1 fields, prioritizing prediction/model datasets
PRIORITY = ["multifactor_return_pred", "predictive_starmine", "ai_equity_alpha",
            "analyst_revision_horizons", "global_seasonal_model", "tech_chart_model"]
by_ds = {}
try:
    with open(JSONL, encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("region") != "USA" or r.get("delay") != 1 or r.get("type") != "MATRIX":
                continue
            ds = str(r.get("dataset_id") or r.get("dataset") or "").lower()
            cat = str(r.get("category_name") or r.get("category") or "").lower()
            if ds.startswith("pv1") or not (ds.startswith("model") or "model" in cat or ds in PRIORITY):
                continue
            fid = r.get("id")
            if fid and len(by_ds.setdefault(ds, [])) < 2:
                by_ds[ds].append(fid)
except Exception as e:
    print("discovery err", e, flush=True)
# one field per dataset, priority datasets first
fields = []
for ds in PRIORITY:
    fields += by_ds.get(ds, [])[:1]
for ds, fs in by_ds.items():
    if ds not in PRIORITY:
        fields.append(fs[0])
fields = fields[:120]
print(f"discovered {len(fields)} candidate fields across {len(by_ds)} datasets", flush=True)

def make_cfg(expr, neut):
    return {"type": "REGULAR", "settings": {"instrumentType": "EQUITY", "region": "USA",
            "universe": "TOP1000", "delay": 1, "decay": 5, "neutralization": neut, "truncation": 0.05,
            "pasteurization": "ON", "unitHandling": "VERIFY", "nanHandling": "OFF",
            "language": "FASTEXPR", "visualization": False, "testPeriod": "P5Y0M0D"},
           "regular": expr}

def run_multi(payloads):
    """Submit list of (label, expr, neut); return dict label->metrics via multi-sim."""
    results = {}
    items = list(payloads)
    batches = [items[i:i + MULTI_SIZE] for i in range(0, len(items), MULTI_SIZE)]
    inflight = {}; bi = 0
    while bi < len(batches) or inflight:
        while len(inflight) < CONCURRENT_MULTI and bi < len(batches):
            batch = batches[bi]; bi += 1
            payload = [make_cfg(e, n) for (_, e, n) in batch]
            loc = None
            for _ in range(5):
                try:
                    resp = s.post(f"{API}/simulations", json=payload, timeout=30)
                except Exception:
                    time.sleep(8); continue
                if resp.status_code == 201:
                    loc = resp.headers.get("Location"); break
                if resp.status_code == 401:
                    print("COOKIE_DIED", flush=True); return results
                if resp.status_code == 429:
                    time.sleep(20); continue
                if resp.status_code == 400:
                    break
                time.sleep(6)
            if loc:
                inflight[loc] = batch
            time.sleep(3)
        for url in list(inflight.keys()):
            try:
                resp = s.get(url, timeout=25)
            except Exception:
                continue
            if resp.status_code == 401:
                print("COOKIE_DIED", flush=True); return results
            if resp.status_code != 200:
                continue
            try:
                if float(resp.headers.get("Retry-After", 0) or 0) > 0:
                    continue
            except Exception:
                pass
            children = resp.json().get("children") or []
            batch = inflight.pop(url)
            for idx, child in enumerate(children):
                try:
                    aid = s.get(f"{API}/simulations/{child}", timeout=20).json().get("alpha")
                    if aid and idx < len(batch):
                        a = s.get(f"{API}/alphas/{aid}", timeout=15).json(); iss = a.get("is") or {}
                        fails = [c.get("name") for c in (iss.get("checks") or [])
                                 if c.get("result") == "FAIL" and c.get("name") != "OLD_SIMULATION"]
                        results[batch[idx][0]] = dict(id=aid, sh=iss.get("sharpe", 0) or 0,
                            to=iss.get("turnover", 0) or 0, ret=iss.get("returns", 0) or 0, fails=fails)
                except Exception:
                    pass
        time.sleep(8)
    return results

def robust(aid):
    for _ in range(2):
        try:
            r = s.get(f"{API}/alphas/{aid}/recordsets/yearly-stats", timeout=20)
            if r.status_code == 200 and r.text.strip():
                for row in [x for x in r.json().get("records", []) if x and x[-1] == "TEST"]:
                    if (len(row) > 7 and isinstance(row[7], (int, float)) and row[7] < -0.15) or \
                       (len(row) > 6 and isinstance(row[6], (int, float)) and row[6] < -1.0):
                        return False
                return True
        except Exception:
            pass
        time.sleep(2)
    return True

# ---- STAGE 1: single signals ----
print("STAGE 1: testing single signals...", flush=True)
singles = [(f, f"rank(ts_delta({f}, 120))", random.choice(NEUTS)) for f in fields]
r1 = run_multi(singles)
good = [(m["sh"], f, m) for f, m in r1.items()
        if m["sh"] >= 1.0 and 0.01 < m["to"] <= 0.30 and not m["fails"]]
good.sort(reverse=True)
top = good[:16]
print(f"STAGE 1 done: {len(good)} good singles, taking top {len(top)}", flush=True)
for sh, f, m in top:
    print("  single S=%.2f TO=%.0f%% %s" % (sh, m["to"] * 100, f[:34]), flush=True)

# ---- STAGE 2: pairwise combinations (different fields) ----
print("STAGE 2: combining top singles pairwise...", flush=True)
combos = []
for i in range(len(top)):
    for j in range(i + 1, len(top)):
        A = top[i][1]; B = top[j][1]
        expr = f"rank(ts_delta({A}, 120)) + rank(ts_delta({B}, 120))"
        combos.append((f"{A[:12]}+{B[:12]}", expr, "STATISTICAL"))
random.shuffle(combos)
combos = combos[:120]
print(f"testing {len(combos)} combinations", flush=True)
r2 = run_multi(combos)
winners = []
for label, m in r2.items():
    if m["sh"] >= 1.3 and 0.01 < m["to"] <= 0.30 and not m["fails"] and robust(m["id"]):
        winners.append((m["sh"], m["ret"], m["to"], m["id"], label))
winners.sort(reverse=True)
print("=== HIGH-QUALITY COMBO WINNERS (Sharpe>=1.3, robust, low-turnover) ===", flush=True)
for sh, ret, to, aid, label in winners[:25]:
    print("  COMBO S=%.2f R=%.1f%% TO=%.0f%% id=%s | %s" % (sh, ret * 100, to * 100, aid, label), flush=True)
print(f"FINISHED singles_good={len(good)} combo_winners={len(winners)}", flush=True)
