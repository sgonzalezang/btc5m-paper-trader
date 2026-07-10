#!/usr/bin/env python3
"""Significance tests: (1) momentum gross overpay (mispricing < 0) via 1-h block bootstrap,
(2) p20-favorite 55-60c bucket vs fee-adjusted breakeven, (3) reversal-family TEST win rate CI.
Output: sigtests.json
"""
import json, math, random
from collections import defaultdict

S = '/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad'
W = S + '/work/microstructure'
tr = json.load(open(S + '/data/trades.json'))
pm = json.load(open(S + '/data/pm_prices_sample.json'))
out = {}

def block_boot(pairs, stat, nboot=4000, blocksec=3600, seed=11):
    blocks = defaultdict(list)
    for t0, x in pairs: blocks[t0 // blocksec].append(x)
    bl = list(blocks.values()); B = len(bl)
    rng = random.Random(seed); vals = []
    for _ in range(nboot):
        acc = []
        for _ in range(B): acc.extend(bl[rng.randrange(B)])
        vals.append(stat(acc))
    vals.sort(); return vals

# ---- (1) momentum per-share mispricing, current book, clean trades ----
mom = [t for t in tr if t['status'] == 'settled' and t['src'] == 'current'
       and t['eng'] in ('loose', 'floor', 'band', 'value')
       and t.get('result') in ('win', 'loss') and not t.get('hedge')]
pairs = [(t['t0'], (t['shares'], t['shares'] * ((1.0 if t['result'] == 'win' else 0.0) - t['entry']))) for t in mom]
def mis_per_share(acc):
    sh = sum(a for a, _ in acc); return sum(b for _, b in acc) / sh
obs = mis_per_share([x for _, x in pairs])
dist = block_boot(pairs, mis_per_share)
p_hi = sum(1 for d in dist if d >= 0) / len(dist)
ci = (dist[int(0.025 * len(dist))], dist[int(0.975 * len(dist))])
print(f"momentum mispricing/share: {obs*100:.2f}c  ci95=({ci[0]*100:.2f},{ci[1]*100:.2f})c  "
      f"P(>=0)={p_hi:.4f} (one-sided) n={len(mom)}")
out['momentum_misprice_per_share'] = dict(obs_c=round(obs * 100, 3), ci_c=[round(c * 100, 3) for c in ci],
                                          p_one_sided=p_hi, n=len(mom))
# chronological halves for persistence
mom.sort(key=lambda t: t['t0'])
cut = mom[int(len(mom) * 2 / 3) - 1]['t0']
for lbl, rows in (('TRAIN', [t for t in mom if t['t0'] <= cut]), ('TEST', [t for t in mom if t['t0'] > cut])):
    prs = [(t['t0'], (t['shares'], t['shares'] * ((1.0 if t['result'] == 'win' else 0.0) - t['entry']))) for t in rows]
    o = mis_per_share([x for _, x in prs])
    d = block_boot(prs, mis_per_share, seed=13)
    print(f"  {lbl}: n={len(rows)} misprice/share={o*100:.2f}c ci95=({d[int(0.025*len(d))]*100:.2f},{d[int(0.975*len(d))]*100:.2f})c")
    out[f'momentum_misprice_{lbl}'] = dict(n=len(rows), obs_c=round(o * 100, 3),
                                           ci_c=[round(d[int(0.025 * len(d))] * 100, 3), round(d[int(0.975 * len(d))] * 100, 3)])

# ---- (2) p20 favorite 55-60c bucket, fee-adjusted ----
fl = []
for r in sorted(pm, key=lambda r: r['t0']):
    p = r['p20']
    if p is None: continue
    fav_up = p > 0.5
    pf = p if fav_up else 1 - p
    if not (0.55 < pf <= 0.60): continue
    fav_won = r['up_won'] if fav_up else 1 - r['up_won']
    fl.append((r['t0'], pf, fav_won))
n = len(fl); wins = sum(w for _, _, w in fl); mp = sum(p for _, p, _ in fl) / n
# realistic entry: prices-history point is mid-ish; ask ≈ mid + 0.5-1c, +1c slip
entry = mp + 0.015
be = entry + 0.07 * entry * (1 - entry)
# exact binomial tail P(X >= wins | n, be)
def binom_tail(n, k, p):
    s = 0.0
    for i in range(k, n + 1):
        s += math.comb(n, i) * p ** i * (1 - p) ** (n - i)
    return s
pv = binom_tail(n, wins, be)
print(f"\np20-favorite (0.55,0.60]: n={n} wins={wins} winrate={wins/n:.3f} mean_p20={mp:.3f} "
      f"assumed fill={entry:.3f} breakeven={be:.3f} binom p(one-sided)={pv:.4f}")
out['fav_5560'] = dict(n=n, wins=wins, winrate=round(wins / n, 4), mean_p20=round(mp, 4),
                       fill=round(entry, 4), breakeven=round(be, 4), p=round(pv, 4))
# train/test
cut = fl[int(n * 2 / 3) - 1][0]
for lbl, rows in (('TRAIN', [x for x in fl if x[0] <= cut]), ('TEST', [x for x in fl if x[0] > cut])):
    if not rows: continue
    w = sum(r[2] for r in rows)
    print(f"  {lbl}: n={len(rows)} winrate={w/len(rows):.3f}")
    out[f'fav_5560_{lbl}'] = dict(n=len(rows), winrate=round(w / len(rows), 4))

# ---- (3) reversal family TEST win-rate CI (block bootstrap) ----
fam = sorted([t for t in tr if t['eng'] in ('reversal', 'reversal2', 'latentfire')
              and t['src'] == 'current' and t['status'] == 'settled'], key=lambda t: t['t0'])
cut2 = fam[int(len(fam) * 2 / 3) - 1]['t0']
for lbl, rows in (('ALL', fam), ('TRAIN', [t for t in fam if t['t0'] <= cut2]), ('TEST', [t for t in fam if t['t0'] > cut2])):
    prs = [(t['t0'], 1.0 if t['result'] == 'win' else 0.0) for t in rows]
    d = block_boot(prs, lambda a: sum(a) / len(a), seed=17)
    m = sum(x for _, x in prs) / len(prs)
    print(f"reversal-family win {lbl}: n={len(rows)} {m:.3f} ci95=({d[int(0.025*len(d))]:.3f},{d[int(0.975*len(d))]:.3f})")
    out[f'revfam_win_{lbl}'] = dict(n=len(rows), win=round(m, 4),
                                    ci=[round(d[int(0.025 * len(d))], 4), round(d[int(0.975 * len(d))], 4)])

json.dump(out, open(W + '/sigtests.json', 'w'), indent=1)
print('\nsaved', W + '/sigtests.json')
