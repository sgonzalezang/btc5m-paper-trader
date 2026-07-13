#!/usr/bin/env python3
"""Adversarial verification of R3 (drift-leader stale-ask capture, 60-65c, +14c/sh).

Tests:
 1. Reproduce the claimed cells (ruleA_p_ge60 n=71 and band cell n=89/162).
 2. Exact binomial + hourly-block bootstrap p, WITHOUT the autopsy's code.
 3. Neighbor cells (50-55, 55-60, 65-75) — mechanism consistency.
 4. Reconcile with pooled momentum 60-66c fills.
 5. Candle-drift replacement: recompute the cell with drift from cb1m opens
    (strictly pre-decision, independent of the bot's REST candle 'last').
 6. btcEntry vs cb1m sanity: is the bot feed consistent with candle path at fill?
 7. Pre-registrable split test: select best cell on Jul 7-8, evaluate Jul 9-10 (and reverse).
 8. Honest multiplicity count + Bonferroni on the cluster-robust p.
Writes results.json in this dir.
"""
import json, math, random, collections, datetime, os

HERE = os.path.dirname(os.path.abspath(__file__))
D12 = '/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data'

def fee_ps(p): return 0.07*p*(1-p)
def qstar(p): return p + fee_ps(p)
def wilson(k, n, z=1.96):
    if n == 0: return (0.0, 1.0)
    ph = k/n; d = 1+z*z/n; c = ph+z*z/(2*n); h = z*math.sqrt(ph*(1-ph)/n+z*z/(4*n*n))
    return ((c-h)/d, (c+h)/d)
def binom_sf(k, n, p):
    """P(X >= k) for X~Bin(n,p), exact."""
    from math import comb
    return sum(comb(n, i)*p**i*(1-p)**(n-i) for i in range(k, n+1))
def bboot(items, valfn, B=6000, seed=7):
    blocks = collections.defaultdict(list)
    for t in items: blocks[t['t0']//3600].append(valfn(t))
    bl = list(blocks.values()); rng = random.Random(seed)
    flat = [v for b in bl for v in b]
    if not flat: return None
    mu = sum(flat)/len(flat); st = []
    for _ in range(B):
        s = c = 0
        for _ in range(len(bl)):
            b = bl[rng.randrange(len(bl))]; s += sum(b); c += len(b)
        if c: st.append(s/c)
    st.sort()
    return dict(mean=round(mu, 4),
                ci95=[round(st[int(.025*len(st))], 4), round(st[int(.975*len(st))], 4)],
                p_le0=round(sum(1 for x in st if x <= 0)/len(st), 4),
                n=len(flat), n_blocks=len(bl))

tr = json.load(open(os.path.join(D12, 'trades_unified.json')))
S = [t for t in tr if t.get('status') == 'settled' and t.get('result') in ('win', 'loss')]
MOM = {'loose', 'floor', 'band', 'value', 'fade', 'strict', 'capless', 'calm'}
for t in S:
    t['w'] = 1.0 if t['result'] == 'win' else 0.0
    t['p'] = t['entry']
    d = (t['btcEntry']-t['btcOpen'])/t['btcOpen']*1e4
    t['sdrift'] = d if t['side'] == 'up' else -d
    t['ev_ps'] = t['w'] - t['p'] - fee_ps(t['p'])
mom = [t for t in S if t['eng'] in MOM]
out = {}

def stat(ts, label):
    n = len(ts); k = sum(int(t['w']) for t in ts)
    if n == 0: return dict(label=label, n=0)
    pm = sum(t['p'] for t in ts)/n
    ev = 100*sum(t['ev_ps'] for t in ts)/n
    lo, hi = wilson(k, n)
    return dict(label=label, n=n, wins=k, q=round(k/n, 4), p_mean=round(pm, 4),
                qstar=round(qstar(pm), 4), ev_c=round(ev, 2),
                q_ci95=[round(lo, 4), round(hi, 4)])

# ---------- 1. reproduce
dd = {}
for t in mom: dd.setdefault((t['t0'], t['side']), []).append(t)
um = [v[0] for v in dd.values()]
ruleA = [t for t in um if t['sdrift'] >= 4 and t['p'] >= 0.60]
out['repro_ruleA_ge60'] = stat(ruleA, 'dedup-first, drift>=4, p>=0.60 (claimed n=71)')
band_tr = [t for t in mom if t['sdrift'] >= 4 and 0.60 <= t['p'] < 0.65]
ddb = {}
for t in band_tr: ddb.setdefault((t['t0'], t['side']), []).append(t)
band_u = [v[0] for v in ddb.values()]
out['repro_band6065_dedup'] = stat(band_u, 'filter-first dedup, drift>=4, p in [0.60,0.65) (claimed n=89)')

# ---------- 2. honest p for the claimed cell: exact binomial vs per-trade breakeven
# breakeven win prob for the cell = mean qstar of its trades
for key, cell in (('ruleA_ge60', ruleA), ('band6065', band_u)):
    n = len(cell); k = sum(int(t['w']) for t in cell)
    qs = sum(qstar(t['p']) for t in cell)/n
    out[f'pval_{key}'] = dict(
        n=n, wins=k, breakeven_q=round(qs, 4),
        binom_p_iid=round(binom_sf(k, n, qs), 5),
        block_boot=bboot(cell, lambda t: t['ev_ps']))

# intervals per hour (clustering degree)
hrs = collections.Counter(t['t0']//3600 for t in ruleA)
out['ruleA_hour_conc'] = dict(n_hours=len(hrs), max_per_hour=max(hrs.values()),
                              top5=sorted(hrs.values(), reverse=True)[:5])
# EV concentration by hour
hev = collections.defaultdict(float)
for t in ruleA: hev[t['t0']//3600] += t['ev_ps']
sev = sorted(hev.values(), reverse=True)
out['ruleA_ev_by_hour_top5_c'] = [round(100*x, 1) for x in sev[:5]]
out['ruleA_ev_total_c_per_trade'] = round(100*sum(hev.values())/len(ruleA), 2)

# ---------- 3. neighbor cells, dedup filter-first (same construction as the winner)
for lo_, hi_, lab in ((0.50, 0.55, '50-55'), (0.55, 0.60, '55-60'), (0.65, 0.75, '65-75')):
    ct = [t for t in mom if t['sdrift'] >= 4 and lo_ <= t['p'] < hi_]
    du = {}
    for t in ct: du.setdefault((t['t0'], t['side']), []).append(t)
    out[f'neighbor_{lab}'] = stat([v[0] for v in du.values()], f'drift>=4, p in [{lo_},{hi_}) dedup')

# ---------- 4. reconcile: pooled momentum 60-66c (all fills, trades not dedup)
p6066 = [t for t in mom if 0.60 <= t['p'] < 0.66]
out['reconcile_mom_6066_all'] = stat(p6066, 'mom all fills 60-66c (merge agent cited -1.29c n=1227)')
c6066 = [t for t in p6066 if t['sdrift'] < 4]
out['reconcile_mom_6066_complement'] = stat(c6066, 'mom 60-66c fills with drift<4bps')

# ---------- 5. candle-drift replacement (strictly pre-decision, independent feed)
cb = json.load(open(os.path.join(D12, 'cb1m.json')))
T, O, C = cb['t'], cb['o'], cb['c']
idx = {t: i for i, t in enumerate(T)}
def cndl_drift(t):
    """drift in bps from cb1m opens: open(minute containing fill) vs open(t0).
    open of the fill minute is known at/before the fill moment -> no lookahead."""
    t0 = t['t0']; at_s = t['at']//1000
    m = (at_s//60)*60
    if t0 not in idx or m not in idx or m < t0: return None
    o0 = O[idx[t0]]; om = O[idx[m]]
    d = (om-o0)/o0*1e4
    return d if t['side'] == 'up' else -d
n_ok = n_none = 0
for t in mom:
    t['cdrift'] = cndl_drift(t)
    if t['cdrift'] is None: n_none += 1
    else: n_ok += 1
out['cndl_coverage'] = dict(ok=n_ok, missing=n_none)
# corr between sdrift and cdrift
xs = [(t['sdrift'], t['cdrift']) for t in mom if t['cdrift'] is not None]
mx = sum(a for a, _ in xs)/len(xs); my = sum(b for _, b in xs)/len(xs)
sxx = sum((a-mx)**2 for a, _ in xs); syy = sum((b-my)**2 for _, b in xs)
sxy = sum((a-mx)*(b-my) for a, b in xs)
out['corr_sdrift_cdrift'] = round(sxy/math.sqrt(sxx*syy), 3)

cell_c = [t for t in mom if t['cdrift'] is not None and t['cdrift'] >= 4 and t['p'] >= 0.60]
dc = {}
for t in cell_c: dc.setdefault((t['t0'], t['side']), []).append(t)
cell_cu = [v[0] for v in dc.values()]
out['cell_candledrift_ge60'] = stat(cell_cu, 'cdrift>=4 (cb1m opens, pre-decision), p>=0.60, dedup')
out['cell_candledrift_boot'] = bboot(cell_cu, lambda t: t['ev_ps'])
# overlap
k1 = {(t['t0'], t['side']) for t in ruleA}
k2 = {(t['t0'], t['side']) for t in cell_cu}
out['cell_overlap'] = dict(ledger_only=len(k1-k2), candle_only=len(k2-k1), both=len(k1 & k2))
# the divergent set: qualified on btcEntry drift but NOT on candle drift
div = [t for t in ruleA if (t['t0'], t['side']) not in k2]
out['cell_ledgeronly'] = stat(div, 'in ruleA cell but candle drift <4bps or missing')
both = [t for t in ruleA if (t['t0'], t['side']) in k2]
out['cell_both'] = stat(both, 'in cell under BOTH drift definitions')

# ---------- 6. btcEntry vs candle-path sanity at fill time
diffs = []
for t in mom:
    at_s = t['at']//1000; m = (at_s//60)*60
    if m in idx and t['btcEntry']:
        # candle close of the fill minute = price ~end of that minute (future-ish);
        # candle open = start. btcEntry should sit between-ish if feed is fresh.
        o_, c_ = O[idx[m]], C[idx[m]]
        diffs.append((t['btcEntry']-o_)/o_*1e4)
diffs.sort()
n = len(diffs)
out['btcEntry_minus_minuteopen_bps'] = dict(n=n, p10=round(diffs[int(.1*n)], 2),
                                            p50=round(diffs[n//2], 2), p90=round(diffs[int(.9*n)], 2))

# ---------- 7. pre-registrable split: select cell on half, test on other half
def day(t): return datetime.datetime.fromtimestamp(t['t0'], datetime.timezone.utc).strftime('%m-%d')
BANDS = [(0.35, 0.40), (0.40, 0.45), (0.45, 0.50), (0.50, 0.55), (0.55, 0.60),
         (0.60, 0.65), (0.65, 0.70), (0.70, 0.75), (0.60, 1.01)]
THR = [2, 4, 8]
def cells_of(ts):
    res = {}
    for lo_, hi_ in BANDS:
        for th in THR:
            sub = [t for t in ts if t['sdrift'] >= th and lo_ <= t['p'] < hi_]
            du = {}
            for t in sub: du.setdefault((t['t0'], t['side']), []).append(t)
            u = [v[0] for v in du.values()]
            if len(u) >= 12:
                res[(lo_, hi_, th)] = (len(u), 100*sum(t['ev_ps'] for t in u)/len(u))
    return res
splits = [({'07-07', '07-08'}, {'07-09', '07-10'}), ({'07-09', '07-10'}, {'07-07', '07-08'}),
          ({'07-07', '07-09'}, {'07-08', '07-10'}), ({'07-08', '07-10'}, {'07-07', '07-09'})]
sp_out = []
for tr_days, te_days in splits:
    trn = [t for t in mom if day(t) in tr_days]
    tst = [t for t in mom if day(t) in te_days]
    ctrain = cells_of(trn)
    if not ctrain: continue
    best = max(ctrain, key=lambda k: ctrain[k][1])
    lo_, hi_, th = best
    sub = [t for t in tst if t['sdrift'] >= th and lo_ <= t['p'] < hi_]
    du = {}
    for t in sub: du.setdefault((t['t0'], t['side']), []).append(t)
    u = [v[0] for v in du.values()]
    ev_te = 100*sum(t['ev_ps'] for t in u)/len(u) if u else None
    sp_out.append(dict(train=sorted(tr_days), best_cell=f"p[{lo_},{hi_}) drift>={th}",
                       train_n=ctrain[best][0], train_ev_c=round(ctrain[best][1], 2),
                       test_n=len(u), test_ev_c=(round(ev_te, 2) if ev_te is not None else None)))
out['split_selection_test'] = sp_out
# also: fixed claimed cell (drift>=4, p>=0.60) evaluated per day
per_day = collections.defaultdict(list)
for t in ruleA: per_day[day(t)].append(t)
out['claimed_cell_by_day'] = {d: dict(n=len(v), wins=sum(int(t['w']) for t in v),
                                      ev_c=round(100*sum(t['ev_ps'] for t in v)/len(v), 2))
                              for d, v in sorted(per_day.items())}

# ---------- 8. honest multiplicity: permutation of drift labels within price band
# Null: given price band, drift carries no info. Permute sdrift across trades of the
# same band within the momentum dedup set; recompute the max cell EV over the scan.
rng = random.Random(99)
def scan_max(ts):
    cells = cells_of(ts)
    return max((v[1] for v in cells.values()), default=-99)
obs_max = scan_max(mom)
# permute: shuffle sdrift among dedup momentum trades within 5c price band,
# in hourly blocks to respect drift autocorrelation (block-shuffle: permute hours,
# then reassign whole hourly drift vectors within band-strata is impractical;
# use trade-level permutation stratified by band = anti-conservative null, and
# also hour-level rotation as a second, conservative variant).
def perm_trades(B=400):
    cnt = 0
    band_of = lambda t: int(t['p']*100)//5
    strata = collections.defaultdict(list)
    for t in mom: strata[band_of(t)].append(t)
    for _ in range(B):
        for band, ts in strata.items():
            ds = [t['sdrift'] for t in ts]
            rng.shuffle(ds)
            for t, d_ in zip(ts, ds): t['_pd'] = d_
        # rebuild with permuted drift
        pmax = -99
        for lo_, hi_ in BANDS:
            for th in THR:
                sub = [t for t in mom if t['_pd'] >= th and lo_ <= t['p'] < hi_]
                du = {}
                for t in sub: du.setdefault((t['t0'], t['side']), []).append(t)
                u = [v[0] for v in du.values()]
                if len(u) >= 12:
                    ev = 100*sum(t['ev_ps'] for t in u)/len(u)
                    pmax = max(pmax, ev)
        if pmax >= obs_max: cnt += 1
    return cnt, B
cnt, B = perm_trades()
out['perm_scanmax'] = dict(observed_max_ev_c=round(obs_max, 2), perm_ge_obs=cnt, B=B,
                           p_perm=round((cnt+1)/(B+1), 4),
                           note='trade-level shuffle of drift within 5c price band; ignores time clustering (anti-conservative)')

json.dump(out, open(os.path.join(HERE, 'results.json'), 'w'), indent=1)
print(json.dumps(out, indent=1))
