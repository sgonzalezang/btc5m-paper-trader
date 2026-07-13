import json
d="/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data/"
d10="/Users/sgonzalez/btc5m-paper-trader/research/2026-07-10-edge-hunt/data/"
cb=json.load(open(d+"cb1m.json"))
# columnar -> dict t->(o,c)
O={}; C={}
for t,o,c in zip(cb["t"],cb["o"],cb["c"]):
    O[int(t)]=float(o); C[int(t)]=float(c)
def strike(t0):
    if t0 in O: return O[t0]
    if (t0-60) in C: return C[t0-60]
    return None
pm=json.load(open(d10+"pm_res_3d.json"))
oracle={int(t0):int(up) for t0,up in pm}

# ---- Part A: verify the tie-rule / reference divergence at the SETTLE instant ----
# Our displayed outcome via Coinbase: up iff settle(=strike(t0+300)) - strike(t0) > 0 (strict, matching verdictOf/provisional gap>0)
# Polymarket oracle: ground truth (chainlink, >= tie -> up)
n=0; agree=0; disagree=[]; ties=0; tie_disagree=0
buckets={}  # bps bucket -> [n, disagree]
def bkey(bps):
    for hi in (1,2,5,10,20,50):
        if bps<hi: return f"<{hi}"
    return ">=50"
rows=[]
for t0,up in oracle.items():
    s0=strike(t0); s1=strike(t0+300)
    if s0 is None or s1 is None: continue
    d=s1-s0
    bps=abs(d)/s0*10000.0
    our_up = 1 if d>0 else 0   # strict > (our tie rule); d==0 -> down
    n+=1
    ag = (our_up==up)
    if ag: agree+=1
    else: disagree.append((t0,d,bps,up,our_up))
    if d==0:
        ties+=1
        if up!=our_up: tie_disagree+=1
    bk=bkey(bps)
    b=buckets.setdefault(bk,[0,0]); b[0]+=1
    if not ag: b[1]+=1
    rows.append((t0,d,bps,up,our_up,ag))

print("=== Coinbase-derived displayed outcome vs Polymarket oracle (settle instant) ===")
print(f"n={n} agree={agree} ({100*agree/n:.2f}%) disagree={len(disagree)} ({100*len(disagree)/n:.2f}%)")
print(f"exact Coinbase ties (d==0): {ties}, of which oracle-disagree: {tie_disagree}")
print("\nby |move| bucket (bps): bucket  n  disagree  disagree%")
order=["<1","<2","<5","<10","<20","<50",">=50"]
for k in order:
    if k in buckets:
        nn,dd=buckets[k]; print(f"  {k:>5}  {nn:5d}  {dd:5d}  {100*dd/nn:6.2f}%")

# within-clearMargin slice (the band where the live-leader is UNGUARDED but settle DEFERS)
inband=[r for r in rows if abs(r[1])<max(15.0, r[0+0] and 0)]  # placeholder
# proper: clearMargin uses strike price
def cm(px): return max(15.0, px*0.0003)
inb_n=inb_dis=0; out_n=out_dis=0
for t0,dd,bps,up,ou,ag in rows:
    s0=strike(t0)
    if abs(dd)<cm(s0):
        inb_n+=1;  inb_dis+= (0 if ag else 1)
    else:
        out_n+=1;  out_dis+= (0 if ag else 1)
print(f"\nInside clearMargin band (|move|<~$19; live-leader shows a call, settle DEFERS to oracle):")
print(f"  n={inb_n} displayed-leader-wrong={inb_dis} ({100*inb_dis/inb_n:.2f}%)")
print(f"Outside band (settle would provisionally book):")
print(f"  n={out_n} displayed-leader-wrong={out_dis} ({100*out_dis/out_n:.2f}%)" if out_n else "  n=0")

# ---- Part B: does the provisional-settle path EVER fire at a Coinbase tie (gap==0)? ----
tu=json.load(open(d+"trades_unified.json"))
prov=[t for t in tu if t.get("settledBy","").startswith("feed")]
prov_tie=[t for t in tu if t.get("btcOpen")==t.get("btcClose") and str(t.get("settledBy","")).startswith("feed")]
booked_tie=[t for t in tu if t.get("btcOpen") is not None and t.get("btcOpen")==t.get("btcClose")]
print(f"\n=== Provisional booking tie exposure ===")
print(f"trades total={len(tu)}  ever provisional(feed*)={len([t for t in tu if str(t.get('settledBy','')).startswith('feed')])}")
print(f"trades with btcOpen==btcClose (Coinbase tie): {len(booked_tie)}")
for t in booked_tie:
    print(f"  t0={t['t0']} eng={t.get('eng')} settledBy={t.get('settledBy')} result={t.get('result')} gap={ (t['btcClose']-t['btcOpen']) if t.get('btcClose') is not None else None}")

import collections
from collections import Counter
print("\nsettledBy distribution:", dict(Counter(t.get('settledBy') for t in tu)))

json.dump({
  "n":n,"agree":agree,"agree_pct":round(100*agree/n,3),"disagree":len(disagree),
  "disagree_pct":round(100*len(disagree)/n,3),
  "coinbase_exact_ties":ties,"tie_oracle_disagree":tie_disagree,
  "buckets_bps":{k:{"n":buckets[k][0],"disagree":buckets[k][1]} for k in order if k in buckets},
  "inband":{"n":inb_n,"disagree":inb_dis},"outband":{"n":out_n,"disagree":out_dis},
  "coinbase_tie_trades":len(booked_tie),
}, open("../results.json","w"), indent=2)
print("\nwrote ../results.json")
