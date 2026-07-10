#!/usr/bin/env python3
"""
Sensitivity / decomposition for flavor B (eff6 >= A AND cnt12 <= B).

Purpose:
 1. Lookahead audit: A=0.10 in deploy_spec.json was calibrated on trailing 20d
    as of 2026-07-10 == our TEST window. If results only hold at A=0.10 and not
    at the TRAIN-calibrated A=0.32 (or across the plateau), TEST is contaminated.
 2. Leg decomposition: eff6-only vs cnt12-only vs combined (cnt12-alone was the
    regime family's unstable +1.11c OOS finding; do not silently contradict).
 3. Paired totals vs flagship per fold at mean fill.
Conventions identical to impulse_test.py.
"""
import json, random

BASE = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-10-edge-hunt"
OUT  = BASE + "/work/variant-impulse"
MOVE_THR = 0.0012
P0 = 0.4774
random.seed(20260711)

def cost(p): return p + 0.07 * p * (1 - p)
def pnl(x, p):
    fee = 0.07 * p * (1 - p)
    return (1 - p - fee) if x["win"] else (-p - fee)

d = json.load(open(BASE + "/data/cb5m.json"))
t, o, c = d["t"], d["o"], d["c"]
n = len(t)
moves = [(o[i+1] - o[i]) / o[i] for i in range(n - 1)]
absm = [abs(m) for m in moves]
def eff(i, W):
    num = abs(o[i] - o[i-W])
    den = sum(abs(o[j+1] - o[j]) for j in range(i-W, i))
    return num / den if den > 0 else 0.0

sig = []
for i in range(13, n):
    pm = moves[i-1]
    if abs(pm) < MOVE_THR: continue
    up = c[i] >= o[i]
    win = (not up) if pm > 0 else up
    sig.append({"i": i, "t": t[i], "win": 1 if win else 0,
                "eff6": eff(i, 6),
                "cnt12": sum(1 for j in range(i-13, i-1) if absm[j] >= MOVE_THR)})
t0 = t[0]
for s in sig:
    s["fold"] = min(5, int((s["t"] - t0) / (10 * 86400)))
    s["seg"] = "TRAIN" if (s["t"] - t0) < 40 * 86400 else "TEST"

TRAIN = [x for x in sig if x["seg"] == "TRAIN"]
TEST  = [x for x in sig if x["seg"] == "TEST"]
def q_of(z): return sum(x["win"] for x in z) / len(z) if z else None
def rep(seg, fn):
    sel = [x for x in seg if fn(x)]
    if not sel: return None
    return {"n": len(sel), "ret": round(len(sel)/len(seg), 3),
            "q": round(q_of(sel), 4),
            "net_c": round((q_of(sel) - cost(P0)) * 100, 2)}

out = {}
# ---- 1. parameter plateau: A x B grid, fixed evaluation (no fitting) ----
grid = {}
for A in (0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.32, 0.40):
    for B in (4, 5, 6, 7, 8):
        fn = (lambda a, b: lambda x: x["eff6"] >= a and x["cnt12"] <= b)(A, B)
        grid["A=%.2f,B=%d" % (A, B)] = {"TRAIN": rep(TRAIN, fn), "TEST": rep(TEST, fn)}
out["plateau"] = grid

# ---- 2. leg decomposition ----
legs = {
    "eff6>=0.10_only": lambda x: x["eff6"] >= 0.10,
    "eff6>=0.32_only": lambda x: x["eff6"] >= 0.32,
    "cnt12<=6_only":   lambda x: x["cnt12"] <= 6,
    "combined_A010_B6": lambda x: x["eff6"] >= 0.10 and x["cnt12"] <= 6,
    "combined_A032_B6": lambda x: x["eff6"] >= 0.32 and x["cnt12"] <= 6,
}
out["legs"] = {k: {"TRAIN": rep(TRAIN, fn), "TEST": rep(TEST, fn)} for k, fn in legs.items()}

# ---- 3. per-fold paired totals vs flagship at mean fill ----
fnB = lambda x: x["eff6"] >= 0.10 and x["cnt12"] <= 6
folds = []
for k in range(6):
    f = [x for x in sig if x["fold"] == k]
    sel = [x for x in f if fnB(x)]
    comp = [x for x in f if not fnB(x)]
    folds.append({
        "fold": k, "n_all": len(f), "n_sel": len(sel),
        "net_all_c": round((q_of(f) - cost(P0)) * 100, 2),
        "net_sel_c": round((q_of(sel) - cost(P0)) * 100, 2) if sel else None,
        "net_comp_c": round((q_of(comp) - cost(P0)) * 100, 2) if comp else None,
        "tot_flagship_shareunits": round(sum(pnl(x, P0) for x in f), 2),
        "tot_variant_shareunits": round(sum(pnl(x, P0) for x in sel), 2),
    })
out["folds_paired"] = folds

# pooled 60d complement
compall = [x for x in sig if not fnB(x)]
out["complement_60d"] = {"n": len(compall), "q": round(q_of(compall), 4),
                         "net_c_at_.4774": round((q_of(compall) - cost(P0)) * 100, 2),
                         "net_c_at_.4874": round((q_of(compall) - cost(0.4874)) * 100, 2),
                         "net_c_at_.4974": round((q_of(compall) - cost(0.4974)) * 100, 2)}

# ---- 4. block-boot paired delta (variant - flagship) total EV, TEST ----
def blocks_of(sub):
    bl = {}
    for x in sub:
        bl.setdefault(int((x["t"] - t0) // 3600), []).append(x)
    return list(bl.values())
bl = blocks_of(TEST)
nb = len(bl)
deltas = []
for _ in range(4000):
    samp = [x for _ in range(nb) for x in bl[random.randrange(nb)]]
    dtot = -sum(pnl(x, P0) for x in samp if not fnB(x))   # variant - flagship
    deltas.append(dtot / len(samp))                        # per flagship signal
deltas.sort()
out["test_paired_delta_per_flagship_signal_c"] = {
    "mean": round(sum(deltas)/len(deltas) * 100, 3),
    "ci90": [round(deltas[int(0.05*len(deltas))] * 100, 3),
             round(deltas[int(0.95*len(deltas))] * 100, 3)],
    "p_delta_ge_0": round(sum(1 for v in deltas if v >= 0)/len(deltas), 4),
}

json.dump(out, open(OUT + "/impulse_sensitivity.json", "w"), indent=1)
print(json.dumps(out, indent=1))
