#!/usr/bin/env python3
"""
Isolated-impulse (calm-before-the-spike) variant family vs flagship reversal_v2.

Flagship baseline (reversal_v2): buffered open-to-open prior |move| >= 12bps on
Coinbase 5m (contiguous candles, data verified gapless), contrarian, ties -> Up,
hold to resolution. Fills: <=53c censored ledger, unweighted mean .4774
(q* = .4949); sensitivity +1c/+2c. Fee exact: 0.07*p*(1-p) per share.

Flavors:
 (A) price-only calm gate: |pre-prior move| < calm_thr, calm_thr swept {4,6,8}bps
     on TRAIN ONLY (first 40d); single pre-selected evaluation on TEST (last 20d).
 (B) deploy-spec gate at FIXED params (no refit): eff6 >= 0.10 AND cnt12 <= 6
     (work/regime/deploy_spec.json, deploy_calibrated_trailing20d_asof_2026-07-10).

Conventions match work/regime/regime_tournament.py exactly:
  moves[i] = (o[i+1]-o[i])/o[i];  trigger at candle i is pm = moves[i-1]
  eff6  = |o[i]-o[i-6]| / sum_{j=i-6}^{i-1} |o[j+1]-o[j]|   (includes trigger move)
  cnt12 = #{ j in [i-13, i-2] : |moves[j]| >= 12bps }        (trigger excluded)
  calm  = |moves[i-2]|                                        (pre-prior interval)
  outcome: up = c[i] >= o[i] (tie -> Up); win = contrarian side wins

Stats: chronological TRAIN (first 40d) / TEST (last 20d); six 10d folds;
block bootstrap with 1h blocks (12 intervals) for all headline p-values;
paired-vs-flagship = complement book (variant - flagship = -complement).
"""
import json, math, random

BASE = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-10-edge-hunt"
OUT  = BASE + "/work/variant-impulse"

MOVE_THR = 0.0012
FILLS = {"mean_.4774": 0.4774, "plus1c_.4874": 0.4874, "plus2c_.4974": 0.4974}
BOOT_B = 4000
random.seed(20260710)

def cost(p):   # total cost per share incl. exact fee
    return p + 0.07 * p * (1 - p)

def ev_share(q, p):
    return q - cost(p)

d = json.load(open(BASE + "/data/cb5m.json"))
t, o, c = d["t"], d["o"], d["c"]
n = len(t)
moves = [(o[i+1] - o[i]) / o[i] for i in range(n - 1)]
absm = [abs(m) for m in moves]

def eff(i, W):
    num = abs(o[i] - o[i-W])
    den = sum(abs(o[j+1] - o[j]) for j in range(i-W, i))
    return num / den if den > 0 else 0.0

# ---- signals ----
WARM = 13   # cnt12 needs j >= i-13 >= 0
sig_all = []      # warmup=1 for baseline reproduction only
sig = []          # warmup=13: common signal set for all comparisons
for i in range(1, n):
    pm = moves[i-1]
    if abs(pm) < MOVE_THR:
        continue
    up = c[i] >= o[i]
    win = (not up) if pm > 0 else up
    rec = {"i": i, "t": t[i], "win": 1 if win else 0, "pm": abs(pm)}
    sig_all.append(rec)
    if i >= WARM:
        rec = dict(rec)
        rec["calm"]  = absm[i-2]
        rec["eff6"]  = eff(i, 6)
        rec["eff12"] = eff(i, 12)
        rec["cnt12"] = sum(1 for j in range(i-13, i-1) if absm[j] >= MOVE_THR)
        sig.append(rec)

t0 = t[0]
for s in sig:
    s["fold"] = min(5, int((s["t"] - t0) / (10 * 86400)))
    s["seg"] = "TRAIN" if (s["t"] - t0) < 40 * 86400 else "TEST"
    s["blk"] = int((s["t"] - t0) // 3600)          # 1h block id

# baseline reproduction (warmup=1, to match best_spec.json)
def q_of(sub):
    return sum(x["win"] for x in sub) / len(sub) if sub else None
tr_all = [x for x in sig_all if (x["t"] - t0) < 40 * 86400]
te_all = [x for x in sig_all if (x["t"] - t0) >= 40 * 86400]
baseline_repro = {
    "full": {"n": len(sig_all), "q": round(q_of(sig_all), 4)},
    "train_first40d": {"n": len(tr_all), "q": round(q_of(tr_all), 4)},
    "test_last20d": {"n": len(te_all), "q": round(q_of(te_all), 4)},
    "expected": {"full": [4023, 0.5334], "train": [2649, 0.5228], "test": [1374, 0.5539]},
}
print("baseline repro:", baseline_repro)

TRAIN = [x for x in sig if x["seg"] == "TRAIN"]
TEST  = [x for x in sig if x["seg"] == "TEST"]
FOLDS = [[x for x in sig if x["fold"] == k] for k in range(6)]

# ---- block bootstrap helpers ----
def blocks_of(sub):
    bl = {}
    for x in sub:
        bl.setdefault(x["blk"], []).append(x)
    return list(bl.values())

def boot_stat(sub, fn, B=BOOT_B):
    """fn(list_of_trades) -> float or None. Returns list of bootstrap stats."""
    bl = blocks_of(sub)
    nb = len(bl)
    out = []
    for _ in range(B):
        samp = [x for _ in range(nb) for x in bl[random.randrange(nb)]]
        v = fn(samp)
        if v is not None:
            out.append(v)
    return out

def pnl_share(x, p):
    fee = 0.07 * p * (1 - p)
    return (1 - p - fee) if x["win"] else (-p - fee)

def net_share(sub, p):
    return sum(pnl_share(x, p) for x in sub) / len(sub) if sub else None

def pctile(v, q):
    if not v: return None
    s = sorted(v); k = (len(s) - 1) * q
    f = int(k); return s[f] + (s[f+1] - s[f]) * (k - f) if f + 1 < len(s) else s[f]

def seg_report(sub, sel_fn, p_fill):
    sel = [x for x in sub if sel_fn(x)]
    comp = [x for x in sub if not sel_fn(x)]
    r = {
        "n_all": len(sub), "n_sel": len(sel), "n_comp": len(comp),
        "retention": round(len(sel) / len(sub), 4) if sub else None,
        "q_all": round(q_of(sub), 4) if sub else None,
        "q_sel": round(q_of(sel), 4) if sel else None,
        "q_comp": round(q_of(comp), 4) if comp else None,
    }
    for lbl, p in FILLS.items():
        r["net_sel_" + lbl] = round(net_share(sel, p), 5) if sel else None
        r["net_comp_" + lbl] = round(net_share(comp, p), 5) if comp else None
        r["net_all_" + lbl] = round(net_share(sub, p), 5) if sub else None
    # complement at trending-adjusted fills (+1c, +2c richer) -- the complement is
    # cascade/trend-heavy, where confirmed fills run 1-2c richer
    r["net_comp_trendadj_+1c"] = round(net_share(comp, 0.4874), 5) if comp else None
    r["net_comp_trendadj_+2c"] = round(net_share(comp, 0.4974), 5) if comp else None
    return r, sel, comp

def boot_pvals(sub, sel_fn, p_fill):
    """block-bootstrap p-values on segment sub."""
    def stat_qsel(s):
        z = [x for x in s if sel_fn(x)]
        return q_of(z)
    def stat_net_sel(s):
        z = [x for x in s if sel_fn(x)]
        return net_share(z, p_fill)
    def stat_gate(s):
        a = [x for x in s if sel_fn(x)]; b = [x for x in s if not sel_fn(x)]
        if not a or not b: return None
        return q_of(a) - q_of(b)
    def stat_comp_net(s):
        z = [x for x in s if not sel_fn(x)]
        return net_share(z, p_fill)
    bs_net  = boot_stat(sub, stat_net_sel)
    bs_gate = boot_stat(sub, stat_gate)
    bs_comp = boot_stat(sub, stat_comp_net)
    return {
        "p_net_sel_le_0": round(sum(1 for v in bs_net if v <= 0) / len(bs_net), 4),
        "p_gate_effect_le_0": round(sum(1 for v in bs_gate if v <= 0) / len(bs_gate), 4),
        "comp_net_ci90": [round(pctile(bs_comp, 0.05), 5), round(pctile(bs_comp, 0.95), 5)],
        "p_comp_net_ge_0": round(sum(1 for v in bs_comp if v >= 0) / len(bs_comp), 4),
    }

def fold_table(sel_fn, p_fill):
    rows = []
    for k in range(6):
        f = FOLDS[k]
        sel = [x for x in f if sel_fn(x)]
        rows.append({
            "fold": k, "n_all": len(f), "n_sel": len(sel),
            "q_all": round(q_of(f), 4) if f else None,
            "q_sel": round(q_of(sel), 4) if sel else None,
            "net_sel_c": round(net_share(sel, p_fill) * 100, 3) if sel else None,
        })
    return rows

P0 = FILLS["mean_.4774"]
results = {"baseline_repro": baseline_repro,
           "common_signal_set": {"n": len(sig), "n_train": len(TRAIN), "n_test": len(TEST),
                                 "q_train": round(q_of(TRAIN), 4), "q_test": round(q_of(TEST), 4)}}

# =========== FLAVOR A: calm-before-spike, sweep on TRAIN only ===========
sweepA = {}
for thr_bps in (4, 6, 8):
    thr = thr_bps / 1e4
    fn = (lambda th: (lambda x: x["calm"] < th))(thr)
    rep, sel, comp = seg_report(TRAIN, fn, P0)
    tot_net = sum(pnl_share(x, P0) for x in sel)
    rep["train_total_net_usd_per_share_x1"] = round(tot_net, 3)
    sweepA["calm<%dbps" % thr_bps] = rep
results["A_train_sweep"] = sweepA

# selection rule (TRAIN only): highest TRAIN net/share among thresholds with
# retention >= 20%; report total too.
bestA = max((k for k in sweepA if sweepA[k]["retention"] >= 0.20),
            key=lambda k: sweepA[k]["net_sel_mean_.4774"])
results["A_selected_on_train"] = bestA
thrA = int(bestA.split("<")[1].replace("bps", "")) / 1e4
fnA = lambda x: x["calm"] < thrA

repA_test, selA_te, compA_te = seg_report(TEST, fnA, P0)
results["A_test"] = repA_test
results["A_test_boot"] = boot_pvals(TEST, fnA, P0)
results["A_train_boot"] = boot_pvals(TRAIN, fnA, P0)
results["A_folds"] = fold_table(fnA, P0)
# diagnostics: does A-selected correlate with trend/big moves? (fill-adjustment call)
selA_all = [x for x in sig if fnA(x)]
compA_all = [x for x in sig if not fnA(x)]
results["A_diag"] = {
    "sel_mean_eff12": round(sum(x["eff12"] for x in selA_all)/len(selA_all), 4),
    "comp_mean_eff12": round(sum(x["eff12"] for x in compA_all)/len(compA_all), 4),
    "sel_mean_priormove_bps": round(sum(x["pm"] for x in selA_all)/len(selA_all)*1e4, 2),
    "comp_mean_priormove_bps": round(sum(x["pm"] for x in compA_all)/len(compA_all)*1e4, 2),
    "sel_mean_cnt12": round(sum(x["cnt12"] for x in selA_all)/len(selA_all), 2),
    "comp_mean_cnt12": round(sum(x["cnt12"] for x in compA_all)/len(compA_all), 2),
}

# =========== FLAVOR B: deploy-spec gate, FIXED eff6>=0.10 & cnt12<=6 ===========
fnB = lambda x: x["eff6"] >= 0.10 and x["cnt12"] <= 6
repB_tr, selB_tr, compB_tr = seg_report(TRAIN, fnB, P0)
repB_te, selB_te, compB_te = seg_report(TEST, fnB, P0)
results["B_train"] = repB_tr
results["B_test"] = repB_te
results["B_train_boot"] = boot_pvals(TRAIN, fnB, P0)
results["B_test_boot"] = boot_pvals(TEST, fnB, P0)
results["B_folds"] = fold_table(fnB, P0)
selB_all = [x for x in sig if fnB(x)]
compB_all = [x for x in sig if not fnB(x)]
results["B_diag"] = {
    "sel_mean_eff12": round(sum(x["eff12"] for x in selB_all)/len(selB_all), 4),
    "comp_mean_eff12": round(sum(x["eff12"] for x in compB_all)/len(compB_all), 4),
    "sel_mean_priormove_bps": round(sum(x["pm"] for x in selB_all)/len(selB_all)*1e4, 2),
    "comp_mean_priormove_bps": round(sum(x["pm"] for x in compB_all)/len(compB_all)*1e4, 2),
    "gate_fail_split": {
        "eff6_only_fail": sum(1 for x in sig if not (x["eff6"] >= 0.10) and x["cnt12"] <= 6),
        "cnt12_only_fail": sum(1 for x in sig if (x["eff6"] >= 0.10) and x["cnt12"] > 6),
        "both_fail": sum(1 for x in sig if not (x["eff6"] >= 0.10) and x["cnt12"] > 6),
    },
}

# =========== overlap of A and B ===========
inA = set(x["i"] for x in sig if fnA(x)); inB = set(x["i"] for x in sig if fnB(x))
results["AB_overlap"] = {"nA": len(inA), "nB": len(inB),
                         "n_both": len(inA & inB),
                         "jaccard": round(len(inA & inB) / len(inA | inB), 3)}

# =========== calm gradient diagnostic (TRAIN only, no selection) ===========
grad = []
for lo, hi, lbl in [(0, 2, "0-2"), (2, 4, "2-4"), (4, 6, "4-6"), (6, 8, "6-8"),
                    (8, 12, "8-12"), (12, 999, "12+")]:
    z = [x for x in TRAIN if lo/1e4 <= x["calm"] < hi/1e4]
    grad.append({"calm_bps": lbl, "n": len(z), "q": round(q_of(z), 4) if z else None})
results["calm_gradient_train"] = grad
gradT = []
for lo, hi, lbl in [(0, 2, "0-2"), (2, 4, "2-4"), (4, 6, "4-6"), (6, 8, "6-8"),
                    (8, 12, "8-12"), (12, 999, "12+")]:
    z = [x for x in TEST if lo/1e4 <= x["calm"] < hi/1e4]
    gradT.append({"calm_bps": lbl, "n": len(z), "q": round(q_of(z), 4) if z else None})
results["calm_gradient_test"] = gradT

json.dump(results, open(OUT + "/impulse_results.json", "w"), indent=1)
print(json.dumps(results, indent=1))
