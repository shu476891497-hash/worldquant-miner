# WQ Field Mapping Coverage Report

Generated: 2026-05-26 08:38 UTC

## Summary

| Metric | Value |
|--------|-------|
| Total WQ fields | 7,820 |
| Exact matches | 45 |
| Proxy matches | 1,537 |
| Unavailable | 6,238 |
| **Coverage %** | **20.2%** |

## Coverage by Category

| Category | Total | Exact | Proxy | Unavailable | Coverage % |
|----------|-------|-------|-------|-------------|------------|
| model | 3,296 | 0 | 8 | 3,288 | 0.2% |
| fundamental | 1,758 | 24 | 479 | 1,255 | 28.6% |
| analyst | 1,374 | 0 | 949 | 425 | 69.1% |
| news | 1,018 | 0 | 0 | 1,018 | 0.0% |
| pv | 195 | 21 | 13 | 161 | 17.4% |
| option | 138 | 0 | 88 | 50 | 63.8% |
| socialmedia | 22 | 0 | 0 | 22 | 0.0% |
| sentiment | 19 | 0 | 0 | 19 | 0.0% |

## Exact Match Fields

| WQ Field | Source | Maps To |
|----------|--------|---------|
| `assets` | simfin | Total Assets |
| `assets_curr` | simfin | Total Current Assets |
| `bookvalue_ps` | simfin | Book Value per Share (derived) |
| `cap` | yfinance | marketCap (yfinance info) |
| `capex` | simfin | Capital Expenditures |
| `cash` | simfin | Cash & Cash Equivalents |
| `cash_st` | simfin | Cash & Cash Equivalents |
| `cashflow` | simfin | Net Cash from Operating Activities |
| `cashflow_dividends` | simfin | Dividends Paid |
| `cashflow_fin` | simfin | Net Cash from Financing Activities |
| `cashflow_invst` | simfin | Net Cash from Investing Activities |
| `cashflow_op` | simfin | Net Cash from Operating Activities |
| `close` | yfinance | Adj Close |
| `cogs` | simfin | Cost of Goods Sold |
| `country` | yfinance | yfinance info['country'] |
| `currency` | yfinance | yfinance info['currency'] |
| `cusip` | yfinance | yfinance info['cusip'] |
| `debt_lt` | simfin | Long Term Debt |
| `dividend` | yfinance | Dividends |
| `ebitda` | simfin | EBITDA |
| `equity` | simfin | Total Equity |
| `exchange` | yfinance | yfinance info['exchange'] |
| `high` | yfinance | High |
| `industry` | yfinance | yfinance info['industry'] |
| `interest_expense` | simfin | Interest Expense, Net |
| `isin` | yfinance | yfinance info['isin'] |
| `liabilities` | simfin | Total Liabilities |
| `liabilities_curr` | simfin | Total Current Liabilities |
| `low` | yfinance | Low |
| `market` | yfinance | yfinance info['market'] |
| `open` | yfinance | Open |
| `operating_income` | simfin | Operating Income (Loss) |
| `pretax_income` | simfin | Pretax Income (Loss) |
| `rd_expense` | simfin | Research & Development |
| `returns` | yfinance | pct_change(Adj Close) |
| `revenue` | simfin | Revenue |
| `sales` | simfin | Revenue |
| `sector` | yfinance | yfinance info['sector'] |
| `sedol` | yfinance | yfinance info['sedol'] |
| `sga_expense` | simfin | Selling, General & Administrative |
| `sharesout` | yfinance | sharesOutstanding (yfinance info) |
| `split` | yfinance | Stock Splits |
| `subindustry` | yfinance | yfinance info['subindustry'] |
| `ticker` | yfinance | yfinance info['ticker'] |
| `volume` | yfinance | Volume |

## Proxy Match Fields (sample)

| WQ Field | Source | Computation |
|----------|--------|-------------|
| `accrued_liabilities_total` | simfin | SimFin approximate: accrued_liabilities_total (heuristic match on 'liabilit') |
| `accrued_liabilities_total_2` | simfin | SimFin approximate: accrued_liabilities_total_2 (heuristic match on 'liabilit') |
| `accumulated_amortization_customer_intangibles` | simfin | SimFin approximate: accumulated_amortization_customer_intangibles (heuristic match on 'amortization') |
| `accumulated_amortization_customer_intangibles_2` | simfin | SimFin approximate: accumulated_amortization_customer_intangibles_2 (heuristic match on 'amortization') |
| `accumulated_amortization_finite_intangibles` | simfin | SimFin approximate: accumulated_amortization_finite_intangibles (heuristic match on 'amortization') |
| `accumulated_depreciation_depletion_amortization_ppne` | simfin | SimFin approximate: accumulated_depreciation_depletion_amortization_ppne (heuristic match on 'depreciation') |
| `accumulated_oci_net_of_tax_value` | simfin | SimFin approximate: accumulated_oci_net_of_tax_value (heuristic match on 'tax') |
| `acquired_cash_equivalents_business_combination` | simfin | SimFin approximate: acquired_cash_equivalents_business_combination (heuristic match on 'cash') |
| `acquired_finite_intangible_assets` | simfin | SimFin approximate: acquired_finite_intangible_assets (heuristic match on 'asset') |
| `acquired_finite_intangible_assets_total` | simfin | SimFin approximate: acquired_finite_intangible_assets_total (heuristic match on 'asset') |
| `acquisition_assets_property_plant_equipment` | simfin | SimFin approximate: acquisition_assets_property_plant_equipment (heuristic match on 'asset') |
| `acquisition_identifiable_assets_recognized` | simfin | SimFin approximate: acquisition_identifiable_assets_recognized (heuristic match on 'asset') |
| `acquisition_liabilities_assumed` | simfin | SimFin approximate: acquisition_liabilities_assumed (heuristic match on 'liabilit') |
| `acquisition_proforma_revenue` | simfin | SimFin approximate: acquisition_proforma_revenue (heuristic match on 'revenue') |
| `acquisition_related_costs_expense` | simfin | SimFin approximate: acquisition_related_costs_expense (heuristic match on 'expense') |
| `acquisition_related_expenses` | simfin | SimFin approximate: acquisition_related_expenses (heuristic match on 'expense') |
| `actual_cashflow_per_share_value_quarterly` | WRDS/IBES | IBES approximate: actual_cashflow_per_share_value_quarterly |
| `actual_dividend_value_quarterly` | WRDS/IBES | IBES approximate: actual_dividend_value_quarterly |
| `actual_eps_value_quarterly` | WRDS/IBES | IBES approximate: actual_eps_value_quarterly |
| `actual_return_on_pension_plan_assets` | simfin | SimFin approximate: actual_return_on_pension_plan_assets (heuristic match on 'asset') |
| `actual_sales_value_annual` | WRDS/IBES | IBES approximate: actual_sales_value_annual |
| `actual_sales_value_quarterly` | WRDS/IBES | IBES approximate: actual_sales_value_quarterly |
| `actuals_reporting_currency` | WRDS/IBES | IBES approximate: actuals_reporting_currency |
| `actuals_value_currency_code` | WRDS/IBES | IBES approximate: actuals_value_currency_code |
| `adj_net_income_median` | WRDS/IBES | IBES approximate: adj_net_income_median |
| `adjfactor` | yfinance | Close / Adj Close |
| `adv20` | yfinance | rolling_mean(Volume, 20) |
| `afss_accumulated_oci_adjustment_net_tax` | simfin | SimFin approximate: afss_accumulated_oci_adjustment_net_tax (heuristic match on 'tax') |
| `allocated_sbp_expense_rsu` | simfin | SimFin approximate: allocated_sbp_expense_rsu (heuristic match on 'expense') |
| `allocated_sbp_expense_stock_options` | simfin | SimFin approximate: allocated_sbp_expense_stock_options (heuristic match on 'expense') |
| `allocated_sbp_expense_total` | simfin | SimFin approximate: allocated_sbp_expense_total (heuristic match on 'expense') |
| `anl4_adxqf_mean` | WRDS/IBES | IBES approximate: anl4_adxqf_mean |
| `anl4_adxqf_median` | WRDS/IBES | IBES approximate: anl4_adxqf_median |
| `anl4_adxqf_numest` | WRDS/IBES | IBES approximate: anl4_adxqf_numest |
| `anl4_adxqfv110_mean` | WRDS/IBES | IBES approximate: anl4_adxqfv110_mean |
| `anl4_adxqfv110_median` | WRDS/IBES | IBES approximate: anl4_adxqfv110_median |
| `anl4_adxqfv110_numest` | WRDS/IBES | IBES approximate: anl4_adxqfv110_numest |
| `anl4_ady_mean` | WRDS/IBES | IBES approximate: anl4_ady_mean |
| `anl4_ady_median` | WRDS/IBES | IBES approximate: anl4_ady_median |
| `anl4_ady_numest` | WRDS/IBES | IBES approximate: anl4_ady_numest |
| `anl4_af_eps_value` | WRDS/IBES | IBES approximate: anl4_af_eps_value |
| `anl4_afv4_actual` | WRDS/IBES | IBES approximate: anl4_afv4_actual |
| `anl4_afv4_cfps_mean` | WRDS/IBES | IBES approximate: anl4_afv4_cfps_mean |
| `anl4_afv4_cfps_median` | WRDS/IBES | IBES approximate: anl4_afv4_cfps_median |
| `anl4_afv4_div_mean` | WRDS/IBES | IBES approximate: anl4_afv4_div_mean |
| `anl4_afv4_div_median` | WRDS/IBES | IBES approximate: anl4_afv4_div_median |
| `anl4_afv4_eps_high` | WRDS/IBES | IBES approximate: anl4_afv4_eps_high |
| `anl4_afv4_eps_low` | WRDS/IBES | IBES approximate: anl4_afv4_eps_low |
| `anl4_afv4_eps_mean` | WRDS/IBES | IBES approximate: anl4_afv4_eps_mean |
| `anl4_afv4_eps_number` | WRDS/IBES | IBES approximate: anl4_afv4_eps_number |
| ... | ... | *(1487 more proxy fields)* |

## WRDS Download Guide

For fields that cannot be sourced from yfinance or SimFin, the following WRDS databases provide equivalent data:

### CRSP Daily Stock File

**Description:** Stock prices, returns, market cap, shares outstanding

**Database:** `crsp`

**Table:** `crsp.dsf`

**Key columns:** `permno`, `date`, `prc`, `ret`, `shrout`, `vol`, `cfacpr`, `cfacshr`, `bidlo`, `askhi`

**Unmapped WQ fields served:** ~161

**SQL template:**
```sql
SELECT permno, date, prc, ret, retx, shrout, vol, cfacpr, cfacshr, bidlo, askhi
FROM crsp.dsf
WHERE date BETWEEN '{start_date}' AND '{end_date}'
  AND permno IN (SELECT permno FROM crsp.dsenames
                 WHERE ticker IN ({tickers}))
ORDER BY permno, date;
```

### CRSP Monthly Stock File

**Description:** Monthly returns and delisting info

**Database:** `crsp`

**Table:** `crsp.msf`

**Key columns:** `permno`, `date`, `prc`, `ret`, `shrout`, `vol`

**Unmapped WQ fields served:** ~161

**SQL template:**
```sql
SELECT permno, date, prc, ret, retx, shrout, vol
FROM crsp.msf
WHERE date BETWEEN '{start_date}' AND '{end_date}'
ORDER BY permno, date;
```

### Compustat Annual Fundamentals

**Description:** Annual fundamental data (income statement, balance sheet, cash flow)

**Database:** `comp`

**Table:** `comp.funda`

**Key columns:** `gvkey`, `datadate`, `sale`, `ebitda`, `ni`, `oibdp`, `at`, `lt`, `ceq`, `capx`, `dp`, `xsga`, `xrd`, `revt`, `cogs`, `txt`, `oiadp`, `csho`, `prcc_f`, `epspx`, `epsfi`

**Unmapped WQ fields served:** ~1255

**SQL template:**
```sql
SELECT gvkey, datadate, fyear, sale, ebitda, ni, oibdp,
       at, lt, ceq, capx, dp, xsga, xrd, revt, cogs,
       txt, oiadp, csho, prcc_f, epspx, epsfi
FROM comp.funda
WHERE indfmt = 'INDL'
  AND datafmt = 'STD'
  AND popsrc = 'D'
  AND consol = 'C'
  AND datadate BETWEEN '{start_date}' AND '{end_date}'
ORDER BY gvkey, datadate;
```

### Compustat Quarterly Fundamentals

**Description:** Quarterly fundamental data

**Database:** `comp`

**Table:** `comp.fundq`

**Key columns:** `gvkey`, `datadate`, `rdq`, `saleq`, `niq`, `oibdpq`, `atq`, `ltq`, `ceqq`, `capxq`, `cshoq`, `epspxq`

**Unmapped WQ fields served:** ~1255

**SQL template:**
```sql
SELECT gvkey, datadate, rdq, fqtr, fyearq,
       saleq, niq, oibdpq, atq, ltq, ceqq, capxq,
       cshoq, epspxq
FROM comp.fundq
WHERE indfmt = 'INDL'
  AND datafmt = 'STD'
  AND popsrc = 'D'
  AND consol = 'C'
  AND datadate BETWEEN '{start_date}' AND '{end_date}'
ORDER BY gvkey, datadate;
```

### IBES Detail Estimates

**Description:** Individual analyst EPS estimates

**Database:** `ibes`

**Table:** `ibes.det_epsus`

**Key columns:** `ticker`, `analys`, `fpedats`, `estimator`, `value`, `estcur`, `pdf`

**Unmapped WQ fields served:** ~425

**SQL template:**
```sql
SELECT ticker, analys, fpedats, estimator, value,
       estcur, pdf, fpi
FROM ibes.det_epsus
WHERE fpedats BETWEEN '{start_date}' AND '{end_date}'
ORDER BY ticker, fpedats;
```

### IBES Summary Statistics

**Description:** Consensus analyst estimates (mean, median, high, low, count)

**Database:** `ibes`

**Table:** `ibes.statsum_epsus`

**Key columns:** `ticker`, `statpers`, `fpedats`, `meanest`, `medest`, `highest`, `lowest`, `numest`, `actual`, `stdev`

**Unmapped WQ fields served:** ~425

**SQL template:**
```sql
SELECT ticker, statpers, fpedats, fpi,
       meanest, medest, highest, lowest,
       numest, actual, stdev
FROM ibes.statsum_epsus
WHERE statpers BETWEEN '{start_date}' AND '{end_date}'
ORDER BY ticker, statpers;
```

### OptionMetrics Implied Volatility Surface

**Description:** Options implied volatility and Greeks

**Database:** `optionm`

**Table:** `optionm.opprcd`

**Key columns:** `secid`, `date`, `exdate`, `cp_flag`, `strike_price`, `impl_volatility`, `delta`, `gamma`, `vega`, `theta`, `best_bid`, `best_offer`, `volume`, `open_interest`

**Unmapped WQ fields served:** ~50

**SQL template:**
```sql
SELECT secid, date, exdate, cp_flag,
       strike_price / 1000 AS strike,
       impl_volatility, delta, gamma, vega, theta,
       best_bid, best_offer, volume, open_interest
FROM optionm.opprcd
WHERE date BETWEEN '{start_date}' AND '{end_date}'
ORDER BY secid, date, exdate, strike_price;
```

### Ravenpack News Analytics

**Description:** News sentiment scores and event data

**Database:** `ravenpack`

**Table:** `ravenpack.rp_entity_news_v3`

**Key columns:** `rp_entity_id`, `event_sentiment_score`, `relevance`, `novelty`, `timestamp_utc`, `event_type`, `topic`

**Unmapped WQ fields served:** ~1037

**SQL template:**
```sql
SELECT rp_entity_id, timestamp_utc,
       event_sentiment_score, relevance, novelty,
       event_type, topic, headline
FROM ravenpack.rp_entity_news_v3
WHERE timestamp_utc BETWEEN '{start_date}' AND '{end_date}'
  AND relevance >= 75
ORDER BY timestamp_utc;
```
