"""Parts B & C: Polymarket book vs calibrated FV on pm_prices_sample (216 mkts, ~3d),
then value-style entry simulation with margin swept on the sample's first 2/3.

FV inputs: lambda=0.95 (cb5m TRAIN QMLE), kappa=0.9 (overlap-train logloss) — both fitted
strictly before the pm sample window. s=20 FV is look-ahead contaminated (drift interpolated
using the 1m candle close at 60s) -> reported but flagged, headline on s=60/150.
Book prices are CLOB prices-history fidelity=1 samples (mid-ish, +/-90s timing tolerance).
Fill model: base = p_side + 0.01 slip; stress = p_side + 0.02. Fee = 0.07*f*(1-f) per share.
Outcome: actual Polymarket resolution (up_won) — the real oracle, not the Coinbase proxy.
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
print(f'pm sample n={len(pm)}  t0 {pm[0]["t0"]}..{pm[-1]["t0"]}')

def fv_at(t0, s):
    if t0 not in sig_by_t0 or t0 not in open_by_t0: return None, None, None
    if any((t0 + k * 60) not in m1 for k in range(3)): return None, None, None
    o = open_by_t0[t0]; sig = sig_by_t0[t0]
    if s == 20:  px = m1[t0][0] + (m1[t0][1] - m1[t0][0]) * (20 / 60)
    elif s == 60: px = m1[t0][1]
    else:        px = 0.5 * (m1[t0 + 60][1] + m1[t0 + 120][1])
    d = math.log(px / o)
    srem = KAP * sig * math.sqrt((300 - s) / 300)
    return phi(d / srem), d, sig

rows = []
for m in pm:
    for s, key in ((20, 'p20'), (60, 'p60'), (150, 'p150')):
        p = m.get(key)
        if p is None: continue
        fv, d, sig = fv_at(m['t0'], s)
        if fv is None: continue
        rows.append({'t0': m['t0'], 's': s, 'p': p, 'fv': fv, 'd': d, 'sig': sig, 'up': m['up_won']})
print(f'joined rows: {len(rows)}')

# ---------- Part B: systematic mispricing ----------
sigs = sorted({r['sig'] for r in rows})
lo_t, hi_t = sigs[len(sigs)//3], sigs[2*len(sigs)//3]
def vol_reg(s): return 'low' if s < lo_t else ('high' if s >= hi_t else 'mid')

print('\n== B1: book vs FV, by seconds-in ==')
bres = {}
for s in (20, 60, 150):
    sub = [r for r in rows if r['s'] == s]
    if not sub: continue
    diff = [r['p'] - r['fv'] for r in sub]
    md = sum(diff) / len(diff)
    bri_b = sum((r['p'] - r['up']) ** 2 for r in sub) / len(sub)
    bri_f = sum((r['fv'] - r['up']) ** 2 for r in sub) / len(sub)
    pv = block_bootstrap_pvalue(diff, block=12)
    print(f' s={s:3d} n={len(sub)}  mean(book-FV)={md:+.4f} (bb p={pv})  Brier book={bri_b:.4f}  FV={bri_f:.4f}')
    bres[s] = {'n': len(sub), 'mean_diff': md, 'p': pv, 'brier_book': bri_b, 'brier_fv': bri_f}

print('\n== B2: mean(book - FV) by |d| bucket (bps), s=60/150 ==')
def dbps(r): return abs(r['d']) * 1e4
bkts = [(0, 2), (2, 5), (5, 10), (10, 1e9)]
b2 = []
for s in (60, 150):
    for lo, hi in bkts:
        sub = [r for r in rows if r['s'] == s and lo <= dbps(r) < hi]
        if len(sub) < 5: continue
        md = sum(r['p'] - r['fv'] for r in sub) / len(sub)
        wr_book = sum(r['up'] for r in sub) / len(sub)
        mfv = sum(r['fv'] for r in sub) / len(sub); mp = sum(r['p'] for r in sub) / len(sub)
        print(f' s={s:3d} |d| [{lo},{hi if hi<1e9 else "inf"}) n={len(sub):3d} mean_p={mp:.3f} mean_fv={mfv:.3f} diff={md:+.4f} up_rate={wr_book:.3f}')
        b2.append({'s': s, 'lo': lo, 'hi': hi, 'n': len(sub), 'mean_p': mp, 'mean_fv': mfv, 'diff': md, 'up_rate': wr_book})

print('\n== B3: mean(book - FV) by vol regime, s=60/150 ==')
b3 = []
for s in (60, 150):
    for reg in ('low', 'mid', 'high'):
        sub = [r for r in rows if r['s'] == s and vol_reg(r['sig']) == reg]
        if len(sub) < 5: continue
        md = sum(r['p'] - r['fv'] for r in sub) / len(sub)
        print(f' s={s:3d} vol={reg:4s} n={len(sub):3d} mean(book-FV)={md:+.4f}')
        b3.append({'s': s, 'reg': reg, 'n': len(sub), 'diff': md})

print('\n== B4: does (FV - p) predict (outcome - p)?  bucket by FV-p, s=60/150 pooled ==')
b4 = []
for lo, hi in [(-1, -0.10), (-0.10, -0.05), (-0.05, -0.02), (-0.02, 0.02), (0.02, 0.05), (0.05, 0.10), (0.10, 1)]:
    sub = [r for r in rows if r['s'] in (60, 150) and lo <= (r['fv'] - r['p']) < hi]
    if len(sub) < 5: continue
    resid = [r['up'] - r['p'] for r in sub]
    mr = sum(resid) / len(resid)
    print(f' fv-p [{lo:+.2f},{hi:+.2f}) n={len(sub):3d}  mean(outcome-p)={mr:+.4f}')
    b4.append({'lo': lo, 'hi': hi, 'n': len(sub), 'mean_resid': mr})

# ---------- Part C: value-entry simulation ----------
# Entry rule at s: side=Up if p_up + slip < fv - margin ; side=Down if (1-p_up) + slip < (1-fv) - margin.
# Down token price approximated 1 - p_up (mid symmetry) — documented assumption.
pm_t0s = sorted({m['t0'] for m in pm})
cut = pm_t0s[len(pm_t0s) * 2 // 3]
print(f'\npm sample chrono split: train t0 < {cut}, test >= (train {sum(1 for t in pm_t0s if t < cut)}, test {sum(1 for t in pm_t0s if t >= cut)})')

def sim(rows, s_use, margin, slip):
    trades = []
    for r in rows:
        if r['s'] != s_use: continue
        for side, psid, q in (('up', r['p'], r['fv']), ('down', 1 - r['p'], 1 - r['fv'])):
            f = psid + slip
            if f >= q - margin: continue
            if f <= 0.02 or f >= 0.98: continue
            won = r['up'] if side == 'up' else 1 - r['up']
            pnl = won - f - fee(f)
            trades.append({'t0': r['t0'], 's': s_use, 'side': side, 'f': f, 'fv_side': q, 'won': won, 'pnl': pnl})
            break  # one side max per row
    return trades

def summ(tr):
    if not tr: return {'n': 0}
    n = len(tr); w = sum(t['won'] for t in tr); pnl = sum(t['pnl'] for t in tr)
    mf = sum(t['f'] for t in tr) / n
    be = breakeven(mf)
    return {'n': n, 'win': w / n, 'avg_fill': mf, 'breakeven_at_fill': be,
            'ev_per_share': pnl / n, 'total_pnl_per_share': pnl}

print('\n== C: margin sweep on pm-TRAIN (slip=0.01) ==')
sweep = []
for s_use in (60, 150):
    for margin in (0.02, 0.03, 0.05, 0.07, 0.10):
        tr = sim([r for r in rows if r['t0'] < cut], s_use, margin, 0.01)
        st = summ(tr)
        sweep.append({'s': s_use, 'margin': margin, **st})
        if st['n']: print(f" s={s_use:3d} m={margin:.2f} n={st['n']:3d} win={st['win']:.3f} fill={st['avg_fill']:.3f} be={st['breakeven_at_fill']:.3f} EV/sh={st['ev_per_share']:+.4f}")
        else: print(f" s={s_use:3d} m={margin:.2f} n=0")

# pick best TRAIN combo with n>=15 by EV/share
cands = [x for x in sweep if x['n'] >= 15]
best = max(cands, key=lambda x: x['ev_per_share']) if cands else None
print('\nbest TRAIN combo:', best)
cres = {'sweep_train': sweep, 'best': best}
if best:
    for slip, tag in ((0.01, 'base'), (0.02, 'stress')):
        tr = sim([r for r in rows if r['t0'] >= cut], best['s'], best['margin'], slip)
        st = summ(tr)
        pv = block_bootstrap_pvalue([t['pnl'] for t in tr], block=12) if st['n'] >= 24 else None
        print(f"TEST ({tag} slip={slip}): {st}  bb_p={pv}")
        cres[f'test_{tag}'] = {**st, 'bb_p': pv}
    # also show TEST at the same s for all margins (transparency, not selection)
    for margin in (0.02, 0.03, 0.05, 0.07, 0.10):
        tr = sim([r for r in rows if r['t0'] >= cut], best['s'], margin, 0.01)
        st = summ(tr)
        if st['n']: print(f" [test-grid] s={best['s']} m={margin:.2f} n={st['n']:3d} win={st['win']:.3f} fill={st['avg_fill']:.3f} EV/sh={st['ev_per_share']:+.4f}")

json.dump({'b1': bres, 'b2': b2, 'b3': b3, 'b4': b4, 'c': cres, 'pm_cut': cut},
          open(OUT + '/bc_results.json', 'w'), indent=1)
print('\nsaved', OUT + '/bc_results.json')
