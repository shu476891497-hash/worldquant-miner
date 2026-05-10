# WQ Forum D0 Template Library (Auto-Generated)

Generated from 70 forum posts | 12 templates extracted

## Template 1
**Logic:** D0 intraday mean-reversion: combines opening gap (close vs open), volume tail-cut, and prior return decay, neutralized by subindustry and cap-bucketed

```
group_neutralize(group_zscore(rank(ts_delay(close,1) - open) + rank(min(ts_delay(volume,1)/adv20, 5)) - rank(ts_delay(returns,1)), subindustry), bucket(rank(cap), range='0.1,1,0.1'))
```

## Template 2
**Logic:** D0 opening gap weighted by liquidity: multiplies gap signal by squared industry-rank of ADV20, neutralized by subindustry

```
group_neutralize(rank(ts_delay(close,1) - open) * signed_power(group_rank(adv20, subindustry), 2), subindustry)
```

## Template 3
**Logic:** D0 fear plus analyst divergence: combines fear signal (return dispersion) with negative analyst std divergence, neutralized by subindustry

```
group_neutralize(rank(ts_mean(abs(ts_delay(returns,1) - group_mean(ts_delay(returns,1), 1, market))/(abs(ts_delay(returns,1))+0.1), 20)) + rank(-ts_av_diff(vec_min({ANALYST_F}), 360)), subindustry)
```

## Template 4
**Logic:** D0 news momentum plus volume tail: combines news VWAP change with volume tail-cut, neutralized by subindustry

```
group_neutralize(rank(ts_zscore(ts_delta(ts_mean(news_all_vwap, 5), 5))) + rank(min(ts_delay(volume,1)/adv20, 5)), subindustry)
```

## Template 5
**Logic:** D0 option sentiment scaled by price: multiplies option max/close ratio with negative prior return, neutralized by subindustry

```
group_neutralize(rank(ts_scale(vec_max({BLUE_F})/ts_delay(close,1), 120)) * rank(-ts_delay(returns,1)), subindustry)
```

## Template 6
**Logic:** D0 gap plus volume surge minus return: uses opening gap, volume/mean volume, and negative prior return, neutralized by subindustry and cap

```
group_neutralize(group_zscore(rank((open - ts_delay(close,1))/ts_delay(close,1)) + rank(ts_delay(volume,1)/ts_mean(ts_delay(volume,1), 20)) - rank(ts_delay(returns,1)), subindustry), bucket(rank(cap), range='0.1,1,0.1'))
```

## Template 7
**Logic:** D0 regression residual plus reversal: combines 60-day regression of returns on opening gap with negative prior return, neutralized by subindustry

```
group_neutralize(rank(ts_regression(ts_delay(returns,1), open/ts_delay(close,1) - 1, 60)) + rank(-ts_delay(returns,1)), subindustry)
```

## Template 8
**Logic:** D0 gap times 5-day momentum: multiplies opening gap signal by 5-day mean return, neutralized by subindustry

```
group_neutralize(rank(ts_delay(close,1) - open) * rank(ts_mean(ts_delay(returns,1), 5)), subindustry)
```

## Template 9
**Logic:** D0 news momentum plus intraday close/open ratio: combines news VWAP change with today's close/open ratio, neutralized by subindustry

```
group_neutralize(rank(ts_zscore(ts_delta(ts_mean(news_all_vwap, 5), 5))) + rank(ts_delay(close,1)/open - 1), subindustry)
```

## Template 10
**Logic:** D0 volume surge times analyst divergence: multiplies volume ratio with negative analyst std divergence, neutralized by subindustry

```
group_neutralize(rank(ts_delay(volume,1)/ts_mean(ts_delay(volume,1), 20)) * rank(-ts_av_diff(vec_min({ANALYST_F}), 360)), subindustry)
```

## Template 11
**Logic:** D0 option sentiment plus volume tail: combines option max/close with volume tail-cut, neutralized by subindustry

```
group_neutralize(rank(ts_scale(vec_max({BLUE_F})/ts_delay(close,1), 120)) + rank(min(ts_delay(volume,1)/adv20, 5)), subindustry)
```

## Template 12
**Logic:** D0 opening gap weighted by liquidity rank: multiplies gap by squared industry-rank of 20-day mean volume, neutralized by subindustry

```
group_neutralize(rank(ts_delay(close,1) - open) * signed_power(group_rank(ts_mean(ts_delay(volume,1), 20), subindustry), 2), subindustry)
```

