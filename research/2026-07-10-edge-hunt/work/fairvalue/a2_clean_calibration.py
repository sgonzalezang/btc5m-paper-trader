"""Part A v2: calibration with EXACT candle closes only (s=60/120/180; zero interpolation,
zero look-ahead: close of candle [t0+s-60, t0+s) IS the price at t0+s).
Lambda=0.95 fixed from cb5m TRAIN QMLE. Kappa refit on overlap-train, headline on overlap-test.
Also B4 redo: (fv-p) vs (outcome-p) on pm sample with non-anticipating FV.
"""
import json, math, sys
sys.path.insert(0, '/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad/work/fairvalue')
from fv_lib import *

OUT = SC + '/work/fairvalue'
LAM = 0.95

t5, o5, c5, r5, up5 = cb5m_series()
sig5 = ewma_sigma(t5, r5, LAM)
sig_by_t0 = {t5[i]: sig5[i] for i in range(len(t5)) if sig5[i] is not None}
info5 = {t5[i]: (o5[i], up5[i]) for i in range(len(t5))}
d1 = load_candles('cb1m')
m1 = {d1['t'][i]: (d1['o'][i], d1['c'][i]) for i in range(len(d1['t']))}
ov0, ov1 = d1['t'][0], d1['t'][-1] + 60
ov_cut = ov0 + (ov1 - ov0) * 2 // 3

rows = []
t0 = ((ov0 + 299) // 300) * 300
while t0 + 300 <= ov1:
    if t0 in info5 and t0 in sig_by_t0 and all((t0 + k * 60) in m1 for k in range(3)):
        o_ivl, up = info5[t0]; sig = sig_by_t0[t0]
        for s in (60, 120, 180):
            px = m1[t0 + s - 60][1]
            d = math.log(px / o_ivl)
            srem = sig * math.sqrt((300 - s) / 300)
            rows.append({'t0': t0, 's': s, 'd': d, 'srem': srem, 'up': up})
    t0 += 300
print(f'intervals={len(rows)//3}')

def logloss(rr, k):
    L = 0.0
    for r in rr:
        f = min(max(phi(r['d'] / (k * r['srem'])), 1e-6), 1 - 1e-6)
        L += -(r['up'] * math.log(f) + (1 - r['up']) * math.log(1 - f))
    return L / len(rr)

tr = [r for r in rows if r['t0'] < ov_cut]; te = [r for r in rows if r['t0'] >= ov_cut]
ll = [(k, logloss(tr, k)) for k in (0.8, 0.85, 0.9, 0.95, 1.0, 1.05, 1.1, 1.2)]
for k, v in ll: print(f'kappa={k} train_ll={v:.4f}')
KAP = min(ll, key=lambda x: x[1])[0]
print('kappa*=', KAP)

def calib(rr, k, label):
    out = {}
    print(f'\n== {label} (kappa={k}) ==')
    for s in (60, 120, 180):
        sub = [r for r in rr if r['s'] == s]
        fvs = [min(max(phi(r['d'] / (k * r['srem'])), 1e-6), 1 - 1e-6) for r in sub]
        ups = [r['up'] for r in sub]
        bri = sum((f - u) ** 2 for f, u in zip(fvs, ups)) / len(sub)
        bri0 = sum((0.5 - u) ** 2 for u in ups) / len(sub)
        tab = []
        for lo, hi in [(0, .2), (.2, .35), (.35, .45), (.45, .55), (.55, .65), (.65, .8), (.8, 1.01)]:
            idx = [i for i in range(len(sub)) if lo <= fvs[i] < hi]
            if not idx: continue
            mf = sum(fvs[i] for i in idx) / len(idx); mu = sum(ups[i] for i in idx) / len(idx)
            tab.append({'lo': lo, 'hi': hi, 'n': len(idx), 'mean_fv': round(mf, 3), 'realized': round(mu, 3)})
            print(f'  s={s} fv[{lo:.2f},{hi:.2f}) n={len(idx):4d} mean_fv={mf:.3f} realized={mu:.3f}')
        print(f'  s={s} n={len(sub)} Brier={bri:.4f} vs 0.25 -> skill={(bri0-bri)/bri0*100:.1f}%')
        out[s] = {'n': len(sub), 'brier': bri, 'skill_pct': (bri0 - bri) / bri0 * 100, 'table': tab}
    return out

res_te = calib(te, KAP, 'OVERLAP-TEST (headline)')

# --- B4 redo: non-anticipating FV vs pm book prints ---
pm = json.load(open(DATA + '/pm_prices_sample.json'))
def fv_na(t0, s):
    if t0 not in sig_by_t0 or t0 not in info5: return None
    o = info5[t0][0]; sig = sig_by_t0[t0]
    if s == 60:
        if t0 not in m1: return None
        px = m1[t0][1]
    else:
        if (t0 + 60) not in m1: return None
        px = m1[t0 + 60][1]
    return phi(math.log(px / o) / (KAP * sig * math.sqrt((300 - s) / 300)))

prow = []
for m in pm:
    for s, key in ((60, 'p60'), (150, 'p150')):
        if m.get(key) is None: continue
        fv = fv_na(m['t0'], s)
        if fv is None: continue
        prow.append({'s': s, 'p': m[key], 'fv': fv, 'up': m['up_won']})
print(f'\n== B4-NA: (fv - p) vs (outcome - p), pm sample n={len(prow)} (non-anticipating FV) ==')
b4 = []
for lo, hi in [(-1, -0.10), (-0.10, -0.05), (-0.05, -0.02), (-0.02, 0.02), (0.02, 0.05), (0.05, 0.10), (0.10, 1)]:
    sub = [r for r in prow if lo <= r['fv'] - r['p'] < hi]
    if len(sub) < 5: continue
    mr = sum(r['up'] - r['p'] for r in sub) / len(sub)
    print(f'  fv-p [{lo:+.2f},{hi:+.2f}) n={len(sub):3d} mean(outcome-p)={mr:+.4f}')
    b4.append({'lo': lo, 'hi': hi, 'n': len(sub), 'mean_resid': round(mr, 4)})
# overall Brier comparison book vs NA-FV
for s in (60, 150):
    sub = [r for r in prow if r['s'] == s]
    bb = sum((r['p'] - r['up']) ** 2 for r in sub) / len(sub)
    bf = sum((r['fv'] - r['up']) ** 2 for r in sub) / len(sub)
    print(f'  s={s}: Brier(book)={bb:.4f}  Brier(NA-FV)={bf:.4f}  n={len(sub)}')

json.dump({'kappa': KAP, 'kappa_sweep': ll, 'calib_test': res_te, 'b4_na': b4},
          open(OUT + '/a2_results.json', 'w'), indent=1)
print('saved', OUT + '/a2_results.json')
