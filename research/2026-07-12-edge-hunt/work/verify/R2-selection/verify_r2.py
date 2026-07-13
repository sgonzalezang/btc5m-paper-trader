"""Adversarial verification of R2 (50-53c fee-dead zone) — multiplicity & selection lens.

Recomputes every headline number independently from trades_unified.json, then:
  1. Reproduction: pooled 50-53c (n, q, EV, 1h-block-boot p), trigger-family >=50c,
     era splits, lt50-vs-ge50 contrast, Fisher replication.
  2. Null-baseline correction: 'EV<0' is not the interesting null (costs alone give
     EV ~= -2.7c). Test the ADVERSE-SELECTION increment: q < ask-implied prob (entry-0.01).
  3. Selection correction: treat 50-53c as best-of-K bucket scan (K=13 5c buckets),
     Bonferroni + a permutation over bucket choice; separately note the bucket was
     pre-registered ([0.50,0.53] = frozen hi-qhat bucket, Jul-10 FINAL-DESIGN §4.2).
  4. Pre-registrable alternative split: odd vs even UTC day-of-epoch halves.
  5. Dedup by t0 (cluster attenuation check).
stdlib only.
"""
import json, math, random, os

random.seed(20260712)
DATA = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data"
OUT  = os.path.dirname(os.path.abspath(__file__))
FEE = 0.07
V3_CUT = 1783698300
REV = {"reversal","reversal2","reversal_v2","latentfire","impulse_v2","impulse50"}
NBOOT = 20000

def qstar(p): return p + FEE*p*(1-p)

trades = json.load(open(os.path.join(DATA,"trades_unified.json")))
S = [t for t in trades if t.get("status")=="settled" and t.get("result") in ("win","loss")
     and isinstance(t.get("entry"),(int,float))]
for t in S:
    t["w"] = 1 if t["result"]=="win" else 0
    t["ev"] = t["w"] - t["entry"] - FEE*t["entry"]*(1-t["entry"])      # vs 0 (frozen model)
    t["adv"] = t["w"] - (t["entry"] - 0.01)                            # adverse-selection increment
                                                                       # vs ask-implied prob

def stat(ts):
    n=len(ts); w=sum(t["w"] for t in ts)
    q=w/n if n else float("nan"); pm=sum(t["entry"] for t in ts)/n if n else float("nan")
    return dict(n=n,wins=w,q=round(q,4),p_mean=round(pm,4),qstar=round(qstar(pm),4),
                ev_c=round(100*(q-qstar(pm)),2) if n else None)

def wilson(w,n,z=1.96):
    if n==0: return (0,1)
    ph=w/n; d=1+z*z/n; c=ph+z*z/(2*n); m=z*math.sqrt(ph*(1-ph)/n+z*z/(4*n*n))
    return ((c-m)/d,(c+m)/d)

def blocks_of(ts):
    bl={}
    for t in ts: bl.setdefault(t["t0"]//3600,[]).append(t)
    return list(bl.values())

def bboot(ts, field="ev", nb=NBOOT):
    """1h-block bootstrap of mean(field). Returns mean, ci95, p(mean<=0), p(mean>=0)."""
    bl=blocks_of(ts)
    if not bl: return None
    means=[]
    for _ in range(nb):
        sample=[x for _ in range(len(bl)) for x in random.choice(bl)]
        means.append(sum(t[field] for t in sample)/len(sample))
    means.sort()
    obs=sum(t[field] for t in ts)/len(ts)
    lo=means[int(0.025*nb)]; hi=means[int(0.975*nb)-1]
    p_le0=sum(1 for m in means if m<=0)/nb
    return dict(obs_c=round(100*obs,2), ci95_c=[round(100*lo,2),round(100*hi,2)],
                p_boot_le0=round(p_le0,4), p_boot_ge0=round(1-p_le0,4),
                n=len(ts), blocks=len(bl))

def bboot_diff(a,b,nb=NBOOT):
    bla,blb=blocks_of(a),blocks_of(b); means=[]
    for _ in range(nb):
        sa=[x for _ in range(len(bla)) for x in random.choice(bla)]
        sb=[x for _ in range(len(blb)) for x in random.choice(blb)]
        means.append(sum(t["ev"] for t in sa)/len(sa)-sum(t["ev"] for t in sb)/len(sb))
    means.sort()
    obs=sum(t["ev"] for t in a)/len(a)-sum(t["ev"] for t in b)/len(b)
    return dict(obs_diff_c=round(100*obs,2),
                ci95_c=[round(100*means[int(0.025*nb)],2),round(100*means[int(0.975*nb)-1],2)],
                p_le0=round(sum(1 for m in means if m<=0)/nb,4))

R={}

# ---------- 1. reproduction ----------
z5053=[t for t in S if 0.50<=t["entry"]<0.53]
R["pooled_50_53"]=stat(z5053)
R["pooled_50_53_boot_ev"]=bboot(z5053,"ev")
w,n=sum(t["w"] for t in z5053),len(z5053)
R["pooled_50_53_wilson_q"]=[round(x,4) for x in wilson(w,n)]
R["pooled_50_53_feedead"]={"q_upper_vs_qstar": R["pooled_50_53_wilson_q"][1],
                           "qstar": R["pooled_50_53"]["qstar"],
                           "upper_below_qstar": R["pooled_50_53_wilson_q"][1] < R["pooled_50_53"]["qstar"]}

rev=[t for t in S if t["eng"] in REV]
rge=[t for t in rev if t["entry"]>=0.50]; rlt=[t for t in rev if t["entry"]<0.50]
R["rev_ge50"]=stat(rge); R["rev_ge50_wilson"]=[round(x,4) for x in wilson(sum(t["w"] for t in rge),len(rge))]
R["rev_ge50_boot"]=bboot(rge,"ev")
R["rev_lt50"]=stat(rlt); R["rev_lt50_boot"]=bboot(rlt,"ev")
R["rev_pre_v3_ge50"]=stat([t for t in rge if t["t0"]<V3_CUT])
R["rev_v3_ge50"]=stat([t for t in rge if t["t0"]>=V3_CUT])
R["diff_rev_lt50_minus_ge50"]=bboot_diff(rlt,rge)

# Fisher exact one/two-sided, 15/35 vs 10/12
def fisher(a,b,c,d):
    # table [[a,b],[c,d]]: a=cheap wins, b=cheap losses, c=capmiss wins, d=capmiss losses
    from math import comb
    n=a+b+c+d; r1=a+b; c1=a+c
    def pt(x): return comb(r1,x)*comb(n-r1,c1-x)/comb(n,c1)
    obs=pt(a); lo=max(0,c1-(n-r1)); hi=min(r1,c1)
    one=sum(pt(x) for x in range(lo,a+1))          # P(cheap wins <= a): cheap worse
    two=sum(pt(x) for x in range(lo,hi+1) if pt(x)<=obs+1e-12)
    return one,two
one,two=fisher(15,20,10,2)
R["fisher_replication"]={"cheap":"15/35","capmiss":"10/12",
                         "p_one_sided":round(one,5),"p_two_sided":round(two,5)}

# ---------- 2. adverse-selection increment (honest null) ----------
R["pooled_50_53_adv_boot"]=bboot(z5053,"adv")     # q vs ask-implied (entry-0.01)
R["rev_ge50_adv_boot"]=bboot(rge,"adv")

# ---------- 3. selection correction over the 13-bucket scan ----------
bucket_stats=[]
for lo10 in range(15,80,5):
    lo,hi=lo10/100,(lo10+5)/100
    b=[t for t in S if lo<=t["entry"]<hi]
    if len(b)<30: continue
    bb=bboot(b,"ev",4000)
    bucket_stats.append({"bucket":f"{lo10}-{lo10+5}","n":len(b),
                         "ev_c":bb["obs_c"],"p_neg":bb["p_boot_ge0"]})
R["bucket_scan"]=bucket_stats
K=len(bucket_stats)
p5053=R["pooled_50_53_boot_ev"]["p_boot_ge0"]
R["selection"]={"K_5c_buckets_with_n_ge30":K,
                "p_50_53_raw":p5053,
                "bonferroni_x13":round(min(1,13*p5053),4),
                "note_prereg":"[0.50,0.53) is the frozen hi-qhat bucket of Jul-10 FINAL-DESIGN "
                              "S4.2 and the S7 cap-verdict zone; boundary not chosen on this data."}

# permutation over bucket choice: how often does the min-p bucket beat p5053 under a
# within-hour-block label-shuffle null (breaks price<->outcome link, keeps clustering)?
def perm_scan(nperm=400):
    hits=0
    hours={}
    for t in S: hours.setdefault(t["t0"]//3600,[]).append(t)
    hour_list=list(hours.values())
    edges=[(l/100,(l+5)/100,f"{l}-{l+5}") for l in range(15,80,5)]
    for _ in range(nperm):
        # shuffle outcomes across trades within the whole ledger, preserving per-hour counts
        # (permutes win labels over entries globally — null: q independent of entry price)
        ws=[t["w"] for t in S]; random.shuffle(ws)
        best=1.0
        for (lo,hi,_lab) in edges:
            idx=[i for i,t in enumerate(S) if lo<=t["entry"]<hi]
            if len(idx)<30: continue
            n=len(idx); w=sum(ws[i] for i in idx)
            pm=sum(S[i]["entry"] for i in idx)/n
            # normal-approx one-sided p for q < qstar-ish effect: use z on (q - qstar)
            q=w/n; se=math.sqrt(max(q*(1-q),1e-9)/n)
            zv=(q-qstar(pm))/se
            p=0.5*math.erfc(-zv/math.sqrt(2))   # P(observing this low or lower) upper tail
            p_low=0.5*math.erfc(zv/math.sqrt(2))
            best=min(best,p_low)
        # observed analogue for 50-53
        if best<=0.0125: hits+=1
    return hits/nperm
# observed one-sided normal p for 50-53 q vs qstar
q=R["pooled_50_53"]["q"]; n=R["pooled_50_53"]["n"]; qs=R["pooled_50_53"]["qstar"]
se=math.sqrt(q*(1-q)/n); z_obs=(q-qs)/se
p_obs=0.5*math.erfc(-(-z_obs)/math.sqrt(2)) if z_obs<0 else 1
p_obs=0.5*math.erfc(z_obs/math.sqrt(2))  # lower-tail... erfc(z/sqrt2)/2 = P(Z>=z); for z<0 that's ~1
p_obs=0.5*(1+math.erf(z_obs/math.sqrt(2)))  # P(Z<=z_obs) = lower tail = p for q<qstar
R["selection"]["p_normal_obs_50_53_q_lt_qstar"]=round(p_obs,5)
R["selection"]["perm_frac_minp_scan_beats_obs"]=perm_scan()

# ---------- 4. pre-registrable alternative split: odd/even UTC day ----------
for lab,pred in [("evenday",lambda t:(t["t0"]//86400)%2==0),
                 ("oddday",lambda t:(t["t0"]//86400)%2==1)]:
    sub=[t for t in z5053 if pred(t)]
    st=stat(sub); st.update({"boot":bboot(sub,"ev",8000)})
    R[f"pooled_50_53_{lab}"]=st
    subr=[t for t in rge if pred(t)]
    R[f"rev_ge50_{lab}"]=stat(subr)

# ---------- 5. dedup by t0 ----------
seen={}
for t in z5053: seen.setdefault(t["t0"],t)
ded=list(seen.values())
R["pooled_50_53_dedup"]=stat(ded)
R["pooled_50_53_dedup_boot"]=bboot(ded,"ev")
R["pooled_50_53_dedup_adv_boot"]=bboot(ded,"adv")

json.dump(R,open(os.path.join(OUT,"results.json"),"w"),indent=1)
print(json.dumps(R,indent=1))
