import json, statistics as st, random
S='/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad'
d=json.load(open(S+'/data/cb5m.json')); t,o,c=d['t'],d['o'],d['c']
tix={tt:i for i,tt in enumerate(t)}
pm=json.load(open(S+'/data/pm_prices_sample.json'))
def fee(p): return 0.07*p*(1-p)

rows=[]
for m in pm:
    i=tix.get(m['t0'])
    if not i: continue
    if t[i]-t[i-1]!=300: continue
    mv=(o[i]-o[i-1])/o[i-1]*1e4
    if abs(mv)<12: continue
    cost20=(1-m['p20']) if mv>0 else m['p20']
    win=(1-m['up_won']) if mv>0 else m['up_won']
    rows.append(dict(t0=m['t0'],mv=mv,cost20=cost20,win=win))
print('thr12 signal markets in pm sample:',len(rows))
print('pm sample span days:',(pm[-1]['t0']-pm[0]['t0'])/86400)

# 1) CAP ANALYSIS at p20: effective = cost20+0.01 slip; fill iff effective <= cap
for cap in (0.53,0.55):
    fills=[r for r in rows if r['cost20']+0.01<=cap]
    nofill=[r for r in rows if r['cost20']+0.01>cap]
    if fills:
        wr=st.mean(r['win'] for r in fills)
        evs=[r['win']-(r['cost20']+0.01)-fee(r['cost20']+0.01) for r in fills]
        print(f"cap {cap}: fill {len(fills)}/{len(rows)} ({len(fills)/len(rows):.0%}) | win_rate(fills)={wr:.4f} | mean eff cost={st.mean(r['cost20']+0.01 for r in fills):.4f} | EV/share={st.mean(evs):+.4f}")
    if nofill:
        print(f"          skipped {len(nofill)}: win_rate would-have-been {st.mean(r['win'] for r in nofill):.4f}")

# cheap vs expensive split (adverse selection direction)
cheap=[r for r in rows if r['cost20']<=0.50]; exp=[r for r in rows if r['cost20']>0.50]
print(f"contrarian cheap (<=50c raw): n={len(cheap)} win={st.mean(r['win'] for r in cheap):.4f} | expensive (>50c): n={len(exp)} win={st.mean(r['win'] for r in exp):.4f}")

# 2) same-window baseline from pm_res_3d (all resolutions, bigger n) at assumed 51c
res=json.load(open(S+'/data/pm_res_3d.json'))
wins=[];  
for t0,upw in res:
    i=tix.get(t0)
    if not i or t[i]-t[i-1]!=300: continue
    mv=(o[i]-o[i-1])/o[i-1]
    if abs(mv)<0.0012: continue
    win=(1-upw) if mv>0 else upw
    wins.append(win)
print(f"pm_res_3d thr12: n={len(wins)} q={st.mean(wins):.4f}  (same window, PM resolutions, price-blind)")

# 3) bootstrap CI on capped EV (n small)
fills=[r for r in rows if r['cost20']+0.01<=0.53]
rng=random.Random(11); B=5000; means=[]
for _ in range(B):
    s=[fills[rng.randrange(len(fills))] for _ in fills]
    means.append(st.mean(r['win']-(r['cost20']+0.01)-fee(r['cost20']+0.01) for r in s))
means.sort()
print(f"capped-53 EV bootstrap 90% CI: [{means[int(0.05*B)]:+.4f}, {means[int(0.95*B)]:+.4f}] n={len(fills)}")
