"""ML-PLAN Phase 1 executed: walk-forward meta-model vs bucketed-qhat baselines.

Everything per PREREG.md (written first). Python3 stdlib only.
Outputs: results.json (all numbers), preds_oos.json (per-row OOS predictions).
"""
import json, math, os, sys
import lr

HERE = os.path.dirname(os.path.abspath(__file__))
DS = os.path.join(HERE, "..", "dataset", "signals_60d.json")
CB5 = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data/cb5m.json"

IVL = 300
DAY = 86400
FOLD = 10 * DAY
T_START = 1778500800            # May 11 12:00 UTC (dataset window start)
T_TEST = 1782432000             # Jun 26 00:00 UTC
CAP = 0.56
SEED_LO, SEED_HI = 0.5057, 0.5068
PRIOR_IMPL = 400
FILL_ANCH = [0.45, 0.49, 0.51]
COST_ANCH = [0.467325, 0.507493, 0.527493]
GAS = 0.004
AVAIL = 0.55
LAMBDAS = [0.03, 0.1, 0.3, 1.0, 3.0, 10.0, 30.0, 100.0]
BOOT_B = 10000
EPS_CLIP = 0.01

FEATNAMES = ["cost", "pm", "eff6", "cnt12", "hsin", "hcos", "vol", "spread", "sec"]
CONST = {"cost": COST_ANCH[1], "spread": 0.01, "sec": 20.0}


def load():
    D = json.load(open(DS))
    rows = [r for r in D["rows"] if r.get("trigger") and r.get("gatePass")]
    # harmonized 2x5m vol for ALL rows
    cb = json.load(open(CB5))
    idx = {t: i for i, t in enumerate(cb["t"])}
    H, L = cb["h"], cb["l"]
    n_match = n_5m2 = 0
    for r in rows:
        t0 = r["t0"]
        j1, j2 = idx.get(t0 - 600), idx.get(t0 - 300)
        assert j1 is not None and j2 is not None, t0
        lo = min(L[j1], L[j2])
        v = round((max(H[j1], H[j2]) - lo) / lo * 100, 4)
        r["_vol5"] = v
        if r["feats"]["vol_src"] == "5m2":
            n_5m2 += 1
            if abs(v - r["feats"]["vol10m"]) < 1e-9:
                n_match += 1
    assert n_match == n_5m2, (n_match, n_5m2)
    print(f"vol harmonization: reproduced {n_match}/{n_5m2} 5m2 rows exactly")
    for r in rows:
        r["_win"] = None if r["label"] == "tie" else (1 if r["label"] == r["side"] else 0)
        h = r["feats"]["hour"]
        r["_x"] = {
            "cost": CONST["cost"], "pm": r["feats"]["pm"], "eff6": r["eff6"],
            "cnt12": float(r["cnt12"]), "hsin": math.sin(2 * math.pi * h / 24),
            "hcos": math.cos(2 * math.pi * h / 24), "vol": r["_vol5"],
            "spread": CONST["spread"], "sec": CONST["sec"]}
        r["_xship"] = dict(r["_x"], vol=r["feats"]["vol10m"])   # vol-as-shipped variant
    return rows


def featmat(rows, names, volkey="_x"):
    return [[r[volkey][k] for k in names] for r in rows]


# ---------------- baselines: nightly bucketed qhat ----------------
def qhat_series(rows):
    """Per-(day, anchor) qhat values for impl and spec variants, walk-forward.
    Nightly at 00:10 UTC: settled = labeled rows with t0+300 <= nightly_ts,
    within trailing 31d (t0 >= ns - 31d). Ties never settle a win -> excluded
    from the book (candle analogue of no-PM-resolution ambiguity)."""
    ex = [r for r in rows if r["_win"] is not None]
    days = sorted({r["t0"] // DAY for r in rows})
    out = {}   # (day, ai) -> {"impl": q, "spec": q}
    for day in range(min(days) - 1, max(days) + 2):
        ns = day * DAY + 600
        book = [r for r in ex if r["t0"] + IVL <= ns and r["t0"] >= ns - 31 * DAY]
        for ai, (fp, ca) in enumerate(zip(FILL_ANCH, COST_ANCH)):
            # every candle row carries the same anchor price in scenario ai
            w, n = sum(r["_win"] for r in book), len(book)
            # impl: bucket by cost<0.50 -> at this anchor ALL rows share a bucket
            lo_impl = ca < 0.50
            seed = SEED_LO if lo_impl else SEED_HI
            q_impl = min(CAP, (w + PRIOR_IMPL * seed) / (n + PRIOR_IMPL))
            # spec: bucket by p_eff<0.50
            q_spec = min(CAP, (w + 100) / (n + 200))
            out[(day, ai)] = {"impl": round(q_impl, 6), "spec": round(q_spec, 6)}
    return out


def baseline_pred(r, qs, ai, variant):
    # qhat active at t0 was set at the latest nightly (00:10 UTC) <= t0
    day = (r["t0"] - 600) // DAY
    return qs[(day, ai)][variant]


# ---------------- metrics ----------------
def brier(ps, ys):
    return sum((p - y) ** 2 for p, y in zip(ps, ys)) / len(ys)


def logloss(ps, ys):
    s = 0.0
    for p, y in zip(ps, ys):
        p = min(max(p, EPS_CLIP), 1 - EPS_CLIP)
        s += -(y * math.log(p) + (1 - y) * math.log(1 - p))
    return s / len(ys)


def block_boot_meandiff(t0s, diffs, B=BOOT_B, seed=12345):
    """1h-block bootstrap CI for mean(diffs). Deterministic LCG."""
    blocks = {}
    for t, d in zip(t0s, diffs):
        blocks.setdefault(t // 3600, []).append(d)
    keys = sorted(blocks)
    bs = [(sum(blocks[k]), len(blocks[k])) for k in keys]
    m = len(bs)
    state = seed
    means = []
    for _ in range(B):
        tot = cnt = 0.0
        for _ in range(m):
            state = (state * 6364136223846793005 + 1442695040888963407) % (1 << 64)
            j = (state >> 33) % m
            tot += bs[j][0]; cnt += bs[j][1]
        means.append(tot / cnt if cnt else 0.0)
    means.sort()
    def pct(q):
        i = q * (B - 1)
        lo_i, hi_i = int(i), min(int(i) + 1, B - 1)
        fr = i - lo_i
        return means[lo_i] * (1 - fr) + means[hi_i] * fr
    point = sum(diffs) / len(diffs)
    p_le0 = sum(1 for v in means if v <= 0) / B
    return {"mean": point, "ci95": [pct(0.025), pct(0.975)], "ci90": [pct(0.05), pct(0.95)],
            "p_boot_le0": p_le0, "n": len(diffs), "n_blocks": m}


# ---------------- walk-forward engine ----------------
def walkforward(rows, names, lam, volkey="_x"):
    """Returns list of (row, phat) for all OOS rows (ex-tie), + per-fold info."""
    ex = [r for r in rows if r["_win"] is not None]
    preds, folds = {}, []
    k = 1
    while T_START + k * FOLD < rows[-1]["t0"] + 1:
        lo, hi = T_START + k * FOLD, T_START + (k + 1) * FOLD
        tr = [r for r in ex if r["t0"] < lo]                      # train ex-tie only
        te = [r for r in rows if lo <= r["t0"] < hi]              # predict ties too (money sens.)
        if te:
            X = featmat(tr, names, volkey); y = [r["_win"] for r in tr]
            mu, sd = lr.standardize_fit(X)
            Xs = lr.standardize_apply(X, mu, sd)
            w, b, J, it, conv = lr.fit_gd(Xs, y, lam)
            Xt = lr.standardize_apply(featmat(te, names, volkey), mu, sd)
            for r, p in zip(te, lr.predict(Xt, w, b)):
                preds[r["t0"]] = p
            folds.append({"k": k, "lo": lo, "hi": hi, "n_train": len(tr), "n_test": len(te),
                          "iters": it, "conv": conv, "b": round(b, 6),
                          "w": {nm: round(wj, 6) for nm, wj in zip(names, w)}})
        k += 1
    return preds, folds


def main():
    rows = load()
    ex = [r for r in rows if r["_win"] is not None]
    qs = qhat_series(rows)
    results = {"prereg": "PREREG.md", "n_gated": len(rows), "n_extie": len(ex)}

    # ---------- lambda path (TRAIN-internal OOS selection) ----------
    path = []
    for lam in LAMBDAS:
        preds, folds = walkforward(rows, FEATNAMES, lam)
        oos = [r for r in ex if r["t0"] in preds]
        tr_oos = [r for r in oos if r["t0"] < T_TEST]
        te_oos = [r for r in oos if r["t0"] >= T_TEST]
        pb = brier([preds[r["t0"]] for r in tr_oos], [r["_win"] for r in tr_oos])
        pl = logloss([preds[r["t0"]] for r in tr_oos], [r["_win"] for r in tr_oos])
        tb = brier([preds[r["t0"]] for r in te_oos], [r["_win"] for r in te_oos])
        tl = logloss([preds[r["t0"]] for r in te_oos], [r["_win"] for r in te_oos])
        path.append({"lambda": lam, "brier_train_oos": round(pb, 6), "logloss_train_oos": round(pl, 6),
                     "brier_test_oos": round(tb, 6), "logloss_test_oos": round(tl, 6),
                     "n_train_oos": len(tr_oos), "n_test_oos": len(te_oos),
                     "final_fold_w": folds[-1]["w"], "final_fold_b": folds[-1]["b"]})
        print(f"lam={lam:<7} TRAIN-OOS brier={pb:.6f} ll={pl:.6f} | TEST-OOS brier={tb:.6f} ll={tl:.6f}")
    best = min(path, key=lambda e: e["brier_train_oos"])
    lam_star = best["lambda"]
    results["lambda_path"] = path
    results["lambda_star"] = lam_star
    results["K_selection"] = len(LAMBDAS)
    print("lambda* =", lam_star)

    # ---------- primary model at lambda* ----------
    preds, folds = walkforward(rows, FEATNAMES, lam_star)
    results["folds"] = folds
    oos = [r for r in ex if r["t0"] in preds]
    te_oos = [r for r in oos if r["t0"] >= T_TEST]
    tr_oos = [r for r in oos if r["t0"] < T_TEST]

    def eval_block(sub, tag):
        ys = [r["_win"] for r in sub]
        t0s = [r["t0"] for r in sub]
        pm = [preds[r["t0"]] for r in sub]
        out = {"n": len(sub), "base_rate": round(sum(ys) / len(ys), 4),
               "model": {"brier": round(brier(pm, ys), 6), "logloss": round(logloss(pm, ys), 6)}}
        for ai in range(3):
            anch = {}
            for var in ("impl", "spec"):
                pb_ = [baseline_pred(r, qs, ai, var) for r in sub]
                bb, bl = brier(pb_, ys), logloss(pb_, ys)
                dB = [(b1 - y) ** 2 - (m1 - y) ** 2 for b1, m1, y in zip(pb_, pm, ys)]
                def _ll(p, y):
                    p = min(max(p, EPS_CLIP), 1 - EPS_CLIP)
                    return -(y * math.log(p) + (1 - y) * math.log(1 - p))
                dL = [_ll(b1, y) - _ll(m1, y) for b1, m1, y in zip(pb_, pm, ys)]
                anch[var] = {"brier": round(bb, 6), "logloss": round(bl, 6),
                             "improve_brier": block_boot_meandiff(t0s, dB),
                             "improve_logloss": block_boot_meandiff(t0s, dL)}
            out[f"anchor_p{FILL_ANCH[ai]}"] = anch
        # context baselines
        out["const_0.5"] = {"brier": round(brier([0.5] * len(ys), ys), 6),
                            "logloss": round(logloss([0.5] * len(ys), ys), 6)}
        print(f"[{tag}] n={len(sub)} base={out['base_rate']} model brier={out['model']['brier']}")
        return out

    results["TEST_primary"] = eval_block(te_oos, "TEST-OOS")
    results["pooled_OOS"] = eval_block(oos, "pooled-OOS")
    results["TRAIN_internal"] = eval_block(tr_oos, "TRAIN-OOS")

    # ---------- verdict per prereg ----------
    med = results["TEST_primary"][f"anchor_p{FILL_ANCH[1]}"]
    checks = {}
    for var in ("impl", "spec"):
        for met in ("improve_brier", "improve_logloss"):
            ci = med[var][met]["ci95"]
            checks[f"{var}_{met}"] = {"mean": round(med[var][met]["mean"], 6),
                                      "ci95": [round(ci[0], 6), round(ci[1], 6)],
                                      "excludes_zero_positive": ci[0] > 0}
    results["verdict_checks"] = checks
    results["VERDICT"] = "PASS" if all(c["excludes_zero_positive"] for c in checks.values()) else "FAIL"
    print("VERDICT:", results["VERDICT"], json.dumps(checks, indent=1))

    # ---------- money metric ----------
    def kelly_pnl(sub, qfun, ai):
        """Fixed $1000 bank quarter-Kelly at anchor ai. Returns per-row pnl list + t0s.
        Rows with _win None (ties) count as losses when present in sub."""
        c = COST_ANCH[ai]
        pnls, t0s, staked = [], [], 0
        for r in sub:
            q = qfun(r)
            f = (q - c) / (1 - c)
            if f <= 0:
                pnls.append(0.0); t0s.append(r["t0"]); continue
            stake = min(0.25 * f * 1000.0, 50.0)
            if stake < 1.0:
                pnls.append(0.0); t0s.append(r["t0"]); continue
            sh = stake / c
            win = r["_win"]
            pnls.append(sh * ((win if win is not None else 0) - c) - GAS)
            t0s.append(r["t0"]); staked += 1
        return pnls, t0s, staked

    te_all = [r for r in rows if r["t0"] in preds and r["t0"] >= T_TEST]  # incl. ties
    money = {}
    for ai in range(3):
        entry = {}
        for tag, sub in (("extie", te_oos), ("ties_as_loss", te_all)):
            pm_, tm_, sm = kelly_pnl(sub, lambda r: preds[r["t0"]], ai)
            e = {"model": {"total": round(sum(pm_), 2), "staked": sm,
                           "per_signal": round(sum(pm_) / len(sub), 4),
                           "total_x_avail": round(sum(pm_) * AVAIL, 2)}}
            for var in ("impl", "spec"):
                pq_, tq_, sq = kelly_pnl(sub, lambda r: baseline_pred(r, qs, ai, var), ai)
                d = [a - b for a, b in zip(pm_, pq_)]
                e[var] = {"total": round(sum(pq_), 2), "staked": sq,
                          "per_signal": round(sum(pq_) / len(sub), 4),
                          "diff_model_minus_qhat": block_boot_meandiff(tm_, d,
                              B=BOOT_B if tag == "extie" else 2000)}
            entry[tag] = e
        money[f"anchor_p{FILL_ANCH[ai]}"] = entry
    results["money_TEST"] = money
    for k, v in money.items():
        e = v["extie"]
        print(f"money[{k}] model ${e['model']['total']} ({e['model']['staked']} staked) | "
              f"impl ${e['impl']['total']} | spec ${e['spec']['total']}")

    # ---------- ablations at lambda* (diagnostics) ----------
    abl = []
    groups = {"pm": ["pm"], "eff6": ["eff6"], "cnt12": ["cnt12"],
              "hour": ["hsin", "hcos"], "vol": ["vol"]}
    def run_cfg(tag, names, volkey="_x"):
        p2, _ = walkforward(rows, names, lam_star, volkey)
        sub = [r for r in te_oos if r["t0"] in p2]
        ys = [r["_win"] for r in sub]
        ps = [p2[r["t0"]] for r in sub]
        e = {"cfg": tag, "n": len(sub), "brier_test_oos": round(brier(ps, ys), 6),
             "logloss_test_oos": round(logloss(ps, ys), 6)}
        subtr = [r for r in tr_oos if r["t0"] in p2]
        e["brier_train_oos"] = round(brier([p2[r["t0"]] for r in subtr], [r["_win"] for r in subtr]), 6)
        abl.append(e)
        print("abl", tag, e["brier_test_oos"], e["logloss_test_oos"])
    for g, cols in groups.items():
        run_cfg(f"drop_{g}", [n for n in FEATNAMES if n not in cols])
    for g, cols in groups.items():
        run_cfg(f"only_{g}", cols)
    run_cfg("vol_as_shipped", FEATNAMES, "_xship")
    results["ablations"] = abl
    results["K_diagnostic"] = len(abl)

    # ---------- persist ----------
    with open(os.path.join(HERE, "results.json"), "w") as f:
        json.dump(results, f, indent=1)
    with open(os.path.join(HERE, "preds_oos.json"), "w") as f:
        json.dump({str(r["t0"]): {"phat": round(preds[r["t0"]], 6), "win": r["_win"],
                                  "split": r["split"]} for r in oos}, f)
    print("wrote results.json")


if __name__ == "__main__":
    main()
