#!/usr/bin/env python3
"""(c) live-cadence caps, corrected: thin the stream to ~5-6 trades/day INSIDE each
bootstrap rep (not a single unlucky draw). Day-block resampling, TEST segment."""
import json, random, os
from collections import defaultdict

SCRATCH = "/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad"
W = os.path.join(SCRATCH, "work", "sizing")
random.seed(17)

P = 0.51; COST = P + 0.07 * P * (1 - P); STAKE = 50.0; GAS = 0.004
WPNL = STAKE / COST - STAKE
THIN = 0.104

stream = json.load(open(os.path.join(W, "stream.json")))
split_t = json.load(open(os.path.join(W, "stream_stats.json")))["split_t"]
gated = sorted([s for s in stream if s["eff"] <= 0.48], key=lambda s: s["t0"])
test = [s for s in gated if s["t0"] >= split_t]
by_day = defaultdict(list)
for s in test: by_day[s["t0"] // 86400].append(s["win"])
seqs = [by_day[d] for d in sorted(by_day)]

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

NBOOT = 6000
acc = {n: {"tw": [], "dd": [], "nt": []} for n, _, _ in CAPS}
for _ in range(NBOOT):
    sample = [[w for w in random.choice(seqs) if random.random() < THIN] for _ in seqs]
    for n, L, N in CAPS:
        tw, dd, nt = run_days(sample, L, N)
        acc[n]["tw"].append(tw); acc[n]["dd"].append(dd); acc[n]["nt"].append(nt)
base_mean = sum(acc["none"]["tw"]) / NBOOT
base_dd = sorted(acc["none"]["dd"])[NBOOT // 2]
res = {}
print(f" base mean pnl (no cap): {base_mean:.0f} over {len(seqs)} days")
print(f" {'cap':6s} {'meanPnL':>8s} {'medPnL':>7s} {'p5PnL':>7s} {'medDD':>6s} {'p95DD':>6s} {'tr/day':>6s} {'EVcost%':>8s} {'DDred%':>7s}")
for n, L, N in CAPS:
    tw = sorted(acc[n]["tw"]); dd = sorted(acc[n]["dd"])
    v = {"mean": sum(tw)/NBOOT, "med": tw[NBOOT//2], "p5": tw[int(.05*NBOOT)],
         "medDD": dd[NBOOT//2], "p95DD": dd[int(.95*NBOOT)],
         "trd": sum(acc[n]["nt"])/NBOOT/len(seqs)}
    ev_cost = (1 - v["mean"]/base_mean)*100
    dd_red = (1 - v["medDD"]/base_dd)*100
    res[n] = dict(v, ev_cost=ev_cost, dd_red=dd_red)
    print(f" {n:6s} {v['mean']:8.0f} {v['med']:7.0f} {v['p5']:7.0f} {v['medDD']:6.0f} {v['p95DD']:6.0f} {v['trd']:6.1f} {ev_cost:8.1f} {dd_red:7.1f}")
json.dump(res, open(os.path.join(W, "caps_livefreq2_results.json"), "w"), indent=1)
