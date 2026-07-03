#!/usr/bin/env python3
"""Power-Pool-compliant overnight miner.

Builds a large Analyst+Fundamental queue from the consultant field pool
(streamed JSONL), forces Power Pool theme settings (TOP1000, delay=1,
rotating STATISTICAL/CROWDING/FAST/SLOW/SLOW_AND_FAST neutralizations),
keeps 8 simulations in flight, and reports hits (Sharpe>=1.5 & Fitness>=1.0).

At startup it fetches the account's recent alphas and skips any expression
already simulated, so restarts never waste quota.
"""
import sys, time, dataclasses, requests
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from official_docs_miner import WQClient, ParamVariant, API_BASE
from consultant_auto_miner import build_queue

NEUTS = ["STATISTICAL", "CROWDING", "FAST", "SLOW", "SLOW_AND_FAST"]  # PP theme-compliant
INFLIGHT = 8

c = WQClient(str(Path(__file__).resolve().parent / "credential_4.txt"))
assert c.authenticate(), "auth failed"

# Skip expressions already simulated on this account (no wasted quota on restart)
already: set[str] = set()
try:
    for off in range(0, 500, 100):
        r = c.sess.get(f"{API_BASE}/users/self/alphas?limit=100&offset={off}&order=-dateCreated&hidden=false", timeout=30)
        if r.status_code != 200:
            break
        res = r.json().get("results", [])
        for a in res:
            reg = a.get("regular")
            code = reg.get("code", "") if isinstance(reg, dict) else str(reg or "")
            if code:
                already.add(code.replace(" ", ""))
        if len(res) < 100:
            break
except Exception as e:
    print("prefetch err", str(e)[:100], flush=True)
print(f"prefetched {len(already)} existing expressions to skip", flush=True)

raw = []
for cat in ("Analyst", "Fundamental"):
    try:
        raw += build_queue(stage="probe", max_fields=250, include_official=False,
                           field_source="consultant", category_name=cat)
    except Exception as e:
        print("build_queue", cat, "err", e, flush=True)

jobs = []
seen: set[str] = set()
for i, (name, v) in enumerate(raw):
    key = v.expression.strip().replace(" ", "")
    if key in seen or key in already:
        continue
    seen.add(key)
    v2 = dataclasses.replace(v, universe="TOP1000", neutralization=NEUTS[i % len(NEUTS)], delay=1)
    jobs.append((name, v2))
print(f"THEME-COMPLIANT QUEUE: {len(jobs)} variants (TOP1000, delay1, PP-neutralizations)", flush=True)

inflight = {}
qi = 0
submitted = done = passed = 0
last_print = 0
while qi < len(jobs) or inflight:
    while len(inflight) < INFLIGHT and qi < len(jobs):
        name, v = jobs[qi]; qi += 1
        try:
            u = c.submit_simulation(v.expression, v)
        except Exception as e:
            print("submit err", str(e)[:80], flush=True); u = None
        if u:
            inflight[u] = (name, v); submitted += 1
        time.sleep(2)
    for url in list(inflight.keys()):
        try:
            r = c.sess.get(url, timeout=20)
        except Exception:
            continue
        if r.status_code == 401:
            print("COOKIE_EXPIRED_401 - stopping", flush=True)
            qi = len(jobs); inflight.clear(); break
        if r.status_code != 200:
            continue
        d = r.json()
        if "alpha" in d or d.get("status") == "ERROR":
            name, v = inflight.pop(url); done += 1
            aid = d.get("alpha"); aid = aid[0] if isinstance(aid, list) else aid
            if aid:
                try:
                    a = c.sess.get(f"{API_BASE}/alphas/{aid}", timeout=15).json()
                    iss = a.get("is") or {}
                    sh = iss.get("sharpe", 0) or 0; f = iss.get("fitness", 0) or 0
                    if f >= 1.0 and sh >= 1.5:
                        passed += 1
                        print("HIT S=%.2f F=%.2f TO=%.0f%% n=%s id=%s | %s" % (
                            sh, f, (iss.get("turnover", 0) or 0) * 100,
                            v.neutralization, aid, v.expression[:50]), flush=True)
                except Exception:
                    pass
    if done >= last_print + 20:
        last_print = done
        print(f"progress: submitted={submitted} done={done} hits={passed}", flush=True)
    time.sleep(8)
print(f"FINISHED submitted={submitted} done={done} hits={passed}", flush=True)
