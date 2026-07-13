"""Fine-tune stage per PREREG.md: pretrained model -> 32 settled live measure
records (real cost/spread/sec now vary). LOO evaluation vs LOO-refit qhat
variants. Declared UNPOWERED up front (n=32); directional only.
"""
import json, math, os
import lr
from run_walkforward import (load, FEATNAMES, COST_ANCH, featmat, brier, logloss)

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data/state_extract.json"
LAM_STAR = 100.0
MU_GRID = [0.3, 1.0, 3.0, 10.0]
SEED_LO, SEED_HI, PRIOR_IMPL, CAP = 0.5057, 0.5068, 400, 0.56


def fit_offset(Xs, y, mu, w0, b0, max_iter=3000, tol=1e-9):
    """Minimize mean CE + mu/(2n)*||theta - theta0||^2 via BB-GD (theta incl. intercept)."""
    n, d = len(Xs), len(Xs[0])
    w, b = list(w0), b0

    def lg(w, b):
        p = lr.predict(Xs, w, b)
        eps = 1e-12
        ce = -sum(yi * math.log(max(pi, eps)) + (1 - yi) * math.log(max(1 - pi, eps))
                  for yi, pi in zip(y, p)) / n
        J = ce + mu / (2 * n) * (sum((a - c) ** 2 for a, c in zip(w, w0)) + (b - b0) ** 2)
        r = [pi - yi for pi, yi in zip(p, y)]
        gw = [sum(r[i] * Xs[i][j] for i in range(n)) / n + mu / n * (w[j] - w0[j]) for j in range(d)]
        gb = sum(r) / n + mu / n * (b - b0)
        return J, gw, gb

    J, gw, gb = lg(w, b)
    bw, bb, bJ = list(w), b, J
    lrate, pw, pb, pgw, pgb = 1.0, None, None, None, None
    for _ in range(max_iter):
        nw = [a - lrate * g for a, g in zip(w, gw)]
        nb = b - lrate * gb
        nJ, ngw, ngb = lg(nw, nb)
        if nJ < bJ: bw, bb, bJ = list(nw), nb, nJ
        if pw is not None:
            s = [a - c for a, c in zip(nw, pw)] + [nb - pb]
            g = [a - c for a, c in zip(ngw, pgw)] + [ngb - pgb]
            ss, sg = sum(a * a for a in s), sum(a * c for a, c in zip(s, g))
            lrate = min(max(ss / sg, 1e-4), 1e4) if sg > 1e-18 else 1.0
        pw, pb, pgw, pgb = list(w), b, list(gw), gb
        w, b, J, gw, gb = nw, nb, nJ, ngw, ngb
        if max(abs(gb), max(abs(g) for g in gw)) < tol:
            return w, b
    return bw, bb


def main():
    # ---------- pretrain final model on ALL 60d ex-tie rows ----------
    rows = load()
    ex = [r for r in rows if r["_win"] is not None]
    X = featmat(ex, FEATNAMES)
    y = [r["_win"] for r in ex]
    mu_s, sd_s = lr.standardize_fit(X)
    Xs = lr.standardize_apply(X, mu_s, sd_s)
    w_pre, b_pre, J, it, conv = lr.fit_gd(Xs, y, LAM_STAR)
    print("pretrain full-data fit:", {n: round(w, 5) for n, w in zip(FEATNAMES, w_pre)}, "b", round(b_pre, 5), conv)

    # ---------- live records ----------
    S = json.load(open(STATE))
    recs = [m for m in S["measure"] if m.get("f") and m.get("win") is not None]
    print("live settled records with feats:", len(recs), "wins", sum(m["win"] for m in recs))
    lives = []
    for m in recs:
        f = m["f"]
        p_eff = f["ask"] + 0.01
        cost = p_eff + 0.07 * p_eff * (1 - p_eff)
        h = f["hour"]
        lives.append({"t0": m["t0"], "win": m["win"], "p_eff": p_eff,
                      "x": {"cost": cost, "pm": f["pm"], "eff6": f["eff6"],
                            "cnt12": float(f["cnt12"]),
                            "hsin": math.sin(2 * math.pi * h / 24),
                            "hcos": math.cos(2 * math.pi * h / 24),
                            "vol": f["vol"], "spread": f["spread"], "sec": float(f["sec"])}})
    # standardization: shared feats use PRETRAIN stats; cost/spread/sec use live stats
    live_only = {"cost", "spread", "sec"}
    lmu, lsd = {}, {}
    for k in live_only:
        vals = [lv["x"][k] for lv in lives]
        mu_k = sum(vals) / len(vals)
        var = sum((v - mu_k) ** 2 for v in vals) / len(vals)
        lmu[k], lsd[k] = mu_k, (math.sqrt(var) if var > 1e-12 else 1.0)
    def zrow(lv):
        out = []
        for j, k in enumerate(FEATNAMES):
            if k in live_only:
                out.append((lv["x"][k] - lmu[k]) / lsd[k])
            else:
                out.append((lv["x"][k] - mu_s[j]) / sd_s[j])
        return out
    Z = [zrow(lv) for lv in lives]
    yl = [lv["win"] for lv in lives]
    n = len(lives)

    # ---------- LOO: fine-tuned model per mu ----------
    res = {"n_live": n, "wins": sum(yl), "mu_grid": MU_GRID, "K_finetune": len(MU_GRID)}
    loo = {}
    for mu in MU_GRID:
        ps = []
        for i in range(n):
            Zi = [Z[j] for j in range(n) if j != i]
            yi = [yl[j] for j in range(n) if j != i]
            w, b = fit_offset(Zi, yi, mu, w_pre, b_pre)
            ps.append(lr.predict([Z[i]], w, b)[0])
        loo[mu] = {"brier": round(brier(ps, yl), 6), "logloss": round(logloss(ps, yl), 6),
                   "preds_minmax": [round(min(ps), 4), round(max(ps), 4)]}
        print("mu", mu, loo[mu])
    res["loo_finetune"] = {str(k): v for k, v in loo.items()}
    mu_star = min(MU_GRID, key=lambda m: loo[m]["brier"])
    res["mu_star"] = mu_star

    # ---------- LOO baselines ----------
    # pretrained, no fine-tune
    ps_pre = lr.predict(Z, w_pre, b_pre)
    res["pretrained_no_ft"] = {"brier": round(brier(ps_pre, yl), 6), "logloss": round(logloss(ps_pre, yl), 6)}
    # LOO-refit qhat impl / spec (trailing-book analogue: the other 31 records)
    for var in ("impl", "spec"):
        ps = []
        for i in range(n):
            others = [lives[j] for j in range(n) if j != i]
            me = lives[i]
            if var == "impl":
                mine_lo = (me["x"]["cost"] < 0.50)
                grp = [o for o in others if (o["x"]["cost"] < 0.50) == mine_lo]
                seed = SEED_LO if mine_lo else SEED_HI
                q = min(CAP, (sum(o["win"] for o in grp) + PRIOR_IMPL * seed) / (len(grp) + PRIOR_IMPL))
            else:
                mine_lo = (me["p_eff"] < 0.50)
                grp = [o for o in others if (o["p_eff"] < 0.50) == mine_lo]
                q = min(CAP, (sum(o["win"] for o in grp) + 100) / (len(grp) + 200))
            ps.append(q)
        res[f"qhat_{var}_loo"] = {"brier": round(brier(ps, yl), 6), "logloss": round(logloss(ps, yl), 6)}
    res["const_0.5"] = {"brier": 0.25, "logloss": round(logloss([0.5] * n, yl), 6)}
    # deployed state values as-is (qlo .5068 / qhi .5030, bucket cost<0.50) -- in-sample, context only
    ps = [(0.5068 if lv["x"]["cost"] < 0.50 else 0.5030) for lv in lives]
    res["qhat_deployed_state_insample"] = {"brier": round(brier(ps, yl), 6), "logloss": round(logloss(ps, yl), 6)}

    # ---------- final fine-tuned coefficients at mu_star (all 32) ----------
    w_ft, b_ft = fit_offset(Z, yl, mu_star, w_pre, b_pre)
    res["finetuned_coefs_standardized"] = {n_: round(w_, 6) for n_, w_ in zip(FEATNAMES, w_ft)}
    res["finetuned_intercept"] = round(b_ft, 6)
    res["pretrain_coefs_standardized"] = {n_: round(w_, 6) for n_, w_ in zip(FEATNAMES, w_pre)}
    res["pretrain_intercept"] = round(b_pre, 6)
    res["standardization"] = {"shared_mu": {k: round(m, 6) for k, m in zip(FEATNAMES, mu_s)},
                              "shared_sd": {k: round(s, 6) for k, s in zip(FEATNAMES, sd_s)},
                              "live_only_mu": {k: round(v, 6) for k, v in lmu.items()},
                              "live_only_sd": {k: round(v, 6) for k, v in lsd.items()}}
    res["UNPOWERED"] = "n=32 over 2.5 days; nothing here can overturn the primary FAIL"
    with open(os.path.join(HERE, "finetune_results.json"), "w") as fh:
        json.dump(res, fh, indent=1)
    print(json.dumps({k: res[k] for k in ("pretrained_no_ft", "qhat_impl_loo", "qhat_spec_loo",
                                          "const_0.5", "qhat_deployed_state_insample", "mu_star")}, indent=1))
    print("finetuned coefs:", res["finetuned_coefs_standardized"], "b", res["finetuned_intercept"])
    print("wrote finetune_results.json")


if __name__ == "__main__":
    main()
