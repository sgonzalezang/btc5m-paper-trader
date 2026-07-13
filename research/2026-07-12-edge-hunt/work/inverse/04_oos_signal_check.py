#!/usr/bin/env python3
"""OOS check of the momentum-family SIGNAL (not its prices).

Signal proxy: 1m drift at t0+60s: d = c1m(t0..t0+60)/o(t0) - 1, |d| >= theta.
(Engines triggered at median 27s on median 2.6bps; the first 1m close is the
closest look-ahead-safe candle proxy.)
Outcome: open(t0+300) vs open(t0), buffered consecutive 5m opens via 1m data;
tie -> up (Coinbase proxy for Chainlink; ~97%+ agreement, noted).

Eras: A = Jun 26 -> Jul 10 15:05 (family alive: in-sample era)
      B = Jul 10 15:05 -> Jul 13 (family retired: fresh, never seen by them)
Continuation rate per theta in {2,4,8} bps, 1h-block bootstrap CI on era B.
Economics overlay: ledger says such signals priced at ~59c ask+slip
(q* = 0.5956); prior work says 62-65c for confirmed drift. Signal must beat
that to matter - report the gap.
"""
import json, random, statistics
from collections import defaultdict

CB1M = '/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data/cb1m.json'
OUT = '/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work/inverse/oos_signal.json'
RETIRE = 1783698300  # 2026-07-10 15:05 UTC last family trade t0
JUN26 = 1782432000   # 2026-06-26 00:00 UTC

def block_boot_ci(vals_by_block, nboot=4000, seed=23):
    rng = random.Random(seed)
    blocks = list(vals_by_block.values())
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
    out = {'construction': '1m drift at t0+60s; outcome open(t0+300) vs open(t0), tie->up; Coinbase proxy', 'eras': {}}
    thetas = [0.0002, 0.0004, 0.0008]
    for era, lo, hi in (('A_family_alive_Jun26-Jul10', JUN26, RETIRE), ('B_fresh_Jul10-Jul13', RETIRE, 4e18)):
        res = {}
        for theta in thetas:
            wins_by_block = defaultdict(list)
            n = 0
            for t0 in range(min(t) // 300 * 300 + 300, max(t), 300):
                if not (lo <= t0 < hi):
                    continue
                i0 = idx.get(t0)
                i5 = idx.get(t0 + 300)
                if i0 is None or i5 is None:
                    continue
                drift = c[i0] / o[i0] - 1  # first 1m candle close vs its open (= interval open)
                if abs(drift) < theta:
                    continue
                up_out = o[i5] >= o[i0]
                cont = (drift > 0) == up_out
                # tie->up convention: if equal opens, up wins; drift>0 side wins tie
                wins_by_block[t0 // 3600].append(1.0 if cont else 0.0)
                n += 1
            if n < 30:
                res[f'theta_{theta*1e4:.0f}bps'] = {'n': n, 'note': 'too few'}
                continue
            vals = [v for b in wins_by_block.values() for v in b]
            q = statistics.fmean(vals)
            clo, chi = block_boot_ci(wins_by_block)
            res[f'theta_{theta*1e4:.0f}bps'] = {
                'n': n, 'continuation': round(q, 4), 'ci95': [round(clo, 4), round(chi, 4)],
                'net_at_59c_c': round((q - 0.59 - 0.07 * 0.59 * 0.41) * 100, 2),
                'net_at_55c_c': round((q - 0.55 - 0.07 * 0.55 * 0.45) * 100, 2),
                'net_at_50c_c': round((q - 0.50 - 0.07 * 0.25) * 100, 2)}
        out['eras'][era] = res
    # unconditional up rate per era (drift-of-period control)
    for era, lo, hi in (('A', JUN26, RETIRE), ('B', RETIRE, 4e18)):
        ups = []
        for t0 in range(min(t) // 300 * 300 + 300, max(t), 300):
            if not (lo <= t0 < hi):
                continue
            i0, i5 = idx.get(t0), idx.get(t0 + 300)
            if i0 is None or i5 is None:
                continue
            ups.append(1.0 if o[i5] >= o[i0] else 0.0)
        out[f'up_rate_era_{era}'] = {'n': len(ups), 'up': round(statistics.fmean(ups), 4)}
    json.dump(out, open(OUT, 'w'), indent=1)
    print(json.dumps(out, indent=1))

if __name__ == '__main__':
    main()
