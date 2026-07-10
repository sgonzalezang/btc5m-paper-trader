#!/usr/bin/env python3
"""Adversarial verification of the FILL MODEL finding — lens: regime robustness & out-of-sample.
Independent reproduction from data/, then re-splits (by day, by thirds) and Kaufman-efficiency
regime segmentation of: (1) uncensored contrarian c20 distribution + <=55c availability,
(2) censored ledger fill distribution, (3) ask-vs-c20 join, (4) fillability.
Outputs: regime_attack_results.json
"""
import json, math, time, random
from collections import defaultdict

S = '/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad'
W = S + '/work/verify-microstructure'
random.seed(7)

pm = json.load(open(S + '/data/pm_prices_sample.json'))
tr = json.load(open(S + '/data/trades.json'))
cb = json.load(open(S + '/data/cb5m.json'))
cbt = [int(t) for t in cb['t']]; cbo = cb['o']
cbi = {t: i for i, t in enumerate(cbt)}

def prior_move_bps(t0):
    i = cbi.get(t0); j = cbi.get(t0 - 300)
    if i is None or j is None: return None
    return (cbo[i] - cbo[j]) / cbo[j] * 1e4

def kaufman_eff(t0, win=12):
    """Efficiency over the `win` completed 5m intervals ending at t0 (open-to-open moves)."""
    i = cbi.get(t0)
    if i is None or i < win: return None
    net = abs(cbo[i] - cbo[i - win])
    den = sum(abs(cbo[k + 1] - cbo[k]) for k in range(i - win, i))
    return net / den if den > 0 else None

def qtiles(xs, qs=(0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95)):
    xs = sorted(xs); n = len(xs)
    if n == 0: return None
    out = {}
    for q in qs:
        k = q * (n - 1); f = int(math.floor(k)); c = min(f + 1, n - 1)
        out[f'p{int(q*100)}'] = round(xs[f] + (k - f) * (xs[c] - xs[f]), 4)
    return out

def med(xs):
    xs = sorted(xs); n = len(xs)
    return None if n == 0 else (xs[n // 2] if n % 2 else 0.5 * (xs[n // 2 - 1] + xs[n // 2]))

out = {}

# ---------- REPRODUCTION (independent code path) ----------
sig = []
for r in pm:
    b = prior_move_bps(r['t0'])
    if b is None or abs(b) < 12: continue
    c20 = r['p20'] if b < 0 else 1 - r['p20']
    c60 = r['p60'] if b < 0 else 1 - r['p60']
    won = r['up_won'] if b < 0 else 1 - r['up_won']
    e = kaufman_eff(r['t0'])
    sig.append(dict(t0=r['t0'], b=b, c20=round(c20, 4), c60=round(c60, 4), won=won, eff=e))
sig.sort(key=lambda s: s['t0'])
c20s = [s['c20'] for s in sig]
avail = sum(1 for s in sig if s['c20'] + 0.01 <= 0.55) / len(sig)
out['repro_pm'] = dict(n=len(sig), of=len(pm), c20_q=qtiles(c20s),
                       avail_le_55c=round(avail, 4),
                       win_rate=round(sum(s['won'] for s in sig) / len(sig), 4))

fam = [t for t in tr if t['eng'] in ('reversal', 'reversal2', 'latentfire')
       and t['src'] == 'current' and t['status'] == 'settled']
fam.sort(key=lambda t: t['t0'])
ents = [t['entry'] for t in fam]
sh = sum(t['shares'] for t in fam)
pbar = sum(t['shares'] * t['entry'] for t in fam) / sh
out['repro_ledger'] = dict(n=len(fam), entry_q=qtiles(ents), wtd_entry=round(pbar, 4),
                           winrate=round(sum(1 for t in fam if t['result'] == 'win') / len(fam), 4))

fam_by_t0 = defaultdict(list)
for t in fam: fam_by_t0[t['t0']].append(t)
join = [(s, t) for s in sig for t in fam_by_t0.get(s['t0'], [])]
ds = [t['ask'] - s['c20'] for s, t in join]
out['repro_join'] = dict(n=len(ds), median=round(med(ds), 4) if ds else None,
                         mean=round(sum(ds) / len(ds), 4) if ds else None)

t0_lo = min(t['t0'] for t in fam); t0_hi = max(t['t0'] for t in fam)
elig = [t0 for t0 in cbt if t0_lo <= t0 <= t0_hi
        and (lambda b: b is not None and abs(b) >= 12)(prior_move_bps(t0))]
ent_t0 = set(t['t0'] for t in fam)
out['repro_fillability'] = dict(eligible=len(elig), entered=len(ent_t0),
                                rate=round(len(ent_t0) / len(elig), 4))

# ---------- ATTACK 1: re-splits (by UTC day = "week" proxy given 3-day span; and thirds) ----------
def seg_pm(subset, label, store):
    if not subset:
        store[label] = dict(n=0); return
    cs = [s['c20'] for s in subset]
    store[label] = dict(n=len(subset), c20_med=round(med(cs), 4), c20_q=qtiles(cs),
                        avail=round(sum(1 for s in subset if s['c20'] + 0.01 <= 0.55) / len(subset), 4),
                        win=round(sum(s['won'] for s in subset) / len(subset), 4))

split_pm = {}
for s in sig:
    day = time.strftime('%m-%d', time.gmtime(s['t0']))
    s['day'] = day
for day in sorted(set(s['day'] for s in sig)):
    seg_pm([s for s in sig if s['day'] == day], 'day_' + day, split_pm)
n3 = len(sig)
seg_pm(sig[:n3 // 3], 'third_1', split_pm)
seg_pm(sig[n3 // 3:2 * n3 // 3], 'third_2', split_pm)
seg_pm(sig[2 * n3 // 3:], 'third_3', split_pm)
seg_pm(sig[:2 * n3 // 3], 'train_2of3', split_pm)
seg_pm(sig[2 * n3 // 3:], 'test_1of3', split_pm)
out['pm_splits'] = split_pm

def seg_led(subset, label, store):
    if not subset:
        store[label] = dict(n=0); return
    es = [t['entry'] for t in subset]
    shx = sum(t['shares'] for t in subset)
    store[label] = dict(n=len(subset), entry_med=round(med(es), 4), entry_q=qtiles(es),
                        wtd_entry=round(sum(t['shares'] * t['entry'] for t in subset) / shx, 4),
                        win=round(sum(1 for t in subset if t['result'] == 'win') / len(subset), 4))

split_led = {}
for t in fam:
    t['day'] = time.strftime('%m-%d', time.gmtime(t['t0']))
for day in sorted(set(t['day'] for t in fam)):
    seg_led([t for t in fam if t['day'] == day], 'day_' + day, split_led)
nf = len(fam)
seg_led(fam[:nf // 3], 'third_1', split_led)
seg_led(fam[nf // 3:2 * nf // 3], 'third_2', split_led)
seg_led(fam[2 * nf // 3:], 'third_3', split_led)
seg_led(fam[:2 * nf // 3], 'train_2of3', split_led)
seg_led(fam[2 * nf // 3:], 'test_1of3', split_led)
out['ledger_splits'] = split_led

# ---------- ATTACK 2: Kaufman-efficiency regimes ----------
eff_pm = {}
calm = [s for s in sig if s['eff'] is not None and s['eff'] <= 0.48]
trend = [s for s in sig if s['eff'] is not None and s['eff'] > 0.48]
seg_pm(calm, 'calm_eff_le_048', eff_pm)
seg_pm(trend, 'trend_eff_gt_048', eff_pm)
out['pm_by_eff'] = eff_pm
out['pm_eff_dist'] = qtiles([s['eff'] for s in sig if s['eff'] is not None])

eff_led = {}
for t in fam:
    t['eff'] = kaufman_eff(t['t0'])
seg_led([t for t in fam if t['eff'] is not None and t['eff'] <= 0.48], 'calm_eff_le_048', eff_led)
seg_led([t for t in fam if t['eff'] is not None and t['eff'] > 0.48], 'trend_eff_gt_048', eff_led)
out['ledger_by_eff'] = eff_led

# join by eff
ds_calm = [t['ask'] - s['c20'] for s, t in join if s['eff'] is not None and s['eff'] <= 0.48]
ds_trend = [t['ask'] - s['c20'] for s, t in join if s['eff'] is not None and s['eff'] > 0.48]
out['join_by_eff'] = dict(calm=dict(n=len(ds_calm), med=round(med(ds_calm), 4) if ds_calm else None),
                          trend=dict(n=len(ds_trend), med=round(med(ds_trend), 4) if ds_trend else None))
# join by halves
jh = len(join)
join_sorted = sorted(join, key=lambda x: x[0]['t0'])
d1 = [t['ask'] - s['c20'] for s, t in join_sorted[:jh // 2]]
d2 = [t['ask'] - s['c20'] for s, t in join_sorted[jh // 2:]]
out['join_halves'] = dict(h1=dict(n=len(d1), med=round(med(d1), 4), mean=round(sum(d1) / len(d1), 4)),
                          h2=dict(n=len(d2), med=round(med(d2), 4), mean=round(sum(d2) / len(d2), 4)))

# ---------- ATTACK 3: how trending was this window vs the 60-day history? ----------
# distribution of eff across all cb5m intervals, and share of signal-eligible intervals per eff bucket
effs_all, effs_window = [], []
for idx, t0 in enumerate(cbt):
    e = kaufman_eff(t0)
    if e is None: continue
    effs_all.append(e)
    if min(s['t0'] for s in sig) <= t0 <= max(s['t0'] for s in sig):
        effs_window.append(e)
out['eff_context'] = dict(all60d_q=qtiles(effs_all), window_q=qtiles(effs_window),
                          all60d_share_calm=round(sum(1 for e in effs_all if e <= 0.48) / len(effs_all), 4),
                          window_share_calm=round(sum(1 for e in effs_window if e <= 0.48) / len(effs_window), 4))

# ---------- ATTACK 4: prior-move-size parameter stability across thirds ----------
size_stab = {}
for lbl, sub in (('third_1', sig[:n3 // 3]), ('third_2', sig[n3 // 3:2 * n3 // 3]), ('third_3', sig[2 * n3 // 3:])):
    small = [s['c20'] for s in sub if 12 <= abs(s['b']) < 16]
    big = [s['c20'] for s in sub if abs(s['b']) >= 16]
    size_stab[lbl] = dict(n_small=len(small), med_small=round(med(small), 4) if small else None,
                          n_big=len(big), med_big=round(med(big), 4) if big else None)
out['size_split_stability'] = size_stab

# ---------- bootstrap CI on TEST-third availability (1h blocks) ----------
def block_boot_avail(subset, B=2000):
    if not subset: return None
    blocks = defaultdict(list)
    for s in subset: blocks[s['t0'] // 3600].append(s)
    keys = list(blocks)
    stats = []
    for _ in range(B):
        samp = [x for k in (random.choice(keys) for _ in keys) for x in blocks[k]]
        stats.append(sum(1 for s in samp if s['c20'] + 0.01 <= 0.55) / len(samp))
    stats.sort()
    return [round(stats[int(0.025 * B)], 3), round(stats[int(0.975 * B)], 3)]

out['avail_ci'] = dict(full=block_boot_avail(sig), test_third=block_boot_avail(sig[2 * n3 // 3:]))

json.dump(out, open(W + '/regime_attack_results.json', 'w'), indent=1)
print(json.dumps(out, indent=1))
