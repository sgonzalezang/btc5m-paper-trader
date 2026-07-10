#!/usr/bin/env python3
"""
Deep-dive on the winning gate: eff6 >= a AND cnt <= b ("isolated impulse").
1) TRAIN(first 40d)/TEST(last 20d): calibrate on TRAIN, quote TEST; 1h-block bootstrap p-values.
2) Threshold sensitivity grid on TEST around the TRAIN-calibrated point.
3) Recalibration cadence experiment: trailing window W x refit period R, pooled OOS on the
   common span (last 20d), threshold-path volatility, calibration sample sizes.
"""
import json, random, sys

BASE = "/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad/work/regime"
exec(open(BASE + "/regime_tournament.py").read().split("# ---- folds")[0])
# gives: trades (with features), t, WIN_PNL, LOSE_PNL, BREAKEVEN, P_ENTRY, SHARES_50

t0 = t[0]
DAY = 86400.0
for x in trades:
    x["day"] = (x["t"] - t0) / DAY
    x["blk"] = x["i"] // 12          # 1-hour block id

TRAIN = [x for x in trades if x["day"] < 40]
TEST  = [x for x in trades if x["day"] >= 40]

EFF6_GRID = [round(0.06 + 0.02*k, 2) for k in range(18)]   # 0.06..0.40
CNT_GRID  = list(range(0, 9))

def gate(x, a, b): return x["eff6"] >= a and x["cnt"] <= b

def calib(sub):
    best = None
    min_n = max(20, int(0.25 * len(sub)))
    for a in EFF6_GRID:
        for b in CNT_GRID:
            g = [x for x in sub if gate(x, a, b)]
            if len(g) < min_n: continue
            tot = sum(x["pnl"] for x in g)
            if best is None or tot > best[0]:
                best = (tot, a, b, len(g))
    return best

def st(sub):
    if not sub: return {"n": 0}
    nn = len(sub); w = sum(x["win"] for x in sub); p = sum(x["pnl"] for x in sub)/nn
    return {"n": nn, "wr": round(w/nn, 4), "pps_c": round(p*100, 3), "usd50": round(p*SHARES_50, 3)}

# ---------- 1) TRAIN/TEST ----------
cal = calib(TRAIN)
_, A, B, _ = cal
print(f"TRAIN-calibrated gate: eff6 >= {A} AND cnt <= {B}")
gTR = [x for x in TRAIN if gate(x, A, B)]
gTE = [x for x in TEST  if gate(x, A, B)]
lfTE = [x for x in TEST if x["eff12"] <= 0.48]
print("TRAIN all:", st(TRAIN), " gated:", st(gTR))
print("TEST  all:", st(TEST),  " gated:", st(gTE), " retention:", round(len(gTE)/len(TEST),3))
print("TEST  latentfire eff12<=0.48:", st(lfTE))

# block bootstrap helpers
def blocks_of(sub):
    d = {}
    for x in sub: d.setdefault(x["blk"], []).append(x)
    return list(d.values())

def boot_p(sub_blocks, statfn, reps=10000, seed=7):
    rng = random.Random(seed)
    nb = len(sub_blocks); cnt_le = 0; used = 0
    for _ in range(reps):
        picks = [sub_blocks[rng.randrange(nb)] for _ in range(nb)]
        flat = [x for blk in picks for x in blk]
        v = statfn(flat)
        if v is None: continue
        used += 1
        if v <= 0: cnt_le += 1
    return cnt_le / used, used

# TRAIN gate effect: wr(gated) - wr(all)  (does the gate select better trades?)
def eff_stat(flat):
    g = [x for x in flat if gate(x, A, B)]
    if len(g) < 10: return None
    return sum(x["win"] for x in g)/len(g) - sum(x["win"] for x in flat)/len(flat)
pTR, uTR = boot_p(blocks_of(TRAIN), eff_stat)
# TEST gated mean pnl > 0
def pnl_stat(flat):
    return sum(x["pnl"] for x in flat)/len(flat) if flat else None
pTE, uTE = boot_p(blocks_of(gTE), pnl_stat)
# TEST gate effect
pTE2, uTE2 = boot_p(blocks_of(TEST), eff_stat)
# TEST ungated mean pnl > 0 (for contrast)
pTE3, _ = boot_p(blocks_of(TEST), pnl_stat)
print(f"bootstrap p (1h blocks, 10k): TRAIN gate-effect<=0: {pTR:.4f} | TEST gated pnl<=0: {pTE:.4f} | TEST gate-effect<=0: {pTE2:.4f} | TEST ungated pnl<=0: {pTE3:.4f}")

# ---------- 2) sensitivity grid on TEST ----------
sens = []
print("\nTEST pps (cents/share) by (a=eff6min, b=cntmax); TRAIN pick marked *")
hdr = "a\\b " + " ".join(f"{b:>7}" for b in range(1, 8))
print(hdr)
for a in [0.06, 0.10, 0.14, 0.18, 0.22, 0.26, 0.30, 0.34, 0.38]:
    row = []
    for b in range(1, 8):
        g = [x for x in TEST if gate(x, a, b)]
        v = (sum(x["pnl"] for x in g)/len(g)*100) if len(g) >= 30 else None
        sens.append({"a": a, "b": b, "n": len(g), "pps_c": None if v is None else round(v, 2)})
        mark = "*" if (a == A and b == B) else " "
        row.append(("   --  " if v is None else f"{v:6.2f}{mark}"))
    print(f"{a:4} " + " ".join(row))

# ---------- 3) recalibration cadence ----------
print("\nRecalibration schemes, pooled OOS restricted to common span day>=40:")
schemes = [(10,10),(20,10),(30,10),(40,10),(20,5),(40,5),(10,5)]
scheme_rows = []
for (W, R) in schemes:
    oos = []; path = []; caln = []
    tt = 40.0
    while tt < 60.0 - 1e-9:
        calsub = [x for x in trades if tt - W <= x["day"] < tt]
        cb = calib(calsub)
        if cb is not None:
            _, a, b, ncal = cb
            path.append((round(tt,1), a, b)); caln.append(ncal)
            oos.extend(x for x in trades if tt <= x["day"] < tt + R and gate(x, a, b))
        tt += R
    s = st(oos)
    # threshold path volatility
    da = [abs(path[i][1]-path[i-1][1]) for i in range(1, len(path))]
    db = [abs(path[i][2]-path[i-1][2]) for i in range(1, len(path))]
    row = {"W": W, "R": R, "oos": s, "path": path, "cal_n": caln,
           "mean_step_a": round(sum(da)/len(da), 3) if da else None,
           "mean_step_b": round(sum(db)/len(db), 2) if db else None}
    scheme_rows.append(row)
    print(f"  W={W:2}d R={R:2}d -> OOS {s}  path={path}  cal_n={caln}")

# static TRAIN fit applied to same span (cadence baseline: never refit)
static_oos = [x for x in TEST if gate(x, A, B)]
print(f"  static 40d fit (no refit)   -> OOS {st(static_oos)}")

# full 10d-refit path over the whole series for step-change stats (uses all 5 refits)
full_path = []
tt = 10.0
while tt < 60.0 - 1e-9:
    calsub = [x for x in trades if max(0, tt-20) <= x["day"] < tt]
    cb = calib(calsub)
    if cb: full_path.append((round(tt,1), cb[1], cb[2], cb[3]))
    tt += 10.0
print("\n20d-window refit path over whole series (t, a, b, cal_n):", full_path)

json.dump({"train_cal": {"a": A, "b": B},
           "train_all": st(TRAIN), "train_gated": st(gTR),
           "test_all": st(TEST), "test_gated": st(gTE), "test_latentfire": st(lfTE),
           "boot_p": {"train_gate_effect": pTR, "test_gated_pnl": pTE,
                      "test_gate_effect": pTE2, "test_ungated_pnl": pTE3},
           "sensitivity_test": sens, "schemes": scheme_rows,
           "static_test": st(static_oos), "full_refit_path_w20": full_path},
          open(BASE + "/deepdive_results.json", "w"), indent=1)
print("\nsaved ->", BASE + "/deepdive_results.json")
