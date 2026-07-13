# Competitor scan — public BTC 5m/15m prediction-market bots

2026-07-11. Survey of GitHub (plus web search) for bots trading Polymarket's short-window
BTC Up/Down markets, to draw inspiration and calibrate our approach. Companion docs:
`2026-07-10-edge-hunt/FINAL-DESIGN.md` (our locked strategy), `ML-PLAN.md` (learning roadmap).

## Headline finding

**Nobody publishes a credible, fee-adjusted, out-of-sample success rate.** Every "win rate"
found is a backtest or an early simulation, and the honest repos admit it. The absence is the
signal: it matches our own research (fees eat naive edges; backtests without real fill pricing
produce fake 80% win rates).

## The repos that matter

### ThinkEnigmatic/polymarket-bot-arena — convergent evolution with our design
- 4 competing bots on BTC 5m: momentum, mean reversion (z-score + RSI), sentiment, hybrid.
- Bayesian learning: "tracks win rates by market conditions (price bucket, BTC momentum,
  time of day)"; resolved outcomes feed back into the model. That is our engine race + our
  bucketed qhat, independently invented.
- Every 12h, bottom-2 bots are replaced by "mutated versions of the winners."
- **No performance numbers published.**
- Assessment: structure validates ours. The 12-hour evolutionary churn is exactly the
  noise-chasing our red team killed (ranking by 12h P&L promotes luck). Our promotion bars
  (400+ paired signals, CI > 0, 10-day cadence) are the discipline they skipped.
- **Worth stealing:** win-rate-by-condition bucketing (price bucket x momentum x time-of-day)
  is a coarse version of our Phase-1 meta-model. External validation for ML-PLAN Phase 1.

### Archetapp gist (Polymarket BTC 5-Minute Up/Down Trading Bot)
- Momentum composite of 7 indicators, window-delta dominant; enters at T-10s before close
  "when price direction is largely locked in."
- Independently discovered our fill-model insight, stated plainly: fixed 50c pricing "shows
  80%+ win rate" but is fake; delta-based pricing means "when we're confident, so is the
  market, and tokens cost more" (delta ~0.15%+ -> tokens at 92-97c).
- **No profitability claim made** — telling, and consistent with our momentum autopsy:
  buying near-certain outcomes late is fee-dead (our exits family measured buy-the-favorite
  at 150s: 73.9% wins vs 75.4% break-even).

### aulekator/Polymarket-BTC-15-Minute-Trading-Bot (533 stars)
- 7-phase architecture: spike detection + Fear & Greed sentiment + cross-exchange divergence,
  weighted voting fusion, 30% stop-loss / 20% take-profit.
- Claims "~75% win rate in early runs" (simulation).
- **Zero mention of fees anywhere.** On a binary needing ~52% after taker fees, a fee-blind
  75% from "early runs" is uninformative. Stops/take-profits are the overlay class our exits
  research proved fee-dead on this structure.

### Others
- radioman/polymarket-arbitrage-trading-bot (482★): BTC/ETH 5m "arbitrage" framing.
- KaustubhPatange/polymarket-trade-engine (293★): general binary-market execution engine —
  possibly useful as execution reference, not strategy.
- yyq7903/auto-trading (34★), dearolaf (14★), and a long tail of small 5m bots: momentum
  variants, no validated results.

## Scam flag

Several top-starred results ("polymarket weather trading bot" 622★, "Polymarket-Arbitrage-
Trading-Bot" 566★) show keyword-stuffed duplicated descriptions — classic SEO/drainer-repo
markings; star counts likely inorganic. **Never clone-and-run a Polymarket bot that ships a
binary or asks for a private key/seed phrase.**

## What this means for us

1. Our two structural advantages over the public field: fees as the FIRST constraint (not an
   afterthought), and out-of-sample proof with adversarial verification. The public bots
   optimize the backtest and omit the fee line — the recipe for an 80% win rate that loses money.
2. Nobody found (or at least published) our isolated-impulse gate. The public strategies are
   momentum-heavy — the side our autopsy showed loses to fees plus adverse selection.
3. The one imported idea: condition-bucketed win-rate learning (bot-arena) -> already covered
   by ML-PLAN Phase 1 features (ask, prior move, eff6, cnt12, spread, sec, hour, vol).

Sources: github.com/ThinkEnigmatic/polymarket-bot-arena · gist.github.com/Archetapp/7680adabc48f812a561ca79d73cbac69 ·
github.com/aulekator/Polymarket-BTC-15-Minute-Trading-Bot · github.com/radioman/polymarket-arbitrage-trading-bot ·
GitHub search 2026-07-11 ("bitcoin 5 minute trading bot", "btc prediction 5 minute", "polymarket trading bot").
