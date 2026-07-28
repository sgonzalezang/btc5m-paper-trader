# leader50 refinement hunt — and leader50z / leader50w, its pre-registered forward tests

**Date:** 2026-07-28 · **Status:** pre-registration (written BEFORE any twin forward data)
**Data:** 575 real leader50 paper fills + 938 oracle-confirmed leader signals (~14 days),
2.5x the 07-22 study. Five independent lenses (entry band, side, limit width,
timing/microstructure, calendar), every split stability-checked across data halves.

## One-line result
The only refinement that survived every cross-lens control is the **fill-slack tax**:
fills caught only because the limit allows +1¢ over the first quote (ask2 > ask1) are
stably toxic (−10.5pp, −$268, n=69, negative in both halves, both sides, every price
band). Dropping them leaves **+2.8pp / +$1,380** vs the blended +1.2pp / +$1,112.
Deployed as **`leader50z`** ("Leader Held"). A weekend effect earned a cheap second
test as **`leader50w`**. **Neither is armed for real money.**

## Why the slack tax is believable (not just mined)
A quote that ticks UP in the ~2.5–5s between signal and fill means the book is moving
away — you are the slow one reaching for a stale price. It is the miniature version of
the already-validated runaway lesson (chasing "ran" quotes loses −$812 at any width).
The gradient is monotone: quote improved > held > worsened. It survived controls for
entry price (negative in both the ≥64c and ≤63c slices), side, session, and latency.

## What was deployed (this commit)
- **`leader50z`** ("Leader Held"): records an identical copy of each leader50 fill ONLY
  when the re-poll quote held or improved (ask2 ≤ ask1) — the fills a limit of exactly
  ask1 (no +1¢ slack) would have taken. IDENTICAL booked prices/sizes/fees (the entry
  keeps the parent's +1¢ conservatism markup), so any edge gap between the twins is pure
  fill-SELECTION, never flattered pricing. Strict subset of leader50; ~88% of its fills.
- **`leader50w`** ("Leader Wknd"): identical copy of leader50 fills on Sat/Sun UTC only.
  Weekend fills ran +6.7pp (+$312), stable across halves, and +9.7pp even ex-Asia hours
  (so NOT the leader50s effect repackaged) — but only 4 weekend days of data (p≈0.38
  standalone). A cheap orthogonal test; idle Mon–Fri by construction.
- Both: paper/shadow, external, never orderable, no pings, generic settle path.

## PRE-REGISTERED decision rules (fixed 2026-07-28, before any twin data)
**leader50z** — judge on twin fills from after this deploy only:
- **CONFIRM the refinement** iff, at n ≥ **100** twin fills (~6 days): twin edge >
  concurrent blended leader50 edge over the same window, AND twin edge > 0 in both
  halves of its own window.
- **REFUTE** iff at n ≥ 100 the twin trails the parent or its edge ≤ 0.
- Two sub-metrics ride inside (flagged post-hoc, observation only until their own n):
  (a) fills at entry ≥ 64c — if that slice shows edge < 0 in both halves after n ≥ 40,
  pre-register a `min(ask1, 0.63)` cap twin THEN (not before);
  (b) fills landing 62–63c (the +10.9pp pocket) — judge nothing before n ≥ 80 pocket fills.
**leader50w** — judge on twin fills from after this deploy only:
- Evaluate at n ≥ **50** fills or **4 weekends**, whichever first. **KEEP** iff edge > 0
  overall AND the sign holds in ≥ 3 of 4 weekends; else retire the weekend idea.
- Do NOT move these bars. Do NOT arm real money on any leader book — the separate
  graduation bar (day-block bootstrap CI excluding zero) still governs that, unchanged.

## Tested and killed this hunt (do not re-propose without NEW evidence)
- **Down-vs-up side twin:** the fill-P&L gap (+$995 vs +$116) is fill-selection luck —
  the full 938-signal book is side-symmetric (63.9% vs 63.8%) and the gap sign-flips
  across halves. CORRECTS the 07-27 read that down was the engine.
- **Limit widening (+2c/+3c):** incremental fills stably −9.2pp; K=∞ loses −$416. The
  runaway stays a skip signal at every width. (With the slack tax, the true optimum
  looks like LESS slack, not more.)
- **0.58–0.64 band tighten, 56–58/60–62 buckets, entrySec gates, drift shaping, dtMs,
  held-vs-improved split, day-of-week gates, streak/drawdown structure:** all sign-flip
  across halves or collapse ex-Asia — noise at this n.
- **US-cash-session blackout (Mon–Fri 13:30–20:00 UTC, −3.1pp stable):** real-looking
  but the same "US-offline" hypothesis family as leader50s/leader50w — deferred until
  both those twins report, to avoid triple-counting one idea.
- **Cooling check:** leader50 is NOT cooling — daily-edge slope +0.42pp/day (p=0.46),
  second half of fills better than the first (+1.7 vs +0.8pp). The +1.8→+1.2 blended
  dilution is variance.

## Standing results this builds on
- 07-27 pre-registered side eval: BOTH sides cleared the survival bar (n≥40/side); the
  full-signal metric now flatters unfillable would-bes (+$1,292 of +$2,403) — actual
  fills +$1,112 are the honest number.
- leader50s (Asia twin): forward-testing since 07-23; at deploy time +1.9pp on n=48,
  running ahead of the parent. Its bar (n≥120) is unchanged by anything here.
- Chase path: REFUTED. Fade path (fade50): REFUTED (−$5,709). P&L-streak stand-downs:
  REFUTED (autocorr ≈ 0).

## Method
Analysis staged in scratchpad/edgehunt2/l50_refine.json (fills + full signal book with
both polls' quotes). 5-lens adversarial workflow + adjudicator with deconfounding
(overlap decomposition between the slack gate and the price cap; session controls on
every calendar cut). Stability = sign holds in both time halves; anything that failed
is listed as killed above regardless of pooled significance.
