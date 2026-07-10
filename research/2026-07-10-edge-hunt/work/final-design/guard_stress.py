import json, math
S='/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad'
cb=json.load(open(S+'/data/cb5m.json'))
t,o,c=cb['t'],cb['o'],cb['c']

# censored ledger fill prices (effective cost ask+slip), ledger order, cap 53c
tr=json.load(open(S+'/data/trades.json'))
fills=[x['entry'] for x in tr if x.get('eng') in ('reversal','reversal2','latentfire')
       and x.get('status')=='settled' and x.get('result') in ('win','loss')
       and x.get('entry') is not None and x['entry']<=0.53+1e-9]

# signal stream: buffered open-to-open, 12bps, contrarian, ties->Up
sig=[]
for i in range(1,len(t)):
    if t[i]-t[i-1]!=300: continue
    pr=(o[i]-o[i-1])/o[i-1]
    if abs(pr)<0.0012: continue
    up = c[i] >= o[i]
    win = (pr>0 and not up) or (pr<0 and up)
    sig.append((t[i], win))
t0=sig[0][0]
# per-10d window q (sanity vs best_spec .572/.477/.507/.552/.529/.579)
wq=[]
for w in range(6):
    ss=[x for x in sig if w*10*86400 <= x[0]-t0 < (w+1)*10*86400]
    wq.append((len(ss), round(sum(1 for _,x in ss if x)/len(ss),3) if ss else None))

def fee(p): return 0.07*p*(1-p)

def sim(guard='none'):
    bank=1000.0; peak=1000.0; maxdd=0.0
    hist=[]           # (time, win, net_per_share, fillable)
    trades=0; g_first=None; g_days=0; breaker_day=None
    k=0
    day_flag={}
    for idx,(ts,win) in enumerate(sig):
        fillable=(idx*13)%20<11
        p=fills[k%len(fills)] if fillable else None
        if fillable: k+=1
        nps=(1-p-fee(p)) if (fillable and win) else (-(p+fee(p)) if fillable else None)
        # trailing windows over fillable settled signals
        w30=[h for h in hist if ts-h[0]<=30*86400 and h[3]]
        w15=[h for h in hist if ts-h[0]<=15*86400 and h[3]]
        w7 =[h for h in hist if ts-h[0]<= 7*86400 and h[3]]
        n30=len(w30); wins30=sum(1 for h in w30 if h[1])
        qraw=min((wins30+200)/(n30+400),0.56)
        g=False
        if guard in ('spec','fast') and len(w15)>=250 and sum(h[2] for h in w15)/len(w15)<-0.01: g=True
        if guard=='fast' and len(w7)>=120 and sum(h[2] for h in w7)/len(w7)<-0.02: g=True
        qu = 0.5+(qraw-0.5)/2 if g else qraw
        if g and g_first is None: g_first=(ts-t0)/86400
        if g: day_flag[int((ts-t0)//86400)]=1
        if fillable and bank>=250:
            cost=p+fee(p)
            f=qu-(1-qu)*cost/(1-cost)
            if f>0:
                stake=min(0.25*f*bank,0.05*bank)
                sh=stake/p
                bank+=sh*((1-cost) if win else -cost)
                trades+=1
                peak=max(peak,bank); maxdd=max(maxdd,(peak-bank)/peak)
        elif bank<250 and breaker_day is None:
            breaker_day=(ts-t0)/86400
        if fillable: hist.append((ts,win,nps,True))
        else: hist.append((ts,win,None,False))
    return dict(final=round(bank,1),maxdd_pct=round(maxdd*100,1),trades=trades,
                guard_first_day=round(g_first,1) if g_first else None,
                guard_days=len(day_flag),breaker_day=breaker_day)

res={'window_q':wq,'n_signals':len(sig),'span_days':round((sig[-1][0]-t0)/86400,1),
     'no_guard':sim('none'),'guard_spec':sim('spec'),'guard_fast':sim('fast')}
json.dump(res,open(S+'/work/final-design/guard_stress.json','w'),indent=1)
print(json.dumps(res,indent=1))
