#!/usr/bin/env python3
"""Power Pool THEME optimizer for the current week (USA D1 theme) — MULTI-SIM.
Theme = region=USA, delay=1, universe=TOP1000, neutralization in
{STATISTICAL, CROWDING, FAST, SLOW, SLOW_AND_FAST}, datasets NOT pv1.

Uses official ACE multi-simulation: POST /simulations with a list of up to 10
configs; the parent returns `children`; each child yields an `alpha`. Keeps 8
multi-sims (=up to 80 sims) in flight for ~10x throughput vs single sims.

Targets USA model/predictive/technical datasets (orthogonal to risk factors),
the only kind that can keep Sharpe>=1.0 under risk-model neutralization.
Simple PP-eligible expressions (<=8 ops, <=3 fields), hash-dedup, skip
already-simulated, ~4h. Logs HITs (Sharpe>=1.0, theme-compliant, no fails).
Path-agnostic: works on Windows (local) and Linux (VPS).
"""
import time, requests, json, hashlib, random
from pathlib import Path

BASE = Path(__file__).resolve().parent
API = "https://api.worldquantbrain.com"
JSONL = BASE / "constants" / "consultant_fields" / "consultant_expression_fields.jsonl"
TIME_BUDGET = 4 * 3600
CONCURRENT_MULTI = 8   # concurrent multi-sims (1..8)
MULTI_SIZE = 10        # alphas per multi-sim (2..10)
NEUTS = ["STATISTICAL", "CROWDING", "FAST", "SLOW", "SLOW_AND_FAST"]
DECAY = [0, 5, 10]
random.seed(7)

tok = (BASE / "credential_4.txt").read_text().split("COOKIE:")[1].strip()
s = requests.Session(); s.cookies.set("t", tok, domain=".worldquantbrain.com")
assert s.get(f"{API}/users/self", timeout=20).status_code == 200, "cookie invalid at start"

# ---- discover USA delay-1 MATRIX fields from model/predictive datasets (not pv1) ----
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
            fields.append(fid)
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
for fid in fields:
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
print(f"QUEUE: {len(jobs)} theme-compliant configs | multi-sim {CONCURRENT_MULTI}x{MULTI_SIZE}=up to {CONCURRENT_MULTI*MULTI_SIZE} in flight | budget 4h", flush=True)

def make_cfg(expr, n, dc):
    return {"type": "REGULAR", "settings": {"instrumentType": "EQUITY", "region": "USA",
            "universe": "TOP1000", "delay": 1, "decay": dc, "neutralization": n, "truncation": 0.05,
            "pasteurization": "ON", "unitHandling": "VERIFY", "nanHandling": "OFF",
            "language": "FASTEXPR", "visualization": False, "testPeriod": "P5Y0M0D"},
           "regular": expr}

def submit_multi(batch):
    payload = [make_cfg(e, n, dc) for (e, n, dc) in batch]
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

def eval_alpha(alpha_id):
    global hits
    try:
        a = s.get(f"{API}/alphas/{alpha_id}", timeout=15).json(); iss = a.get("is") or {}
        st = a.get("settings") or {}
        reg = a.get("regular"); expr = reg.get("code", "") if isinstance(reg, dict) else str(reg or "")
        sh = iss.get("sharpe", 0) or 0; fi = iss.get("fitness", 0) or 0
        fails = [c.get("name") for c in (iss.get("checks") or [])
                 if c.get("result") == "FAIL" and c.get("name") != "OLD_SIMULATION"]
        if sh >= 1.0 and not fails:
            hits += 1
            print("HIT S=%.2f F=%.2f TO=%.0f%% n=%s d=%s id=%s | %s" % (
                sh, fi, (iss.get("turnover", 0) or 0) * 100, st.get("neutralization"), st.get("decay"), alpha_id, expr[:55]), flush=True)
        elif sh >= 1.0:
            print("near S=%.2f n=%s fails=%s | %s" % (sh, st.get("neutralization"), ",".join(fails[:2]), expr[:45]), flush=True)
    except Exception:
        pass

# batch jobs into multi-sims of MULTI_SIZE
batches = [jobs[i:i + MULTI_SIZE] for i in range(0, len(jobs), MULTI_SIZE)]
t0 = time.time()
inflight = {}   # multi_url -> batch(list of (expr,n,dc))
bi = submitted = done_children = hits = 0
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
            continue  # parent still running
        d = r.json()
        children = d.get("children") or []
        batch = inflight.pop(url)
        # map each child -> its job via child's own alpha; children order follows submit order
        for child in children:
            try:
                cj = s.get(f"{API}/simulations/{child}", timeout=20).json()
                aid = cj.get("alpha")
                if aid:
                    eval_alpha(aid)
                done_children += 1
            except Exception:
                pass
    if done_children and done_children % 40 < MULTI_SIZE:
        print(f"progress: submitted={submitted} done={done_children} hits={hits} inflight={len(inflight)} elapsed={int(time.time()-t0)//60}min", flush=True)
    time.sleep(8)
print(f"FINISHED submitted={submitted} done_children={done_children} hits={hits} elapsed={int(time.time()-t0)//60}min", flush=True)
