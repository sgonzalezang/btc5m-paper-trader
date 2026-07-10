#!/usr/bin/env python3
"""
ADVERSARIAL VERIFICATION of variant-impulse Flavor B (eff6>=0.10 AND cnt12<=6).
Independent reimplementation from data/cb5m.json; fee/fill/market-reality lens.

Checks:
 1. Reproduce baseline (4023/.5334; TRAIN 2649/.5228; TEST 1374/.5539).
 2. Reproduce gate B TRAIN (1733/.5418) and TEST (1009/.5669), nets at .4774/+1c/+2c.
 3. Six 10d folds; block-boot (1h) gate-effect p on TRAIN and TEST; paired-vs-flagship
    delta on TEST and 60d (variant - flagship = -complement pnl per flagship signal).
 4. FILL REALISM from pm_prices_sample.json (last ~3d): actual contrarian-side price
    at 20s/60s for gate-selected vs complement signals, by move size; availability
    under the .53 effective-cost cap; recompute selected TEST net at the observed
    pm-sample mean fill.
 5. Look-ahead audit: TRAIN-calibrated A=0.32 on TEST (params-from-TEST concern).
"""
import json, random

BASE = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-10-edge-hunt"
OUT  = "/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad/work/verify-variant-impulse"
THR = 0.0012
SLIP = 0.01
random.seed(987654321)  # different seed than the original on purpose

def fee(p): return 0.07 * p * (1 - p)
def qstar(p): return p + fee(p)
def pnl(win, p): return (1 - p - fee(p)) if win else (-p - fee(p))

d = json.load(open(BASE + "/data/cb5m.json"))
t, o, c = d["t"], d["o"], d["c"]
n = len(t)
mv = [(o[i+1] - o[i]) / o[i] for i in range(n - 1)]

sig_all, sig = [], []
for i in range(1, n):
    pmv = mv[i-1]
    if abs(pmv) < THR: continue
    up = c[i] >= o[i]                       # tie -> Up
    win = up if pmv < 0 else (not up)       # contrarian
    r = dict(i=i, t=t[i], win=int(win), pm=abs(pmv), side=("down" if pmv > 0 else "up"))
    sig_all.append(r)
    if i >= 13:
        den = sum(abs(o[j+1] - o[j]) for j in range(i-6, i))
        r["eff6"] = abs(o[i] - o[i-6]) / den if den > 0 else 0.0
        r["cnt12"] = sum(1 for j in range(i-13, i-1) if abs(mv[j]) >= THR)
        sig.append(r)

t0 = t[0]
for s in sig:
    s["seg"] = "TRAIN" if s["t"] - t0 < 40*86400 else "TEST"
    s["fold"] = min(5, int((s["t"] - t0) / (10*86400)))
    s["blk"] = int((s["t"] - t0) // 3600)

def q(sub): return sum(x["win"] for x in sub) / len(sub) if sub else None
def net(sub, p): return sum(pnl(x["win"], p) for x in sub) / len(sub) if sub else None

TRA = [x for x in sig_all if x["t"] - t0 < 40*86400]
TEA = [x for x in sig_all if x["t"] - t0 >= 40*86400]
res = {"baseline": {"full": [len(sig_all), round(q(sig_all),4)],
                    "train": [len(TRA), round(q(TRA),4)],
                    "test": [len(TEA), round(q(TEA),4)]}}

gate = lambda x: x["eff6"] >= 0.10 and x["cnt12"] <= 6
gate032 = lambda x: x["eff6"] >= 0.32 and x["cnt12"] <= 6
TR = [x for x in sig if x["seg"] == "TRAIN"]; TE = [x for x in sig if x["seg"] == "TEST"]

def seg(sub, g):
    sel = [x for x in sub if g(x)]; comp = [x for x in sub if not g(x)]
    return {"n": len(sub), "n_sel": len(sel), "q_all": round(q(sub),4),
            "q_sel": round(q(sel),4), "q_comp": round(q(comp),4) if comp else None,
            "net_sel_c": {p: round(net(sel,p)*100,2) for p in (0.4774,0.4874,0.4974)},
            "net_all_c": {p: round(net(sub,p)*100,2) for p in (0.4774,0.4874,0.4974)},
            "net_comp_c_.4774": round(net(comp,0.4774)*100,2) if comp else None}
res["B_train"] = seg(TR, gate); res["B_test"] = seg(TE, gate)
res["A032_test"] = seg(TE, gate032)
res["folds"] = []
for k in range(6):
    f = [x for x in sig if x["fold"] == k]; s = [x for x in f if gate(x)]
    res["folds"].append({"fold": k, "n_sel": len(s), "q_sel": round(q(s),4),
                         "net_sel_c": round(net(s,0.4774)*100,2),
                         "net_all_c": round(net(f,0.4774)*100,2)})

# ---- block bootstrap (1h blocks) ----
def boot(sub, fn, B=4000):
    bl = {}
    for x in sub: bl.setdefault(x["blk"], []).append(x)
    bl = list(bl.values()); nb = len(bl); out = []
    for _ in range(B):
        s = [x for _ in range(nb) for x in bl[random.randrange(nb)]]
        v = fn(s)
        if v is not None: out.append(v)
    return out

def gate_eff(s):
    a = [x for x in s if gate(x)]; b = [x for x in s if not gate(x)]
    return (q(a) - q(b)) if (a and b) else None
def comp_net(s):
    b = [x for x in s if not gate(x)]
    return net(b, 0.4774) if b else None

for lbl, sub in (("train", TR), ("test", TE)):
    bg = boot(sub, gate_eff)
    res["boot_" + lbl] = {"p_gate_le_0": round(sum(1 for v in bg if v <= 0)/len(bg),4)}
# paired delta: (variant - flagship) per flagship signal = -mean_comp_pnl * n_comp/n_all
def paired_delta(s):
    b = [x for x in s if not gate(x)]
    if not s: return None
    return -sum(pnl(x["win"],0.4774) for x in b) / len(s)
for lbl, sub in (("test", TE), ("full60", sig)):
    bd = boot(sub, paired_delta)
    bd.sort()
    res["paired_" + lbl] = {"mean_c": round(paired_delta(sub)*100,3),
        "ci90_c": [round(bd[int(0.05*len(bd))]*100,2), round(bd[int(0.95*len(bd))]*100,2)],
        "p_ge_0": round(sum(1 for v in bd if v >= 0)/len(bd),4)}

# ---- FILL REALISM: pm_prices_sample vs gate subsets ----
pm = json.load(open(BASE + "/data/pm_prices_sample.json"))
pm_by_t0 = {m["t0"]: m for m in pm}
tidx = {tt: k for k, tt in enumerate(t)}
rows = []
for s in sig:
    m = pm_by_t0.get(s["t"])
    if not m: continue
    up_p20, up_p60 = m["p20"], m["p60"]
    if up_p20 is None: continue
    side_p20 = up_p20 if s["side"] == "up" else 1 - up_p20
    side_p60 = (up_p60 if s["side"] == "up" else 1 - up_p60) if up_p60 is not None else None
    # resolution check vs proxy
    pm_win = m["up_won"] if s["side"] == "up" else 1 - m["up_won"]
    rows.append(dict(t=s["t"], sel=gate(s), pm_bps=s["pm"]*1e4, side=s["side"],
                     cost20=side_p20 + SLIP, cost60=(side_p60 + SLIP) if side_p60 is not None else None,
                     win_cb=s["win"], win_pm=pm_win))
def stats(rs, key="cost20"):
    v = sorted(r[key] for r in rs if r[key] is not None)
    if not v: return None
    mean = sum(v)/len(v)
    avail = sum(1 for x in v if x <= 0.53 + 1e-9)/len(v)
    return {"n": len(v), "mean": round(mean,4), "p25": round(v[len(v)//4],3),
            "p50": round(v[len(v)//2],3), "p75": round(v[3*len(v)//4],3),
            "avail_le_.53": round(avail,3)}
selr = [r for r in rows if r["sel"]]; comr = [r for r in rows if not r["sel"]]
res["pm_fill"] = {
    "n_matched": len(rows),
    "sel_cost20": stats(selr), "comp_cost20": stats(comr),
    "sel_cost60": stats(selr, "cost60"), "comp_cost60": stats(comr, "cost60"),
    "resolution_agreement": round(sum(1 for r in rows if r["win_cb"] == r["win_pm"])/len(rows),4),
}
# by move size
for lo, hi, lbl in ((12,16,"12-16"),(16,24,"16-24"),(24,999,"24+")):
    z = [r for r in selr if lo <= r["pm_bps"] < hi]
    res["pm_fill"]["sel_cost20_%sbps" % lbl] = stats(z)
# selected-subset net using pm-observed fills: censored (<=.53) mean cost -> as fill p
cens = [r["cost20"] for r in selr if r["cost20"] is not None and r["cost20"] <= 0.53+1e-9]
if cens:
    pfill = sum(cens)/len(cens)
    res["pm_fill"]["sel_censored_mean_cost20"] = round(pfill,4)
    res["pm_fill"]["qstar_at_that_fill"] = round(qstar(pfill),4)
    selTE = [x for x in TE if gate(x)]
    res["pm_fill"]["TEST_net_sel_at_pm_fill_c"] = round(net(selTE, pfill)*100,2)
    # win-rate of PM-available selected signals only (availability correlated with outcome?)
    availsel = [r for r in selr if r["cost20"] <= 0.53+1e-9]
    res["pm_fill"]["n_sel_pm_avail"] = len(availsel)
    res["pm_fill"]["q_sel_pm_avail_cbproxy"] = round(sum(r["win_cb"] for r in availsel)/len(availsel),4)
    res["pm_fill"]["q_sel_pm_avail_pmres"] = round(sum(r["win_pm"] for r in availsel)/len(availsel),4)
    res["pm_fill"]["net_sel_pm_avail_actualfills_c"] = round(
        sum(pnl(r["win_pm"], r["cost20"]) for r in availsel)/len(availsel)*100, 2)
    # win rate of ALL matched selected signals (no availability censor) on both resolutions
    res["pm_fill"]["q_sel_pm_all_cbproxy"] = round(sum(r["win_cb"] for r in selr)/len(selr),4)
    res["pm_fill"]["q_sel_pm_all_pmres"]  = round(sum(r["win_pm"] for r in selr)/len(selr),4)
    ccens = [r for r in comr if r["cost20"] is not None and r["cost20"] <= 0.53+1e-9]
    res["pm_fill"]["n_comp_pm_avail"] = len(ccens)
    if ccens:
        res["pm_fill"]["comp_censored_mean_cost20"] = round(sum(r["cost20"] for r in ccens)/len(ccens),4)
        res["pm_fill"]["net_comp_pm_avail_actualfills_c"] = round(
            sum(pnl(r["win_pm"], r["cost20"]) for r in ccens)/len(ccens)*100, 2)
    # same-window sanity: what does the CB-proxy q say for the pm 3d window overall
    lo, hi = pm[0]["t0"], pm[-1]["t0"]
    win3d = [x for x in sig if lo <= x["t"] <= hi]
    sel3d = [x for x in win3d if gate(x)]
    res["pm_fill"]["window3d_all_signals"] = {"n": len(win3d), "q_cb": round(q(win3d),4)}
    res["pm_fill"]["window3d_sel_signals"] = {"n": len(sel3d), "q_cb": round(q(sel3d),4)}

json.dump(res, open(OUT + "/verify_results.json", "w"), indent=1)
print(json.dumps(res, indent=1))
