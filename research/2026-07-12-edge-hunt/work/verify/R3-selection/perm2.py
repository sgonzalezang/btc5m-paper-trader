#!/usr/bin/env python3
"""Sharper permutation tests for R3.
A) z-max over the scanned grid (fair to large-n cells) under within-band drift shuffle.
B) fixed-cell permutation: drift>=4 flag shuffled within band [0.60,0.65) only —
   tests the drift increment for that band without selection.
C) hour-block shuffle variant of (A): whole hours' drift vectors swapped between
   hours (within band strata broken — instead shuffle hour labels of drift), to
   respect autocorrelation.
Appends to results.json.
"""
import json, math, random, collections, os

HERE = os.path.dirname(os.path.abspath(__file__))
D12 = '/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data'
def fee_ps(p): return 0.07*p*(1-p)

tr = json.load(open(os.path.join(D12, 'trades_unified.json')))
S = [t for t in tr if t.get('status') == 'settled' and t.get('result') in ('win', 'loss')]
MOM = {'loose', 'floor', 'band', 'value', 'fade', 'strict', 'capless', 'calm'}
for t in S:
    t['w'] = 1.0 if t['result'] == 'win' else 0.0
    t['p'] = t['entry']
    d = (t['btcEntry']-t['btcOpen'])/t['btcOpen']*1e4
    t['sdrift'] = d if t['side'] == 'up' else -d
    t['ev_ps'] = t['w'] - t['p'] - fee_ps(t['p'])
mom = [t for t in S if t['eng'] in MOM]

BANDS = [(0.35, 0.40), (0.40, 0.45), (0.45, 0.50), (0.50, 0.55), (0.55, 0.60),
         (0.60, 0.65), (0.65, 0.70), (0.70, 0.75), (0.60, 1.01)]
THR = [2, 4, 8]

def cell_stats(ts, dkey):
    """returns dict cell -> (n, ev_c, z) on dedup intervals."""
    res = {}
    for lo_, hi_ in BANDS:
        for th in THR:
            sub = [t for t in ts if t[dkey] >= th and lo_ <= t['p'] < hi_]
            du = {}
            for t in sub: du.setdefault((t['t0'], t['side']), []).append(t)
            u = [v[0] for v in du.values()]
            n = len(u)
            if n >= 12:
                evs = [t['ev_ps'] for t in u]
                mu = sum(evs)/n
                var = sum((e-mu)**2 for e in evs)/(n-1)
                z = mu/math.sqrt(var/n) if var > 0 else 0.0
                res[(lo_, hi_, th)] = (n, 100*mu, z)
    return res

obs = cell_stats(mom, 'sdrift')
obs_zmax = max(v[2] for v in obs.values())
obs_cell = obs.get((0.60, 0.65, 4))
out = {}
out['obs_grid_cells'] = len(obs)
out['obs_zmax'] = round(obs_zmax, 3)
out['obs_cell_6065_4'] = dict(n=obs_cell[0], ev_c=round(obs_cell[1], 2), z=round(obs_cell[2], 3))

rng = random.Random(1234)

# A) z-max permutation, trade-level shuffle of drift within 5c price band
def band_of(t): return min(int(t['p']*100)//5, 19)
strata = collections.defaultdict(list)
for t in mom: strata[band_of(t)].append(t)
B = 500
cnt_z = cnt_cellz = 0
for _ in range(B):
    for band, ts in strata.items():
        ds = [t['sdrift'] for t in ts]
        rng.shuffle(ds)
        for t, d_ in zip(ts, ds): t['_pd'] = d_
    pg = cell_stats(mom, '_pd')
    if pg and max(v[2] for v in pg.values()) >= obs_zmax: cnt_z += 1
    pc = pg.get((0.60, 0.65, 4))
    if pc and pc[2] >= obs_cell[2]: cnt_cellz += 1
out['perm_zmax_tradelevel'] = dict(B=B, p=round((cnt_z+1)/(B+1), 4),
                                   note='P(max cell z over grid >= observed max z) under within-band drift shuffle')
out['perm_fixedcell_tradelevel'] = dict(B=B, p=round((cnt_cellz+1)/(B+1), 4),
                                        note='P(cell 60-65 drift>=4 z >= observed) — no selection, drift-increment test')

# C) hour-block shuffle: permute the mapping hour->drift-vector.
# Implementation: group trades by hour; shuffle the hours' drift multisets by
# rotating the assignment: assign each trade the drift of a random trade from a
# randomly matched hour (matched within price band to preserve q(p)).
# Simpler conservative variant: within band, shuffle drift between trades of
# DIFFERENT hours only in whole-hour swaps: permute hour labels then reassign
# drifts hour-to-hour within band where counts allow; fallback trade-level.
hours = sorted({t['t0']//3600 for t in mom})
byhb = collections.defaultdict(list)   # (band, hour) -> trades
for t in mom: byhb[(band_of(t), t['t0']//3600)].append(t)
cnt_z2 = cnt_cellz2 = 0
B2 = 500
for _ in range(B2):
    # for each band: collect per-hour drift lists, permute hour assignment among
    # hours with equal counts where possible; otherwise pool-and-chunk preserving sizes
    for band in {b for b, h in byhb}:
        hs = [h for (b, h) in byhb if b == band]
        lists = [[t['sdrift'] for t in byhb[(band, h)]] for h in hs]
        # pool whole hour-vectors and reassign to hours with same sizes: group by size
        bysize = collections.defaultdict(list)
        for L in lists: bysize[len(L)].append(L)
        for sz, Ls in bysize.items(): rng.shuffle(Ls)
        it = {sz: iter(Ls) for sz, Ls in bysize.items()}
        for h in hs:
            ts = byhb[(band, h)]
            L = next(it[len(ts)])
            for t, d_ in zip(ts, L): t['_pd'] = d_
    pg = cell_stats(mom, '_pd')
    if pg and max(v[2] for v in pg.values()) >= obs_zmax: cnt_z2 += 1
    pc = pg.get((0.60, 0.65, 4))
    if pc and pc[2] >= obs_cell[2]: cnt_cellz2 += 1
out['perm_zmax_hourblock'] = dict(B=B2, p=round((cnt_z2+1)/(B2+1), 4),
                                  note='hour-vector reassignment within band (size-matched); preserves within-hour drift correlation')
out['perm_fixedcell_hourblock'] = dict(B=B2, p=round((cnt_cellz2+1)/(B2+1), 4))

res_path = os.path.join(HERE, 'results.json')
res = json.load(open(res_path)); res['perm2'] = out
json.dump(res, open(res_path, 'w'), indent=1)
print(json.dumps(out, indent=1))
