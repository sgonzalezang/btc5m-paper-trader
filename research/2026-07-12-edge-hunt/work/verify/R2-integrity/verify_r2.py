#!/usr/bin/env python3
"""Adversarial verification of FINDING R2 (50-53c fill zone fee-dead).
Re-derives every headline number from RAW data (trades_unified.json, cb1m.json,
state_extract.json). Integrity checks: dupes, survivorship, ties, epoch units,
outcome-vs-candle agreement, dedup-by-interval, rolling-buffer bias in the
misses replication. Stdlib only.
"""
import json, random, math
from collections import defaultdict

D = '/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data'
OUT = {}

def fee(p): return 0.07*p*(1-p)
def qstar(p): return p + fee(p)
def wilson(k, n, z=1.96):
    if n == 0: return (0.0, 1.0)
    ph = k/n; d = 1+z*z/n
    c = ph + z*z/(2*n); h = z*math.sqrt(ph*(1-ph)/n + z*z/(4*n*n))
    return ((c-h)/d, (c+h)/d)

tr = json.load(open(f'{D}/trades_unified.json'))
cb1 = json.load(open(f'{D}/cb1m.json'))
st = json.load(open(f'{D}/state_extract.json'))

# ---------- A. ledger integrity ----------
OUT['A_counts'] = dict(total=len(tr),
    settled=sum(1 for t in tr if t.get('status')=='settled' and t.get('result') in ('win','loss')),
    by_status=dict())
sc = defaultdict(int)
for t in tr: sc[t.get('status','?')] += 1
OUT['A_counts']['by_status'] = dict(sc)

# duplicates: same (t0, eng, side) more than once?
seen = defaultdict(list)
for i, t in enumerate(tr): seen[(t['t0'], t['eng'], t['side'])].append(i)
dups = {str(k): v for k, v in seen.items() if len(v) > 1}
OUT['A_dupes_t0_eng_side'] = dict(n_dup_keys=len(dups), example=list(dups.items())[:3])

# epoch sanity: at(ms)/1000 - t0(s) should equal ~entrySec, within window 0..300
bad_epoch = 0; es_mismatch = 0
for t in tr:
    if 'at' in t and t.get('t0'):
        dt = t['at']/1000 - t['t0']
        if not (-5 <= dt <= 320): bad_epoch += 1
        if 'entrySec' in t and t['entrySec'] is not None and abs(dt - t['entrySec']) > 10:
            es_mismatch += 1
OUT['A_epoch'] = dict(bad_epoch=bad_epoch, entrySec_mismatch_gt10s=es_mismatch)

# entry = ask + slip check
bad_entry = sum(1 for t in tr if t.get('ask') is not None and abs(t['entry']-(t['ask']+t.get('slip',0.01))) > 1e-6)
OUT['A_entry_eq_ask_plus_slip_violations'] = bad_entry

# unsettled survivorship: where do the non-settled live in price space?
uns = [t for t in tr if not (t.get('status')=='settled' and t.get('result') in ('win','loss'))]
OUT['A_unsettled'] = dict(n=len(uns),
    in_50_53=sum(1 for t in uns if 0.50 <= t['entry'] < 0.53),
    by_status=dict((s, sum(1 for t in uns if t.get('status')==s)) for s in set(t.get('status') for t in uns)),
    entries=sorted(round(t['entry'],2) for t in uns)[:20])

# ---------- B. candle map + outcome cross-check ----------
c1 = {t: o for t, o in zip(cb1['t'], cb1['o'])}
def res_cb(t0):
    a, b = c1.get(t0), c1.get(t0+300)
    if a is None or b is None: return None
    if b > a: return 'up'
    if b < a: return 'down'
    return 'tie'

S = [t for t in tr if t.get('status')=='settled' and t.get('result') in ('win','loss')]
agree = disagree = nocand = ties = 0
dis_by_settler = defaultdict(int)
for t in S:
    r = res_cb(t['t0'])
    if r is None: nocand += 1; continue
    if r == 'tie': ties += 1; continue
    pred_win = (r == t['side'])
    if pred_win == (t['result']=='win'): agree += 1
    else:
        disagree += 1; dis_by_settler[t.get('settledBy','?')] += 1
OUT['B_outcome_vs_candle'] = dict(agree=agree, disagree=disagree, no_candle=nocand,
    candle_tie=ties, disagree_by_settledBy=dict(dis_by_settler),
    agree_rate=round(agree/(agree+disagree), 4))

# same check restricted to the 50-53 zone
z = [t for t in S if 0.50 <= t['entry'] < 0.53]
za = zd = zt = zn = 0
for t in z:
    r = res_cb(t['t0'])
    if r is None: zn += 1
    elif r == 'tie': zt += 1
    elif (r == t['side']) == (t['result']=='win'): za += 1
    else: zd += 1
OUT['B_zone_outcome_check'] = dict(n=len(z), agree=za, disagree=zd, tie=zt, no_candle=zn)

# ---------- C. re-derive headline stats ----------
for t in S:
    t['w'] = 1.0 if t['result']=='win' else 0.0
    t['ev'] = t['w'] - t['entry'] - fee(t['entry'])

def stat(ts):
    n = len(ts)
    if n == 0: return dict(n=0)
    q = sum(t['w'] for t in ts)/n
    pm = sum(t['entry'] for t in ts)/n
    ev = sum(t['ev'] for t in ts)/n
    lo, hi = wilson(int(sum(t['w'] for t in ts)), n)
    return dict(n=n, wins=int(sum(t['w'] for t in ts)), q=round(q,4), p_mean=round(pm,4),
                qstar_mean=round(sum(qstar(t['entry']) for t in ts)/n,4),
                ev_c=round(100*ev,2), wilson_q=[round(lo,4), round(hi,4)])

def bboot(ts, B=6000, seed=99):
    rnd = random.Random(seed)
    blocks = defaultdict(list)
    for t in ts: blocks[t['t0']//3600].append(t['ev'])
    keys = list(blocks.values()); nb = len(keys); means = []
    for _ in range(B):
        s = []
        for _ in range(nb): s.extend(rnd.choice(keys))
        means.append(sum(s)/len(s))
    means.sort()
    mu = sum(t['ev'] for t in ts)/len(ts)
    return dict(mean_c=round(100*mu,2), ci_c=[round(100*means[int(.025*B)],2), round(100*means[int(.975*B)-1],2)],
                p_ge0=round(sum(1 for m in means if m >= 0)/B, 4), blocks=nb)

zone = [t for t in S if 0.50 <= t['entry'] < 0.53]
OUT['C_pooled_50_53'] = stat(zone)
OUT['C_pooled_50_53_boot'] = bboot(zone)

# dedup by (t0, side): one vote per interval-side (engines pile onto same signal)
dd = {}
for t in zone: dd.setdefault((t['t0'], t['side']), t)
zdd = list(dd.values())
OUT['C_pooled_50_53_dedup'] = stat(zdd)
OUT['C_pooled_50_53_dedup_boot'] = bboot(zdd)

# dedup by t0 only (some intervals have both sides -> those cancel in q)
dd2 = defaultdict(list)
for t in zone: dd2[t['t0']].append(t)
both_sides = sum(1 for v in dd2.values() if len(set(x['side'] for x in v)) > 1)
OUT['C_zone_intervals_with_both_sides'] = both_sides

# trigger family
REV = {'reversal','reversal2','reversal_v2','latentfire','impulse_v2','impulse50'}
V3_CUT = None
# v3 era cut: impulse_v2 first trade
V3_CUT = min(t['t0'] for t in S if t['eng']=='impulse_v2')
OUT['C_v3_cut_iso'] = V3_CUT

rev_ge50 = [t for t in S if t['eng'] in REV and t['entry'] >= 0.50]
OUT['C_rev_ge50'] = stat(rev_ge50); OUT['C_rev_ge50_boot'] = bboot(rev_ge50)
OUT['C_rev_ge50_pre'] = stat([t for t in rev_ge50 if t['t0'] < V3_CUT])
OUT['C_rev_ge50_v3'] = stat([t for t in rev_ge50 if t['t0'] >= V3_CUT])
ddr = {}
for t in rev_ge50: ddr.setdefault((t['t0'], t['side']), t)
OUT['C_rev_ge50_dedup'] = stat(list(ddr.values()))
OUT['C_rev_ge50_dedup_boot'] = bboot(list(ddr.values()))
OUT['C_rev_lt50'] = stat([t for t in S if t['eng'] in REV and t['entry'] < 0.50])

# breakeven at mean fill for rev_ge50
pm = OUT['C_rev_ge50']['p_mean']
OUT['C_rev_ge50_breakeven'] = round(qstar(pm), 4)

# per-engine breakdown in zone (rules out single-engine artifact)
eng_rows = {}
for e in sorted(set(t['eng'] for t in zone)):
    eng_rows[e] = stat([t for t in zone if t['eng']==e])
OUT['C_zone_by_engine'] = eng_rows

# per-day breakdown (rules out one bad day)
day_rows = {}
for t in zone:
    day_rows.setdefault(t['t0']//86400, []).append(t)
OUT['C_zone_by_day'] = {str(k): stat(v) for k, v in sorted(day_rows.items())}

# ---------- D. ties / voids in zone ----------
tiny = [t for t in zone if t.get('btcClose') is not None and t.get('btcOpen') and
        abs(t['btcClose']-t['btcOpen'])/t['btcOpen'] < 1e-5]
OUT['D_zone_tiny_moves_lt1bp'] = dict(n=sum(1 for t in zone if t.get('btcClose') and t.get('btcOpen') and abs(t['btcClose']-t['btcOpen'])/t['btcOpen'] < 1e-4),
    exact_tie=len(tiny), wins_among_tiny=sum(1 for t in tiny if t['result']=='win'))

# sensitivity: drop all <1bp-move trades from zone; recompute
zbig = [t for t in zone if not (t.get('btcClose') and t.get('btcOpen') and abs(t['btcClose']-t['btcOpen'])/t['btcOpen'] < 1e-4)]
OUT['D_zone_excl_lt1bp'] = stat(zbig)

# ---------- E. misses replication re-derivation ----------
meas = {m['t0']: m for m in st['measure']}
by_eng = defaultdict(dict)
for t in tr:
    if t['t0'] >= V3_CUT: by_eng[t['eng']][t['t0']] = t
iv2, i50 = by_eng.get('impulse_v2', {}), by_eng.get('impulse50', {})
cheap_t0 = set(meas) | set(iv2) | set(i50)
cheap = []
for t0 in sorted(cheap_t0):
    side = (meas.get(t0) or {}).get('side') or (iv2.get(t0) or i50.get(t0))['side']
    w = res_cb(t0)
    if w in ('up','down'): cheap.append((t0, side, 1 if w==side else 0))
exp_t0 = {}
for m in st['misses_btc']:
    if ('Rev≤53c' in m['note'] or 'Rev≤55c' in m['note']) and m['t0'] not in cheap_t0:
        exp_t0.setdefault(m['t0'], m)
expensive = []
for t0, m in sorted(exp_t0.items()):
    w = res_cb(t0)
    if w in ('up','down'): expensive.append((t0, m['side'], 1 if w==m['side'] else 0))

def C_(n, k):
    return math.comb(n, k)
def fisher_onesided(w1, n1, w2, n2):
    N, K, n = n1+n2, w1+w2, n2
    p = 0.0
    for x in range(w2, min(K, n)+1):
        if n-x > N-K or K-x > n1: continue
        p += C_(K, x)*C_(N-K, n-x)/C_(N, n)
    return p

w1, n1 = sum(w for _,_,w in cheap), len(cheap)
w2, n2 = sum(w for _,_,w in expensive), len(expensive)
OUT['E_replication'] = dict(cheap=dict(n=n1, wins=w1, wr=round(w1/n1,3) if n1 else None),
    expensive=dict(n=n2, wins=w2, wr=round(w2/n2,3) if n2 else None),
    fisher_onesided_p=round(fisher_onesided(w1, n1, w2, n2), 5))

# rolling-buffer time-coverage confound: t0 span of each group
def span(rows): return (min(r[0] for r in rows), max(r[0] for r in rows)) if rows else None
OUT['E_time_spans'] = dict(cheap=span(cheap), expensive=span(expensive),
    cheap_iso=[span(cheap)[0], span(cheap)[1]], exp_iso=[span(expensive)[0], span(expensive)[1]])

# restrict cheap to the expensive buffer window and re-test
lo_t, hi_t = span(expensive)
cheap_w = [r for r in cheap if lo_t <= r[0] <= hi_t]
w1w, n1w = sum(w for _,_,w in cheap_w), len(cheap_w)
OUT['E_replication_windowed'] = dict(cheap=dict(n=n1w, wins=w1w, wr=round(w1w/n1w,3) if n1w else None),
    expensive=dict(n=n2, wins=w2),
    fisher_onesided_p=round(fisher_onesided(w1w, n1w, w2, n2), 5) if n1w else None)

# multi-guard contamination: how many 'expensive' misses failed guards beyond the cap?
multi = clean = 0
for t0, m in exp_t0.items():
    note = m['note']
    part = note.split('short:')[-1]
    fails = [x.strip() for x in part.split(',')]
    other = [f for f in fails if 'Rev≤' not in f]
    if other: multi += 1
    else: clean += 1
OUT['E_expensive_guard_purity'] = dict(cap_only=clean, cap_plus_other_guards=multi,
    notes=[exp_t0[k]['note'] for k in sorted(exp_t0)][:12])

# cap-only subset re-test
exp_clean = []
for t0, m in sorted(exp_t0.items()):
    part = m['note'].split('short:')[-1]
    fails = [x.strip() for x in part.split(',')]
    if all('Rev≤' in f for f in fails):
        w = res_cb(t0)
        if w in ('up','down'): exp_clean.append((t0, 1 if w==m['side'] else 0))
w2c, n2c = sum(w for _,w in exp_clean), len(exp_clean)
OUT['E_replication_cap_only'] = dict(n=n2c, wins=w2c,
    fisher_onesided_p=round(fisher_onesided(w1, n1, w2c, n2c), 5) if n2c else None)

json.dump(OUT, open('/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work/verify/R2-integrity/rederive.json','w'), indent=1)
print(json.dumps(OUT, indent=1))
