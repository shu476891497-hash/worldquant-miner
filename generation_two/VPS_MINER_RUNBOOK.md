# VPS Miner Runbook

This note records the failure modes found while operating the WorldQuant miner
on the Tencent VPS. Read it before starting, stopping, or diagnosing a run.

## VPS target

- Host: Tencent VPS (Ubuntu)
- Working tree: `/root/worldquant-miner/generation_two`
- Miner: `official_docs_miner.py`
- Logs: `/root/worldquant-miner/generation_two/logs/`

## Credential contract

`official_docs_miner.py` reads `credential_4.txt` as **two lines**:

```text
<email>
COOKIE:<JWT>
```

A one-line `COOKIE:<JWT>` file is invalid. It produces the message
`credential format error (requires 2 lines)` and the infinite miner merely
waits and retries; it does not simulate anything. Before starting a long run,
verify the cookie against `GET /users/self` from the same VPS.

## Safe lifecycle

1. Stop existing miner processes in a **separate** remote command.
2. In a new remote command, start the replacement process.
3. Verify PID, command line, latest log, and a successful authentication line.

Never put `pkill -f official_docs_miner.py` in the same shell command whose
text also contains `official_docs_miner.py`: `pkill` can match that shell's
own command line and terminate the launcher before `nohup` starts.

## Verified model-category command

```bash
cd /root/worldquant-miner/generation_two
mkdir -p logs
STAMP=$(date +%Y%m%d_%H%M%S)
nohup timeout 4h env PYTHONUNBUFFERED=1 \
  python3 -u official_docs_miner.py \
  --infinite --rounds 2 --templates-per-round 10 --variants 3 \
  --max-concurrent 3 --category model --delay-between 12 \
  > "logs/official_model_4h_${STAMP}.log" 2>&1 < /dev/null &
```

## Minimum health check

```bash
ps -ef | grep '[o]fficial_docs_miner.py'
LOG=$(ls -t logs/official_model_4h_*.log | head -1)
tail -n 60 "$LOG"
```

Healthy means the `timeout` parent and Python child are both present, the log
is growing, authentication succeeded, and simulation batches appear. A single
`unknown variable` means that one template is unavailable in the selected
scope; it is not an authentication failure. Record and remove repeatedly
invalid template fields rather than restarting the whole miner.

## Submission policy

- The strict `pp_autosubmit.py` path is intentionally limited to platform
  `POWER_POOL_ELIGIBLE` alphas.
- A POST response of HTTP `201` means only `REQUEST_ACCEPTED`; it is not pool
  entry. The authoritative confirmation is `GET /alphas/<id>` returning
  `status == ACTIVE`.
- Submit only candidates already marked `POWER_POOL_ELIGIBLE`, one request at
  a time. Persist `REQUEST_ACCEPTED` so an in-progress alpha is never posted
  again. Poll its status rather than submitting more copies.
- Stop immediately on HTTP `429` (`THROTTLED`). Do not retry a throttled
  request in a loop.
