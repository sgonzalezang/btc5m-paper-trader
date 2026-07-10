# BTC5M EDGE HUNT — SHARED RESEARCH BRIEF

You are one agent in a coordinated quant research program on a PAPER trading system.
Read this whole brief before doing anything. Everything you conclude must be consistent
with the market spec, cost model, and methodology bar below.

## Hard boundaries
- PAPER research only. Never place an order, never POST to any trading API.
- Read-only on ~/btc5m-paper-trader (never modify files there). Write only under the scratchpad.
- Public GET APIs only (Coinbase, Binance/binance.vision, Kraken, Deribit, Polymarket gamma + CLOB).
  Sleep >= 0.15s between calls. Back off on 429.
- Nothing related to VPNs or geoblock circumvention, ever. If an API is georestricted, note it and move on.
- python3 stdlib is guaranteed. Check `python3 -c "import numpy"` and use numpy if present.

## The market
- Polymarket "Bitcoin Up or Down" 5-minute binaries. Slug: btc-updown-5m-<t0>, t0 aligned to 300s.
- Resolution source: Chainlink BTC/USD data stream (NOT any spot exchange).
- TIE RULE: resolves Up if close >= open. Equality goes to Up.
- Coinbase BTC-USD is our validated proxy for the oracle: direction agreement 97.7% overall on
  260 resolved markets, 100% for intervals with |move| >= 4bps. All disagreement lives below ~2bps.
  Treat sub-2bps intervals as having ~11% resolution noise vs the Coinbase proxy.

## Cost model (exact, from the bot)
- Taker fee per fill: fee = shares * 0.07 * p * (1-p), where p = fill price. Peaks at 50c.
- Gas: $0.004 per trade (negligible).
- Slippage: fills assume ask + 1c ("slip"). Entries are taken from the real CLOB ask.
- Hold-to-resolution EV per share buying at fill price p with true win prob q:
    EV = q - p - 0.07 * p * (1-p)
  BREAK-EVEN win rate q*(p) = p + 0.07 * p * (1-p):
    p=0.35 -> 0.3659 | p=0.50 -> 0.5175 | p=0.55 -> 0.5673 | p=0.60 -> 0.6168 | p=0.65 -> 0.6659
- Any rule that cannot beat q*(p) at its own realistic fill prices ON TEST DATA is dead. No exceptions.
- Early exit (selling before resolution) pays a second taker fee plus the spread. Model it if you test exits.

## Validated prior findings (do NOT rediscover; build on or challenge with better data)
1. REVERSAL EDGE (the only confirmed edge): after a completed prior-interval |move| >= 12bps,
   the next interval reverses ~56% (10 days, n=2,876 intervals, buffered construction;
   placebo p=0.000, block bootstrap p=0.015). Entry near 50c clears the fee hurdle.
2. REGIME DEPENDENCE: Kaufman trend efficiency = |net move| / sum(|moves|) over trailing 12
   five-minute intervals. eff <= 0.48 (choppy): reversal ~60%. High eff (trending): ~43% and the
   strategy loses. Gating turned a losing 10-day always-on book (-$2,866) into +$917.
   Efficiency was the ONLY regime signal that survived out-of-sample; vol level and
   recent-outcome streaks did not.
3. MOMENTUM IS FEE-DEAD: 2-4bps early drift continues ~64.6% gross (selection-free), but entries
   price at 62-65c, so net after fee ~ zero. Fade variants pay double vig and lose.
4. OPTIONAL STOPPING: profit-stop / loss-stop rules do not change EV. Frame any stop work as
   variance/drawdown control only, never as an edge.
5. Feeds: engines compute drift as same-feed ratios, so a constant cross-feed basis cancels.
   Coinbase is the primary feed. Basis wiggle within a window is ~$4.5 median.

## Live paper book so far (reset 2026-07-08, through 07-10; stake $50/trade)
loose -$2,922 (n=600) | floor -$1,623 (531) | band -$1,826 (504) | value -$1,965 (452)
fade -$1,291 (480) | strict -$23 (2) | reversal +$202 (70) | reversal2 +$145 (67) | latentfire -$2 (18)
Older history exists in the pre-reset archive (see datasets).

## Engine definitions (current, from ENGINE_CFG in the bot)
- loose: momentum, 7/10 checks + stability, entry <= 65c. floor: + drift >= 0.02%. band: drift in
  [0.02%, 0.04%]. strict: 10/10 checks. value: fair-value gate, buys when ask + slip < fv - margin
  with fv from a Phi(drift/vol) model. fade: contrarian mirror of loose.
- reversal: prior-interval |move| >= 0.12% completed -> buy the OTHER side at <= 55c cap
  (revEntryMax), >= 150s left (revWinMin), hold to resolution. reversal2: same + gamma fallback
  fill when the book is thin (revLoose). latentfire: reversal2 + efficiency gate eff <= 0.48
  over 12 intervals (effGate/effMax/effWin).

## Datasets (written by the Harvest phase to <SCRATCH>/data/)
All candle files columnar: {"t":[...],"o":[...],"h":[...],"l":[...],"c":[...],"v":[...]}, ascending, deduped.
- cb5m.json    Coinbase BTC-USD 5m, ~60 days   (primary hypothesis-testing series)
- cb1m.json    Coinbase BTC-USD 1m, ~14 days   (path-shape work)
- cbdaily.json Coinbase BTC-USD 1d, ~365 days  (long-context vol)
- eth5m.json   Coinbase ETH-USD 5m, ~60 days   (cross-asset lead-lag)
- bn5m.json    Binance spot BTCUSDT 5m, ~60 days (basis series; may be absent if georestricted)
- funding.json / premium5m.json / oi5m.json  perp funding, futures premium, open interest
  (Binance fapi or Deribit fallback; check the "source" field inside; any may be absent)
- trades.json          flattened paper ledger, ALL engines, current + pre-reset archive, field "src"
                       marks which state file each trade came from; deduped
- ledger_summary.json  per-engine stats incl. ask quantiles, entrySec, fillFrac, fees, feed counts
- ivlhist.json         bot's persisted recent interval returns
- pm_res_3d.json       [[t0, up_won], ...] actual Polymarket resolutions, last ~3 days
- pm_prices_sample.json per-market Up-token price snapshots through the interval
                       (fields: t0, up_won, p20, p60, p150, pLast) for fill-price realism
- state_snapshot.json / state_prereset.json  raw copies of the bot state files
Check file existence before use; degrade gracefully and note anything missing.

## Methodology bar (non-negotiable)
1. Chronological evaluation only. Default split: first 2/3 of the span = TRAIN, last 1/3 = TEST.
   Every headline number must be quoted on TEST. Parameter sweeps must be walk-forward.
2. Reversal-style constructions must use the buffered open-to-open method: prior move =
   (o[t] - o[t-1]) / o[t-1] using consecutive 5m candle OPENS (shared boundary), outcome =
   sign(c[t] - o[t]) with ties counted as Up. This kills the boundary-gap artifact.
3. Costs per the exact model above at realistic fill prices. For ~50c reversal-style entries use
   pm_prices_sample.json for what the book actually charges. Document every price assumption.
4. Headline p-values via block bootstrap with 1-hour blocks (12 intervals). Bar: p < 0.01 on TRAIN
   and the effect must persist on TEST. A lone p ~ 0.05 in a project running dozens of tests is noise.
5. Be brutal. Max 5 findings. verdict "promising" is reserved for effects that clear fees on TEST.
   Dead ends are valuable output; list them explicitly.
6. Save intermediate tables/scripts under <SCRATCH>/work/<your-key>/ and cite exact paths in your
   findings notes so verifiers can audit you.
