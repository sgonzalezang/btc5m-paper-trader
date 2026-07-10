import json, math
S='/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad'
out={}

# ---------- 1. qhat shrinkage: broken vs fixed ----------
def qb(w,n): return (w+200*0.5)/(n+400)   # broken
def qf(w,n): return (w+200)/(n+400)       # fixed (prior mass 400 @ mean 0.5)
out['qhat']={'broken_n0':qb(0,0),'fixed_n0':qf(0,0),
  'fixed_n100_52pct':qf(52,100),'fixed_n400_52pct':qf(0.52*400,400),
  'fixed_n900_52pct':qf(0.52*900,900),'broken_n900_52pct':qb(0.52*900,900),
  'seed_from_ledger_155_at_5226':qf(round(0.5226*155),155)}

# ---------- 2. ledger reversal family censored at effective cost <= .53 ----------
tr=json.load(open(S+'/data/trades.json'))
fam=[t for t in tr if t.get('eng') in ('reversal','reversal2','latentfire')
     and t.get('status')=='settled' and t.get('result') in ('win','loss')
     and t.get('entry') is not None]
def quant(xs,q):
    xs=sorted(xs); 
    if not xs: return None
    k=(len(xs)-1)*q; f=math.floor(k); c=math.ceil(k)
    return xs[f] if f==c else xs[f]+(xs[c]-xs[f])*(k-f)
def stats(sub):
    ent=[t['entry'] for t in sub]; sh=[t.get('shares') or 0 for t in sub]
    wins=sum(1 for t in sub if t['result']=='win')
    wm=sum(e*s for e,s in zip(ent,sh))/sum(sh) if sum(sh)>0 else None
    return {'n':len(sub),'q':round(wins/len(sub),4) if sub else None,
            'p25':quant(ent,.25),'p50':quant(ent,.5),'p75':quant(ent,.75),
            'wtd_mean':round(wm,4) if wm else None}
out['ledger_all']=stats(fam)
cens=[t for t in fam if t['entry']<=0.53+1e-9]
out['ledger_cap53']=stats(cens)
out['cap53_retained']=round(len(cens)/len(fam),3)
# fraction of censored fills with total cost (p+fee) < 0.50 and < 0.5063 (launch qhat seeds)
def tot(p): return p+0.07*p*(1-p)
out['cap53_frac_cost_lt_050']=round(sum(1 for t in cens if tot(t['entry'])<0.50)/len(cens),3)
out['cap53_frac_cost_lt_5063']=round(sum(1 for t in cens if tot(t['entry'])<0.5063)/len(cens),3)
out['cap53_frac_cost_lt_5275']=round(sum(1 for t in cens if tot(t['entry'])<0.5275)/len(cens),3)

# ---------- 3. availability under 53c cap, pm sample ----------
ss=json.load(open(S+'/work/sizing/stream_stats.json'))
p20=ss['pm_match']['p_side20_sorted']
out['avail_pm_le_525']={'n':len(p20),'le':sum(1 for x in p20 if x<=0.525+1e-9),
                        'frac':round(sum(1 for x in p20 if x<=0.525+1e-9)/len(p20),3)}

# ---------- 4. fee formula conformance on full ledger ----------
mx=0.0; nfee=0
for t in tr:
    if t.get('feeEntry') is not None and t.get('shares') and t.get('entry'):
        f=t['shares']*0.07*t['entry']*(1-t['entry']); mx=max(mx,abs(f-t['feeEntry'])); nfee+=1
out['fee_conformance']={'n':nfee,'max_abs_diff':round(mx,6)}

# ---------- 5. power: one-sided alpha=.05 (90% CI LB>0), binomial normal approx ----------
def hurdle(p): return p+0.07*p*(1-p)
def power(q,h,n,infl=1.0):
    se=math.sqrt(q*(1-q)/n)*infl
    z=(q-h)/se-1.6449
    return 0.5*(1+math.erf(z/math.sqrt(2)))
wm_old=0.4861; wm_new=out['ledger_cap53']['wtd_mean']
h_old=hurdle(wm_old); h_new=hurdle(wm_new)
out['hurdles']={'old_55cap_fill':wm_old,'old_hurdle':round(h_old,4),
                'new_53cap_fill':wm_new,'new_hurdle':round(h_new,4)}
tab={}
for q in (0.510,0.515,0.523,0.533,0.5474):
    row={}
    for n in (1000,1500,2000,2500,3000):
        row[n]={'plain':round(power(q,h_new,n),3),'infl15':round(power(q,h_new,n,1.15),3)}
    tab[q]=row
out['power_new_hurdle']=tab
out['power_old_hurdle_q523']={n:round(power(0.523,h_old,n),3) for n in (1500,2000)}
# n for 80% power at q=.523, new hurdle, 15% inflation
def n80(q,h,infl):
    lo,hi=100,200000
    while hi-lo>1:
        mid=(lo+hi)//2
        if power(q,h,mid,infl)>=0.80: hi=mid
        else: lo=mid
    return hi
out['n80_q523_new']={'plain':n80(0.523,h_new,1.0),'infl15':n80(0.523,h_new,1.15)}
out['n80_q523_old']={'plain':n80(0.523,h_old,1.0),'infl15':n80(0.523,h_old,1.15)}

json.dump(out,open(S+'/work/final-design/checks.json','w'),indent=1)
print(json.dumps(out,indent=1))
