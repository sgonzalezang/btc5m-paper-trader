#!/usr/bin/env python3
"""Adversarial verify of reversal60 best spec (fixed 12bps contrarian, hold, 51c).
Lens: regime robustness & out-of-sample.
 (1) reproduce headline TRAIN/TEST numbers
 (2) re-split by calendar week; first/last thirds of full span AND of TEST
 (3) Kaufman efficiency segmentation (eff<=0.48 vs >0.48) per split
 (4) most-trending stretches: would the spec have survived?
 (5) parameter (threshold) stability across 6x10d folds
Stdlib only."""
import json, random

SC = "/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad"
d = json.load(open(SC + "/data/cb5m.json"))
t, o, c = d["t"], d["o"], d["c"]
n = len(t)

def fee(p): return 0.07 * p * (1 - p)
P = 0.51
QSTAR = P + fee(P)  # 0.527493
def net51(q): return q - P - fee(P)

# Kaufman efficiency over trailing 12 completed intervals, info known at entry of i:
# uses closes c[i-13..i-1]
def kauf(i):
    if i < 13: return None
    num = abs(c[i-1] - c[i-13])
    den = sum(abs(c[j] - c[j-1]) for j in range(i-12, i))
    return num/den if den > 0 else None

sigs = []  # (t0, win, absmv_bps, eff)
gaps = 0
for i in range(1, n):
    if t[i] - t[i-1] != 300:
        gaps += 1; continue
    mv = (o[i] - o[i-1]) / o[i-1]
    if abs(mv) * 1e4 < 12.0: continue
    up_won = 1 if c[i] >= o[i] else 0
    win = (1 - up_won) if mv > 0 else up_won
    sigs.append((t[i], win, abs(mv)*1e4, kauf(i)))

t0, t1 = t[0], t[-1]; span = t1 - t0
train = [s for s in sigs if s[0] < t0 + span*2/3]
test  = [s for s in sigs if s[0] >= t0 + span*2/3]

def q_of(rows): return (sum(r[1] for r in rows)/len(rows)) if rows else None

def block_boot_p(rows, target, nboot=4000, block=12, seed=17):
    wins = [r[1] for r in rows]; m = len(wins)
    if m == 0: return None
    rng = random.Random(seed); cnt = 0
    nblocks = (m + block - 1)//block
    for _ in range(nboot):
        s = 0; k = 0
        for _b in range(nblocks):
            st = rng.randrange(0, max(1, m - block + 1))
            take = min(block, m - k)
            s += sum(wins[st:st+take]); k += take
            if k >= m: break
        if s/k <= target: cnt += 1
    return cnt/nboot

out = {"gaps": gaps, "span_days": span/86400.0, "n_candles": n}

# (1) headline
qtr, qte = q_of(train), q_of(test)
out["headline"] = {
    "train": {"n": len(train), "q": qtr, "net51": net51(qtr)},
    "test":  {"n": len(test),  "q": qte, "net51": net51(qte),
              "p_vs_half": block_boot_p(test, 0.5),
              "p_vs_qstar": block_boot_p(test, QSTAR)},
}
print("HEADLINE  TRAIN n=%d q=%.4f net51=%+.4f | TEST n=%d q=%.4f net51=%+.4f p.5=%.4f pq*=%.4f"
      % (len(train), qtr, net51(qtr), len(test), qte, net51(qte),
         out["headline"]["test"]["p_vs_half"], out["headline"]["test"]["p_vs_qstar"]))

# (2a) weekly split
print("\n== weekly (7d buckets from start) ==")
weeks = {}
for s in sigs:
    w = int((s[0]-t0)//(7*86400))
    weeks.setdefault(w, []).append(s)
wk_rows = []
for w in sorted(weeks):
    rows = weeks[w]; q = q_of(rows)
    wk_rows.append({"week": w, "n": len(rows), "q": q, "net51": net51(q)})
    print("wk%02d n=%4d q=%.4f net51=%+.4f %s" % (w, len(rows), q, net51(q),
          "TEST" if rows[0][0] >= t0+span*2/3 else ""))
out["weekly"] = wk_rows
pos_wk = sum(1 for r in wk_rows if r["net51"] > 0)
print("weeks clearing fees at 51c: %d / %d" % (pos_wk, len(wk_rows)))

# (2b) thirds of full span and thirds of TEST
def thirds(rows, label):
    lo = min(r[0] for r in rows); hi = max(r[0] for r in rows); sp = hi - lo + 1
    res = []
    for k in range(3):
        seg = [r for r in rows if lo + sp*k/3 <= r[0] < lo + sp*(k+1)/3]
        q = q_of(seg)
        res.append({"n": len(seg), "q": q, "net51": net51(q) if q is not None else None})
        print("%s third%d n=%4d q=%s net51=%s" % (label, k+1, len(seg),
              "%.4f" % q if q else "-", "%+.4f" % net51(q) if q else "-"))
    return res
print("\n== thirds ==")
out["thirds_full"] = thirds(sigs, "FULL")
out["thirds_test"] = thirds(test, "TEST")

# (3) Kaufman efficiency segmentation
print("\n== Kaufman efficiency (<=0.48 calm vs >0.48 trending) ==")
seg = {}
for name, rows in [("TRAIN", train), ("TEST", test), ("FULL", sigs)]:
    calm = [r for r in rows if r[3] is not None and r[3] <= 0.48]
    trend = [r for r in rows if r[3] is not None and r[3] > 0.48]
    qc, qt_ = q_of(calm), q_of(trend)
    seg[name] = {"calm": {"n": len(calm), "q": qc, "net51": net51(qc) if qc else None},
                 "trend": {"n": len(trend), "q": qt_, "net51": net51(qt_) if qt_ else None}}
    print("%s calm n=%4d q=%.4f net51=%+.4f | trend n=%4d q=%.4f net51=%+.4f"
          % (name, len(calm), qc, net51(qc), len(trend), qt_, net51(qt_)))
out["eff_segments"] = seg
# bootstrap on TEST-trending: does spec lose significantly there?
test_trend = [r for r in test if r[3] is not None and r[3] > 0.48]
out["test_trend_p_vs_qstar"] = block_boot_p(test_trend, QSTAR)
test_calm = [r for r in test if r[3] is not None and r[3] <= 0.48]
out["test_calm_p_vs_half"] = block_boot_p(test_calm, 0.5)
out["test_calm_p_vs_qstar"] = block_boot_p(test_calm, QSTAR)
print("TEST calm p(q<=0.5)=%.4f p(q<=q*)=%.4f | TEST trend p(q<=q*)=%.4f"
      % (out["test_calm_p_vs_half"], out["test_calm_p_vs_qstar"], out["test_trend_p_vs_qstar"]))

# (4) most trending stretch: rank days by median eff of signals; also daily net drift
print("\n== per-day eff & spec pnl: 5 most-trending days ==")
days = {}
for s in sigs:
    dy = int((s[0]-t0)//86400)
    days.setdefault(dy, []).append(s)
day_rows = []
for dy, rows in days.items():
    effs = sorted(r[3] for r in rows if r[3] is not None)
    med = effs[len(effs)//2] if effs else None
    q = q_of(rows)
    day_rows.append({"day": dy, "n": len(rows), "med_eff": med, "q": q, "net51": net51(q)})
day_rows.sort(key=lambda r: -(r["med_eff"] or 0))
for r in day_rows[:5]:
    print("day %2d n=%3d med_eff=%.3f q=%.4f net51=%+.4f" % (r["day"], r["n"], r["med_eff"], r["q"], r["net51"]))
out["top_trend_days"] = day_rows[:8]

# (5) threshold stability across 6x10d folds: argmax net51 per fold among thresholds
print("\n== best threshold per 10d fold (by net51; min 30 sigs) ==")
THRS = [8, 10, 12, 14, 16, 20, 25]
# need all-move signal list
allsig = []
for i in range(1, n):
    if t[i]-t[i-1] != 300: continue
    mv = (o[i]-o[i-1])/o[i-1]
    up_won = 1 if c[i] >= o[i] else 0
    win = (1-up_won) if mv > 0 else up_won
    allsig.append((t[i], win, abs(mv)*1e4))
folds = []
for k in range(6):
    lo = t0 + span*k/6; hi = t0 + span*(k+1)/6
    rows = [s for s in allsig if lo <= s[0] < hi]
    best = None
    tab = {}
    for thr in THRS:
        sel = [s for s in rows if s[2] >= thr]
        if len(sel) < 30: continue
        q = q_of(sel); nv = net51(q)
        tab[thr] = {"n": len(sel), "q": q, "net51": nv}
        if best is None or nv > tab[best]["net51"]: best = thr
    folds.append({"fold": k, "best_thr": best, "tab": tab})
    print("fold %d best_thr=%s  " % (k, best) +
          " ".join("%d:%+.3f(n=%d)" % (thr, v["net51"], v["n"]) for thr, v in sorted(tab.items())))
out["fold_thresholds"] = folds

json.dump(out, open(SC + "/work/verify-reversal60/attack3_out.json", "w"), indent=1)
print("\nsaved attack3_out.json")
