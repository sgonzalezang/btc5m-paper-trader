#!/usr/bin/env python3
"""Refinements: paired sizing test, unified early-book-lean test (exact),
cap-miss x reversal55 overlap, extended candle context, liveness audit."""
import json, math, random, datetime
from collections import defaultdict

DATA = '/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data'
WORK = '/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work/misses'
FEE = 0.07
ERA0, ERA1 = 1783695900, 1783914000
random.seed(20260712)

def ut(t): return datetime.datetime.utcfromtimestamp(t).strftime('%m-%d %H:%M')
def fee(p): return FEE*p*(1-p)

cb = json.load(open(f'{DATA}/cb1m.json'))
OP = dict(zip(cb['t'], cb['o']))
st = json.load(open(f'{DATA}/state_extract.json'))
TR = json.load(open(f'{DATA}/trades_unified.json'))
prev = json.load(open(f'{WORK}/results.json'))

def ret5(t):
    a, b = OP.get(t), OP.get(t+300)
    return None if (a is None or b is None) else (b-a)/a
def res(t0):
    r = ret5(t0)
    return None if r is None else ('up' if r>0 else ('down' if r<0 else 'tie'))
def gate(t0):
    rets = [ret5(t0-300*k) for k in range(1,14)]
    if any(r is None for r in rets): return None
    last6 = [rets[k-1] for k in range(6,0,-1)]
    den = sum(abs(r) for r in last6); net=1.0
    for r in last6: net *= (1.0+r)
    eff6 = (abs(net-1.0)/den) if den>0 else 1.0
    cnt12 = sum(1 for k in range(2,14) if abs(rets[k-1])>=0.0012)
    return eff6>=0.10 and cnt12<=6

def C(n,k):
    return math.comb(n,k)
def fisher_onesided(w1,n1,w2,n2):
    """P(X >= w2) for group2 wins under hypergeometric with margins fixed."""
    N, K, n = n1+n2, w1+w2, n2
    p = 0.0
    for x in range(w2, min(K,n)+1):
        if n-x > N-K or K-x > n1: continue
        p += C(K,x)*C(N-K,n-x)/C(N,n)
    return p

v3 = [t for t in TR if t['t0'] >= ERA0]
by_eng = defaultdict(dict)
for t in v3: by_eng[t['eng']][t['t0']] = t
iv2, i50 = by_eng['impulse_v2'], by_eng['impulse50']
rev, rev2, rv2 = by_eng['reversal'], by_eng['reversal2'], by_eng['reversal_v2']
meas = {m['t0']: m for m in st['measure']}

def ev_share(t):
    if t.get('result') not in ('win','loss'): return None
    p = t['entry']
    return (1-p-fee(p)) if t['result']=='win' else (-p-fee(p))

out = {}

# ---------- A. paired impulse_v2 vs impulse50 ----------
pairs = []
for t0 in sorted(set(iv2) & set(i50)):
    a, b = ev_share(iv2[t0]), ev_share(i50[t0])
    if a is None or b is None: continue
    pairs.append(dict(t0=t0, iso=ut(t0), iv2_entry=iv2[t0]['entry'], i50_entry=i50[t0]['entry'],
                      iv2_ev_c=round(100*a,2), i50_ev_c=round(100*b,2), delta_c=round(100*(a-b),2),
                      price_improve_c=round(100*(i50[t0]['entry']-iv2[t0]['entry']),2)))
deltas = [(p['t0'], p['delta_c']/100) for p in pairs]
# block bootstrap on paired deltas
def bboot(rows, B=4000):
    if not rows: return None
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
    return dict(mean_c=round(100*mu,2), lo_c=round(100*means[int(.025*B)],2), hi_c=round(100*means[int(.975*B)-1],2),
                p_vs0=round(2*min(frac,1-frac),4), nblocks=n)
# iv2-only t0s (i50 absent = ??) and i50-only (pure skips)
out['paired_sizing'] = dict(
    n_pairs=len(pairs), mean_delta_c=round(sum(p['delta_c'] for p in pairs)/len(pairs),2),
    mean_price_improve_c=round(sum(p['price_improve_c'] for p in pairs)/len(pairs),2),
    n_price_improved=sum(1 for p in pairs if p['price_improve_c']>0),
    block_boot=bboot(deltas),
    iv2_only=sorted(set(iv2)-set(i50)), i50_only=sorted(set(i50)-set(iv2)),
    pairs=pairs)

# same-outcome check: deltas driven purely by entry price? (same t0 same side -> same win)
out['paired_sizing']['note'] = ('delta per share = price improvement (same outcome both books); '
                                'impulse_v2 waits out the first poll when ask>=48c (f_nonpos) and refills cheaper')

# ---------- B. unified early-book-lean test ----------
# Group CHEAP: gate-era 12bps triggers where contrarian side was fillable <=53c in first 45s
#   = measure book t0s (36) + impulse trades  --> outcome from cb1m
# Group EXPENSIVE: trigger t0s whose miss note says cap53/cap55 red (ask+slip > cap all window)
#   unique t0s across all engines' misses, excluding any that appear in CHEAP.
cheap_t0 = set(meas) | set(iv2) | set(i50)
cheap = []
for t0 in sorted(cheap_t0):
    side = (meas.get(t0) or {}).get('side') or (iv2.get(t0) or i50.get(t0))['side']
    w = res(t0)
    if w in ('up','down'): cheap.append((t0, 1 if w==side else 0))
missed = st['misses_btc']
exp_t0 = {}
for m in missed:
    if ('Rev≤53c' in m['note'] or 'Rev≤55c' in m['note']) and m['t0'] not in cheap_t0:
        exp_t0.setdefault(m['t0'], m['side'])
expensive = []
for t0, side in sorted(exp_t0.items()):
    w = res(t0)
    if w in ('up','down'): expensive.append((t0, 1 if w==side else 0))
w1, n1 = sum(w for _,w in cheap), len(cheap)
w2, n2 = sum(w for _,w in expensive), len(expensive)
out['early_book_lean'] = dict(
    cheap=dict(n=n1, wins=w1, wr=round(w1/n1,3)),
    expensive_capmissed=dict(n=n2, wins=w2, wr=round(w2/n2,3)),
    fisher_onesided_p=round(fisher_onesided(w1,n1,w2,n2),5),
    note=('one-sided pre-specified: prior round found fillable q=.4516 vs unfillable q=.7692 on the '
          'pm-matched sample; this is the live Jul10-13 replication. cheap = contrarian ask fillable '
          '<=53c in first 45s; expensive = signal present but ask stayed above cap.'))

# ---------- C. cap53-missed t0s x reversal(55c)/reversal2 books ----------
xr = []
for t0 in sorted(exp_t0):
    hit = None
    for eng, book in (('reversal',rev), ('reversal2',rev2)):
        if t0 in book:
            t = book[t0]; e = ev_share(t)
            hit = dict(eng=eng, entry=t['entry'], result=t.get('result'), ev_c=None if e is None else round(100*e,2))
            break
    xr.append(dict(t0=t0, iso=ut(t0), side=exp_t0[t0], win=(res(t0)==exp_t0[t0]), fill_55c_book=hit))
n_filled55 = sum(1 for x in xr if x['fill_55c_book'])
out['capmiss_x_rev55'] = dict(rows=xr, n=len(xr), n_filled_by_55c_book=n_filled55,
    note='how many cap53-missed signals the 55c-cap shadow actually caught, and at what EV')
# all v3 reversal-family fills entry>0.54 (the 53->55/56 band) pooled
band55 = []
for eng in ('reversal','reversal2'):
    for t0, t in by_eng[eng].items():
        e = ev_share(t)
        if e is not None and t['entry'] > 0.54: band55.append((t0, e, t['entry']))
u = {}
for t0, e, p in band55: u.setdefault(t0, []).append(e)
rows = sorted((t0, sum(v)/len(v)) for t0,v in u.items())
out['band_54_56_fills'] = dict(n=len(rows), ev_share_c=round(100*sum(v for _,v in rows)/len(rows),2) if rows else None,
                               wr=round(sum(1 for _,v in rows if v>0)/len(rows),3) if rows else None,
                               block_boot=bboot(rows) if len(rows)>=5 else None)

# ---------- D. extended candle context (Jun 26 -> Jul 13, no bot join) ----------
t_all = sorted(OP)
start = ((t_all[0]//300)+14)*300
ctx = {'trigger': [], 'gate_pass': []}
for t0 in range(start, ERA1, 300):
    r = ret5(t0-300); w = res(t0)
    if r is None or w is None or w=='tie': continue
    if abs(r) < 0.0012: continue
    side = 'down' if r>0 else 'up'
    win = 1 if w==side else 0
    ctx['trigger'].append((t0,win))
    g = gate(t0)
    if g: ctx['gate_pass'].append((t0,win))
def wrs(rows):
    n=len(rows); w=sum(x for _,x in rows)
    return dict(n=n, wr=round(w/n,4))
# weekly breakdown of gate-pass contrarian wr
wk = defaultdict(list)
for t0,win in ctx['gate_pass']:
    wk[datetime.datetime.utcfromtimestamp(t0).strftime('%m-%d')[:5]].append(win)
daily = {d: dict(n=len(v), wr=round(sum(v)/len(v),3)) for d,v in sorted(wk.items())}
out['context_jun26_jul13'] = dict(all_triggers=wrs(ctx['trigger']), gate_pass=wrs(ctx['gate_pass']),
    gate_pass_daily=daily,
    era_gate_pass=wrs([(t,w) for t,w in ctx['gate_pass'] if t>=ERA0]),
    pre_era_gate_pass=wrs([(t,w) for t,w in ctx['gate_pass'] if t<ERA0]))

# ---------- E. liveness on the 12 'no_bot_evidence' funnel holes ----------
alive_ts = sorted(set([t['t0'] for t in v3] + list(meas) + [m['t0'] for m in missed]))
holes = [r for r in prev['funnel']['gate_pass_detail'] if r['fate']=='no_bot_evidence']
hole_rows = []
for r in holes:
    t0 = r['t0']
    near = min((abs(a-t0) for a in alive_ts), default=None)
    rr = ret5(t0-300)
    hole_rows.append(dict(t0=t0, iso=r['iso'], win=r['win'], nearest_bot_record_min=round(near/60,1),
                          prior_move_bps=round(abs(rr)*10000,1)))
out['funnel_holes'] = dict(rows=hole_rows,
    note='nearest bot record distance: <15 min => bot was alive, likely tick-feed prior-move < 12bps (boundary miss); large => downtime')

json.dump(out, open(f'{WORK}/results_refine.json','w'), indent=1)
for k in out:
    print('==='+k+'===')
    v = dict(out[k])
    v.pop('pairs',None); v.pop('rows',None)
    print(json.dumps(v, indent=1, default=str))
print('pairs:')
for p in out['paired_sizing']['pairs']: print(json.dumps(p))
print('capmiss rows:')
for x in out['capmiss_x_rev55']['rows']: print(json.dumps(x, default=str))
print('holes:')
for h in out['funnel_holes']['rows']: print(json.dumps(h))
