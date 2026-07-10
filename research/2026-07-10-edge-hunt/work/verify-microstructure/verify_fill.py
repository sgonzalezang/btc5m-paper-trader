#!/usr/bin/env python3
"""ADVERSARIAL VERIFICATION of 'FILL MODEL: contrarian entry after >=12bps prior move'.
Lens: regime robustness & out-of-sample. Independent reproduction, then re-splits:
  - chronological thirds (first/last) AND per-day (weekly split impossible: pm span=3d, ledger=32h)
  - Kaufman efficiency regime (eff over trailing 12 five-min intervals, gate 0.48)
  - prior-move size buckets
  - join sub-claim (ask vs c20 mid) split in halves
Writes verify_results.json.
"""
import json, math
from collections import defaultdict

S = '/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad'
W = S + '/work/verify-microstructure'

pm = json.load(open(S + '/data/pm_prices_sample.json'))
tr = json.load(open(S + '/data/trades.json'))
cb = json.load(open(S + '/data/cb5m.json'))
cbt, cbo, cbc = cb['t'], cb['o'], cb['c']
cbi = {int(t): i for i, t in enumerate(cbt)}

def prior_move_bps(t0):
    i = cbi.get(t0); j = cbi.get(t0 - 300)
    if i is None or j is None: return None
    return (cbo[i] - cbo[j]) / cbo[j] * 1e4

def kaufman_eff(t0, win=12):
    """Efficiency of the 12 completed 5m intervals ending at t0 (trailing, no lookahead).
    eff = |o[t0] - o[t0-12*300]| / sum |o[k]-o[k-300]|, buffered open-to-open."""
    idx = [cbi.get(t0 - 300 * k) for k in range(win + 1)]
    if any(i is None for i in idx): return None
    opens = [cbo[i] for i in idx]  # opens at t0, t0-300, ..., t0-3600 (newest first)
    net = abs(opens[0] - opens[-1])
    tot = sum(abs(opens[k] - opens[k + 1]) for k in range(win))
    return net / tot if tot > 0 else None

def qtiles(xs, qs=(0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95)):
    xs = sorted(xs); n = len(xs)
    if n == 0: return {}
    out = {}
    for q in qs:
        k = q * (n - 1); f = int(math.floor(k)); c = min(f + 1, n - 1)
        out[f'p{int(q*100)}'] = round(xs[f] + (k - f) * (xs[c] - xs[f]), 4)
    return out

def med(xs):
    xs = sorted(xs); n = len(xs)
    return None if n == 0 else (xs[n // 2] if n % 2 else 0.5 * (xs[n // 2 - 1] + xs[n // 2]))

R = {}

# ============ 1. REPRODUCE HEADLINE ============
sig = []
for r in pm:
    b = prior_move_bps(r['t0'])
    if b is None or abs(b) < 12: continue
    c20 = r['p20'] if b < 0 else round(1 - r['p20'], 4)
    c60 = r['p60'] if b < 0 else round(1 - r['p60'], 4)
    won = r['up_won'] if b < 0 else 1 - r['up_won']
    e = kaufman_eff(r['t0'])
    sig.append(dict(t0=r['t0'], prior_bps=round(b, 2), c20=c20, c60=c60, won=won, eff=e))
sig.sort(key=lambda s: s['t0'])
c20s = [s['c20'] for s in sig]
avail = sum(1 for s in sig if s['c20'] + 0.01 <= 0.55) / len(sig)
R['repro_pm'] = dict(n=len(sig), of=len(pm), c20_q=qtiles(c20s), avail_le_55c=round(avail, 4),
                     win_rate=round(sum(s['won'] for s in sig) / len(sig), 4))
print('REPRO pm-sample: n=%d/%d  c20 %s  avail=%.3f' % (len(sig), len(pm), qtiles(c20s), avail))

fam = [t for t in tr if t['eng'] in ('reversal', 'reversal2', 'latentfire')
       and t['src'] == 'current' and t['status'] == 'settled']
fam.sort(key=lambda t: t['t0'])
ents = [t['entry'] for t in fam]
sh = sum(t['shares'] for t in fam)
pbar = sum(t['shares'] * t['entry'] for t in fam) / sh
R['repro_ledger'] = dict(n=len(fam), entry_q=qtiles(ents), wtd_entry=round(pbar, 4),
                         winrate=round(sum(1 for t in fam if t['result'] == 'win') / len(fam), 4))
print('REPRO ledger: n=%d entry %s wtd=%.4f' % (len(fam), qtiles(ents), pbar))

fam_by = defaultdict(list)
for t in fam: fam_by[t['t0']].append(t)
join = []
for s in sig:
    for t in fam_by.get(s['t0'], []):
        join.append(dict(t0=s['t0'], d=round(t['ask'] - s['c20'], 4)))
ds = [j['d'] for j in join]
R['repro_join'] = dict(n=len(join), median=med(ds), mean=round(sum(ds) / len(ds), 4) if ds else None)
print('REPRO join: n=%d median=%.4f mean=%.4f' % (len(join), med(ds), sum(ds) / len(ds)))

t0_lo = min(t['t0'] for t in fam); t0_hi = max(t['t0'] for t in fam)
elig = [t0 for t0 in (int(x) for x in cbt) if t0_lo <= t0 <= t0_hi
        and (lambda b: b is not None and abs(b) >= 12)(prior_move_bps(t0))]
ent_t0 = set(t['t0'] for t in fam)
R['repro_fillability'] = dict(eligible=len(elig), entered=len(ent_t0),
                              rate=round(len(ent_t0) / len(elig), 3))
print('REPRO fillability: %d/%d = %.3f' % (len(ent_t0), len(elig), len(ent_t0) / len(elig)))

# ============ 2. RE-SPLITS: thirds + per-day ============
def seg_stats_sig(sub):
    if not sub: return dict(n=0)
    c = [s['c20'] for s in sub]
    return dict(n=len(sub), c20_med=med(c), c20_q=qtiles(c),
                avail=round(sum(1 for s in sub if s['c20'] + 0.01 <= 0.55) / len(sub), 3),
                win=round(sum(s['won'] for s in sub) / len(sub), 3))

def seg_stats_led(sub):
    if not sub: return dict(n=0)
    e = [t['entry'] for t in sub]
    shp = sum(t['shares'] for t in sub)
    wr = sum(1 for t in sub if t['result'] == 'win') / len(sub)
    return dict(n=len(sub), entry_med=med(e), entry_q=qtiles(e),
                wtd=round(sum(t['shares'] * t['entry'] for t in sub) / shp, 4),
                win=round(wr, 3))

n = len(sig); k = n // 3
R['pm_thirds'] = dict(first=seg_stats_sig(sig[:k]), mid=seg_stats_sig(sig[k:2 * k]),
                      last=seg_stats_sig(sig[2 * k:]))
n2 = len(fam); k2 = n2 // 3
R['led_thirds'] = dict(first=seg_stats_led(fam[:k2]), mid=seg_stats_led(fam[k2:2 * k2]),
                       last=seg_stats_led(fam[2 * k2:]))
import time
def day(t0): return time.strftime('%m-%d', time.gmtime(t0))
R['pm_by_day'] = {d: seg_stats_sig([s for s in sig if day(s['t0']) == d])
                  for d in sorted(set(day(s['t0']) for s in sig))}
R['led_by_day'] = {d: seg_stats_led([t for t in fam if day(t['t0']) == d])
                   for d in sorted(set(day(t['t0']) for t in fam))}
print('\nPM thirds:', json.dumps({k_: dict(n=v['n'], med=v['c20_med'], avail=v['avail']) for k_, v in R['pm_thirds'].items()}))
print('PM by day:', json.dumps({k_: dict(n=v['n'], med=v.get('c20_med'), avail=v.get('avail')) for k_, v in R['pm_by_day'].items()}))
print('LED thirds:', json.dumps({k_: dict(n=v['n'], med=v['entry_med'], wtd=v['wtd'], win=v['win']) for k_, v in R['led_thirds'].items()}))
print('LED by day:', json.dumps({k_: dict(n=v['n'], med=v.get('entry_med'), wtd=v.get('wtd'), win=v.get('win')) for k_, v in R['led_by_day'].items()}))

# ============ 3. KAUFMAN EFFICIENCY REGIME ============
calm = [s for s in sig if s['eff'] is not None and s['eff'] <= 0.48]
trend = [s for s in sig if s['eff'] is not None and s['eff'] > 0.48]
R['pm_eff'] = dict(calm=seg_stats_sig(calm), trend=seg_stats_sig(trend),
                   eff_q=qtiles([s['eff'] for s in sig if s['eff'] is not None]))
print('\nEFF calm<=0.48:', json.dumps(dict(n=len(calm), med=med([s['c20'] for s in calm]) if calm else None,
      avail=R['pm_eff']['calm'].get('avail'))))
print('EFF trend>0.48:', json.dumps(dict(n=len(trend), med=med([s['c20'] for s in trend]) if trend else None,
      avail=R['pm_eff']['trend'].get('avail'))))

# ledger trades by efficiency at t0
for t in fam: t['_eff'] = kaufman_eff(t['t0'])
lcalm = [t for t in fam if t['_eff'] is not None and t['_eff'] <= 0.48]
ltrend = [t for t in fam if t['_eff'] is not None and t['_eff'] > 0.48]
R['led_eff'] = dict(calm=seg_stats_led(lcalm), trend=seg_stats_led(ltrend))
print('LED eff calm:', json.dumps(dict(n=len(lcalm), med=med([t['entry'] for t in lcalm]) if lcalm else None, win=R['led_eff']['calm'].get('win'))))
print('LED eff trend:', json.dumps(dict(n=len(ltrend), med=med([t['entry'] for t in ltrend]) if ltrend else None, win=R['led_eff']['trend'].get('win'))))

# availability in trending regime — would it have survived a strongly trending stretch?
# use FULL cb5m 60d to count |prior|>=12bps signals per eff regime (frequency), and pm-sample for price
allsig_eff = []
for i in range(13, len(cbt)):
    t0 = int(cbt[i])
    b = prior_move_bps(t0)
    if b is None or abs(b) < 12: continue
    e = kaufman_eff(t0)
    if e is not None: allsig_eff.append((t0, b, e))
n_calm = sum(1 for _, _, e in allsig_eff if e <= 0.48)
R['cb60d_signal_regime'] = dict(n=len(allsig_eff), calm=n_calm, trend=len(allsig_eff) - n_calm,
                                calm_share=round(n_calm / len(allsig_eff), 3))
print('60d cb5m signals: n=%d calm_share=%.3f' % (len(allsig_eff), n_calm / len(allsig_eff)))

# ============ 4. PRIOR-MOVE SIZE + JOIN SPLIT ============
for lo, hi, lbl in ((12, 16, '12-16'), (16, 24, '16-24'), (24, 1e9, '24+')):
    sub = [s for s in sig if lo <= abs(s['prior_bps']) < hi]
    R['pm_size_' + lbl] = seg_stats_sig(sub)
    print('size %s: n=%d med=%s avail=%s' % (lbl, len(sub),
          R['pm_size_' + lbl].get('c20_med'), R['pm_size_' + lbl].get('avail')))

join.sort(key=lambda j: j['t0'])
h = len(join) // 2
R['join_halves'] = dict(first=dict(n=h, med=med([j['d'] for j in join[:h]])),
                        last=dict(n=len(join) - h, med=med([j['d'] for j in join[h:]])))
print('JOIN halves:', json.dumps(R['join_halves']))

# TEST-n audit per the verifier rubric
R['test_n_audit'] = dict(
    ledger_last_third=len(fam[2 * k2:]),
    pm_last_third=len(sig[2 * k:]),
    join_total=len(join),
    pm_total=len(sig))
print('\nTEST-n audit:', json.dumps(R['test_n_audit']))

json.dump(R, open(W + '/verify_results.json', 'w'), indent=1)
print('\nsaved', W + '/verify_results.json')
