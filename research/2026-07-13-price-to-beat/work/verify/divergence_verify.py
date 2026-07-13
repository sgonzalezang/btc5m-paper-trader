import json, collections
c=json.load(open('/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data/cb1m.json'))
o={t:v for t,v in zip(c['t'],c['o'])}
cl={t:v for t,v in zip(c['t'],c['c'])}
pm=[(t0,up) for t0,up in json.load(open('/Users/sgonzalez/btc5m-paper-trader/research/2026-07-10-edge-hunt/data/pm_res_3d.json'))]

def ref_price(t0):
    if t0 in o: return o[t0]
    if (t0-60) in cl: return cl[t0-60]   # fallback: prior candle close
    return None

rows=[]
missing=0
for t0,up in pm:
    r=ref_price(t0); e=ref_price(t0+300)
    if r is None or e is None:
        missing+=1; continue
    d=e-r
    bps=abs(d)/r*1e4
    naive_up = 1 if d>0 else 0            # live-leader convention d>0 (tie->down)
    naive_up_ge = 1 if d>=0 else 0        # >= convention
    rows.append((t0,up,d,bps,naive_up,naive_up_ge))

n=len(rows)
dis=[x for x in rows if x[4]!=x[1]]
dis_ge=[x for x in rows if x[5]!=x[1]]
print('pm total',len(pm),'usable',n,'missing_candle',missing)
print('naive(d>0) agree %%: %.3f  disagree n=%d (%.3f%%)'%(100*(1-len(dis)/n),len(dis),100*len(dis)/n))
print('naive(>=)  agree %%: %.3f  disagree n=%d'%(100*(1-len(dis_ge)/n),len(dis_ge)))

# bps slices of disagreement
edges=[0,1,2,3,5,8,12,20,1e9]
buck=collections.OrderedDict()
for i in range(len(edges)-1):
    lo,hi=edges[i],edges[i+1]
    inb=[x for x in rows if lo<=x[3]<hi]
    db=[x for x in inb if x[4]!=x[1]]
    buck[f'[{lo},{hi})']={'n':len(inb),'disagree':len(db),'rate_pct':round(100*len(db)/len(inb),2) if inb else 0}
for k,v in buck.items(): print(k,v)

# share of disagreements under thresholds
und2=sum(1 for x in dis if x[3]<2); und3=sum(1 for x in dis if x[3]<3)
print('disagreements: total',len(dis),'<2bps',und2,'(%.1f%%)'%(100*und2/len(dis)),'<3bps',und3,'(%.1f%%)'%(100*und3/len(dis)))
maxdis=max((x[3] for x in dis),default=0)
print('max bps among disagreements: %.3f'%maxdis)

# clearMargin hard-call defer: assume clearMargin ~ 3bps band (need actual $ -> compute both 3bps and $19)
for band_bps in [2.0,3.0]:
    hard=[x for x in rows if x[3]>=band_bps]
    hdis=[x for x in hard if x[4]!=x[1]]
    print('defer band %gbps -> hard n=%d, hard disagree=%d, deferred=%d'%(band_bps,len(hard),len(hdis),n-len(hard)))

json.dump({'n':n,'missing':missing,'naive_d0_disagree':len(dis),'naive_ge_disagree':len(dis_ge),
           'naive_d0_agree_pct':round(100*(1-len(dis)/n),3),
           'buckets':buck,'dis_under2':und2,'dis_under3':und3,'max_dis_bps':round(maxdis,3)},
          open('divergence_verify.json','w'),indent=1)
