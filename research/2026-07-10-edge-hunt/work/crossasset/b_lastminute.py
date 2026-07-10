"""(b) Last-minute momentum: cb1m 14d. Signal = open-to-open return over [t0-60, t0)
(r = (o1[t0]-o1[t0-60])/o1[t0-60], knowable at t0). Outcome = interval [t0, t0+300) from cb5m.
Train = first 2/3 of the 14d, test = last 1/3. Then fill-price realism via pm_prices_sample."""
import sys, json
sys.path.insert(0, "/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad/work/crossasset")
from util import *

cb5 = load("cb5m"); cb1 = load("cb1m")
o1 = dict(zip(cb1["t"], cb1["o"]))
out5 = {}
for i, t in enumerate(cb5["t"]):
    out5[t] = 1 if cb5["c"][i] >= cb5["o"][i] else 0

t_lo, t_hi = cb1["t"][0], cb1["t"][-1]
rows = []  # (t0, r_lm_bps, outcome)
for t0 in cb5["t"]:
    if t0 - 60 < t_lo or t0 > t_hi: continue
    if t0 not in o1 or (t0 - 60) not in o1 or t0 not in out5: continue
    r = (o1[t0] - o1[t0 - 60]) / o1[t0 - 60]
    rows.append((t0, r * 1e4, out5[t0]))
N = len(rows)
cut_t = rows[split_idx(N)][0]
print(f"matched 5m intervals with last-minute signal: {N}; span {(rows[-1][0]-rows[0][0])/86400:.1f}d; train/test cut t0={cut_t}")

# map to a global index grid for block bootstrap (use position in rows; blocks of 12 = 1h)
results = {}
print(f"\n== P(outcome follows sign of last-minute move) by |r| bucket ==")
print(f"{'bucket(bps)':>12} {'trainRate':>9} {'nTr':>5} {'pTr':>7} {'testRate':>9} {'nTe':>5}")
for lo, hi in [(0.5, 1), (1, 2), (2, 4), (4, 8), (8, 1e9), (2, 1e9), (4, 1e9), (0, 1e9)]:
    tr = {}; te = {}
    for idx, (t0, rb, oc) in enumerate(rows):
        if rb == 0: continue
        m = abs(rb)
        if not (lo <= m < hi): continue
        hit = 1 if (oc == 1) == (rb > 0) else 0
        (tr if t0 < cut_t else te)[idx] = hit
    r, ntr, p, ci = block_bootstrap_p(tr, N)
    kte, nte, rte = rate(list(te.values()))
    lab = f"[{lo},{'inf' if hi>1e8 else hi})"
    print(f"{lab:>12} {r:9.4f} {ntr:5d} {p:7.4f} {rte:9.4f} {nte:5d}")
    results[f"follow_{lab}"] = dict(train=r, n_train=ntr, p_train=p, test=rte, n_test=nte)

# Longer lookbacks for context: 2m and 3m pre-interval momentum
for look in (120, 180):
    tr = {}; te = {}
    for idx, (t0, rb, oc) in enumerate(rows):
        if (t0 - look) not in o1 or t0 not in o1: continue
        r = (o1[t0] - o1[t0 - look]) / o1[t0 - look] * 1e4
        if abs(r) < 2: continue
        hit = 1 if (oc == 1) == (r > 0) else 0
        (tr if t0 < cut_t else te)[idx] = hit
    r_, ntr, p, ci = block_bootstrap_p(tr, N)
    kte, nte, rte = rate(list(te.values()))
    print(f"lookback {look}s |r|>=2bps: train {r_:.4f} (n={ntr}, p={p:.4f})  test {rte:.4f} (n={nte})")
    results[f"look{look}_ge2"] = dict(train=r_, n_train=ntr, p_train=p, test=rte, n_test=nte)

json.dump(results, open("/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad/work/crossasset/b_lastminute_results.json", "w"), indent=1)
print("\nsaved b_lastminute_results.json")
