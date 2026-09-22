# Forward research v1

This is experimental paper signal evaluation, not a profitable trading system or an execution service.
Existing recommendation scores and mail remain unchanged. No orders are sent.

## Start collecting

After merging, manually run **Analyze, email and deploy** on main once with
`initialize_research=true`, `send_email=false`. The first observation has no returns.
An authorized deployment commit containing `[initialize-research]` is the equivalent
non-email bootstrap path when workflow dispatch is unavailable.
Subsequent hourly workflows restore the newest main-branch `research-ledger-v1` artifact,
settle old records, append the first observation per Korean calendar day, and upload the
entire cumulative ledger (90-day rolling artifact retention). A restore API failure,
expired ledger, or corrupt JSON stops research instead of resetting it. The existing
mail workflow continues. If history is absent, initialization must be explicitly enabled.
Download ledger artifacts periodically for an independent backup. More than 90 days
without successful updates may require backup recovery. Never initialize to conceal a gap.

## Fixed protocol

- First daily screened universe is saved, including nonselected coins. It is NOT the entire exchange universe.
- Features include recommendation/score, exposure change with matching source availability,
  active community sources, seven-day return minus BTC return, official announcement URLs,
  risk checks and the model prediction/version. News URLs are frozen at observation.
- Entry: the next successful live quote observation within six hours, never the signal price.
- Exit: first observed quote at or after entry + 1/3/7 days, maximum six hours late.
  Unavailable quotes stay missing and visible; coins leaving the screen are still queried.
- Fees: 5 bps per side; slippage: 10 bps per side, multiplicatively applied on entry/exit.
  These are assumptions, not verified exchange fees. Cost doubling is reported as a stress test.
- Benchmarks: original buy candidates, price > EMA20 > EMA50, observed universe,
  BTC over matched holding windows, and zero-return cash reference.
- Experimental model: deterministic L2 logistic regression, fixed features/scales, daily refit,
  only completed 3-day outcomes strictly older than a seven-day embargo. Minimum 60 signal
  dates and 200 eligible records, both target classes. Threshold 0.60 is fixed, not optimized.
  Predictions are stored once and never recomputed for previous observations.
- Learned and attention/news candidates require non-bear regime, RSI <70, seven-day return
  between -5% and 20%, KRW turnover >=1 billion, verified unlock data with no upcoming unlock.
  Attention/news additionally requires exposure >=2x, >=2 active sources, relative return >0,
  and an associated official announcement. Announcement presence is not bullish sentiment.

## What is not claimed

Mean per-signal returns are NOT an investable compounded equity curve. Positions overlap;
capital allocation, order book depth, market impact, taxes and execution outages are not simulated.
Drawdown is sampled quote peak-to-trough, not intraperiod or portfolio drawdown. Missing
outcomes are counted separately, not treated as zero. Missingness can bias the completed sample.
The model uses overlapping correlated outcomes; sample count is not effective independent size.
There is no automatic promotion or claim of probability calibration/statistical significance.

Next gates before capital use: immutable held-out test period, time-block confidence intervals,
capital-constrained portfolio simulation, calibration evaluation, independent walk-forward review,
and prospective paper operation across market regimes. Semantic novelty, syndicated-news
deduplication and causal policy interpretation are not implemented in v1.

## Verification

`python -m unittest discover -s tests -v`

`node --check docs/research.js`

`python -m src.research` fetches public Upbit quotes and updates local research state.
For deterministic offline testing use the unit fixtures; never publish synthetic data as live history.
