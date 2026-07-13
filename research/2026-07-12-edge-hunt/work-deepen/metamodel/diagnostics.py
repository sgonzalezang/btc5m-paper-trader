"""POST-HOC diagnostics (labeled as such; the FAIL verdict is already fixed by
PREREG.md). Questions:
 D1. Where does the lambda path bottom out? (extend grid + intercept-only)
 D2. Does walk-forward intercept-only (trailing base rate, 10d refit) beat the
     nightly qhat baselines? (isolates cadence/cap effects from feature value)
 D3. Best TEST ablation (only_pm) vs spec-qhat: block-boot CI (TEST-selected,
     K=11 -- diagnostic only, can never be a pass)
 D4. Calibration of the primary model on TEST.
"""
import json, math, os
import lr
from run_walkforward import (load, qhat_series, baseline_pred, walkforward, featmat,
                             brier, logloss, block_boot_meandiff, FEATNAMES,
                             T_TEST, T_START, FOLD, EPS_CLIP)

HERE = os.path.dirname(os.path.abspath(__file__))


def intercept_only_preds(rows):
    """Walk-forward trailing-mean (all prior ex-tie rows), 10d refit."""
    ex = [r for r in rows if r["_win"] is not None]
    preds = {}
    k = 1
    while T_START + k * FOLD < rows[-1]["t0"] + 1:
        lo, hi = T_START + k * FOLD, T_START + (k + 1) * FOLD
        tr = [r for r in ex if r["t0"] < lo]
        q = sum(r["_win"] for r in tr) / len(tr)
        for r in ex:
            if lo <= r["t0"] < hi:
                preds[r["t0"]] = q
        k += 1
    return preds


def main():
    rows = load()
    ex = [r for r in rows if r["_win"] is not None]
    qs = qhat_series(rows)
    out = {"note": "POST-HOC diagnostics; verdict unaffected (FAIL per PREREG)."}

    # D1 extended lambda path
    ext = []
    for lam in (300.0, 1000.0, 10000.0):
        preds, _ = walkforward(rows, FEATNAMES, lam)
        oos = [r for r in ex if r["t0"] in preds]
        tr = [r for r in oos if r["t0"] < T_TEST]
        te = [r for r in oos if r["t0"] >= T_TEST]
        ext.append({"lambda": lam,
                    "brier_train_oos": round(brier([preds[r["t0"]] for r in tr], [r["_win"] for r in tr]), 6),
                    "brier_test_oos": round(brier([preds[r["t0"]] for r in te], [r["_win"] for r in te]), 6)})
        print("ext lam", lam, ext[-1])
    io = intercept_only_preds(rows)
    oos = [r for r in ex if r["t0"] in io]
    tr = [r for r in oos if r["t0"] < T_TEST]
    te = [r for r in oos if r["t0"] >= T_TEST]
    ext.append({"lambda": "inf (intercept-only trailing mean)",
                "brier_train_oos": round(brier([io[r["t0"]] for r in tr], [r["_win"] for r in tr]), 6),
                "brier_test_oos": round(brier([io[r["t0"]] for r in te], [r["_win"] for r in te]), 6)})
    print("intercept-only", ext[-1])
    out["D1_extended_lambda"] = ext

    # D2 intercept-only vs qhat baselines on TEST (median anchor)
    ys = [r["_win"] for r in te]
    t0s = [r["t0"] for r in te]
    pio = [io[r["t0"]] for r in te]
    d2 = {"intercept_brier_test": round(brier(pio, ys), 6)}
    for var in ("impl", "spec"):
        pb = [baseline_pred(r, qs, 1, var) for r in te]
        dB = [(b1 - y) ** 2 - (m1 - y) ** 2 for b1, m1, y in zip(pb, pio, ys)]
        d2[var] = {"qhat_brier": round(brier(pb, ys), 6),
                   "improve_brier_intercept_over_qhat": block_boot_meandiff(t0s, dB, B=4000)}
        print("D2", var, d2[var]["qhat_brier"], round(d2[var]["improve_brier_intercept_over_qhat"]["mean"], 6),
              [round(x, 6) for x in d2[var]["improve_brier_intercept_over_qhat"]["ci95"]])
    out["D2_intercept_vs_qhat"] = d2

    # D3 only_pm (TEST-best ablation, post-hoc) vs spec qhat
    R = json.load(open(os.path.join(HERE, "results.json")))
    lam_star = R["lambda_star"]
    ppm, _ = walkforward(rows, ["pm"], lam_star)
    ppmv = [ppm[r["t0"]] for r in te]
    d3 = {"only_pm_brier_test": round(brier(ppmv, ys), 6), "selected_on": "TEST (K=11 diagnostics)"}
    for var in ("impl", "spec"):
        pb = [baseline_pred(r, qs, 1, var) for r in te]
        dB = [(b1 - y) ** 2 - (m1 - y) ** 2 for b1, m1, y in zip(pb, ppmv, ys)]
        d3[var] = block_boot_meandiff(t0s, dB, B=4000)
        print("D3 only_pm vs", var, round(d3[var]["mean"], 6), [round(x, 6) for x in d3[var]["ci95"]])
    out["D3_only_pm_posthoc"] = d3

    # D4 calibration of primary model on TEST + prediction spread
    preds = {int(k): v["phat"] for k, v in json.load(open(os.path.join(HERE, "preds_oos.json"))).items()}
    pv = sorted(preds[r["t0"]] for r in te)
    out["D4_pred_range_TEST"] = {"min": round(pv[0], 4), "p25": round(pv[len(pv)//4], 4),
                                 "median": round(pv[len(pv)//2], 4), "p75": round(pv[3*len(pv)//4], 4),
                                 "max": round(pv[-1], 4)}
    qb = sorted(te, key=lambda r: preds[r["t0"]])
    n5 = len(qb) // 5
    cal = []
    for i in range(5):
        seg = qb[i*n5: (i+1)*n5 if i < 4 else len(qb)]
        cal.append({"mean_pred": round(sum(preds[r["t0"]] for r in seg) / len(seg), 4),
                    "emp_win": round(sum(r["_win"] for r in seg) / len(seg), 4), "n": len(seg)})
    out["D4_calibration_quintiles_TEST"] = cal
    print("D4 range", out["D4_pred_range_TEST"]); print("D4 cal", cal)

    # qhat trajectory samples (median anchor)
    days = sorted({r["t0"] // 86400 for r in rows})
    traj = []
    for day in days[::7] + [days[-1]]:
        traj.append({"day_utc": day * 86400, "impl": qs[(day, 1)]["impl"], "spec": qs[(day, 1)]["spec"]})
    out["qhat_trajectory_p49"] = traj
    print("qhat traj:", [(t["impl"], t["spec"]) for t in traj])

    with open(os.path.join(HERE, "diagnostics.json"), "w") as f:
        json.dump(out, f, indent=1)
    print("wrote diagnostics.json")


if __name__ == "__main__":
    main()
