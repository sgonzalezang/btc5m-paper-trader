#!/usr/bin/env python3
"""R1 adversarial verification: re-derive the impulse_v2 vs impulse50 sizing delta
from RAW trades_unified.json + raw candles, with integrity checks.
Stdlib only."""
import json, math, random, collections, datetime

DATA='/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data/'
T=json.load(open(DATA+'trades_unified.json'))
cb1=json.load(open(DATA+'cb1m.json'))
cb5=json.load(open(DATA+'cb5m.json'))

def utc(ts): return datetime.datetime.utcfromtimestamp(ts).strftime('%m-%d %H:%M:%S')

open1=dict(zip(cb1['t'],cb1['o']))
open5=dict(zip(cb5['t'],cb5['o']))

def candle_result(t0):
    """Coinbase proxy: open(t0+300) vs open(t0). Returns ('up'/'down'/'tie', move_bps)."""
    o0=open1.get(t0, open5.get(t0)); o1=open1.get(t0+300, open5.get(t0+300))
    if o0 is None or o1 is None: return None, None
    mv=(o1-o0)/o0*1e4
    if o1>o0: return 'up',mv
    if o1<o0: return 'down',mv
    return 'tie',mv

FEE=lambda p: 0.07*p*(1-p)
GAS=0.004

v2=[t for t in T if t['eng']=='impulse_v2' and t['status']=='settled']
i50=[t for t in T if t['eng']=='impulse50' and t['status']=='settled']
v2open=[t for t in T if t['eng']=='impulse_v2' and t['status']!='settled']
i50open=[t for t in T if t['eng']=='impulse50' and t['status']!='settled']

report={}
report['counts']={'v2_settled':len(v2),'i50_settled':len(i50),
                  'v2_open':[(t['t0'],utc(t['t0'])) for t in v2open],
                  'i50_open':[(t['t0'],utc(t['t0'])) for t in i50open]}

# ---------- integrity check 1: entrySec / lookahead ----------
bad_entry=[]
for t in v2+i50:
    es=t.get('entrySec')
    at_s=t['at']/1000.0
    implied=at_s-t['t0']
    if es is None or abs(implied-es)>10 or es<0 or es>60:
        bad_entry.append({'eng':t['eng'],'t0':t['t0'],'entrySec':es,'implied':round(implied,1)})
report['entrysec_check']={'n_flagged':len(bad_entry),'rows':bad_entry,
    'max_entrySec_v2':max(t['entrySec'] for t in v2),
    'max_entrySec_i50':max(t['entrySec'] for t in i50)}

# ---------- integrity check 2: pnl model + result vs candles ----------
pnl_dev=[]; res_mismatch=[]; tiny_moves=[]
for t in v2+i50:
    p=t['entry']; sh=t['shares']; st=t['stake']
    if t['result']=='win':
        model=sh*(1-p)-sh*FEE(p)-GAS
    else:
        model=-st-sh*FEE(p)-GAS
    # note: fee conventions vary; try logged feeEntry/feeExit
    fe=t.get('feeEntry',0) or 0; fx=t.get('feeExit',0) or 0
    model2=(sh*(1-p) if t['result']=='win' else -st)-fe-fx-GAS
    dev=min(abs(model-t['pnl']),abs(model2-t['pnl']))
    if dev>0.02: pnl_dev.append({'eng':t['eng'],'t0':t['t0'],'pnl':t['pnl'],'model':round(model,3),'model2':round(model2,3)})
    cr,mv=candle_result(t['t0'])
    won_side = t['side'] if t['result']=='win' else ('up' if t['side']=='down' else 'down')
    if cr is not None:
        if abs(mv)<4: tiny_moves.append({'eng':t['eng'],'t0':t['t0'],'mv_bps':round(mv,2),'ledger_winner':won_side,'cb_winner':cr})
        if cr!='tie' and cr!=won_side:
            res_mismatch.append({'eng':t['eng'],'t0':t['t0'],'utc':utc(t['t0']),'mv_bps':round(mv,2),'ledger_winner':won_side,'cb_winner':cr,'settledBy':t.get('settledBy')})
report['pnl_model_check']={'n_dev_gt_2c':len(pnl_dev),'rows':pnl_dev[:10]}
report['result_vs_coinbase']={'n_mismatch':len(res_mismatch),'rows':res_mismatch,
                              'n_tiny_lt4bps':len(tiny_moves),'tiny_rows':tiny_moves}

# ---------- pairing ----------
v2d={t['t0']:t for t in v2}; i50d={t['t0']:t for t in i50}
common=sorted(set(v2d)&set(i50d))
only50=sorted(set(i50d)-set(v2d))
only2=sorted(set(v2d)-set(i50d))
report['pairing']={'common':len(common),'i50_only(skips)':len(only50),'v2_only':len(only2),
    'skip_t0s':[[t0,utc(t0)] for t0 in only50]}

# side agreement on common
side_mismatch=[t0 for t0 in common if v2d[t0]['side']!=i50d[t0]['side']]
res_agree=[t0 for t0 in common if v2d[t0]['result']==i50d[t0]['result']]
report['pairing']['side_mismatch']=side_mismatch
report['pairing']['result_agree']=len(res_agree)

# per-share EV after frozen cost model, per SIGNAL (policy view, $-per-$50-notional-share basis)
def ps_cents(t):
    """net per-share in cents from the ledger pnl normalized by shares."""
    return 100.0*t['pnl']/t['shares']

def ps_model(t):
    p=t['entry']; q=1.0 if t['result']=='win' else 0.0
    return 100.0*(q-p-FEE(p))

# policy delta per signal: v2 ps (0 if skipped) minus i50 ps, over the 34 i50 signals
rows=[]
for t0 in sorted(set(i50d)|set(v2d)):
    a=v2d.get(t0); b=i50d.get(t0)
    ps_a=ps_model(a) if a else 0.0
    ps_b=ps_model(b) if b else 0.0
    rows.append({'t0':t0,'utc':utc(t0),'delta':ps_a-ps_b,
                 'v2_entry':a['entry'] if a else None,'i50_entry':b['entry'] if b else None,
                 'v2_sec':a['entrySec'] if a else None,'i50_sec':b['entrySec'] if b else None,
                 'result':(a or b)['result'],'side':(a or b)['side'],
                 'kind':'common' if (a and b) else ('skip' if b else 'v2only')})
deltas=[r['delta'] for r in rows]
mean_delta=sum(deltas)/len(deltas)
report['policy_delta']={'n_signals':len(rows),'mean_c':round(mean_delta,2)}

# decomposition
comm=[r for r in rows if r['kind']=='common']
same_price=[r for r in comm if abs(r['v2_entry']-r['i50_entry'])<1e-9]
improved=[r for r in comm if r['v2_entry']<r['i50_entry']-1e-9]
richer=[r for r in comm if r['v2_entry']>r['i50_entry']+1e-9]
skips=[r for r in rows if r['kind']=='skip']
report['decomposition']={
 'identical':{'n':len(same_price),'sum_delta_c':round(sum(r['delta'] for r in same_price),2)},
 'improved':{'n':len(improved),'sum_delta_c':round(sum(r['delta'] for r in improved),2),
             'mean_improvement_c':round(sum((r['i50_entry']-r['v2_entry'])*100 for r in improved)/max(1,len(improved)),2),
             'mean_delta_c':round(sum(r['delta'] for r in improved)/max(1,len(improved)),2)},
 'richer':{'n':len(richer)},
 'skips':{'n':len(skips),'sum_delta_c':round(sum(r['delta'] for r in skips),2),
          'i50_wins_on_skips':sum(1 for r in skips if r['result']=='win'),
          'mean_i50_entry':round(sum(r['i50_entry'] for r in skips)/max(1,len(skips)),4),
          'rows':[{'t0':r['t0'],'utc':r['utc'],'entry':r['i50_entry'],'result':r['result'],'delta_c':round(r['delta'],1)} for r in skips]}}

# ---------- bootstrap variance: multiple schemes ----------
random.seed(20260712)
def block_boot(rows, key_seconds, B=20000):
    blocks=collections.defaultdict(list)
    for r in rows: blocks[r['t0']//key_seconds].append(r['delta'])
    bl=list(blocks.values()); nb=len(bl)
    means=[]
    for _ in range(B):
        s=[]
        for _ in range(nb): s.extend(random.choice(bl))
        means.append(sum(s)/len(s))
    means.sort()
    lo=means[int(0.05*B)]; hi=means[int(0.95*B)]
    p=2*min(sum(1 for m in means if m<=0)/B, sum(1 for m in means if m>=0)/B)
    return {'nblocks':nb,'mean_c':round(mean_delta,2),'ci90':[round(lo,2),round(hi,2)],'p_two_sided':round(p,4)}

report['bootstrap']={
 '1h_blocks':block_boot(rows,3600),
 '3h_blocks':block_boot(rows,3*3600),
 '6h_blocks':block_boot(rows,6*3600),
 '1d_blocks':block_boot(rows,86400)}

# permutation-style sign test on the skip leg alone (the only stochastic leg):
# under H0 the skipped trades are break-even at their price mix -> per-share EV 0.
# exact binomial: skips won k of n at mean entry p -> what q would make EV 0?
n_sk=len(skips); k_sk=sum(1 for r in skips if r['result']=='win')
p_mix=sum(r['i50_entry'] for r in skips)/n_sk
qstar=p_mix+FEE(p_mix)
from math import comb
binom_le=sum(comb(n_sk,j)*qstar**j*(1-qstar)**(n_sk-j) for j in range(0,k_sk+1))
report['skip_leg_test']={'n':n_sk,'wins':k_sk,'mix_entry':round(p_mix,4),'qstar':round(qstar,4),
    'binom_P(K<=k | q=qstar)':round(binom_le,4),
    'note':'one-sided exact test that skipped trades were worse than break-even'}

# mechanical-leg audit: conditional on identical outcome + cheaper fill, delta>0 by construction
mech=all(r['delta']>0 for r in improved if True)
report['improved_leg_mechanical']={'all_positive_by_construction':mech,
  'explanation':'same outcome + lower entry => delta strictly positive whichever way the trade settles; the leg has selection risk (waiting) priced only via the skip leg'}

# ---------- adversarial counterfactual: what if waiting had cost, symmetric test ----------
# The honest policy contrast is total delta (done). Additional stress: drop the single best
# and worst signal (jackknife extremes) to see fragility.
sd=sorted(deltas)
report['fragility']={
 'drop_best':round((sum(sd[:-1]))/(len(sd)-1),2),
 'drop_worst':round((sum(sd[1:]))/(len(sd)-1),2),
 'drop_best2':round((sum(sd[:-2]))/(len(sd)-2),2),
 'top3_deltas':[round(x,1) for x in sd[-3:]],'bottom3':[round(x,1) for x in sd[:3]],
 'n_nonzero':sum(1 for d in deltas if abs(d)>1e-9),
 'n_positive':sum(1 for d in deltas if d>1e-9),'n_negative':sum(1 for d in deltas if d<-1e-9)}

json.dump(report, open('/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work/verify/R1-integrity/rederive_out.json','w'), indent=1)
print(json.dumps(report, indent=1))
EOF
