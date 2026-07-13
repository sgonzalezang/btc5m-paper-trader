"""PREREG-promised optimizer cross-check, executed (was missing an artifact).

For every walk-forward fold training set at lambda* (and the grid extremes),
fit BB-GD (the production optimizer) and IRLS/Newton independently; record
max |coef difference| including intercept. PREREG bar: agree to <= 1e-5.
Also an independent-spot-check section: recompute TEST-OOS headline metrics
from preds_oos.json + the dataset with fresh code (no run_walkforward imports
for the metric math), and recompute the nightly spec/impl qhat series with an
independently-written loop.
"""
import json, math, os
import lr
from run_walkforward import load, featmat, FEATNAMES, T_START, T_TEST, FOLD

HERE = os.path.dirname(os.path.abspath(__file__))
DAY = 86400
IVL = 300
out = {}

rows = load()
ex = [r for r in rows if r["_win"] is not None]

# ---------- 1. optimizer cross-check ----------
checks = []
for lam in (0.03, 100.0):
    k = 1
    while T_START + k * FOLD < rows[-1]["t0"] + 1:
        lo = T_START + k * FOLD
        tr = [r for r in ex if r["t0"] < lo]
        te_exists = any(lo <= r["t0"] < lo + FOLD for r in rows)
        k += 1
        if not te_exists or not tr:
            continue
        X = featmat(tr, FEATNAMES)
        y = [r["_win"] for r in tr]
        mu, sd = lr.standardize_fit(X)
        Xs = lr.standardize_apply(X, mu, sd)
        w1, b1, J1, i1, c1 = lr.fit_gd(Xs, y, lam)
        w2, b2, J2, i2, c2 = lr.fit_irls(Xs, y, lam)
        dmax = max(max(abs(a - b) for a, b in zip(w1, w2)), abs(b1 - b2))
        checks.append({"lambda": lam, "fold_lo": lo, "n_train": len(tr),
                       "max_coef_diff": dmax, "J_gd": J1, "J_irls": J2,
                       "gd_conv": c1, "irls_conv": c2})
worst = max(c["max_coef_diff"] for c in checks)
out["optimizer_crosscheck"] = {"folds_by_lambda": checks, "worst_max_coef_diff": worst,
                               "prereg_bar_1e-5_met": worst <= 1e-5}
print(f"IRLS cross-check: {len(checks)} fits, worst max|dcoef| = {worst:.3e}, bar met: {worst <= 1e-5}")

# ---------- 2. independent recompute of TEST-OOS headline ----------
preds = {int(t): v for t, v in json.load(open(os.path.join(HERE, "preds_oos.json"))).items()}
te = [r for r in ex if r["t0"] in preds and r["t0"] >= T_TEST]
ys = [r["_win"] for r in te]
pm = [preds[r["t0"]]["phat"] for r in te]
n = len(te)
brier_m = sum((p - y) ** 2 for p, y in zip(pm, ys)) / n
base = sum(ys) / n

# independent nightly qhat recompute (fresh loop, no qhat_series reuse)
def qhat_at(t0, variant, anchor_cost, anchor_fill):
    # latest nightly (00:10 UTC) at or before t0
    ns = ((t0 - 600) // DAY) * DAY + 600
    book = [r for r in ex if r["t0"] + IVL <= ns and r["t0"] >= ns - 31 * DAY]
    w = sum(r["_win"] for r in book); m = len(book)
    if variant == "impl":
        seed = 0.5057 if anchor_cost < 0.50 else 0.5068
        return min(0.56, (w + 400 * seed) / (m + 400))
    return min(0.56, (w + 100) / (m + 200))

qc = {}
for var in ("impl", "spec"):
    pb = [qhat_at(r["t0"], var, 0.507493, 0.49) for r in te]
    qc[var] = {"brier": sum((p - y) ** 2 for p, y in zip(pb, ys)) / n,
               "mean_improve_over_model": sum((b - y) ** 2 - (p - y) ** 2
                                              for b, p, y in zip(pb, pm, ys)) / n}
out["independent_recompute_TEST"] = {
    "n": n, "base_rate": base, "model_brier": brier_m,
    "qhat_median_anchor": qc,
    "matches_results_json": {
        "n": n == 721, "base_rate": abs(base - 0.57) < 5e-4,
        "model_brier": abs(brier_m - 0.247069) < 1e-6,
        "impl_brier": abs(qc["impl"]["brier"] - 0.246341) < 1e-6,
        "spec_brier": abs(qc["spec"]["brier"] - 0.246209) < 1e-6,
        # 1e-7 tolerance: preds_oos.json phat and qhat_series q are 6dp-rounded,
        # results.json means were computed on unrounded values (deltas ~1-2e-8)
        "impl_improve_mean_tol1e-7": abs(qc["impl"]["mean_improve_over_model"] - (-0.0007272547054037069)) < 1e-7,
        "spec_improve_mean_tol1e-7": abs(qc["spec"]["mean_improve_over_model"] - (-0.0008591163687892798)) < 1e-7}}
print("independent TEST recompute:", json.dumps(out["independent_recompute_TEST"]["matches_results_json"]))

# ---------- 3. money metric independent spot-check (median anchor, ex-tie, impl) ----------
c = 0.507493
tot_m = tot_q = 0.0
for r in te:
    for tag, q in (("m", preds[r["t0"]]["phat"]), ("q", qhat_at(r["t0"], "impl", c, 0.49))):
        f = (q - c) / (1 - c)
        if f <= 0:
            continue
        stake = min(0.25 * f * 1000.0, 50.0)
        if stake < 1.0:
            continue
        pnl = (stake / c) * (r["_win"] - c) - 0.004
        if tag == "m":
            tot_m += pnl
        else:
            tot_q += pnl
out["money_spotcheck_p49_extie"] = {
    "model_total": round(tot_m, 2), "impl_total": round(tot_q, 2),
    "matches_results_json": {"model": abs(tot_m - 1289.54) < 0.02,
                             "impl": abs(tot_q - 1335.71) < 0.02}}
print("money spot-check:", json.dumps(out["money_spotcheck_p49_extie"]))

with open(os.path.join(HERE, "crosscheck_irls.json"), "w") as f:
    json.dump(out, f, indent=1, default=float)
print("wrote crosscheck_irls.json")
