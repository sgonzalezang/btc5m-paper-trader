"""Fold-cadence sensitivity (5d / 20d retrain vs the pre-registered 10d).
Regenerates cadence_sensitivity.json (the prior session left no script).
Model at lambda*=100 vs spec-qhat on the SAME TEST-era rows as the primary
(the 10d-fold OOS TEST set), median anchor. Sensitivity only; not the verdict.
"""
import json, math, os
import lr
from run_walkforward import (load, qhat_series, baseline_pred, featmat, brier,
                             block_boot_meandiff, FEATNAMES, T_START, T_TEST)

HERE = os.path.dirname(os.path.abspath(__file__))
DAY = 86400
LAM = 100.0

rows = load()
ex = [r for r in rows if r["_win"] is not None]
qs = qhat_series(rows)

# primary TEST-OOS row set (from the 10d run) for apples-to-apples scoring
preds10 = {int(t): v for t, v in json.load(open(os.path.join(HERE, "preds_oos.json"))).items()}
te = [r for r in ex if r["t0"] in preds10 and r["t0"] >= T_TEST]
ys = [r["_win"] for r in te]
t0s = [r["t0"] for r in te]
pspec = [baseline_pred(r, qs, 1, "spec") for r in te]
spec_b = brier(pspec, ys)

out = {}
for days in (5, 20):
    fold = days * DAY
    preds = {}
    k = 1
    while T_START + k * fold < rows[-1]["t0"] + 1:
        lo, hi = T_START + k * fold, T_START + (k + 1) * fold
        tr = [r for r in ex if r["t0"] < lo]
        sub = [r for r in ex if lo <= r["t0"] < hi]
        if sub and tr:
            X = featmat(tr, FEATNAMES); y = [r["_win"] for r in tr]
            mu, sd = lr.standardize_fit(X)
            Xs = lr.standardize_apply(X, mu, sd)
            w, b, J, it, conv = lr.fit_gd(Xs, y, LAM)
            Xt = lr.standardize_apply(featmat(sub, FEATNAMES), mu, sd)
            for r, p in zip(sub, lr.predict(Xt, w, b)):
                preds[r["t0"]] = p
        k += 1
    sub = [r for r in te if r["t0"] in preds]
    ysub = [r["_win"] for r in sub]
    pmod = [preds[r["t0"]] for r in sub]
    psp = [baseline_pred(r, qs, 1, "spec") for r in sub]
    dB = [(b1 - y) ** 2 - (m1 - y) ** 2 for b1, m1, y in zip(psp, pmod, ysub)]
    bt = block_boot_meandiff([r["t0"] for r in sub], dB, B=4000)
    out[f"fold_{days}d"] = {"n_test": len(sub), "model_brier": round(brier(pmod, ysub), 6),
                            "spec_brier": round(brier(psp, ysub), 6),
                            "improve_mean": round(bt["mean"], 6),
                            "ci95": [round(bt["ci95"][0], 6), round(bt["ci95"][1], 6)]}
    print(f"fold_{days}d:", out[f"fold_{days}d"])

with open(os.path.join(HERE, "cadence_sensitivity.json"), "w") as f:
    json.dump(out, f, indent=1)
print("wrote cadence_sensitivity.json")
