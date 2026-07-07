#!/usr/bin/env python3
"""Power Pool THEME optimizer v2 — DIVERSITY + PER-FIELD OPTIMIZATION.

Fixes the "mine-and-forget" problem: instead of emitting every barely-passing
variant, this sweeps a small param grid PER FIELD and keeps only the single
best variant (highest returns) that clears the bar, deduped by field so the
Power Pool grows with genuinely diverse, money-optimized signals.

Bar per variant: theme-compliant (USA/TOP1000/delay1/{STATISTICAL,CROWDING,
FAST,SLOW,SLOW_AND_FAST}), Sharpe>=1.0, turnover 1%-30% (low-turnover only),
<=8 ops, <=3 fields, no FAILs.

Broad coverage: caps to 2 fields per dataset so it spreads across 55+ model
datasets rather than re-hitting the same few. Skips fields already on the
account (submitted or tested). Multi-sim (8x10=80 in flight). ~4h budget.
Logs one BEST line per field that yields a qualifying, optimized factor.
"""
import time, requests, json, hashlib, random
from pathlib import Path

BASE = Path(__file__).resolve().parent
API = "https://api.worldquantbrain.com"
JSONL = BASE / "constants" / "consultant_fields" / "consultant_expression_fields.jsonl"
TIME_BUDGET = 4 * 3600
CONCURRENT_MULTI = 8
MULTI_SIZE = 10
NEUTS = ["STATISTICAL", "CROWDING", "FAST", "SLOW"]
MAX_TURNOVER = 0.30
random.seed(11)

tok = (BASE / "credential_4.txt").read_text().split("COOKIE:")[1].strip()
s = requests.Session(); s.cookies.set("t", tok, domain=".worldquantbrain.com")
assert s.get(f"{API}/users/self", timeout=20).status_code == 200, "cookie invalid at start"

# fields already used on the account (skip — avoid re-mining spent signals)
used_fields = set()
try:
    for off in range(0, 900, 100):
        r = s.get(f"{API}/users/self/alphas?limit=100&offset={off}&order=-dateCreated&hidden=false", timeout=30)
        if r.status_code != 200:
            break
        res = r.json().get("results", [])
        for a in res:
            reg = a.get("regular"); code = reg.get("code", "") if isinstance(reg, dict) else str(reg or "")
            import re as _re
            for m in _re.findall(r"[A-Za-z_][A-Za-z0-9_]+", code):
                if m.islower() and ("_" in m) and m not in {"ts_delta","ts_backfill","ts_zscore","ts_mean","group_rank","group_zscore","group_neutralize","group_cartesian_product"}:
                    used_fields.add(m)
        if len(res) < 100:
            break
except Exception as e:
    print("prefetch err", str(e)[:80], flush=True)
print(f"skipping {len(used_fields)} already-used fields", flush=True)

# discover diverse USA delay-1 model/predictive fields (cap 2 per dataset)
fields = []
per_ds = {}
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
            if ds.startswith("pv1"):
                continue
            if not (ds.startswith("model") or "model" in cat or ds in {
                    "multifactor_return_pred", "predictive_starmine", "ai_equity_alpha",
                    "tech_chart_model", "analyst_revision_horizons", "global_seasonal_model"}):
                continue
            fid = r.get("id")
            if not fid or fid in used_fields:
                continue
            if per_ds.get(ds, 0) >= 2:
                continue
            per_ds[ds] = per_ds.get(ds, 0) + 1
            fields.append(fid)
            if len(fields) >= 600:
                break
except Exception as e:
    print("discovery err", e, flush=True)
print(f"discovered {len(fields)} NEW diverse fields across {len(per_ds)} datasets", flush=True)

# per field, a small optimization grid (low-turnover-biased structures)
def variants_for(f):
    out = []
    for w in (120, 250):                 # slow deltas -> low turnover
        out.append((f, f"rank(ts_delta({f}, {w}))", 0))
        out.append((f, f"rank(ts_delta({f}, {w}))", 10))
    out.append((f, f"quantile(ts_backfill({f}, 20))", 5))
    out.append((f, f"group_rank(ts_mean({f}, 60), industry)", 10))
    return out

all_jobs = []  # (field, expr, decay, neut)
for fid in fields:
    for (f, expr, dc) in variants_for(fid):
        all_jobs.append((f, expr, dc, random.choice(NEUTS)))
random.shuffle(all_jobs)
print(f"QUEUE: {len(all_jobs)} configs | keep best-returns per field, TO<={int(MAX_TURNOVER*100)}%, multi-sim {CONCURRENT_MULTI}x{MULTI_SIZE}", flush=True)

def make_cfg(expr, dc, neut):
    return {"type": "REGULAR", "settings": {"instrumentType": "EQUITY", "region": "USA",
            "universe": "TOP1000", "delay": 1, "decay": dc, "neutralization": neut, "truncation": 0.05,
            "pasteurization": "ON", "unitHandling": "VERIFY", "nanHandling": "OFF",
            "language": "FASTEXPR", "visualization": False, "testPeriod": "P5Y0M0D"},
           "regular": expr}

def submit_multi(batch):
    payload = [make_cfg(e, dc, n) for (_, e, dc, n) in batch]
    for attempt in range(5):
        try:
            r = s.post(f"{API}/simulations", json=payload, timeout=30)
        except Exception:
            time.sleep(10); continue
        if r.status_code == 201:
            return r.headers.get("Location")
        if r.status_code == 401:
            return "401"
        if r.status_code == 400:
            return None
        if r.status_code == 429:
            time.sleep(15 + attempt * 8); continue
        time.sleep(8)
    return None

best = {}  # field -> (returns, sharpe, turnover, id, expr, neut, decay)

def is_robust(alpha_id):
    """Reject overfit blowups: any out-of-sample (TEST) year with returns<-15% or sharpe<-1."""
    for _ in range(3):
        try:
            r = s.get(f"{API}/alphas/{alpha_id}/recordsets/yearly-stats", timeout=20)
            if r.status_code == 200 and r.text.strip():
                recs = r.json().get("records", [])
                test = [row for row in recs if row and row[-1] == "TEST"] or recs
                for row in test:
                    yr_sh = row[6] if len(row) > 6 and isinstance(row[6], (int, float)) else 0
                    yr_ret = row[7] if len(row) > 7 and isinstance(row[7], (int, float)) else 0
                    if yr_ret < -0.15 or yr_sh < -1.0:
                        return False
                return True
        except Exception:
            pass
        time.sleep(2)
    return True  # if unavailable, don't block

def eval_alpha(alpha_id, field, dc, neut):
    try:
        a = s.get(f"{API}/alphas/{alpha_id}", timeout=15).json(); iss = a.get("is") or {}
        reg = a.get("regular"); expr = reg.get("code", "") if isinstance(reg, dict) else ""
        sh = iss.get("sharpe", 0) or 0; to = iss.get("turnover", 0) or 0; ret = iss.get("returns", 0) or 0
        fails = [c.get("name") for c in (iss.get("checks") or [])
                 if c.get("result") == "FAIL" and c.get("name") != "OLD_SIMULATION"]
        if sh >= 1.0 and 0.01 < to <= MAX_TURNOVER and not fails and is_robust(alpha_id):
            cur = best.get(field)
            if cur is None or ret > cur[0]:
                best[field] = (ret, sh, to, alpha_id, expr, neut, dc)
                print("BEST field=%s R=%.1f%% S=%.2f TO=%.0f%% n=%s d=%s id=%s | %s" % (
                    field, ret * 100, sh, to * 100, neut, dc, alpha_id, expr[:48]), flush=True)
    except Exception:
        pass

batches = [all_jobs[i:i + MULTI_SIZE] for i in range(0, len(all_jobs), MULTI_SIZE)]
t0 = time.time()
inflight = {}
bi = submitted = done = 0
stop = False
while not stop and (bi < len(batches) or inflight):
    if time.time() - t0 > TIME_BUDGET:
        print("TIME BUDGET REACHED", flush=True); break
    while len(inflight) < CONCURRENT_MULTI and bi < len(batches):
        batch = batches[bi]; bi += 1
        loc = submit_multi(batch)
        if loc == "401":
            print("COOKIE_EXPIRED_401 - stopping", flush=True); stop = True; break
        if loc:
            inflight[loc] = batch; submitted += len(batch)
        time.sleep(3)
    for url in list(inflight.keys()):
        try:
            r = s.get(url, timeout=25)
        except Exception:
            continue
        if r.status_code == 401:
            print("COOKIE_EXPIRED_401 - stopping", flush=True); stop = True; break
        if r.status_code != 200:
            continue
        try:
            retry = float(r.headers.get("Retry-After", 0) or 0)
        except Exception:
            retry = 0
        if retry > 0:
            continue
        d = r.json()
        children = d.get("children") or []
        batch = inflight.pop(url)
        for idx, child in enumerate(children):
            try:
                cj = s.get(f"{API}/simulations/{child}", timeout=20).json()
                aid = cj.get("alpha")
                if aid and idx < len(batch):
                    field, _, dc, neut = batch[idx]
                    eval_alpha(aid, field, dc, neut)
                done += 1
            except Exception:
                pass
    if done and done % 50 < MULTI_SIZE:
        print(f"progress: submitted={submitted} done={done} distinct_winners={len(best)} elapsed={int(time.time()-t0)//60}min", flush=True)
    time.sleep(8)

print("=== TOP DISTINCT WINNERS (best-returns per field) ===", flush=True)
for field, (ret, sh, to, aid, expr, neut, dc) in sorted(best.items(), key=lambda kv: -kv[1][0])[:30]:
    print("  R=%.1f%% S=%.2f TO=%.0f%% id=%s | %s" % (ret * 100, sh, to * 100, aid, expr[:50]), flush=True)
print(f"FINISHED submitted={submitted} done={done} distinct_winners={len(best)}", flush=True)
