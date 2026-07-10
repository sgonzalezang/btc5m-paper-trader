#!/usr/bin/env python3
"""Independent reproduction of the FILL MODEL finding (verify-microstructure).

Re-derives from raw data only (cb5m.json, pm_prices_sample.json, trades.json):
 1. Buffered open-to-open prior moves >= 12bps -> contrarian-side price at ~20s
    from pm_prices_sample (uncensored CLOB minute distribution).
 2. Availability <= 55c (+/- slip variants).
 3. Ledger reversal-family fill distribution (n, entry quantiles, share-wtd mean,
    entrySec quantiles, win rate).
 4. t0 join of ledger ask vs pm-sample contrarian 20s price.
 5. Threshold sensitivity: 12bps +/-20%, 55c cap +/-20%.
"""
import json
from statistics import median

S = '/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad'

def q(xs, p):
    """Linear-interpolation quantile (numpy default)."""
    xs = sorted(xs)
    if not xs: return None
    k = (len(xs) - 1) * p
    f = int(k); c = min(f + 1, len(xs) - 1)
    return xs[f] + (xs[c] - xs[f]) * (k - f)

def qdict(xs, ps=(5,10,25,50,75,90,95)):
    return {f'p{p}': round(q(xs, p/100), 4) for p in ps}

# ---------- 1. signals from cb5m (buffered open-to-open) ----------
cb = json.load(open(S + '/data/cb5m.json'))
t, o, c = cb['t'], cb['o'], cb['c']
idx = {tt: i for i, tt in enumerate(t)}
def prior_move(t0):
    i = idx.get(t0)
    if i is None or i == 0: return None
    if t[i-1] != t0 - 300: return None      # require consecutive candle
    return (o[i] - o[i-1]) / o[i-1]

pm = json.load(open(S + '/data/pm_prices_sample.json'))
print('pm sample rows:', len(pm))

def signal_stats(thr_bps, cap, slip=0.01):
    sig = []
    for r in pm:
        mv = prior_move(r['t0'])
        if mv is None or abs(mv) < thr_bps / 10000: continue
        if r.get('p20') is None: continue
        # contrarian side: fade the prior move
        c20 = (1 - r['p20']) if mv > 0 else r['p20']
        c60 = None
        if r.get('p60') is not None:
            c60 = (1 - r['p60']) if mv > 0 else r['p60']
        # did contrarian side win?
        cwin = (1 - r['up_won']) if mv > 0 else r['up_won']
        sig.append({'t0': r['t0'], 'mv': mv, 'c20': c20, 'c60': c60, 'win': cwin})
    n = len(sig)
    c20s = [s['c20'] for s in sig]
    c60s = [s['c60'] for s in sig if s['c60'] is not None]
    out = {
        'thr_bps': thr_bps, 'cap': cap, 'n': n,
        'c20_q': qdict(c20s) if c20s else None,
        'c60_q': qdict(c60s) if c60s else None,
        'avail_c20_le_cap': round(sum(1 for x in c20s if x <= cap) / n, 4) if n else None,
        'avail_c20_plus_slip_le_cap_plus_slip': round(sum(1 for x in c20s if x + slip <= cap + slip) / n, 4) if n else None,
        'win_rate': round(sum(s['win'] for s in sig) / n, 4) if n else None,
    }
    return out, sig

base, sig = signal_stats(12, 0.55)
print('\n=== UNCENSORED PM SAMPLE (12bps, cap 55c) ===')
print(json.dumps(base, indent=1))

# bucket split like family: 12-16 vs >=16
lo = [s['c20'] for s in sig if abs(s['mv']) < 16/10000]
hi = [s['c20'] for s in sig if abs(s['mv']) >= 16/10000]
print('c20 median 12-16bps:', round(median(lo), 4) if lo else None, f'(n={len(lo)})',
      ' >=16bps:', round(median(hi), 4) if hi else None, f'(n={len(hi)})')

# ---------- 2. ledger reversal-family fills ----------
tr = json.load(open(S + '/data/trades.json'))
fam = [x for x in tr if x.get('eng') in ('reversal', 'reversal2', 'latentfire')]
print('\n=== LEDGER FAMILY ===  n =', len(fam))
entries = [x['entry'] for x in fam if x.get('entry') is not None]
asks    = [x['ask'] for x in fam if x.get('ask') is not None]
esec    = [x['entrySec'] for x in fam if x.get('entrySec') is not None]
shares  = [(x['entry'], x.get('shares', 0)) for x in fam if x.get('entry') is not None]
wins    = [1 if x.get('result') == 'win' else 0 for x in fam if x.get('result') in ('win', 'loss')]
wtd = sum(e * s for e, s in shares) / sum(s for _, s in shares)
print('entry_q:', json.dumps(qdict(entries)))
print('ask_q:  ', json.dumps(qdict(asks)))
print('entrySec_q:', json.dumps(qdict(esec)), 'n_esec =', len(esec))
print('share-wtd mean entry:', round(wtd, 4), ' q* =', round(wtd + 0.07 * wtd * (1 - wtd), 4))
print('win rate:', round(sum(wins) / len(wins), 4), f'(n={len(wins)})')
pnl = sum(x.get('pnl', 0) for x in fam)
print('family pnl:', round(pnl, 2))

# chrono split of ledger entries (2/3 - 1/3)
fam_s = sorted(fam, key=lambda x: x['t0'])
k = len(fam_s) * 2 // 3
e1 = [x['entry'] for x in fam_s[:k]]; e2 = [x['entry'] for x in fam_s[k:]]
w2 = [1 if x.get('result') == 'win' else 0 for x in fam_s[k:] if x.get('result') in ('win', 'loss')]
print('entry median train/test:', median(e1), median(e2))
# last third win rate
n3 = len(fam_s) // 3
last3 = [1 if x.get('result') == 'win' else 0 for x in fam_s[-n3:] if x.get('result') in ('win', 'loss')]
print('last-third win rate:', round(sum(last3) / len(last3), 4), f'(n={len(last3)})')

# ---------- 3. t0 join ledger ask vs pm c20 ----------
pmidx = {r['t0']: r for r in pm}
joins = []
for x in fam:
    r = pmidx.get(x['t0'])
    if not r or r.get('p20') is None: continue
    c20 = (1 - r['p20']) if x['side'] == 'down' else r['p20']
    joins.append(x['ask'] - c20)
print('\n=== JOIN (ledger ask - pm c20 same t0/side) ===  n =', len(joins))
if joins:
    print('median:', round(median(joins), 4), 'mean:', round(sum(joins) / len(joins), 4))
    print('q:', json.dumps(qdict(joins)))

# ---------- 4. threshold sensitivity ----------
print('\n=== SENSITIVITY ===')
res = {}
for thr in (9.6, 12, 14.4):
    for cap in (0.44, 0.55, 0.66):
        st, _ = signal_stats(thr, cap)
        res[f'thr{thr}_cap{cap}'] = {'n': st['n'], 'c20_med': st['c20_q']['p50'] if st['c20_q'] else None,
                                     'avail': st['avail_c20_le_cap'], 'win': st['win_rate']}
for kk, v in res.items():
    print(kk, v)

json.dump({'base': base, 'sensitivity': res,
           'ledger': {'n': len(fam), 'entry_q': qdict(entries), 'wtd_entry': round(wtd, 4),
                      'winrate': round(sum(wins) / len(wins), 4),
                      'last_third_winrate': round(sum(last3) / len(last3), 4)},
           'join': {'n': len(joins), 'median': round(median(joins), 4) if joins else None,
                    'mean': round(sum(joins) / len(joins), 4) if joins else None}},
          open(S + '/work/verify-microstructure/repro_results.json', 'w'), indent=1)
print('\nsaved repro_results.json')
