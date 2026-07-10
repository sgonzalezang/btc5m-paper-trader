# VARIANT FAMILIES — RANKED VERDICTS & SHADOW SPECS
Variant-architect deliverable · 2026-07-10 · addendum to `FINAL-DESIGN.md` (v2.1)
Integrates with — never overrides — FINAL-DESIGN §2 (roster), §5.2 (promotion machinery), §8 (validation plan).
Baseline everything is paired against: **`reversal_v2`** = buffered open-to-open prior |move| ≥ 12bps on Coinbase 5m (contiguous candles), contrarian, ties→Up, hold to resolution, effective cost ≤ .53, fills from the censored-ledger mix (mean .4774, q\*=.4949), 55% availability, exact fee `shares·0.07·p·(1−p)`. 60d baseline: **4,023 signals, q=.5334, +3.9c/share** at mean fill (TRAIN 2,649/.5228 · TEST 1,374/.5539 — reproduced independently in every family before any variant was scored).

Fee break-evens used throughout: q\*(.4774)=.4949 · q\*(.4874)=.5049 · q\*(.4974)=.5149 · q\*(.53)=.5474.

---

## 1. Ranked verdicts

| Rank | Family | Verdict | One-line basis |
|---|---|---|---|
| 1 | **impulse** | **PROMISING — [CANDIDATE], shadow-confirmed on 60d** | Only overlay in the program with NO TRAIN→TEST sign flip; beats flagship per-share on both segments and in all six folds; totals vs flagship are a wash (paired CI spans 0) → shadow, not swap |
| 2 | **band** | **DEAD as a trigger modification** | 12–20bps band loses to take-all on TEST paired (−0.44c) and drops 35–46% of total EV; monster-move premise TRAIN-inverted; existing `rev20_shadow` roster entry unchanged |
| 3 | **asym** | **DEAD in full** | Side asymmetry p=.32 with live-ledger sign flips; no fill-side skew; ETH confirmation +0.2/0.3pp can't beat flagship — re-confirms the original no-encode decision on 6× the data |

### 1.1 impulse — the survivor (3-lens verified, all three lenses reproduced every headline number)

Gate: **eff6 ≥ 0.10 AND cnt12 ≤ 6**, parameters FIXED from `work/regime/deploy_spec.json` (no refit in the test). Conventions (load-bearing — implement exactly): trigger move pm = buffered open-to-open move into the trade interval, ≥ 12bps; **eff6 = |o[i] − o[i−6]| / Σ|last 6 moves| with the trigger move INCLUDED**; **cnt12 = count of |move| ≥ 12bps among the 12 moves BEFORE the trigger, trigger EXCLUDED**.

| Split | n_sel / n_all | q_sel | q_comp | net_sel @.4774 | @+1c | @+2c | gate-effect block-boot p |
|---|---|---|---|---|---|---|---|
| TRAIN (40d) | 1,733 / 2,648 | .5418 | .4863 | **+4.70c** | +3.69c | +2.69c | .002–.0035 |
| TEST (20d) | 1,009 / 1,374 | .5669 | .5178 | **+7.20c** | +6.20c | +5.20c | .033–.040 |
| pooled 60d | 2,742 / 4,022 | .5511 | .4953 | **+5.62c** | +4.62c | +3.62c | — |

Flagship same-splits net: TRAIN +2.78c, TEST +5.90c. All six 10d folds net-positive for the gated book (7.95 / 1.29 / 4.24 / 5.35 / 4.86 / 9.46c); the gate flips the only losing flagship fold (fold 1: −1.76c ungated → +1.29c). Retention 65.5% TRAIN / 73.4% TEST (68.2% pooled ⇒ 45.7 selected signals/day, ~25 fills/day at 55% availability).

**Why it is NOT a flagship swap:** paired (variant − flagship) totals per flagship signal: TEST **−0.61c**, block-boot CI90 [−1.61, +0.39], p(≥0)=.15; full-60d **−0.01c**, CI90 [−0.74, +0.69] — an exact wash at flat mean fill. The complement (n=1,280, q=.4953, +0.04c at .4774) is fee-dead but not negative. Per FINAL-DESIGN §5.2 today's verdict is correctly "no change".

**Fill realism / trending adjustment (confirmed program finding, applied):** the complement is cascade-heavy (mean prior move 24.9bps vs 21.5 selected, dominated by cnt12>6), so the ~1–2c-richer trending fills apply to IT: complement 60d net becomes −0.96c at +1c and −1.96c at +2c, pushing the paired delta toward 0/positive. The selected subset is mildly trend-tilted on eff12 (.336 vs .267) but smaller-move, so its own nets are quoted at the flat mix + sensitivities above (conservative). Reality check from `pm_prices_sample` (49 matched signals, last ~3d): selected honest ≤.53-censored fill **.4978** — the +2c row — with availability ~47–55%; at that fill TEST nets +5.16c vs q\*(.4978)=.5153, and even at the worst cap-allowed fill (.53, q\*=.5474) TEST q_sel .5669 nets ~+2c. Honest fills cut volume and ~2c/share, not viability.

**Residual caveats (verified, conceded, priced in):** (a) the gate form won a ~13-candidate tournament on the same 60d — family-level TRAIN significance after multiplicity discount is ~0.05–0.09, marginal; (b) deploy A=0.10 was calibrated on the trailing 20d (= TEST window), but the TRAIN-calibrated A=0.32 does equally well on TEST (+7.28c) and all 35 swept (A,B) beat or match flagship TEST net — a plateau, not a cherry-pick, so the lookahead is not load-bearing; (c) ±20% sensitivity on A, B, and the 12bps trigger holds (TRAIN +3.8→+4.9c, TEST +5.8→+7.5c, no sign flips). Verification artifacts: `work/verify-variant-impulse/{verify_impulse.py,verify_results.json}`.

### 1.2 band — dead as machinery, one quantified fact worth keeping

- Band-limited 12–20bps trigger: TEST paired delta vs take-all **−0.44c/share**, total EV −35–46%; TRAIN "support" (+0.77c) is p=.19 noise. Dead.
- Premise inverted: monster moves (25+bps) revert MOST on TEST (q .5610, boot p=.009) while TRAIN is the family's worst bucket (.5105, p=.29) — the size gradient is TEST-only in both directions, so NO magnitude reweighting has TRAIN persistence.
- **Keep this number:** the ≥16bps contrarian side is priced **1.2–2.4c richer**, and the .53 cap converts that premium into *skips*, not richer fills (measured availability .571/.364/.444/.250 for 12-16/16-20/20-25/25+). q\*(.55)=.5673 exceeds even the best TEST bucket q — paying up stays fee-dead, exactly as kelly_table found. The cap is doing its job; do not relax it.
- `rev20_shadow` (already in the FINAL-DESIGN §2 roster): TEST-strong (+6.57c/share availability-weighted), TRAIN-unsupported (20+ q .5181 < 12–20 .5264) — stays a zero-stake shadow, spec unchanged, forward criterion in §3.2 below.
- Artifacts: `work/variant-band/{band_analysis.py,band_results.json,band_addendum.py,band_addendum.json}`.

### 1.3 asym — dead in full, valuable as a re-confirmation

- fadeUP − fadeDOWN q delta on 60d: +1.5pp full (p=.32, CI [−1.4, +4.7pp]), +1.3pp TRAIN (p=.45), +1.7pp TEST (p=.56); fold deltas span −0.3 to +2.9pp; the live ledger flips the sign vs candles and flips again under .53 censoring. Nothing to encode.
- No side-conditional fill skew: contrarian Down .5267 vs Up .5234 mean cost at 20s — 0.3c inside noise (n=18/31).
- ETH same-direction confirmation: 92% of 12bps BTC impulses are already market-wide; filter nudges q +0.2/+0.3pp, cannot beat flagship like-for-like; the tightened (12–16bps) version is a TEST-only gradient — the standing kill pattern.
- Artifacts: `work/variant-asym/{a_side_asym.py,a_side_asym_results.json,b_side_fills.py,b_side_fills_results.json,c_joint_impulse.py,c_joint_impulse_results.json}`.

---

## 2. Survivor shadow spec — `impulse_shadow` [CANDIDATE]

This finalizes the roster row FINAL-DESIGN §2 already reserves (init A=0.10, B=6, deploy-calibrated per SC3). Zero stake. Promotable ONLY via §5.2 machinery ([CANDIDATE] class: additionally requires human sign-off and enters at half stake). Never touches the live path.

### 2.1 ENGINE_CFG entry

```python
"impulse_shadow": dict(
    label="ImpulseShadow", tunable=False, stake=0.0,          # zero-stake shadow, never sizes
    driftMin=None, driftMax=None, entryMax=None, volMax=None, # momentum machinery off
    revThr=0.12, revEntryMax=0.53, revWinMin=255,             # identical to reversal_v2 (FROZEN)
    holdToClose=True,                                          # no stop/hedge/timed exit
    effGate=False,                                             # NOT the latentfire eff12 gate
    impGate=True,
    impEffWin=6,   impEffMin=0.10,                             # A: eff6 >= 0.10 (deploy_spec trailing-20d)
    impCntWin=12,  impCntThr=0.12, impCntMax=6,                # B: cnt12 (|move|>=12bps) <= 6
)
```

Shadow-refit governance (per §5.1/SC3): (A, B) refittable every 10 days, min 250 signals in window, bounds A∈[0,1], B∈[0,12], no step caps (zero-stake books cannot lose money). Objective and window per `deploy_spec.json` `recalibration` block. effMax/eff12 machinery does not apply to this engine.

### 2.2 Eval diff vs `_reversal_v2_eval` (§3.2 of FINAL-DESIGN)

Identical to `_reversal_v2_eval` through the computation of `fillable` — same trigger (contiguous prior candle, buffered open-to-open |move| ≥ revThr), same contrarian side with ties→Up, same real-CLOB-only book with re-poll on one-sided books, same .53 effective-cost cap, spread ≤ 2c, top ≥ $200, revWinMin 255, freshness gates — with ONE additional condition inserted alongside `signal`: the impulse gate. Compute it from the buffered open-to-open history (13 contiguous completed 5m candles required — one more than the latentfire gate; the persisted `ivlHist` keeps 20, and the §3.2 cold-start rebuild rule applies with lookback 13): with `h` = completed open-to-open returns ending at the trigger (`h[-1]` = trigger move), `eff6 = abs(o_now - o_6ago) / sum(abs(r) for r in h[-6:])` (trigger move INCLUDED in both numerator span and denominator; compute the numerator from opens, not summed returns, to match the audited construction) and `cnt12 = sum(1 for r in h[-13:-1] if abs(r) >= impCntThr/100)` (trigger EXCLUDED). Gate passes iff `eff6 >= impEffMin and cnt12 <= impCntMax`; insufficient/non-contiguous history fails the gate (records nothing). On `fillable and gate`, the shadow records the identical would-be fill (`ask + slip`) into its own book; `stake=0.0` always, `f_full`/risk/bench logic never runs. Because paper fills are stake-independent and the gate is a deterministic function of public candle history, the paired delta vs `reversal_v2` on common signals is computable to the penny (design doctrine, §2). Log the gate features (`eff6`, `cnt12`) on EVERY flagship signal — selected or not — so the complement book falls out for free.

---

## 3. What each shadow must prove forward, and how long that takes

Cadence basis (design §8): ~67 flagship signals/day; 55% availability ⇒ ~37 measurement-book fills/day; impulse retention 68.2% ⇒ ~25 selected + ~12 complement fills/day. Per-fill settled-outcome SD ≈ 50c; per-fill cost SD ≈ 4.4c (censored-ledger IQR .450–.510). Power below: one-sided α=.05 / 90%-CI-lower-bound form, 80% power, block-bootstrap SE inflation bracketed [1.0, 1.15×] exactly as FINAL-DESIGN §8. All forward scoring on Polymarket resolutions, exact fee, realized fills.

### 3.1 `impulse_shadow` — four pre-registered forward checks

**F1 — Fill-mix conformance and the complement-fill prediction (days-to-weeks; falsifiable fastest).**
Claim: selected realized fill mix ≈ the .4774 anchor (pm-sample says it may land near .4978 = the +2c row); complement contrarian fills **1–2c richer** than selected (cascade-heavy complement — the confirmed trending-fill adjustment). Detecting a 1c fill differential at SD 4.4c needs ~**120 complement fills ≈ 10 days**; a 2c differential needs ~30 fills ≈ 3 days. If the differential fails to appear, the "paired delta reaches parity under honest fills" argument dies and the shadow is per-share-only. If selected fills land at ~.4978, quote the +2c sensitivity row as operative (TEST +5.2c) and stretch F2's clock accordingly.

**F2 — Selected book clears fees in absolute terms (weeks).**
Claim: net/share > 0 at realized fills (90% CI lb > 0). At the .4774 mix the point edge is q_sel − q\* = .5511 − .4949 = 5.6pp ⇒ **489–647 selected fills = 20–26 days** at 25/day. If F1 lands at the .4978 mix (edge 3.6pp): **1,206–1,595 fills = 48–64 days**. This is the shadow's Phase-1-style survival evidence.

**F3 — The gate effect itself, out-of-sample (the day-60 informational verdict).**
Claim: q_sel − q_comp > 0 on forward measurement-book fills (point estimate ~5.0–5.6pp; TRAIN 5.55pp, TEST 4.91pp). At the 68/32 split, SE = 1.074/√N ⇒ 80% power at a true 5pp needs **2,852–3,772 total measurement-book fills = 77–102 days** at 37/day. At day 60 (N≈2,215) power is **60–71%** — quote the CI either way. This check is the analogue of §8's latentfire gate verdict and should be published next to it at day 60: it either keeps the impulse gate alive as the best-evidenced overlay in the program or sends it to the same graveyard.

**F4 — §5.2 totals promotion (honest math: effectively unreachable — and that is fine).**
Promotion requires paired (shadow − flagship) net/share, 90% block-boot CI lb > 0, on ≥400 paired signals. The per-flagship-fill paired delta is 0 on selected fills and −pnl on complement fills (31.8% of fills), so its SD ≈ √0.318 · 50c ≈ 28c ⇒ at the 400-fill minimum (~11 days) the CI half-width is **±2.3–2.7c**. The 60d point estimate of the delta is **−0.01c at flat fills**; even under the confirmed trending-fill adjustment on the complement the delta is only **+0.31c to +0.62c** per flagship fill, which needs **~12,800–51,200 paired fills = 347–1,387 days** for 80% power. Plain statement: **`impulse_shadow` will not clear §5.2 on totals at its own point estimate on any realistic horizon; the expected 10-day verdict is "no change" indefinitely — the design working, not failing (§5.2).** Do NOT lower the bar to force it. The realistic promotion path is conditional: F1's fill differential materializes at the ≥1c end AND the forward complement underperforms its 60d showing — then the delta drifts toward the detectable range and §5.2 fires on its own schedule. Until then the shadow costs nothing and measures everything.

### 3.2 `rev20_shadow` (existing roster entry — band family adjacent; no spec change)

What it must prove: that the big-move per-share gradient exists at all. TRAIN says no (20+ q .5181 < 12–20 q .5264, −0.8pp); TEST says yes (.5648 vs .5459, +1.9pp). A powered test of +1.9pp at rev20's 42.6% retention needs **~17,500 measurement-book fills ≈ 475 days** — it can never clear §5.2 at the TEST point estimate. Its forward criterion is therefore a pre-registered SIGN check, not a powered test: at the day-60 review, if the forward 20+ vs 12–20 paired gradient is ≤ 0 (the TRAIN pattern again), retire `rev20_shadow` to [DEAD] with the other overlays; if positive, it stays a dashboard line and nothing more. It shares its fills with `measure_book`, so this costs zero machinery.

### 3.3 Everything else

`latentfire_v2`, `measure_book`, `frozen_baseline`: untouched — nothing in the three variant families alters their FINAL-DESIGN specs, cadences, or day-60 verdicts. The asym and band families produced no engine, no parameter, and no gate.

---

## 4. Dead list — do not retest

Standing kill pattern (applies throughout): **a TEST-only lift with no TRAIN support is DEAD.** The program has run dozens of tests; lone p≈0.05 is noise.

### impulse family (rejected branches of the surviving family)
1. **Price-only calm gate (pre-prior |move| < 4/6/8bps), all thresholds** — TRAIN-inverted (gate effect p=.66 wrong direction), TEST-only lift. Standing kill pattern.
2. **"Calm-before-the-spike" as a literal mechanism** — on TRAIN the calmest pre-prior buckets are the WORST reversion cohorts (q .5085 at 0–2bps vs .5352 at 8–12bps). The TEST gradient is regime coincidence.
3. **cnt12 ≤ 6 standalone** — direction-consistent both segments but only +0.33c over ungated on TEST at 83% retention; too weak to justify machinery outside the combined gate.
4. **Flavor B as an immediate flagship replacement** — paired TEST delta −0.61c (CI90 [−1.62, +0.39]) at flat fills; parity only under the trending-fill adjustment. Route is the pre-registered shadow → §5.2 path, nothing faster.
5. **A=0.32 (TRAIN-calibrated) as the deploy point** — per-share stronger but TEST retention .52 leaves ~35% of flagship total EV on the table; dominated by A=0.10 for the shadow's purpose.

### band family
6. **Band-limited 12–20bps trigger as flagship replacement** — TEST paired −0.44c vs take-all, total EV −35–46%; TRAIN support is p=.19 noise.
7. **Any magnitude-shaped trigger reweighting (either direction)** — TRAIN shape (.523/.533/.531/.510) and TEST shape (.552/.536/.570/.561) disagree; no weighting has TRAIN persistence.
8. **Dropping the 16–20 bucket ("12–16 + 20+" book)** — post-hoc slice after seeing fills; the bucket clears its own rich .5028 fill on BOTH splits (+1.3c/+1.6c); dies only at +2c sensitivity, which the cap handles anyway.
9. **pm-sample censored 25+ fills as evidence of "cheap monster fills"** — censoring artifact (n=2 of 8 under the cap); uncensored 25+ is the RICHEST bucket (.5475, 25% availability); the ledger (+0.9c, n=21) is the honest estimate.
10. **Relaxing the .53 cap to capture big-move signals** — q\*(.55)=.5673 exceeds even the best TEST bucket q; the ≥16bps fill premium (+1.2–2.4c) is a cost, not information. Re-confirms c_entryprice/kelly_table.

### asym family
11. **Any side encoding in reversal_v2 (side stake, side filter, side entry cap)** — delta p=.32 on 60d; live ledger sign-flips vs candles and again under .53 censoring; no fill-side skew (Down .5267 vs Up .5234, n=18/31). Original no-encode decision re-confirmed on 6× data.
12. **Tie-rule mechanism for the asymmetry** — quantified and rejected: fadeUP/buy-Down is the BETTER side despite paying the tie penalty; ex-tie-zone deltas stay insignificant (.5456 vs .5236).
13. **Move-size × side interaction** — bucket deltas incoherent across TRAIN/TEST (largest TEST bucket 30+bps flips negative for fadeUP).
14. **ETH same-direction confirmation as a filter** — 92% of impulses already market-wide; +0.2/0.3pp, cannot beat flagship; excluding btc-only signals is EV-negative (complement ~breakeven TRAIN +0.5c, positive TEST +2.3c, fold deltas −11.5..+16.8pp).
15. **Tightened ETH threshold (12–16bps)** — TEST-only gradient, flat TRAIN; identical shape to the rev20 trap.
16. **ETH-divergence veto (opposite-direction ≥8bps)** — 8 events in 60 days; unusable at this horizon.
17. **Side-conditional fill harvesting** — no structurally cheaper contrarian side exists (0.3c inside noise).

---

## 5. Artifacts

- Impulse (verification, reproduces every headline number): `work/verify-variant-impulse/{verify_impulse.py,verify_results.json}` (the originating agent's `work/variant-impulse/{impulse_test.py,impulse_results.json}` lived in its own workspace and is not present here; the verification artifacts are the auditable record).
- Gate parameters: `work/regime/deploy_spec.json` (A=0.10/B=6 deploy-calibrated; recalibration governance block).
- Band: `work/variant-band/{band_analysis.py,band_results.json,band_addendum.py,band_addendum.json}`.
- Asym: `work/variant-asym/{a_side_asym.py,a_side_asym_results.json,b_side_fills.py,b_side_fills_results.json,c_joint_impulse.py,c_joint_impulse_results.json}`.
- Design anchors: `FINAL-DESIGN.md` §2 (roster row), §5.1–5.3 (refit/promotion), §8 (power bracket convention).
