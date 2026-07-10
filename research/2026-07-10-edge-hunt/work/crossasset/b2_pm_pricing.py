"""(b2) Does the Polymarket book already price pre-t0 momentum at 20s in?
Match pm_prices_sample (216 markets, ~3d) with the last-minute cb1m signal;
report the cost of the momentum-side token at p20 and net EV at observed hold rates."""
import sys, json
sys.path.insert(0, "/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad/work/crossasset")
from util import *

cb5 = load("cb5m"); cb1 = load("cb1m"); pm = load("pm_prices_sample")
o1 = dict(zip(cb1["t"], cb1["o"]))
out5 = {t: (1 if c >= o else 0) for t, o, c in zip(cb5["t"], cb5["o"], cb5["c"])}

rows = []
for m in pm:
    t0 = m["t0"]
    if t0 not in o1 or (t0 - 60) not in o1: continue
    r = (o1[t0] - o1[t0 - 60]) / o1[t0 - 60] * 1e4
    rows.append((t0, r, m["up_won"], m["p20"], m.get("p60")))
print(f"matched pm markets with signal: {len(rows)} of {len(pm)}")

res = {}
for lo in (1, 2, 4):
    sel = [x for x in rows if abs(x[1]) >= lo]
    if not sel: continue
    # cost of the momentum-side token at 20s: Up token price if up-momentum, else 1 - p20
    costs = [x[3] if x[1] > 0 else 1 - x[3] for x in sel]
    hits = [1 if (x[2] == 1) == (x[1] > 0) else 0 for x in sel]
    q = sum(hits) / len(hits)
    med = pct(costs, 0.5)
    fill = med + 0.01  # ask+1c slip per cost model
    print(f"|r|>={lo}bps: n={len(sel)} holdRate={q:.3f} medCost(p20)={med:.3f} "
          f"fill={fill:.3f} q*={qstar(fill):.3f} netEV/share={ev(q, fill):+.4f}")
    res[f"ge{lo}"] = dict(n=len(sel), hold=q, med_cost=med, fill=fill, qstar=qstar(fill), ev=ev(q, fill))
    # quartiles of cost to show dispersion
    print(f"   cost quartiles: {pct(costs,0.25):.3f}/{pct(costs,0.5):.3f}/{pct(costs,0.75):.3f}")

# how much of the signal is priced: mean momentum-side cost vs 0.5
allc = [x[3] if x[1] > 0 else 1 - x[3] for x in rows if abs(x[1]) >= 1]
print(f"\nmean momentum-side cost at 20s (|r|>=1bps): {sum(allc)/len(allc):.4f} (0.500 = unpriced)")
json.dump(res, open("/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad/work/crossasset/b2_pm_pricing_results.json", "w"), indent=1)
print("saved b2_pm_pricing_results.json")
