# leader_v1 / leader50 — side-asymmetry watch

Ongoing research observation, opened 2026-07-13. Owner question that started it:
*"When the engine alerts and the price then moves down, should we not be wary of that?"*
Yes — and the answer generalized into a payoff-structure concern worth tracking.

Re-run the numbers any time: `python3 research/leader-v1-side-watch/track_leader_sides.py`
(reads live `bot/state.json`, writes a dated snapshot under `snapshots/`).

## What leader50 actually bets

leader50 buys the **leader side** — the direction BTC is *already* drifting (4–8bps) early
in the interval — when that side quotes **55–66¢**. So it is a **momentum / continuation**
bet on a small move, bought at a **favorite's price**. That is the opposite thesis from the
rest of the program (impulse_v2 and the reversal family *fade* moves), which is the first
reason for skepticism.

## The observation (first ~21 oracle-confirmed signals, all 2026-07-13)

- **Full-signal P&L (fills + would-be misses) is NEGATIVE (~−$112)**, even though the
  **actual filled P&L is POSITIVE (~+$35)**. The gap is **survivorship**: several of the
  worst signals never filled (the quote "ran"), so they cost no real money — but the
  would-be tracking shows they would have lost. The honest read of signal quality is the
  full-signal number, and it is under water.
- **Side skew:** the **up-leader** side is the weak one — ~50% win, ~−$103 full-signal.
  The **down-leader** side is better but no longer clearly positive (~64% win, ~−$9 after
  two more signals). Do not over-read either at this n.
- **Continuation ~57%** (small drifts continued to the close 57% of the time) — a slight
  momentum tilt, not reversion. But 57% is **not enough**, because of:
- **The payoff trap.** Buying at 55–66¢ means a win pays only ~+$30 on a $50 stake while a
  loss costs ~−$51. Break-even therefore needs roughly **58–62% wins**. A 50% up-side is
  deeply under water; a 57% blended rate still loses. This is structural, not noise.

## Sub-question: should we CHASE the quotes that "ran out of range"? (No.)

Owner asked 2026-07-13 whether the signals leader50 skips because the ask climbed past
its limit ("ran") are secretly winners worth entering. First n=6: **only 2/6 = 33% won**,
and simulating a chase **at the ran-up price loses −$157** (worse than the −$148 at the
pre-run price). Intuition says a climbing ask = momentum = winner; the data says the
opposite — a quote that keeps climbing in those 2–3 seconds is the market **overshooting
right before it snaps back**, i.e. a **reversal warning**. So the "re-poll, don't chase"
rule is a feature: it screens out leader50's worst signals, which is why the actual fills
(+$35) look better than the full-signal quality (−$112). **Do not add a chase path.**
Tracked in the same script (`ran_quotes` block); revisit if the chase P&L turns positive
over a much larger n, which would contradict the reversion mechanic.

## Promising sub-hypothesis: FADE the run-up (buy the opposite side)

Owner asked 2026-07-13: on a run-up, instead of chasing the leader, take the OPPOSITE side?
First n=7: opposite won **4/7 (57%)**, and the return is **+$168** (sensitivity +$123 to
+$183) — positive despite the middling win rate because the opposite side is CHEAP (~37¢)
when the leader ran to ~65¢, so break-even is only ~40%. This is the program's reversion
thesis reappearing: the overshoot snaps back, and you buy the snap-back cheap.

**This is the most promising thread in the leader family so far — but it is NOT validated:**
- n=7, in-sample, hypothesis-generated-from-the-data. One or two trades swing it.
- The opposite-side price is ESTIMATED as `1 − leader_bid2` (binary parity); we only polled
  the leader book. The true opposite ask has its own spread — at these prices a 1–2¢ error
  moves the P&L materially.

**INSTRUMENTED 2026-07-13 as `fade50`** (owner: "add both as the same shadow models — run
ups and run downs"). fade50 is a staked $50 paper engine that buys the OPPOSITE side of every
leader_v1 signal at the **real opposite-side book** (polled at re-poll time — fixes the parity
estimate), tagged **fadeUp** (faded an up-move → bought down) vs **fadeDown** (faded a
down-move → bought up) and by whether the leader ran. Both directions of the question are now
measured with true fills; see the `fade50_live` block in track_leader_sides.py and the Fade $50
card/line on the site.

**Pre-registered gate (unchanged):** evaluate at **n ≥ 30 fade50 fills per direction** or
2026-07-27. A direction graduates to consideration only with a positive full-signal P&L at
real prices AND win% above its break-even (≈40% at ~37¢ entries; recompute from actual avg
entry). Do not read the tiny early sample as an edge — the parity-estimate +$168 on n=7 was a
hypothesis, and fade50 exists to test it honestly. Stays paper / NEVER_ORDERABLE throughout.

## Pre-registered decision rule (set 2026-07-13, before more data — do not move)

- **Primary metric:** full-signal P&L and win% **per bet side** (incl. would-be). Do NOT
  switch to actual-fills-only — that is survivorship-biased and would flatter the engine.
- **Break-even bar:** win% ≥ **60%** on a side (derived from the 55–66¢ entry band, not
  chosen after the fact) AND positive full-signal P&L.
- **Sample gate:** evaluate each side at **n ≥ 40** oracle-confirmed signals for that side,
  or **2026-07-27** (≈2 weeks), whichever comes first.
- **Actions at the gate:**
  - up-leader still < break-even and negative full-signal P&L → **gate out up-leader
    alerts** (leader50 takes down-leader only), re-open the watch on the down side.
  - **both** sides < break-even at n ≥ 40 each → **retire the leader idea** (stop treating
    it as a live candidate; keep the book for the record).
  - a side clears the bar (≥60% AND positive) with n ≥ 40 → that side **graduates** to a
    real candidate for a staked paper book, re-verified first.
- **Throughout:** leader50 stays **$0-notional/paper** and **NEVER_ORDERABLE** on the
  executor — no real money is exposed while this resolves, regardless of the numbers.

## Why this is honest science, not a post-hoc story

The concern is mechanically grounded (momentum-on-small-drifts vs the program's reversion
findings + a fixed unfavorable payoff ratio from the entry band), the primary metric and
break-even bar are fixed **now**, and the sample gate is pre-committed so we cannot stop at
a flattering moment. The would-be ledger (separate from actual P&L by construction) is what
keeps the sample un-limited by our fill latency, so the hit-rate we judge is the signal's,
not our execution's.

## Snapshots

`snapshots/<heartbeat>.json` — one per run, so the series is auditable over time.
The first is `snapshots/20260713*.json`.
