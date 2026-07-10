"""Part D: autopsy of the live value engine's settled paper trades in trades.json.
Realized win rate vs fee break-even by entry-price / entrySec / drift buckets,
plus single-gate counterfactuals: which one gate change recovers the most PnL,
checked for stability across chronological halves.
"""
import json, math, sys
sys.path.insert(0, '/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad/work/fairvalue')
from fv_lib import *

OUT = SC + '/work/fairvalue'
tr = json.load(open(DATA + '/trades.json'))
val = [t for t in tr if t.get('eng') == 'value' and t.get('status') == 'settled'
       and t.get('result') in ('win', 'loss') and t.get('entry') is not None]
val.sort(key=lambda t: t['at'])
print(f'settled value trades: {len(val)}  span {val[0]["t0"]}..{val[-1]["t0"]}')
tot = sum(t['pnl'] for t in val)
wins = sum(1 for t in val if t['result'] == 'win')
avg_e = sum(t['entry'] for t in val) / len(val)
print(f'total pnl ${tot:.0f}  win {wins}/{len(val)} = {wins/len(val):.3f}  avg entry {avg_e:.3f}  breakeven at avg {breakeven(avg_e):.3f}')

def bucket_table(val, keyf, buckets, label):
    print(f'\n== by {label} ==')
    out = []
    for lo, hi in buckets:
        sub = [t for t in val if lo <= keyf(t) < hi]
        if not sub: continue
        n = len(sub); w = sum(1 for t in sub if t['result'] == 'win') / n
        pe = sum(t['entry'] for t in sub) / n
        pnl = sum(t['pnl'] for t in sub)
        be = breakeven(pe)
        out.append({'lo': lo, 'hi': hi, 'n': n, 'win': round(w, 3), 'avg_entry': round(pe, 3),
                    'breakeven': round(be, 3), 'edge': round(w - be, 3), 'pnl': round(pnl, 0)})
        print(f'  [{lo},{hi}) n={n:3d} win={w:.3f} avg_entry={pe:.3f} be={be:.3f} edge={w-be:+.3f} pnl=${pnl:+.0f}')
    return out

res = {}
res['by_entry'] = bucket_table(val, lambda t: t['entry'],
    [(0, 0.50), (0.50, 0.55), (0.55, 0.60), (0.60, 0.65), (0.65, 0.70), (0.70, 1.01)], 'entry price')
res['by_entrysec'] = bucket_table(val, lambda t: t.get('entrySec', -1),
    [(0, 30), (30, 60), (60, 90), (90, 120), (120, 180), (180, 301)], 'entrySec')
res['by_drift'] = bucket_table(val, lambda t: abs(t.get('driftPct') or 0),
    [(0, 0.01), (0.01, 0.02), (0.02, 0.03), (0.03, 0.05), (0.05, 0.10), (0.10, 9)], '|driftPct| (%)')
res['by_side'] = bucket_table(val, lambda t: 0 if t['side'] == 'up' else 1, [(0, 1), (1, 2)], 'side (0=up,1=down)')

# implied fv at entry: gate was ask+slip < fv - 0.03 -> fv > entry + 0.03 (entry=ask+slip)
# so entry+0.03 is a LOWER bound on the engine's fv; realized win rate vs that bound:
print('\n== engine self-belief vs reality ==')
lb = [t['entry'] + 0.03 for t in val]
print(f'  mean lower-bound fv (entry+margin) = {sum(lb)/len(lb):.3f}   realized win rate = {wins/len(val):.3f}')

# single-gate counterfactuals
half = len(val) // 2
gates = [
    ('entry<=0.50', lambda t: t['entry'] <= 0.50),
    ('entry<=0.55', lambda t: t['entry'] <= 0.55),
    ('entry<=0.60', lambda t: t['entry'] <= 0.60),
    ('entry<=0.65', lambda t: t['entry'] <= 0.65),
    ('entrySec<=60', lambda t: t.get('entrySec', 999) <= 60),
    ('entrySec>=60', lambda t: t.get('entrySec', -1) >= 60),
    ('entrySec>=120', lambda t: t.get('entrySec', -1) >= 120),
    ('entrySec<=120', lambda t: t.get('entrySec', 999) <= 120),
    ('|drift|>=0.02', lambda t: abs(t.get('driftPct') or 0) >= 0.02),
    ('|drift|<=0.04', lambda t: abs(t.get('driftPct') or 0) <= 0.04),
    ('|drift|>=0.03', lambda t: abs(t.get('driftPct') or 0) >= 0.03),
    ('side==up', lambda t: t['side'] == 'up'),
    ('side==down', lambda t: t['side'] == 'down'),
]
print(f'\n== single-gate counterfactuals (base pnl ${tot:.0f}, n={len(val)}) ==')
rows = []
for name, f in gates:
    keep = [t for t in val if f(t)]
    pnl = sum(t['pnl'] for t in keep)
    d1 = sum(t['pnl'] for t in val[:half] if f(t)) - sum(t['pnl'] for t in val[:half])
    d2 = sum(t['pnl'] for t in val[half:] if f(t)) - sum(t['pnl'] for t in val[half:])
    n = len(keep); w = sum(1 for t in keep if t['result'] == 'win') / max(1, n)
    pe = sum(t['entry'] for t in keep) / max(1, n)
    rows.append({'gate': name, 'n': n, 'win': round(w, 3), 'avg_entry': round(pe, 3),
                 'pnl': round(pnl, 0), 'improvement': round(pnl - tot, 0),
                 'impr_half1': round(d1, 0), 'impr_half2': round(d2, 0)})
    print(f'  {name:15s} n={n:3d} win={w:.3f} entry={pe:.3f} pnl=${pnl:+7.0f} improve=${pnl-tot:+7.0f} (h1 {d1:+.0f} / h2 {d2:+.0f})')
res['gates'] = rows

# does the mis-scaled live sigma explain it? live fv uses range/1.6 vol; our kappa*~1.05 on a
# proper EWMA. Compare implied entry-quality: expected win rate from OUR calibrated model at the
# engine's own entries, using driftPct and entrySec (sigma from cb5m EWMA lam=.95).
t5, o5, c5, r5, up5 = cb5m_series()
sig5 = ewma_sigma(t5, r5, 0.95)
sig_by_t0 = {t5[i]: sig5[i] for i in range(len(t5)) if sig5[i] is not None}
KAP = 1.05
have = 0; tot_q = 0.0; ev = 0.0; per = []
for t in val:
    sg = sig_by_t0.get(t['t0'])
    dp = t.get('driftPct'); es = t.get('entrySec')
    if sg is None or dp is None or es is None or not (0 <= es < 300): continue
    d = math.log(1 + dp / 100.0)  # driftPct is % move from open at entry (signed for side? check)
    # driftPct appears positive in samples for both sides; treat as |move| toward the taken side
    q = phi(abs(d) / (KAP * sg * math.sqrt((300 - es) / 300)))
    e = t['entry']
    per.append({'q': q, 'e': e, 'won': 1 if t['result'] == 'win' else 0})
    tot_q += q; ev += q - e - fee(e); have += 1
print(f'\n== recalibrated-model view of the engine entries (n={have}) ==')
print(f'  mean calibrated q = {tot_q/have:.3f}  vs mean entry = {sum(p["e"] for p in per)/have:.3f}')
print(f'  model-implied EV/share at engine fills = {ev/have:+.4f}')
print(f'  realized win rate on these = {sum(p["won"] for p in per)/have:.3f}')
res['recal'] = {'n': have, 'mean_q': tot_q / have, 'mean_entry': sum(p['e'] for p in per) / have,
                'model_ev_per_share': ev / have, 'realized_win': sum(p['won'] for p in per) / have}

json.dump(res, open(OUT + '/d_autopsy.json', 'w'), indent=1)
print('\nsaved', OUT + '/d_autopsy.json')
