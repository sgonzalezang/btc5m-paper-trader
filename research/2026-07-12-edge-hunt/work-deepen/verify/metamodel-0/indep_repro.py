#!/usr/bin/env python3
"""ADVERSARIAL VERIFICATION (REPRO lens) of wave-2 'metamodel' unit.

Fully independent re-implementation from PREREG.md spec:
  - dataset recomputed from cb5m.json with fresh code (trigger/gate/label/vol),
    cross-checked against the canonical signals_60d.json
  - logistic regression trained by MY OWN Newton-Raphson + Cholesky solver
    (the unit used BB gradient descent + Gaussian-elimination IRLS; this is a
    third, independent optimizer/implementation)
  - my own walk-forward, lambda path + TRAIN-internal selection, qhat baselines,
    1h-block bootstrap (Mersenne RNG, not their LCG), pass-bar, money sim,
    D1/D2 diagnostics, ablations, fine-tune baselines.
Python3 stdlib only. Writes results_indep.json.
"""
import json, math, os, random

HERE = os.path.dirname(os.path.abspath(__file__))
MM = os.path.normpath(os.path.join(HERE, "..", "..", "metamodel"))
DS = os.path.normpath(os.path.join(HERE, "..", "..", "dataset", "signals_60d.json"))
CB5 = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data/cb5m.json"
STATE = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data/state_extract.json"

IVL, DAY = 300, 86400
T_START = 1778500800          # May 11 12:00 UTC
T_TEST = 1782432000           # Jun 26 00:00 UTC
FOLD = 10 * DAY
CAP, SEED_LO, SEED_HI, PRIOR_IMPL = 0.56, 0.5057, 0.5068, 400
FILL_ANCH = [0.45, 0.49, 0.51]
COST_ANCH = [0.467325, 0.507493, 0.527493]
LAMBDAS = [0.03, 0.1, 0.3, 1.0, 3.0, 10.0, 30.0, 100.0]
FEATN = ["cost", "pm", "eff6", "cnt12", "hsin", "hcos", "vol", "spread", "sec"]
CONST_COST, CONST_SPREAD, CONST_SEC = 0.507493, 0.01, 20.0
GAS, AVAIL = 0.004, 0.55
CLIP = 0.01

OUT = {}

# ---------------------------------------------------------------- dataset
def build_rows_indep():
    cb = json.load(open(CB5))
    T, O, H, L = cb["t"], cb["o"], cb["h"], cb["l"]
    pos = {t: i for i, t in enumerate(T)}
    def roo(t):
        i = pos.get(t)
        if i is None or i + 1 >= len(T) or T[i + 1] != t + IVL:
            return None
        return (O[i + 1] - O[i]) / O[i]
    rows = []
    for t0 in range(T[1], T[-1] - IVL + 1, IVL):
        rp, r0 = roo(t0 - IVL), roo(t0)
        if rp is None or r0 is None:
            continue
        if abs(rp) * 100 < 0.12:
            continue
        rs = [roo(t0 - IVL * k) for k in range(1, 14)]
        if any(x is None for x in rs):
            continue
        last6 = rs[:6]
        den = sum(abs(x) for x in last6)
        net = 1.0
        for x in last6:
            net *= 1.0 + x
        eff6 = (abs(net - 1.0) / den) if den > 0 else 1.0
        cnt12 = sum(1 for x in rs[1:13] if abs(x) >= 0.0012)
        if not (eff6 >= 0.10 and cnt12 <= 6):
            continue
        side = "down" if rp > 0 else "up"
        label = "tie" if abs(r0) < 0.0001 else ("up" if r0 > 0 else "down")
        j1, j2 = pos[t0 - 600], pos[t0 - 300]
        lo = min(L[j1], L[j2])
        vol5 = round((max(H[j1], H[j2]) - lo) / lo * 100, 4)
        h = (t0 % DAY) // 3600
        rows.append({
            "t0": t0, "side": side, "label": label,
            "win": None if label == "tie" else (1 if label == side else 0),
            "x": {"cost": CONST_COST, "pm": round(abs(rp) * 100, 4),
                  "eff6": round(eff6, 4), "cnt12": float(cnt12),
                  "hsin": math.sin(2 * math.pi * h / 24),
                  "hcos": math.cos(2 * math.pi * h / 24),
                  "vol": vol5, "spread": CONST_SPREAD, "sec": CONST_SEC}})
    return rows


def crosscheck_dataset(rows):
    D = json.load(open(DS))
    ref = {r["t0"]: r for r in D["rows"] if r.get("trigger") and r.get("gatePass")}
    mine = {r["t0"]: r for r in rows}
    mism = {"only_mine": sorted(set(mine) - set(ref)), "only_ref": sorted(set(ref) - set(mine)),
            "field": 0}
    for t0, r in mine.items():
        rr = ref.get(t0)
        if not rr:
            continue
        ok = (rr["side"] == r["side"] and rr["label"] == r["label"]
              and abs(rr["feats"]["pm"] - r["x"]["pm"]) < 5e-5
              and abs(rr["eff6"] - r["x"]["eff6"]) < 5e-5
              and rr["cnt12"] == int(r["x"]["cnt12"]))
        if not ok:
            mism["field"] += 1
    return mism


# ---------------------------------------------------------------- my LR (Newton + Cholesky)
def zfit(X):
    n, d = len(X), len(X[0])
    mu = [sum(r[j] for r in X) / n for j in range(d)]
    sd = []
    for j in range(d):
        v = sum((r[j] - mu[j]) ** 2 for r in X) / n
        sd.append(math.sqrt(v) if v > 1e-12 else 1.0)
    return mu, sd


def zap(X, mu, sd):
    return [[(r[j] - mu[j]) / sd[j] for j in range(len(mu))] for r in X]


def sigm(z):
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


def chol_solve(A, b):
    m = len(A)
    Lc = [[0.0] * m for _ in range(m)]
    for i in range(m):
        for j in range(i + 1):
            s = A[i][j] - sum(Lc[i][k] * Lc[j][k] for k in range(j))
            if i == j:
                Lc[i][i] = math.sqrt(max(s, 1e-14))
            else:
                Lc[i][j] = s / Lc[j][j]
    y = [0.0] * m
    for i in range(m):
        y[i] = (b[i] - sum(Lc[i][k] * y[k] for k in range(i))) / Lc[i][i]
    x = [0.0] * m
    for i in range(m - 1, -1, -1):
        x[i] = (y[i] - sum(Lc[k][i] * x[k] for k in range(i + 1, m))) / Lc[i][i]
    return x


def newton_fit(Xs, y, lam, max_iter=60):
    """Minimize mean CE + lam/(2n)||w||^2 (intercept free). theta=[b,w]."""
    n, d = len(Xs), len(Xs[0])
    th = [0.0] * (d + 1)
    X1 = [[1.0] + r for r in Xs]
    prevJ = None
    for it in range(1, max_iter + 1):
        z = [sum(t * x for t, x in zip(th, r)) for r in X1]
        p = [sigm(v) for v in z]
        ce = 0.0
        for yi, pi in zip(y, p):
            pi = min(max(pi, 1e-12), 1 - 1e-12)
            ce -= yi * math.log(pi) + (1 - yi) * math.log(1 - pi)
        J = ce / n + lam / (2 * n) * sum(th[j] ** 2 for j in range(1, d + 1))
        g = [sum((p[i] - y[i]) * X1[i][j] for i in range(n)) / n for j in range(d + 1)]
        for j in range(1, d + 1):
            g[j] += lam / n * th[j]
        gi = max(abs(v) for v in g)
        if gi < 1e-11:
            return th[1:], th[0], J, it, True
        Hm = [[0.0] * (d + 1) for _ in range(d + 1)]
        for i in range(n):
            wgt = max(p[i] * (1 - p[i]), 1e-10)
            xi = X1[i]
            for a in range(d + 1):
                va = wgt * xi[a]
                row = Hm[a]
                for c in range(a, d + 1):
                    row[c] += va * xi[c]
        for a in range(d + 1):
            for c in range(a, d + 1):
                Hm[a][c] /= n
                Hm[c][a] = Hm[a][c]
        for j in range(1, d + 1):
            Hm[j][j] += lam / n
        st = chol_solve(Hm, g)
        # backtracking on J
        tstep = 1.0
        for _ in range(50):
            nt = [th[j] - tstep * st[j] for j in range(d + 1)]
            zz = [sum(t * x for t, x in zip(nt, r)) for r in X1]
            pp = [sigm(v) for v in zz]
            ce2 = 0.0
            for yi, pi in zip(y, pp):
                pi = min(max(pi, 1e-12), 1 - 1e-12)
                ce2 -= yi * math.log(pi) + (1 - yi) * math.log(1 - pi)
            J2 = ce2 / n + lam / (2 * n) * sum(nt[j] ** 2 for j in range(1, d + 1))
            if J2 <= J + 1e-15:
                break
            tstep *= 0.5
        th = nt
        if prevJ is not None and abs(prevJ - J2) < 1e-14 and gi < 1e-8:
            return th[1:], th[0], J2, it, True
        prevJ = J2
    return th[1:], th[0], prevJ, max_iter, gi < 1e-6


def predict(X, w, b):
    return [sigm(b + sum(a * c for a, c in zip(w, r))) for r in X]


# ---------------------------------------------------------------- metrics
def brier(ps, ys):
    return sum((p - y) ** 2 for p, y in zip(ps, ys)) / len(ys)


def ll1(p, y):
    p = min(max(p, CLIP), 1 - CLIP)
    return -(y * math.log(p) + (1 - y) * math.log(1 - p))


def logloss(ps, ys):
    return sum(ll1(p, y) for p, y in zip(ps, ys)) / len(ys)


def block_boot(t0s, diffs, B=10000, seed=2718):
    bl = {}
    for t, d in zip(t0s, diffs):
        bl.setdefault(t // 3600, [0.0, 0])
        bl[t // 3600][0] += d
        bl[t // 3600][1] += 1
    bs = [tuple(v) for _, v in sorted(bl.items())]
    m = len(bs)
    rng = random.Random(seed)
    means = []
    for _ in range(B):
        tot = cnt = 0.0
        for _ in range(m):
            s, c = bs[rng.randrange(m)]
            tot += s
            cnt += c
        means.append(tot / cnt)
    means.sort()
    def pct(q):
        i = q * (B - 1)
        lo = int(i)
        hi = min(lo + 1, B - 1)
        f = i - lo
        return means[lo] * (1 - f) + means[hi] * f
    return {"mean": sum(diffs) / len(diffs),
            "ci95": [pct(0.025), pct(0.975)], "ci90": [pct(0.05), pct(0.95)],
            "p_le0": sum(1 for v in means if v <= 0) / B, "n": len(diffs), "blocks": m}


# ---------------------------------------------------------------- qhat baselines
def qhat_tables(rows):
    ex = [r for r in rows if r["win"] is not None]
    need_days = {(r["t0"] - 600) // DAY for r in rows}
    tab = {}
    for day in range(min(need_days), max(need_days) + 1):
        ns = day * DAY + 600
        book = [r for r in ex if r["t0"] + IVL <= ns and r["t0"] >= ns - 31 * DAY]
        w, n = sum(r["win"] for r in book), len(book)
        per = []
        for ca in COST_ANCH:
            seed = SEED_LO if ca < 0.50 else SEED_HI
            qi = min(CAP, (w + PRIOR_IMPL * seed) / (n + PRIOR_IMPL))
            qsp = min(CAP, (w + 100) / (n + 200))
            per.append({"impl": qi, "spec": qsp})
        tab[day] = per
    return tab


def qbase(r, tab, ai, var):
    return tab[(r["t0"] - 600) // DAY][ai][var]


# ---------------------------------------------------------------- walk-forward
def walkforward(rows, names, lam, fold=FOLD):
    ex = [r for r in rows if r["win"] is not None]
    last = rows[-1]["t0"]
    preds, folds = {}, []
    k = 1
    while T_START + k * fold < last + 1:
        lo, hi = T_START + k * fold, T_START + (k + 1) * fold
        tr = [r for r in ex if r["t0"] < lo]
        te = [r for r in rows if lo <= r["t0"] < hi]
        if te and tr:
            X = [[r["x"][c] for c in names] for r in tr]
            mu, sd = zfit(X)
            w, b, J, it, conv = newton_fit(zap(X, mu, sd), [r["win"] for r in tr], lam)
            Xt = zap([[r["x"][c] for c in names] for r in te], mu, sd)
            for r, p in zip(te, predict(Xt, w, b)):
                preds[r["t0"]] = p
            folds.append({"k": k, "n_train": len(tr), "iters": it, "conv": conv,
                          "b": b, "w": {c: wj for c, wj in zip(names, w)}})
        k += 1
    return preds, folds


def main():
    rows = build_rows_indep()
    OUT["n_gated_indep"] = len(rows)
    OUT["dataset_crosscheck"] = crosscheck_dataset(rows)
    ex = [r for r in rows if r["win"] is not None]
    OUT["n_extie"] = len(ex)
    te_ex = [r for r in ex if r["t0"] >= T_TEST]
    OUT["test_gated"] = sum(1 for r in rows if r["t0"] >= T_TEST)
    print("gated", len(rows), "extie", len(ex), "xcheck", OUT["dataset_crosscheck"])

    tab = qhat_tables(rows)

    # ---- lambda path ----
    path = []
    for lam in LAMBDAS:
        preds, folds = walkforward(rows, FEATN, lam)
        oos = [r for r in ex if r["t0"] in preds]
        tr = [r for r in oos if r["t0"] < T_TEST]
        te = [r for r in oos if r["t0"] >= T_TEST]
        e = {"lambda": lam,
             "brier_train_oos": brier([preds[r["t0"]] for r in tr], [r["win"] for r in tr]),
             "brier_test_oos": brier([preds[r["t0"]] for r in te], [r["win"] for r in te]),
             "n_tr": len(tr), "n_te": len(te),
             "conv_all": all(f["conv"] for f in folds)}
        path.append(e)
        print(f"lam={lam:<6} tr={e['brier_train_oos']:.6f} te={e['brier_test_oos']:.6f} conv={e['conv_all']}")
    lam_star = min(path, key=lambda e: e["brier_train_oos"])["lambda"]
    OUT["lambda_path"] = path
    OUT["lambda_star"] = lam_star
    mono = all(path[i]["brier_train_oos"] >= path[i + 1]["brier_train_oos"] for i in range(len(path) - 1))
    OUT["lambda_path_monotone_train"] = mono
    print("lambda* =", lam_star, "monotone(train-oos):", mono)

    # ---- primary at lambda* ----
    preds, folds = walkforward(rows, FEATN, lam_star)
    OUT["folds"] = folds
    oos = [r for r in ex if r["t0"] in preds]
    te = [r for r in oos if r["t0"] >= T_TEST]
    ys = [r["win"] for r in te]
    t0s = [r["t0"] for r in te]
    pm = [preds[r["t0"]] for r in te]
    prim = {"n": len(te), "base": sum(ys) / len(ys),
            "model_brier": brier(pm, ys), "model_ll": logloss(pm, ys),
            "pred_min": min(pm), "pred_max": max(pm),
            "n_pred_gt_cap056": sum(1 for p in pm if p > 0.56)}
    checks = {}
    for ai in (0, 1, 2):
        for var in ("impl", "spec"):
            pb = [qbase(r, tab, ai, var) for r in te]
            key = f"a{FILL_ANCH[ai]}_{var}"
            prim[key + "_brier"] = brier(pb, ys)
            prim[key + "_ll"] = logloss(pb, ys)
            dB = [(b1 - y) ** 2 - (m1 - y) ** 2 for b1, m1, y in zip(pb, pm, ys)]
            dL = [ll1(b1, y) - ll1(m1, y) for b1, m1, y in zip(pb, pm, ys)]
            bB = block_boot(t0s, dB)
            bL = block_boot(t0s, dL)
            prim[key + "_improve_brier"] = bB
            prim[key + "_improve_ll"] = bL
            if ai == 1:
                checks[f"{var}_brier"] = bB["ci95"][0] > 0
                checks[f"{var}_ll"] = bL["ci95"][0] > 0
    prim["const05_brier"] = brier([0.5] * len(ys), ys)
    OUT["TEST_primary"] = prim
    OUT["pass_checks_ci95_lower_gt0"] = checks
    OUT["VERDICT_indep"] = "PASS" if all(checks.values()) else "FAIL"
    print("TEST n", prim["n"], "base", round(prim["base"], 4),
          "model brier", round(prim["model_brier"], 6), "ll", round(prim["model_ll"], 6))
    for var in ("impl", "spec"):
        k = f"a0.49_{var}"
        print(var, "brier", round(prim[k + "_brier"], 6),
              "dBrier", round(prim[k + "_improve_brier"]["mean"], 6),
              [round(x, 6) for x in prim[k + "_improve_brier"]["ci95"]],
              "p", prim[k + "_improve_brier"]["p_le0"],
              "| dLL", round(prim[k + "_improve_ll"]["mean"], 6),
              [round(x, 6) for x in prim[k + "_improve_ll"]["ci95"]])
    print("VERDICT (indep):", OUT["VERDICT_indep"])

    # pooled
    yso = [r["win"] for r in oos]
    OUT["pooled"] = {"n": len(oos), "model_brier": brier([preds[r["t0"]] for r in oos], yso)}

    # ---- compare per-row predictions vs unit's preds_oos.json ----
    ref = json.load(open(os.path.join(MM, "preds_oos.json")))
    diffs = []
    miss = 0
    for r in oos:
        e = ref.get(str(r["t0"]))
        if e is None:
            miss += 1
            continue
        diffs.append(abs(e["phat"] - preds[r["t0"]]))
    OUT["pred_compare"] = {"n": len(diffs), "missing": miss,
                           "max_absdiff": max(diffs), "mean_absdiff": sum(diffs) / len(diffs)}
    print("pred compare vs unit:", OUT["pred_compare"])

    # ---- ablations ----
    groups = {"pm": ["pm"], "eff6": ["eff6"], "cnt12": ["cnt12"],
              "hour": ["hsin", "hcos"], "vol": ["vol"]}
    abl = {}
    full_te_brier = prim["model_brier"]
    for g, cols in groups.items():
        p2, _ = walkforward(rows, [c for c in FEATN if c not in cols], lam_star)
        abl["drop_" + g] = brier([p2[r["t0"]] for r in te], ys)
        p3, _ = walkforward(rows, cols, lam_star)
        abl["only_" + g] = brier([p3[r["t0"]] for r in te], ys)
    OUT["ablations_test_brier"] = abl
    OUT["ablations_all_beat_full"] = {k: v < full_te_brier for k, v in abl.items()}
    print("ablations:", {k: round(v, 6) for k, v in abl.items()})
    print("full model TEST brier:", round(full_te_brier, 6),
          "beaten by all?", all(v < full_te_brier for v in abl.values()))

    # ---- D1 extended + intercept-only ----
    ext = {}
    for lam in (300.0, 1000.0, 10000.0):
        p2, _ = walkforward(rows, FEATN, lam)
        ext[str(lam)] = {"tr": brier([p2[r["t0"]] for r in oos if r["t0"] < T_TEST],
                                     [r["win"] for r in oos if r["t0"] < T_TEST]),
                         "te": brier([p2[r["t0"]] for r in te], ys)}
    io = {}
    k = 1
    last = rows[-1]["t0"]
    while T_START + k * FOLD < last + 1:
        lo, hi = T_START + k * FOLD, T_START + (k + 1) * FOLD
        tr = [r for r in ex if r["t0"] < lo]
        q = sum(r["win"] for r in tr) / len(tr)
        for r in ex:
            if lo <= r["t0"] < hi:
                io[r["t0"]] = q
        k += 1
    pio = [io[r["t0"]] for r in te]
    ext["intercept_only"] = {"tr": brier([io[r["t0"]] for r in oos if r["t0"] < T_TEST],
                                         [r["win"] for r in oos if r["t0"] < T_TEST]),
                             "te": brier(pio, ys)}
    OUT["D1_extended"] = ext
    print("D1 ext:", {k2: {a: round(b, 6) for a, b in v.items()} for k2, v in ext.items()})

    # ---- D2: intercept-only vs qhat, B=20000 ----
    d2 = {}
    for var in ("impl", "spec"):
        pb = [qbase(r, tab, 1, var) for r in te]
        dB = [(b1 - y) ** 2 - (m1 - y) ** 2 for b1, m1, y in zip(pb, pio, ys)]
        d2[var] = block_boot(t0s, dB, B=20000, seed=97531)
        print("D2 intercept vs", var, round(d2[var]["mean"], 6),
              "ci95", [round(x, 7) for x in d2[var]["ci95"]],
              "ci90", [round(x, 7) for x in d2[var]["ci90"]], "p", d2[var]["p_le0"])
    OUT["D2_intercept_vs_qhat"] = d2
    OUT["qhat_traj_last_impl"] = tab[max(tab)][1]["impl"]
    OUT["qhat_traj_last_spec"] = tab[max(tab)][1]["spec"]

    # ---- money sim (median anchor + p51 ties-as-loss) ----
    te_all = [r for r in rows if r["t0"] in preds and r["t0"] >= T_TEST]

    def kelly(sub, qf, ai):
        c = COST_ANCH[ai]
        pnl, tt = [], []
        st = 0
        for r in sub:
            q = qf(r)
            f = (q - c) / (1 - c)
            s = min(0.25 * f * 1000.0, 50.0) if f > 0 else 0.0
            if s < 1.0:
                pnl.append(0.0)
                tt.append(r["t0"])
                continue
            sh = s / c
            w = r["win"] if r["win"] is not None else 0
            pnl.append(sh * (w - c) - GAS)
            tt.append(r["t0"])
            st += 1
        return pnl, tt, st

    money = {}
    for ai, tag, sub in ((1, "extie_p49", te), (2, "tiesloss_p51", te_all)):
        pmn, tmn, smn = kelly(sub, lambda r: preds[r["t0"]], ai)
        e = {"model_total": sum(pmn), "model_staked": smn,
             "model_total_x_avail": sum(pmn) * AVAIL}
        for var in ("impl", "spec"):
            pq, _, sq = kelly(sub, lambda r, v=var: qbase(r, tab, ai, v), ai)
            d = [a - b for a, b in zip(pmn, pq)]
            e[var] = {"total": sum(pq), "staked": sq,
                      "diff": block_boot(tmn, d, B=4000, seed=1357)}
        money[tag] = e
        print(f"money[{tag}] model {sum(pmn):.2f} ({smn}) impl {e['impl']['total']:.2f} "
              f"spec {e['spec']['total']:.2f} diff_impl {e['impl']['diff']['mean']:.4f} "
              f"ci {[round(x,3) for x in e['impl']['diff']['ci95']]}")
    OUT["money"] = money

    # ---- fine-tune baselines from state_extract (independent) ----
    S = json.load(open(STATE))
    recs = [m for m in S["measure"] if m.get("f") and m.get("win") is not None]
    yl = [m["win"] for m in recs]
    n = len(recs)
    ftb = {"n": n, "wins": sum(yl), "const_brier": brier([0.5] * n, yl)}
    for var in ("impl", "spec"):
        ps = []
        for i, m in enumerate(recs):
            others = [recs[j] for j in range(n) if j != i]
            if var == "impl":
                pe = m["f"]["ask"] + 0.01
                ci = pe + 0.07 * pe * (1 - pe)
                mine_lo = ci < 0.50
                grp = [o for o in others
                       if ((o["f"]["ask"] + 0.01) + 0.07 * (o["f"]["ask"] + 0.01) * (1 - (o["f"]["ask"] + 0.01)) < 0.50) == mine_lo]
                seed = SEED_LO if mine_lo else SEED_HI
                q = min(CAP, (sum(o["win"] for o in grp) + PRIOR_IMPL * seed) / (len(grp) + PRIOR_IMPL))
            else:
                mine_lo = (m["f"]["ask"] + 0.01) < 0.50
                grp = [o for o in others if ((o["f"]["ask"] + 0.01) < 0.50) == mine_lo]
                q = min(CAP, (sum(o["win"] for o in grp) + 100) / (len(grp) + 200))
            ps.append(q)
        ftb[f"qhat_{var}_loo_brier"] = brier(ps, yl)
    ps = [(0.5068 if (m["f"]["ask"] + 0.01) + 0.07 * (m["f"]["ask"] + 0.01) * (1 - (m["f"]["ask"] + 0.01)) < 0.50 else 0.5030) for m in recs]
    ftb["deployed_insample_brier"] = brier(ps, yl)
    OUT["finetune_baselines"] = ftb
    print("finetune baselines:", {k: (round(v, 6) if isinstance(v, float) else v) for k, v in ftb.items()})

    with open(os.path.join(HERE, "results_indep.json"), "w") as f:
        json.dump(OUT, f, indent=1, default=float)
    print("wrote results_indep.json")


if __name__ == "__main__":
    main()
