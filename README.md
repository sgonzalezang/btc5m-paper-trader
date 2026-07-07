# Polymarket 5-Minute Crypto — Paper Trader

A live signal engine and **paper trader** for Polymarket's crypto **Up/Down 5-minute**
markets (BTC, ETH, SOL, XRP, DOGE), implementing a momentum-into-close strategy.
One self-contained HTML file — no build, no backend, no dependencies.

**It never places real orders.** It reads public market data only, records simulated
entries to a browser-local ledger, and settles them against Polymarket's own market
resolution — so you can measure whether the strategy actually clears its breakeven
before risking anything. Not financial advice.

## Run it

Open `index.html` in a browser (or the GitHub Pages URL of this repo) and press
**▶ Start watching**. Leave the tab open — intervals roll every 5 minutes and a
strict profile passes on most of them by design.

## Two engines at once

The page runs **two paper traders side by side** over the same live signal:

- **Strict** — needs **all 10** guards green (the disciplined strategy; trades rarely)
- **Loose** — needs only **N/10** green (default 6, tunable in the toolbar) so you see plenty of
  action and can compare a trigger-happy version's P&L against the strict one. The lesson: loose
  trades far more but usually at worse entry prices, and entry price is your breakeven win rate.

## The strategy

Ported from the "5min-btc-polymarket" momentum-into-close skill:

- Enter only with **60–150 s left** in the interval
- Only on a confirmed move ≥ **0.10% / 0.07%** of the interval open (≈ $100/$70 on BTC)
- Only when crowd skew agrees (momentum-side mid ≥ 52¢)
- Price cap **ask ≤ 70¢** — your entry price *is* your breakeven win rate
- Spread ≤ 3¢ · top-ask depth ≥ $30 · quotes fresh (book ≤ 8 s, feed ≤ 15 s)
- **Quote stable across two consecutive ticks** (≤ 15¢ jump) — dirty-data guard
- Per-day trade and loss caps · 0.25%/0.30% spot-retrace stop-loss
- $1+ micro-hedge when late skew goes extreme (≥ 95¢/93¢)
- Paper fills pay a configurable **slippage haircut** (default +1¢) on the visible ask

## Data sources (all public, all fetched in your browser)

- Markets: Gamma API by deterministic slug `<asset>-updown-5m-<unix start>`
  (300-second UTC boundaries), with series/search sweep fallback
- Executable quotes: CLOB order book (`clob.polymarket.com/book`), Gamma fallback
- Spot: 1-minute candles, Coinbase Exchange → Binance data mirror → Kraken
- Resolution: markets resolve on Chainlink price streams; the ledger settles from
  Polymarket's resolved outcome (spot feed only as a provisional fallback)
- A public CORS-proxy fallback chain kicks in if a direct call is blocked

## Tests

Mocked-network Chromium harnesses (no live API calls):

```
npm install playwright-core
node tests/btc5m.test.js    # 25 unit assertions (guards, fills, stop, hedge, settle, persistence)
node tests/btc5m.asset.js   # multi-asset discovery + %-threshold scaling
node tests/btc5m.e2e.js     # full real-time lifecycle (~5-7 min): auto-entry → rollover → settle
```

Set the Chromium path in the scripts if yours differs from `/opt/pw-browsers/chromium`
(e.g. point `executablePath` at a local Chrome).

## Scope

Paper trading only, deliberately. Real execution needs an authenticated CLOB client,
EIP-712 order signing, latency engineering, and jurisdiction checks — build that only
if the paper ledger's win rate beats its average entry price by 5+ points over a real
sample.

## Lifetime tracking (24/7 headless bot)

`bot/btc5m_bot.py` runs BOTH engines (strict 10/10 + loose 7/10) around the
clock as a launchd service — see `bot/README-bot.md`. It publishes its ledger
(`state.json`) to the `data` branch; `live.html` shows both ledgers with
per-trade guard detail, and the main page's Lifetime panel shows the strict
engine's running return. (An earlier strict-only daemon lived in `daemon/`;
retired 2026-07-06, recoverable from git history.)
