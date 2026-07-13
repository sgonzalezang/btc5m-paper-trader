#!/usr/bin/env python3
"""Final drills:
A) Pre-registered-style deployable rule on the ledger: momentum-side fill when
   sdrift>=4bps, any entrySec, p=ask+slip<=0.66 (i.e., all cap-compliant momentum fills),
   dedup by (t0,side). q, EV, 1h-block boot. Plus 60-65c concentration note.
B) Candle continuation era split: Jun26-Jul2 / Jul3-Jul9 / Jul10-13 (stability of gross rate).
C) pm_prices_sample join with cb1m drift: market charge for the drift side at 60s/150s
   vs realized win rate — independent (non-ledger) pricing check, n=216 markets.
D) rev-family 50-53c toxic zone: what does it look like on candles? contrarian entries
   at 50-53c are fading a >=12bps move; check candle reversal rate Jun26-Jul13 for
   context (not fit).
Appends 'deploy_rule' to results.json."""
import json, math, random, collections, os, datetime

HERE=os.path.dirname(os.path.abspath(__file__))
D12=os.path.join(HERE,'..','..','data')
D10=os.path.join(HERE,'..','..','..','2026-07-10-edge-hunt','data')

def fee_ps(p): return 0.07*p*(1-p)
def qstar(p):  return p+fee_ps(p)
def wilson(k,n,z=1.96):
    if n==0: return (0.0,1.0)
    ph=k/n; d=1+z*z/n; c=ph+z*z/(2*n); h=z*math.sqrt(ph*(1-ph)/n+z*z/(4*n*n))
    return ((c-h)/d,(c+h)/d)
def bboot(items,valfn,B=4000,seed=31):
    blocks=collections.defaultdict(list)
    for t in items: blocks[t['t0']//3600].append(valfn(t))
    bl=list(blocks.values()); rng=random.Random(seed)
    flat=[v for b in bl for v in b]
    mu=sum(flat)/len(flat); st=[]
    for _ in range(B):
        s=c=0
        for _ in range(len(bl)):
            b=bl[rng.randrange(len(bl))]; s+=sum(b); c+=len(b)
        if c: st.append(s/c)
    st.sort()
    return dict(mean=round(mu,4),ci95=[round(st[int(.025*len(st))],4),round(st[int(.975*len(st))],4)],
                p_le0=round(sum(1 for x in st if x<=0)/len(st),4),n=len(flat),n_blocks=len(bl))

tr=json.load(open(os.path.join(D12,'trades_unified.json')))
S=[t for t in tr if t.get('status')=='settled' and t.get('result') in ('win','loss')]
MOM={'loose','floor','band','value','fade','strict','capless','calm'}
for t in S:
    t['w']=1.0 if t['result']=='win' else 0.0
    t['p']=t['entry']
    d=(t['btcEntry']-t['btcOpen'])/t['btcOpen']*1e4
    t['sdrift']=d if t['side']=='up' else -d
    t['ev_ps']=t['w']-t['p']-fee_ps(t['p'])
out={}

# ---- A. deployable momentum-tail rule, all fills (no ask-band cherry-pick)
mom=[t for t in S if t['eng'] in MOM]
dd={}
for t in mom: dd.setdefault((t['t0'],t['side']),[]).append(t)
um=[v[0] for v in dd.values()]
rule=[t for t in um if t['sdrift']>=4]
k=sum(int(t['w']) for t in rule); n=len(rule)
lo,hi=wilson(k,n)
out['ruleA_all']=dict(n=n,wins=k,q=round(k/n,4),p_mean=round(sum(t['p'] for t in rule)/n,4),
                      qstar=round(sum(qstar(t['p']) for t in rule)/n,4),
                      ev_c=round(100*sum(t['ev_ps'] for t in rule)/n,2),
                      q_ci95=[round(lo,4),round(hi,4)])
out['ruleA_boot']=bboot(rule,lambda t:t['ev_ps'])
out['ruleA_price_mix']=dict(collections.Counter(f"{int(t['p']*100)//5*5}" for t in rule))
by_day=collections.defaultdict(lambda:[0,0,0.0])
for t in rule:
    d0=datetime.datetime.fromtimestamp(t['t0'],datetime.timezone.utc).strftime('%m-%d')
    by_day[d0][0]+=int(t['w']); by_day[d0][1]+=1; by_day[d0][2]+=t['ev_ps']
out['ruleA_by_day']={k2:dict(wins=v[0],n=v[1],ev_c=round(100*v[2]/v[1],2)) for k2,v in sorted(by_day.items())}
# and with the 60c floor (the concentrated version) for comparison, stated as best-of-2
rule2=[t for t in rule if t['p']>=0.60]
k2_=sum(int(t['w']) for t in rule2); n2=len(rule2)
out['ruleA_p_ge60']=dict(n=n2,wins=k2_,q=round(k2_/n2,4),
                         ev_c=round(100*sum(t['ev_ps'] for t in rule2)/n2,2))
out['ruleA_boot_ge60']=bboot(rule2,lambda t:t['ev_ps'],seed=37)

# ---- B. candle continuation era split
cb=json.load(open(os.path.join(D12,'cb1m.json')))
T,O=cb['t'],cb['o']
idx={t:i for i,t in enumerate(T)}
def era3(t0):
    d=datetime.datetime.fromtimestamp(t0,datetime.timezone.utc)
    if d < datetime.datetime(2026,7,3,tzinfo=datetime.timezone.utc): return 'jun26-jul2'
    if d < datetime.datetime(2026,7,10,tzinfo=datetime.timezone.utc): return 'jul3-jul9'
    return 'jul10-13'
cont=collections.defaultdict(lambda:[0,0])
for t0 in T:
    if t0%300: continue
    if t0+300 not in idx or t0+60 not in idx: continue
    o0=O[idx[t0]]; o5=O[idx[t0+300]]; o1=O[idx[t0+60]]
    dr=(o1-o0)/o0*1e4
    if abs(dr)<4: continue
    c=( (o5>=o0) == (dr>0) )
    r=cont[era3(t0)]; r[0]+=int(c); r[1]+=1
out['candle_min1_ge4bps_era']={k3:dict(n=v[1],q_cont=round(v[0]/v[1],4),
                                       ci95=[round(x,4) for x in wilson(v[0],v[1])]) for k3,v in sorted(cont.items())}

# ---- C. pm_prices join: what the market charges for the drift side at 60s/150s
pm=json.load(open(os.path.join(D10,'pm_prices_sample.json')))
rows=collections.defaultdict(lambda:[0,0,0.0])   # (snap,driftbucket) -> [wins, n, sum charge]
def db(a):
    return '<2' if a<2 else '2-4' if a<4 else '4-8' if a<8 else '>=8'
for mkt in pm:
    t0=mkt['t0']
    if t0 not in idx or t0+300 not in idx: continue
    o0=O[idx[t0]]
    for snap,sec in [('p60',60),('p150',150)]:
        tm=t0+sec-(sec%60)   # drift known at the last full minute <= snap time
        if snap=='p60': tm=t0+60
        else: tm=t0+120      # for p150 use 2min drift (strictly before 150s)
        if tm not in idx: continue
        om=O[idx[tm]]
        dr=(om-o0)/o0*1e4
        if abs(dr)<1e-9: continue
        pdrift = mkt[snap] if dr>0 else 1.0-mkt[snap]   # price of the drift side
        won = (mkt['up_won']==1)==(dr>0)
        r=rows[(snap,db(abs(dr)))]
        r[0]+=int(won); r[1]+=1; r[2]+=pdrift
pmj={}
for (snap,b),(kk,nn,ps) in sorted(rows.items()):
    if nn>=10:
        charge=ps/nn
        lo3,hi3=wilson(kk,nn)
        pmj[f"{snap}|drift{b}"]=dict(n=nn,market_charge_driftside=round(charge,4),
                                     realized_q=round(kk/nn,4),q_ci95=[round(lo3,4),round(hi3,4)],
                                     ev_after_fee_c=round(100*(kk/nn-charge-0.01-fee_ps(charge+0.01)),2),
                                     note='charge=snapshot mid-ish price of drift side; +1c slip applied in EV')
out['pm_prices_join']=pmj

# ---- D. context: candle reversal rate after >=12bps prior move when current px ~50-53c zone
# (the rev-family 50-53c fills are fades of a >=12bps move where the market prices the fade side ~50-52c ask)
rev=collections.defaultdict(lambda:[0,0])
for t0 in T:
    if t0%300: continue
    if t0-300 not in idx or t0 not in idx or t0+300 not in idx: continue
    op=O[idx[t0-300]]; o0=O[idx[t0]]; o5=O[idx[t0+300]]
    pm_=(o0-op)/op*1e4
    if abs(pm_)<12: continue
    rv=((o5>=o0) != (pm_>0)) if pm_>0 else ((o5>=o0)==(pm_<0))
    # reversal = next interval moves opposite to prior move; ties->Up handled via >=
    nxt_up = o5>=o0
    rv = (nxt_up if pm_<0 else (not nxt_up))
    r=rev[era3(t0)]; r[0]+=int(rv); r[1]+=1
out['candle_reversal_ge12_era']={k4:dict(n=v[1],q_rev=round(v[0]/v[1],4)) for k4,v in sorted(rev.items())}

res_path=os.path.join(HERE,'results.json')
res=json.load(open(res_path)); res['deploy_rule']=out
json.dump(res,open(res_path,'w'),indent=1)
print(json.dumps(out,indent=1))
