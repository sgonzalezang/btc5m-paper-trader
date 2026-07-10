"""Part C v2: value-entry sim with STRICTLY non-anticipating FV inputs.
- decision at s=60 : d = log(close@60s / open)   (candle [t0,t0+60) close = price at 60s)
- decision at s=150: d = log(close@120s / open)  (30s stale by construction; NO future info)
Remaining-time scaling still uses actual seconds left at decision (240 / 150).
Also: staleness diagnostics — edge by |fv-p| gap size; excluding extreme gaps (>0.10)
where stale last-trade prints most likely fake the fill.
"""
import json, math, sys
sys.path.insert(0, '/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad/work/fairvalue')
from fv_lib import *

OUT = SC + '/work/fairvalue'
LAM, KAP = 0.95, 0.9

t5, o5, c5, r5, up5 = cb5m_series()
sig5 = ewma_sigma(t5, r5, LAM)
sig_by_t0 = {t5[i]: sig5[i] for i in range(len(t5)) if sig5[i] is not None}
open_by_t0 = {t5[i]: o5[i] for i in range(len(t5))}
d1 = load_candles('cb1m')
m1 = {d1['t'][i]: (d1['o'][i], d1['c'][i]) for i in range(len(d1['t']))}
pm = json.load(open(DATA + '/pm_prices_sample.json'))

def fv_na(t0, s):
    """non-anticipating FV at decision time s"""
    if t0 not in sig_by_t0 or t0 not in open_by_t0: return None
    o = open_by_t0[t0]; sig = sig_by_t0[t0]
    if s == 60:
        if t0 not in m1: return None
        px = m1[t0][1]
    elif s == 150:
        if (t0 + 60) not in m1: return None
        px = m1[t0 + 60][1]   # price at 120s only
    else:
        return None
    d = math.log(px / o)
    srem = KAP * sig * math.sqrt((300 - s) / 300)
    return phi(d / srem)

rows = []
for m in pm:
    for s, key in ((60, 'p60'), (150, 'p150')):
        p = m.get(key)
        if p is None: continue
        fv = fv_na(m['t0'], s)
        if fv is None: continue
        rows.append({'t0': m['t0'], 's': s, 'p': p, 'fv': fv, 'up': m['up_won']})
print(f'rows: {len(rows)}')

pm_t0s = sorted({m['t0'] for m in pm})
cut = pm_t0s[len(pm_t0s) * 2 // 3]

def sim(rr, s_use, margin, slip, gapcap=None):
    tr = []
    for r in rr:
        if r['s'] != s_use: continue
        for side, psid, q in (('up', r['p'], r['fv']), ('down', 1 - r['p'], 1 - r['fv'])):
            f = psid + slip
            if f >= q - margin: continue
            if gapcap is not None and (q - psid) > gapcap: continue
            if f <= 0.02 or f >= 0.98: continue
            won = r['up'] if side == 'up' else 1 - r['up']
            tr.append({'f': f, 'won': won, 'pnl': won - f - fee(f), 't0': r['t0'], 'side': side})
            break
    return tr

def summ(tr):
    if not tr: return {'n': 0}
    n = len(tr)
    return {'n': n, 'win': round(sum(t['won'] for t in tr) / n, 3),
            'avg_fill': round(sum(t['f'] for t in tr) / n, 3),
            'be': round(breakeven(sum(t['f'] for t in tr) / n), 3),
            'ev_sh': round(sum(t['pnl'] for t in tr) / n, 4)}

print('\n== TRAIN sweep (non-anticipating, slip=0.01) ==')
res = {'train': [], 'test': [], 'gap': []}
for s_use in (60, 150):
    for margin in (0.02, 0.03, 0.05, 0.07, 0.10):
        st = summ(sim([r for r in rows if r['t0'] < cut], s_use, margin, 0.01))
        res['train'].append({'s': s_use, 'm': margin, **st})
        print(f" s={s_use:3d} m={margin:.2f} {st}")

print('\n== TEST grid (transparency) ==')
for s_use in (60, 150):
    for margin in (0.02, 0.03, 0.05, 0.07, 0.10):
        tr = sim([r for r in rows if r['t0'] >= cut], s_use, margin, 0.01)
        st = summ(tr)
        pv = block_bootstrap_pvalue([t['pnl'] for t in tr], block=12) if st['n'] >= 24 else None
        res['test'].append({'s': s_use, 'm': margin, **st, 'bb_p': pv})
        print(f" s={s_use:3d} m={margin:.2f} {st} bb_p={pv}")

print('\n== edge by fv-p gap bucket (s=150, all sample, buy the cheap side, slip=0.01) ==')
for lo, hi in [(0.03, 0.05), (0.05, 0.08), (0.08, 0.12), (0.12, 1.0)]:
    tr = []
    for r in rows:
        if r['s'] != 150: continue
        for side, psid, q in (('up', r['p'], r['fv']), ('down', 1 - r['p'], 1 - r['fv'])):
            gap = q - psid
            if not (lo <= gap < hi): continue
            f = psid + 0.01
            if f <= 0.02 or f >= 0.98: continue
            won = r['up'] if side == 'up' else 1 - r['up']
            tr.append({'f': f, 'won': won, 'pnl': won - f - fee(f), 't0': r['t0'], 'side': side})
            break
    st = summ(tr)
    res['gap'].append({'lo': lo, 'hi': hi, **st})
    print(f" gap [{lo:.2f},{hi:.2f}) {st}")

print('\n== TEST with gapcap=0.10 (drop likely-stale extreme gaps), s=150 ==')
for margin in (0.02, 0.03, 0.05):
    tr = sim([r for r in rows if r['t0'] >= cut], 150, margin, 0.01, gapcap=0.10)
    st = summ(tr)
    res.setdefault('test_gapcap', []).append({'m': margin, **st})
    print(f" m={margin:.2f} {st}")

print('\n== sanity: pLast vs outcome (how informative are these snapshots near close) ==')
good = [m for m in pm if m.get('pLast') is not None]
bri = sum((m['pLast'] - m['up_won']) ** 2 for m in good) / len(good)
print(f' n={len(good)} Brier(pLast)={bri:.4f}')

json.dump(res, open(OUT + '/c2_results.json', 'w'), indent=1)
print('saved', OUT + '/c2_results.json')
