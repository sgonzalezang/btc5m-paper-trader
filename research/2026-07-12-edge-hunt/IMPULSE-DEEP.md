# IMPULSE-DEEP — Wave 2 (Deepening) Definitive Report

**Program:** btc5m edge program, wave 2 (2026-07-13). Base strategy: `impulse_v2` as deployed
(wave 1 settled engine choice; see `research/2026-07-12-edge-hunt/FINDINGS.md`).
**Units:** dataset / patches / qhat / metamodel / params — each independently built and then
adversarially verified by two lenses. **All five units: CONFIRMED (10/10 verifier votes).**
Numbers below are the verifier-corrected values; corrections that changed a unit's own quoted
figure are marked ⚠.

Nothing live was modified by this wave. All deployment is owner action, gated by the
no-deploy-without-approval rule.

---

## 1. Executive summary

**Wave 2 found no new alpha — and confirms that none was hiding in the flagship's own
parameters.** What it delivers instead is (a) a canonical, exactly-validated 60-day signal
dataset; (b) a tested, replay-verified 5-patch set that fixes every wave-1 CONFIRMED defect
(R4 kill-metric semantics, R8 spec deviations, restart-flap/log pollution) plus the two
pre-registered zero-cost risk controls (≤47c first-fill cap, leader_v1 $0-stake shadow);
(c) proof that the qhat calibrator, the gate parameters, the entry cap and the entry window
are all sitting on plateaus whose every loosening direction is a cliff; and (d) a
pre-registered FAIL on the ML meta-model — the 8 candle-derivable context features carry
zero out-of-sample information beyond a trailing base rate.

**What makes impulse_v2 better, by how much (verified):**

- **P1 (R4 amendment)** prevents the day-14 kill from firing on first-poll costs that run
  −6.23c/sh while the operated arm runs positive (+3.55c/sh on its own 26 settled fills).
  Reproduced exactly by both verifiers. This is protective value, not new EV — but it is the
  single highest-stakes item: the kill becomes evaluable near day 14 and, unamended, reads a
  book biased ~5–6.5c/sh structurally against the policy.
- **P2 (R8 conformance, prior 400→200 at mean 0.5)** removes a verified ~1.1c
  anti-conservative sizing-threshold inflation and halves qhat learning lag. Live effect
  today: qlo 0.5068→~0.495, sized boundary tightens (first-fill ask ≲0.466), ~6.1→4.9
  sized/day, 3 flipped decisions at mean −0.25c/sh — an EV wash that closes exactly the
  cost window wave-1 R2 proved fee-dead. The metamodel unit independently corroborated this
  is where the only measurable calibration gain lives (intercept-only trailing mean nearly
  beats deployed qhat, p_boot ≈ .036, mechanism = prior shrinkage lag).
- **P4 (firstFillMax = 0.47)** is behaviorally null today (0/26 flagship fills, 0/36 sized
  book records affected — the f>0 rule already caps at ask ~.47) and permanently forecloses
  the verified loophole where nightly qhat drift to the 0.56 ceiling would re-open 48–53c
  first fills worth −10 to −13c/sh each (R2 zone, fee-dead in every era and cut).
- **Everything else stays frozen.** revThr 12bps / eff6Min 0.10 / cnt12Max 6 /
  revEntryMax 0.53 / revWinMin 255 (45s): 40 swept cells (K fully counted), no cell
  dominates the frozen point on both TRAIN and TEST; every loosening is a bootstrap-
  significant cliff; every tightening is per-share noise that loses total-$. The 0.56 qhat
  cap never binds any conforming calibrator over 63 nightly replays. The meta-model does not
  open Phase 2.

**Honest edge posterior (unchanged by this wave):** working central for the deployed arm
**+0.75c/sh first-poll / +1.71c/sh as-operated, SE ~1.9** (wave-1 R6, re-affirmed). The 60d
candle bed's TEST level (+6.76c/sh ex-tie, $163/day mid at frozen anchors) is the optimistic
pole and rides a TEST-era q run-up (.5700 ex-tie) that no estimator is entitled to
extrapolate. No scale-up is justified; the applied patch set changes expected $/day by ≈ $0
as-operated and exists to protect verdict integrity and cap tail leaks.

**One adjudication this synthesis makes:** the patches unit implemented the registered
`p_eff<0.50` bucket boundary; the qhat unit then proved (confirmed by both its verifiers,
with an R2-consistent stress test) that the deployed `cost<0.50` boundary is the *better*
design — it quarantines the fee-dead .49-anchor fills in the hi bucket instead of letting
them drag qlo down. Wave-1 Tier-1 #4 explicitly allowed "or document the deviation."
**Resolution: apply P2 with the bucket-boundary hunk reverted (keep `cost<0.50`, add the
dated deviation note); adopt all other P2 components as shipped.** This is exactly the qhat
unit's recommended `hybrid_cost_M200` configuration. See §3.

---

## 2. Per-unit results

### 2.1 dataset — CONFIRMED (2/2)

**Deliverable:** `work-deepen/dataset/signals_60d.json` (+ `README.md`, `build_signals.py`,
`validation.json`) — a line-faithful port of the bot's trigger+gate pipeline over cb5m
May 11 → Jul 13.

**Verified numbers:** 18,044 rows; 4,102 triggers; 2,802 gate-passes (2,015 TRAIN / 787
TEST); 182 gated ties (6.5%); gated q ex-tie .5489 pooled / .5408 TRAIN / .5700 TEST
(ties-as-loss .5132 / .5097 / .5222). cb5m has zero candle gaps (independently audited);
gateReady 18,032/18,044. Both verifiers reproduced **every decision bit across all 18,044
rows** with independent implementations, not just the tasked 200-row sample.

**Key facts wave 2 rests on:**
- **Prior-program reconciliation is EXACT.** ⚠ Correction: the q residual is ZERO, not
  −0.0008 — with unrounded returns q_sel reproduces the prior program's .5511 exactly; the
  residual was the validator's own 4dp rounding of two sub-0.01bp moves.
- **Feed-vs-candle noise floor:** live gate features are not candle-reproducible (eff6
  median |Δ| .042, max .22; cnt12 ±1 at the boundary; trigger membership fuzzy ~1–2bps;
  15.5% of triggers sit within ±1.5bps of 12bps). Nothing may be tuned finer than this.
- **The measurement book is availability-censored:** 50 candle gate-passes in the live
  window vs 36 records vs 30 clean matches (reach rate 0.60). `_measure_record` fires only
  on FILLABLE signals. Any availability/kill/qhat denominator must come from the dataset's
  gate-pass universe, not the book. ledger_only = 0 (measurement-first ordering confirmed).
- **Labels:** open-to-open agrees 98.8% with actual PM resolutions (929/940 non-tie); ties
  resolved Up only 43.2% — never credit ties.
- **Ledger validation:** 13 exceptions over 106 v3-era trades, all explained (3 past
  horizon, 3 at one proven feed-borderline trigger, 7 in the Jul-13 cnt12-borderline
  cascade). No gate-code bug. ⚠ Joint trigger+gate counts are 22/27 (impulse_v2) and
  29/35 (impulse50); the per-engine figures in the unit's text counted the gate bit alone.
- ⚠ vol10m source is near-perfectly collinear with the TRAIN/TEST split (150 of the
  13,253 5m-proxy rows are TEST-era) — a vol-source dummy is confounded with era.

**Verification artifacts:** `work-deepen/verify/dataset-0/results.json`,
`work-deepen/verify/dataset-1/{verify_core,verify_joins}.py`.

### 2.2 patches — CONFIRMED (2/2)

**Deliverable:** 5 ordered diffs + patched bot copy + seed file + replay harness in
`work-deepen/patches/`. Baseline md5 `471e2c2f9468c9f090886950d43a5e57` equals the live bot
(untouched, verified by both lenses). Selftests 62 (baseline) → 103 (final), all green at
every stage; `replay_dryrun.py` replays migration + seeding + nightly over the real book/
ledger with all named invariants passing (0 fails; 21 named checks in
`replay_results.json`); both verifiers reran it byte-equal from fresh copies.

| Patch | What it does | Verified effect |
|---|---|---|
| **P1** `patch1-r4-measurement-amendment.diff` | Poll-cumulative bestCost + realized fillCost per record; sized/skip stamped at t0+45s window close (MF6); one-shot idempotent ledger migration; **written pre-commitment: day-14 kill / guards / qhat read opCost = fillCost else bestCost, seeds excluded** | Migration joins 27/36 rows (all flagship trades; 12 orphan f_nonpos skips repaired); first-poll basis −6.23c/sh (reproduces R4 exactly) vs operated −2.40c/sh on the same n=35; schema-additive; outcomes/sides/t0s untouched |
| **P2** `patch2-r8-conformance.diff` | Registered prior (w+100)/(n+200) at mean 0.5 cap 0.56; p_eff bucket boundary; M2 guard seeding (`impulse_guard_seed.json`, n=123, +2.75c/sh, deterministic regen); 15d haircut tier deleted per SC3; −1c release hysteresis; named constants + dated CHANGELOG | qlo 0.5068→0.4934 (p_eff buckets) / →0.4953 (cost buckets per §1 adjudication); sized boundary ask ≲0.466; seeds make the 7d guard evaluable with no fire (n7 +1.61c on 158); learning lag halves |
| **P3** `patch3-restart-flap-fix.diff` | Metrics write only to cfg metricsPath (selftest writes nothing); lastNightly==0 sets baseline without catch-up nightly; epoch fence prunes pre-epoch non-seed rows | Mechanism proven byte-level: the Jul-10 "flap" lines are `--selftest` fixture output (qlo 0.4175 = (90+400·0.5057)/700); live state never flapped; production log untouched (14 lines) |
| **P4** `patch4-firstfill-cap.diff` | firstFillMax=0.47 on impulse_v2 only, evaluated before qhat at every fillable poll's sizing step; raw-ask comparison (ask of exactly 0.47 sizes); named SKIP; measurement still records; controls untouched (selftest-asserted) | Null today; frozen backstop vs qhat drift re-opening 48–53c. ⚠ H_cap_diag "24/36 would skip" is 21/36 (three asks of exactly .47 inflated by the 4dp cost inversion) |
| **P5** `patch5-leader-shadow.diff` | leader_v1 $0-stake fill-conformance shadow: drift 4–8bps aligned, leader-side ask [0.55,0.66), records ask/bid/depth + ~2.5s re-poll (ask2/bid2/dtMs), defers when any live entry window is open, bounded/persisted/published | 12 new selftest assertions (⚠ not 9); zero interaction with any trading book. ⚠ Overclaim trimmed: the re-poll phase-shifts the free-running 4s loop, so later intervals' first polls can land up to ~2.5s later — inside existing jitter, no decision rule changes |

⚠ Governance note from verification: `replay_dryrun.py` is a sound commit gate but is **not**
the FINAL-DESIGN §6.5 M4 artifact (no 60d gate-objective replay, no bounds/step-cap/promotion
state-machine asserts). M4 remains outstanding before any gate-constant refit may go live.

⚠ Kill context for the owner: the pre-committed operated basis currently reads −2.40c/sh
(n=35 — not evaluable at min 200; dragged by 9 never-entered legacy signals priced at rich
first-poll costs, −19.64c/sh, because pre-amendment rows have no bestCost). The kill will
hinge on the ~170 new amended records; the amendment removes the mechanical bias, it does
not guarantee survival.

**Verification artifacts:** `work-deepen/verify/patches-0/results.json`,
`work-deepen/verify/patches-1/results.json` (independent recomputation from raw
state/ledger; both reproduce every headline number).

### 2.3 qhat — CONFIRMED (2/2)

**Deliverables:** `work-deepen/qhat/{audit,calib,part3,part4}_results.json`.

- **Guard/bench audit:** all 4 genuine nightlies replicate to 4dp; live state was NEVER
  benched or haircut (the task brief's premise was stale); bench cost in the v3 era = $0;
  the "flap" is definitively selftest fixture pollution (byte-identical signature,
  mechanism at btc5m_bot.py:1586-93). A no-n-minimum bench would have fired Jul 11 on n=4
  and forfeited +$129.07 — the n-minimums SAVED money.
- ⚠ **Guard-tier reachability corrected (qhat-1 lens):** NOT "structurally unreachable" —
  the 14.2/day settle cadence is a 2.5-day quiet-regime figure. At TEST-era gated-signal
  rates (mean 45/day, max-7d 54/day) with the observed 0.72 record-capture or the fill
  model's 0.55 availability (20–39 rec/day), the 7d≥120 tier is reachable in ordinary
  weeks — **and could arm on the unamended −6.23c first-poll book before day 14 while the
  operated arm is positive.** This strengthens, not weakens, the amend-R4-first sequencing:
  a falsely-active haircut costs $32.50–85/day on the 60d bed.
- **Calibrator tournament (K=22, TRAIN-selected, TEST once):** the TRAIN winner
  (60d-informed seed .54) is rejected — the seed is the quantity being evaluated
  (circular), the beat is stake-level leverage on the bed's positive level
  (⚠ its per-share cps 6.32 < deployed 6.95 — an R6-forbidden scale-up in disguise), and
  on the real book it opens 12 rich first-poll records averaging −18.5c/sh (⚠ the quoted
  "−$2.22/share" is the sum over the 12). At live n=36 all conforming families are noise
  (≤3 decision flips, mean −0.25c/sh).
- **SURPRISE (confirmed under stress by both lenses):** the R8 "bucket boundary deviation"
  `cost<0.50` is the BETTER design. Base fill model favors the registered `p_eff<0.50`
  (+$479 TEST), but under the R2-consistent stress (zero edge at the .49/.51 anchors —
  which R2 CONFIRMED on real fills) the ordering flips: −$150 CI90 [−195,−106]; `cost<0.50`
  is the only boundary with $0 exposure at the fee-dead .49 anchor and is uniquely robust
  to ±1c bucket-edge jitter. **Resolve R8 item 1 as DOCUMENT THE DEVIATION, keep the code.**
- **Cap 0.56 never binds** for the deployed/spec/hybrid/neutral-seed families over 63
  nightlies (⚠ scope: e_shrink families do bind 5–6/63 nights; deployed hi-bucket raw
  reached .5357, lo .5224); cap changes in either direction: rejected, $0.00 delta.
- **Recommended config `hybrid_cost_M200`:** cost<0.50 buckets (keep, document) + prior
  200 @ mean 0.5 + cap 0.56 + single 7d/−2c haircut tier with −1c hysteresis + M2 seeding.
  ⚠ Framing per verification: adopt on governance/conformance grounds — "not worse,
  EV-wash live" (its bed cps 6.63 < deployed 6.95; its +$213 TEST delta does not survive
  selection correction; `cost_M200_seedled` — ledger-anchored seeds at M=200 — is the
  documented equally-robust alternative). Prior-mass decomposition: 400→200 contributes
  +$359 TEST; seed-mean →0.5 gives back −$146 (noise).

**Verification artifacts:** `work-deepen/verify/qhat-0/results.json`,
`work-deepen/verify/qhat-1/{indep_checks,check2_results}.json`.

### 2.4 metamodel — CONFIRMED FAIL (2/2), pre-registered STOP

**Deliverables:** `work-deepen/metamodel/{PREREG.md, results.json, diagnostics.json,
finetune_results.json, crosscheck_irls.json}`.

- **ML-PLAN Phase 1 verdict: FAIL.** The 8-feature L2 logistic meta-model
  (cost/pm/eff6/cnt12/hour/vol/spread/sec), trained strictly walk-forward on the canonical
  2,802-signal dataset, is pointwise WORSE than both qhat baselines on TEST-OOS
  (n=721, ex-tie): model Brier .247069 vs impl .246341 / spec .246209. All four
  pre-registered bootstrap checks fail with negative point estimates. Robust to fill
  anchors, fold cadence (5d/20d), fold re-anchoring, bootstrap seeds and block sizes
  (verifier stresses). Decisively: NO lambda on the path beats either baseline even
  pointwise, so no selection rule could have produced PASS.
- **Zero feature signal:** regularization path is monotone into intercept-only
  (TEST Brier .245925 beats the full model); ⚠ 4/5 drop-one and 5/5 single-feature
  ablations beat the full model (drop_pm is the exception, 3.4e-5 worse — "every ablation"
  was overstated). Strike pm/eff6/cnt12/hour/vol from future sizing candidates.
- **Closest miss is not ML:** a featureless walk-forward trailing mean nearly beats
  deployed qhat (Brier +0.000416, p_boot .0355 at 1h blocks; ⚠ block-size sensitive,
  .048–.071 at 2–4h). Mechanism: prior shrinkage lag — impl qhat reached only ~.546 while
  realized TEST q ran .570. This is exactly the R8 prior fix P2 ships; no model needed.
- **Money metric:** quarter-Kelly at frozen fills shows no economic difference; even the
  uncapped model-q lost. ⚠ Quoted totals ($1,289/$1,336/$1,460) are raw pre-availability;
  ×0.55 figures are separate fields.
- **Fine-tune on the 36-record live book:** unpowered and monotonically LOO-degrading;
  do not fine-tune below ~hundreds of settled records; the R4 amendment is prerequisite
  for book costs to be usable as features at all.
- **Do NOT open Phase 2 shadow deployment.** Re-run condition: ~400–600 settled
  amended records with real per-signal prices (~30–45 days post-P1), pre-registered then,
  centered on real price features only.

**Verification artifacts:** `work-deepen/verify/metamodel-0/results_indep.json`,
`work-deepen/verify/metamodel-1/` (three-optimizer agreement, per-row OOS max Δ 5e-7).

### 2.5 params — CONFIRMED (2/2): freeze everything

**Deliverables:** `work-deepen/params/{sweep1d,sweep2d,cap_window,verdicts}.json`. K=40
total (26 candle-backtest cells + 14 modeled overlay cells), fully counted.

- **Frozen reference:** TRAIN +3.84c/sh ex-tie, $93/day; TEST +6.76c/sh, $163/day
  (frozen anchors, $50 stakes, 0.55 availability; ties never credited). Reproduced to the
  cent by both verifiers from raw candles with independent code.
- **Every loosening is a cliff:** revThr 8bps TEST CI90 [−4.47,−0.40] (added mass
  q_xt .5125 = fee-dead); eff6Min 0/.05 TEST-significant (added mass q_xt .39–.46);
  cnt12Max 8 TRAIN CI90 [−1.82,−0.16]. **Every tightening is a plateau** that loses $/day;
  strongest signal anywhere (cnt12Max=3, TEST +1.91c, p=.105 pre-multiplicity,
  TRAIN −0.02c) dies under K correction and train-test consistency.
- **2D: no rescue, no ridge** — cliffs are additive (interaction −0.02c); the sub-12bps
  mass stays q .50–.52 under every tighter-gate combination.
- **Cap (0.53) is nearly inert for the flagship** (f>0 already imposes an implicit .47
  first-fill ask cap, .46 post-P2); the cap-down table (per-share EV +7.9→+15.2c capping
  .53→.47, availability 0.71 refill / 0.33 no-refill bracket) is filed as CAP-DOWN
  evidence for the **day-60 verdict**, not a mid-experiment move. ⚠ Use the no-refill
  bracket; the r2adj pole (+24.7c) is optimistic even within-table.
- **firstFillMax=0.47 recommendation confirmed** (feeds P4). ⚠ Semantics pinned per
  verification: strict raw-ask comparison, ask > 0.47 skips (an ask of exactly .47 sizes;
  the revEntryMax ask+slip convention would wrongly block 2/26 real fills). ⚠ The
  0.49-rejection arithmetic: a .49-ask fill costs .5175 all-in (not .5075) — still inside
  the R2 dead zone; rejection stands, strengthened. Leak foreclosed: f_nonpos cohort
  −9.99c/sh (n=21); impulse50 fills >.47 ask −12.87c/sh (n=20).
- **Window 45s is the plateau top:** ⚠ "97.4% capture" is a latency artifact — by the
  ledger's own entrySec, 100% ≤45s; 30s loses ~8% of fills (~$8.5/day), 15s ~27%; no speed
  alpha exists (micro F3 re-confirmed, fast entries 4.45c WORSE, p=.75); extending past
  45s is unmeasurable (censored misses) and every proxy is adverse. Do not extend before
  the miss-ask logging fix lands.
- **Verdict sheet:** all five parameters "frozen point on plateau, leave it." Zero day-60
  re-registration candidates. eff6/cnt12/revThr sit within ~1–2× the feed-vs-candle noise
  floor — finer tuning is unidentifiable by construction.

**Verification artifacts:** `work-deepen/verify/params-0/results.json`,
`work-deepen/verify/params-1/results.json`.

---

## 3. THE ACTION PLAN

### APPLY NOW (verification confirmed zero risk to pre-registered verdicts)

All items are owner actions. Deploy procedure (from `work-deepen/patches/README.md`): copy
`btc5m_bot_patched.py` over `bot/btc5m_bot.py` AND `impulse_guard_seed.json` next to it (or
apply diffs 1→5 in order), then run `--selftest` (expect 103/103) and `replay_dryrun.py`
(expect 0 fails) as the commit gate. Item 2's one-hunk modification requires a selftest
re-run before deploy.

1. **P1 — R4 measurement-book amendment. HARD DEADLINE: before day 14.**
   Patch: `work-deepen/patches/patch1-r4-measurement-amendment.diff`.
   Tests: 7 new selftests green; replay sections B/E/G; both verifier reruns byte-equal;
   independent recomputation of −6.23c/−2.40c/+3.84c from raw data by both lenses.
   Effect: kill/guards/qhat read the operated/best-fillable basis per the written
   pre-commitment; 27/36 legacy rows joined to real fills; prevents a false day-14 kill of
   a policy positive as operated. Verdict risk: none (outcomes/sides/t0s and the first-poll
   diagnostic series untouched; this IS the wave-1-mandated amendment).

2. **P2 — R8 conformance, MODIFIED per the qhat unit's confirmed stress result: keep the
   `cost<0.50` bucket boundary (revert that hunk), adopt everything else** — prior
   (w+100)/(n+200) at mean 0.5 cap 0.56, M2 seeding (`impulse_guard_seed.json`), 15d tier
   deletion, −1c hysteresis, named constants, dated CHANGELOG including the bucket-boundary
   deviation note wave-1 Tier-1 #4 requires.
   Patch: `work-deepen/patches/patch2-r8-conformance.diff` minus the boundary hunk
   (resulting config = qhat's `hybrid_cost_M200`, `work-deepen/qhat/part4_results.json`).
   Tests: 12 P2 selftests green as shipped (the ~2 boundary probes need updating with the
   hunk reverted — re-run selftest before deploy); seed file regenerates byte-identical.
   Effect: qlo 0.5068→~0.4953, removes ~1.1c anti-conservative inflation, halves learning
   lag, guards evaluable from day 1 with no fire (seeded n7 +1.61c/158); ~6.1→4.9 sized/day,
   3 live flips at mean −0.25c/sh (wash). Verdict risk: none (verdicts never read qhat;
   seeds excluded from the kill). Bundle in the SAME dated human-reviewed refit as P1 —
   M=200 tracks the book 2× faster, so it must not run ahead of the amended book.

3. **P3 — restart-flap fix.**
   Patch: `work-deepen/patches/patch3-restart-flap-fix.diff`.
   Tests: 5 new selftests + replay section F; mechanism confirmed byte-level by both
   verifiers (fixture signature qlo 0.4175). Effect: selftest can no longer pollute
   production loop_metrics; no catch-up nightly on stale/empty state; epoch fence. Zero
   live behavior change today. Verdict risk: none.

4. **P4 — firstFillMax = 0.47 on impulse_v2 only.**
   Patch: `work-deepen/patches/patch4-firstfill-cap.diff`.
   Tests: 5 new selftests (cap beats qhat=0.56; ≤47c sizes; refill path preserved; control
   non-leakage asserted); params unit + both its verifiers confirm 0/26 fills and 0/36
   sized records move today. Semantics as implemented and hereby pinned: raw-ask strict
   comparison at every fillable poll's sizing step (more conservative than literal
   first-fill-only; consistent with R1/R2). Effect: $0/day now; forecloses a 10–13c/sh
   leak per fill if qhat drift re-opens 48–53c. Verdict risk: none (measurement book still
   records; controls untouched).

5. **P5 — leader_v1 $0-stake fill-conformance shadow.**
   Patch: `work-deepen/patches/patch5-leader-shadow.diff`.
   Tests: 12 new selftest assertions (record/re-poll, deferral, rejections, dedupe,
   $0-stake, backfill, snapshot). Effect: begins collecting the quote-persistence data
   (ask2/bid2/dtMs) that alone can decide wave-1 R3. Cost bound: ≤1 extra book poll +
   ≤2.5s sleep per 5m interval; ~2.5s poll-phase shift on subsequent intervals (inside
   existing jitter). Verdict risk: none — touches no trading or measurement book.

6. **Bookkeeping (no code):** log the R8 bucket-boundary deviation note and the P2/P1
   changelog; record this report as the ML-PLAN Phase-1 pre-registered STOP; carry wave-1
   Tier-1 #5 (R7 retention band re-registration ~0.60–0.80) which is untouched by wave 2.

### SHADOW FIRST (measurement before money — nothing here changes behavior)

- **leader_v1 promotion bar:** promote nothing until the shadow demonstrates live ask
  persistence at sub-market quotes over a real sample; expected result at market-displayed
  prices is ~0 to −3c/sh (R3) — treat positive conformance as a surprise to re-verify.
- **Miss-ask logging (wave-1 Tier-2 #7):** add ask + eval-timestamp to the miss/skip ring
  buffer. Prerequisite for: classifying the 20 unaccounted gate-passes, any entry-window
  extension, and de-censoring the availability denominator (reach rate 0.60).
- **Meta-model: explicitly NOT shadowed.** Phase 1 FAILED its pre-registered bar; logging
  coefficients next to qhat would be theater. Re-run condition (pre-register then): ~400–600
  settled amended measurement records with real per-signal prices (~30–45 days post-P1),
  features = real price/cost only.
- **M4 replay harness (FINAL-DESIGN §6.5):** must be built before any gate-constant refit
  is ever proposed; `replay_dryrun.py` is a commit gate, not M4.

### WAIT (day-60 refit / more data; the pre-registered machinery is the arbiter)

- **All five gate/entry parameters stay frozen through day 60:** revThr 12bps, eff6Min
  0.10, cnt12Max 6, revEntryMax 0.53, revWinMin 255. Quote the loosening cliffs
  (`sweep1d.json`) at anyone proposing to widen the funnel for volume.
- **Cap-down on flat arms (revEntryMax → <0.50):** belongs to the pre-registered day-60 cap
  verdict; `cap_window.json` is filed as CAP-DOWN evidence. No mid-experiment move
  (inert for the flagship anyway).
- **Guard n-minimum rescale (7d 120→80, 15d 250→170):** only after the amended book
  accrues. Sharpened urgency from verification: in a normal-signal week the 7d tier can
  arm on the UNAMENDED book before day 14 — one more reason P1 cannot slip.
- **No stake scale-up** (wave-1 R6 stands: central +1.71c/sh as-operated, SE ~1.9).
- **No qhat cap change in either direction; no informed seeds; nothing faster than M=200**
  (qhat dead ends, verified).
- **Day-60 gate-increment verdict:** will be underpowered (~25% rejection mass); plan the
  pre-registered extension (day-90) now, per wave-1 Tier-3 #10.
- **Entry-window extension (45→60/90s):** blocked until miss-ask logging lands; every
  current proxy is adverse.

---

## 4. Updated posterior on the flagship's edge and expected $/day

Wave 2 adds no evidence that moves the edge posterior; it narrows what the edge is NOT
(no gate-parameter ridge, no context-feature information, no calibrator alpha) and repairs
the instruments that will measure it.

- **Working central (unchanged, wave-1 R6 verified): +0.75c/sh first-poll / +1.71c/sh
  as-operated, SE ~1.9.** Still indistinguishable from zero; still no scale-up.
- **Optimistic pole:** the 60d candle bed at frozen anchors runs TEST +6.76c/sh ex-tie
  ($163/day mid at $50 stakes, 0.55 availability); ties-as-loss floor +1.98c/sh. This
  level is concentrated in ~2 TEST weeks (wave-1 R6 caveat) and is a bound, not a forecast.
- **Expected $/day change from the applied set: ≈ $0 as-operated.** P4 binds nothing
  today; P2 drops ~1.2 sized signals/day whose measured EV is a wash (mean −0.25c/sh on
  the flipped records — exactly the R2-dead cost window), with upside only if the 60d
  level persists. At current geometry (~10–11 flagship fills/day, ~$50 stakes ≈ 100 sh)
  the central expectation is on the order of +$15–20/day with an SE of the same magnitude
  — quote it as "positive central, not distinguishable from zero at current n."
- **The real EV of this wave is protective:** (a) the day-14 kill now reads a basis that
  cannot fire mechanically on a positive policy (unamended gap +3.84c/sh on n=35, and the
  9 legacy fallback rows wash out as amended records accrue); (b) a falsely-armed haircut
  ($32.50–85/day exposure) is foreclosed by sequencing; (c) a qhat-drift re-opening of the
  48–53c zone (−10 to −13c/sh per fill) is capped at zero cost.
- **Kill outlook, honestly:** operated-basis preview −2.40c/sh at n=35 is not evaluable
  (min 200) and is biased down by legacy rows; the verdict will hinge on ~170 fresh
  amended records. The amendment removes bias; it does not guarantee survival. That is
  the point of the pre-registration.

---

## 5. Dead ends from this wave (do not re-hunt)

1. Exact candle replication of live gate features (eff6 to 4dp) — impossible under any candle convention; the feed is private 4s-poll data (dataset).
2. Classifying the 20 unaccounted live-window gate-passes offline — no log trace exists until miss-ask logging ships (dataset).
3. 60d-informed qhat seeds (.54 family) — circular, R6-forbidden leverage, opens 12 rich first-poll records at mean −18.5c/sh (qhat).
4. qhat cap changes in either direction — never binds conforming calibrators; $0.00 delta at .58/.60/1.00 (qhat).
5. Window/decay calibrator variants (10d, ∞, half-life 7/14d) — all within noise of spec; trailing-30d is fine (qhat).
6. Shrink-to-pooled-base-rate calibrators — under-size with no bed advantage (qhat).
7. Flipping the bucket boundary to registered p_eff<0.50 — fails the R2-consistent stress −$150 TEST CI90 [−195,−106] (qhat; adjudicated in §3).
8. Removing/rescaling guard n-minimums before the R4 amendment — the no-min bench would have fired Jul 11 and forfeited +$129 operated (qhat).
9. Hunting a live bench/haircut mis-fire — never happened; "flap" was selftest fixture pollution, mechanism located and patched (qhat/patches).
10. Candle-context features (pm, eff6, cnt12, hour, vol) as a sizing model — monotone path to intercept-only; pre-registered Phase-1 FAIL (metamodel).
11. Fine-tuning on the ~36-record live book — LOO-degrading at every anchor strength; also R4-contaminated and 40% availability-censored (metamodel).
12. Fold-cadence or only_pm rescues of the meta-model — fail the bar; only_pm is TEST-selected and still insufficient (metamodel).
13. Ties→Up crediting in any form — re-killed on independent PM joins (ties Up 43.2%) (dataset/metamodel).
14. Rescuing sub-12bps triggers with tighter eff6/cnt12 — added mass stays q .50–.52 everywhere (params).
15. Combined eff6×cnt12 re-tune — cliffs are additive, no ridge (params).
16. Tightening gate params for per-share EV — never significant, always $/day-worse, TEST-concentration-shaped (params).
17. Raising revEntryMax to .55 — dominated; 53–55c band q=.433, −12.9c/sh (params, wave-1 #36 re-confirmed).
18. firstFillMax=0.49 — a .49-ask fill costs .5175 all-in, inside the R2 dead zone (params, corrected arithmetic).
19. Shrinking or extending the 45s entry window — no speed alpha (fast 4.45c worse, p=.75); post-45s proxies all adverse; extension unmeasurable until miss logging (params).
20. Tuning eff6/cnt12/revThr finer than the feed-vs-candle noise floor (eff6 ±0.04–0.06, cnt12 ±1, trigger ±1–2bps) — unidentifiable by construction (dataset, inherited everywhere).

---

*Wave 2 synthesis, 2026-07-13. All numbers cross-checked against the cited artifacts in
`work-deepen/` and `work-deepen/verify/`; verifier corrections supersede unit-quoted figures
wherever marked ⚠. Honest > impressive. Nothing outside the research tree was modified; the
live bot's md5 was verified unchanged by two independent lenses.*
