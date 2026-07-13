#!/usr/bin/env python3
"""Policy-level accounting: impulse_v2's wait-or-skip vs impulse50's take-first,
per gated signal (n=34 settled), plus v3-era per-engine book stats."""
import json, math, random, datetime
from collections import defaultdict

DATA = '/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data'
WORK = '/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work/misses'
FEE = 0.07; ERA0 = 1783695900
random.seed(20260712)
def fee(p): return FEE*p*(1-p)
def ut(t): return datetime.datetime.utcfromtimestamp(t).strftime('%m-%d %H:%M')

st = json.load(open(f'{DATA}/state_extract.json'))
TR = json.load(open(f'{DATA}/trades_unified.json'))
v3 = [t for t in TR if t['t0'] >= ERA0]
by_eng = defaultdict(dict)
for t in v3: by_eng[t['eng']][t['t0']] = t
iv2, i50 = by_eng['impulse_v2'], by_eng['impulse50']
meas = {m['t0']: m for m in st['measure']}

def ev_share(t):
    if t.get('result') not in ('win','loss'): return None
    p = t['entry']
    return (1-p-fee(p)) if t['result']=='win' else (-p-fee(p))

def bboot(rows, B=4000):
    blocks = defaultdict(list)
    for t0,v in rows: blocks[t0//3600].append(v)
    keys=list(blocks.values()); n=len(keys); means=[]
    for _ in range(B):
        s=[]
        for _ in range(n): s.extend(random.choice(keys))
        means.append(sum(s)/len(s))
    means.sort()
    mu=sum(v for _,v in rows)/len(rows)
    frac=sum(1 for m in means if m<=0)/B
    return dict(mean_c=round(100*mu,2), lo_c=round(100*means[int(.025*B)],2),
                hi_c=round(100*means[int(.975*B)-1],2), p_vs0=round(2*min(frac,1-frac),4), nblocks=n)

# per-signal policy delta: signals = all settled impulse50 trades (take-everything book)
rows = []; detail=[]
for t0, t in sorted(i50.items()):
    e50 = ev_share(t)
    if e50 is None: continue
    tv = iv2.get(t0)
    eiv = ev_share(tv) if tv else 0.0   # skip = 0 EV per share (no position)
    rows.append((t0, (eiv or 0.0) - e50))
    detail.append(dict(t0=t0, iso=ut(t0), i50_entry=t['entry'], i50_ev_c=round(100*e50,2),
                       iv2=('trade@%.2f' % tv['entry']) if tv else 'SKIP',
                       delta_c=round(100*((eiv or 0.0)-e50),2)))
tot = sum(v for _,v in rows)
out = dict(
    n_signals=len(rows),
    policy_delta_total_c=round(100*tot,1),
    policy_delta_per_signal_c=round(100*tot/len(rows),2),
    block_boot=bboot(rows),
    detail=detail)

# split of the delta: price-improvement pairs vs avoided-skip losers
imp = [d for d in detail if d['iv2']!='SKIP' and d['delta_c']!=0]
skp = [d for d in detail if d['iv2']=='SKIP']
out['decomposition'] = dict(
    identical_fills=sum(1 for d in detail if d['iv2']!='SKIP' and d['delta_c']==0),
    price_improved=dict(n=len(imp), total_c=round(sum(d['delta_c'] for d in imp),1)),
    skips_avoided=dict(n=len(skp), total_c=round(sum(d['delta_c'] for d in skp),1),
                       i50_wr_on_skipped=round(sum(1 for d in skp if d['i50_ev_c']>0)/len(skp),3) if skp else None))

# v3-era per-engine books
books = {}
for eng in ('impulse_v2','impulse50','reversal_v2','reversal','reversal2'):
    evs = [(t0, ev_share(t)) for t0, t in by_eng[eng].items() if ev_share(t) is not None]
    if not evs: continue
    evs.sort()
    n=len(evs); mu=sum(v for _,v in evs)/n
    books[eng] = dict(n=n, wr=round(sum(1 for _,v in evs if v>0)/n,3),
                      ev_share_c=round(100*mu,2),
                      mean_entry=round(sum(by_eng[eng][t0]['entry'] for t0,_ in evs)/n,4),
                      pnl_usd=round(sum(by_eng[eng][t0].get('pnl') or 0 for t0,_ in evs),2),
                      block_boot=bboot(evs) if n>=5 else None)
out['v3_books'] = books

# capmiss x rev55: mean EV of the 7 real fills
xr = json.load(open(f'{WORK}/results_refine.json'))['capmiss_x_rev55']['rows']
fills = [x['fill_55c_book']['ev_c'] for x in xr if x['fill_55c_book'] and x['fill_55c_book']['ev_c'] is not None]
out['capmiss_real_fills'] = dict(n=len(fills), mean_ev_c=round(sum(fills)/len(fills),2),
                                 wins=sum(1 for f in fills if f>0))

json.dump(out, open(f'{WORK}/results_policy.json','w'), indent=1)
o=dict(out); o.pop('detail')
print(json.dumps(o, indent=1))
print('skipped-signal details:')
for d in detail:
    if d['iv2']=='SKIP': print(json.dumps(d))
