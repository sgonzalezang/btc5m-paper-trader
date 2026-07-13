"""Adversarial verify: independent recompute of metamodel headline numbers.
Own code throughout: dataset load, qhat walk-forward series, Brier/LL, block
bootstrap (random.Random, multiple seeds, multiple block sizes), intercept-only
D2, money sim. Compares against results.json / diagnostics.json claims.
"""
import json, math, random

MM = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work-deepen/metamodel"
DS = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work-deepen/dataset/signals_60d.json"
DAY = 86400
IVL = 300
T_START = 1778500800
T_TEST = 1782432000
FOLD = 10 * DAY
CAP = 0.56
COST_ANCH = {0: 0.467325, 1: 0.507493, 2: 0.527493}
EPS = 0.01

D = json.load(open(DS))
rows = [r for r in D["rows"] if r.get("trigger") and r.get("gatePass")]
for r in rows:
    r["w"] = None if r["label"] == "tie" else (1 if r["label"] == r["side"] else 0)
ex = [r for r in rows if r["w"] is not None]
print("gated", len(rows), "extie", len(ex))

preds = {int(k): v["phat"] for k, v in json.load(open(MM + "/preds_oos.json")).items()}
te = [r for r in ex if r["t0"] >= T_TEST and r["t0"] in preds]
oos = [r for r in ex if r["t0"] in preds]
print("TEST-OOS extie n =", len(te), "base rate", round(sum(r["w"] for r in te) / len(te), 4),
      "pooled OOS n =", len(oos))
# every TEST extie row should be in preds
missing = [r["t0"] for r in ex if r["t0"] >= T_TEST and r["t0"] not in preds]
print("TEST extie rows missing from preds:", len(missing))
# and OOS should start at T_START+FOLD
print("min OOS t0 - (T_START+10d) =", min(preds) - (T_START + FOLD))

# ---- my own qhat series ----
def qhat_at(t0, ai, variant):
    day = (t0 - 600) // DAY
    ns = day * DAY + 600
    book = [r for r in ex if r["t0"] + IVL <= ns and r["t0"] >= ns - 31 * DAY]
    w = sum(r["w"] for r in book); n = len(book)
    if variant == "impl":
        seed = 0.5057 if COST_ANCH[ai] < 0.50 else 0.5068
        return min(CAP, (w + 400 * seed) / (n + 400))
    return min(CAP, (w + 100) / (n + 200))

# cache per day
qcache = {}
def qhat(r, ai, variant):
    day = (r["t0"] - 600) // DAY
    key = (day, ai, variant)
    if key not in qcache:
        qcache[key] = qhat_at(r["t0"], ai, variant)
    return qcache[key]

def brier(ps, ys): return sum((p - y) ** 2 for p, y in zip(ps, ys)) / len(ys)
def ll1(p, y):
    p = min(max(p, EPS), 1 - EPS)
    return -(y * math.log(p) + (1 - y) * math.log(1 - p))
def logloss(ps, ys): return sum(ll1(p, y) for p, y in zip(ps, ys)) / len(ys)

ys = [r["w"] for r in te]
pm = [preds[r["t0"]] for r in te]
t0s = [r["t0"] for r in te]
print("\nmodel TEST brier", round(brier(pm, ys), 6), "(claim .247069)  ll",
      round(logloss(pm, ys), 6), "(claim .687289)")

def myboot(t0s, diffs, seed, B=10000, blocksec=3600):
    blocks = {}
    for t, d in zip(t0s, diffs):
        blocks.setdefault(t // blocksec, []).append(d)
    bs = [(sum(v), len(v)) for k, v in sorted(blocks.items())]
    m = len(bs)
    rng = random.Random(seed)
    means = []
    for _ in range(B):
        tot = cnt = 0
        for _ in range(m):
            s, c = bs[rng.randrange(m)]
            tot += s; cnt += c
        means.append(tot / cnt)
    means.sort()
    lo, hi = means[int(0.025 * B)], means[int(0.975 * B) - 1]
    p = sum(1 for v in means if v <= 0) / B
    return sum(diffs) / len(diffs), lo, hi, p

report = {}
for ai in (1, 0, 2):
    for var in ("impl", "spec"):
        pb = [qhat(r, ai, var) for r in te]
        bB, bL = brier(pb, ys), logloss(pb, ys)
        dB = [(b - y) ** 2 - (m - y) ** 2 for b, m, y in zip(pb, pm, ys)]
        dL = [ll1(b, y) - ll1(m, y) for b, m, y in zip(pb, pm, ys)]
        mB = myboot(t0s, dB, seed=777)
        mL = myboot(t0s, dL, seed=778)
        print(f"anchor{ai} {var}: qhat brier {bB:.6f} ll {bL:.6f} | dBrier {mB[0]:+.6f} "
              f"CI[{mB[1]:+.6f},{mB[2]:+.6f}] p_le0={mB[3]:.3f} | dLL {mL[0]:+.6f} CI[{mL[1]:+.6f},{mL[2]:+.6f}]")
        if ai == 1:
            report[var] = (bB, bL, mB, mL)

# seed & block-size sensitivity of verdict checks (median anchor, impl, brier)
pb = [qhat(r, 1, "impl") for r in te]
dB = [(b - y) ** 2 - (m - y) ** 2 for b, m, y in zip(pb, pm, ys)]
print("\nverdict-diff sensitivity (impl brier):")
for seed in (1, 2, 3, 42, 12345):
    for bsz in (1800, 3600, 7200, 14400):
        m0, lo, hi, p = myboot(t0s, dB, seed=seed, blocksec=bsz)
        print(f"  seed={seed} block={bsz}s: mean {m0:+.6f} CI[{lo:+.6f},{hi:+.6f}] pass={lo>0}")

# ---- D2 intercept-only ----
io = {}
k = 1
while T_START + k * FOLD < rows[-1]["t0"] + 1:
    lo_, hi_ = T_START + k * FOLD, T_START + (k + 1) * FOLD
    tr = [r for r in ex if r["t0"] < lo_]
    q = sum(r["w"] for r in tr) / len(tr)
    for r in ex:
        if lo_ <= r["t0"] < hi_:
            io[r["t0"]] = q
    k += 1
pio = [io[r["t0"]] for r in te]
print("\nintercept-only TEST brier", round(brier(pio, ys), 6), "(claim .245925)")
for var in ("impl", "spec"):
    pb = [qhat(r, 1, var) for r in te]
    dB = [(b - y) ** 2 - (m - y) ** 2 for b, m, y in zip(pb, pio, ys)]
    print(f"D2 vs {var}:")
    for seed in (1, 2, 777, 12345):
        m0, lo, hi, p = myboot(t0s, dB, seed=seed)
        print(f"  seed={seed}: mean {m0:+.7f} CI95[{lo:+.7f},{hi:+.7f}] p_le0={p:.4f}")
    for bsz in (1800, 7200, 14400):
        m0, lo, hi, p = myboot(t0s, dB, seed=777, blocksec=bsz)
        print(f"  block={bsz}s: mean {m0:+.7f} CI95[{lo:+.7f},{hi:+.7f}] p_le0={p:.4f}")

# ---- money (median anchor, ex-tie) ----
c = COST_ANCH[1]
def pnl(qf):
    tot = 0.0; per = []
    for r in te:
        q = qf(r)
        f = (q - c) / (1 - c)
        if f <= 0:
            per.append(0.0); continue
        st = min(0.25 * f * 1000, 50.0)
        if st < 1:
            per.append(0.0); continue
        per.append(st / c * (r["w"] - c) - 0.004)
    return per
p_model = pnl(lambda r: preds[r["t0"]])
p_impl = pnl(lambda r: qhat(r, 1, "impl"))
p_spec = pnl(lambda r: qhat(r, 1, "spec"))
print("\nmoney extie median anchor: model", round(sum(p_model), 2), "(claim 1289.54)",
      "impl", round(sum(p_impl), 2), "(claim 1335.71)", "spec", round(sum(p_spec), 2), "(claim 1459.97)")
d = [a - b for a, b in zip(p_model, p_impl)]
m0, lo, hi, p = myboot(t0s, d, seed=9)
print("diff model-impl per-signal", round(m0, 4), "CI", [round(lo, 3), round(hi, 3)])

# ---- qhat trajectory end vs realized ----
last_day = max(r["t0"] for r in rows) // DAY
print("\nimpl qhat at end:", round(qhat_at(last_day * DAY + 601, 1, "impl"), 4),
      "spec:", round(qhat_at(last_day * DAY + 601, 1, "spec"), 4),
      "realized TEST q:", round(sum(ys) / len(ys), 4))
