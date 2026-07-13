"""Drill into the dedup attenuation: is the pooled 50-53c negativity an artifact of
multi-engine piling into the same losing intervals? And what do the deployment-relevant
per-engine ledgers say? stdlib only."""
import json, math, random, os
random.seed(7)
DATA="/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data"
OUT=os.path.dirname(os.path.abspath(__file__))
FEE=0.07; V3_CUT=1783698300
REV={"reversal","reversal2","reversal_v2","latentfire","impulse_v2","impulse50"}

def qstar(p): return p+FEE*p*(1-p)
S=[t for t in json.load(open(os.path.join(DATA,"trades_unified.json")))
   if t.get("status")=="settled" and t.get("result") in ("win","loss")]
for t in S:
    t["w"]=1 if t["result"]=="win" else 0
    t["ev"]=t["w"]-t["entry"]-FEE*t["entry"]*(1-t["entry"])

z=[t for t in S if 0.50<=t["entry"]<0.53]
R={}

# cluster by (t0, side): within-cluster mean ev, then across clusters
cl={}
for t in z: cl.setdefault((t["t0"],t["side"]),[]).append(t)
groups=list(cl.values())
gev=[sum(t["ev"] for t in g)/len(g) for g in groups]
gq=[sum(t["w"] for t in g)/len(g) for g in groups]
R["cluster_t0side"]={"n_clusters":len(groups),
    "ev_c_unweighted":round(100*sum(gev)/len(gev),2),
    "q_unweighted":round(sum(gq)/len(gq),4),
    "mean_cluster_size":round(len(z)/len(groups),2)}

# block boot on cluster means (1h blocks)
bl={}
for g,e in zip(groups,gev): bl.setdefault(g[0]["t0"]//3600,[]).append(e)
blocks=list(bl.values()); NB=20000; means=[]
for _ in range(NB):
    s=[x for _ in range(len(blocks)) for x in random.choice(blocks)]
    means.append(sum(s)/len(s))
means.sort()
R["cluster_t0side_boot"]={"ci95_c":[round(100*means[int(.025*NB)],2),round(100*means[int(.975*NB)-1],2)],
    "p_ge0":round(sum(1 for m in means if m>=0)/NB,4)}

# cluster size vs outcome: do piled-on intervals lose more?
by_size={}
for g in groups:
    k=min(len(g),5)
    by_size.setdefault(k,[]).append(sum(t["w"] for t in g)/len(g))
R["q_by_cluster_size"]={k:{"n":len(v),"q":round(sum(v)/len(v),4)} for k,v in sorted(by_size.items())}

# era composition of clusters vs trades
pre=[t for t in z if t["t0"]<V3_CUT]; v3=[t for t in z if t["t0"]>=V3_CUT]
R["era_trades"]={"pre":{"n":len(pre),"q":round(sum(t['w'] for t in pre)/len(pre),4)},
                 "v3":{"n":len(v3),"q":round(sum(t['w'] for t in v3)/len(v3),4)}}
for lab,sub in [("pre",pre),("v3",v3)]:
    c={}
    for t in sub: c.setdefault((t["t0"],t["side"]),[]).append(t)
    gs=[sum(t["w"] for t in g)/len(g) for g in c.values()]
    R["era_clusters_"+lab]={"n":len(gs),"q":round(sum(gs)/len(gs),4),
                            "mean_size":round(len(sub)/len(gs),2)}

# deployment-relevant per-engine 50-53c ledgers (one trade per interval per engine)
R["per_engine_50_53"]={}
engs={}
for t in z: engs.setdefault(t["eng"],[]).append(t)
for e,ts in sorted(engs.items(),key=lambda kv:-len(kv[1])):
    n=len(ts); w=sum(t["w"] for t in ts); pm=sum(t["entry"] for t in ts)/n
    R["per_engine_50_53"][e]={"n":n,"q":round(w/n,4),"ev_c":round(100*(w/n-qstar(pm)),2)}

# rev-family trigger engines only (the actual action targets): reversal_v2 + impulse50 + impulse_v2, v3 era
tgt=[t for t in z if t["eng"] in ("reversal_v2","impulse50","impulse_v2")]
n=len(tgt); w=sum(t["w"] for t in tgt)
if n: R["v3_action_targets_50_53"]={"n":n,"q":round(w/n,4),
        "ev_c":round(100*(w/n-qstar(sum(t['entry'] for t in tgt)/n)),2)}

# fair per-bucket adverse-selection scan (q vs ask-implied entry-0.01), cluster level,
# for Bonferroni: which buckets show significant adverse selection?
scan=[]
for l in range(35,75,5):
    lo,hi=l/100,(l+5)/100
    b=[t for t in S if lo<=t["entry"]<hi]
    c={}
    for t in b: c.setdefault((t["t0"],t["side"]),[]).append(t)
    ga=[sum(t["w"]-(t["entry"]-0.01) for t in g)/len(g) for g in c.values()]
    if len(ga)<30: continue
    m=sum(ga)/len(ga); sd=math.sqrt(sum((x-m)**2 for x in ga)/(len(ga)-1))
    zv=m/(sd/math.sqrt(len(ga)))
    p=0.5*(1+math.erf(zv/math.sqrt(2)))  # lower tail
    scan.append({"bucket":f"{l}-{l+5}","n_cl":len(ga),"adv_c":round(100*m,2),
                 "p_lowtail":round(p,4)})
R["adv_scan_clusters"]=scan

json.dump(R,open(os.path.join(OUT,"dedup_results.json"),"w"),indent=1)
print(json.dumps(R,indent=1))
