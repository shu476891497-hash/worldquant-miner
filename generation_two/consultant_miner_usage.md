# Consultant Auto Miner Usage

This file documents the consultant-grade miner added for the WorldQuant consultant workflow.

## Files

- `consultant_tips_summary.md`
  - Human-readable summary of the consultant tips document.
- `consultant_auto_miner.py`
  - Quota-aware, hash-deduplicated staged alpha miner.
- `constants/consultant_simulation_cache.json`
  - Full simulation-config hash cache created when simulations are submitted.
- `consultant_miner_results.json`
  - Results written by the consultant miner.
- `logs/consultant_auto_miner.log`
  - Run log.

## Credential Format

The repo's cookie workflow must use:

```text
anonymous
COOKIE:<jwt>
```

The second line must start with exactly one `COOKIE:` prefix.

## Dry Run First

Use dry-run to inspect the queue without consuming simulations:

```bash
python consultant_auto_miner.py --dry-run --stage probe --field-source earnings --max-fields 12 --max-variants 30
```

Useful field sources:

```bash
--field-source earnings
--field-source general
--field-source all
```

By default, earnings4 auto-generated variants only use `ern4_*` ids because those
match BRAIN Fast Expression autocomplete and the official examples. Some cached
03/2026 earnings rows use Data-page display ids; try them only when you are
intentionally exploring raw dataset ids:

```bash
python consultant_auto_miner.py --dry-run --field-source earnings --allow-raw-earnings-fields
```

## Staged Mining

Consultant docs recommend testing a small search space before expanding. Suggested sequence:

```bash
python consultant_auto_miner.py --stage probe --field-source earnings --max-fields 12 --max-variants 30 --batch-size 3 --quota-reserve 1000
```

If a family shows signal:

```bash
python consultant_auto_miner.py --stage refine --field-source earnings --max-fields 20 --max-variants 60 --batch-size 3 --quota-reserve 1000
```

For larger exploitation:

```bash
python consultant_auto_miner.py --stage exploit --field-source all --max-fields 30 --max-variants 120 --batch-size 3 --quota-reserve 1000
```

## Investability Check

Run a smaller MaxTrade ON pass for promising families:

```bash
python consultant_auto_miner.py --stage probe --field-source earnings --max-fields 8 --max-variants 20 --max-trade ON --batch-size 2
```

## Diagnostics

Fetch one alpha's metrics/checks:

```bash
python consultant_auto_miner.py --inspect-alpha <alpha_id>
```

Fetch one alpha plus recordsets:

```bash
python consultant_auto_miner.py --inspect-alpha <alpha_id> --fetch-recordsets
```

Fetch consultant diversity breakdown:

```bash
python consultant_auto_miner.py --diversity
```

The diversity JSON is saved to:

```text
logs/consultant_diversity.json
```

## What Makes It Consultant-Grade

- Reads simulation quota headers:
  - `X-Ratelimit-Limit`
  - `X-Ratelimit-Remaining`
  - `X-Ratelimit-Reset`
- Stops before the quota reserve is breached.
- Hashes the full simulation config, not just the expression.
- Starts with meaningful probe queues instead of huge parameter sweeps.
- Scores data fields using coverage, date coverage, alpha/user count, and description keywords.
- Marks result descriptions with:
  - consultant D0/D1 core threshold status
  - Power Pool shape status: operator count and field count
- Can fetch capitalization/PnL recordsets for promising alphas.

## Current Limitations

- Multi-Simulation API is summarized but not yet implemented because the exact production payload shape can vary; the current miner uses concurrent regular simulations.
- SuperAlpha construction is summarized but not yet automated.
- Python Alpha translation is summarized but not yet automated.
