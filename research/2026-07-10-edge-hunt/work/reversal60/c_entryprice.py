#!/usr/bin/env python3
"""(c) Entry-price realism: join pm_prices_sample (216 markets, ~3d) to cb5m prior
moves. After |prior move|>=thr, what does the CONTRARIAN side cost at p20/p60/p150?
Also EV at actual costs and an entry-price sensitivity curve 0.48-0.58.
Output: c_entryprice.json"""
import json, statistics as st

S = "/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad"
d = json.load(open(f"{S}/data/cb5m.json"))
t, o, c = d["t"], d["o"], d["c"]
tix = {tt: i for i, tt in enumerate(t)}
pm = json.load(open(f"{S}/data/pm_prices_sample.json"))

def fee(p): return 0.07*p*(1-p)

rows = []
agree = tot_res = 0
for m in pm:
    i = tix.get(m["t0"])
    if i is None or i == 0: continue
    mvbps = (o[i]-o[i-1])/o[i-1]*1e4
    cb_up = 1 if c[i] >= o[i] else 0
    tot_res += 1; agree += (cb_up == m["up_won"])
    rows.append(dict(t0=m["t0"], mv=mvbps, up_won=m["up_won"], cb_up=cb_up,
                     p20=m["p20"], p60=m["p60"], p150=m["p150"]))
print(f"matched {len(rows)}/{len(pm)} markets to cb5m; cb-vs-PM resolution agreement "
      f"{agree}/{tot_res} = {agree/tot_res:.3f}")

def q(xs, f):
    xs = sorted(xs); n=len(xs); return xs[min(n-1,int(f*n))]

out = {"n_matched": len(rows), "resolution_agreement": agree/tot_res}
for thr in [12, 20]:
    sig = [r for r in rows if abs(r["mv"]) >= thr]
    res = {"n": len(sig)}
    print(f"\n== |prior move| >= {thr}bps: n={len(sig)} signal markets in sample ==")
    for snap in ["p20", "p60", "p150"]:
        costs, wins, evs_raw, evs_slip = [], [], [], []
        for r in sig:
            pup = r[snap]
            if pup is None: continue
            cost = (1-pup) if r["mv"] > 0 else pup     # contrarian side price
            win = (1-r["up_won"]) if r["mv"] > 0 else r["up_won"]
            costs.append(cost); wins.append(win)
            evs_raw.append(win - cost - fee(cost))
            ps = min(0.99, cost+0.01)                   # ask+1c slip convention
            evs_slip.append(win - ps - fee(ps))
        n = len(costs)
        med = st.median(costs); mean = st.mean(costs)
        res[snap] = dict(n=n, cost_mean=mean, cost_med=med,
                         cost_q25=q(costs,0.25), cost_q75=q(costs,0.75),
                         frac_le_51=sum(1 for x in costs if x <= 0.51)/n,
                         frac_le_55=sum(1 for x in costs if x <= 0.55)/n,
                         win_rate=st.mean(wins),
                         ev_raw=st.mean(evs_raw), ev_slip1c=st.mean(evs_slip))
        print(f"{snap:>5}: cost mean={mean:.3f} med={med:.3f} IQR[{q(costs,0.25):.3f},"
              f"{q(costs,0.75):.3f}] P(cost<=0.51)={res[snap]['frac_le_51']:.2f} "
              f"P(<=0.55)={res[snap]['frac_le_55']:.2f} | win={st.mean(wins):.3f} "
              f"EV_raw={st.mean(evs_raw):+.4f} EV_+1c={st.mean(evs_slip):+.4f} (n={n})")
    out[f"thr{thr}"] = res

# sensitivity curve: EV(p) = q - p - fee(p) for TEST q at 12 and 20 bps
a = json.load(open(f"{S}/work/reversal60/a_stability.json"))
qs = {r["thr"]: r["q_test"] for r in a["thresholds"]}
curve = []
print("\n== EV per share vs entry price (q_TEST: 12bps=%.4f, 20bps=%.4f) ==" % (qs[12], qs[20]))
for cents in range(48, 59):
    p = cents/100
    ev12 = qs[12] - p - fee(p); ev20 = qs[20] - p - fee(p)
    curve.append(dict(p=p, ev12=ev12, ev20=ev20))
    print(f"p={p:.2f}: EV(12bps)={ev12:+.4f}  EV(20bps)={ev20:+.4f}")
out["sensitivity"] = curve
json.dump(out, open(f"{S}/work/reversal60/c_entryprice.json","w"), indent=1)
print("saved c_entryprice.json")
