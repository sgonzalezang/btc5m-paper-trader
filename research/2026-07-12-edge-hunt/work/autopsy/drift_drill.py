#!/usr/bin/env python3
"""Drill into the drift-lag cell: mom drift>=4bps, ask-band 60-65c, EV +14c.
1) dedupe by (t0,side); engine mix; era split; entrySec distribution
2) q as f(entrySec, drift) on the ledger, dedup
3) independent candle check (cb1m): P(close dir = drift dir | drift at t seconds), Jun 26-Jul 13
4) what the market charged (ledger ask) vs candle-fair q, by (elapsed, drift) cell
Appends 'drift_drill' to results.json."""
import json, math, random, collections, os

HERE = os.path.dirname(os.path.abspath(__file__))
D12 = os.path.join(HERE, '..', '..', 'data')

def fee_ps(p): return 0.07*p*(1-p)
def qstar(p):  return p + fee_ps(p)
def wilson(k,n,z=1.96):
    if n==0: return (0.0,1.0)
    ph=k/n; d=1+z*z/n; c=ph+z*z/(2*n); h=z*math.sqrt(ph*(1-ph)/n+z*z/(4*n*n))
    return ((c-h)/d,(c+h)/d)
def bboot(items, valfn, keyfn, B=4000, seed=23):
    blocks=collections.defaultdict(list)
    for t in items: blocks[keyfn(t)].append(valfn(t))
    bl=list(blocks.values()); rng=random.Random(seed)
    flat=[v for b in bl for v in b]
    if not flat: return None
    mu=sum(flat)/len(flat); st=[]
    for _ in range(B):
        s=c=0
        for _ in range(len(bl)):
            b=bl[rng.randrange(len(bl))]; s+=sum(b); c+=len(b)
        if c: st.append(s/c)
    st.sort()
    return dict(mean=round(mu,4), ci95=[round(st[int(.025*len(st))],4),round(st[int(.975*len(st))],4)],
                p_le0=round(sum(1 for x in st if x<=0)/len(st),4), n=len(flat), n_blocks=len(bl))

tr=json.load(open(os.path.join(D12,'trades_unified.json')))
S=[t for t in tr if t.get('status')=='settled' and t.get('result') in ('win','loss')]
MOM={'loose','floor','band','value','fade','strict','capless','calm'}
for t in S:
    t['w']=1.0 if t['result']=='win' else 0.0
    t['p']=t['entry']
    d=(t['btcEntry']-t['btcOpen'])/t['btcOpen']*1e4
    t['sdrift']=d if t['side']=='up' else -d
    t['ev_ps']=t['w']-t['p']-fee_ps(t['p'])
mom=[t for t in S if t['eng'] in MOM]
out={}

# ---- 1. the cell, deduped
cell=[t for t in mom if t['sdrift']>=4 and 0.60<=t['p']<0.65]
dd={}
for t in cell: dd.setdefault((t['t0'],t['side']),[]).append(t)
uniq=[v[0] for v in dd.values()]
k=sum(int(t['w']) for t in uniq); n=len(uniq)
lo,hi=wilson(k,n)
out['cell_dedup']=dict(n_trades=len(cell), n_unique=n, wins=k, q=round(k/n,4),
                       p_mean=round(sum(t['p'] for t in uniq)/n,4),
                       qstar=round(sum(qstar(t['p']) for t in uniq)/n,4),
                       ev_c=round(100*sum(t['ev_ps'] for t in uniq)/n,2),
                       q_ci95=[round(lo,4),round(hi,4)])
out['cell_dedup_boot']=bboot(uniq, lambda t:t['ev_ps'], lambda t:t['t0']//3600)
out['cell_engine_mix']=dict(collections.Counter(t['eng'] for t in cell))
es=sorted((t.get('entrySec') or 0) for t in uniq)
out['cell_entrySec']=dict(p10=es[int(.1*n)],p50=es[n//2],p90=es[int(.9*n)])
# era split (day granularity)
days=collections.defaultdict(lambda:[0,0])
for t in uniq:
    import datetime
    d0=datetime.datetime.fromtimestamp(t['t0'],datetime.timezone.utc).strftime('%m-%d')
    days[d0][0]+=int(t['w']); days[d0][1]+=1
out['cell_by_day']={k2:f"{v[0]}/{v[1]}" for k2,v in sorted(days.items())}

# ---- 2. ledger q by (entrySec bucket, drift bucket), momentum family, dedup by (t0,side)
ddm={}
for t in mom: ddm.setdefault((t['t0'],t['side']),[]).append(t)
um=[v[0] for v in ddm.values()]
def esb(s):
    s=s or 0
    return '<60' if s<60 else '60-150' if s<150 else '150-240' if s<240 else '>=240'
def db(d):
    return '<2' if d<2 else '2-4' if d<4 else '4-8' if d<8 else '>=8'
tab=collections.defaultdict(lambda:[0,0,0.0,0.0])
for t in um:
    key=(esb(t.get('entrySec')), db(t['sdrift']))
    r=tab[key]; r[0]+=int(t['w']); r[1]+=1; r[2]+=t['p']; r[3]+=t['ev_ps']
grid={}
for (e,d),(kk,nn,ps,evs) in sorted(tab.items()):
    if nn>=10:
        grid[f"sec{e}|drift{d}"]=dict(n=nn,q=round(kk/nn,4),p_mean=round(ps/nn,4),ev_c=round(100*evs/nn,2))
out['mom_grid_dedup']=grid

# ---- 3. candle-based gross continuation, cb1m Jun26-Jul13 (no ledger involvement)
cb=json.load(open(os.path.join(D12,'cb1m.json')))
T,O=cb['t'],cb['o']
idx={t:i for i,t in enumerate(T)}
res_cont=collections.defaultdict(lambda:[0,0])   # (elapsed_min, driftbucket) -> [cont wins, n]
for i,t0 in enumerate(T):
    if t0%300: continue
    if t0+300 not in idx: continue
    o0=O[idx[t0]]; o5=O[idx[t0+300]]
    outcome_up = o5>=o0   # tie -> Up per rule
    for m in (1,2,3,4):
        if t0+60*m not in idx: continue
        om=O[idx[t0+60*m]]
        drift=(om-o0)/o0*1e4
        adrift=abs(drift)
        dirup=drift>0
        if adrift<1e-9: continue
        b=db(adrift)
        cont = (outcome_up==dirup)
        r=res_cont[(m,b)]; r[0]+=int(cont); r[1]+=1
cand={}
for (m,b),(kk,nn) in sorted(res_cont.items()):
    lo2,hi2=wilson(kk,nn)
    cand[f"min{m}|drift{b}"]=dict(n=nn,q_cont=round(kk/nn,4),ci95=[round(lo2,4),round(hi2,4)])
out['candle_continuation_jun26_jul13']=cand

# ---- 4. market charge vs candle-fair, per (elapsed,drift) cell — mom ledger dedup
mkt=collections.defaultdict(lambda:[0.0,0])
for t in um:
    m=min(4,max(1,int((t.get('entrySec') or 0)//60)))
    key=(m,db(t['sdrift']))
    if t['sdrift']>=2:      # only where side==drift direction meaningfully
        r=mkt[key]; r[0]+=t['p']; r[1]+=1
charge={}
for key,(ps,nn) in sorted(mkt.items()):
    if nn>=10:
        m,b=key
        fair=cand.get(f"min{m}|drift{b}")
        charge[f"min{m}|drift{b}"]=dict(n_ledger=nn, ask_plus_slip_mean=round(ps/nn,4),
                                        candle_q_cont=fair['q_cont'] if fair else None,
                                        implied_edge_c=round(100*((fair['q_cont'] if fair else 0)-ps/nn-fee_ps(ps/nn)),2) if fair else None)
out['market_charge_vs_candle_fair']=charge

# ---- 5. the negative twin: drift>=4bps but ask 50-60c — early entries?
twin=[t for t in um if t['sdrift']>=4 and 0.50<=t['p']<0.60]
es2=sorted((t.get('entrySec') or 0) for t in twin)
out['twin_5060_entrySec']=dict(n=len(twin), p50=es2[len(es2)//2] if twin else None)

res_path=os.path.join(HERE,'results.json')
res=json.load(open(res_path)); res['drift_drill']=out
json.dump(res,open(res_path,'w'),indent=1)
print(json.dumps(out,indent=1))
