#!/usr/bin/env python3
"""(c) Drawdown control: daily loss caps and daily trade caps on the gated (latentfire)
flat-$50 stream, fixed fill p=0.51. EV-neutral-per-trade by prior finding #4 (optional
stopping), so any EV change comes purely from trades NOT taken; we quantify the
DD-reduction-vs-upside-cost tradeoff.

Bootstrap: resample whole DAYS with replacement (cap mechanics are daily; day unit
preserves intraday ordering). 4000 resamples. Headline on TEST days.
Metrics: mean/median terminal pnl ($1k bankroll ref), median & p95 max drawdown ($),
P(maxDD > $400), trades/day taken.
"""
import json, random, os
from collections import defaultdict

SCRATCH = "/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad"
W = os.path.join(SCRATCH, "work", "sizing")
random.seed(5)

P = 0.51
COST = P + 0.07 * P * (1 - P)
STAKE = 50.0
GAS = 0.004
WPNL = STAKE / COST - STAKE

stream = json.load(open(os.path.join(W, "stream.json")))
split_t = json.load(open(os.path.join(W, "stream_stats.json")))["split_t"]
gated = sorted([s for s in stream if s["eff"] <= 0.48], key=lambda s: s["t0"])

by_day = defaultdict(list)
for s in gated:
    by_day[s["t0"] // 86400].append(s["win"])
days_all = sorted(by_day)
days_test = [d for d in days_all if d * 86400 >= split_t]

CAPS = [("none", None, None), ("L200", 200, None), ("L150", 150, None), ("L100", 100, None),
        ("L50", 50, None), ("N30", None, 30), ("N15", None, 15), ("L150N30", 150, 30)]

def run_days(day_seqs, losscap, tradecap):
    total, peak, maxdd, ntr = 0.0, 0.0, 0.0, 0
    for wins in day_seqs:
        dpnl, k = 0.0, 0
        for w in wins:
            if losscap is not None and dpnl <= -losscap: break
            if tradecap is not None and k >= tradecap: break
            pnl = (WPNL if w else -STAKE) - GAS
            dpnl += pnl; k += 1
            total += pnl
            peak = max(peak, total)
            maxdd = max(maxdd, peak - total)
        ntr += k
    return total, maxdd, ntr

def bootstrap(days, nboot=4000):
    res = {name: {"tw": [], "dd": [], "nt": []} for name, _, _ in CAPS}
    seqs = [by_day[d] for d in days]
    for _ in range(nboot):
        sample = [random.choice(seqs) for _ in seqs]
        for name, L, N in CAPS:
            tw, dd, nt = run_days(sample, L, N)
            res[name]["tw"].append(tw); res[name]["dd"].append(dd); res[name]["nt"].append(nt)
    out = {}
    base_mean = sum(res["none"]["tw"]) / nboot
    base_dd = sorted(res["none"]["dd"])[nboot // 2]
    for name, L, N in CAPS:
        tw = sorted(res[name]["tw"]); dd = sorted(res[name]["dd"]); nt = res[name]["nt"]
        mean_tw = sum(tw) / nboot
        med_dd = dd[nboot // 2]
        out[name] = {"mean_pnl": mean_tw, "med_pnl": tw[nboot // 2], "p5_pnl": tw[int(.05 * nboot)],
                     "med_dd": med_dd, "p95_dd": dd[int(.95 * nboot)],
                     "P_dd_gt400": sum(1 for x in dd if x > 400) / nboot,
                     "trades_day": sum(nt) / nboot / len(days),
                     "ev_cost_pct": (1 - mean_tw / base_mean) * 100 if base_mean else None,
                     "dd_red_pct": (1 - med_dd / base_dd) * 100 if base_dd else None}
    return out

results = {"TEST": bootstrap(days_test), "FULL60": bootstrap(days_all)}
json.dump(results, open(os.path.join(W, "caps_results.json"), "w"), indent=1)
for seg in results:
    print("\n==", seg, f"({len(days_test) if seg=='TEST' else len(days_all)} days)")
    print(f" {'cap':8s} {'meanPnL':>8s} {'medPnL':>8s} {'p5PnL':>8s} {'medDD':>7s} {'p95DD':>7s} {'P(DD>400)':>9s} {'tr/day':>6s} {'EVcost%':>8s} {'DDred%':>7s}")
    for name, _, _ in CAPS:
        v = results[seg][name]
        print(f" {name:8s} {v['mean_pnl']:8.0f} {v['med_pnl']:8.0f} {v['p5_pnl']:8.0f} "
              f"{v['med_dd']:7.0f} {v['p95_dd']:7.0f} {v['P_dd_gt400']:9.3f} {v['trades_day']:6.1f} "
              f"{v['ev_cost_pct']:8.1f} {v['dd_red_pct']:7.1f}")
