#!/usr/bin/env python3
"""Test (c): hourly vol seasonality + vol-scaled reversal trigger vs fixed 12bps.
Rolling per-session vol = median |open-to-open 5m move| over trailing 7d within
the same session (strictly past data). Walk-forward: k chosen on TRAIN
(max net EV, and trade-count-matched variant), evaluated once on TEST.
Both rules compared on identical eval range (post 7d burn-in).
Fees at p=0.51 (live ledger median reversal fill).
"""
import json, time, random, math, bisect
S = '/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad'
random.seed(99)
d = json.load(open(f'{S}/data/cb5m.json')); t,o,c = d['t'],d['o'],d['c']
n=len(t); P=0.51; FEE=0.07*P*(1-P); QSTAR=P+FEE

def session(h):
    return 'Asia' if h<7 else 'Europe' if h<13 else 'US' if h<21 else 'Late'

absr=[]; rows=[]
for i in range(1,n):
    r=(o[i]-o[i-1])/o[i-1]; up=c[i]>=o[i]
    tm=time.gmtime(t[i])
    rows.append(dict(r=r, ar=abs(r), rev=(not up) if r>0 else up,
                     hour=tm.tm_hour, sess=session(tm.tm_hour)))
m=len(rows)

# ---- hourly vol profile (descriptive) ----
split=(2*m)//3
print('== per-hour vol (median |5m move|, bps): TRAIN | TEST ==')
prof={}
for h in range(24):
    a=sorted(r['ar'] for r in rows[:split] if r['hour']==h)
    b=sorted(r['ar'] for r in rows[split:] if r['hour']==h)
    prof[h]=(a[len(a)//2]*1e4, b[len(b)//2]*1e4)
    print(f'h{h:02d} {prof[h][0]:5.2f} | {prof[h][1]:5.2f}')
sess_med={}
for s in ('Asia','Europe','US','Late'):
    a=sorted(r['ar'] for r in rows[:split] if r['sess']==s)
    sess_med[s]=a[len(a)//2]*1e4
print('TRAIN session median vol (bps):', {k:round(v,2) for k,v in sess_med.items()})

# ---- rolling per-session median |r| over trailing 7d, strictly past ----
WIN=2016  # 7d of 5m
from collections import deque
buf={s:deque() for s in ('Asia','Europe','US','Late')}   # (idx, ar)
srt={s:[] for s in buf}                                   # sorted ar values
vol=[None]*m
for i,row in enumerate(rows):
    s=row['sess']
    q=buf[s]; sl=srt[s]
    # median from strictly past same-session data
    if len(sl)>=50:
        vol[i]=sl[len(sl)//2]
    q.append((i,row['ar'])); bisect.insort(sl,row['ar'])
    while q and q[0][0] < i-WIN:
        _,old=q.popleft(); del sl[bisect.bisect_left(sl,old)]

burn=WIN  # eval from first index where 7d history exists
ev_lo, ev_hi = burn, m
tr_range=range(burn, split); te_range=range(split, m)

def evaluate(idx, trig):
    k=[i for i in idx if trig(i)]
    if not k: return 0, float('nan'), float('nan')
    q=sum(rows[i]['rev'] for i in k)/len(k)
    return len(k), q, q-QSTAR

# fixed rule on same eval ranges
TH=0.0012
fx_tr=evaluate(tr_range, lambda i: rows[i]['ar']>=TH)
fx_te=evaluate(te_range, lambda i: rows[i]['ar']>=TH)
days_tr=(t[split]-t[burn])/86400; days_te=(t[-1]-t[split])/86400
print(f'\nFIXED 12bps: TRAIN n={fx_tr[0]} q={fx_tr[1]:.4f} netEV={fx_tr[2]:+.4f} ({fx_tr[0]/days_tr:.1f} tr/day)')
print(f'             TEST  n={fx_te[0]} q={fx_te[1]:.4f} netEV={fx_te[2]:+.4f} ({fx_te[0]/days_te:.1f} tr/day)')

# ---- k sweep on TRAIN ----
print('\n== vol-scaled: trigger |r|>=k*vol_sess(7d roll)  (TRAIN sweep) ==')
best=None; matched=None
res={}
for k10 in range(8,41,2):
    k=k10/10
    f=lambda i,k=k: vol[i] is not None and rows[i]['ar']>=k*vol[i]
    ntr,qtr,evtr=evaluate(tr_range,f)
    res[k]=(ntr,qtr,evtr)
    tot=evtr*ntr if ntr else -9e9
    print(f'k={k:3.1f} n={ntr:5d} q={qtr:.4f} netEV={evtr:+.4f} totalEVshares={evtr*ntr:+8.1f}')
    if ntr>=300 and (best is None or evtr>res[best][2]): best=k
    if matched is None or abs(ntr-fx_tr[0])<abs(res[matched][0]-fx_tr[0]): matched=k
print(f'\nTRAIN-selected: k_bestEV={best} (n>=300), k_matched={matched} (trade count ~ fixed rule)')

out=dict(hour_vol=prof, sess_med=sess_med,
         fixed=dict(train=fx_tr, test=fx_te),
         sweep={str(k):v for k,v in res.items()}, k_best=best, k_matched=matched)

for lbl,k in (('k_bestEV',best),('k_matched',matched)):
    f=lambda i,k=k: vol[i] is not None and rows[i]['ar']>=k*vol[i]
    nte,qte,evte=evaluate(te_range,f)
    print(f'{lbl}={k}: TEST n={nte} q={qte:.4f} netEV={evte:+.4f} ({nte/days_te:.1f} tr/day) '
          f'vs fixed TEST netEV={fx_te[2]:+.4f}')
    out[f'test_{lbl}']=dict(k=k,n=nte,q=qte,ev=evte)

# ---- block-bootstrap: TEST diff (vol-scaled(k_matched) minus fixed) in rev rate ----
def pref(f):
    p=[0]
    for i in range(m): p.append(p[-1]+(1 if f(i) else 0))
    return p
kk=matched
fA=lambda i: vol[i] is not None and rows[i]['ar']>=kk*vol[i]
fB=lambda i: rows[i]['ar']>=TH
ta=pref(lambda i: i>=split and fA(i)); ra=pref(lambda i: i>=split and fA(i) and rows[i]['rev'])
tb=pref(lambda i: i>=split and fB(i)); rb=pref(lambda i: i>=split and fB(i) and rows[i]['rev'])
obs=ra[m]/ta[m]-rb[m]/tb[m]
B=12; boots=[]
for _ in range(3000):
    sta=sra=stb=srb=0
    for _ in range(m//B):
        s=random.randint(0,m-B)
        sta+=ta[s+B]-ta[s]; sra+=ra[s+B]-ra[s]; stb+=tb[s+B]-tb[s]; srb+=rb[s+B]-rb[s]
    if sta and stb: boots.append(sra/sta-srb/stb)
p2=2*min(sum(1 for b in boots if b<=0)/len(boots), sum(1 for b in boots if b>=0)/len(boots))
print(f'\nTEST diff (vol-scaled k={kk} minus fixed): {obs:+.4f}  block-boot p={min(p2,1):.4f}')
out['test_diff_matched']=dict(obs=obs,p=min(p2,1))
json.dump(out, open(f'{S}/work/seasonality/c_results.json','w'), indent=1)
print(f'saved -> {S}/work/seasonality/c_results.json')
