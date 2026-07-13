#!/usr/bin/env python3
"""Item 2: inversion test with honest economics.

Taking the opposite side of each retired-engine trade means buying the OTHER
token at its ask + 1c slip. Complementary-book identity: ask_other ~= 1 - bid_this.
So p_inv = 1 - bid + 0.01 = 1 - (ask - spread) + 0.01.

Spread source, in order of preference:
  1. signals.log real decision-time bid (exact ask match verified) - loose/floor/band.
  2. fallback spread assumption (1c base = 94% of logged books; 2c sensitivity).

Inverse win = 1 - win (settlement is binary). Fee = frozen 0.07*p*(1-p) at p_inv.
NOTE optimism: assumes the opposite book is fillable at 1-bid+1c with no adverse
selection; real inverted fills would be worse. Any negative result is therefore
a STRONG negative.
"""
import json, random, statistics
from collections import defaultdict

DATA = '/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data/trades_unified.json'
SIGLOG = '/Users/sgonzalez/btc5m-paper-trader/bot/signals.log'
OUT = '/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work/inverse/inversion.json'
FAM = ['loose', 'floor', 'band', 'value', 'fade']

def fee(p):
    return 0.07 * p * (1 - p)

def load_spreads():
    sig = {}
    with open(SIGLOG) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                s = json.loads(line)
            except json.JSONDecodeError:
                continue
            if s.get('ask') is not None and s.get('bid') is not None:
                sig[(s['engine'], s['t0'])] = (s['ask'], s['bid'])
    return sig

def block_boot(vals_by_block, nboot=4000, seed=13):
    rng = random.Random(seed)
    blocks = list(vals_by_block.values())
    means = []
    for _ in range(nboot):
        sample = []
        for _ in range(len(blocks)):
            sample.extend(rng.choice(blocks))
        means.append(statistics.fmean(sample))
    means.sort()
    return means

def eval_inversion(trades, sig, fallback_spread):
    rows = []
    n_real_spread = 0
    for t in trades:
        ask = t['ask']
        got = sig.get((t['eng'], t['t0']))
        if got and abs(got[0] - ask) < 1e-9:
            spread = got[0] - got[1]
            n_real_spread += 1
        else:
            spread = fallback_spread
        p_inv = 1 - (ask - spread) + 0.01
        if p_inv >= 0.99 or p_inv <= 0.01:
            continue
        w_inv = 0.0 if t['result'] == 'win' else 1.0
        rows.append((t, p_inv, w_inv, w_inv - p_inv - fee(p_inv)))
    return rows, n_real_spread

def summarize(rows, label):
    if len(rows) < 20:
        return {'label': label, 'n': len(rows), 'note': 'too few'}
    ev = statistics.fmean(r[3] for r in rows)
    q = statistics.fmean(r[2] for r in rows)
    p = statistics.fmean(r[1] for r in rows)
    by_block = defaultdict(list)
    for t, p_inv, w, e in rows:
        by_block[t['t0'] // 3600].append(e)
    means = block_boot(by_block)
    lo, hi = means[int(0.025 * len(means))], means[int(0.975 * len(means))]
    p_ge0 = sum(1 for m in means if m >= 0) / len(means)
    return {'label': label, 'n': len(rows), 'inv_wr': round(q, 4), 'avg_p_inv': round(p, 4),
            'ev_share_c': round(ev * 100, 2), 'ci95_c': [round(lo * 100, 2), round(hi * 100, 2)],
            'p_ev_ge_0': round(p_ge0, 4)}

def main():
    d = json.load(open(DATA))
    settled = [t for t in d if t['status'] == 'settled' and t['eng'] in FAM]
    sig = load_spreads()
    out = {'assumptions': 'p_inv = 1 - bid + 1c slip; bid real where logged else ask - fallback_spread; frozen fee model; optimistic fill (no adverse selection)'}
    for fs in (0.01, 0.02):
        key = f'fallback_spread_{int(fs*100)}c'
        out[key] = {}
        for e in FAM + ['ALL']:
            sub = settled if e == 'ALL' else [t for t in settled if t['eng'] == e]
            rows, n_real = eval_inversion(sub, sig, fs)
            s = summarize(rows, f'{e} inverted')
            s['n_real_spread'] = n_real
            out[key][e] = s
    # cheap-inverse subset: only invert where p_inv <= 0.50 (cheap other side)
    out['inv_cheap_le50'] = {}
    for e in FAM + ['ALL']:
        sub = settled if e == 'ALL' else [t for t in settled if t['eng'] == e]
        rows, _ = eval_inversion(sub, sig, 0.01)
        rows = [r for r in rows if r[1] <= 0.50]
        out['inv_cheap_le50'][e] = summarize(rows, f'{e} inverted, p_inv<=50c')
    json.dump(out, open(OUT, 'w'), indent=1)
    for k in ('fallback_spread_1c', 'fallback_spread_2c', 'inv_cheap_le50'):
        print('==', k)
        for e, s in out[k].items():
            if 'ev_share_c' in s:
                print(f"  {e:6s} n={s['n']:4d} inv_wr={s['inv_wr']:.3f} p_inv={s['avg_p_inv']:.3f} EV/sh={s['ev_share_c']:+.2f}c CI{s['ci95_c']} p_ge0={s['p_ev_ge_0']}")
            else:
                print(f"  {e:6s} n={s['n']} too few")

if __name__ == '__main__':
    main()
