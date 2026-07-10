#!/usr/bin/env python3
"""Test (b): momentum persistence by session on cb1m (14d).
For each 5m interval with full 1m coverage: drift = first-60s move
(c-o of the 1m candle at t0)/o; condition |drift| in [2,4] bps;
hold = final 5m direction (c(t0+299)-o, ties Up) matches drift sign.
Split by session; chronological 2/3-1/3 split; block bootstrap (12x5m=1h
-> here blocks are on the 5m-interval series, 12 per block).
Realistic fill: join pm_prices_sample (p60 = Up price at 60s) with drift sign.
"""
import json, time, random, math
S = '/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad'
random.seed(42)

d = json.load(open(f'{S}/data/cb1m.json'))
t, o, c = d['t'], d['o'], d['c']
by_t = {tt: k for k, tt in enumerate(t)}

def session(h):
    if h < 7: return 'Asia'
    if h < 13: return 'Europe'
    if h < 21: return 'US'
    return 'Late'

t0s = sorted(tt for tt in t if tt % 300 == 0)
rows = []
for t0 in t0s:
    ks = [by_t.get(t0 + 60 * j) for j in range(5)]
    if any(k is None for k in ks): continue
    op = o[ks[0]]
    drift = (c[ks[0]] - op) / op            # first-60s move
    close = c[ks[4]]
    up = close >= op                        # tie -> Up
    ad = abs(drift) * 1e4                   # bps
    cond = 2.0 <= ad <= 4.0
    hold = up if drift > 0 else ((not up) if drift < 0 else False)
    tm = time.gmtime(t0)
    rows.append(dict(t0=t0, cond=cond, hold=hold, drift=drift,
                     sess=session(tm.tm_hour), wkend=tm.tm_wday >= 5))
print(f'5m intervals with full 1m coverage: {len(rows)}; conditioned (|drift| 2-4bps): {sum(r["cond"] for r in rows)}')

split = (2 * len(rows)) // 3
train, test = rows[:split], rows[split:]

def rate(sub):
    k = [r for r in sub if r['cond']]
    return (len(k), sum(r['hold'] for r in k) / len(k)) if k else (0, float('nan'))

def block_boot_diff(sub, pred, B=12, R=3000):
    m = len(sub)
    def pref(f):
        p=[0]
        for r in sub: p.append(p[-1] + (1 if f(r) else 0))
        return p
    ta=pref(lambda r: r['cond'] and pred(r)); ra=pref(lambda r: r['cond'] and pred(r) and r['hold'])
    tb=pref(lambda r: r['cond'] and not pred(r)); rb=pref(lambda r: r['cond'] and not pred(r) and r['hold'])
    if not ta[m] or not tb[m]: return float('nan'), 1.0
    obs = ra[m]/ta[m] - rb[m]/tb[m]
    boots=[]
    for _ in range(R):
        sta=sra=stb=srb=0
        for _ in range(m//B):
            s=random.randint(0, m-B)
            sta+=ta[s+B]-ta[s]; sra+=ra[s+B]-ra[s]; stb+=tb[s+B]-tb[s]; srb+=rb[s+B]-rb[s]
        if sta and stb: boots.append(sra/sta-srb/stb)
    p2=2*min(sum(1 for b in boots if b<=0)/len(boots), sum(1 for b in boots if b>=0)/len(boots))
    return obs, min(p2,1.0)

out={}
print('\n== P(hold | 2-4bps first-60s drift) ==')
for name, sub in (('TRAIN', train), ('TEST', test), ('ALL', rows)):
    k,q = rate(sub)
    print(f'{name}: n={k} P(hold)={q:.4f}')
    out[f'uncond_{name}']=dict(n=k,q=q)

print('\n== by session (TRAIN | TEST) ==')
out['session']={}
for s in ('Asia','Europe','US','Late'):
    ktr,qtr = rate([r for r in train if r['sess']==s])
    kte,qte = rate([r for r in test if r['sess']==s])
    obs,p = block_boot_diff(train, lambda r,s=s: r['sess']==s)
    print(f'{s:7s} TRAIN n={ktr:3d} q={qtr:.4f} (diff {obs:+.4f} p={p:.3f}) | TEST n={kte:3d} q={qte:.4f}')
    out['session'][s]=dict(train_n=ktr,train_q=qtr,p_train=p,test_n=kte,test_q=qte)

# ---- realistic momentum fill from pm_prices_sample (last ~3d overlap) ----
pm = json.load(open(f'{S}/data/pm_prices_sample.json'))
pm_by_t0 = {x['t0']: x for x in pm}
fills=[]; wins=[]
for r in rows:
    x = pm_by_t0.get(r['t0'])
    if x is None or not r['cond']: continue
    up_p = x['p60']
    fill = (up_p if r['drift']>0 else 1-up_p) + 0.01   # ask~snapshot +1c slip
    won = x['up_won']==1 if r['drift']>0 else x['up_won']==0
    fills.append(fill); wins.append(won)
if fills:
    fills_s=sorted(fills)
    med=fills_s[len(fills_s)//2]; mean=sum(fills)/len(fills)
    wr=sum(wins)/len(wins)
    # EV using per-trade actual fill and PM outcome
    ev=sum((1 if w else 0)-f-0.07*f*(1-f) for w,f in zip(wins,fills))/len(fills)
    print(f'\n== realistic momentum fills (pm_prices_sample join, n={len(fills)}) ==')
    print(f'fill p10={fills_s[len(fills_s)//10]:.3f} p50={med:.3f} p90={fills_s[9*len(fills_s)//10]:.3f} mean={mean:.3f}')
    print(f'PM win rate at those fills={wr:.4f}  net EV/share={ev:+.4f}')
    qstar = med + 0.07*med*(1-med)
    print(f'break-even at median fill q*({med:.3f})={qstar:.4f}')
    out['pm_join']=dict(n=len(fills), fill_med=med, fill_mean=mean, win=wr, ev=ev, qstar_med=qstar)
    # per-session EV at median-session fill using cb-derived hold rates would be
    # optimistic; report session-level joined EV where n allows
    bysess={}
    for r,f_,w_ in zip([r for r in rows if r['cond'] and r['t0'] in pm_by_t0], fills, wins):
        bysess.setdefault(r['sess'],[]).append((f_,w_))
    for s,v in sorted(bysess.items()):
        e=sum((1 if w else 0)-f-0.07*f*(1-f) for f,w in v)/len(v)
        print(f'  {s:7s} n={len(v):3d} win={sum(w for _,w in v)/len(v):.3f} EV={e:+.4f}')
json.dump(out, open(f'{S}/work/seasonality/b_results.json','w'), indent=1)
print(f"\nsaved -> {S}/work/seasonality/b_results.json")
