#!/usr/bin/env python3
"""Entry-cost & adverse-selection analysis on 215 triggered markets (3 days),
using last pre-entry (<= t0+15s) Up mid from CLOB prices-history and ACTUAL
Polymarket resolutions."""
import json

S = "/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad"
rows = json.load(open(S + "/work/verify-regime/trig_prices.json"))

def q(xs, p):
    xs = sorted(xs); k = (len(xs)-1)*p
    f = int(k); return xs[f] + (xs[min(f+1,len(xs)-1)]-xs[f])*(k-f)
def fee(p): return 0.07*p*(1-p)

have = [r for r in rows if r["entry_up_mid"] is not None]
ages = [r["entry_pt_age"] for r in have]
print(f"markets with pre-entry point: {len(have)}/{len(rows)}; point age p50={q(ages,.5):.0f}s p90={q(ages,.9):.0f}s")

for tag, sub in [("ALL triggers", have), ("GATED (A=0.32,B=6)", [r for r in have if r["gated"]])]:
    n = len(sub)
    costs = []
    wins = 0
    for r in sub:
        buy_up = r["pm"] < 0
        cost = r["entry_up_mid"] if buy_up else 1 - r["entry_up_mid"]
        win = (r["up_won"] == 1) if buy_up else (r["up_won"] == 0)
        costs.append((cost, win))
        wins += win
    cs = [c for c, _ in costs]
    print(f"\n=== {tag}: n={n}  wr(actual PM)={wins/n:.4f}")
    print(f"  reversal-side pre-entry mid: p10={q(cs,.1):.3f} p25={q(cs,.25):.3f} p50={q(cs,.5):.3f} mean={sum(cs)/n:.4f} p90={q(cs,.9):.3f}")
    print(f"  frac mid>0.53 (ask likely > 55c cap w/ spread+slip): {sum(1 for x in cs if x>0.53)/n:.3f}")
    for slip in (0.01, 0.02):
        ev = sum((1 if w else 0) - min(c+slip,0.99) - fee(min(c+slip,0.99)) for c, w in costs)/n
        print(f"  EV/share all-filled @ mid+{slip*100:.0f}c: {ev*100:+.2f} c")
    # deployable version: only fill if mid+slip <= 0.55 (engine cap)
    for slip in (0.01, 0.02):
        f2 = [(min(c+slip,0.99), w) for c, w in costs if c+slip <= 0.55]
        if f2:
            ev = sum((1 if w else 0) - p - fee(p) for p, w in f2)/len(f2)
            wr2 = sum(w for _, w in f2)/len(f2)
            print(f"  capped<=55c @ +{slip*100:.0f}c: n={len(f2)} ({len(f2)/n:.0%}) wr={wr2:.4f} EV={ev*100:+.2f} c")
    # adverse selection: cheap vs expensive reversal side
    med = q(cs, .5)
    lo = [(c, w) for c, w in costs if c <= med]; hi = [(c, w) for c, w in costs if c > med]
    print(f"  wr when reversal side cheap (mid<= {med:.3f}): {sum(w for _,w in lo)/len(lo):.4f} (n={len(lo)}) | expensive: {sum(w for _,w in hi)/len(hi):.4f} (n={len(hi)})")
    # flat 51c assumption for contrast
    ev51 = sum((1 if w else 0) for _, w in costs)/n - 0.51 - fee(0.51)
    print(f"  EV at flat 51c assumption: {ev51*100:+.2f} c")
