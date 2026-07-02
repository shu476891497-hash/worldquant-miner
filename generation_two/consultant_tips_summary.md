# WorldQuant Consultant Tips Summary

Source: `C:\Users\22637\OneDrive\Worldquant\full consultant tips by worldquant.txt`

## API And Automation Details

- Authentication:
  - `POST https://api.worldquantbrain.com/authentication` with basic auth returns a JWT.
  - If biometrics/persona is enabled, `401` includes `WWW-Authenticate: persona` and a `Location` URL that must be completed in a browser.
  - For this repo's cookie workflow, `credential_4.txt` must be two lines: an arbitrary user label, then `COOKIE:<jwt>`.

- Simulation:
  - `POST /simulations` accepts `type`, `settings`, and `regular` expression.
  - The `Location` response header is the progress URL.
  - `GET <progress_url>` should obey the `Retry-After` header. When finished, the JSON contains `alpha`.
  - After completion, fetch `GET /alphas/<alpha_id>` for IS metrics and checks.

- Rate limit / simulation quota:
  - Successful simulations count toward daily quota, including duplicate alphas and child simulations in multi-simulations.
  - Response headers on simulation POST:
    - `X-Ratelimit-Limit`
    - `X-Ratelimit-Remaining`
    - `X-Ratelimit-Reset`
  - A consultant miner should stop or sleep when remaining simulations approach a reserve threshold instead of blindly submitting.

- Recordsets:
  - `GET /alphas/<alpha_id>/recordsets` lists available recordsets.
  - `GET /alphas/<alpha_id>/recordsets/<name>` retrieves detail.
  - Useful recordsets include PnL, Sharpe by capitalization, PnL by capitalization, and average size by capitalization.

- Diversity endpoint:
  - `GET /users/<userid>/activities/diversity?grouping=region,delay,dataCategory`
  - Useful for monitoring region/delay/category concentration.

## Research Rules From The Consultant Docs

- Start with a narrow search space: run roughly 10-50 simulations to test an idea before sweeping full parameter grids.
- Avoid duplicate simulations with a local hash of the full alpha configuration, not just expression text.
- Data field selection:
  - Prefer fields with sufficient coverage and date coverage.
  - Avoid identifiers, timestamps, dates, ISIN/CUSIP/symbol-like fields.
  - Use alpha count/user count as crowding clues; low usage can indicate underexplored fields.
  - Select one representative from similar fields first, then substitute similar fields after a signal appears.
- Operator selection:
  - Test one operator family member initially, then swap within the family if signal exists.
  - Families include aggregation (`ts_mean`, `ts_median`, `ts_sum`), delta/zscore (`ts_delta`, `ts_av_diff`, `ts_zscore`), and group operators (`group_rank`, `group_zscore`).
- Parameter selection:
  - Fast signals: 5, 10, 21 days.
  - Slow signals: 63, 121, 252 days.
  - Do not brute-force too many lookbacks before a base signal is proven.
- Neutralization:
  - Single country: market can be a first baseline.
  - Industry/subindustry/sector refine industry-specific signals.
  - Risk neutralizations like SLOW, FAST, CROWDING, REVERSION_AND_MOMENTUM are related to SLOW_AND_FAST; STATISTICAL is separate.
- Good automation practice:
  - Automation should cut redundant work, not invent nonsense.
  - Expressions still need financial sense.
  - Normalize fields to remove firm-size bias when comparing cross-sectionally.
  - Avoid adding noise just to lower production correlation.
  - Avoid overfitting via too many parameters or too many fields.

## Consultant Submission/Diagnostic Rules

- Review extra simulation views:
  - Risk-handled performance, including SLOW_AND_FAST neutralization.
  - Investability-constrained performance with MaxTrade ON.
- Consultant-only simulation features:
  - Multi-Simulation can test multiple alpha variations faster. A consultant can run up to 8 simultaneous Multi-Simulations, each with up to 10 sequential alphas.
  - All alphas inside a single Multi-Simulation must share region, delay, language, and instrument type.
  - Use names for alphas in a batch so results remain traceable.
  - If resources are unavailable, reduce the number of alphas per Multi-Simulation.
  - Test Period can isolate the last 0-6 years of IS as a validation period.
- Consultant-only settings:
  - Pasteurize controls whether values outside the alpha universe are set to NaN.
  - NaNHandling controls how missing data is treated.
  - MaxTrade validates investability by constraining per-step position changes.
  - MaxPosition constrains maximum position sizes.
- Consultant submission thresholds outside CHN:
  - Fitness: greater than 1.5 for Delay 0 and greater than 1 for Delay 1.
  - Sharpe: greater than 2.69 for Delay 0 and greater than 1.58 for Delay 1.
  - Turnover: greater than 1% and less than 70%.
  - Self-correlation: below 0.7, or Sharpe at least 10% greater than the correlated alpha.
  - Prod-correlation: similar criterion but against the full production alpha pool, not only the user's pool.
  - Weight: maximum stock weight must stay below the relevant threshold.
  - Subuniverse and IS ladder tests are core failure modes to diagnose.
- Failure interpretation:
  - Weight failure: reduce concentration.
  - Correlation failure: reduce max correlation, but do not add meaningless noise.
  - Fitness failure: improve return/Sharpe, not only turnover.
  - Delay-0 failing Delay-1 Sharpe suggests the alpha may be better as Delay-1.
  - Subuniverse failure suggests weak performance in the more liquid or required subuniverse slice.
- Capitalization recordsets matter:
  - Good Sharpe across high cap and low cap is healthier.
  - Extremely uneven PnL/Sharpe by cap can flag fragility.

## Power Pool Notes

- Power Pool alphas are intentionally simple and high quality.
- Eligibility shape:
  - Sharpe >= 1.0.
  - Unique operators, including repeated operators, <= 8. `ts_backfill` and `group_backfill` are not counted.
  - Unique data fields excluding grouping fields <= 3.
  - Power Pool correlation < 0.5.
  - Turnover, sub-universe, and robust-universe tests pass.
- If Power Pool self-correlation is above 0.5, Sharpe needs to be 10% higher than the most correlated alpha.
- Pure Power Pool alpha descriptions need at least 100 characters using idea/rationale style.
- Low turnover and liquid universes help after-cost performance.

## Python Alpha And SuperAlpha Notes

- Python alphas use the `@alpha` decorator, exactly one decorated function per file.
- Two simulation paths exist:
  - BrainLabs local simulation for fast iteration.
  - Actual platform/API simulation for final validation.
- Translating Fast Expression to Python Alpha requires operator descriptions, field descriptions, and correct `@alpha(data=[...], store=[...])` syntax.
- SuperAlpha:
  - Has a selection expression and combo expression.
  - OS component activation is preferred for realistic evaluation because it activates component alphas from their OS start dates.
  - IS activation is useful for initial research but can inflate performance.
  - For GLB SuperAlphas, neutralize to `COUNTRY`, test on `TOP3000`, then submit on `MINVOL1M`; enable MaxTrade for scalability.

## Miner Implications

- Add quota-aware submission based on response headers.
- Add hash-based simulation cache using the full config.
- Add a staged workflow:
  - `probe`: 10-50 meaningful variants, one field/operator representative per family.
  - `refine`: expand lookbacks/neutralization only around promising signals.
  - `exploit`: larger run once an idea family has positive evidence.
- Prefer generated queues sorted by field metadata and economic descriptions.
- Save enough metadata to explain why a variant was tested.
- Fetch recordsets for top results only, not every failed alpha.
- Add Power Pool shape diagnostics: operator count and field count before simulation/submission.
- Add API diagnostic commands for diversity, alpha checks, and recordsets.
