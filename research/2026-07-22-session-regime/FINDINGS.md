# The session (time-of-day) regime — and leader50s, its pre-registered forward test

**Date:** 2026-07-22 · **Status:** pre-registration (written BEFORE any leader50s forward data)

## One-line result
Of every regime signal we tested for leader50, the **only** one that survived an
out-of-sample stability check is the **clock**: leader50's edge is an **Asia-session**
phenomenon. In-spec (0.55–0.66 entries) it wins **+10.8pp in 00–08 UTC** and **loses
−4.9pp in the US afternoon (16–24 UTC)**. We deploy `leader50s` — leader50 gated to
00–08 UTC — as a **paper/shadow** forward test. **Not armed for real money.**

## How we got here
The question was the owner's: *build an "awareness system" that recognizes bad regimes
and stands down.* A 4-lens feasibility panel (2026-07-22) tested four conditioning
signals on the leader50 out-of-sample forward window (n=351, trades after the
2026-07-15 pre-registration boundary):

1. **P&L-streak / downturn detector** (the literal ask) — **DEAD.** Per-trade win/loss
   autocorrelation ≈ **−0.065** (streaks carry no memory). Every "stand down after
   recent losses" variant **lost $200–600** vs always-on. Concretely, a "stop after two
   losing days" rule would have skipped **07-17 (+$660)**, the single best day.
2. **Volatility regime** — noise. The tercile ranking **inverts** between the two data
   halves (high-vol best in H1, worst in H2); also time-confounded.
3. **Trend / chop (efficiency ratio)** — noise. No stable separation across halves.
4. **Session / time-of-day** — **SURVIVED.** The one stable axis.

## The finding (leader50 forward window, in-spec 0.55–0.66 fills)
| Session (UTC) | n | win% | edge | P&L |
|---|---|---|---|---|
| **Asia 00–08** | 72 | 73.6 | **+10.8pp** | **+$604** |
| EU 08–16 | 122 | 63.9 | +1.7pp (noise) | +$275 |
| **US 16–24** | 66 | 57.6 | **−4.9pp** | **−$154** |

- **Stable:** Asia positive and US negative in **both halves** under two split methods,
  and Asia positive on **7 of 8** UTC days — not one lucky day.
- **Not a fill artifact:** the effect is **stronger** on in-spec fills (+10.8pp) than on
  all fills (+8.2pp); the off-spec cheap winners are spread across sessions, not clustered
  in Asia. So it is the clock, not a handful of cheap fills.
- **Causally plausible:** BTC flow/vol differs by session; a small early drift may carry
  further in the Asia book than in the noisier US afternoon.

## The honest caveats (why forward-test, not arm)
- **Borderline significance.** Asia edge one-sided p ≈ **0.032**; Asia-vs-rest p ≈
  **0.057**; per-half Asia n as low as 46. On ~9 calendar days this marginally clears zero.
- **The panel explicitly advised against a HARD real-money gate** on this sample — a
  binary "Asia-only" rule risks repeating the stop-after-losses overfit and forfeits the
  ~break-even EU book. For **real money** the eventual form is a soft **size-tilt**
  (up-size Asia, trim the US-afternoon hours 13–16/19/22, EU flat), never a skip-gate,
  never a P&L-streak stand-down.
- **A shadow twin is the right experiment though:** a clean Asia-only gate on **paper**
  isolates the hypothesis with zero real-money risk. That is `leader50s`.
- **Practical note for the operator:** Mexico is UTC−6, so the winning Asia window is
  ~18:00–02:00 local and the losing US window is ~10:00–18:00 local (the daytime hours).

## What was deployed (main @ this commit)
- **`leader50s`** ("Leader Asia"): records an **identical copy** of every leader50 fill
  (same side/price/size/fee) **only when the interval's UTC hour ∈ [0,8)**; stands down
  otherwise. A strict **subset** of leader50 with **zero price divergence**, so any P&L
  gap between the two curves is the **clock alone**. Flat $50, hold to close,
  **shadow/paper**, never orderable (`_leader50sess_clone`, not `evaluate()`).
- Website: `leader50s` added to the display (amber); the heavy-negative / dead engines
  retired from the chart in the same push (display only — they keep trading in the bot).

## PRE-REGISTERED decision rule (fixed 2026-07-22, before any leader50s forward data)
Judge `leader50s` on its trades from **after this deploy only**. It is a **relative** test
against its own parent over the same window (that is what isolates the session effect):

- **GRADUATE the session tilt to a live candidate** iff ALL of:
  1. `leader50s` n ≥ **120** (Asia-only accrues ~⅓ leader50's rate), AND
  2. `leader50s` realized edge > 0, AND
  3. a **day-block bootstrap 95% CI on `leader50s`'s edge excludes zero**, AND
  4. over the same post-deploy window, **`leader50s` edge > all-hours `leader50` edge**
     (the gate must actually beat trading every hour — else the session split was noise).
- **RETIRE the hypothesis** iff after n ≥ 120 the CI includes/sits below zero, or condition
  (4) fails.
- Do **NOT** let this backtest move the bar. Do **NOT** arm real money before GRADUATE.
- On GRADUATE, the real-money form is a **size-tilt, not a hard gate**, sized as if the
  true session edge is **half** the observed one.

## Method files
Feasibility panel + verification: `scratchpad/edgehunt2/` (leader50_ledger.json, candle
data, lens scripts). Regime autocorrelation, session-by-half stability, and in-spec/off-spec
decomposition all reproduced here.
