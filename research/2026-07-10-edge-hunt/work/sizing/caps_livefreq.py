#!/usr/bin/env python3
"""(c) addendum: caps at LIVE latentfire cadence (~5 trades/day -> thin stream to 10%),
plus 1-hour-block bootstrap of TEST gated win rate vs fee hurdle q*(0.51)=0.5275."""
import json, random, os
from collections import defaultdict

SCRATCH = "/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad"
W = os.path.join(SCRATCH, "work", "sizing")
random.seed(9)

P = 0.51; COST = P + 0.07 * P * (1 - P); STAKE = 50.0; GAS = 0.004
WPNL = STAKE / COST - STAKE

stream = json.load(open(os.path.join(W, "stream.json")))
split_t = json.load(open(os.path.join(W, "stream_stats.json")))["split_t"]
gated = sorted([s for s in stream if s["eff"] <= 0.48], key=lambda s: s["t0"])
test = [s for s in gated if s["t0"] >= split_t]

# --- block bootstrap of TEST gated win rate (1h blocks) ---
blk = defaultdict(list)
for s in test: blk[s["t0"] // 3600].append(s["win"])
blocks = [blk[k] for k in sorted(blk)]
NB = 10000
q_hat = sum(s["win"] for s in test) / len(test)
lows = 0; qs = []
for _ in range(NB):
    w = [];
    for _ in range(len(blocks)): w.extend(random.choice(blocks))
    q = sum(w) / len(w); qs.append(q)
    if q <= 0.5275: lows += 1
qs.sort()
print(f"TEST gated q={q_hat:.4f} n={len(test)}  bootCI95=[{qs[int(.025*NB)]:.4f},{qs[int(.975*NB)]:.4f}]  P(q<=q*0.5275)={lows/NB:.4f}")

# --- caps at live cadence ---
thin = [s for s in test if random.random() < 0.104]   # ~5.2/day
by_day = defaultdict(list)
for s in thin: by_day[s["t0"] // 86400].append(s["win"])
days = sorted(by_day)
print("thinned TEST trades:", len(thin), "days:", len(days), "tr/day:", round(len(thin)/len(days), 1))

CAPS = [("none", None, None), ("L150", 150, None), ("L100", 100, None), ("L50", 50, None),
        ("N6", None, 6), ("N3", None, 3)]

def run_days(day_seqs, L, N):
    total, peak, maxdd, ntr = 0.0, 0.0, 0.0, 0
    for wins in day_seqs:
        dpnl, k = 0.0, 0
        for w in wins:
            if L is not None and dpnl <= -L: break
            if N is not None and k >= N: break
            pnl = (WPNL if w else -STAKE) - GAS
            dpnl += pnl; k += 1; total += pnl
            peak = max(peak, total); maxdd = max(maxdd, peak - total)
        ntr += k
    return total, maxdd, ntr

res = {}
seqs = [by_day[d] for d in days]
NBOOT = 4000
acc = {n: {"tw": [], "dd": [], "nt": []} for n, _, _ in CAPS}
for _ in range(NBOOT):
    sample = [random.choice(seqs) for _ in seqs]
    for n, L, N in CAPS:
        tw, dd, nt = run_days(sample, L, N)
        acc[n]["tw"].append(tw); acc[n]["dd"].append(dd); acc[n]["nt"].append(nt)
base_mean = sum(acc["none"]["tw"]) / NBOOT
base_dd = sorted(acc["none"]["dd"])[NBOOT // 2]
print(f"\n {'cap':6s} {'meanPnL':>8s} {'medPnL':>7s} {'p5PnL':>7s} {'medDD':>6s} {'p95DD':>6s} {'tr/day':>6s} {'EVcost%':>8s} {'DDred%':>7s}")
for n, L, N in CAPS:
    tw = sorted(acc[n]["tw"]); dd = sorted(acc[n]["dd"])
    v = {"mean": sum(tw)/NBOOT, "med": tw[NBOOT//2], "p5": tw[int(.05*NBOOT)],
         "medDD": dd[NBOOT//2], "p95DD": dd[int(.95*NBOOT)],
         "trd": sum(acc[n]["nt"])/NBOOT/len(days)}
    ev_cost = (1 - v["mean"]/base_mean)*100
    dd_red = (1 - v["medDD"]/base_dd)*100
    res[n] = dict(v, ev_cost=ev_cost, dd_red=dd_red)
    print(f" {n:6s} {v['mean']:8.0f} {v['med']:7.0f} {v['p5']:7.0f} {v['medDD']:6.0f} {v['p95DD']:6.0f} {v['trd']:6.1f} {ev_cost:8.1f} {dd_red:7.1f}")
json.dump({"boot_q": {"q": q_hat, "n": len(test), "p_below_hurdle": lows/NB,
                      "ci95": [qs[int(.025*NB)], qs[int(.975*NB)]]},
           "caps_livefreq": res}, open(os.path.join(W, "caps_livefreq_results.json"), "w"), indent=1)
