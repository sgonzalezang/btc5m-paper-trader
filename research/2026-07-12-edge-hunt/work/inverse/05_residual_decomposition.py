#!/usr/bin/env python3
"""Head-start decomposition: full-interval continuation vs residual-4min
continuation after a >=theta first-minute drift. If residual ~= 50%, the
momentum 'signal' is purely the mechanical head start already in the price.
Adds 1h-block bootstrap CI on the residual rate (the null claim).
"""
import json, random, statistics
from collections import defaultdict

CB1M = '/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data/cb1m.json'
OUT = '/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work/inverse/residual_decomposition.json'
JUN26 = 1782432000

def boot_ci(by_block, nboot=4000, seed=29):
    rng = random.Random(seed)
    blocks = list(by_block.values())
    means = []
    for _ in range(nboot):
        s = []
        for _ in range(len(blocks)):
            s.extend(rng.choice(blocks))
        means.append(statistics.fmean(s))
    means.sort()
    return means[int(0.025 * len(means))], means[int(0.975 * len(means))]

def main():
    cb = json.load(open(CB1M))
    t, o, c = cb['t'], cb['o'], cb['c']
    idx = {ts: i for i, ts in enumerate(t)}
    out = {}
    for theta in (0.0002, 0.0004, 0.0008):
        full_b, res_b = defaultdict(list), defaultdict(list)
        for t0 in range(min(t) // 300 * 300 + 300, max(t), 300):
            if t0 < JUN26:
                continue
            i0, i5 = idx.get(t0), idx.get(t0 + 300)
            if i0 is None or i5 is None:
                continue
            drift = c[i0] / o[i0] - 1
            if abs(drift) < theta:
                continue
            up_out = o[i5] >= o[i0]
            full_b[t0 // 3600].append(1.0 if (drift > 0) == up_out else 0.0)
            r = o[i5] / c[i0] - 1
            if r != 0:
                res_b[t0 // 3600].append(1.0 if (drift > 0) == (r > 0) else 0.0)
        fv = [v for b in full_b.values() for v in b]
        rv = [v for b in res_b.values() for v in b]
        flo, fhi = boot_ci(full_b)
        rlo, rhi = boot_ci(res_b, seed=31)
        out[f'theta_{theta*1e4:.0f}bps'] = {
            'n_full': len(fv), 'full_interval_continuation': round(statistics.fmean(fv), 4),
            'full_ci95': [round(flo, 4), round(fhi, 4)],
            'n_resid': len(rv), 'residual_4min_continuation': round(statistics.fmean(rv), 4),
            'resid_ci95': [round(rlo, 4), round(rhi, 4)]}
    json.dump(out, open(OUT, 'w'), indent=1)
    print(json.dumps(out, indent=1))

if __name__ == '__main__':
    main()
