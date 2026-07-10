import json, math
S='/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad'
cb=json.load(open(S+'/data/cb5m.json')); t,o,c=cb['t'],cb['o'],cb['c']
tr=json.load(open(S+'/data/trades.json'))
fills=[x['entry'] for x in tr if x.get('eng') in ('reversal','reversal2','latentfire')
       and x.get('status')=='settled' and x.get('result') in ('win','loss')
       and x.get('entry') is not None and x['entry']<=0.53+1e-9]
sig=[]
for i in range(1,len(t)):
    if t[i]-t[i-1]!=300: continue
    pr=(o[i]-o[i-1])/o[i-1]
    if abs(pr)<0.0012: continue
    up=c[i]>=o[i]; win=(pr>0 and not up) or (pr<0 and up)
    sig.append((t[i],win))
t0=sig[0][0]
def fee(p): return 0.07*p*(1-p)
def sim(guard, disaster):
    bank=1000.; peak=1000.; maxdd=0.; ddday=None
    hist=[]; g_first=None; k=0; frozen=False; breaker_day=None
    for idx,(ts,win) in enumerate(sig):
        d=(ts-t0)/86400
        if disaster and 30<=d<50: win=(idx*7)%100<38   # inject q=.38 for 20d
        fillable=(idx*13)%20<11
        p=fills[k%len(fills)] if fillable else None
        if fillable: k+=1
        nps=(1-p-fee(p)) if (fillable and win) else (-(p+fee(p)) if fillable else None)
        w30=[h for h in hist if ts-h[0]<=30*86400 and h[2] is not None]
        w15=[h for h in hist if ts-h[0]<=15*86400 and h[2] is not None]
        w7 =[h for h in hist if ts-h[0]<= 7*86400 and h[2] is not None]
        qraw=min((sum(1 for h in w30 if h[1])+200)/(len(w30)+400),0.56)
        g=False
        if guard in('spec','fast') and len(w15)>=250 and sum(h[2] for h in w15)/len(w15)<-0.01: g=True
        if guard=='fast' and len(w7)>=120 and sum(h[2] for h in w7)/len(w7)<-0.02: g=True
        qu=0.5+(qraw-0.5)/2 if g else qraw
        if g and g_first is None: g_first=round(d,1)
        if fillable and bank>=250:
            cost=p+fee(p); f=qu-(1-qu)*cost/(1-cost)
            if f>0:
                stake=min(0.25*f*bank,0.05*bank); sh=stake/p
                bank+=sh*((1-cost) if win else -cost)
                if bank>peak: peak=bank
                dd=(peak-bank)/peak
                if dd>maxdd: maxdd, ddday = dd, round(d,1)
        elif bank<250 and breaker_day is None: breaker_day=round(d,1)
        hist.append((ts,win,nps))
    return dict(final=round(bank,1),maxdd_pct=round(maxdd*100,1),dd_day=ddday,
                guard_first=g_first,breaker_day=breaker_day)
res={}
for dis in (False,True):
    for g in ('none','spec','fast'):
        res[('disaster_' if dis else 'hist_')+g]=sim(g,dis)
json.dump(res,open(S+'/work/final-design/guard_disaster.json','w'),indent=1)
print(json.dumps(res,indent=1))
