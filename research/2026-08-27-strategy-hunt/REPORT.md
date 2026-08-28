# Strategy hunt 2026-08-27 — final report

**Mission:** find a winning strategy for Polymarket btc-updown-5m, backtest it, build it plus variants.
**Method:** 30-day harvest (8,636 markets, outcomes + in-interval price paths + Coinbase 1-min candles),
Fable-5 design doc (7 candidate families, 68 configs, pre-registered protocol), train/val/test time
splits, then three independent adversarial audits (code, statistics, market mechanics).

## Verdict

**No taker strategy demonstrated positive expectancy at realistic fills on the live oracle regime.**
The apparent winners (+20 to +140%/$, t up to 12) were artifacts, dismantled by the audits:

1. **Stale-midpoint look-ahead (fatal).** prices-history at fidelity=1 returns ~one MIDPOINT per
   minute (93% of prints end in half-cents), stamped ~+10s past each minute. Decisions at +70/130/
   190/250s therefore priced off a quote that predates the signal candle in 46-64% of markets —
   one minute of BTC tape leaked into the entry price. Requiring the quote to postdate its signal
   candle collapses every pick to noise or worse (C1 flips significantly negative).
2. **Oracle regime churn.** Settlement is a Chainlink 60s-TWAP-vs-strike (NOT Coinbase spot close);
   the oracle config changed FOUR times inside the window (spot → twap-30 → twap-60 on 08-14).
   Train was 88% dead-regime; val/test 100% live-regime. Also: the harvester's print phase shifted
   ~08-11, making val/test prints ~56s stale vs 1-3s in early train.
3. **Fee confirmed:** 0.07·shares·p·(1−p), taker-only (crypto_fees_v2, rate .07, exponent 1,
   rebateRate .2). Matches the bot's taker_fee and the earlier 6,500-fill reconciliation exactly.
   **Maker fills pay ZERO fee and earn a 20% rebate** — the entire 1.7-6pp hurdle is taker-only.
4. **Tradability:** spread is 1c essentially always; $20-50 fills at touch (mid+0.5c) — EXCEPT
   right after a jump, when depth evaporates (6 shares at touch observed post-move). The collapsed
   side (≤18c late) is untradeable: one-sided books, no exit, realized 13.2% win vs 16.9% breakeven.

### What survived (as hypotheses, not proofs)
- **Coinbase→Polymarket lead/lag (C5):** on fresh-print days the effect persists under harsh
  conditional-slippage models (+20%/$, day-clustered t≈2.9, 7/7 days) — but 91% of its backtest
  fills happened where the live book runs away, and post-jump depth evaporation is exactly the
  fill problem. Cannot be settled by any backtest on this data.
- **Maker fee asymmetry:** structural, not directional — post instead of lift and the house edge
  reverses sign.

### Killed for good
- C1 fair-value taker (artifact; significantly negative honest), C2 trail-band fade, C3 impulse-open
  grid, C4 late-collapse (untradeable side), C6 session gates, C7 streak-fade (P(cont|streak≥3)
  = 50.0% exactly, n=2,190 — the market prices streaks correctly).
- Base rates: the book is CALIBRATED at midpoints (±2pp every bucket/offset). Late longshots are
  overpriced (4.0% win at ≤10c) — but the tradable favorite side nets nothing after real fills.

## The build (deployed)

Four SHADOW paper engines in btc5m_bot.py — the only honest next step: measure the surviving
hypotheses live, where the book is real. Shared signal: last-60s spot move ≥ 1σ₆₀, aligned with
interval displacement, leading side's real ask ≥ gap below the Φ fair value, ask ≤ 60c, entry
window 45-250s, one entry/interval, hold to close, flat $50. Differing ONLY in execution:

| engine | execution |
|---|---|
| leadlag | lift the book, limit ask+1c, no chase (arrival price) |
| leadlag12 | same, 12c gap (deeper mispricing) |
| leadlagT | limit ask+3c (does paying up capture the runaways?) |
| leadlagM | MAKER: post at the bid, zero fee; fill proxy = later ask crosses the post |

**Pre-registered kill criterion:** any engine with ≥200 FILLED trades and negative fill-conditioned
ret/$ is retired. RAN/expired-post lines in the log are the fill-selection data.

## Protocol notes
- The embargoed test window was **deliberately NOT consumed** (out_test.json absent, no
  test_consumed.stamp): all three audits agree it sits 100% in the stale-print + regime-shifted
  zone and would measure the artifact. Any future test must re-harvest post-08-14-only data with
  second-level quotes (or live capture).
- Statistics postscript: day-clustered t at G=7 has a hard p-floor of 0.0078 (sign-flip support);
  normal references overstate significance by orders of magnitude. Never select on tclu vs normal.

Files: harvest.py, bt.py, candidates.py, run_protocol.py, baserates.py, picks.json, out_train.json.
Audit transcripts: session agents (code / stats / mechanics), 2026-08-27→28.
