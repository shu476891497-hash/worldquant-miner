#!/usr/bin/env python3
"""Power Pool THEME optimizer for the current week (USA D1 theme).
Theme = region=USA, delay=1, universe=TOP1000, neutralization in
{STATISTICAL, CROWDING, FAST, SLOW, SLOW_AND_FAST}, datasets NOT pv1.

Fundamental/analyst signals die under risk-model neutralization, so this
targets USA model/predictive/technical datasets (orthogonal to risk factors),
which are the only kind that can keep Sharpe>=1.0 under these neutralizations.
Simple PP-eligible expressions (<=8 ops, <=3 fields), 8 in flight, hash-dedup,
skip already-simulated, ~4h. Logs HITs (Sharpe>=1.0, theme-compliant, no fails).

Path-agnostic: works on Windows (local) and Linux (VPS). Reads credential_4.txt
and the streamed JSONL field pool from its own directory.
"""
import time, requests, json, hashlib, random
from pathlib import Path

BASE = Path(__file__).resolve().parent
API = "https://api.worldquantbrain.com"
JSONL = BASE / "constants" / "consultant_fields" / "consultant_expression_fields.jsonl"
TIME_BUDGET = 4 * 3600
INFLIGHT = 8
NEUTS = ["STATISTICAL", "CROWDING", "FAST", "SLOW", "SLOW_AND_FAST"]  # theme-compliant
DECAY = [0, 5, 10]
random.seed(7)

tok = (BASE / "credential_4.txt").read_text().split("COOKIE:")[1].strip()
s = requests.Session(); s.cookies.set("t", tok, domain=".worldquantbrain.com")
assert s.get(f"{API}/users/self", timeout=20).status_code == 200, "cookie invalid at start"

fields = []
seen_ds_count = {}
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
            if not fid:
                continue
            if seen_ds_count.get(ds, 0) >= 6:
                continue
            seen_ds_count[ds] = seen_ds_count.get(ds, 0) + 1
            fields.append((fid, ds))
            if len(fields) >= 400:
                break
except Exception as e:
    print("field discovery err", e, flush=True)
print(f"discovered {len(fields)} USA model/predictive fields across {len(seen_ds_count)} datasets", flush=True)

def structs(f):
    return [
        f"group_rank(ts_backfill({f}, 20), industry)",
        f"group_rank(ts_zscore({f}, 60), industry)",
        f"rank(ts_delta({f}, 120))",
        f"group_rank(ts_mean({f}, 20), subindustry)",
        f"quantile(ts_backfill({f}, 20))",
    ]

variants = []
for fid, ds in fields:
    variants.extend(structs(fid))
random.shuffle(variants)

jobs = []
seen_cfg = set()
for expr in variants:
    for n in NEUTS:
        for dc in DECAY:
            key = hashlib.sha256(f"{expr}|{n}|{dc}".encode()).hexdigest()
            if key in seen_cfg:
                continue
            seen_cfg.add(key)
            jobs.append((expr, n, dc))
random.shuffle(jobs)

already = set()
try:
    for off in range(0, 500, 100):
        r = s.get(f"{API}/users/self/alphas?limit=100&offset={off}&order=-dateCreated&hidden=false", timeout=30)
        if r.status_code != 200:
            break
        res = r.json().get("results", [])
        for a in res:
            reg = a.get("regular"); code = reg.get("code", "") if isinstance(reg, dict) else str(reg or "")
            st = a.get("settings") or {}
            if code:
                already.add(f"{code.replace(' ', '')}|{st.get('neutralization')}|{st.get('decay')}")
        if len(res) < 100:
            break
except Exception as e:
    print("prefetch err", str(e)[:80], flush=True)
jobs = [j for j in jobs if f"{j[0].replace(' ', '')}|{j[1]}|{j[2]}" not in already]
print(f"QUEUE: {len(jobs)} theme-compliant configs (USA/TOP1000/special-neut) | budget 4h", flush=True)

def submit(expr, n, dc):
    cfg = {"type": "REGULAR", "settings": {"instrumentType": "EQUITY", "region": "USA",
            "universe": "TOP1000", "delay": 1, "decay": dc, "neutralization": n, "truncation": 0.05,
            "pasteurization": "ON", "unitHandling": "VERIFY", "nanHandling": "OFF",
            "language": "FASTEXPR", "visualization": False, "testPeriod": "P5Y0M0D"},
           "regular": expr}
    for attempt in range(5):
        try:
            r = s.post(f"{API}/simulations", json=cfg, timeout=30)
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

t0 = time.time()
inflight = {}
qi = submitted = done = hits = 0
stop = False
while not stop and (qi < len(jobs) or inflight):
    if time.time() - t0 > TIME_BUDGET:
        print("TIME BUDGET REACHED", flush=True); break
    while len(inflight) < INFLIGHT and qi < len(jobs):
        expr, n, dc = jobs[qi]; qi += 1
        loc = submit(expr, n, dc)
        if loc == "401":
            print("COOKIE_EXPIRED_401 - stopping", flush=True); stop = True; break
        if loc:
            inflight[loc] = (expr, n, dc); submitted += 1
        time.sleep(2)
    for url in list(inflight.keys()):
        try:
            r = s.get(url, timeout=20)
        except Exception:
            continue
        if r.status_code == 401:
            print("COOKIE_EXPIRED_401 - stopping", flush=True); stop = True; break
        if r.status_code != 200:
            continue
        d = r.json()
        if "alpha" in d or d.get("status") == "ERROR":
            expr, n, dc = inflight.pop(url); done += 1
            aid = d.get("alpha"); aid = aid[0] if isinstance(aid, list) else aid
            if aid:
                try:
                    a = s.get(f"{API}/alphas/{aid}", timeout=15).json(); iss = a.get("is") or {}
                    sh = iss.get("sharpe", 0) or 0; fi = iss.get("fitness", 0) or 0
                    fails = [c.get("name") for c in (iss.get("checks") or [])
                             if c.get("result") == "FAIL" and c.get("name") != "OLD_SIMULATION"]
                    if sh >= 1.0 and not fails:
                        hits += 1
                        print("HIT S=%.2f F=%.2f TO=%.0f%% n=%s d=%s id=%s | %s" % (
                            sh, fi, (iss.get("turnover", 0) or 0) * 100, n, dc, aid, expr[:55]), flush=True)
                    elif sh >= 1.0:
                        print("near S=%.2f n=%s fails=%s | %s" % (sh, n, ",".join(fails[:2]), expr[:45]), flush=True)
                except Exception:
                    pass
    if done and done % 25 == 0:
        print(f"progress: submitted={submitted} done={done} hits={hits} elapsed={int(time.time()-t0)//60}min", flush=True)
    time.sleep(8)
print(f"FINISHED submitted={submitted} done={done} hits={hits} elapsed={int(time.time()-t0)//60}min", flush=True)
