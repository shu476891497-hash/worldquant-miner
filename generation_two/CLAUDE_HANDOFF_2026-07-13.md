# WorldQuant Miner Handoff - 2026-07-13

## Objective

Mine new USA alpha candidates efficiently, preserve account-level simulation
capacity, and submit only when the platform's current checks allow it.

## Current VPS State

- Host: Tencent VPS, working tree `/root/worldquant-miner/generation_two`.
- Authentication: the current cookie was refreshed and verified from the VPS
  with `GET /users/self` returning HTTP 200.
- Credential file format is mandatory:

  ```text
  <email>
  COOKIE:<JWT>
  ```

- A separate official miner process exists with default `max_concurrent=1`.
  Do not kill it without confirming ownership.
- Account-wide simulation capacity is 3. Any miner started by Codex should use
  `--max-concurrent 2` while that separate process exists.

## Mining Efficiency Rules

1. Query the remote historical cache before choosing a category. Do not run a
   category with no untested variants.
2. The remote cache showed: `earnings=0` untested variants, while
   `fundamental=239`, `option=14`, `pv=29`, `news=15`, and `analyst=1` at the
   last audit. Earnings must not be run again until new earnings templates are
   added.
3. Use a four-hour bounded `nohup timeout 4h` process and verify both the PID
   and log after startup.
4. Stop only the miner process that Codex launched; never use broad `pkill`
   when another miner may be owned by the user.
5. Treat platform errors as template evidence. Remove or repair a repeatedly
   invalid expression instead of letting infinite mode repeat it.

## FND6 Event Vector Rule

`fnd6_newqeventv110_*` fields are event vectors. They cannot be supplied
directly to `ts_zscore`. The quarterly-safe form is:

```text
ts_zscore(ts_backfill(vec_avg(field), 63), 252)
```

Two official templates were corrected accordingly:

- `fnd6_liability_fair_value_mix` (`lol2q`)
- `fnd6_level3_liability_risk` (`lul3q`)

The same event-vector audit also corrected direct FND6 event usages in
`pnciaq`, `rcaq`, `gdwlipq`, `invfgq`, `invwipq`, and the `lltq` denominator
inside the debt-due template. Do a static scan for
`fnd6_newqeventv110_` without `vec_avg(` before launching any new sweep.
The older `fnd6_eventv110_dd1q` field is also a vector and must be reduced
with `vec_avg` before it is used in a ratio.
This applies to all FND6 field names containing `eventv110`, including
`fnd6_cptnewqeventv110_rectq`; scan the generic substring, not just one
prefix family.

Do not introduce arbitrary epsilon denominators into new fundamental templates.
For quarterly event data, use quarterly state holding (`63`) and economically
matched denominators.

## Submission Policy

- `pp_autosubmit.py` is intentionally strict: it only submits platform-labeled
  `POWER_POOL_ELIGIBLE` candidates. This is the Power Pool fast-path policy,
  not a universal prerequisite for every Regular alpha submission.
- Evaluate GLB Regular candidates separately from Power Pool candidates. A GLB
  Regular alpha can be worth submitting when its static Regular checks pass
  (total Sharpe, fitness, three regional Sharpes, turnover, concentration,
  sub-universe Sharpe, and 2Y Sharpe), even before it has a
  `POWER_POOL_ELIGIBLE` classification. Correlation and Regular submission
  checks may remain `PENDING` until a submission request starts server-side
  evaluation.
- Do not use `submit_authorized_batch.py` for normal operation. Use
  `pp_autosubmit.py`, which filters for `POWER_POOL_ELIGIBLE` and now polls
  until the authoritative status is `ACTIVE`.
- HTTP 201 from `/submit` means only `REQUEST_ACCEPTED`, not successful entry.
  Never describe an alpha as submitted into the pool until a subsequent
  `GET /alphas/<id>` returns `status == ACTIVE`.
- Historical POST requests for `XgnWrL6m`, `MPQ1WXor`, `rKl53Lvd`,
  `2rLO8v8P`, `vRlkw5wd`, and `WjGP1NkO` returned HTTP 201, but their final
  ACTIVE/PENDING states were not verified before the account hit 429/401.
- Never retry HTTP 429 in a loop.

### GLB audit on 2026-07-13

- `GET /users/self/alphas?settings.region=GLB` returned 8 existing GLB alphas
  before the targeted rescue produced a ninth alpha.
- `blqGvzPr` and `RR8jdzGb` passed every available static GLB Regular quality
  threshold, including 2Y Sharpe. One submit request was sent for each; both
  returned HTTP 201 but remained `UNSUBMITTED` with server checks `PENDING` at
  the last poll. They are not yet confirmed `ACTIVE`.
- `KP9lkrE8` is promising but not Regular-ready: fitness is 0.91 and 2Y Sharpe
  is -0.04. Its static total and regional Sharpe checks pass.

## Current Candidate Audit

The following high-metric historical IDs are not immediately submit-ready:

| ID | State | Blocking reason |
| --- | --- | --- |
| `JjdrdA7e` | UNSUBMITTED | `LOW_SUB_UNIVERSE_SHARPE` and `OLD_SIMULATION` fail |
| `d5QGPvQw` | UNSUBMITTED | `OLD_SIMULATION` fail |
| `A13QjkOl` | UNSUBMITTED | low Sharpe warning and `OLD_SIMULATION` fail |
| `d5QG6XdY` | UNSUBMITTED | low Sharpe warning and `OLD_SIMULATION` fail |
| `Jjd92zvx` | UNSUBMITTED | low Sharpe warning and `OLD_SIMULATION` fail |
| `kqKAYQLL` | UNSUBMITTED | low Sharpe warning and `OLD_SIMULATION` fail |
| `P01VrbAJ` | UNSUBMITTED | `OLD_SIMULATION` fail |
| `omYNR2gm` | UNSUBMITTED | `OLD_SIMULATION` fail |
| `e7rEOOmz` | ACTIVE | already submitted/active |

`OLD_SIMULATION` means rerun the expression before attempting submission; do
not post stale IDs and expect the platform to accept them.

## Useful Files

- `official_docs_miner.py`: official template miner.
- `VPS_MINER_RUNBOOK.md`: credential and VPS lifecycle rules.
- `FACTOR_QUALITY_UPGRADE.md`: PP quality-gate design.
- `pp_usa_combo.py`: correlation-aware two-signal miner.
- `pp_autosubmit.py`: strict PP-only submission guard.
- `submit_authorized_batch.py`: explicit-ID, audit-recorded submission tool.
- `pp_glb_high_turnover.py`: GLB/TOP3000/D1/Country-neutral high-turnover
  probe. It uses one GLB simulation at a time (two account slots), records
  `MATCHES_THEMES`, and never submits alphas.
