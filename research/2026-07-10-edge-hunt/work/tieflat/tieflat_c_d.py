#!/usr/bin/env python3
"""Tie rule / flat intervals — parts (c) and (d).

(c) anchor Coinbase-proxy flat buckets against actual Polymarket resolutions (pm_res_3d):
    agreement by |move| bucket; actual P(Up) in flat buckets and in bottom trailing-vol decile.
(d) pricing: pm_prices_sample p20 in quiet regimes; net edge of
    "buy Up at p20<=0.52 when forecast vol in bottom decile", exact fee model.
"""
import json, math, random

SCRATCH = '/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad'
D = SCRATCH + '/data/'
W = SCRATCH + '/work/tieflat/'

cb = json.load(open(D + 'cb5m.json'))
t, o, c = cb['t'], cb['o'], cb['c']
n = len(t)
idx = {tt: i for i, tt in enumerate(t)}
move_bps = [ (c[i]-o[i])/o[i]*1e4 for i in range(n) ]

def tvol(i):
    if i < 12 or t[i]-t[i-12] != 3600: return None
    return sum(abs(move_bps[j]) for j in range(i-12, i))/12.0

# TRAIN decile edges (recompute identically to tieflat_a.py)
rows = [(i, tvol(i)) for i in range(12, n)]
rows = [(i, tv) for i, tv in rows if tv is not None]
split = int(len(rows)*2/3)
tv_train = sorted(tv for _, tv in rows[:split])
edges = [tv_train[int(len(tv_train)*k/10)] for k in range(1, 10)]
D0_EDGE = edges[0]
def decile(tv):
    d = 0
    for e in edges:
        if tv >= e: d += 1
        else: break
    return d
print(f'D0 trailing-vol edge (train) = {D0_EDGE:.3f} bps mean|move| over trailing hour')

pm = json.load(open(D + 'pm_res_3d.json'))   # [[t0, up_won], ...]
out = {'d0_edge_bps': D0_EDGE}

# ---- (c) match pm resolutions to cb candles ----
matched = []
for t0, upw in pm:
    i = idx.get(t0)
    if i is None: continue
    tv = tvol(i)
    matched.append((t0, upw, move_bps[i], 1 if c[i] >= o[i] else 0, tv))
print(f'pm_res n={len(pm)}, matched to cb5m: {len(matched)}')

def wilson(w, m, z=1.96):
    if m == 0: return (float('nan'),)*2
    p = w/m
    den = 1 + z*z/m
    ctr = (p + z*z/(2*m))/den
    hw = z*math.sqrt(p*(1-p)/m + z*z/(4*m*m))/den
    return ctr-hw, ctr+hw

print('\n(c) proxy agreement + actual P(Up) by realized |move| bucket (Coinbase):')
buckets = [('<1bps', 0, 1), ('1-2bps', 1, 2), ('2-4bps', 2, 4), ('>=4bps', 4, 1e9)]
out['c_buckets'] = {}
for lbl, lo, hi in buckets:
    sub = [r for r in matched if lo <= abs(r[2]) < hi]
    m = len(sub)
    agree = sum(1 for r in sub if r[1] == r[3])
    upw = sum(r[1] for r in sub)
    upproxy = sum(r[3] for r in sub)
    lo95, hi95 = wilson(upw, m)
    out['c_buckets'][lbl] = {'n': m, 'agree': agree/m if m else None,
        'p_up_actual': upw/m if m else None, 'p_up_proxy': upproxy/m if m else None,
        'wilson95_actual': [lo95, hi95]}
    print(f'  {lbl:7s} n={m:3d} agree={agree/m*100 if m else 0:5.1f}% '
          f'P(Up)actual={upw/m if m else 0:.3f} [{lo95:.3f},{hi95:.3f}] proxy={upproxy/m if m else 0:.3f}')

# bottom trailing-vol decile (tradable ex ante) on actual resolutions
sub = [r for r in matched if r[4] is not None and decile(r[4]) == 0]
m = len(sub); w = sum(r[1] for r in sub)
lo95, hi95 = wilson(w, m)
print(f'\n(c) actual P(Up) in trailing-vol D0 (ex-ante): n={m} P(Up)={w/m if m else 0:.3f} [{lo95:.3f},{hi95:.3f}]')
out['c_d0_actual'] = {'n': m, 'p_up': w/m if m else None, 'wilson95': [lo95, hi95]}
# overall actual up rate
w_all = sum(r[1] for r in matched)
print(f'(c) actual P(Up) overall 3d: n={len(matched)} {w_all/len(matched):.3f}')
out['c_overall'] = {'n': len(matched), 'p_up': w_all/len(matched)}

# ---- (d) pricing in quiet regimes ----
ps = json.load(open(D + 'pm_prices_sample.json'))
recs = []
for r in ps:
    i = idx.get(r['t0'])
    tv = tvol(i) if i is not None else None
    if tv is None: continue
    recs.append({**r, 'tv': tv, 'dec': decile(tv)})
print(f'\n(d) pm_prices_sample n={len(ps)}, with cb trailing vol: {len(recs)}')

def qs(xs, probs=(0.1, 0.25, 0.5, 0.75, 0.9)):
    xs = sorted(xs); m = len(xs)
    return {f'q{int(p*100)}': xs[min(m-1, int(p*m))] for p in probs}

d0p = [r['p20'] for r in recs if r['dec'] == 0]
rest = [r['p20'] for r in recs if r['dec'] != 0]
print(f'  p20 in D0 (n={len(d0p)}):', {k: round(v,3) for k,v in qs(d0p).items()} if d0p else 'none')
print(f'  p20 rest  (n={len(rest)}):', {k: round(v,3) for k,v in qs(rest).items()} if rest else 'none')
out['d_p20_D0'] = {'n': len(d0p), 'quantiles': qs(d0p) if d0p else None}
out['d_p20_rest'] = {'n': len(rest), 'quantiles': qs(rest) if rest else None}
# quietest 3 deciles pooled, since D0 alone may be tiny
dlo = [r for r in recs if r['dec'] <= 2]
print(f'  p20 in D0-D2 (n={len(dlo)}):', {k: round(v,3) for k,v in qs([r["p20"] for r in dlo]).items()} if dlo else 'none')

def fee(p): return 0.07 * p * (1 - p)

def run_strat(sel, label, slip=0.0):
    """buy Up at p20(+slip) for markets in sel; hold to resolution."""
    pnl, wins = [], 0
    for r in sel:
        fill = r['p20'] + slip
        if fill >= 1: continue
        pl = r['up_won'] - fill - fee(fill)
        pnl.append(pl); wins += r['up_won']
    m = len(pnl)
    if m == 0:
        print(f'  {label}: n=0'); return {'n': 0}
    mean = sum(pnl)/m
    lo95, hi95 = wilson(wins, m)
    # bootstrap CI on mean pnl (iid over markets; small n, quote honestly)
    rnd = random.Random(11); boots = []
    for _ in range(4000):
        s = [pnl[rnd.randrange(m)] for _ in range(m)]
        boots.append(sum(s)/m)
    boots.sort()
    blo, bhi = boots[100], boots[3899]
    res = {'n': m, 'win_rate': wins/m, 'wilson95_win': [lo95, hi95],
           'mean_pnl_per_share': mean, 'boot95_pnl': [blo, bhi],
           'avg_fill': sum(r['p20']+slip for r in sel)/m}
    print(f'  {label}: n={m} win={wins/m:.3f} [{lo95:.3f},{hi95:.3f}] '
          f'meanPnL/share={mean:+.4f} boot95=[{blo:+.4f},{bhi:+.4f}] avg fill={res["avg_fill"]:.3f}')
    return res

print('\n(d) strategy: buy Up @ p20 when p20<=0.52 and forecast vol in bottom decile:')
sel0 = [r for r in recs if r['dec'] == 0 and r['p20'] is not None and r['p20'] <= 0.52]
out['d_strat_D0'] = run_strat(sel0, 'D0, p20<=0.52, no slip')
out['d_strat_D0_slip'] = run_strat(sel0, 'D0, p20<=0.52, +1c slip', slip=0.01)
sel02 = [r for r in recs if r['dec'] <= 2 and r['p20'] is not None and r['p20'] <= 0.52]
out['d_strat_D0_2'] = run_strat(sel02, 'D0-D2, p20<=0.52, no slip')
out['d_strat_D0_2_slip'] = run_strat(sel02, 'D0-D2, p20<=0.52, +1c slip', slip=0.01)
# reference: unconditional buy Up at p20<=0.52
selall = [r for r in recs if r['p20'] is not None and r['p20'] <= 0.52]
out['d_strat_all'] = run_strat(selall, 'ALL deciles, p20<=0.52, no slip')

# break-even at typical fill
for p in (0.50, 0.52):
    print(f'  break-even win rate at p={p}: {p + fee(p):.4f}')

# decile distribution of the price sample (was the sample skewed by vol?)
from collections import Counter
cnt = Counter(r['dec'] for r in recs)
print('\n(d) sample count by decile:', dict(sorted(cnt.items())))
out['d_sample_decile_counts'] = dict(sorted(cnt.items()))

json.dump(out, open(W + 'result_c_d.json', 'w'), indent=1)
print('\nsaved', W + 'result_c_d.json')
