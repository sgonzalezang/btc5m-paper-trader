# ML integration plan — impulse_v2 ("constantly improving" roadmap)

Written 2026-07-10, after FINAL-DESIGN v3 went live. Reference doc for future sessions.
Owner context: the flagship already runs online learning (bucketed qhat, nightly Bayesian-style
update from settled outcomes). This plan upgrades that learner in stages WITHOUT touching the
verified strategy structure.

## Architecture: meta-labeling

The rules decide WHEN to trade (12bps buffered trigger + isolated-impulse gate + 53c cap +
first-45s window — all FROZEN, all verified). The model learns HOW MUCH to trust each trade:
a calibrated P(win | context) that replaces the two-bucket qhat inside the existing
quarter-Kelly formula. ML improves sizing precision; it never invents trades.

Why this shape: the 2026-07-10 research program (research/2026-07-10-edge-hunt/) killed nearly
every contextual feature as a TRADE FILTER (sessions, path shape, ETH lead, funding, vol scaling
— all TRAIN->TEST failures), and the fair-value family showed the book is at least as informed
as our models. Small data (25-50 fills/day) + brutal fees + nonstationary regimes = tiny,
heavily-regularized models with adversarial validation, or nothing.

## Phase 0 — data flywheel (DONE 2026-07-10, this commit)

Enrich every measurement-book record with the decision-time features, so training data accrues
from day one. Schema per record (bot/btc5m_bot.py `_measure_record`):

    { t0, side, cost, win, sized, skip,
      f: { ask, pm (prior move %), eff6, cnt12, spread, sec (entry sec into interval),
           hour (UTC), vol (trailing 10-min range %) } }

Persisted in st["impulse"]["measure"] (bounded 12,000 ≈ 30+ days), published in state.json.
No behavior change. Every day without this is training data lost.

## Phase 1 — meta-model v0 (offline; when ~2 weeks of live fills exist)

- Model: L2-regularized logistic regression, MAX 8 features (the Phase-0 set), pure-python
  trainable (the bot is stdlib-only; coefficients get baked in as plain numbers).
- Data: pretrain on the 60d signal-level dataset (research data/cb5m.json construction, proxy
  outcomes), fine-tune on live oracle-settled measurement records.
- Validation: strictly walk-forward, 1h-block bootstrap.
- PASS BAR (pre-registered): must beat the bucketed qhat on out-of-sample Brier/log-loss with a
  CI that excludes zero improvement. If it cannot beat two buckets, STOP and say so — the
  research suggests this is a live possibility.

## Phase 2 — shadow deployment

- New zero-stake book `impulse_ml`: identical trigger/gate/cap/timing, sized by model
  probabilities through the same quarter-Kelly formula.
- Nightly coefficient retraining is allowed; PROMOTION decisions only at the 10-day cadence
  (FINAL-DESIGN §5.2: >=400 paired signals, 90% block-boot CI lower bound > 0, human sign-off).
  The red team proved faster loops chase noise.

## Phase 3 — reflexes

- Drift detection: Page-Hinkley test on the win-rate stream -> faster stake benching than the
  trailing-window guard tiers. Ships as an ops control, EV-neutral framing.
- Thompson sampling over stake fractions (quarter vs half vs eighth Kelly) as a smarter
  aggression dial. Shadow-first, same promotion bars.

## Phase 4 — gate learning (ONLY with evidence)

Learned P(reversal | context) proposing gate thresholds instead of fixed eff6>=0.10 / cnt12<=6.
Touches strategy structure, so highest overfit risk: long paired shadow vs the frozen gate,
promotion needs the full §5.2 bar plus a human review of what the model actually learned.

## Permanent guardrails

1. No deep nets, no LLM-in-the-loop scoring: thousands of samples, not millions.
2. No features the research explicitly killed (session filters, path shape, ETH confirm, ...)
   unless re-verified with new data.
3. Structure (trigger/cap/timing/hold-to-close) frozen; ML touches sizing first, gates last.
4. frozen_baseline shadow keeps scoring whether ANY learning pays (regret metric); regret
   < -$50 at day 30 freezes the learner (FINAL-DESIGN §5.6).
5. Everything promotes through shadow -> paired CI -> human sign-off. Nothing self-promotes.
6. Coefficients live in the bot as literals; training happens offline; the bot never trains.

## Status log

- 2026-07-10: Phase 0 shipped. Phases 1-4 awaiting user green light + data accrual.
