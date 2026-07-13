"""Fold re-seeding: shift the walk-forward fold anchor by +3d/+5d/+7d at
lambda*=100 and recheck the TEST-era comparison vs both qhat baselines.
Uses the unit's load()/lr (verified via IRLS crosscheck + byte repro), but my
own fold loop, metrics, and bootstrap."""
import sys, math, random, json
sys.path.insert(0, "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work-deepen/verify/metamodel-1/rerun")
import lr
from run_walkforward import load, featmat, FEATNAMES

DAY = 86400
IVL = 300
T_START = 1778500800
T_TEST = 1782432000
FOLD = 10 * DAY
CAP = 0.56
CA = 0.507493
EPS = 0.01

rows = load()
for r in rows:
    pass
ex = [r for r in rows if r["_win"] is not None]

def qhat_series(variant):
    q = {}
    for day in range(min(r["t0"] for r in rows) // DAY - 1, max(r["t0"] for r in rows) // DAY + 2):
        ns = day * DAY + 600
        book = [r for r in ex if r["t0"] + IVL <= ns and r["t0"] >= ns - 31 * DAY]
        w, n = sum(r["_win"] for r in book), len(book)
        if variant == "impl":
            q[day] = min(CAP, (w + 400 * 0.5068) / (n + 400))
        else:
            q[day] = min(CAP, (w + 100) / (n + 200))
    return q
QI, QS = qhat_series("impl"), qhat_series("spec")

def brier(ps, ys): return sum((p - y) ** 2 for p, y in zip(ps, ys)) / len(ys)
def ll1(p, y):
    p = min(max(p, EPS), 1 - EPS)
    return -(y * math.log(p) + (1 - y) * math.log(1 - p))

def boot(t0s, diffs, seed=7, B=4000):
    blocks = {}
    for t, d in zip(t0s, diffs):
        blocks.setdefault(t // 3600, []).append(d)
    bs = [(sum(v), len(v)) for k, v in sorted(blocks.items())]
    m = len(bs); rng = random.Random(seed); means = []
    for _ in range(B):
        tot = cnt = 0
        for _ in range(m):
            s, c = bs[rng.randrange(m)]
            tot += s; cnt += c
        means.append(tot / cnt)
    means.sort()
    return sum(diffs) / len(diffs), means[int(0.025 * B)], means[int(0.975 * B) - 1]

for off_days in (3, 5, 7):
    start = T_START + off_days * DAY
    preds = {}
    k = 1
    while start + k * FOLD < rows[-1]["t0"] + 1:
        lo, hi = start + k * FOLD, start + (k + 1) * FOLD
        tr = [r for r in ex if r["t0"] < lo]
        te = [r for r in ex if lo <= r["t0"] < hi]
        if te:
            X = featmat(tr, FEATNAMES); y = [r["_win"] for r in tr]
            mu, sd = lr.standardize_fit(X)
            Xs = lr.standardize_apply(X, mu, sd)
            w, b, J, it, conv = lr.fit_gd(Xs, y, 100.0)
            Xt = lr.standardize_apply(featmat(te, FEATNAMES), mu, sd)
            for r, p in zip(te, lr.predict(Xt, w, b)):
                preds[r["t0"]] = p
        k += 1
    te = [r for r in ex if r["t0"] >= T_TEST and r["t0"] in preds]
    ys = [r["_win"] for r in te]; t0s = [r["t0"] for r in te]
    pmod = [preds[r["t0"]] for r in te]
    out = {"offset_days": off_days, "n_test": len(te), "model_brier": round(brier(pmod, ys), 6)}
    for tag, Q in (("impl", QI), ("spec", QS)):
        pb = [Q[(r["t0"] - 600) // DAY] for r in te]
        dB = [(b - y) ** 2 - (m - y) ** 2 for b, m, y in zip(pb, pmod, ys)]
        dL = [ll1(b, y) - ll1(m, y) for b, m, y in zip(pb, pmod, ys)]
        mB = boot(t0s, dB); mL = boot(t0s, dL, seed=8)
        out[tag] = {"qhat_brier": round(brier(pb, ys), 6),
                    "dBrier": [round(x, 6) for x in mB], "dLL": [round(x, 6) for x in mL],
                    "pass_brier": mB[1] > 0, "pass_ll": mL[1] > 0}
    print(json.dumps(out))
