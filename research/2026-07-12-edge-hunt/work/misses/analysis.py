#!/usr/bin/env python3
"""Misses & counterfactuals — 2026-07-12 edge hunt.

What the bot did NOT trade, v3 era (2026-07-10 15:05 UTC -> 2026-07-13 03:40 UTC):
 1. near-miss dataset from state misses list + resolution via cb1m
 2. Kelly-skip counterfactuals from the measurement book (corrected for later-fill rescues)
 3. bench cost audit
 4. full trigger->gate->cap/fill funnel from cb1m with win rates per stage
 5. cap-band EV from actual fills (reversal 55c book) + cap-rejected misses

Frozen cost model: EV/share = q - p - 0.07*p*(1-p); gas $0.004/trade; fill = ask + 1c.
All win resolution: open(t0) vs open(t0+300) from Coinbase 1m candles (97.2% agreement
with ledger outcomes on 3,495 settled trades; ties counted separately).
Stdlib only.
"""
import json, math, random, datetime

DATA = '/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data'
OUT  = '/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work/misses/results.json'
FEE  = 0.07
ERA0, ERA1 = 1783695900, 1783914000   # Jul 10 15:05 -> Jul 13 03:40 UTC (heartbeat)

random.seed(20260712)

def ut(t): return datetime.datetime.utcfromtimestamp(t).strftime('%m-%d %H:%M')
def fee(p): return FEE*p*(1-p)
def cost(p): return p + fee(p)

# ---------- data ----------
cb = json.load(open(f'{DATA}/cb1m.json'))
OP = dict(zip(cb['t'], cb['o']))
st = json.load(open(f'{DATA}/state_extract.json'))
TR = json.load(open(f'{DATA}/trades_unified.json'))

def ret5(t):
    a, b = OP.get(t), OP.get(t+300)
    return None if (a is None or b is None) else (b-a)/a

def res(t0):
    """winning side of interval t0 per Coinbase proxy."""
    r = ret5(t0)
    if r is None: return None
    return 'up' if r > 0 else ('down' if r < 0 else 'tie')

def wilson_or_binom_p(w, n, p0):
    """two-sided exact-ish binomial p-value of w wins in n vs p0 (normal approx for n>30)."""
    if n == 0: return None
    mean, sd = n*p0, math.sqrt(n*p0*(1-p0))
    if sd == 0: return None
    z = (w - mean)/sd
    # two-sided normal
    return 2*(1 - 0.5*(1+math.erf(abs(z)/math.sqrt(2))))

def block_boot_mean(rows, B=4000):
    """rows: list of (t0, value). 1h-block bootstrap CI of the mean."""
    if not rows: return None
    blocks = {}
    for t0, v in rows: blocks.setdefault(t0//3600, []).append(v)
    keys = list(blocks.values()); n = len(keys)
    means = []
    for _ in range(B):
        s = []
        for _ in range(n): s.extend(random.choice(keys))
        means.append(sum(s)/len(s))
    means.sort()
    mu = sum(v for _, v in rows)/len(rows)
    lo, hi = means[int(0.025*B)], means[int(0.975*B)-1]
    # p-value vs 0 (two-sided, bootstrap percentile)
    frac = sum(1 for m in means if m <= 0)/B
    p = 2*min(frac, 1-frac)
    return dict(mean=round(mu,4), lo=round(lo,4), hi=round(hi,4), p_vs0=round(p,4), nblocks=n)

results = {'meta': dict(era=[ERA0, ERA1], resolution='cb1m open(t0) vs open(t0+300), 97.2% ledger agreement',
                        cost_model='EV/share = q - p - 0.07*p*(1-p), fill=ask+1c, gas $0.004/trade')}

# ---------- ledgers ----------
v3 = [t for t in TR if t['t0'] >= ERA0]
by_eng = {}
for t in v3: by_eng.setdefault(t['eng'], {})[t['t0']] = t
iv2 = by_eng.get('impulse_v2', {}); i50 = by_eng.get('impulse50', {}); rv2 = by_eng.get('reversal_v2', {})
rev = by_eng.get('reversal', {}); rev2 = by_eng.get('reversal2', {})
meas = {m['t0']: m for m in st['measure']}

def ev_share(t):
    """realized net EV/share of a settled ledger trade under frozen model."""
    if t.get('result') not in ('win','loss'): return None
    p = t['entry']
    return (1 - p - fee(p)) if t['result']=='win' else (-p - fee(p))

# =========================================================================
# 1) KELLY SKIPS — corrected for later-fill rescue
# =========================================================================
skips = [m for m in st['measure'] if not m['sized']]
sized = [m for m in st['measure'] if m['sized']]
pure_skips, rescued = [], []
for m in skips:
    (rescued if m['t0'] in iv2 else pure_skips).append(m)

def book_stats(rows, label):
    settled = [m for m in rows if m['win'] is not None]
    n = len(settled); w = sum(m['win'] for m in settled)
    mc = sum(m['cost'] for m in settled)/n if n else None
    evs = [(m['t0'], m['win'] - m['cost']) for m in settled]   # cost already includes fee
    bb = block_boot_mean(evs) if n >= 5 else None
    return dict(label=label, n=n, wins=w, wr=round(w/n,4) if n else None,
                mean_cost=round(mc,4) if n else None,
                ev_share_c=round(100*(w/n - mc),2) if n else None,
                block_boot=bb)

k_first = book_stats(skips, 'first-poll f_nonpos (ask>=48c at first fillable poll)')
k_pure  = book_stats(pure_skips, 'pure skips (never traded)')
k_resc_meas = book_stats(rescued, 'rescued (skipped first poll, filled later cheaper) AT FIRST-POLL cost')
resc_pairs = []
for m in rescued:
    t = iv2[m['t0']]
    if t.get('result') in ('win','loss'):
        resc_pairs.append(dict(t0=m['t0'], first_cost=m['cost'], fill_cost=round(cost(t['entry']),4),
                               improve_c=round(100*(m['cost']-cost(t['entry'])),2), win=1 if t['result']=='win' else 0))
k_sized = book_stats(sized, 'sized at first poll (ask<=47c)')
results['kelly_skips'] = dict(
    first_poll_highband=k_first, pure_skips=k_pure, rescued_at_firstcost=k_resc_meas,
    sized_first_poll=k_sized, rescue_pairs=resc_pairs,
    note='f_nonpos fires iff effective cost >= qhat(~0.503-0.507) i.e. ask>=48c; the sizer is a de-facto 47c ask cap at first poll')

# impulse50 book split by entry band (it takes EVERYTHING fillable at flat $50)
def band(t):
    p = t['entry']
    return '<40c' if p < .40 else ('40-44c' if p < .45 else ('45-47c' if p < .48 else ('48-53c' if p <= .54 else '>54c')))
i50_bands = {}
for t in i50.values():
    e = ev_share(t)
    if e is None: continue
    i50_bands.setdefault(band(t), []).append((t['t0'], e))
results['impulse50_by_band'] = {b: dict(n=len(v), wr=round(sum(1 for _,x in v if x>0)/len(v),3),
                                        ev_share_c=round(100*sum(x for _,x in v)/len(v),2))
                                for b, v in sorted(i50_bands.items())}

# =========================================================================
# 2) BENCH AUDIT
# =========================================================================
lm = [json.loads(l) for l in open('/Users/sgonzalez/btc5m-paper-trader/bot/loop_metrics.jsonl')]
bench_windows = [(r['t'], r['benched']) for r in lm]
benched_skips_in_book = [m for m in st['measure'] if m.get('skip') == 'benched']
results['bench_audit'] = dict(
    current_benched=st['impulse_cfg']['benched'],
    loop_metrics=[dict(t=r['t'], iso=ut(r['t']), benched=r['benched'], measured=r['measured'], n15=r.get('n15'), qlo=r['qlo']) for r in lm],
    benched_skips_recorded=len(benched_skips_in_book),
    note=('impulse_cfg.benched is FALSE at heartbeat (Jul 13 03:40). Bench flag was true only on Jul 10 '
          '15:03-17:30 nightly runs computed from the STALE pre-launch seeded 300-row book (n15=-0.1975); '
          'the fresh book (reset Jul 10 15:05) never triggered it and no skip="benched" exists in the '
          'measurement book. Bench has blocked zero gated cap-compliant signals: cost/saving = $0.'))

# =========================================================================
# 3) NEAR-MISSES from state misses list, resolved via cb1m
# =========================================================================
misses = st['misses_btc']
def categorize(note):
    cats = []
    if 'Isolated' in note: cats.append('gate')
    if 'Rev≤53c' in note or 'Rev≤53c' in note: cats.append('cap53')
    if 'Rev≤55c' in note or 'Rev≤55c' in note: cats.append('cap55')
    if 'thin book' in note: cats.append('thin')
    if 'wide spread' in note: cats.append('spread')
    if 'stale quote' in note: cats.append('stale')
    if not cats: cats.append('window_only')
    return cats

# unique per (t0, engine-family): impulse family (impulse_v2/impulse50) vs reversal_v2 vs reversal/2
miss_rows = []
for m in misses:
    w = res(m['t0'])
    if w is None: continue
    miss_rows.append(dict(t0=m['t0'], eng=m['eng'], side=m['side'], cats=categorize(m['note']),
                          note=m['note'], win=None if w=='tie' else (1 if w==m['side'] else 0)))
cat_stats = {}
for cat in ('gate','cap53','cap55','thin','spread','stale','window_only'):
    seen = set(); rows = []
    for m in miss_rows:
        if cat in m['cats'] and m['win'] is not None and m['t0'] not in seen:
            seen.add(m['t0']); rows.append(m)
    n = len(rows); w = sum(m['win'] for m in rows)
    cat_stats[cat] = dict(n_unique_t0=n, wins=w, wr=round(w/n,3) if n else None,
                          p_vs_50=round(wilson_or_binom_p(w,n,0.5),3) if n else None,
                          t0s=[m['t0'] for m in rows])
results['near_miss_by_reason'] = cat_stats

# cap53-missed: EV if cap were 55c (fill ~54.5c mid-band) using realized q
c53 = cat_stats['cap53']
if c53['n_unique_t0']:
    q = c53['wins']/c53['n_unique_t0']
    for pfill in (0.54, 0.55):
        c53[f'ev_at_{int(pfill*100)}c_fill_c'] = round(100*(q - pfill - fee(pfill)),2)
results['near_miss_by_reason']['cap53'] = c53

# =========================================================================
# 4) FUNNEL from cb1m, v3 era
# =========================================================================
def gate(t0):
    rets = [ret5(t0 - 300*k) for k in range(1,14)]
    if any(r is None for r in rets): return None, None, None
    last6 = [rets[k-1] for k in range(6,0,-1)]  # rets[5]..rets[0] oldest->newest? careful
    # rets[k-1] = interval starting t0-300k. last6 per bot: k=6..1 (oldest->trigger)
    den = sum(abs(r) for r in last6); net = 1.0
    for r in last6: net *= (1.0+r)
    eff6 = (abs(net-1.0)/den) if den>0 else 1.0
    cnt12 = sum(1 for k in range(2,14) if abs(rets[k-1]) >= 0.0012)
    return (eff6 >= 0.10 and cnt12 <= 6), round(eff6,4), cnt12

funnel = dict(intervals=0, no_candle=0, trigger=0, gate_pass=0)
stage_outcomes = {'trigger':[], 'gate_pass':[], 'gate_fail':[]}
fate_counts = {}
fate_outcomes = {}
gate_pass_rows = []
for t0 in range(ERA0, ERA1+300, 300):
    rprev = ret5(t0-300)
    w = res(t0)
    if rprev is None or w is None:
        funnel['no_candle'] += 1; continue
    funnel['intervals'] += 1
    if abs(rprev) < 0.0012: continue
    funnel['trigger'] += 1
    side = 'down' if rprev > 0 else 'up'   # contrarian
    win = None if w=='tie' else (1 if w==side else 0)
    stage_outcomes['trigger'].append((t0,win))
    ok, e6, c12 = gate(t0)
    if ok is None: fate='gate_unknown'
    elif ok:
        funnel['gate_pass'] += 1
        stage_outcomes['gate_pass'].append((t0,win))
        # fate join
        if t0 in iv2: fate='traded_impulse_v2'
        elif t0 in i50: fate='traded_impulse50_only'
        elif t0 in meas: fate='measured_skip_no_trade'
        else:
            mm=[m for m in miss_rows if m['t0']==t0 and m['eng'] in ('impulse_v2','impulse50')]
            if mm:
                cs = sorted(set(c for m in mm for c in m['cats']))
                fate='missed:'+'+'.join(cs)
            elif t0 in rv2 or t0 in rev or t0 in rev2 or any(m['t0']==t0 for m in miss_rows):
                fate='bot_alive_no_impulse_record'
            else: fate='no_bot_evidence'
        gate_pass_rows.append(dict(t0=t0, iso=ut(t0), side=side, win=win, eff6=e6, cnt12=c12, fate=fate))
    else:
        stage_outcomes['gate_fail'].append((t0,win))
        fate='gate_blocked'
    fate_counts[fate]=fate_counts.get(fate,0)+1
    if win is not None: fate_outcomes.setdefault(fate,[]).append((t0,win))

def wr_stats(rows, p0=0.5):
    xs=[w for _,w in rows if w is not None]; n=len(xs); w=sum(xs)
    return dict(n=n, wins=w, wr=round(w/n,4) if n else None,
                p_vs_50=round(wilson_or_binom_p(w,n,p0),4) if n else None)
results['funnel'] = dict(
    counts=funnel,
    contrarian_wr=dict(all_triggers=wr_stats(stage_outcomes['trigger']),
                       gate_pass=wr_stats(stage_outcomes['gate_pass']),
                       gate_fail=wr_stats(stage_outcomes['gate_fail'])),
    fate_counts=fate_counts,
    fate_wr={k: wr_stats(v) for k,v in fate_outcomes.items()},
    gate_pass_detail=gate_pass_rows)

# =========================================================================
# 5) FILL-SELECTION: gate-pass triggers filled vs not filled
# =========================================================================
filled_t0 = set(meas) | set(iv2) | set(i50)
fill_rows, nofill_rows = [], []
for r in gate_pass_rows:
    (fill_rows if r['t0'] in filled_t0 else nofill_rows).append((r['t0'], r['win']))
results['fill_selection'] = dict(
    filled=wr_stats(fill_rows), not_filled=wr_stats(nofill_rows),
    note='filled = cap-compliant fillable within first 45s (measure book or trade); not_filled = gate passed per candles but no fill/measure record')

# =========================================================================
# 6) GATE INCREMENT on live fills: reversal_v2 (ungated) split by candle gate
# =========================================================================
gp, gf = [], []
for t0, t in rv2.items():
    e = ev_share(t)
    if e is None: continue
    ok,_,_ = gate(t0)
    if ok is None: continue
    (gp if ok else gf).append((t0, e))
def ev_stats(rows):
    n=len(rows)
    if not n: return dict(n=0)
    mu=sum(v for _,v in rows)/n
    return dict(n=n, ev_share_c=round(100*mu,2), wr=round(sum(1 for _,v in rows if v>0)/n,3),
                block_boot=block_boot_mean(rows) if n>=5 else None)
results['gate_increment_live'] = dict(
    reversal_v2_gatepass=ev_stats(gp), reversal_v2_gateblocked=ev_stats(gf),
    note='reversal_v2 = ungated 53c control; split by candle-recomputed impulse gate')

# =========================================================================
# 7) CAP: actual 53-56c fills (reversal 55c book, v3 era) + all-fills band EV
# =========================================================================
pool = []
for eng in ('reversal','reversal2','reversal_v2','impulse50','impulse_v2'):
    for t0, t in by_eng.get(eng, {}).items():
        e = ev_share(t)
        if e is None: continue
        pool.append(dict(t0=t0, eng=eng, entry=t['entry'], ev=e))
over53 = [(p['t0'],p['ev']) for p in pool if p['entry'] > 0.54]
b48_54 = [(p['t0'],p['ev']) for p in pool if 0.48 <= p['entry'] <= 0.54]
under48 = [(p['t0'],p['ev']) for p in pool if p['entry'] < 0.48]
results['cap_bands_all_v3_fills'] = dict(
    entry_under_48c=ev_stats(sorted(set(under48))),
    entry_48_54c=ev_stats(sorted(set(b48_54))),
    entry_over_54c=ev_stats(sorted(set(over53))),
    note='pooled v3-era reversal-family fills (may double count same t0 across engines; dedup by (t0,ev) tuple)')

# dedup by t0 (one obs per interval, prefer cheapest fill? no - average)
from collections import defaultdict
per_t0 = defaultdict(list)
for p in pool: per_t0[p['t0']].append(p)
bands_dedup = {'<48c':[], '48-54c':[], '>54c':[]}
for t0, ps in per_t0.items():
    for p in ps:
        b = '<48c' if p['entry']<0.48 else ('48-54c' if p['entry']<=0.54 else '>54c')
        bands_dedup[b].append((t0,p['ev'])); break  # first record per t0 only? no...
# simpler honest version: per (t0,band) mean
bands2 = {'<48c':defaultdict(list), '48-54c':defaultdict(list), '>54c':defaultdict(list)}
for p in pool:
    b = '<48c' if p['entry']<0.48 else ('48-54c' if p['entry']<=0.54 else '>54c')
    bands2[b][p['t0']].append(p['ev'])
results['cap_bands_per_t0'] = {b: ev_stats(sorted((t0, sum(v)/len(v)) for t0,v in d.items()))
                               for b,d in bands2.items()}

# =========================================================================
# 8) signals.log emit-vs-fill audit (v3 era)
# =========================================================================
sig = []
for line in open('/Users/sgonzalez/btc5m-paper-trader/bot/signals.log'):
    try: s = json.loads(line)
    except Exception: continue
    if s.get('t0',0) >= ERA0: sig.append(s)
sig_iv2 = [s for s in sig if s['engine']=='impulse_v2']
unfilled = [s for s in sig_iv2 if s['t0'] not in iv2]
results['signals_audit'] = dict(
    v3_signals_by_engine={e: sum(1 for s in sig if s['engine']==e) for e in set(s['engine'] for s in sig)},
    impulse_v2_emitted=len(sig_iv2), impulse_v2_traded=len(iv2),
    emitted_not_filled=[dict(t0=s['t0'], ask=s['ask']) for s in unfilled])

json.dump(results, open(OUT,'w'), indent=1)
print(json.dumps({k:v for k,v in results.items() if k not in ('funnel',)}, indent=1)[:1])  # noop
# ---------- console report ----------
def pr(*a): print(*a)
pr('=== KELLY SKIPS ===')
for k in ('first_poll_highband','pure_skips','rescued_at_firstcost','sized_first_poll'):
    pr(k, json.dumps(results['kelly_skips'][k]))
pr('rescues:', json.dumps(resc_pairs))
pr()
pr('=== impulse50 by band ===', json.dumps(results['impulse50_by_band'], indent=0))
pr()
pr('=== NEAR MISS BY REASON ===')
for k,v in cat_stats.items(): pr(k, json.dumps({x:y for x,y in v.items() if x!='t0s'}))
pr()
pr('=== FUNNEL ===', json.dumps(results['funnel']['counts']))
pr('wr:', json.dumps(results['funnel']['contrarian_wr']))
pr('fates:', json.dumps(fate_counts, indent=0))
pr('fate wr:', json.dumps(results['funnel']['fate_wr']))
pr()
pr('=== FILL SELECTION ===', json.dumps(results['fill_selection']))
pr()
pr('=== GATE INCREMENT (live rv2 fills) ===', json.dumps(results['gate_increment_live']))
pr()
pr('=== CAP BANDS per t0 ===', json.dumps(results['cap_bands_per_t0']))
pr()
pr('=== SIGNALS AUDIT ===', json.dumps(results['signals_audit']))
pr()
pr('=== BENCH ===', results['bench_audit']['note'])
