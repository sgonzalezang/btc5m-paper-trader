import json, math, random
S='/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad'
def q(xs,p):
    xs=sorted(xs); n=len(xs)
    if n==0: return None
    k=(n-1)*p; f=math.floor(k); c=min(f+1,n-1)
    return xs[f]+(xs[c]-xs[f])*(k-f)

cb=json.load(open(S+'/data/cb5m.json')); t,o=cb['t'],cb['o']
idx={tt:i for i,tt in enumerate(t)}
pm=json.load(open(S+'/data/pm_prices_sample.json'))
rows=[]
for m in pm:
    i=idx.get(m['t0'])
    if i is None or i==0 or t[i]-t[i-1]!=300: continue
    r=(o[i]-o[i-1])/o[i-1]
    cpx=(1-m['p20']) if r>0 else m['p20']
    rows.append((m['t0'],r,cpx))

print("== threshold sensitivity (uncensored c20) ==")
for TH in (0.00096,0.0012,0.00144):
    xs=[c for _,r,c in rows if abs(r)>=TH]
    if not xs: continue
    av=sum(1 for x in xs if x<=0.55)/len(xs)
    print(f" TH={TH*1e4:.1f}bps n={len(xs)} p25={q(xs,.25):.3f} p50={q(xs,.5):.3f} p75={q(xs,.75):.3f} avail<=.55={av:.3f}")

print("\n== cap sensitivity (availability) ==")
xs=[c for _,r,c in rows if abs(r)>=0.0012]
for cap in (0.44,0.50,0.55,0.60,0.66):
    print(f" cap={cap:.2f}: avail={sum(1 for x in xs if x<=cap)/len(xs):.3f}")

print("\n== chronological split of signal c20 (2/3 - 1/3) ==")
sigs=sorted([(t0,c) for t0,r,c in rows if abs(r)>=0.0012])
k=len(sigs)*2//3
a=[c for _,c in sigs[:k]]; b=[c for _,c in sigs[k:]]
print(f" train n={len(a)} median={q(a,.5):.3f} avail={sum(1 for x in a if x<=.55)/len(a):.3f}")
print(f" test  n={len(b)} median={q(b,.5):.3f} avail={sum(1 for x in b if x<=.55)/len(b):.3f}")

print("\n== availability binomial 95% CI (normal approx + exact-ish bootstrap) ==")
n=len(xs); kk=sum(1 for x in xs if x<=0.55); ph=kk/n
se=math.sqrt(ph*(1-ph)/n)
print(f" {kk}/{n} = {ph:.3f} +- {1.96*se:.3f} -> [{ph-1.96*se:.3f},{ph+1.96*se:.3f}]")

print("\n== ledger split (chronological halves + thirds) ==")
tr=json.load(open(S+'/data/trades.json'))
rev=sorted([x for x in tr if x.get('eng') in ('reversal','reversal2','latentfire')], key=lambda x:x['at'])
h=len(rev)//2
for lab,part in (("H1",rev[:h]),("H2",rev[h:])):
    e=[x['entry'] for x in part]
    print(f" {lab}: n={len(e)} median entry={q(e,.5):.3f} p90={q(e,.9):.3f}")

print("\n== ledger cap censoring check ==")
e=[x['entry'] for x in rev]
print(f" frac entries in [.54,.56] (at cap): {sum(1 for x in e if .54<=x<=.56)/len(e):.3f}; max entry={max(e):.3f}")

print("\n== dedupe check: unique t0 per eng vs total (multiple engines same interval) ==")
t0s=set((x['t0'],x['eng']) for x in rev); ut0=set(x['t0'] for x in rev)
print(f" fills={len(rev)} unique (t0,eng)={len(t0s)} unique t0={len(ut0)}")

print("\n== block bootstrap (1h) CI on c20 median and availability ==")
random.seed(7)
by={}
for t0,c in sigs: by.setdefault(t0//3600,[]).append(c)
blocks=list(by.values()); B=2000
med=[];av=[]
for _ in range(B):
    samp=[v for _ in range(len(blocks)) for v in random.choice(blocks)]
    med.append(q(samp,.5)); av.append(sum(1 for x in samp if x<=.55)/len(samp))
med.sort(); av.sort()
print(f" c20 median CI [{med[int(.025*B)]:.3f},{med[int(.975*B)]:.3f}]  avail CI [{av[int(.025*B)]:.3f},{av[int(.975*B)]:.3f}]")
