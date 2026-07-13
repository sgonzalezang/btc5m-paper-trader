#!/usr/bin/env python3
"""R5 verification, part 2: the stopped-trade survivorship correction.

The 3,495-trade pool underlying R5's decomposition EXCLUDES 70 settled trades
with result='stopped' (stop-loss exits; btcClose=null in the ledger) while
INCLUDING 71 hedge-flagged trades (hold-to-res q_sw=0.984 -- hedges are placed
conditional on leading late in the interval). Stops fire conditional on losing:
imputed hold-to-resolution wr of the stopped 70 = 0.014 (69/70 lost; Coinbase
open(t0) vs open(t0+300) proxy, all 70 imputable, no ties).

Restoring the stopped trades to the pool flips gross selection at mid from
+0.55c/sh to -0.48c/sh. This is the honest estimate of what R5 calls
'positive selection at mid'. Writes results_stopped.json.
"""
import json, statistics, collections, random, os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = '/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt'

def fee(p): return 0.07 * p * (1 - p)

tr = json.load(open(os.path.join(ROOT, 'data', 'trades_unified.json')))
cb = json.load(open(os.path.join(ROOT, 'data', 'cb1m.json')))
idx = {ts: i for i, ts in enumerate(cb['t'])}
o = cb['o']

def res_up(t0):
    i0, i5 = idx.get(t0), idx.get(t0 + 300)
    if i0 is None or i5 is None: return None
    d = o[i5] - o[i0]
    return None if d == 0 else d > 0

sett = [t for t in tr if t.get('status') == 'settled']
stop = [t for t in sett if t.get('result') == 'stopped']
wl   = [t for t in sett if t.get('result') in ('win', 'loss')]

imp = []
for t in stop:
    r = res_up(t['t0'])
    if r is not None:
        imp.append((t, 1.0 if (r == (t['side'] == 'up')) else 0.0))

aug = [(t, 1.0 if t['result'] == 'win' else 0.0) for t in wl] + imp
sh = sum(t['shares'] for t, _ in aug)
q  = sum(t['shares'] * w for t, w in aug) / sh
a  = sum(t['shares'] * t['ask'] for t, _ in aug) / sh
p  = sum(t['shares'] * t['entry'] for t, _ in aug) / sh
f  = sum(t['shares'] * fee(t['entry']) for t, _ in aug) / sh

byb = collections.defaultdict(list)
for t, w in aug:
    byb[t['t0'] // 3600].append((t['shares'] * (w - (t['ask'] - 0.005)), t['shares']))
blocks = list(byb.values()); rng = random.Random(41); outs = []
for _ in range(4000):
    s = []
    for _ in range(len(blocks)):
        s.extend(blocks[rng.randrange(len(blocks))])
    outs.append(sum(x for x, _ in s) / sum(y for _, y in s))
outs.sort()

H = [t for t in wl if t.get('hedge')]
shH = sum(t['shares'] for t in H)
res = dict(
    n_stopped=len(stop), n_stopped_imputable=len(imp),
    stopped_hold_to_res_wr=round(statistics.fmean(w for _, w in imp), 4),
    stopped_avg_ask=round(statistics.fmean(t['ask'] for t, _ in imp), 4),
    stopped_ledger_pnl=round(sum(t['pnl'] for t in stop), 2),
    hedged_n=len(H),
    hedged_q_sw=round(sum(t['shares'] * (1.0 if t['result'] == 'win' else 0.0) for t in H) / shH, 4),
    hedged_ask_sw=round(sum(t['shares'] * t['ask'] for t in H) / shH, 4),
    augmented_pool=dict(
        n=len(aug), q_sw=round(q, 4), ask_sw=round(a, 4),
        sel_at_ask_c=round(100 * (q - a), 2),
        sel_at_mid_c=round(100 * (q - a + 0.005), 2),
        sel_at_mid_ci95_c=[round(100 * outs[int(.025 * len(outs))], 2),
                           round(100 * outs[int(.975 * len(outs))], 2)],
        sel_at_mid_p_le0=round(sum(1 for x in outs if x <= 0) / len(outs), 3),
        fee_c=round(100 * f, 2), slip_c=round(100 * (p - a), 2),
        net_c=round(100 * (q - p - f), 2)),
    full_ledger_pnl_incl_stopped=round(sum(t['pnl'] for t in sett), 2))

json.dump(res, open(os.path.join(HERE, 'results_stopped.json'), 'w'), indent=1)
print(json.dumps(res, indent=1))
