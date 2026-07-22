# The big-move reversion edge — max-effort hunt, 2026-07-15

## One-line result
Fading a **≥0.20% prior-interval move** and holding to close wins **~58%** where the fee
break-even is **~52%** — a real, statistically robust edge that lives in exactly the trades our
existing engines avoid. Deployed as shadow engines `revert20` / `revert18` to forward-test the
one number a backtest cannot see: the real fill prices. **Not armed for real money.**

## How we got here (three nulls, then this)
1. `fade50` (fade the run-up): +$168 in-sample n=7 → **−$2,306** out-of-sample. Refuted.
2. Hunt #1 (45,303 hypotheses, single-interval features): **NO EDGE**, 0/12 survived holdout.
3. Hunt #2 (multi-timeframe hourly/15m/5m, 248 hypotheses): **NO EDGE**, 0/13 survived, 9 flipped sign.
4. This campaign — the first real signal.

## The finding (unbiased candle sample, not our trades)
Over 3 weeks of BTC 5m candles (~6,000 intervals), the outcome = sign(close−open):
- Raw BTC 5m **mean-reverts**: after a >0.1% move the next interval reverses ~54.6% (perm-null 50.1±0.5%).
- The edge concentrates in **bigger moves**. Fade ≥0.20% prior move, bet at open, hold to close:
  - n=453, **win 58.1%**, edge **+6.3pp**, binomial **p=0.0041**.
  - Threshold **plateau** 0.15%–0.25% (all positive, peak +7.3pp at 0.18%) — not a mined spike.
  - **Week-by-week +4.6 / +5.5 / +8.3pp** (most recent strongest) — not decaying.
  - **Day-block bootstrap 95% CI = [54.1%, 62.3%]**, entirely above the 51.75% break-even. Autocorrelation-honest.
- **The book does NOT price it:** our earliest fills of this bet paid ~50c mean, and cheap (≤50c)
  fills reverted *more* (53%) than rich (>50c) fills (49%) — the opposite of an efficient book.
- Settlement (Polymarket) agrees with Coinbase close>open 97.7% of the time.

## Why we never caught it
Our engines trade **intra-interval** (ride the move happening now = momentum = lose). This is an
**inter-interval** trade (prior candle moved → this candle reverts). And of 453 qualifying
intervals our engines touched only 54, which reverted just 51.9%, while the **399 we ignored
reverted 58.9%**. Our logic actively selects the worst reversions. The old `reversal` engine is
this exact trade at the wrong threshold (0.12% instead of ≥0.18%).

## The honest caveat (why forward-test, not arm)
Our handful of actual fills won 51.9%, not 58%. That gap is a tiny self-selected subset, and a
clean engine should capture far more — but "should" is not "did." Realistic EV spans **conservative
~53% (+$0.75/$50 trade)** to **optimistic ~58% (+$4.50/$50 trade)**. Both positive. Which is real
depends on the fills a dedicated engine actually gets at the open, at scale. **Only forward data
answers it.**

## What was deployed (main @ a9ccb7d)
- `revert20`: fade ≥0.20% prior move, bet reversal at open, hold to close. Flat $50, **shadow/paper**.
- `revert18`: same at ≥0.18% (the significance peak).
- Identical to the proven `reversal` machinery — ONLY `revThr` changed. So the pair also answers
  "was the reversal engine's loss just the threshold?"
- NOT in `--signal-engines` → no live orders. They record entries at the real open book price.

## PRE-REGISTERED forward-test decision rule (fixed 2026-07-15, before any forward data)
Judge `revert20` on trades from **after this deploy only** (t0 > 2026-07-15 deploy time):
- **GRADUATE to a live candidate** iff: n ≥ 150 AND realized edge > 0 (win rate above the
  per-trade break-even bar) AND a day-block bootstrap 95% CI on the edge that **excludes zero**.
- **RETIRE** iff: after n ≥ 150 the edge CI includes or sits below zero.
- Do NOT let the backtest number move this bar. Do NOT arm real money before GRADUATE.
- Even on GRADUATE, size as if the true edge is **half** the observed one.

## Method files
Analysis env + data staged under scratchpad/edgehunt (train/holdout split at t0=1783979100,
candles5m_3wk.json). Walk-forward GBM ceiling = 51.9% overall / 54.6% high-confidence (= the same
big-move reversion; the model found nothing beyond it).
