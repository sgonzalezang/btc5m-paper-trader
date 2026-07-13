#!/usr/bin/env python3
"""Adversarial inference tests for R1:
(1) efficient-market null Monte Carlo for the total policy delta,
(2) exact binomial for the skip leg,
(3) v2 ABSOLUTE book significance,
(4) overlap of R1's delta with the 48-53c 'toxic zone' (R2 double-count),
(5) settledBy audit."""
import json, math, random, collections
from math import comb

DATA='/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data/'
T=json.load(open(DATA+'trades_unified.json'))
FEE=lambda p:0.07*p*(1-p)
v2={t['t0']:t for t in T if t['eng']=='impulse_v2' and t['status']=='settled'}
i50={t['t0']:t for t in T if t['eng']=='impulse50' and t['status']=='settled'}
common=sorted(set(v2)&set(i50)); skips=sorted(set(i50)-set(v2))
out={}

def ps(t):
    p=t['entry']; q=1.0 if t['result']=='win' else 0.0
    return 100*(q-p-FEE(p))

# ---- (1) efficient-market null: every fill is break-even (q = p + fee).
# Under this null the identical pairs contribute 0, the improved pairs contribute their
# deterministic price-difference delta, and the skip deltas are mean-zero noise.
# Question: P(total policy delta >= observed 10.55) under the null?
improved=[(v2[t]['entry'],i50[t]['entry']) for t in common if v2[t]['entry']<i50[t]['entry']-1e-9]
mech=sum(100*((pb+FEE(pb))-(pa+FEE(pa))) for pa,pb in improved)  # deterministic component
skip_p=[i50[t]['entry'] for t in skips]
obs_total=10.55*34
random.seed(7)
B=200000; ge=0; tots=[]
for _ in range(B):
    s=mech
    for p in skip_p:
        q=p+FEE(p)  # break-even null
        win=random.random()<q
        s+= -(100*((1 if win else 0)-p-FEE(p)))  # skip delta = -(i50 ps)
    tots.append(s)
    if s>=obs_total-1e-6: ge+=1
tots.sort()
out['efficient_null_MC']={
 'mechanical_component_c_per_signal':round(mech/34,2),
 'expected_delta_under_null_c':round(sum(tots)/B/34,2),
 'observed_c':10.55,
 'P(delta>=observed | null)':round(ge/B,4),
 'null_ci90_c_per_signal':[round(tots[int(0.05*B)]/34,2),round(tots[int(0.95*B)]/34,2)],
 'note':'improvement leg is deterministic given fill prices; only skip outcomes are stochastic. This is the honest p for "the f>0 rule added value beyond mechanics" '}

# ---- (2) exact binomial skip leg (n=8) and with flagship's n=7 variant
for n_lab,tset in (('n8_all_skips',skips),):
    k=sum(1 for t in tset if i50[t]['result']=='win'); n=len(tset)
    pm=sum(i50[t]['entry'] for t in tset)/n; qs=pm+FEE(pm)
    p_le=sum(comb(n,j)*qs**j*(1-qs)**(n-j) for j in range(k+1))
    out['skip_binomial_'+n_lab]={'n':n,'wins':k,'mix':round(pm,4),'qstar':round(qs,4),'P(K<=k|q*)':round(p_le,4)}

# ---- (3) v2 absolute book
n=len(common); k=sum(1 for t in common if v2[t]['result']=='win')
pm_=sum(v2[t]['entry'] for t in common)/n; qs=pm_+FEE(pm_)
p_ge=sum(comb(n,j)*qs**j*(1-qs)**(n-j) for j in range(k,n+1))
mean_ps=sum(ps(v2[t]) for t in common)/n
out['v2_absolute_book']={'n':n,'wins':k,'wr':round(k/n,4),'avg_entry':round(pm_,4),'qstar':round(qs,4),
 'ps_mean_c':round(mean_ps,2),'binom_P(K>=k|q*)':round(p_ge,4),
 'note':'is the flagship book itself distinguishable from break-even? '}

# ---- (4) R2 toxic-zone overlap: i50 first fills at >=0.48
zone=[t for t in sorted(i50) if i50[t]['entry']>=0.48]
zone_common=[t for t in zone if t in common]; zone_skip=[t for t in zone if t in skips]
zone_ps=sum(ps(i50[t]) for t in zone)
w=sum(1 for t in zone if i50[t]['result']=='win')
# how much of the policy delta comes from trades where i50's first fill was in the zone?
delta_from_zone=0.0
for t in common:
    a,b=v2[t],i50[t]
    d=ps(a)-ps(b)
    if b['entry']>=0.48: delta_from_zone+=d
for t in skips:
    if i50[t]['entry']>=0.48: delta_from_zone+= -ps(i50[t])
total_delta=sum((ps(v2[t])-ps(i50[t])) for t in common)+sum(-ps(i50[t]) for t in skips)
out['toxic_zone_overlap']={
 'i50_first_fills_ge48c':{'n':len(zone),'wins':w,'wr':round(w/len(zone),3),'sum_ps_c':round(zone_ps,1),
                          'of_which_common':len(zone_common),'skips':len(zone_skip)},
 'policy_delta_total_c':round(total_delta,1),
 'delta_from_zone_signals_c':round(delta_from_zone,1),
 'share_of_delta_from_zone':round(delta_from_zone/total_delta,3),
 'note':'R1 delta and any separate 48-53c-toxic-zone finding are the SAME trades counted twice'}

# ---- (5) settledBy audit + fee fields on the 60 trades
sb=collections.Counter(t['settledBy'] for t in list(v2.values())+list(i50.values()))
out['settledBy']=dict(sb)

# ---- (6) qhat threshold vs actual v2 fills (cap behavior)
mx_ident=max(v2[t]['entry'] for t in common if abs(v2[t]['entry']-i50[t]['entry'])<1e-9)
mx_all=max(v2[t]['entry'] for t in common)
out['v2_fill_cap_check']={'max_v2_entry_common':mx_all,'max_identical_pair_entry':mx_ident,
 'skip_first_poll_entries':sorted(round(i50[t]['entry'],2) for t in skips),
 'note':'v2 never filled above ~0.48 entry (=47c ask); consistent with f>0 iff p_eff<=~0.4886 from qlo=0.5068'}

json.dump(out, open('/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work/verify/R1-integrity/null_tests_out.json','w'), indent=1)
print(json.dumps(out, indent=1))
