#!/usr/bin/env python3
"""
ADVERSARIAL VERIFICATION of variant family "impulse" Flavor B:
fixed gate eff6>=0.10 AND cnt12<=6 on flagship reversal_v2 signals.

Independent implementation (own code, own seed). Lens: regime robustness & OOS.
Checks:
 0. data integrity (gapless 5m), baseline reproduction (4023/.5334 etc.)
 1. headline reproduction: TRAIN/TEST q_sel/q_comp, nets at .4774/+1c/+2c,
    block-boot gate-effect p on TRAIN and TEST, 6x10d folds
 2. lookahead-free check: TRAIN-calibrated A=0.32 gate on TEST
 3. weekly folds (~9): gate effect + net_sel + paired delta per week
 4. alternate thirds (3x20d): gate effect per third; alt split TEST=first 20d
 5. Kaufman eff12 regime segmentation: gate effect within eff12<=0.48 and >0.48,
    and within eff12 terciles (TRAIN/TEST separately for the binary split)
 6. paired delta vs flagship: per-fold, leave-one-fold-out, TEST + full CI
"""
import json, random

BASE = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-10-edge-hunt"
OUT  = "/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad/work/verify-variant-impulse"
THR = 0.0012
P0 = 0.4774
random.seed(20260991)  # different seed from original on purpose
B = 4000

d = json.load(open(BASE + "/data/cb5m.json"))
t, o, c = d["t"], d["o"], d["c"]
n = len(t)
gaps = sum(1 for i in range(1, n) if t[i] - t[i-1] != 300)
assert gaps == 0, "data not gapless: %d gaps" % gaps

moves = [(o[i+1] - o[i]) / o[i] for i in range(n - 1)]
absm = [abs(m) for m in moves]

def eff(i, W):
    den = sum(abs(o[j + 1] - o[j]) for j in range(i - W, i))
    return abs(o[i] - o[i - W]) / den if den > 0 else 0.0

sig_all, sig = [], []
for i in range(1, n):
    pm = moves[i - 1]
    if abs(pm) < THR:
        continue
    up = c[i] >= o[i]                       # tie -> Up
    win = (not up) if pm > 0 else up        # contrarian
    r = {"i": i, "t": t[i], "win": 1 if win else 0, "pm": abs(pm)}
    sig_all.append(r)
    if i >= 13:
        r = dict(r)
        r["eff6"] = eff(i, 6)
        r["eff12"] = eff(i, 12)
        r["cnt12"] = sum(1 for j in range(i - 13, i - 1) if absm[j] >= THR)
        sig.append(r)

t0 = t[0]
for s in sig:
    dt = s["t"] - t0
    s["fold"] = min(5, int(dt / (10 * 86400)))
    s["week"] = int(dt / (7 * 86400))
    s["third"] = min(2, int(dt / (20 * 86400)))
    s["seg"] = "TRAIN" if dt < 40 * 86400 else "TEST"
    s["blk"] = int(dt // 3600)

def q_of(z): return sum(x["win"] for x in z) / len(z) if z else None
def fee(p): return 0.07 * p * (1 - p)
def pnl(x, p): return (1 - p - fee(p)) if x["win"] else (-p - fee(p))
def net(z, p): return sum(pnl(x, p) for x in z) / len(z) if z else None

TRAIN = [x for x in sig if x["seg"] == "TRAIN"]
TEST  = [x for x in sig if x["seg"] == "TEST"]

out = {"n_candles": n, "gaps": gaps}
tr_all = [x for x in sig_all if x["t"] - t0 < 40 * 86400]
te_all = [x for x in sig_all if x["t"] - t0 >= 40 * 86400]
out["baseline"] = {"full": [len(sig_all), round(q_of(sig_all), 4)],
                   "train": [len(tr_all), round(q_of(tr_all), 4)],
                   "test": [len(te_all), round(q_of(te_all), 4)]}

gate = lambda x: x["eff6"] >= 0.10 and x["cnt12"] <= 6
gate32 = lambda x: x["eff6"] >= 0.32 and x["cnt12"] <= 6

def seg_rep(z, fn):
    sel = [x for x in z if fn(x)]
    comp = [x for x in z if not fn(x)]
    return {"n_sel": len(sel), "n_comp": len(comp),
            "retention": round(len(sel) / len(z), 4),
            "q_all": round(q_of(z), 4), "q_sel": round(q_of(sel), 4),
            "q_comp": round(q_of(comp), 4) if comp else None,
            "net_sel_.4774_c": round(net(sel, P0) * 100, 2),
            "net_sel_.4874_c": round(net(sel, 0.4874) * 100, 2),
            "net_sel_.4974_c": round(net(sel, 0.4974) * 100, 2)}

out["B_train"] = seg_rep(TRAIN, gate)
out["B_test"]  = seg_rep(TEST, gate)
out["B32_train"] = seg_rep(TRAIN, gate32)
out["B32_test"]  = seg_rep(TEST, gate32)

# block bootstrap
def blocks(z):
    bl = {}
    for x in z:
        bl.setdefault(x["blk"], []).append(x)
    return list(bl.values())

def boot(z, fn_stat, reps=B):
    bl = blocks(z); nb = len(bl); res = []
    for _ in range(reps):
        s = [x for _ in range(nb) for x in bl[random.randrange(nb)]]
        v = fn_stat(s)
        if v is not None:
            res.append(v)
    return res

def gate_effect(s, fn=gate):
    a = [x for x in s if fn(x)]; b2 = [x for x in s if not fn(x)]
    if not a or not b2: return None
    return q_of(a) - q_of(b2)

for lbl, z in (("train", TRAIN), ("test", TEST)):
    bs = boot(z, gate_effect)
    bs2 = boot(z, lambda s: net([x for x in s if gate(x)], P0))
    out["boot_" + lbl] = {
        "p_gate_effect_le_0": round(sum(1 for v in bs if v <= 0) / len(bs), 4),
        "p_net_sel_le_0": round(sum(1 for v in bs2 if v <= 0) / len(bs2), 4)}

# 6x10d folds: q_sel, net_sel, paired delta (variant total - flagship total)
folds = []
for k in range(6):
    f = [x for x in sig if x["fold"] == k]
    sel = [x for x in f if gate(x)]
    comp = [x for x in f if not gate(x)]
    folds.append({"fold": k, "n_all": len(f), "n_sel": len(sel),
                  "q_all": round(q_of(f), 4), "q_sel": round(q_of(sel), 4),
                  "q_comp": round(q_of(comp), 4) if comp else None,
                  "gate_eff_pp": round((q_of(sel) - q_of(comp)) * 100, 2) if comp else None,
                  "net_sel_c": round(net(sel, P0) * 100, 2),
                  "paired_delta_tot": round(-sum(pnl(x, P0) for x in comp), 2)})
out["folds_10d"] = folds
out["loo_paired_delta_full60d_tot"] = {
    "all": round(-sum(pnl(x, P0) for x in sig if not gate(x)), 2),
    "drop_each_fold": [round(-sum(pnl(x, P0) for x in sig if not gate(x) and x["fold"] != k), 2)
                       for k in range(6)]}

# weekly folds
weeks = []
for w in sorted(set(x["week"] for x in sig)):
    f = [x for x in sig if x["week"] == w]
    sel = [x for x in f if gate(x)]
    comp = [x for x in f if not gate(x)]
    weeks.append({"week": w, "n_all": len(f), "n_sel": len(sel),
                  "q_sel": round(q_of(sel), 4) if sel else None,
                  "q_comp": round(q_of(comp), 4) if comp else None,
                  "gate_eff_pp": round((q_of(sel) - q_of(comp)) * 100, 2) if sel and comp else None,
                  "net_sel_c": round(net(sel, P0) * 100, 2) if sel else None,
                  "paired_delta_tot": round(-sum(pnl(x, P0) for x in comp), 2)})
out["weekly"] = weeks
ge = [w["gate_eff_pp"] for w in weeks if w["gate_eff_pp"] is not None]
ns = [w["net_sel_c"] for w in weeks if w["net_sel_c"] is not None]
out["weekly_summary"] = {"n_weeks": len(weeks),
                         "gate_eff_pos": sum(1 for v in ge if v > 0),
                         "net_sel_pos": sum(1 for v in ns if v > 0),
                         "paired_delta_pos": sum(1 for w in weeks if w["paired_delta_tot"] > 0)}

# alternate thirds
thirds = []
for k in range(3):
    f = [x for x in sig if x["third"] == k]
    sel = [x for x in f if gate(x)]
    comp = [x for x in f if not gate(x)]
    thirds.append({"third": k, "n_all": len(f), "n_sel": len(sel),
                   "q_sel": round(q_of(sel), 4), "q_comp": round(q_of(comp), 4),
                   "gate_eff_pp": round((q_of(sel) - q_of(comp)) * 100, 2),
                   "net_sel_c": round(net(sel, P0) * 100, 2)})
out["thirds_20d"] = thirds
# alternate 2/3-1/3 split: TEST = FIRST third (reverse-chronological robustness)
alt_test  = [x for x in sig if x["third"] == 0]
out["alt_split_test_first20d"] = seg_rep(alt_test, gate)
bs = boot(alt_test, gate_effect)
out["alt_split_test_first20d"]["boot_p_gate_effect_le_0"] = \
    round(sum(1 for v in bs if v <= 0) / len(bs), 4)

# eff12 regime segmentation
def reg_rep(z, lbl):
    sel = [x for x in z if gate(x)]
    comp = [x for x in z if not gate(x)]
    return {"regime": lbl, "n_all": len(z), "n_sel": len(sel),
            "q_sel": round(q_of(sel), 4) if sel else None,
            "q_comp": round(q_of(comp), 4) if comp else None,
            "gate_eff_pp": round((q_of(sel) - q_of(comp)) * 100, 2) if sel and comp else None,
            "net_sel_c": round(net(sel, P0) * 100, 2) if sel else None}

segm = {}
for scope_lbl, scope in (("full60d", sig), ("TRAIN", TRAIN), ("TEST", TEST)):
    lo = [x for x in scope if x["eff12"] <= 0.48]
    hi = [x for x in scope if x["eff12"] > 0.48]
    segm[scope_lbl] = [reg_rep(lo, "eff12<=0.48"), reg_rep(hi, "eff12>0.48")]
effs = sorted(x["eff12"] for x in sig)
t1, t2 = effs[len(effs)//3], effs[2*len(effs)//3]
segm["terciles_full60d"] = [
    reg_rep([x for x in sig if x["eff12"] <= t1], "eff12 lo (<=%.3f)" % t1),
    reg_rep([x for x in sig if t1 < x["eff12"] <= t2], "eff12 mid"),
    reg_rep([x for x in sig if x["eff12"] > t2], "eff12 hi (>%.3f)" % t2)]
out["eff12_regimes"] = segm

# paired delta CIs (variant - flagship = -complement), per flagship signal
def paired_ci(z):
    bl = blocks(z); nb = len(bl); ds = []
    for _ in range(B):
        s = [x for _ in range(nb) for x in bl[random.randrange(nb)]]
        ds.append(-sum(pnl(x, P0) for x in s if not gate(x)) / len(s))
    ds.sort()
    return {"mean_c": round(sum(ds) / len(ds) * 100, 3),
            "ci90_c": [round(ds[int(0.05 * len(ds))] * 100, 3),
                       round(ds[int(0.95 * len(ds))] * 100, 3)],
            "p_ge_0": round(sum(1 for v in ds if v >= 0) / len(ds), 4)}
out["paired_delta_test"] = paired_ci(TEST)
out["paired_delta_full"] = paired_ci(sig)

json.dump(out, open(OUT + "/verify_regime_oos_results.json", "w"), indent=1)
print(json.dumps(out, indent=1))
