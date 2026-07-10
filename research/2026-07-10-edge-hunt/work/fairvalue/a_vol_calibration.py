"""Part A: EWMA lambda sweep on cb5m TRAIN (QMLE), then FV calibration on cb1m overlap.

FV(Up at s sec in) = Phi(d / (sigma*sqrt((300-s)/300))), d = log drift so far from cb1m.
- s=60 : close of 1m candle [t0,t0+60)          (exact)
- s=150: mean(close@120s, close@180s)            (interpolated, documented)
- s=20 : open + (close-open)*20/60 of 1st candle (linear interp, documented)
Lambda fitted on cb5m TRAIN = first 2/3 (ends before cb1m starts -> calibration is fully OOS wrt lambda).
Overlap itself split 2/3-1/3 chronologically: scale-multiplier kappa fit on OVERLAP-TRAIN only,
headline calibration quoted on OVERLAP-TEST.
"""
import json, math, sys
sys.path.insert(0, '/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad/work/fairvalue')
from fv_lib import *

OUT = SC + '/work/fairvalue'

t5, o5, c5, r5, up5 = cb5m_series()
span0, span1 = t5[0], t5[-1] + 300
t_cut = span0 + (span1 - span0) * 2 // 3
print(f'cb5m n={len(t5)} span {span0}..{span1}  TRAIN cut {t_cut}')

# ---- lambda sweep (TRAIN only) ----
lams = [0.80, 0.85, 0.90, 0.92, 0.94, 0.95, 0.96, 0.97, 0.98, 0.99]
rows = []
for lam in lams:
    sig = ewma_sigma(t5, r5, lam)
    tr, ntr = qmle_loss(r5, sig, span0, t_cut, t5)
    te, nte = qmle_loss(r5, sig, t_cut, span1, t5)
    rows.append((lam, tr, ntr, te, nte))
    print(f'lam={lam:.2f}  TRAIN QMLE={tr:.4f} (n={ntr})  [TEST QMLE={te:.4f} n={nte}]')
best = min(rows, key=lambda x: x[1])
LAM = best[0]
print(f'chosen on TRAIN: lambda={LAM}')

sig5 = ewma_sigma(t5, r5, LAM)
sig_by_t0 = {t5[i]: sig5[i] for i in range(len(t5)) if sig5[i] is not None}
out5 = {t5[i]: (o5[i], up5[i]) for i in range(len(t5))}

# ---- build FV rows on cb1m overlap ----
d1 = load_candles('cb1m')
t1 = d1['t']; o1 = d1['o']; c1 = d1['c']
m1 = {t1[i]: (o1[i], c1[i]) for i in range(len(t1))}

ov0, ov1 = t1[0], t1[-1] + 60
ov_cut = ov0 + (ov1 - ov0) * 2 // 3
print(f'cb1m overlap {ov0}..{ov1}  overlap-train cut {ov_cut}')

rows_fv = []  # per (t0, s): d, sigma_rem, fv, up
t0 = ((ov0 + 299) // 300) * 300
skipped = 0
while t0 + 300 <= ov1:
    ok = t0 in out5 and t0 in sig_by_t0 and all((t0 + k * 60) in m1 for k in range(3))
    if not ok:
        skipped += 1; t0 += 300; continue
    o_ivl, up = out5[t0]
    sig = sig_by_t0[t0]
    p20 = m1[t0][0] + (m1[t0][1] - m1[t0][0]) * (20 / 60)   # linear interp in 1st candle
    p60 = m1[t0][1]
    p150 = 0.5 * (m1[t0 + 60][1] + m1[t0 + 120][1])
    for s, px in ((20, p20), (60, p60), (150, p150)):
        d = math.log(px / o_ivl)
        srem = sig * math.sqrt((300 - s) / 300)
        rows_fv.append({'t0': t0, 's': s, 'd': d, 'sig': sig, 'srem': srem, 'up': up})
    t0 += 300
print(f'FV rows: {len(rows_fv)} ({len(rows_fv)//3} intervals, skipped {skipped})')

# ---- fit scale multiplier kappa on OVERLAP-TRAIN (z = d_terminal residual scale) ----
# kappa scales sigma: fv = Phi(d/(kappa*srem)). Fit by minimizing log-loss on overlap-train, per s pooled.
def logloss(rows, kappa):
    L, n = 0.0, 0
    for r in rows:
        f = phi(r['d'] / (kappa * r['srem']))
        f = min(max(f, 1e-6), 1 - 1e-6)
        L += -(r['up'] * math.log(f) + (1 - r['up']) * math.log(1 - f))
        n += 1
    return L / max(1, n)

tr_rows = [r for r in rows_fv if r['t0'] < ov_cut]
te_rows = [r for r in rows_fv if r['t0'] >= ov_cut]
kaps = [0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.8, 2.0]
ll = [(k, logloss(tr_rows, k)) for k in kaps]
for k, v in ll: print(f'kappa={k:.1f} overlap-train logloss={v:.4f}')
KAP = min(ll, key=lambda x: x[1])[0]
print(f'chosen kappa={KAP} (overlap-train)')

# ---- calibration on OVERLAP-TEST ----
def calib_table(rows, kappa, label):
    print(f'\n== calibration {label} (kappa={kappa}) ==')
    res = {}
    for s in (20, 60, 150):
        sub = [r for r in rows if r['s'] == s]
        for r in sub:
            r['fv'] = min(max(phi(r['d'] / (kappa * r['srem'])), 1e-6), 1 - 1e-6)
        bri = sum((r['fv'] - r['up']) ** 2 for r in sub) / len(sub)
        base = sum(r['up'] for r in sub) / len(sub)
        bri0 = sum((0.5 - r['up']) ** 2 for r in sub) / len(sub)
        # reliability by fv bucket
        buckets = [(0, .3), (.3, .4), (.4, .45), (.45, .55), (.55, .6), (.6, .7), (.7, 1.01)]
        tab = []
        for lo, hi in buckets:
            bb = [r for r in sub if lo <= r['fv'] < hi]
            if not bb: tab.append((lo, hi, 0, None, None)); continue
            tab.append((lo, hi, len(bb), sum(x['fv'] for x in bb) / len(bb),
                        sum(x['up'] for x in bb) / len(bb)))
        print(f' s={s:3d}  n={len(sub)}  base_up={base:.3f}  Brier(FV)={bri:.4f} vs Brier(.5)={bri0:.4f}  skill={(bri0-bri)/bri0*100:.1f}%')
        for lo, hi, n, mf, mu in tab:
            if n: print(f'   fv [{lo:.2f},{hi:.2f}) n={n:4d}  mean_fv={mf:.3f}  realized_up={mu:.3f}')
        res[s] = {'n': len(sub), 'brier_fv': bri, 'brier_05': bri0, 'base': base,
                  'table': [(lo, hi, n, mf, mu) for lo, hi, n, mf, mu in tab]}
    return res

res_tr = calib_table(tr_rows, KAP, 'OVERLAP-TRAIN')
res_te = calib_table(te_rows, KAP, 'OVERLAP-TEST  << headline')
res_te_k1 = calib_table([dict(r) for r in te_rows], 1.0, 'OVERLAP-TEST kappa=1 (raw brief formula)')

json.dump({'lambda_sweep': rows, 'lambda': LAM, 'kappa_sweep': ll, 'kappa': KAP,
           'ov_cut': ov_cut, 'calib_train': res_tr, 'calib_test': res_te,
           'calib_test_kappa1': res_te_k1},
          open(OUT + '/a_results.json', 'w'), indent=1, default=str)
print('\nsaved', OUT + '/a_results.json')
