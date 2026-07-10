#!/usr/bin/env python3
"""Check whether the TRAIN-selected hour set beats its complement ON TEST
(block bootstrap of the TEST-side difference), plus hour-set stability."""
import json, time, random, math
S = '/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad'
random.seed(7)
d = json.load(open(f'{S}/data/cb5m.json')); t,o,c = d['t'],d['o'],d['c']
TH=0.0012
rows=[]
for i in range(1,len(t)):
    r=(o[i]-o[i-1])/o[i-1]; up=c[i]>=o[i]
    rows.append(dict(trig=abs(r)>=TH, rev=(not up) if r>0 else up, hour=time.gmtime(t[i]).tm_hour))
split=(2*len(rows))//3; test=rows[split:]
SEL={0,1,3,5,6,9,11,15,16,20,21,22}
B,R=12,4000; m=len(test)
def pref(x):
    p=[0]
    for v in x: p.append(p[-1]+v)
    return p
ta=pref([1 if (r['trig'] and r['hour'] in SEL) else 0 for r in test])
ra=pref([1 if (r['trig'] and r['hour'] in SEL and r['rev']) else 0 for r in test])
tb=pref([1 if (r['trig'] and r['hour'] not in SEL) else 0 for r in test])
rb=pref([1 if (r['trig'] and r['hour'] not in SEL and r['rev']) else 0 for r in test])
obs=ra[m]/ta[m]-rb[m]/tb[m]
boots=[]
for _ in range(R):
    sta=sra=stb=srb=0
    for _ in range(m//B):
        s=random.randint(0,m-B)
        sta+=ta[s+B]-ta[s]; sra+=ra[s+B]-ra[s]; stb+=tb[s+B]-tb[s]; srb+=rb[s+B]-rb[s]
    if sta and stb: boots.append(sra/sta-srb/stb)
p2=2*min(sum(1 for b in boots if b<=0)/len(boots), sum(1 for b in boots if b>=0)/len(boots))
print(f'TEST: q_sel={ra[m]/ta[m]:.4f} (n={ta[m]}) q_rest={rb[m]/tb[m]:.4f} (n={tb[m]}) diff={obs:+.4f} p={min(p2,1):.4f}')
# stability: split TRAIN in half, re-select hours in each half, report overlap
tr=rows[:split]; h1,h2=tr[:len(tr)//2],tr[len(tr)//2:]
def selhours(sub,qstar=0.5275,minn=20):
    out=set()
    for h in range(24):
        k=[r for r in sub if r['trig'] and r['hour']==h]
        if len(k)>=minn and sum(r['rev'] for r in k)/len(k)>qstar: out.add(h)
    return out
s1,s2=selhours(h1),selhours(h2)
print(f'hours selected 1st half TRAIN: {sorted(s1)}')
print(f'hours selected 2nd half TRAIN: {sorted(s2)}')
print(f'overlap: {sorted(s1&s2)}  jaccard={len(s1&s2)/max(1,len(s1|s2)):.2f}')
