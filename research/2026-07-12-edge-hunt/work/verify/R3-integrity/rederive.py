#!/usr/bin/env python3
"""Adversarial re-derivation of FINDING R3 (drift-leader stale-ask capture, 60-65c band)
from RAW data only. Integrity checks:
 1. rebuild cell + ruleA from trades_unified raw
 2. per-trade guard flags in the cell (Fresh / Depth / Stable2tick / Window / Spread)
 3. settlement cross-check vs cb1m candles; settledBy mix; tie handling
 4. duplicate detection across _src merges
 5. epoch/entrySec consistency; btcEntry vs its own minute candle (lookahead test)
 6. survivorship: state_extract lifetime totals vs ledger counts; recovered-vs-live win rates
 7. fillFrac / stake in the cell
 8. reconcile with pooled 60-66c momentum fills
 9. dedup-representative sensitivity
10. own 1h-block bootstrap (fresh code, fresh seeds)
11. out-of-era qualifying trades (v3 era, any engine)
12. ask responsiveness to drift (staleness quantification)
13. pm_prices_sample same-market comparison of bot ask vs snapshot price
Writes results.json in this dir.
"""
import json, math, random, collections, datetime, os

HERE = os.path.dirname(os.path.abspath(__file__))
D12 = '/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data'
D10 = '/Users/sgonzalez/btc5m-paper-trader/research/2026-07-10-edge-hunt/data'

def fee_ps(p): return 0.07*p*(1-p)
def qstar(p): return p+fee_ps(p)
def wilson(k,n,z=1.96):
    if n==0: return (0.0,1.0)
    ph=k/n; d=1+z*z/n; c=ph+z*z/(2*n); h=z*math.sqrt(ph*(1-ph)/n+z*z/(4*n*n))
    return ((c-h)/d,(c+h)/d)
def bboot(items,valfn,B=6000,seed=101):
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

out={}
tr=json.load(open(os.path.join(D12,'trades_unified.json')))
cb=json.load(open(os.path.join(D12,'cb1m.json')))
T,O,H,L,C=cb['t'],cb['o'],cb['h'],cb['l'],cb['c']
idx={t:i for i,t in enumerate(T)}

# ---------- 4. duplicates ----------
keys=collections.Counter((t['t0'],t.get('eng'),t.get('side')) for t in tr)
dups={str(k):v for k,v in keys.items() if v>1}
at_dups=collections.Counter(t['at'] for t in tr)
out['dup_t0_eng_side']=dict(n_dup_keys=len(dups), examples=dict(list(dups.items())[:5]))
out['dup_at_ms']=sum(1 for v in at_dups.values() if v>1)

S=[t for t in tr if t.get('status')=='settled' and t.get('result') in ('win','loss')]
MOM={'loose','floor','band','value','fade','strict','capless','calm'}
for t in S:
    t['w']=1.0 if t['result']=='win' else 0.0
    t['p']=t['entry']
    d=(t['btcEntry']-t['btcOpen'])/t['btcOpen']*1e4
    t['sdrift']=d if t['side']=='up' else -d
    t['ev_ps']=t['w']-t['p']-fee_ps(t['p'])
out['n_settled_winloss']=len(S)
other_status=collections.Counter(t.get('status') for t in tr if t.get('status')!='settled')
other_result=collections.Counter(t.get('result') for t in tr if t.get('status')=='settled' and t.get('result') not in('win','loss'))
out['excluded']=dict(status=dict(other_status), settled_other_result=dict(other_result))

mom=[t for t in S if t['eng'] in MOM]

# ---------- 5. epoch / entrySec / btcEntry lookahead ----------
bad_es=0; es_diffs=[]
be_in_cur=0; be_in_next_only=0; be_nowhere=0; be_checked=0
bo_match=0; bo_off=0; bo_checked=0
for t in S:
    es_calc=int(round(t['at']/1000-t['t0']))
    es_diffs.append(abs(es_calc-(t.get('entrySec') or 0)))
    if abs(es_calc-(t.get('entrySec') or 0))>2: bad_es+=1
    # btcEntry vs candle range of the minute containing 'at' (feed can be ~15s stale -> also allow prev minute)
    if t.get('feed')=='Coinbase' and t.get('btcEntry'):
        m0=(int(t['at']/1000)//60)*60
        rng=[m for m in (m0,m0-60) if m in idx]
        nxt=[m for m in (m0+60,m0+120) if m in idx]
        if rng:
            be_checked+=1
            tol=1e-4*t['btcEntry']  # 1bp tolerance
            in_cur=any(L[idx[m]]-tol<=t['btcEntry']<=H[idx[m]]+tol for m in rng)
            in_nxt=any(L[idx[m]]-tol<=t['btcEntry']<=H[idx[m]]+tol for m in nxt)
            if in_cur: be_in_cur+=1
            elif in_nxt: be_in_next_only+=1
            else: be_nowhere+=1
    if t.get('feed')=='Coinbase' and t.get('btcOpen') and t['t0'] in idx:
        bo_checked+=1
        if abs(t['btcOpen']-O[idx[t['t0']]])/O[idx[t['t0']]]<2e-4: bo_match+=1
        else: bo_off+=1
out['entrySec_consistency']=dict(n=len(S), max_abs_diff=max(es_diffs), n_diff_gt2s=bad_es)
out['btcEntry_candle_check']=dict(checked=be_checked, in_current_or_prev_min=be_in_cur,
                                  only_in_future_min=be_in_next_only, in_neither=be_nowhere)
out['btcOpen_vs_cb1m']=dict(checked=bo_checked, within_2bps=bo_match, off=bo_off)

# ---------- 3. settlement cross-check ----------
def cb_outcome(t0):
    if t0 in idx and t0+300 in idx:
        o0,o5=O[idx[t0]],O[idx[t0+300]]
        if o5==o0: return 'tie'
        return 'up' if o5>o0 else 'down'
    return None
agree=disagree=tie=nocover=0
disagree_list=[]
for t in mom:
    oc=cb_outcome(t['t0'])
    if oc is None: nocover+=1; continue
    if oc=='tie': tie+=1; continue
    won_cb=(oc==t['side'])
    if won_cb==(t['w']==1.0): agree+=1
    else:
        disagree+=1
        disagree_list.append(dict(t0=t['t0'],side=t['side'],res=t['result'],settledBy=t.get('settledBy')))
out['settlement_cb_crosscheck_mom']=dict(agree=agree,disagree=disagree,tie=tie,no_candle=nocover,
                                         disagree_sample=disagree_list[:8])

# ---------- 1. rebuild cell & ruleA ----------
cell=[t for t in mom if t['sdrift']>=4 and 0.60<=t['p']<0.65]
dd={}
for t in cell: dd.setdefault((t['t0'],t['side']),[]).append(t)
uniq=[v[0] for v in dd.values()]
k=sum(int(t['w']) for t in uniq); n=len(uniq)
out['cell_rebuilt']=dict(n_trades=len(cell),n_unique=n,wins=k,q=round(k/n,4),
                         p_mean=round(sum(t['p'] for t in uniq)/n,4),
                         ev_c=round(100*sum(t['ev_ps'] for t in uniq)/n,2),
                         q_ci95=[round(x,4) for x in wilson(k,n)])
out['cell_boot']=bboot(uniq,lambda t:t['ev_ps'],seed=7)
out['cell_settledBy']=dict(collections.Counter(t.get('settledBy') for t in uniq))
out['cell_src']=dict(collections.Counter(t.get('_src') for t in uniq))
out['cell_feed']=dict(collections.Counter(t.get('feed') for t in uniq))
# settlement crosscheck within cell
ca=cd=ct=cn=0
for t in uniq:
    oc=cb_outcome(t['t0'])
    if oc is None: cn+=1
    elif oc=='tie': ct+=1
    elif (oc==t['side'])==(t['w']==1.0): ca+=1
    else: cd+=1
out['cell_settle_cb']=dict(agree=ca,disagree=cd,tie=ct,no_candle=cn)

# ruleA (unbanded): momentum dedup, sdrift>=4
ddm={}
for t in mom: ddm.setdefault((t['t0'],t['side']),[]).append(t)
um=[v[0] for v in ddm.values()]
rule=[t for t in um if t['sdrift']>=4]
k2=sum(int(t['w']) for t in rule); n2=len(rule)
out['ruleA_rebuilt']=dict(n=n2,wins=k2,q=round(k2/n2,4),ev_c=round(100*sum(t['ev_ps'] for t in rule)/n2,2))
out['ruleA_boot']=bboot(rule,lambda t:t['ev_ps'],seed=11)
r60=[t for t in rule if t['p']>=0.60]
k3=sum(int(t['w']) for t in r60); n3=len(r60)
out['ruleA_ge60_rebuilt']=dict(n=n3,wins=k3,q=round(k3/n3,4),ev_c=round(100*sum(t['ev_ps'] for t in r60)/n3,2))
out['ruleA_ge60_boot']=bboot(r60,lambda t:t['ev_ps'],seed=13)

# ---------- 9. dedup sensitivity ----------
sens={}
for name,pick in [('first',lambda v:v[0]),('min_p',lambda v:min(v,key=lambda t:t['p'])),
                  ('max_p',lambda v:max(v,key=lambda t:t['p'])),('earliest_at',lambda v:min(v,key=lambda t:t['at']))]:
    u2=[pick(v) for v in dd.values()]
    # NB: for banded cell, membership was decided pre-dedup; keep same groups
    sens[name]=dict(ev_c=round(100*sum(t['ev_ps'] for t in u2)/len(u2),2),
                    p_mean=round(sum(t['p'] for t in u2)/len(u2),4))
# also filter-after-dedup ordering (the n=71 variant): dedup all mom, then band
alt=[t for t in um if t['sdrift']>=4 and 0.60<=t['p']<0.65]
ka=sum(int(t['w']) for t in alt)
sens['dedup_then_band']=dict(n=len(alt),wins=ka,q=round(ka/len(alt),4),
                             ev_c=round(100*sum(t['ev_ps'] for t in alt)/len(alt),2))
out['dedup_sensitivity']=sens

# ---------- 2. guard flags in the cell ----------
def gmap(t): return {k:v for k,v in (t.get('guards') or [])}
gstats=collections.defaultdict(lambda:[0,0])
for t in cell:
    g=gmap(t)
    for kk in ('Fresh','Depth>=min','Stable2tick','Window','Spread<=max','Move>=thr'):
        if kk in g:
            gstats[kk][0]+=g[kk]; gstats[kk][1]+=1
out['cell_guard_pass_rates']={k:dict(passed=v[0],n=v[1],rate=round(v[0]/v[1],3)) for k,v in gstats.items()}
# compare with momentum trades NOT in cell (same era)
gstats2=collections.defaultdict(lambda:[0,0])
noncell=[t for t in mom if not (t['sdrift']>=4 and 0.60<=t['p']<0.65)]
for t in noncell:
    g=gmap(t)
    for kk in ('Fresh','Depth>=min','Stable2tick','Window','Spread<=max','Move>=thr'):
        if kk in g:
            gstats2[kk][0]+=g[kk]; gstats2[kk][1]+=1
out['noncell_guard_pass_rates']={k:dict(rate=round(v[0]/v[1],3),n=v[1]) for k,v in gstats2.items()}

# ---------- 7. fill quality in cell ----------
ff=sorted(t.get('fillFrac') or 0 for t in uniq)
out['cell_fillFrac']=dict(p10=ff[int(.1*n)],p50=ff[n//2],p90=ff[int(.9*n)],
                          frac_full=round(sum(1 for x in ff if x>=0.999)/n,3))
sl=collections.Counter(t.get('slip') for t in uniq)
out['cell_slip']=dict(sl)
stk=sorted(t.get('stake') or 0 for t in uniq)
out['cell_stake_p50']=stk[n//2]

# ---------- 8. reconcile pooled 60-66c ----------
band66=[t for t in mom if 0.60<=t['p']<=0.66]
k4=sum(int(t['w']) for t in band66)
out['pooled_60_66_all']=dict(n=len(band66),q=round(k4/len(band66),4),
                             ev_c=round(100*sum(t['ev_ps'] for t in band66)/len(band66),2))
lo_d=[t for t in band66 if t['sdrift']<4]; hi_d=[t for t in band66 if t['sdrift']>=4]
out['pooled_60_66_split']=dict(
    drift_lt4=dict(n=len(lo_d),q=round(sum(t['w'] for t in lo_d)/len(lo_d),4),
                   ev_c=round(100*sum(t['ev_ps'] for t in lo_d)/len(lo_d),2)),
    drift_ge4=dict(n=len(hi_d),q=round(sum(t['w'] for t in hi_d)/len(hi_d),4),
                   ev_c=round(100*sum(t['ev_ps'] for t in hi_d)/len(hi_d),2)))

# ---------- 6. survivorship ----------
try:
    st=json.load(open(os.path.join(D12,'state_extract.json')))
    life=st.get('lifetime') or {}
    surv={}
    ledger_counts=collections.Counter(t.get('eng') for t in tr)
    for e in sorted(MOM|{'reversal','reversal2','latentfire'}):
        lf=life.get(e) or {}
        surv[e]=dict(ledger=ledger_counts.get(e,0), lifetime_trimmed=lf.get('trimmed'),
                     lifetime_settled=lf.get('settled'), lifetime_wins=lf.get('wins'))
    out['survivorship_lifetime_vs_ledger']=surv
except Exception as e:
    out['survivorship_lifetime_vs_ledger']=str(e)
# recovered vs live win rate, momentum family
bysrc=collections.defaultdict(lambda:[0,0])
for t in mom:
    r=bysrc[t.get('_src')]; r[0]+=int(t['w']); r[1]+=1
out['mom_winrate_by_src']={k:dict(n=v[1],q=round(v[0]/v[1],4)) for k,v in bysrc.items()}
# cell trades by day and src
cdd=collections.defaultdict(lambda:collections.Counter())
for t in uniq:
    d0=datetime.datetime.fromtimestamp(t['t0'],datetime.timezone.utc).strftime('%m-%d')
    cdd[d0][t.get('_src')]+=1
out['cell_day_src']={k:dict(v) for k,v in sorted(cdd.items())}

# ---------- 11. out-of-era qualifying trades (any engine, v3 era) ----------
V3=1783892700  # Jul 10 ~15:05 UTC approx; use trades after Jul 10 15:05 -> compute exact
v3cut=int(datetime.datetime(2026,7,10,15,5,tzinfo=datetime.timezone.utc).timestamp())
oo=[t for t in S if t['t0']>=v3cut and t['sdrift']>=4 and 0.60<=t['p']<0.65]
out['v3_era_qualifying']=dict(n=len(oo),
                              detail=[dict(eng=t['eng'],t0=t['t0'],p=t['p'],w=t['w']) for t in oo[:10]])
oo2=[t for t in S if t['t0']>=v3cut and t['sdrift']>=4]
out['v3_era_drift_ge4_anyprice']=dict(n=len(oo2),
                                      wins=sum(int(t['w']) for t in oo2),
                                      ev_c=round(100*sum(t['ev_ps'] for t in oo2)/len(oo2),2) if oo2 else None)

# ---------- 12. ask responsiveness to drift (staleness quantification) ----------
# momentum dedup, entrySec<60 only: mean entry price by drift bucket vs candle-fair q at 60s
def db(d): return '<2' if d<2 else '2-4' if d<4 else '4-8' if d<8 else '>=8'
resp=collections.defaultdict(lambda:[0.0,0,0])
for t in um:
    if (t.get('entrySec') or 0)<60 and t['sdrift']>=0:
        r=resp[db(t['sdrift'])]; r[0]+=t['p']; r[1]+=1; r[2]+=int(t['w'])
# candle fair at 60s per bucket (Jul 7-10 era only, matching cell)
e0=int(datetime.datetime(2026,7,7,tzinfo=datetime.timezone.utc).timestamp())
e1=int(datetime.datetime(2026,7,11,tzinfo=datetime.timezone.utc).timestamp())
fair=collections.defaultdict(lambda:[0,0])
for t0 in range(e0,e1,300):
    if t0 in idx and t0+60 in idx and t0+300 in idx:
        o0,o1,o5=O[idx[t0]],O[idx[t0+60]],O[idx[t0+300]]
        dr=(o1-o0)/o0*1e4
        if abs(dr)<1e-9: continue
        cont=((o5>=o0)==(dr>0))
        r=fair[db(abs(dr))]; r[0]+=int(cont); r[1]+=1
out['ask_response_sub60s']={b:dict(n=v[1],mean_entry=round(v[0]/v[1],4),ledger_q=round(v[2]/v[1],4),
                                   candle_fair_60s_jul7_10=(round(fair[b][0]/fair[b][1],4) if fair[b][1] else None))
                            for b,v in sorted(resp.items()) if v[1]>=10}

# ---------- 13. pm_prices_sample same-market ask comparison ----------
try:
    pm=json.load(open(os.path.join(D10,'pm_prices_sample.json')))
    pmt={m['t0']:m for m in pm}
    joins=[]
    for t in uniq:
        m=pmt.get(t['t0'])
        if not m: continue
        # snapshot price of the trade's side at 60s
        p60=m.get('p60')
        if p60 is None: continue
        side_p60=p60 if t['side']=='up' else round(1-p60,4)
        joins.append(dict(t0=t['t0'],side=t['side'],entrySec=t.get('entrySec'),bot_entry=t['p'],
                          snap_p60_side=side_p60,w=t['w']))
    out['cell_vs_pm_snapshot']=dict(n_joined=len(joins),
        mean_bot_entry=round(sum(j['bot_entry'] for j in joins)/len(joins),4) if joins else None,
        mean_snap60=round(sum(j['snap_p60_side'] for j in joins)/len(joins),4) if joins else None,
        detail=joins[:15])
except Exception as e:
    out['cell_vs_pm_snapshot']=str(e)

json.dump(out,open(os.path.join(HERE,'results.json'),'w'),indent=1)
print(json.dumps(out,indent=1))
