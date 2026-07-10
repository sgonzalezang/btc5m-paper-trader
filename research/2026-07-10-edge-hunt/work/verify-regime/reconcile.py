#!/usr/bin/env python3
"""Reconcile refetched conditional pricing with the live ledger, and decompose
the headline EV under honest fills."""
import json, math

S = "/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad"

# 1) finding's cited number: unconditional p20 median
pms = json.load(open(S + "/data/pm_prices_sample.json"))
p20 = sorted(m["p20"] for m in pms if m.get("p20") is not None)
print("unconditional p20 median (their cited 49.5c):", p20[len(p20)//2])

rows = json.load(open(S + "/work/verify-regime/trig_prices.json"))
tl = json.load(open(S + "/data/trades.json"))
revs = {x["t0"]: x for x in tl if x.get("eng") in ("reversal","reversal2")
        and x.get("status") == "settled"}

gated = [r for r in rows if r["gated"] and r["entry_up_mid"] is not None]
lo = min(x["t0"] for x in revs.values()); hi = max(x["t0"] for x in revs.values())
print(f"live ledger span: {lo}..{hi}; refetch span: {min(r['t0'] for r in rows)}..{max(r['t0'] for r in rows)}")

def fee(p): return 0.07*p*(1-p)
def wr_ev(sub, slipc):
    n = len(sub); w = 0; ev = 0.0; mp = 0.0
    for r in sub:
        buy_up = r["pm"] < 0
        cost = (r["entry_up_mid"] if buy_up else 1-r["entry_up_mid"]) + slipc
        win = (r["up_won"]==1) if buy_up else (r["up_won"]==0)
        w += win; ev += (1 if win else 0) - cost - fee(cost); mp += cost
    return n, w/n, ev/n*100, mp/n

# 2) split my gated sample into live-overlap vs pre-live
for tag, sub in [
    ("gated, in live span", [r for r in gated if lo <= r["t0"] <= hi]),
    ("gated, before live span", [r for r in gated if r["t0"] < lo]),
    ("gated, bot actually traded it", [r for r in gated if r["t0"] in revs]),
    ("gated, bot did NOT trade", [r for r in gated if lo <= r["t0"] <= hi and r["t0"] not in revs]),
]:
    if not sub: print(tag, "n=0"); continue
    n, wr, ev, mp = wr_ev(sub, 0.01)
    print(f"{tag}: n={n} wr={wr:.4f} meanfill={mp:.4f} EV@mid+1c={ev:+.2f} c/share")

# 3) for gated markets the bot traded: compare bot ask vs my pre-entry mid
diffs = []
for r in gated:
    x = revs.get(r["t0"])
    if not x or x.get("ask") is None: continue
    buy_up = r["pm"] < 0
    mid = r["entry_up_mid"] if buy_up else 1 - r["entry_up_mid"]
    # only comparable if bot bought the same side
    side_up = (x.get("side") == "UP") if x.get("side") else None
    diffs.append((x["ask"], mid, x["ask"] - mid, x.get("side"), "UP" if buy_up else "DOWN"))
same = [d for d in diffs if d[3] and d[3].upper().startswith(d[4][0])]
print(f"\nbot-vs-refetch matched gated markets: {len(diffs)}; same-side: {len(same)}")
if diffs:
    dd = sorted(d[2] for d in diffs)
    print(f"ask - preentry_mid: p10={dd[int(0.1*len(dd))]:.3f} p50={dd[len(dd)//2]:.3f} p90={dd[int(0.9*len(dd))]:.3f} mean={sum(dd)/len(dd):+.4f}")

# 4) headline decomposition at honest conditional fills
wr_test = 0.5676; se_wr = math.sqrt(wr_test*(1-wr_test)/717)
mids = []
for r in gated:
    buy_up = r["pm"] < 0
    mids.append(r["entry_up_mid"] if buy_up else 1-r["entry_up_mid"])
mp = sum(mids)/len(mids); sd = (sum((x-mp)**2 for x in mids)/(len(mids)-1))**0.5
for slip in (0.005, 0.01, 0.015, 0.02):
    p = mp + slip
    ev = wr_test - p - fee(p)
    print(f"decomposed EV: TESTwr 0.5676 - fill({p:.4f}) - fee = {ev*100:+.2f} c/share  (breakeven wr {p+fee(p):.4f})")
print(f"E[fill mid] = {mp:.4f} +- {sd/len(mids)**0.5:.4f}; wr SE {se_wr:.4f} -> EV SE ~{(se_wr**2 + (sd/len(mids)**0.5)**2)**0.5*100:.2f} c")

# 5) two-proportion test: informative-price effect (gated: cheap vs expensive)
import statistics
med = sorted(mids)[len(mids)//2]
loW = [ (r["up_won"]==1) if r["pm"]<0 else (r["up_won"]==0) for r,m in zip(gated,mids) if m <= med]
hiW = [ (r["up_won"]==1) if r["pm"]<0 else (r["up_won"]==0) for r,m in zip(gated,mids) if m > med]
p1, n1 = sum(loW)/len(loW), len(loW); p2, n2 = sum(hiW)/len(hiW), len(hiW)
pp = (sum(loW)+sum(hiW))/(n1+n2)
z = (p2-p1)/math.sqrt(pp*(1-pp)*(1/n1+1/n2))
print(f"\ninformative-price: cheap wr={p1:.3f}(n={n1}) vs expensive wr={p2:.3f}(n={n2}) z={z:.2f}")
