#!/usr/bin/env python3
"""Independent re-derivation of Coinbase-vs-Chainlink-oracle divergence.
Two mirrors of the display's Up/Down:
  M1 (source's): open@t0 vs open@t0+300  (next-window open = terminal)
  M2 (alt):      open@t0 vs close@t0+240 (last in-window 1m candle close)
Ground truth = pm_res_3d oracle (Chainlink >= rule). STDLIB only."""
import json, statistics as st

cb=json.load(open("/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data/cb1m.json"))
O={t:o for t,o in zip(cb["t"],cb["o"])}
C={t:c for t,c in zip(cb["t"],cb["c"])}
res=json.load(open("/Users/sgonzalez/btc5m-paper-trader/research/2026-07-10-edge-hunt/data/pm_res_3d.json"))

def strikeOf(t0):
    if O.get(t0) is not None: return O[t0]
    if C.get(t0-60) is not None: return C[t0-60]
    return None
def clearMargin(px): return max(15.0, px*0.0003)

def run(settle_fn,label):
    rows=[]
    for t0,up in res:
        s=strikeOf(t0); e=settle_fn(t0)
        if s is None or e is None: continue
        d=e-s; bps=abs(d)/s*1e4
        rows.append((t0,bool(up),s,d,bps,abs(d)<clearMargin(s), d>0, d>=0))
    n=len(rows)
    naive=sum(1 for r in rows if r[6]==r[1])          # d>0 tie->down
    naive_ge=sum(1 for r in rows if r[7]==r[1])        # d>=0 tie->up (matches PM convention)
    hard=[r for r in rows if not r[5]]
    hard_ok=sum(1 for r in hard if r[6]==r[1])
    deferred=[r for r in rows if r[5]]
    def_wrong=sum(1 for r in deferred if r[6]!=r[1])
    tot_dis=n-naive
    sub2=sum(1 for r in rows if r[4]<2 and r[6]!=r[1])
    sub3=sum(1 for r in rows if r[4]<3 and r[6]!=r[1])
    buckets=[(0,1),(1,2),(2,3),(3,5),(5,8),(8,12),(12,20),(20,1e9)]
    bk={}
    for lo,hi in buckets:
        b=[r for r in rows if lo<=r[4]<hi]
        if not b: continue
        bk[f"[{lo},{hi})"]={"n":len(b),"disagree":sum(1 for r in b if r[6]!=r[1]),
                            "rate_pct":round(100*sum(1 for r in b if r[6]!=r[1])/len(b),1)}
    return {"label":label,"n":n,
            "naive_d>0_agree_pct":round(100*naive/n,2),"naive_disagree_n":tot_dis,
            "naive_d>=0_agree_pct":round(100*naive_ge/n,2),
            "hard_n":len(hard),"hard_agree_pct":round(100*hard_ok/len(hard),2),"hard_disagree_n":len(hard)-hard_ok,
            "deferred_n":len(deferred),"deferred_pct":round(100*len(deferred)/n,1),"deferred_naive_wrong":def_wrong,
            "sub2bps_share_of_disagree_pct":round(100*sub2/max(1,tot_dis),0),
            "sub3bps_share_of_disagree_pct":round(100*sub3/max(1,tot_dis),0),
            "by_bps":bk}

m1=run(lambda t0: strikeOf(t0+300),"M1 open@t0 vs open@t0+300 (source method)")
m2=run(lambda t0: C.get(t0+240),   "M2 open@t0 vs close@t0+240 (in-window)")
out={"M1":m1,"M2":m2}
print(json.dumps(out,indent=2))
json.dump(out,open("/Users/sgonzalez/btc5m-paper-trader/research/2026-07-13-price-to-beat/work/verify/divergence_recomputed.json","w"),indent=2)
