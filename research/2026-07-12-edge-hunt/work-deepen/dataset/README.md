# signals_60d.json — THE canonical gated-signal dataset (wave-2 DEEPENING)

Built by `build_signals.py` (python3 stdlib only) from `data/cb5m.json` + `data/cb1m.json`,
validated against the 36-record live measurement book (`data/state_extract.json`), the
v3-era ledger (`data/trades_unified.json`), and the prior program's registered counts
(`2026-07-10-edge-hunt/VARIANTS.md`). Standalone copy of the validation block:
`validation.json`. **Every wave-2 agent should consume this file, not re-derive the
pipeline.**

## Headline numbers

| | value |
|---|---|
| rows (every 5m interval, May 11 12:00 → Jul 13 03:35 UTC) | **18,044** (cb5m has ZERO gaps; gateReady on 18,032 — only the first 12 rows lack the 13-interval history) |
| triggers (prior \|move\| ≥ 12bps) | **4,102** |
| gated signals (trigger AND gatePass) | **2,802** (2,015 TRAIN / 787 TEST) |
| ties (\|ret0\| < 1bp) among gated | 182 |
| gated q excluding ties | **.5489 pooled / .5408 TRAIN / .5700 TEST** |
| gated q ties-as-loss | .5132 / .5097 / .5222 |
| prior-program reconciliation (their exact window, their tie rule) | **n_all 4,022 = EXACT, n_sel 2,742 = EXACT**, q .5503 vs claimed .5511 (Δ = ~2 wins of 2,742; residual attributable to their dollar-diff eff6 denominator and/or r0==0 handling — immaterial) |

## Row schema

```json
{"t0": 1783701600,            // interval start, epoch seconds UTC
 "trigger": true,             // |ret(t0-300)|*100 >= 0.12  (bot: prior_move% >= revThr)
 "trig_move": -0.234,         // SIGNED prior-interval move, % of open (-0.234 = -23.4bps)
 "side": "up",                // contrarian side ("down" if trig_move>0 else "up"); null if !trigger
 "eff6": 0.4024,              // gate efficiency, trigger INCLUDED, round4; null if !gateReady
 "cnt12": 2,                  // # |move|>=12bps among 12 pre-trigger intervals, trigger EXCLUDED
 "gateReady": true,           // 13 contiguous completed intervals ending at the trigger existed
 "gatePass": true,            // gateReady AND eff6>=0.10 (unrounded) AND cnt12<=6
 "label": "up",               // open-to-open outcome of [t0,t0+300): up / down / tie(|ret0|<1bp)
 "ret0": 0.0981,              // SIGNED label return, % of open
 "split": "test",             // train = t0 < 1782432000 (Jun 26 00:00 UTC), else test
 "feats": {                   // ALL strictly pre-decision (nothing after t0)
   "pm": 0.234,               // |trig_move|, % — bot's feature convention
   "eff6": 0.4024, "cnt12": 2,   // duplicated for feats consumers
   "hour": 16,                // UTC hour of t0 (bot convention)
   "dow": 4,                  // UTC weekday, 0=Mon
   "vol10m": 0.3396,          // trailing 10-min range% (hi-lo)/lo*100 over [t0-600, t0)
   "vol_src": "1m",           // "1m" = 10x cb1m candles; "5m2" = 2x cb5m candle proxy (see below)
   "ret15m": -0.22,           // open(t0) vs open(t0-900), %
   "ret30m": -0.2086,         // open(t0) vs open(t0-1800), %
   "absret1h": 0.2157 },      // |open(t0) vs open(t0-3600)|, %
 "alt": { ... },              // ONLY on 270 rows where the open-to-close convention flips
                              // trigger (45) or gatePass (228): {conv, trigger, trig_move, eff6, cnt12, gatePass}
 "real": {                    // ONLY on 43 rows with live data at this t0 (any trigger row, incl. gate-rejects
                              // so the reversal_v2 control fills are usable for gate-increment work)
   "measure": {"ask":0.51, "cost_firstpoll":0.5375, "sized":false, "skip":"f_nonpos", "win":1},
   "ledger": [{"eng":"reversal_v2","ask":0.51,"entry":0.52,"cost":0.537472,
               "entrySec":22,"result":"win","side":"up"}] }}
```

Units: **all returns/moves are in % of open** (0.12 = 12bps). `cost` fields are $/share
including the 7% fee on p(1-p). `entry` = ask + 1c slip (ledger). `cost_firstpoll` is the
measurement book's FIRST-POLL cost — per wave-1 R4 it is NOT the operated fill (12/21
f_nonpos skips were later filled ~11c cheaper); always prefer `real.ledger[].entry` for
operated economics.

## Conventions (the load-bearing choices)

1. **Returns are buffered open-to-open from cb5m**: r(t) = (open(t+300)-open(t))/open(t).
   This is the prior program's registered convention (VARIANTS.md baseline) and reconciles
   its counts EXACTLY. The bot live uses its own 4s-poll feed's (last-open)/open, which
   differs from candles by ~1-2bps median, max ~5-7bps per interval (measured directly on
   the live ivlHist2 snapshot). Candle open-to-close is nearly identical to open-to-open
   (Coinbase next-open ≈ close); rows where the o-c convention would flip a decision bit
   carry `alt`.
2. **Gate is a faithful _impulse_gate port** (btc5m_bot.py ~line 535): eff6 = |prod(1+r)-1| /
   sum|r| over the 6 returns ending at the trigger (INCLUDED), den==0 → 1.0; cnt12 counts
   |r| ≥ 0.0012 over the 12 returns BEFORE the trigger (EXCLUDED); needs all 13 contiguous;
   pass iff eff6 ≥ 0.10 (unrounded) AND cnt12 ≤ 6. Trigger compares |r|*100 ≥ 0.12 exactly
   as the bot does.
3. **Labels**: open-to-open; `tie` if |ret0| < 1bp. Ledger PM resolutions agree with
   non-tie labels **929/940 = 98.8%** (1,014 resolved t0s joined; sub-2bps non-tie rows
   97.7%). Ties resolved Up only 32/74 = 43% live — do NOT assume ties→Up (wave-1 killed
   that freebie, #35). Conservative q = ties-as-loss; honest q = exclude ties and treat
   tie mass (182/2,802 = 6.5% of gated) as a separate outcome.
4. **vol10m windows end at t0** ([t0-600, t0)) — the bot's live vol window extends up to
   45s INTO the trade interval. Ours is strictly pre-decision (lookahead-safe, slightly
   staler). Against the 32 measure-book `f.vol` values: median |Δ| = 0.022 (vol ~0.5
   typical, so ~4% relative). `vol_src="1m"` only exists from Jun 26 (cb1m start) — ALL
   TRAIN-era rows use the 2-candle 5m proxy (13,253 rows 5m2 / 4,790 rows 1m / 1 null).
   Do not mix vol sources in a fitted model without a source dummy.

## Fill-price realism layer

Frozen prior-program fill model (top-level `meta.fill_model`, identical for every signal —
it is NOT row-conditional, so it lives in the header, not per row):
- fill anchors p25/p50/p75 = **.45/.49/.51** (fill price INCLUDES +1c slip), share-wtd mean
  .4724, hurdle q* = .4898, availability ~0.55 at the 53c cap; **unfillable signals are
  SKIPS, never 50c fills**.
- cost anchors (fee-inclusive): .467325 / .507497 / .527493.
- EV/share = q − p − 0.07·p·(1−p); gas $0.004/trade.
Real asks where known are in `real` (35 measure joins, 43 ledger-t0 joins, 30 on gate-pass
rows).

## Validation results (divergences are findings — full detail in validation.json)

**(a) Measurement book (36 records).** 30/35 in-window records match as candle
trigger+gate-pass with side 34/35. **eff6 4dp-exact: 0/32** — expected and now quantified:
the book's features come from the bot's private feed; six ~1-2bps-noisy returns give
median |Δeff6| = 0.042 (max 0.22). cnt12 exact 19/32, ±1 32/32. pm median |Δ| = 1.02bps
(max 6.9bps). The open-to-close alt convention does NO better (same 0/32, 19/32) — the
divergence is feed-vs-candle, not o-o vs o-c. **Consequence for wave-2 agents: any model
fitted on candle eff6/cnt12 sees the live gate through ~0.04-0.06 eff6 noise and ±1 cnt12
noise at the boundary; do not tune thresholds finer than this.**
The 5 mismatches cluster ENTIRELY in the Jul 13 01:05–02:20 cascade: 4x candle cnt12=7 vs
book 6 (bot-looser, exactly wave-1 R7's "cnt12 ±1 on borderline cascades"), 1x borderline
trigger (candle 11.1bps vs feed 12.9bps — the trigger interval 1783908900 is IN the live
ivlHist2 snapshot: feed ret +12.90bps vs candle +11.10bps, mechanism proven directly).
1 record (Jul 13 03:40) is past the candle file's label horizon.

**(b) v3-era ledger (106 trades: 27 impulse_v2 / 35 impulse50 / 44 reversal_v2).**
13 exception trade-rows over 7 t0s, ALL explained: 3 rows at t0 1783914000 (beyond candle
window); 3 rows at 1783909200 (the proven borderline trigger above); 7 rows at 4 t0s in
the same Jul 13 cascade where candle cnt12=7 (+1 with candle eff6 .0856 vs feed ≥.10).
Zero unexplained exceptions. reversal_v2 (ungated) t0s are candle triggers 42/44 with the
same 2 explained misses.

**(c) Prior program.** Over their exact candle window (May 11 11:55 → Jul 10 11:50), this
pipeline reproduces **n_all = 4,022 and n_sel = 2,742 EXACTLY (Δ=0)**; q_sel .5503 vs
their .5511 = ~2 wins of 2,742, residual from their slightly different eff6 denominator
(dollar diffs) and/or r0==0 tie handling. The dataset extends their window by ~2.6 days
(+60 gated signals).

**Coverage / censoring (the surprise worth knowing).** In the live measure window
(Jul 10 16:40 → Jul 13 03:40) the candle pipeline finds **50 gate-passes but the measure
book holds only 36** (30 matching + 5 convention-mismatch + 1 horizon): **20 candle
gate-passes have NO live record at all**. `_measure_record` only fires when the signal is
FILLABLE (market found, ask ≤ 53c cap, spread/depth/fresh, first-45s window) — so the
measurement book is availability-censored by construction. 30 measured / 50 candle
signals ≈ 0.60 reach-rate, consistent with the prior program's ~55% availability estimate.
**The measurement book cannot be treated as the signal universe; this dataset is.**

**Borderline mass.** 637/4,102 triggers (15.5%) sit within ±1.5bps of the 12bps threshold,
and 847 near-misses sit at 10.5-12bps — the feed-vs-candle noise band. Threshold-touching
analyses must treat trigger membership as ~1-2bps fuzzy.

## Known limitations

- Candle horizon ends Jul 13 03:40 UTC; last labelable t0 is 03:35.
- `real.measure.cost_firstpoll` carries R4's first-poll semantics (see wave-1 FINDINGS).
- 3 early measure records lack feats; their ask was recovered by inverting
  cost = 1.07p − 0.07p² and subtracting the 1c slip.
- The fill model is frozen from the prior program; it is a 3-day-window estimate
  (DESIGN.md CONFIRMED#1 caveats apply).
- Nothing here says anything about the gate INCREMENT (R7: unproven live) — this file
  just makes the signal universe and its censoring explicit.
