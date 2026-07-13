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

Do not introduce arbitrary epsilon denominators into new fundamental templates.
For quarterly event data, use quarterly state holding (`63`) and economically
matched denominators.

## Submission Policy

- `pp_autosubmit.py` is intentionally strict: it only submits platform-labeled
  `POWER_POOL_ELIGIBLE` candidates.
- `submit_authorized_batch.py` handles an explicit user-approved list, records
  every response, and stops on HTTP 429. It is not a bypass for platform checks.
- Previous successful manual-batch API submissions were `XgnWrL6m`,
  `MPQ1WXor`, and `rKl53Lvd` (HTTP 201). A later request hit platform throttling.
- Never retry HTTP 429 in a loop.

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
