#!/usr/bin/env python3
"""Attacks: threshold +-20%, split sensitivity, tie/oracle-noise sensitivity,
real fill prices from pm_prices_sample.json, multiple-comparison discount."""
import json, random

BASE = '/Users/sgonzalez/btc5m-paper-trader/research/2026-07-10-edge-hunt'
d = json.load(open(BASE+'/data/cb5m.json'))
t, o, c = d['t'], d['o'], d['c']
n = len(t); t0 = t[0]
def fee(p): return 0.07*p*(1-p)
def qstar(p): return p + fee(p)

def build(thr):
    out = []
    for i in range(1, n):
        mv = (o[i]-o[i-1])/o[i-1]
        if abs(mv) < thr: continue
        up = c[i] >= o[i]
        win = (not up) if mv > 0 else up
        outmv = (c[i]-o[i])/o[i]
        out.append((t[i], 1 if win else 0, abs(mv), outmv, up))
    return out

def st(rows, p=0.51):
    if not rows: return {'n':0}
    q = sum(r[1] for r in rows)/len(rows)
    return {'n':len(rows),'q':round(q,4),'net51':round(q-p-fee(p),4)}

print('=== 1. THRESHOLD SENSITIVITY (TEST = last 20d) ===')
for thr in (0.00096, 0.0010, 0.0012, 0.0014, 0.00144, 0.0016):
    sig = build(thr)
    te = [s for s in sig if s[0]-t0 >= 40*86400]
    tr = [s for s in sig if s[0]-t0 < 40*86400]
    print('thr %.5f  TRAIN %s  TEST %s' % (thr, st(tr), st(te)))

print('=== 2. SPLIT SENSITIVITY: q by 10-day window at 12bps ===')
sig = build(0.0012)
for k in range(6):
    w = [s for s in sig if k*10*86400 <= s[0]-t0 < (k+1)*10*86400]
    print('days %2d-%2d %s' % (k*10,(k+1)*10, st(w)))
# alternative test definitions
for cut in (35,40,45,50):
    te=[s for s in sig if s[0]-t0>=cut*86400]
    print('TEST=last %dd:' % (60-cut), st(te))

print('=== 3. TIE + ORACLE-NOISE SENSITIVITY (TEST) ===')
te = [s for s in sig if s[0]-t0 >= 40*86400]
ties = [s for s in te if s[3]==0]
small = [s for s in te if abs(s[3]) < 0.0002]
print('outcome |move|<2bps in TEST: %d of %d (%.1f%%); exact ties: %d'
      % (len(small), len(te), 100*len(small)/len(te), len(ties)))
qs = st(small); print('q on sub-2bps-outcome subset:', qs)
# worst case: assume Coinbase proxy got 11% of sub-2bps outcomes wrong,
# and errors all went in the strategy's favor -> flip 11% of sub-2bps wins to losses
q = sum(s[1] for s in te)/len(te)
wins_small = sum(s[1] for s in small)
flip = 0.11*len(small)  # expected mislabeled count
q_worst = (sum(s[1] for s in te) - flip)/len(te)
q_best  = (sum(s[1] for s in te) + flip)/len(te)
print('TEST q=%.4f; oracle-noise band [%.4f, %.4f]; net51 band [%.4f, %.4f]'
      % (q, q_worst, q_best, q_worst-0.51-fee(0.51), q_best-0.51-fee(0.51)))

print('=== 4. REAL FILLS: pm_prices_sample.json, contrarian side at t0+20s ===')
pm = json.load(open(BASE+'/data/pm_prices_sample.json'))
rows = pm if isinstance(pm, list) else pm.get('rows', pm)
print('pm sample type', type(pm).__name__, 'len', len(rows) if hasattr(rows,'__len__') else '?')
if isinstance(pm, dict): print('keys', list(pm.keys())[:10])
# index cb5m opens by timestamp
oi = {ts:i for i,ts in enumerate(t)}
res = []
for r in rows:
    if not isinstance(r, dict): break
    tt = r.get('t0'); i = oi.get(tt)
    if i is None or i==0: continue
    mv = (o[i]-o[i-1])/o[i-1]
    if abs(mv) < 0.0012: continue
    p20 = r.get('p20')
    if p20 is None: continue
    up_won = r.get('up_won')
    if mv > 0:  # buy Down
        cost = (1-p20) + 0.01; win = 0 if up_won else 1
    else:
        cost = p20 + 0.01; win = 1 if up_won else 0
    res.append((tt, win, cost))
print('matched signal-markets with p20:', len(res))
if res:
    ev_all = sum(w - cst - fee(min(max(cst,0.01),0.99)) for _,w,cst in res)/len(res)
    capped = [(w,cst) for _,w,cst in res if cst <= 0.53]
    q_all = sum(w for _,w,_ in res)/len(res)
    import statistics
    med = statistics.median(cst for _,_,cst in res)
    print('ALL: n=%d q=%.4f median cost=%.3f EV/share=%.4f' % (len(res), q_all, med, ev_all))
    if capped:
        evc = sum(w - cst - fee(cst) for w,cst in capped)/len(capped)
        qc = sum(w for w,_ in capped)/len(capped)
        medc = statistics.median(cst for _,cst in capped)
        print('CAP<=53c: n=%d (%.0f%% pass) q=%.4f median cost=%.3f EV/share=%.4f'
              % (len(capped), 100*len(capped)/len(res), qc, medc, evc))
    frac_above_51 = sum(1 for _,_,cst in res if cst > 0.51)/len(res)
    print('fraction of signals costing >51c at t0+20s: %.2f' % frac_above_51)

print('=== 5. MULTIPLE COMPARISONS ===')
# family reversal60 ran >= 4 sub-analyses (a-d) each with sweeps (thresholds ~6,
# caps ~4, exits ~4, adaptation windows ~3) -> conservatively ~20 effective tests.
# TEST p vs breakeven = 0.0253 one-sided.
for m in (5,10,20):
    print('Bonferroni m=%d: adjusted p vs breakeven = %.3f' % (m, min(1,0.0253*m)))
