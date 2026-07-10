# Adversarial verification: regime "isolated impulse" gate (eff6 >= A AND cnt12 <= B)

Verifier lens: regime robustness & out-of-sample. Scripts: repro.py, attack.py, attack2.py
(attack.py had a units bug in its first run — efficiency denominator used relative moves vs
dollar numerator; fixed before any conclusions were drawn; corrected outputs in attack_out.json).

## Reproduction (repro.py, repro_out.json) — EXACT
- 17,280 candles, 60d, 0 gaps; 3,971 trigger trades; breakeven wr 0.5275 at p=0.51.
- TRAIN calibration reproduces A=0.32, B=6.
- TRAIN: ungated -0.612 c/sh (wr 0.5214) vs gated +3.195 c/sh (wr 0.5594), gate-effect block-boot p=0.0005 (10k reps, own seed).
- TEST: gated +4.015 c/sh, wr 0.5676, n=717, retention 0.522, p(pnl<=0)=0.0152. Matches claim to 3 decimals.
- Walk-forward pooled OOS (attack2.py): n=1468, +2.973 c/sh, wr 0.5572, retention 0.406,
  worst fold -3.333c. Matches. (I count the gate beating ungated in 5/5 OOS folds, not 4/5 —
  fold1 gated -3.33 vs ungated -5.02 is a beat; discrepancy is in the finding's favor.)

## Attacks
1. WEEKLY re-split (gate frozen at 0.32/6): gate beats ungated in 9/9 weeks; gated pps positive
   in 8/9 (only wk1, days 7-14, a -4.5c/sh crash week for ungated reversal, gated -4.0c).
2. THIRDS re-split: frozen gate per third: +2.07 / +3.89 / +4.02 c/sh where ungated was
   -0.74 / -0.56 / +2.64. Calibrating on first third alone picks (0.40, 6) ~= TRAIN pick;
   OOS mid third +3.04, last third +4.16.
3. REGIME by trailing-24h Kaufman efficiency (eff288 terciles, cuts 0.043/0.082):
   - trending tercile: ungated -0.44c -> gated +3.85c (n=599), gate-effect block-boot p=0.001.
   - top-decile trending (eff288>=0.132): ungated -3.50c -> gated +4.23c (n=172).
   - 10 most-trending DAYS: ungated -2.05c, gated -0.34c (n=353) — survives (near flat) a strongly
     trending stretch rather than blowing up.
   - calm tercile: gate adds ~nothing (gate-effect p=0.31); TEST-calm gated -1.16c on n=283,
     but block-boot p(pnl>=0)=0.35 — indistinguishable from noise. This is the one soft spot:
     on TEST the gate's profit came from mid+trending regimes, not calm.
4. DECOMPOSITION on TEST: eff6-only +3.82c (n=852), cnt-only +2.96c (n=1138), combo +4.02c
   (n=717), neither +1.13c (n=657). Everything positive on TEST (favorable period, as the
   finding itself discloses: TEST-alone incremental gate effect p~0.13, reproduced at 0.129).
5. PARAMETER STABILITY: per-10d-fold calibration wanders in A (0.06-0.40; B stays 3-8, mode 5-6),
   BUT the TEST sensitivity surface is a genuine plateau: min +2.0 c/sh over the full
   A in 0.06-0.38 x B in 1-7 grid, every cell positive — the effect does not depend on the exact
   thresholds, and walk-forward OOS stays +2.97c despite the wandering.
6. TEST n = 717 >= 30; walk-forward OOS n = 1468. Sufficiency met.

## Verdict: NOT REFUTED
The regime-robustness attack strengthens the finding: the gate's value concentrates exactly in
trending regimes where ungated reversal loses (consistent with the stated mechanism), it holds
under weekly and thirds re-splits with the gate frozen, and it is threshold-insensitive.
Caveats to carry forward: (a) incremental gate effect on TEST alone is not significant (p~0.13)
because TEST was reversal-friendly overall; the evidence is TRAIN-significant + TEST-persistent,
as the finding honestly states. (b) In the calmest regime tercile the gate adds nothing and the
TEST-calm gated slice is mildly negative (noise-level). (c) Deploy-spec trailing recalibration of
A (0.32 -> 0.10) is cosmetically large but immaterial given the plateau.
