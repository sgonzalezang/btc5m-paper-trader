#!/usr/bin/env python3
"""Sensitivity: fixed fill p=0.51 (and p=0.53) instead of the live empirical fill
distribution -- removes the generous 'cheap fills keep q=measured' assumption."""
import json, math, random, os

SCRATCH = "/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad"
W = os.path.join(SCRATCH, "work", "sizing")
D = os.path.join(SCRATCH, "data")
random.seed(7)

def cost(p): return p + 0.07 * p * (1 - p)
F_FULL = 0.06879686438507804
GAS = 0.004
STRATS = {"flat50": ("flat", 50.0), "kelly_q": ("frac", F_FULL/4),
          "kelly_h": ("frac", F_FULL/2), "kelly_f": ("frac", F_FULL)}

stream = json.load(open(os.path.join(W, "stream.json")))
cb = json.load(open(os.path.join(D, "cb5m.json")))
o_by_t = dict(zip(cb["t"], cb["o"])); c_by_t = dict(zip(cb["t"], cb["c"]))
gated = [s for s in stream if s["eff"] <= 0.48]
for s in gated:
    op, cl = o_by_t[s["t0"]], c_by_t[s["t0"]]
    s["tiny"] = 1 if abs(cl - op)/op < 0.0002 else 0
split_t = json.load(open(os.path.join(W, "stream_stats.json")))["split_t"]

def blocks_of(rows):
    blk = {}
    for s in rows: blk.setdefault(s["t0"]//3600, []).append(s)
    return [blk[k] for k in sorted(blk)]

def run_path(seq, mode, val, b0=1000.0):
    B, peak, maxdd = b0, b0, 0.0
    for (win, p) in seq:
        c = cost(p)
        stake = min(val, B) if mode == "flat" else val * B
        if stake <= 0 or B <= 1.0: stake = 0.0
        pnl = (stake/c - stake) if win else -stake
        B += pnl - (GAS if stake > 0 else 0)
        peak = max(peak, B)
        maxdd = max(maxdd, (peak-B)/peak)
    return B, maxdd

def bootstrap(rows, pfill, nboot=3000):
    blks = blocks_of(rows)
    out = {k: {"tw": [], "dd": []} for k in STRATS}
    for _ in range(nboot):
        seq = []
        for _ in range(len(blks)):
            for s in random.choice(blks):
                w = s["win"]
                if s["tiny"] and random.random() < 0.11: w = 1 - w
                seq.append((w, pfill))
        for k, (mode, val) in STRATS.items():
            twv, ddv = run_path(seq, mode, val)
            out[k]["tw"].append(twv); out[k]["dd"].append(ddv)
    res = {}
    for k in STRATS:
        tw = sorted(out[k]["tw"]); dd = sorted(out[k]["dd"]); n = len(tw)
        res[k] = {"tw_p5": tw[int(.05*n)], "tw_med": tw[n//2], "tw_p95": tw[int(.95*n)],
                  "dd_med": dd[n//2], "dd_p95": dd[int(.95*n)],
                  "p_below_500": sum(1 for x in tw if x < 500)/n,
                  "p_loss": sum(1 for x in tw if x < 1000)/n}
    return res

test_rows = [s for s in gated if s["t0"] >= split_t]
train_rows = [s for s in gated if s["t0"] < split_t]
results = {}
for pf in (0.51, 0.53):
    results[f"TEST_p{pf}"] = bootstrap(test_rows, pf)
    results[f"TRAIN_p{pf}"] = bootstrap(train_rows, pf)
json.dump(results, open(os.path.join(W, "kelly_sens_results.json"), "w"), indent=1)
for seg, r in results.items():
    print("\n==", seg)
    for k, v in r.items():
        print(f" {k:8s} med={v['tw_med']:9.0f} p5={v['tw_p5']:8.0f} p95={v['tw_p95']:9.0f} "
              f"ddMed={v['dd_med']:.2%} ddP95={v['dd_p95']:.2%} P(<500)={v['p_below_500']:.3f} P(loss)={v['p_loss']:.3f}")
