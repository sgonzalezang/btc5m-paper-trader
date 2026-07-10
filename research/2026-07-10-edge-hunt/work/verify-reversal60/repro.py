import json, random, math
S='/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad'
d=json.load(open(S+'/data/cb5m.json'))
t,o,c=d['t'],d['o'],d['c']
n=len(t)
print('candles',n,'span days',(t[-1]-t[0])/86400)

# buffered construction: consecutive candles only
sig=[]  # (t, win_contrarian, move)
for i in range(1,n):
    if t[i]-t[i-1]!=300: continue
    mv=(o[i]-o[i-1])/o[i-1]
    if abs(mv)<0.0012: continue
    up = c[i]>=o[i]   # ties Up
    win = (not up) if mv>0 else up   # contrarian: fade prior move
    sig.append((t[i],1 if win else 0,mv))
print('signals total',len(sig))

t0,t1=t[0],t[-1]
span=t1-t0
cut=t0+span*2/3
train=[s for s in sig if s[0]<cut]
test=[s for s in sig if s[0]>=cut]
def q(x): return sum(w for _,w,_ in x)/len(x)
def ev(qq,p): return qq-p-0.07*p*(1-p)
for name,x in [('TRAIN',train),('TEST',test),('FULL',sig)]:
    print(name,'n=%d q=%.4f ev@51=%.4f'%(len(x),q(x),ev(q(x),0.51)))

# block bootstrap, 1h blocks on TEST
def blockboot(x, p_be, B=4000, seed=7):
    # group by hour
    from collections import defaultdict
    blocks=defaultdict(list)
    for tt,w,_ in x: blocks[tt//3600].append(w)
    bl=list(blocks.values())
    rng=random.Random(seed)
    qhat=q(x)
    cnt5=0;cntbe=0
    nb=len(bl)
    for _ in range(B):
        samp=[w for _ in range(nb) for w in bl[rng.randrange(nb)]]
        qq=sum(samp)/len(samp)
        # p-value: prob resampled edge <= null under shift  (percentile vs null)
        if qq<=0.5: cnt5+=1
        if qq<=p_be: cntbe+=1
    return 2*min(cnt5,B-cnt5)/B, cntbe/B
p_be=0.51+0.07*0.51*0.49
pv5,pvbe=blockboot(test,p_be)
print('TEST block-boot two-sided p vs 0.5 =%.4f, one-sided p vs breakeven(%.4f) =%.4f'%(pv5,p_be,pvbe))

# move-size split on TEST and TRAIN
for name,x in [('TRAIN',train),('TEST',test)]:
    small=[s for s in x if abs(s[2])<0.0020]
    big=[s for s in x if abs(s[2])>=0.0020]
    print(name,'12-20bps n=%d q=%.4f | 20+bps n=%d q=%.4f'%(len(small),q(small),len(big),q(big)))
