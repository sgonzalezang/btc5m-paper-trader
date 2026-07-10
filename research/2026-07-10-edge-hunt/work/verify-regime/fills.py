#!/usr/bin/env python3
"""Adversarial fill-realism check for the isolated-impulse gate.

1) pm_prices_sample.json matched to cb5m: what does the REVERSAL side (opposite
   of the trigger move) cost ~20s into the interval, conditional on the trigger
   and on the gate? EV at honest fills using ACTUAL Polymarket resolutions.
2) Live ledger (trades.json, reversal/reversal2, current + prereset): empirical
   entry-price distribution, per-share realized pnl net of exact fees.
3) Breakeven fill price implied by the TEST gated wr.
"""
import json, math

S = "/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad"

d = json.load(open(S + "/data/cb5m.json"))
t, o, c = d["t"], d["o"], d["c"]
idx = {tt: i for i, tt in enumerate(t)}
THR = 0.0012

def feat(i):
    pm = (o[i]-o[i-1])/o[i-1]
    num = abs(o[i]-o[i-6]); den = sum(abs(o[j+1]-o[j]) for j in range(i-6, i))
    eff6 = num/den if den > 0 else 0.0
    cnt = sum(1 for j in range(i-13, i-1) if abs(o[j+1]-o[j])/o[j] >= THR)
    return pm, eff6, cnt

pms = json.load(open(S + "/data/pm_prices_sample.json"))
print("pm sample markets:", len(pms))

def q(xs, p):
    xs = sorted(xs); k = (len(xs)-1)*p
    f = int(k); return xs[f] + (xs[min(f+1, len(xs)-1)] - xs[f]) * (k - f)

def fee(p): return 0.07*p*(1-p)

rows = []
for m in pms:
    t0 = m["t0"]
    i = idx.get(t0)
    if i is None or i < 14: continue
    pm_, eff6, cnt = feat(i)
    if abs(pm_) < THR: continue
    gated = (eff6 >= 0.32 and cnt <= 6)
    buy_up = pm_ < 0                       # fade the move
    win = m["up_won"] == 1 if buy_up else m["up_won"] == 0
    r = {"t0": t0, "gated": gated, "buy_up": buy_up, "win": win}
    for k_ in ("p20", "p60", "p150"):
        v = m.get(k_)
        r[k_] = None if v is None else (v if buy_up else round(1-v, 4))
    # coinbase-proxy label for comparison
    r["win_cb"] = ((not (c[i] >= o[i])) if pm_ > 0 else (c[i] >= o[i]))
    rows.append(r)

print("triggered among sampled:", len(rows), " gated:", sum(r["gated"] for r in rows))

for tag, sub in [("ALL triggers", rows), ("GATED", [r for r in rows if r["gated"]])]:
    costs = [r["p20"] for r in sub if r["p20"] is not None]
    if not costs: continue
    wr_pm = sum(r["win"] for r in sub if r["p20"] is not None) / len(costs)
    n = len(costs)
    print(f"\n--- {tag}: n={n}")
    print(f"  reversal-side mid @~20s: p10={q(costs,.1):.3f} p50={q(costs,.5):.3f} "
          f"mean={sum(costs)/n:.3f} p90={q(costs,.9):.3f} frac>0.54={sum(1 for x in costs if x>0.54)/n:.2f}")
    print(f"  wr (actual PM resolution) = {wr_pm:.4f}  |  wr (coinbase proxy) = "
          f"{sum(r['win_cb'] for r in sub if r['p20'] is not None)/n:.4f}")
    # label agreement
    agree = sum(1 for r in sub if r["p20"] is not None and r["win"] == r["win_cb"])
    print(f"  label agreement PM vs CB proxy: {agree}/{n}")
    for slip in (0.01, 0.015, 0.02):
        evs = []
        for r in sub:
            if r["p20"] is None: continue
            p = min(r["p20"] + slip, 0.99)
            evs.append((1 if r["win"] else 0) - p - fee(p))
        print(f"  EV/share @ mid+{slip*100:.1f}c slip, ALL fills taken: "
              f"{sum(evs)/len(evs)*100:+.2f} c/share")
        # with the live engine's 55c entry cap (skip expensive)
        evs2 = []
        for r in sub:
            if r["p20"] is None: continue
            p = r["p20"] + slip
            if p > 0.55: continue
            evs2.append((1 if r["win"] else 0) - p - fee(p))
        if evs2:
            print(f"     with 55c cap: n={len(evs2)}  EV {sum(evs2)/len(evs2)*100:+.2f} c/share")

# ---------- live ledger ----------
tr = json.load(open(S + "/data/trades.json"))
if isinstance(tr, dict):
    print("\ntrades.json keys:", list(tr.keys())[:10])
    tl = tr.get("trades", tr)
else:
    tl = tr
print("\nledger rows:", len(tl), "sample keys:", sorted(tl[0].keys()))
