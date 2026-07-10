#!/usr/bin/env python3
"""Does a session filter help INSIDE latentfire's universe?
Universe: |prior open-to-open move| >= 12bps AND Kaufman efficiency
(trailing 12 intervals, open-to-open) <= 0.48. Session split, TRAIN/TEST,
block bootstrap on TRAIN diffs. Also hour-vol TRAIN/TEST profile correlation.
"""
import json, time, random, math
S='/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad'
random.seed(5)
d=json.load(open(f'{S}/data/cb5m.json')); t,o,c=d['t'],d['o'],d['c']
P=0.51; QSTAR=P+0.07*P*(1-P); TH=0.0012
def session(h):
    return 'Asia' if h<7 else 'Europe' if h<13 else 'US' if h<21 else 'Late'
rows=[]
for i in range(1,len(t)):
    r=(o[i]-o[i-1])/o[i-1]; up=c[i]>=o[i]
    eff=None
    if i>=13:
        net=abs(o[i]-o[i-12]); den=sum(abs(o[j]-o[j-1]) for j in range(i-11,i+1))
        eff=net/den if den>0 else 1.0
    rows.append(dict(trig=abs(r)>=TH and eff is not None and eff<=0.48,
                     rev=(not up) if r>0 else up, sess=session(time.gmtime(t[i]).tm_hour)))
m=len(rows); split=(2*m)//3
train,test=rows[:split],rows[split:]
def rate(sub):
    k=[r for r in sub if r['trig']]
    return (len(k), sum(r['rev'] for r in k)/len(k)) if k else (0,float('nan'))
def boot_diff(sub,pred,B=12,R=3000):
    mm=len(sub)
    def pref(f):
        p=[0]
        for r in sub: p.append(p[-1]+(1 if f(r) else 0))
        return p
    ta=pref(lambda r:r['trig'] and pred(r)); ra=pref(lambda r:r['trig'] and pred(r) and r['rev'])
    tb=pref(lambda r:r['trig'] and not pred(r)); rb=pref(lambda r:r['trig'] and not pred(r) and r['rev'])
    if not ta[mm] or not tb[mm]: return float('nan'),1.0
    obs=ra[mm]/ta[mm]-rb[mm]/tb[mm]; boots=[]
    for _ in range(R):
        sa=za=sb=zb=0
        for _ in range(mm//B):
            s=random.randint(0,mm-B)
            sa+=ta[s+B]-ta[s]; za+=ra[s+B]-ra[s]; sb+=tb[s+B]-tb[s]; zb+=rb[s+B]-rb[s]
        if sa and sb: boots.append(za/sa-zb/sb)
    p2=2*min(sum(1 for b in boots if b<=0)/len(boots), sum(1 for b in boots if b>=0)/len(boots))
    return obs,min(p2,1.0)
ktr,qtr=rate(train); kte,qte=rate(test)
print(f'eff-gated reversal universe: TRAIN n={ktr} q={qtr:.4f} netEV={qtr-QSTAR:+.4f} | '
      f'TEST n={kte} q={qte:.4f} netEV={qte-QSTAR:+.4f}')
out={'gated_uncond':dict(train_n=ktr,train_q=qtr,test_n=kte,test_q=qte,
                         train_ev=qtr-QSTAR,test_ev=qte-QSTAR)}
print('\nby session inside gate (TRAIN | TEST):')
out['session']={}
for s in ('Asia','Europe','US','Late'):
    a=rate([r for r in train if r['sess']==s]); b=rate([r for r in test if r['sess']==s])
    obs,p=boot_diff(train,lambda r,s=s:r['sess']==s)
    print(f'{s:7s} TRAIN n={a[0]:4d} q={a[1]:.4f} (diff {obs:+.4f} p={p:.3f}) | '
          f'TEST n={b[0]:4d} q={b[1]:.4f} netEV={b[1]-QSTAR:+.4f}')
    out['session'][s]=dict(train_n=a[0],train_q=a[1],p_train=p,test_n=b[0],test_q=b[1])
# hour-vol profile correlation TRAIN vs TEST (from c_results)
cres=json.load(open(f'{S}/work/seasonality/c_results.json'))
xs=[cres['hour_vol'][str(h)][0] for h in range(24)]; ys=[cres['hour_vol'][str(h)][1] for h in range(24)]
mx=sum(xs)/24; my=sum(ys)/24
cov=sum((x-mx)*(y-my) for x,y in zip(xs,ys))
r=cov/math.sqrt(sum((x-mx)**2 for x in xs)*sum((y-my)**2 for y in ys))
print(f'\nhour-vol profile correlation TRAIN vs TEST: r={r:.3f}')
out['hourvol_corr']=r
json.dump(out,open(f'{S}/work/seasonality/d_results.json','w'),indent=1)
print(f'saved -> {S}/work/seasonality/d_results.json')
