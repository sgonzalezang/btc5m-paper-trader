#!/usr/bin/env python3
"""
Regime-gate tournament for the buffered reversal strategy.

Strategy under test (fixed): prior |open-to-open move| >= 12bps -> buy the OTHER side
at p=0.51, exact fee 0.07*p*(1-p) per share, hold to resolution. Tie -> Up.
Data: cb5m.json (Coinbase BTC-USD 5m, 60d, gapless).

Protocol: six 10-day folds. For each gate candidate, calibrate the threshold on fold k
(objective: total net pnl of gated trades, constraint n_gated >= max(20, 25% of fold trades)),
evaluate on fold k+1. Report pooled OOS net pnl/trade, worst fold, retention.
Baselines: ungated; latentfire fixed gate eff12 <= 0.48.

All features are strictly trailing: computed from candles with index < i plus o[i]
(o[i] is known at decision time; the trigger move itself is (o[i]-o[i-1])/o[i-1]).
"""
import json, math, sys

SCRATCH = "/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad"
DATA = SCRATCH + "/data/cb5m.json"
OUT  = SCRATCH + "/work/regime"

P_ENTRY = 0.51
FEE = 0.07 * P_ENTRY * (1 - P_ENTRY)          # 0.0174930 per share
WIN_PNL  = (1 - P_ENTRY) - FEE                # +0.4725070
LOSE_PNL = -P_ENTRY - FEE                     # -0.5274930
BREAKEVEN = P_ENTRY + FEE                     # 0.5274930 win rate
MOVE_THR = 0.0012                             # 12 bps trigger
SHARES_50 = 50.0 / P_ENTRY                    # $50 stake -> 98.04 shares

d = json.load(open(DATA))
t, o, h, l, c = d["t"], d["o"], d["h"], d["l"], d["c"]
n = len(t)

# open-to-open moves: moves[i] = (o[i+1]-o[i])/o[i], i in 0..n-2
moves = [(o[i+1] - o[i]) / o[i] for i in range(n - 1)]
absm = [abs(m) for m in moves]

# true range (vs prev close), atr12
tr = [0.0] * n
for i in range(1, n):
    tr[i] = max(h[i] - l[i], abs(h[i] - c[i-1]), abs(l[i] - c[i-1])) / c[i-1]
atr12 = [0.0] * n
s = 0.0
for i in range(1, n):
    s += tr[i]
    if i >= 13:
        s -= tr[i-12]
    if i >= 13:
        atr12[i] = s / 12.0   # mean of tr[i-11..i]  (trailing incl. i)

def eff(i, W):
    """Kaufman efficiency of the last W open-to-open moves ending at o[i]."""
    num = abs(o[i] - o[i-W])
    den = sum(abs(o[j+1] - o[j]) for j in range(i-W, i))
    return num / den if den > 0 else 0.0

def meanabs(lo, hi):  # mean of absm[lo..hi-1]
    return sum(absm[j] for j in range(lo, hi)) / (hi - lo)

# ---- build trade list with features ----
WARM = 312   # max lookback: atrpct needs 288 trailing atr12 values (each needs 12 TRs)
trades = []  # dict per trade
for i in range(WARM, n):
    pm = moves[i-1]                      # trigger: prior completed move
    if abs(pm) < MOVE_THR:
        continue
    up = c[i] >= o[i]                    # tie -> Up
    win = (not up) if pm > 0 else up     # we buy the opposite side
    f = {}
    f["eff6"]  = eff(i, 6)
    f["eff12"] = eff(i, 12)
    f["eff24"] = eff(i, 24)
    va = meanabs(i-12, i); vb = meanabs(i-72, i)
    f["vr"] = va / vb if vb > 0 else 1.0
    cur = atr12[i-1]                     # atr of last 12 completed candles
    cnt_le = sum(1 for j in range(i-289, i-1) if atr12[j] <= cur)
    f["atrpct"] = cnt_le / 288.0
    r6  = max(h[i-6:i])  - min(l[i-6:i])
    r24 = max(h[i-24:i]) - min(l[i-24:i])
    f["rc"] = r6 / r24 if r24 > 0 else 1.0
    f["cnt"] = sum(1 for j in range(i-13, i-1) if absm[j] >= MOVE_THR)  # hour BEFORE trigger
    gap = 9999
    for j in range(i-2, max(i-290, -1), -1):
        if absm[j] >= MOVE_THR:
            gap = (i-1-j) * 5
            break
    f["gap"] = gap
    trades.append({"i": i, "t": t[i], "win": 1 if win else 0,
                   "pnl": WIN_PNL if win else LOSE_PNL, **f})

print("total trades:", len(trades), " win rate:",
      round(sum(tr_["win"] for tr_ in trades)/len(trades), 4),
      " breakeven:", round(BREAKEVEN, 4))

# ---- folds: six 10-day bins by time ----
t0 = t[0]
for tr_ in trades:
    tr_["fold"] = min(5, int((tr_["t"] - t0) / (10*86400)))
folds = [[tr_ for tr_ in trades if tr_["fold"] == k] for k in range(6)]
print("fold sizes:", [len(f) for f in folds])

def stats(sub):
    if not sub:
        return {"n": 0, "wr": None, "pps": None, "usd": None}
    nn = len(sub); w = sum(x["win"] for x in sub)
    pps = sum(x["pnl"] for x in sub) / nn
    return {"n": nn, "wr": w/nn, "pps": pps, "usd": pps * SHARES_50}

# ---- gate candidates ----
def frange(a, b, s):
    out = []; x = a
    while x <= b + 1e-9:
        out.append(round(x, 4)); x += s
    return out

CANDS = {
    "eff6":   {"feat": "eff6",  "grid": frange(0.10, 0.90, 0.02), "dirs": ["le", "ge"]},
    "eff12":  {"feat": "eff12", "grid": frange(0.10, 0.90, 0.02), "dirs": ["le", "ge"]},
    "eff24":  {"feat": "eff24", "grid": frange(0.10, 0.90, 0.02), "dirs": ["le", "ge"]},
    "volratio":{"feat": "vr",   "grid": frange(0.40, 2.00, 0.05), "dirs": ["le", "ge"]},
    "atrpct": {"feat": "atrpct","grid": frange(0.05, 0.95, 0.05), "dirs": ["le", "ge"]},
    "rangecomp":{"feat": "rc",  "grid": frange(0.10, 0.95, 0.05), "dirs": ["le", "ge"]},
    "evcount":{"feat": "cnt",   "grid": list(range(0, 9)),        "dirs": ["le", "ge"]},
    "minsince":{"feat": "gap",  "grid": [5,10,15,20,25,30,40,50,60,90,120,180,240], "dirs": ["le", "ge"]},
}

def passes(x, feat, dr, thr):
    v = x[feat]
    return v <= thr if dr == "le" else v >= thr

def calibrate(cand, sub):
    """Pick (dir, thr) maximizing total net pnl with retention constraint."""
    best = None
    min_n = max(20, int(0.25 * len(sub)))
    for dr in cand["dirs"]:
        for thr in cand["grid"]:
            g = [x for x in sub if passes(x, cand["feat"], dr, thr)]
            if len(g) < min_n:
                continue
            tot = sum(x["pnl"] for x in g)
            if best is None or tot > best[0]:
                best = (tot, dr, thr, len(g))
    return best  # may be None

# combo: eff12 <= a AND vr (dir) b
COMBO_EFF = frange(0.30, 0.70, 0.04)
COMBO_VR  = frange(0.60, 1.60, 0.10)
def calibrate_combo(sub, efffeat):
    best = None
    min_n = max(20, int(0.25 * len(sub)))
    for a in COMBO_EFF:
        for dr in ["le", "ge"]:
            for b in COMBO_VR:
                g = [x for x in sub if x[efffeat] <= a and passes(x, "vr", dr, b)]
                if len(g) < min_n:
                    continue
                tot = sum(x["pnl"] for x in g)
                if best is None or tot > best[0]:
                    best = (tot, (a, dr, b), len(g))
    return best

# ---- run tournament ----
results = {}
cal_paths = {}
for name, cand in CANDS.items():
    oos = []; perfold = []; path = []
    for k in range(5):                       # calibrate fold k -> eval fold k+1
        cal = calibrate(cand, folds[k])
        if cal is None:
            perfold.append(None); path.append(None); continue
        _, dr, thr, _ = cal
        path.append((dr, thr))
        g = [x for x in folds[k+1] if passes(x, cand["feat"], dr, thr)]
        oos.extend(g)
        st = stats(g)
        st["base_n"] = len(folds[k+1]); st["cal"] = f"{dr} {thr}"
        perfold.append(st)
    pooled = stats(oos)
    base_n = sum(len(folds[k+1]) for k in range(5))
    worst = min((pf["pps"] for pf in perfold if pf and pf["n"] > 0), default=None)
    results[name] = {"pooled": pooled, "retention": pooled["n"]/base_n,
                     "worst_fold_pps": worst, "perfold": perfold}
    cal_paths[name] = path

for efffeat in ["eff12", "eff24"]:
    name = f"combo_{efffeat}_x_vr"
    oos = []; perfold = []; path = []
    for k in range(5):
        cal = calibrate_combo(folds[k], efffeat)
        if cal is None:
            perfold.append(None); path.append(None); continue
        _, (a, dr, b), _ = cal
        path.append((a, dr, b))
        g = [x for x in folds[k+1] if x[efffeat] <= a and passes(x, "vr", dr, b)]
        oos.extend(g)
        st = stats(g); st["base_n"] = len(folds[k+1]); st["cal"] = f"eff<={a} & vr {dr} {b}"
        perfold.append(st)
    pooled = stats(oos)
    base_n = sum(len(folds[k+1]) for k in range(5))
    worst = min((pf["pps"] for pf in perfold if pf and pf["n"] > 0), default=None)
    results[name] = {"pooled": pooled, "retention": pooled["n"]/base_n,
                     "worst_fold_pps": worst, "perfold": perfold}
    cal_paths[name] = path

# exploratory: isolated-impulse combo, eff6 >= a AND cnt <= b
EFF6_GRID = frange(0.06, 0.40, 0.02)
CNT_GRID = list(range(0, 9))
name = "combo_eff6ge_x_cntle"
oos = []; perfold = []; path = []
for k in range(5):
    best = None
    min_n = max(20, int(0.25 * len(folds[k])))
    for a in EFF6_GRID:
        for b in CNT_GRID:
            g = [x for x in folds[k] if x["eff6"] >= a and x["cnt"] <= b]
            if len(g) < min_n:
                continue
            tot = sum(x["pnl"] for x in g)
            if best is None or tot > best[0]:
                best = (tot, a, b)
    if best is None:
        perfold.append(None); path.append(None); continue
    _, a, b = best
    path.append((a, b))
    g = [x for x in folds[k+1] if x["eff6"] >= a and x["cnt"] <= b]
    oos.extend(g)
    st = stats(g); st["base_n"] = len(folds[k+1]); st["cal"] = f"eff6>={a} & cnt<={b}"
    perfold.append(st)
pooled = stats(oos)
base_n = sum(len(folds[k+1]) for k in range(5))
worst = min((pf["pps"] for pf in perfold if pf and pf["n"] > 0), default=None)
results[name] = {"pooled": pooled, "retention": pooled["n"]/base_n,
                 "worst_fold_pps": worst, "perfold": perfold}
cal_paths[name] = path

# baselines on the same OOS span (folds 1..5)
oos_all = [x for k in range(1, 6) for x in folds[k]]
results["_ungated"] = {"pooled": stats(oos_all), "retention": 1.0,
                       "worst_fold_pps": min(stats(folds[k])["pps"] for k in range(1, 6)),
                       "perfold": [stats(folds[k]) for k in range(1, 6)]}
lf = [x for x in oos_all if x["eff12"] <= 0.48]
lf_pf = [stats([x for x in folds[k] if x["eff12"] <= 0.48]) for k in range(1, 6)]
results["_latentfire_eff12le048"] = {"pooled": stats(lf), "retention": len(lf)/len(oos_all),
                                     "worst_fold_pps": min((pf["pps"] for pf in lf_pf if pf["n"] > 0), default=None),
                                     "perfold": lf_pf}

json.dump({"results": results, "cal_paths": cal_paths,
           "fold_sizes": [len(f) for f in folds],
           "config": {"p_entry": P_ENTRY, "fee": FEE, "breakeven_wr": BREAKEVEN,
                      "move_thr": MOVE_THR, "warmup_idx": WARM}},
          open(OUT + "/tournament_results.json", "w"), indent=1)

# summary table
rows = []
for name, r in sorted(results.items(), key=lambda kv: -(kv[1]["pooled"]["pps"] or -9)):
    p = r["pooled"]
    rows.append((name, p["n"], round(r["retention"], 3),
                 round(p["wr"], 4) if p["wr"] is not None else None,
                 round(p["pps"]*100, 3) if p["pps"] is not None else None,
                 round(p["usd"], 3) if p["usd"] is not None else None,
                 round(r["worst_fold_pps"]*100, 3) if r["worst_fold_pps"] is not None else None))
hdr = ("candidate", "oos_n", "retention", "oos_wr", "pps_cents", "usd_per_trade50", "worst_fold_cents")
with open(OUT + "/tournament_summary.tsv", "w") as fh:
    fh.write("\t".join(hdr) + "\n")
    for r in rows:
        fh.write("\t".join(str(x) for x in r) + "\n")
print("\n" + "\t".join(hdr))
for r in rows:
    print("\t".join(str(x) for x in r))
print("\ncal paths:")
for k, v in cal_paths.items():
    print(" ", k, v)
