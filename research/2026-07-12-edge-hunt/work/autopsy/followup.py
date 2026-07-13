#!/usr/bin/env python3
"""Follow-up drills on the autopsy: cap-zone split, impulse50 vs impulse_v2 paired,
side split at the money (tie rule), momentum drift-lag scan, 45-50c bootstrap,
per-engine decomposition table. Stdlib only. Appends to results.json as 'followup'."""
import json, math, random, collections, os

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, '..', '..', 'data', 'trades_unified.json')

def fee_ps(p):  return 0.07*p*(1-p)
def qstar(p):   return p + fee_ps(p)
def wilson(k, n, z=1.96):
    if n == 0: return (0.0, 1.0)
    ph = k/n; d = 1+z*z/n; c = ph+z*z/(2*n)
    h = z*math.sqrt(ph*(1-ph)/n + z*z/(4*n*n))
    return ((c-h)/d, (c+h)/d)

def bboot(trades, valfn, B=4000, seed=17):
    blocks = collections.defaultdict(list)
    for t in trades: blocks[t['t0']//3600].append(valfn(t))
    bl = list(blocks.values()); rng = random.Random(seed)
    flat = [v for b in bl for v in b]
    if not flat: return None
    mu = sum(flat)/len(flat); stats=[]
    for _ in range(B):
        s=c=0
        for _ in range(len(bl)):
            b = bl[rng.randrange(len(bl))]; s += sum(b); c += len(b)
        if c: stats.append(s/c)
    stats.sort()
    return dict(mean=round(mu,4), ci95=[round(stats[int(.025*len(stats))],4), round(stats[int(.975*len(stats))],4)],
                p_le0=round(sum(1 for x in stats if x<=0)/len(stats),4), n=len(flat), n_blocks=len(bl))

tr = json.load(open(DATA))
S = [t for t in tr if t.get('status')=='settled' and t.get('result') in ('win','loss')]
for t in S:
    t['w'] = 1.0 if t['result']=='win' else 0.0
    t['p'] = t['entry']
    d = (t['btcEntry']-t['btcOpen'])/t['btcOpen']*1e4
    t['sdrift'] = d if t['side']=='up' else -d
    t['ev_ps'] = t['w'] - t['p'] - fee_ps(t['p'])
MOM = {'loose','floor','band','value','fade','strict','capless','calm'}
REV = {'reversal','reversal2','latentfire','reversal_v2','impulse50','impulse_v2'}
out = {}

def stat(ts, label):
    n=len(ts)
    if n==0: return dict(label=label, n=0)
    k=sum(int(t['w']) for t in ts); q=k/n
    pbar=sum(t['p'] for t in ts)/n; qs=sum(qstar(t['p']) for t in ts)/n
    ev=sum(t['ev_ps'] for t in ts)/n
    lo,hi=wilson(k,n)
    return dict(label=label, n=n, wins=k, q=round(q,4), p_mean=round(pbar,4), qstar=round(qs,4),
                ev_c=round(100*ev,2), q_ci95=[round(lo,4),round(hi,4)])

# ---- 1. cap-zone split within reversal family: 50-53 vs 53-55 vs 55-60
rev = [t for t in S if t['eng'] in REV]
out['capzone_rev'] = [stat([t for t in rev if a<=t['p']<b], f"rev {a:.2f}-{b:.2f}")
                      for a,b in [(0.50,0.53),(0.53,0.55),(0.55,0.60)]]
out['capzone_rev_boot_50_53'] = bboot([t for t in rev if 0.50<=t['p']<0.53], lambda t:t['ev_ps'])
mom = [t for t in S if t['eng'] in MOM]
out['capzone_mom'] = [stat([t for t in mom if a<=t['p']<b], f"mom {a:.2f}-{b:.2f}")
                      for a,b in [(0.50,0.53),(0.53,0.55)]]
out['capzone_pooled_50_53'] = stat([t for t in S if 0.50<=t['p']<0.53], 'pooled 0.50-0.53')
out['capzone_pooled_boot_50_53'] = bboot([t for t in S if 0.50<=t['p']<0.53], lambda t:t['ev_ps'])

# ---- 2. impulse50 vs impulse_v2 paired: the hi-bucket / f<=0 skips
i50 = {t['t0']: t for t in S if t['eng']=='impulse50'}
iv2 = {t['t0']: t for t in S if t['eng']=='impulse_v2'}
only50 = [t for k,t in i50.items() if k not in iv2]
both   = [k for k in i50 if k in iv2]
out['impulse50_only'] = stat(only50, 'impulse50 trades skipped by impulse_v2 (f_full<=0 / hi bucket)')
out['impulse50_only_detail'] = [dict(t0=t['t0'], p=t['p'], side=t['side'], w=t['w'], ev_c=round(100*t['ev_ps'],2)) for t in sorted(only50, key=lambda x:x['t0'])]
out['impulse_common_n'] = len(both)
out['impulse_v2_stat'] = stat(list(iv2.values()), 'impulse_v2 all')
out['impulse50_stat'] = stat(list(i50.values()), 'impulse50 all')
iv2_only = [t for k,t in iv2.items() if k not in i50]
out['impulse_v2_only'] = stat(iv2_only, 'impulse_v2 trades with no impulse50 twin')

# ---- 3. side split at the money (tie rule): 48-52c fills
for lo_,hi_,tag in [(0.48,0.52,'48-52'),(0.50,0.55,'50-55'),(0.45,0.50,'45-50')]:
    band=[t for t in S if lo_<=t['p']<hi_]
    up=[t for t in band if t['side']=='up']; dn=[t for t in band if t['side']=='down']
    su,sd=stat(up,f'up {tag}'),stat(dn,f'down {tag}')
    qu,qd=su['q'],sd['q']
    var=qu*(1-qu)/su['n']+qd*(1-qd)/sd['n']
    out[f'side_{tag}']=dict(up=su,down=sd,z_up_minus_down=round((qu-qd)/math.sqrt(var),2))

# ---- 4. momentum drift-lag scan: does any (drift, price) region clear fees?
# K = 8 cells reported; count them as the multiplicity.
cells=[]
for dmin in [4, 8]:
    for a,b in [(0.50,0.55),(0.55,0.60),(0.60,0.65),(0.65,0.75)]:
        ts=[t for t in mom if t['sdrift']>=dmin and a<=t['p']<b]
        s=stat(ts,f'mom drift>={dmin}bps p {a:.2f}-{b:.2f}')
        if s['n']>=30:
            s['boot']=bboot(ts, lambda t:t['ev_ps'], seed=int(dmin*100+a*100))
        cells.append(s)
out['mom_driftlag_scan_K8']=cells
# adverse side for contrast
out['mom_adverse_all']=stat([t for t in mom if t['sdrift']<=-4],'mom drift<=-4bps all prices')

# ---- 5. pooled 45-50c bucket bootstrap + per-side + dedupe + era split
b4550=[t for t in S if 0.45<=t['p']<0.50]
out['pooled_4550_boot']=bboot(b4550, lambda t:t['ev_ps'])
out['pooled_4550_up']=stat([t for t in b4550 if t['side']=='up'],'45-50 up')
out['pooled_4550_down']=stat([t for t in b4550 if t['side']=='down'],'45-50 down')
dd={}
for t in b4550: dd.setdefault((t['t0'],t['side']),t)
out['pooled_4550_dedup']=stat(list(dd.values()),'45-50 dedup by (t0,side)')
out['pooled_4550_dedup_boot']=bboot(list(dd.values()), lambda t:t['ev_ps'])
V3_T0=max(t['t0'] for t in S if t['eng']=='loose')
out['pooled_4550_v3era']=stat([t for t in b4550 if t['t0']>V3_T0],'45-50 v3 era only')
out['pooled_4550_preera']=stat([t for t in b4550 if t['t0']<=V3_T0],'45-50 pre era')

# ---- 6. per-engine decomposition compact table (for the report)
def decomp_row(ts):
    sh=sum(t['shares'] for t in ts)
    q=sum(t['shares']*t['w'] for t in ts)/sh
    p=sum(t['shares']*t['p'] for t in ts)/sh
    ask=sum(t['shares']*t['ask'] for t in ts)/sh
    fees=sum(t['shares']*fee_ps(t['p']) for t in ts)
    model=sum(t['shares']*t['ev_ps']-0.004 for t in ts)
    at_ask=sum(t['shares']*(t['w']-t['ask']-fee_ps(t['ask']))-0.004 for t in ts)
    at_mid=sum(t['shares']*(t['w']-(t['ask']-0.005)-fee_ps(t['ask']-0.005))-0.004 for t in ts)
    return dict(n=len(ts), pnl=round(sum(t['pnl'] for t in ts),2), pnl_model=round(model,2),
                pnl_at_ask=round(at_ask,2), pnl_at_mid=round(at_mid,2), fees=round(fees,2),
                q_sw=round(q,4), p_sw=round(p,4), sel_mid_c=round(100*(q-(ask-0.005)),2),
                net_c=round(100*model/sh,2))
eng_rows={}
for e in sorted(set(t['eng'] for t in S)):
    eng_rows[e]=decomp_row([t for t in S if t['eng']==e])
out['per_engine_decomp']=eng_rows

# ---- 7. rev-family strong-adverse-drift cell (<-6bps, cheap) sanity: not multiple-tested away
cell=[t for t in rev if t['sdrift']<-6 and t['p']<=0.53]
out['rev_strong_adverse_cheap']=stat(cell,'rev sdrift<-6bps p<=53c')
if len(cell)>=15: out['rev_strong_adverse_cheap_boot']=bboot(cell, lambda t:t['ev_ps'])

# ---- 8. how much of momentum-family loss is the 50-60c zone?
z=[t for t in mom if 0.50<=t['p']<0.60]
out['mom_5060_model_loss']=round(sum(t['shares']*t['ev_ps']-0.004 for t in z),2)
out['mom_5060_n']=len(z)

res_path=os.path.join(HERE,'results.json')
res=json.load(open(res_path))
res['followup']=out
json.dump(res, open(res_path,'w'), indent=1)
print(json.dumps(out, indent=1))
