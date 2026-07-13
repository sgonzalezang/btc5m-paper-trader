#!/usr/bin/env python3
"""R4 adversarial verification: re-derive the measurement-book vs operated-arm divergence
from RAW data (state_extract.json measure[] + trades_unified.json), no analyst intermediates.

Checks:
 1. cost field semantics (= ask+1c slip + 7% fee on p)
 2. t0-join of all 36 measure records to impulse_v2 ledger entries
 3. classes: sized_first_poll / rich_first_poll_entered_later / never_entered
 4. same-signal check for the 12 reclassified records (side match, entrySec ordering, price ordering)
 5. duplicate detection in ledger (same eng+t0 twice, cross-_src dupes)
 6. win-field vs Coinbase candle resolution (lookahead / tie handling)
 7. recompute the headline numbers: -6.23 vs +3.57, per-class EV, bootstrap CIs
"""
import json, random, math

BASE='/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data/'
state=json.load(open(BASE+'state_extract.json'))
trades=json.load(open(BASE+'trades_unified.json'))
measure=state['measure']

def fee(p): return 0.07*p*(1-p)

# --- 1. cost semantics
bad=0
for r in measure:
    if r.get('f'):
        p=r['f']['ask']+0.01
        expect=p+fee(p)
        if abs(expect-r['cost'])>0.0005: bad+=1; print('COST MISMATCH',r)
print(f'cost==ask+1c+fee holds for all records with f: mismatches={bad}')

# --- 2. ledger join
iv2=[t for t in trades if t['eng']=='impulse_v2']
i50=[t for t in trades if t['eng']=='impulse50']
print(f'ledger: impulse_v2 n={len(iv2)}, impulse50 n={len(i50)}, total trades={len(trades)}')
from collections import Counter, defaultdict
# duplicates same eng+t0?
c=Counter((t['eng'],t['t0']) for t in trades)
dupes={k:v for k,v in c.items() if v>1}
print('eng+t0 duplicates across whole ledger:', len(dupes))
for k,v in list(dupes.items())[:10]: print('  DUPE',k,v)
by_t0=defaultdict(list)
for t in iv2: by_t0[t['t0']].append(t)

classes={'sized_first_poll':[], 'rich_entered_later':[], 'never_entered':[], 'sized_no_ledger':[]}
rows=[]
for r in measure:
    m=by_t0.get(r['t0'],[])
    row=dict(r); row['ledger']=m
    if r['sized']:
        if m: classes['sized_first_poll'].append(row)
        else: classes['sized_no_ledger'].append(row)
    else:
        if m: classes['rich_entered_later'].append(row)
        else: classes['never_entered'].append(row)
    rows.append(row)
for k,v in classes.items(): print(k, len(v))

# --- 3/4. same-signal check on reclassified records
print('\n--- rich_first_poll_entered_later detail (merge-agent flag) ---')
print('t0        side  m.sec  m.cost  ledger(side,entrySec,entry,allin,pnl/share,result) sideOK laterOK cheaperOK')
ok_side=ok_later=ok_cheaper=0
for row in classes['rich_entered_later']:
    for t in row['ledger']:
        p=t['entry']; allin=p+fee(p)
        side_ok = t['side']==row['side']
        later_ok = t['entrySec']>=row['f']['sec'] if row.get('f') else None
        cheaper_ok = allin < row['cost']-1e-9
        ok_side+=side_ok; ok_later+=bool(later_ok); ok_cheaper+=cheaper_ok
        ps = t['pnl']/t['shares'] if t.get('shares') else None
        print(f"{row['t0']} {row['side']:>4} {row['f']['sec'] if row.get('f') else '?':>5} {row['cost']:.4f}  "
              f"({t['side']},{t['entrySec']},{t['entry']:.2f},{allin:.4f},{ps if ps is None else round(ps,4)},{t['result']}) "
              f"{side_ok} {later_ok} {cheaper_ok}")
n_rel=len(classes['rich_entered_later'])
print(f'side match {ok_side}/{n_rel}, entered later {ok_later}/{n_rel}, cheaper all-in {ok_cheaper}/{n_rel}')

# win agreement between measure record and ledger result
dis=0
for row in classes['rich_entered_later']+classes['sized_first_poll']:
    for t in row['ledger']:
        lw = 1 if t['result']=='win' else 0 if t['result']=='loss' else None
        if row['win'] is not None and lw is not None and lw!=row['win']:
            dis+=1; print('WIN DISAGREE', row['t0'], row['win'], t['result'], t['side'], row['side'])
print('win-field disagreements measure vs ledger:', dis)

# --- 5. also check impulse50 join (same signals, flat stake) as independent same-signal witness
by_t0_50=defaultdict(list)
for t in i50: by_t0_50[t['t0']].append(t)
w=0
for row in classes['rich_entered_later']:
    m50=by_t0_50.get(row['t0'],[])
    for t in m50:
        if t['side']==row['side']: w+=1
print(f'impulse50 entered same t0+side for {w}/{n_rel} reclassified records')

# --- 6. win vs Coinbase resolution + tie handling
cb=json.load(open(BASE+'cb1m.json'))
op=dict(zip(cb['t'],cb['o']))
agree=miss=tie=0
for r in measure:
    if r['win'] is None: continue
    o0=op.get(r['t0']); o1=op.get(r['t0']+300)
    if o0 is None or o1 is None: miss+=1; continue
    mv=(o1-o0)/o0
    up = o1>o0
    cbwin = 1 if ((r['side']=='up')==up and o1!=o0) else 0
    if o1==o0: tie+=1
    if cbwin==r['win']: agree+=1
    else:
        print('CB DISAGREE', r['t0'], r['side'], 'win=',r['win'], f'move={mv*1e4:.1f}bps')
print(f'coinbase agreement: {agree}/{35-miss} (missing candles={miss}, exact ties={tie})')

# --- 7. recompute headline numbers
def net_ps_first_poll(rs):
    # per-share net at first-poll cost: win - cost  (cost is all-in); gas ignored (analyst same)
    xs=[(r['win']-r['cost']) for r in rs if r['win'] is not None]
    return xs
def boot_ci(xs, B=10000, seed=42):
    rnd=random.Random(seed); n=len(xs); ms=[]
    for _ in range(B):
        s=[xs[rnd.randrange(n)] for _ in range(n)]
        ms.append(sum(s)/n)
    ms.sort()
    return ms[int(0.05*B)], ms[int(0.95*B)]

allx=net_ps_first_poll(measure)
print(f'\nALL at first-poll cost: n={len(allx)} mean={100*sum(allx)/len(allx):+.2f}c/sh CI90=({100*boot_ci(allx)[0]:+.2f},{100*boot_ci(allx)[1]:+.2f}) wins={sum(1 for r in measure if r["win"]==1)}')
for k in ['never_entered','sized_first_poll','rich_entered_later']:
    xs=net_ps_first_poll([dict(r) for r in classes[k]])
    if xs:
        lo,hi=boot_ci(xs)
        wr=sum(1 for r in classes[k] if r['win']==1)/len(xs)
        print(f'{k}: n_settled={len(xs)} wr={wr:.4f} mean={100*sum(xs)/len(xs):+.2f}c/sh CI90=({100*lo:+.2f},{100*hi:+.2f})')

# realized per-share for reclassified (at actual ledger fill)
xs=[]
for row in classes['rich_entered_later']:
    for t in row['ledger']:
        if t.get('shares'): xs.append(t['pnl']/t['shares'])
print(f'rich_entered_later REALIZED: n={len(xs)} mean={100*sum(xs)/len(xs):+.2f}c/sh wins={sum(1 for x in xs if x>0)}')

# operated flagship book per-share (all impulse_v2 settled)
xs=[t['pnl']/t['shares'] for t in iv2 if t.get('shares') and t['status']=='settled']
sett=[t for t in iv2 if t['status']=='settled']
print(f'operated impulse_v2 (all settled): n={len(xs)} mean={100*sum(xs)/len(xs):+.2f}c/sh totalPnL={sum(t["pnl"] for t in sett):+.2f}')
# share-weighted
tot_sh=sum(t['shares'] for t in sett); tot_pnl=sum(t['pnl'] for t in sett)
print(f'  share-weighted: {100*tot_pnl/tot_sh:+.2f}c/sh over {tot_sh:.0f} shares')

# how many impulse_v2 ledger entries in the measure window are NOT in measure book?
t0s={r['t0'] for r in measure}
extra=[t for t in iv2 if t['t0'] not in t0s]
tmin=min(r['t0'] for r in measure); tmax=max(r['t0'] for r in measure)
extra_in_window=[t for t in extra if tmin<=t['t0']<=tmax]
print(f'impulse_v2 trades NOT in measure book: {len(extra)} total, {len(extra_in_window)} inside measure t0 window [{tmin},{tmax}]')
for t in extra_in_window[:15]: print('  ', t['t0'], t['side'], t['entry'], t['entrySec'], t['result'], t.get('guards'))
EOF_MARKER=None
