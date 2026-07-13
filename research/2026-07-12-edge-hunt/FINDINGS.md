# BTC 5m Paper Trader — Edge Hunt FINDINGS (2026-07-12 round)

Synthesis of 9 analyst dimensions (autopsy, flagship, inverse, regime, micro, misses,
alphasweep, pricing, + merge) over the pooled 3,495-settled-trade ledger (Jul 7–13),
the 36-record measurement book, and 60+ days of candle history — followed by 3-lens
adversarial verification (integrity / selection / independent-repro) of the 8 merged
findings R1–R8. **All effects below are the verifier-CORRECTED numbers**, quoted
after the frozen cost model (EV/share = q − p − 0.07·p·(1−p), gas $0.004, fills =
ask + 1c). Verification artifacts: `work/verify/R{1..8}-{integrity,selection,repro}/results.json`.

Verdict tally: **R2, R4, R7, R8 CONFIRMED · R1, R3, R5, R6 WEAKENED · 0 refuted outright**
(R3's headline effect was refuted by one of three lenses; its measurement-first action survives).

---

## 1. Executive summary

**How much fee-clearing edge exists?** One level, small, uncertain, already deployed:

- The **gated contrarian LEVEL** remains the only confirmed fee-clearing signal:
  TEST (Jun 26–Jul 13) +4.55c/share, block-boot p=0.0035–0.0045, independently
  re-reproduced from scratch this round (R7-repro). But the honest **working central
  for the deployed arm is +0.75c/share first-poll / +1.71c/share as-operated (SE ~1.8–1.9)**
  after folding in the fresh Jul 10–13 window (R6, posterior arithmetic verified by all
  three lenses). The fresh window itself (−2.75c, n=52, CI90 ≈ [−13, +8]) is statistically
  uninformative — consistent with both zero and the TEST level — so "drought" was an
  over-read, but so would be any scale-up.
- The **gate INCREMENT is still unproven** (live −2.57c, perm p=0.79 at n=34/7; TEST
  +4.7c at p=0.05–0.11, optimistically biased by calibration overlap). Unchanged from
  the prior round's p≈0.13 verdict. (R7, CONFIRMED.)
- The flagship's **relative outperformance of its flat-$50 twin (+10.55c/share-signal,
  ledger-exact)** is real arithmetic but decomposes into ~+4c/signal of mechanical
  re-poll price improvement plus ~+6.6c/signal of 2-of-8 skip luck (exact binomial
  p=0.11); it is the **same phenomenon as the 48–53c toxic zone (R2), not an additive
  second edge**. Treat R1+R2 as ONE edge worth roughly +3–8 $/signal relative to
  naively taking first fills ≥48c. (R1 WEAKENED, R2 CONFIRMED.)
- The **48–53c fill zone never clears fees in any cut** (Wilson upper bound of q below
  q* in every era; interval-dedup point estimate −2.6c/share, statistically the pure
  fee/slip drag). Capping the buyable region below ~0.50 on flat arms is cost-avoidance,
  not alpha. (R2.)
- The one claimed NEW positive edge — **drift-leader stale-ask capture at 60–65c,
  +14c/share on paper** — did not survive: independent Polymarket snapshots show the
  bot's polled asks were stale exactly and only in the qualifying moments (~8c/share
  cheaper than the contemporaneous market); at prices the market actually displayed the
  state is worth ~0 to −3c/share after fees. Live tradability is unproven and plausibly
  zero; only a $0-stake fill-conformance engine can establish a real number. (R3.)
- The **pooled −$8.8k (−$12.0k including stopped trades) is transaction-cost structure
  with ZERO gross selection**: cost stack −3.29c/share vs gross selection at mid
  −0.48c/share (CI [−2.2, +1.3]) once the 70 stop-lossed trades (69/70 lost held-to-res)
  are restored. Residual 4-min continuation after a ≥2bps first-minute drift is 48.7–49.0%
  — momentum here is a mechanical head start with no forward information. Any future taker
  signal at 50c-class fills needs ~3.3c gross just to break even. (R5.)
- **Three verified bot-vs-spec deviations (R8) and a kill-metric semantics gap (R4)**
  are the most consequential findings of the round: the pre-registered day-14 kill reads
  a first-poll measurement book running −6.23c/share while the operated flagship runs
  +3.55c/share on the same signals — the kill becomes evaluable (~n≈205) right at day 14
  and would fire on a policy that is positive as operated. This must be amended before
  day 14.

**Bottom line:** no new deployable alpha was found this round. The round's value is
(a) execution economics — never take first fills ≥~48c; the f>0 per-poll Kelly check is
functionally a limit order and should be frozen as an explicit cap; (b) instrumentation
repairs that protect the pre-registered day-14/day-60 verdicts from firing on artifacts;
(c) a hardened set of invariants (cost hurdle ~3.3c gross; already-realized movement
carries no q). The honest program state: one small contrarian level, ~+1.7c/share
as-operated, riding on guards and a measurement protocol that this round just debugged.

---

## 2. CONFIRMED findings

### R2 — The 48–53c fill zone is fee-dead in every era; cap the buyable region below ~0.50
**Verdicts: CONFIRMED / WEAKENED / CONFIRMED.**
Artifacts: `work/autopsy/results.json` (q2_calibration), `work/pricing/ev_buckets.json`,
`work/misses/results.json`; verification `work/verify/R2-{integrity,selection,repro}/results.json`.

- Reproduced exactly by all three lenses: pooled 50–53c fills n=436, q=.4656 vs
  q*=.5282, **EV −6.26c/share trade-weighted** (1h-block boot CI [−12.0, −1.0],
  p≈0.010); trigger-family ≥50c −8.3c/share, era-stable (pre-v3 −9.2c, v3 −6 to −7c);
  clean v3-era-only OOS cut −18.6c (n=59, p=.045).
- **Corrected headline (quote this one): interval-dedup −2.6c/share (n=259 unique
  (t0,side), CI [−6.7, +1.1], p≈0.09)** — the −6.3c figure is inflated ~2.4x by
  multi-engine pile-ons on losing intervals, and at interval level the deficit is
  statistically indistinguishable from the −2.75c mechanical fee+slip drag of a
  zero-edge 51c fill. No demonstrated adverse selection beyond costs.
- What makes it CONFIRMED anyway: the zone shows **no evidence of clearing fees in any
  cut, era, dedup, or stress** (Wilson upper bound of q < q* trade-weighted; every
  estimand negative), and the [0.50, 0.53) bucket was **genuinely pre-registered** in
  the Jul-10 FINAL-DESIGN (§4.2 hi-bucket unsized at launch; §7 day-60 cap verdict;
  line 87 fillable-vs-unfillable direction) — not a scan winner. The live replication
  (fillable ≤53c won 15/35 vs cap-missed 10/12, Fisher p=0.016) reproduces exactly but
  is downgraded to suggestive: 11 of 12 cap-miss records also failed the first-45s
  window guard.
- **Action (stands):** `revEntryMax` → 0.4999 on flat staked arms; hi qhat bucket stays
  unsized; feeds the day-60 cap verdict toward CAP-DOWN. Expected value: avoiding a
  ~2.6c/share certain cost drag on every flat-arm fill in the zone — not the 6–9c
  originally claimed.

### R4 — Day-14 kill metric reads a book that diverges 9.8c/share from the operated arm
**Verdicts: CONFIRMED / CONFIRMED / CONFIRMED (3–0).**
Artifacts: `work/flagship/results.json` (measurement_book, kill_metric_tension);
verification `work/verify/R4-{integrity,selection,repro}/results.json`.

- Deterministic and fully reproduced by all three lenses: measurement book at
  first-poll cost = **−6.23c/share** (15/35, block CI90 ≈ [−15.4, +3.3]) vs operated
  flagship **+3.55c/share** (12/26 settled) on the same signals — **gap 9.79c/share**.
  All 12 "f_nonpos skip" records that were later entered are the SAME signal refilled
  ~11.2c cheaper (dup-guard forbids second triggers; side matches 12/12; 6/12 won,
  +8.43c/share realized). True never-entered: 3/9, −19.6c at first-poll cost.
- Reframed by verification: first-poll recording **is** the pre-registered MF6 design,
  so this is an **amendment request, not a bug** — except the first-poll `sized/skip`
  stamp genuinely violates MF6's own "skip is final at t0+45s" rule (code-vs-spec defect
  in `_measure_record`, btc5m_bot.py ~line 581). ~5.2c of the 9.8c gap is deterministic
  (re-poll price improvement); ~6.5c is the structurally expected gap under outcome
  exchangeability — either way >2x the −2c kill bar.
- Urgency is real: at 14.6 records/day the book reaches ~205 settled by day 14 — the
  kill becomes evaluable exactly at the kill date and **would fire on a policy whose
  operated book is positive**. The nightly guard tiers and the qhat learner read the
  SAME first-poll book, so the bias reaches guards and learning before it reaches the
  kill. (Note an unresolved tension: R4-selection expects guard n-minimums (~100–250)
  to arrive before day 14, while R8-integrity computes the 7d tier structurally
  unreachable at 14.6 signals/day (~102 < 120). Resolve by direct count when amending.)
- **Action (before day 14):** additionally record best-in-window fillable price (or
  realized fill) per t0; pre-commit in writing which book the day-14 kill reads; fix
  the sized/skip stamp to window-close semantics.

### R7 — Gate increment null on live fills; retention 0.72–0.83 outside the registered [0.40, 0.70] band — but the band itself was mis-registered
**Verdicts: CONFIRMED / WEAKENED / CONFIRMED.**
Artifacts: `work/flagship/results.json` (gate_verdict, gate_retention_conformance),
`work/regime/a3_results.json`, `work/alphasweep/gate_refresh.json`;
verification `work/verify/R7-{integrity,selection,repro}/results.json`.

- Live increment within the ungated control's own fills: gate-pass −7.79c (n=34) vs
  gate-reject −5.22c (n=7), **increment −2.57c, perm p=0.79** — reproduced to the cent
  by all three lenses. CI90 on the increment is [−35.7, +30.3]: read as *uninformative
  null*, not negative. TEST increment +4.7c at p=0.05–0.11 (and optimistically biased:
  A=0.10/B=6 was calibrated on a window overlapping TEST by ~15 days). The gated LEVEL
  on TEST (+4.55c, p≈0.004) survives every stress and was re-reproduced from scratch.
- Retention: candle 21d 0.72–0.73, live 0.758, and **0.83 by the bot's own logged
  decisions** — all above the band's 0.70 edge. The feared feed-vs-candle convention
  artifact exists but runs the wrong way to rescue conformance (all disagreements are
  bot-looser, cnt12 ±1 on borderline cascades).
- Key correction (R7-selection): the deployed A=0.10 gate already retained **0.714 on
  TEST before launch** — the [0.40, 0.70] band was anchored on the *A=0.32
  train-calibrated arm* (retention 0.41–0.52). The excursion is a **band
  mis-registration, not a regime shift and not a gate-code bug**.
- **Action:** log the conformance excursion with the mis-registration explanation;
  re-register the band around the deployed arm's design-time retention (~0.60–0.80);
  do NOT reset the Phase-0 clock, no gate-code hunt, no parameter change. Day-60 gate
  verdict will be underpowered at ~17–28% rejection mass (~3–4 rejected control fills
  per day) — plan the extension now.

### R8 — Bot deviates from the registered qhat spec in three verified ways; nightly/ops hazards
**Verdicts: CONFIRMED / CONFIRMED / CONFIRMED (3–0).**
Artifacts: `work/flagship/results.json` (qhat_reconciliation), `work/misses/results.json`
(bench_audit); verification `work/verify/R8-{integrity,selection,repro}/results.json`.

- No qhat *bug*: closed-form replication reproduces state qlo=0.5068 / qhi=0.5030 to
  4dp (one lagged-settlement boundary record explains the residual). But vs
  FINAL-DESIGN §4.2/§5.3/M2, verified verbatim by all three lenses:
  1. **Bucket boundary** is `cost<0.50` (≡ p_eff<~0.4825) vs registered `p_eff<0.50`;
  2. **Prior mass 400/bucket** (anchored at ledger-seed means) vs registered
     (w+100)/(n+200) — mass 200 at mean 0.5. Learning ~1.9x slower than registered,
     and currently **anti-conservative**: code qlo 0.5068 vs 0.4954 under the
     registered formula on the same data (~1.1c higher sizing threshold);
  3. **M2 guard seeding never implemented** (n=123 cohort located; its +2.75c
     net/share means no guard would have fired — counterfactual $0 to date);
  4. Bonus: code retains the 15d/−1c haircut tier that SC3 explicitly deleted, and the
     line-152 comment falsely claims MF2/MF3 conformance.
- Ops: the "restart flapping" is real but its nature is disputed between lenses —
  R8-integrity/repro count 7–10 stale nightly re-runs on Jul 10; R8-selection decodes
  the 10 anomalous loop_metrics lines as `--selftest` fixture output polluting the
  production log (live state never flapped). Either way: guard `nightly_tick` against
  pre-epoch rows and stop the self-test writing to the production log.
- Verified answer to the "does fixing mid-run corrupt the verdicts?" question: **no** —
  day-14/day-60 statistics consume raw measurement-book outcomes, never qhat; the fix
  flips ~0–3 marginal sizing decisions. Apply at the next human-reviewed refit with a
  dated changelog entry.
- New bookkeeping defect surfaced during verification (overlaps R4): 12/27 live
  flagship fills (44%) exist in the measurement book only as first-poll `f_nonpos`
  skips at costs they never paid — qhat never sees its real fill prices.

---

## 3. WEAKENED findings — and what would resolve each

### R1 — The f>0 quarter-Kelly rule as "the flagship's entire live edge"; freeze as ≤47c first-fill cap
**Verdicts: WEAKENED / WEAKENED / WEAKENED.**
Verification: `work/verify/R1-{integrity,selection,repro}/results.json`.

- The arithmetic is ledger-exact and was reproduced independently three times:
  +10.55c/share-signal vs the flat-$50 twin on the identical signal stream (n=34 t0s,
  26 common pairs — 12 filled ~11.1c cheaper with identical outcomes, 0 richer — plus
  8 skips that went 2/8; policy gap +$362; stake-size curve ≈ 0).
- Why weakened: (a) the "three independent confirmations" are the same 34 trades over
  2.55 days counted three ways; (b) the **price-improvement leg (~+4c/signal) is
  partially mechanical** — conditioned on a cheaper same-outcome fill the delta cannot
  be negative — and 28% of it is one 37.9c pair; (c) the **skip leg (~+6.6c/signal) is
  2-of-8 luck**: exact binomial p=0.109–0.145; the published p=0.034 was an iid
  bootstrap artifact; (d) honest block-boot CI on the total marginally includes zero
  ([−0.2, +19.1], one-sided p≈0.027–0.06 depending on block size); (e) **100% of the
  active events occur at twin entry ≥48–49c — R1 is R2's toxic zone expressed through
  the f>0 rule**, not an additive edge; (f) the flagship's ABSOLUTE book is
  indistinguishable from zero (+3.55c/share, n=26, CI90 [−9.7, +16.1]).
- **Corrected effect: +4 to +6c/share-signal expected** (mechanical re-poll improvement
  +2.8–3.9c + skip avoidance +1.0–1.5c under pooled rich-fill q≈0.47–0.49); sign robust
  to drop-best-day, chrono halves, 96%+ of half-samples.
- The **action survives all three lenses**: an explicit hard first-fill ask cap
  (~47–48c; jitter-robust: 47/48/49c caps yield +$253/+$254/+$202 vs take-all on the
  same signals) in ENGINE_CFG, independent of learned qhat — because nothing currently
  prevents nightly qhat drift from silently re-opening 48–53c first fills
  (bucketing at btc5m_bot.py ~line 564 confirmed).
- **What would resolve it:** nothing to wait for — it's a zero-cost risk control; the
  underlying edge question is subsumed by R2's pre-registered day-60 cap verdict and
  the growing measurement book (n≈200 by day 14). Do not double-count R1 and R2.

### R3 — Drift-leader stale-ask capture at [0.60, 0.65): +14c/share on paper
**Verdicts: REFUTED / WEAKENED / WEAKENED.**
Verification: `work/verify/R3-{integrity,selection,repro}/results.json`.

- In-sample paper number reproduces exactly (n=71/89 dedup intervals, q≈0.79–0.82,
  +14.0–14.3c/share, Jul 7–10 only) and its sign survives every internal stress.
- Why it fails as a deployable edge: (a) **independent PM snapshots show the bot's
  polled ask was ~7.7c/share cheaper than the contemporaneous market ONLY in the
  qualifying drift≥4bps state** (every other drift bucket: bot pays at/above snapshot)
  — the edge is quote staleness in the 8s-fresh REST book during impulses, i.e. a
  cancel-race a taker likely loses; the market prices the same state at .72–.78 where
  realized EV is −0.7 to −2.9c/share; (b) the 60c lower boundary is overfit (59–60c
  aligned trades are q=.368, −24c — a 1c step can't flip q by 42pp); (c) drift
  recomputed from strictly-pre-decision candle opens retains only 19/71 members at
  +4.4c, p=0.17; (d) 100% momentum-era (4 days), zero possible v3-era sample; (e) the
  pooled 60–66c band loses (−1.3c, n≈1,250) — only the paper-fill carve wins.
- **Corrected effect:** at ledger fills, +4–7c/share for edge-robust variants
  (execution-unverified, in-sample); at market-displayed prices, **~0 to −3c/share**.
- **What would resolve it:** the finding's own action — a **$0-stake `leader_v1`
  measurement engine** logging would-be fills against the live book, promoted only if
  live fill conformance at sub-market asks is demonstrated. Do not size anything on the
  +14c figure.

### R5 — Pooled loss is cost structure; momentum trigger had zero residual information
**Verdicts: WEAKENED / WEAKENED / WEAKENED (core strengthened, one leg refuted).**
Verification: `work/verify/R5-{integrity,selection,repro}/results.json`.

- Confirmed and stress-proof: **cost stack −3.29c/share** (fee −1.68, slip −1.11,
  half-spread −0.50; the 1c spread assumption verified in ~94% of 1,588 real logged
  books); accounting identity reconciles to <0.5c; **residual 4-minute continuation
  after a ≥2bps first-minute drift = 48.7–49.0%** (CI [.469, .506], n≈2,840),
  replicating on fresh Jul 10–13 data — the trigger's 72% full-interval "win rate" is
  entirely the already-banked head start.
- Refuted leg: "**positive gross selection at mid (+0.55c)**" was a survivorship
  artifact — the pool excluded 70 stop-lossed trades whose hold-to-resolution outcomes
  (recovered from candles) were 1/70 wins, while including 71 late profit-lock hedges.
  Symmetric universe (n=3,565): **gross selection at mid −0.48c/share (CI [−2.2, +1.3])
  — statistically zero**; at the ask, ~0 to −1c. "Signals were right, prices were
  fatal" collapses to "signals carried no information relative to the standing quote."
  Full settled ledger is −$11,982, not −$8.8k. The ≥8bps "mild reversal" flavor
  (45.7%) does not survive K=3 correction and flips on fresh data.
- **Surviving invariants (use these):** reject any engine whose qhat is
  already-realized movement; a taker signal at 50c-class fills needs **~3.3c gross**;
  fill-price work beats signal work; no exploitable fade either (residual never
  significantly below 50%).
- **What would resolve it:** nothing — this is a completed autopsy. The corrected
  version is *stronger* for the program's architecture than the original claim.

### R6 — "Fresh-window drought / weekly non-stationarity"
**Verdicts: WEAKENED / WEAKENED / CONFIRMED.**
Verification: `work/verify/R6-{integrity,selection,repro}/results.json`.

- All numbers replicate exactly (gated fresh −2.75c n=52; a3 construction −6.08c n=60;
  impulse50 −7.8c, reversal_v2 −7.2c; weekly table; posterior 0.75/1.71c).
- Why weakened: (a) the window is **statistically uninformative** — CI90 ≈ [−13, +8]
  contains both 0 and TEST's +4.5c; 18–31% of same-size historical windows were at
  least as bad (placebo scan); (b) the "corroborating" live books are the same ~50–80
  intervals read four ways, and excluding launch-day Jul 10 they run near-flat
  (impulse50 −4.0c, reversal_v2 −1.9c, flagship +7.5c); the "−13.97c worst day" was
  the UNGATED series (gated Jul 10 was −4.26c, rank 12/64); (c) **"strongly
  non-stationary" fails a permutation test** (weekly SD 3.3c vs stationary null 2.7c,
  p=0.23–0.28) — dispersion is explained by sampling noise, though TEST's +4.5c is
  genuinely concentrated (~84% in 2 weeks).
- **Corrected read:** *no evidence of fee-clearing edge in the fresh window* — not
  proven edge death. **Working central: +0.75c/share first-poll / +1.71c/share
  as-operated (SE ~1.8–1.9)** — verified arithmetic, quote this everywhere.
- The conservative **actions stand on small-n grounds**: no stake scale-up off pooled
  TEST estimates, keep 7d haircut armed, plan the day-60 verdict extension.
- **What would resolve it:** data. At ~13–15 gated signals/day, ±2c/share resolution
  needs ~4–6 more weeks of the measurement book. The pre-registered day-14/day-60
  machinery (once R4 is amended) is the arbiter; no new experiment needed.

---

## 4. KILLED findings and dead ends (do not re-hunt)

One line each; sources in parentheses. Full statistics in each analyst's results.json.

**Signal-family sweeps (alphasweep; K_grid=204 fully counted, TRAIN→TEST discipline):**
1. Multi-lag raw momentum/reversal (5–60m × 2–30bps, 48 cells) — best pick decays to +0.61c p=0.32 TEST.
2. Vol-normalized momentum/reversal (40 cells) — best TRAIN survivor collapses to +0.49c p=0.43.
3. 5m×15m sign-interaction ± vol split — all TRAIN-negative.
4. Binance−Coinbase 1-interval gap — dead both directions; no 5m lead.
5. Perp premium CHANGE — significantly negative both splits; premium LEVEL percentile — sign flip.
6. OI 5m/15m delta combos — best TEST −0.35c.
7. ETH lead standalone (16 cells) — confirmed dead; ETH-BTC divergence fade — TRAIN→TEST sign flip (terminal).
8. Volume-spike reversal — never significant; shadow-grade at best.
9. Close-location-value and wick-dominance extremes — TRAIN→TEST sign flips (terminal).
10. Intra-1m path features; trigger-backloading increment — all decay OOS.

**Ledger autopsies (autopsy / inverse / micro / misses / pricing):**
11. Side/tie-rule asymmetry as filter — z=1.44 pooled, sign flips at 48–52c.
12. Price-level-only entry filters — no 5c bucket clears q*(p) at 95%.
13. "q is flat in price" hypothesis — rejected; q rises .416→.645 across buckets; only miscalibration is q<p at 50–60c.
14. Inverting any retired engine (all 5 + pooled, K=234 rescue cells) — pooled −2.81c; best raw p=0.016 → Bonferroni 1.0.
15. Momentum with ≤50c cap (+4.28c, p=0.09) and fade-inverted ≤50c (+4.04c, p=0.21) — in-sample noise, not deployable.
16. Resurrecting >65c entries — prior TRAIN→TEST kill stands; 65–70c bucket is "market fully agrees" selection.
17. Up-side-only cheap cells — dies under multiplicity; no up-rate asymmetry (.499–.512).
18. Vol-regime terciles as fade filter — ordering flips TRAIN→TEST (re-kill with fresh data).
19. latentfire eff12≤0.48 gate — adds nothing; retirement stands.
20. Funding sign-flips, funding extremes, OI extremes, premium sign — all sign-flip or CI-spanning-zero across splits.
21. Sign autocorrelation lags 2–12 — nothing stable; lag-1 is the only structure and it's fee-dead unconditioned.
22. passCount margin / need+1 revival — win rate monotone in margin but the book prices it faster; every need+1 subset fee-negative.
23. Pre-trigger 1m shape (K=8 splits) — TRAIN and TEST disagree; noise by the program's own bar.
24. Partial fills as informed-book signal — n=3 of 3,481; no sample at $50 stakes.
25. Limit-at-mid — untestable offline (mids move median 14c intra-window; adverse-selection-preferential fills); requires a $0 maker shadow book.
26. Pooled 30–45s entrySec bump — composition artifact.
27. Gate increment on live fills (both constructions) — null; see R7.
28. Non-cap guard loosening — wide-spread misses went 0/5 (guards SAVE money); no trade exists.
29. Taking the 48–53c band at first poll — −10 to −20c/share in every view; only the refill path through it is positive (R1/R2).
30. Executor/emit leak — none; signals.log↔ledger 1:1.
31. Bench-cost counterfactual — $0 (arm was never benched; brief's premise was stale).
32. Better entry second within interval — mid-interval cheapness is adverse-selection bait (q collapses to .32–.33); first-45s window stands.
33. Blind favorite-side at 60s — refuted by 1,841 real momentum fills at 55–66c.
34. Near-tie avoidance — trigger already cuts incidence; nothing to save at sub-49c fills.
35. "Ties resolve Up" freebie — P(up | |move|<1bp)=.447; no bias.
36. Trading cap-rejected high-q signals — 53–55c marginal band runs q=.433, −12.9c; no monetizing construction found.
37. Momentum 2–4bps drift class — re-confirmed fee-dead on the live ledger.
38. Drift-leader at 60–65c as a SIZED strategy — see R3: paper-fill artifact; measurement-only.
39. CAP verdict 55c-vs-53c on current data — confounded (window differs); n=8 pure subset; wait for day 60.
40. Variable-stake modulation (the Kelly stake SIZE itself) — +$6 of $362; the value is the price threshold, not the curve.

---

## 5. Reconciliation with the 2026-07-10 program (FINAL-DESIGN §0)

What the fresh Jul 10–13 data and the pooled ledger did to each prior pillar:

| Prior-round position | This round's verdict |
|---|---|
| Gated LEVEL clears fees on TEST (+4.02c → deployable +1.5–3c) | **Re-confirmed** from scratch (+4.55c, p≈0.004, robust to stresses). But the deployable central drops: **posterior +0.75c first-poll / +1.71c as-operated (SE ~1.8–1.9)** after the uninformative-to-negative fresh window. Within the prior round's stated range at its low end. |
| Gate INCREMENT unproven (p≈0.13) | **Unchanged-to-worse**: live increment −2.57c (p=0.79, n=41); TEST +4.7c (p=0.05–0.11, biased by calibration overlap). Day-60 verdict will be underpowered at current ~25% rejection mass — plan extension. |
| Quarter-Kelly dominance | **Confirmed in a sharper form**: the value is not the stake curve (~$6 of $362) but the f>0 per-poll check acting as an implicit limit order that skips/refills rich first quotes. Freeze it as an explicit ≤47–48c first-fill cap (R1). |
| Fill model .45/.49/.51 at 53c cap | Consistent with live fills; but the measurement book's first-poll semantics divorces recorded costs from real fills on 44% of entries (R4/R8) — amend before the anchors matter. |
| §1 unresolved contradiction on price-informativeness (cheap vs expensive fills) | **Resolved in the cap-down direction**: ≥50c is fee-dead in every era and cut (R2); all measured edge lives at effective entries <0.50 (pricing: q=.482 at mean fill .430 = +3.6c/share). The verify-regime "expensive fills win more" reading was the unfillable-side selection. |
| MF2 bucketed qhat, MF6 measurement book, M2 seeding, SC3 guard collapse | **Implementation drifted from registration** (R8): boundary cost<0.50 vs p_eff<0.50, prior mass 400 vs 200 (anti-conservative ~1.1c today), M2 never coded, deleted 15d tier still present. None corrupts the verdicts if fixed with a dated note; leaving them is worse. |
| Phase-0 retention band [0.40, 0.70] | **Mis-registered** against the A=0.32 arm; deployed arm's own pre-launch TEST retention was 0.714. Re-register ~0.60–0.80; no clock reset (R7). |
| Phase-1 kill (mean ≤ −2c on measurement book) | **Would currently fire on a positive policy** (book −6.23c vs operated +3.55c, gap structural ~5–6.5c). Amend the book before day 14 (R4). |
| "Momentum head start" architecture rationale | **Strengthened**: residual continuation 48.7–49% and gross selection ≈ 0 at mid (R5) independently corroborate the cheap-contrarian design and the never-pay-for-realized-movement invariant. |

---

## 6. DEPLOYMENT RECOMMENDATIONS (owner actions — this hunt modified nothing live)

Ranked by expected value ÷ risk. The live bot must not be touched by researchers.

### Tier 1 — CHANGE NOW (instrumentation & risk controls; no edge bet, no verdict corruption)

1. **[R4 — before day 14, hard deadline]** Amend the measurement book to also record
   the best in-window fillable price (or the realized fill) per t0, alongside the
   first-poll cost; fix the `sized/skip` stamp to MF6's window-close semantics
   (`_measure_record`, ~line 581); **pre-commit in writing which book the day-14 kill
   reads.** EV: prevents a likely false kill of a policy that is +3.55c/share as
   operated (kill input currently −6.23c/share, gap ~9.8c of which ~5–6.5c is
   structural). Risk: none — additive logging plus a dated protocol amendment.
2. **[R1 — zero-cost safeguard]** Add an explicit first-fill ask cap (~0.47) to
   impulse_v2's ENGINE_CFG, independent of learned qhat. EV: freezes the behavior
   worth ~+4–6c/share-signal vs taking rich first fills, and closes the verified
   loophole where nightly qhat drift silently re-opens 48–53c first fills. Risk:
   negligible (cap 47/48/49c all jitter-robust on the observed signals).
3. **[R2]** Set `revEntryMax = 0.4999` on flat staked arms (if the protocol requires
   reversal_v2 to remain an unmodified control, apply to any future flat arm and let
   the pre-registered day-60 cap verdict decide the control). EV: avoids a ~2.6c/share
   certain cost drag; the ≥50c zone clears fees in no cut of any era. Risk: none
   demonstrated (no positive evidence anywhere ≥50c).
4. **[R8]** At the next human-reviewed refit, with a dated changelog entry: prior mass
   400→200 per bucket anchored at mean 0.5 (registered formula); bucket boundary
   cost<0.50 → p_eff<0.50 (or document the deviation); remove the deleted 15d haircut
   tier; fix the false conformance comment; guard `nightly_tick` against pre-epoch
   rows and stop `--selftest` writing to the production loop_metrics. Verified: none
   of this corrupts day-14/day-60 (verdicts never read qhat). EV: removes an
   anti-conservative ~1.1c sizing-threshold inflation and halves learning lag.
5. **[R7]** Log the Phase-0 retention excursion as a band mis-registration
   (band anchored on the A=0.32 arm); re-register ~0.60–0.80 around the deployed arm's
   design-time retention. Do NOT reset the Phase-0 clock; no gate-code hunt; no
   parameter change. Also implement or explicitly pre-register-as-inert the M2 guard
   seeding, and resolve the R4/R8 disagreement on whether the 7d haircut tier
   (min 120 signals) is reachable at ~14.6 signals/day — if not, either lower the
   min-n with a dated note or accept and document that the kill is the only live guard.

### Tier 2 — SHADOW FIRST (measurement before money)

6. **[R3]** Deploy `leader_v1` as a **$0-stake measurement engine**: log the live book
   at drift≥4bps moments and record would-be fills vs the contemporaneous displayed
   ask. Promote ONLY if live fill conformance at sub-market asks is demonstrated.
   Expected live edge is ~0 to −3c/share at market-displayed prices; the paper +14c is
   a stale-quote artifact — treat any positive live conformance as a surprise to be
   re-verified, not confirmation.
7. **[micro/misses logging gap]** Add ask + eval-timestamp to miss/skip ring-buffer
   records (one line). This round's cap questions were unanswerable largely for lack
   of this field.

### Tier 3 — WAIT FOR n (no action; the pre-registered machinery is the arbiter)

8. **No stake scale-up** off pooled TEST estimates (R6): working central is
   +1.7c/share as-operated with SE ~1.9 — the fresh window cannot distinguish the arm
   from zero. Keep the 7d haircut armed; keep quarter-Kelly frozen.
9. **Day-60 cap verdict** (53c vs 55c) — currently confounded and n=8; do not decide
   early. R2's evidence pre-answers it toward CAP-DOWN; let the verdict confirm.
10. **Gate increment** — day-60 will be underpowered (~25% rejection mass); plan a
    pre-registered extension (e.g., day-90) NOW so the extension is not a post-hoc
    choice. No gate parameter changes meanwhile.
11. **No new standalone-signal sweeps over the same 60d window** (alphasweep
    meta-finding): every TEST-positive near-miss is the one contrarian regime factor
    already monetized; marginal return of further search ≈ 0. Next search should wait
    for materially new data or new data *types* (e.g., real book depth, maker fills).

---

## 7. Data appendix

| Dataset | Path | Coverage | Notes |
|---|---|---|---|
| Unified trade ledger | `research/2026-07-12-edge-hunt/data/trades_unified.json` | Jul 7–13, 3,576 rows (3,495 settled win/loss, 70 stopped, 11 open/other) | Deduped across `_src`; pnl reproduces frozen cost model to <$0.005; **`stopped` rows have btcClose=null — restoring their hold-to-res outcomes from candles is REQUIRED for any selection claim (R5)**; 71 hedge-flagged rows condition on late winners. |
| Bot state extract | `research/2026-07-12-edge-hunt/data/state_extract.json` | Live v3 state as of Jul 13 | 36 measurement records — **first-poll semantics: `sized=false` does NOT mean no trade (12/21 f_nonpos skips were filled later, cheaper); always join to the ledger by t0** (R4). benched=false throughout (task brief's "benched" premise was stale). |
| Coinbase 1m | `data/cb1m.json` | Jun 26 → Jul 13 03:40 UTC | Proxy for PM resolution agrees ~97.2% (validated vs 3,495 settles); sub-2bps intervals are the disagreement mass. Starts Jun 26 — no TRAIN-era 1m data. |
| Coinbase 5m / ETH 5m | `data/cb5m.json`, `data/eth5m.json` | May 11 → Jul 13 | Basis of TRAIN(May 11–Jun 25)/TEST(Jun 26–Jul 13) split; 18,045 contiguous intervals. |
| Binance 5m | `2026-07-10-edge-hunt/data/bn5m.json` | **ends Jul 10** | Binance fapi georestricted for refresh. |
| OI / funding / premium | `2026-07-10-edge-hunt/data/oi5m.json`, `funding.json`, `premium5m.json` | **OI/premium end Jul 9–10**; funding extended to Jul 13 via Deribit public API (`work/regime/funding_fresh.json`) | Premium negative ~99% of era — sign untestable. |
| PM resolutions | `2026-07-10-edge-hunt/data/pm_res_3d.json` + ledger settles | 863 + 3,490 = 1,078-market truth map | Used by pricing as the resolution oracle. |
| PM price snapshots | `2026-07-10-edge-hunt/data/pm_prices_sample.json` | 20/60/150s grid, sparse | Semantics mid/last-trade assumed; this dataset is what killed R3's fill realism — **collect denser book snapshots before trusting any paper fill above ~55c in fast markets**. |
| signals.log | `bot/signals.log` | fired trades only, 1:1 with ledger | Sole unique content: the bid (spread). Not a de-censoring source. |
| Verification | `work/verify/R{1..8}-{integrity,selection,repro}/` | 24 artifact sets | The corrected numbers in this report come from these files. |

**Known gaps for the next round:** no book-depth history; no maker-side data (limit-at-mid
untestable); miss records lack ask/timestamp (fix #7 above); Binance/OI/premium frozen at
Jul 9–10; cb1m has no TRAIN era; everything live-era is ~2.5–6 days — every live claim in
this report is n≲60 per book and priced accordingly.

---

*Synthesis: 2026-07-12 round. Honest > impressive. The corrected effects herein supersede
the analysts' original numbers wherever a verifier adjusted them.*
