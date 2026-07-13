# Wave-2 patch set — impulse_v2 instrumentation & risk-control fixes (2026-07-13)

Implementation-ready patches for the wave-1 mandated fixes
(`research/2026-07-12-edge-hunt/FINDINGS.md`, Tier-1 items 1–5 + Tier-2 item 6).
**Nothing here touches the live bot.** Apply by copying `btc5m_bot_patched.py`
over `bot/btc5m_bot.py` **plus** `impulse_guard_seed.json` next to it (or apply
the per-patch diffs in order 1→5). Each diff is one commit-worthy unit and
includes its own selftests.

## PRE-COMMITMENT (R4 — the day-14 kill basis, committed before day 14)

> The day-14 Phase-1 kill (FINAL-DESIGN §7: measurement-book net/share ≤ −2c,
> mean alone, min 200 settled), the §5.2 guard windows, and the nightly qhat
> all read the **OPERATED basis**:
> `opCost = fillCost` when the signal was actually filled, else `bestCost`
> (the best in-window fillable cost); legacy pre-amendment rows fall back to
> their first-poll `cost`. **Seed rows (`seed=True`, the M2 cohort) are
> excluded from the kill and from qhat** (they feed only the guard-window
> n-minimums). The first-poll `cost` series is retained unchanged and
> published as a **diagnostic only** — it feeds no verdict, no guard, no
> estimator.

This is also written as a code comment (CHANGELOG P1 block, top of the
impulse section). Current live preview (replay, n=35 settled): first-poll
basis **−6.23c/sh** (exactly R4's number) vs operated basis **−2.40c/sh** —
gap +3.84c, which will widen as new records accrue real `bestCost` for
never-entered signals (legacy skips have only the first-poll fallback).

## Patches

### P1 — R4 measurement amendment (`patch1-r4-measurement-amendment.diff`)
- `_measure_record` is now poll-cumulative: first fillable poll appends the
  record (first-poll `cost` kept forever as the diagnostic series); later
  in-window polls update `bestCost` in place and refresh a *provisional*
  sized/skip. `_measure_fill` stamps the realized all-in fill cost from
  `paper_enter`. `_measure_finalize` stamps `final` sized/skip at the t0+45s
  window close (MF6 skip-finality — the verified code-vs-spec defect).
  Skip counters now count once per signal, on the final reason.
- One-shot idempotent migration (`_measure_migrate`, flag `mAmend`): legacy
  rows are joined to the flagship ledger by t0 (side-checked). On the live
  book: **27/36 rows joined, including the 12 orphan `f_nonpos` skips that
  were actually traded ~11c cheaper** (R4's headline defect).
- Nightly qhat + guard windows read `_m_opcost` (see pre-commitment).
- Schema-additive; sanitize round-trip verified.
- **Risk to pre-registered verdicts: none.** The day-14/day-60 statistics read
  measurement-book outcomes; this patch *is* the pre-registered amendment R4
  mandates (wave-1 Tier-1 #1), it adds fields and fixes the stamp to the
  MF6-registered semantics. Outcomes (win), sides, t0s and the first-poll
  series are untouched.
- Tests: 7 new selftests (provisional record, in-place bestCost, realized
  fill, window-close finality, migration + idempotency, operated-basis
  bench discrimination) + replay sections B/E/G.

### P2 — R8 conformance (`patch2-r8-conformance.diff` + `impulse_guard_seed.json`)
- **Bucket boundary**: FINAL-DESIGN §4.1 defines `p_eff = ask + slip` (the raw
  fill price, fee excluded) and §4.2 buckets on `p_eff < 0.50` — the code
  bucketed on `cost < 0.50` (≡ p_eff < ~0.4825). The sizer now buckets on
  `p < IMP_BUCKET_LO`; the nightly inverts stored costs exactly
  (`_p_eff_from_cost`, quadratic root, 6dp).
- **Prior**: registered `(wins+100)/(n+200)` — `IMP_PRIOR=200` at
  `IMP_PRIOR_MEAN=0.5`, cap 0.56 — replacing mass 400 anchored at the seeds.
  Seeds remain only as launch-day *state* values (MF3).
- **M2 seeding (§5.3)**: `impulse_guard_seed.json` = the pre-launch
  cap-censored family ledger, deterministically regenerated (`gen_seed.py`)
  and byte-checked against the wave-1 R8-repro locator: n=123, +2.75c/sh,
  span Jul 9 02:35 → Jul 10 14:35. Loaded once (flag `seeded`), rows
  `seed=True`: they count toward guard n-minimums, age out naturally, never
  feed qhat. With seeds the 7d window is evaluable *today*: n7=+1.61c on 158
  → no guard fires (matches R8-repro's counterfactual). Direct-count answer
  to FINDINGS Tier-1 #5: post-seed-ageout (~Jul 17) the 7d≥120 tier goes
  structurally unreachable again at ~14.6 signals/day — documented here, no
  threshold change made (that would be a spec change, not conformance).
- **§5.2/SC3**: deleted 15d/−1c haircut tier removed; haircut = single
  7d<−2c trigger with release hysteresis at ≥−1c (holds state in between /
  without min-n). Bench and breaker untouched. False MF2/MF3 conformance
  comment rewritten.
- **Expected sizing impact at current qlo/qhi** (replay section D, real book,
  operated basis after migration): qlo 0.5068→**0.4934** (lo bucket n=27
  w=12), qhi 0.5030→**0.4952** (n=8 w=3). Sized boundary tightens from
  p_eff<0.4893 to **p_eff<~0.476** (ask ≲ 0.466) — conservative, removes the
  verified ~1.1c anti-conservative inflation; ~0–3 marginal sizing decisions
  flip per R8's verified estimate, and learning speed doubles.
- **Risk to pre-registered verdicts: none.** R8 verified 3-0 that day-14/
  day-60 verdicts never read qhat; seeds are excluded from the kill by the
  pre-commitment; this is the dated, human-reviewed refit FINDINGS Tier-1 #4
  prescribes.
- Tests: 12 new selftests (registered prior, p_eff buckets incl. exact-0.50
  boundary, inverse-formula, sizer bucket unit tests, seed load/one-shot/
  qhat-exclusion/guard-min counting, haircut trigger/hysteresis/15d-tier
  removal) + replay sections A/C/D.

### P3 — restart-flap fix (`patch3-restart-flap-fix.diff`)
Diagnosed mechanism (from code + raw loop_metrics): the 7–10 anomalous Jul-10
lines are byte-exact `--selftest` fixture output (qlo 0.4175 =
(90+400·0.5057)/700) appended to the production `loop_metrics.jsonl` because
the path derived from `__file__`; separately, any restart whose state load
fails (or a resurrected stale state file) ran an immediate catch-up nightly
over an empty/foreign book. Three minimal fixes:
1. metrics write only to `cfg['metricsPath']` (set by `main()`; selftest
   fixtures write nothing — verified: selftest no longer creates the file);
2. `lastNightly==0` sets the baseline **without running** a catch-up nightly
   (first real nightly at the next 00:10 UTC crossed live);
3. impulse state carries `epoch`; nightly prunes non-seed rows with
   t0 < epoch (legacy states load epoch=0 → zero behavior change on the
   current live book).
- **Risk to pre-registered verdicts: none.** Live state never flapped
  (R8-selection); this only prevents fixture pollution and wrong-basis
  recomputation. The skipped catch-up nightly delays a fresh state's first
  qhat refit by <24h — qhat is not a verdict input.
- Tests: 5 new selftests + replay section F.

### P4 — ≤47c first-fill cap, impulse_v2 only (`patch4-firstfill-cap.diff`)
- `ENGINE_CFG["impulse_v2"]["firstFillMax"]=0.47`, evaluated at the sizing
  step before qhat: ask > 0.47 → named SKIP `first_fill_cap`. The
  measurement book still records the signal; cheaper in-window re-polls
  still size (the refill path R1 showed is the flagship's actual live
  outperformance). Independent of learned qhat — closes the verified
  loophole where nightly drift could re-open 48–53c first fills (fee-dead in
  every era/cut, R2). On the current book, 24/36 live first polls would have
  carried the named skip. At today's qlo the qhat threshold (ask ≲ 0.466) is
  the binding constraint — the cap is the frozen backstop, costing nothing.
- **Controls untouched**: impulse50, reversal_v2, reversal, reversal2 have no
  cap key (selftest-asserted). impulse50 remains the pre-registered flat
  twin taking every gate+cap pass.
- **Risk to pre-registered verdicts: none.** The day-60 gate/cap verdicts and
  the day-14 kill read measurement-book outcomes on common signals — the cap
  changes only which signals get *sized*, adds a named skip reason (its own
  §6.4 histogram line), and touches no control arm. Wave-1 Tier-1 #2
  pre-registered exactly this action as a zero-cost risk control.
- Tests: 5 new selftests (cap beats qhat=0.56, ≤47c sizes, refill path,
  control non-leakage, cfg placement) + two P2 tests reworked to unit-level
  sizer probes (the cap now stops 48–50c asks before qhat is consulted).

### P5 — leader_v1 $0-stake fill-conformance shadow (`patch5-leader-shadow.diff`)
- Measurement-only book (NOT an engine: no orders, no stake, no pnl, no
  equity). State qualifies when the current interval's spot drift is aligned
  with the leader side, |drift| ∈ [4,8) bps of open, and the leader side's
  REAL-book ask ∈ [0.55, 0.66) — the R3-verifier band (wide: the 60c lower
  edge was shown overfit; 59–60c aligned ran q=.368; stratify offline).
- Records poll-1 ask/bid/depth from the tick's already-fetched book, then
  **re-polls the same token ~2.5s later** and logs `ask2/bid2/dtMs` — quote
  persistence, the datum that decides whether R3's stale-ask capture is
  real. The blocking re-poll **defers to the next tick (~4–5s, honest dtMs)
  whenever any live arm's entry window is still open**, so the shadow can
  never delay a trading decision. One record per interval, bounded
  (LEADER_KEEP=2000), persisted in state and published in the snapshot
  (`leaderShadow`). Outcomes backfill from the feed proxy (winBy='feed',
  ~97% oracle agreement) and upgrade to oracle when available — diagnostic
  only; the promotion question is ask-persistence, per R3.
- **Risk to pre-registered verdicts: none.** Zero interaction with any
  trading book or the measurement book; runs last in the tick; its only
  cost is ≤1 extra book poll + ≤2.5s sleep per 5-min interval, only when no
  entry window is open (network jitter of this size already exists).
- Tests: 9 new selftests (record + immediate re-poll, deferral + next-tick
  completion, 4 non-qualifying rejections, dedupe, $0-stake, feed/oracle
  backfill, snapshot publication).

### P6 — tests + replay (`replay_dryrun.py`, evidence below)

## Test evidence

| Stage | Selftests | Result |
|---|---|---|
| baseline copy (unpatched) | 62 | ALL PASS |
| stage1 (P1) | 69 | ALL PASS |
| stage2 (P1+P2) | 81 | ALL PASS |
| stage3 (+P3) | 86 | ALL PASS |
| stage4 (+P4) | 91 | ALL PASS |
| **btc5m_bot_patched.py (all)** | **103** | **ALL PASS** |
| `replay_dryrun.py` (M4-style, real 36-record book + ledger + seeds) | 22 checks | **REPLAY ALL PASS** |

Replay highlights (`replay_results.json`): old formula reproduces live
qlo/qhi to 4dp (data sanity); migration joins exactly the 27 ledger-traded
rows (12 orphan skips repaired); seeds n=123 at +2.75c; patched nightly
matches an independent closed-form recomputation; first-poll −6.23c vs
operated −2.40c on the same 35 settled signals; no guard fires; snapshot →
sanitize round-trip preserves every new field.

## Files
- `btc5m_bot_patched.py` — final patched copy (deploy this + the seed file)
- `impulse_guard_seed.json` — M2 cohort (n=123); `gen_seed.py` regenerates it
- `patch{1..5}-*.diff`, `combined-all-patches.diff` — unified diffs (labels `a/bot/btc5m_bot.py`)
- `stages/stage{1..5}.py` — per-patch full copies (each stage selftest-green)
- `baseline_btc5m_bot.py` — pristine copy (md5 = live bot)
- `replay_dryrun.py`, `replay_results.json` — M4 replay + artifact
