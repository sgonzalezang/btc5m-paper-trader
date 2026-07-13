#!/usr/bin/env python3
"""R7 adversarial verification: data-integrity & lookahead lens.

Re-derives from RAW data (trades_unified.json, state_extract.json, cb5m.json):
  A) feed-vs-candle convention check of eff6/cnt12 against the bot's OWN logged
     gate features (the merge agent's flagged concern),
  B) live gate increment within reversal_v2 (ungated control) fills,
  C) gate retention (live window + last 21d) with sensitivity analyses,
  D) survivorship / dedup / epoch checks,
  E) TEST-window candle increment sanity re-check (1h-block bootstrap).
Bot conventions replicated from btc5m_bot.py::_impulse_gate (lines 535-555):
  ret[t] = (close-open)/open of 5m candle at t (bot live tick uses feed open->last;
  cold-start warm uses Coinbase (c-o)/o -- identical convention);
  eff6 over k=1..6 trigger-INCLUDED, compounded; cnt12 over k=2..13 trigger-EXCLUDED,
  |ret|>=0.0012; missing/non-contiguous history -> gate not ready (False).
Trigger (ENGINE_CFG reversal_v2/impulse*): |prev ret|*100 >= 0.12.
"""
import json, random, datetime, math

D = '/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data'
W = '/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work/verify/R7-integrity'
IVL = 300
random.seed(7)

cb = json.load(open(D + '/cb5m.json'))
trades = json.load(open(D + '/trades_unified.json'))
st = json.load(open(D + '/state_extract.json'))

# --- candle maps -------------------------------------------------------------
O = {}; C = {}
for i, t in enumerate(cb['t']):
    O[t] = cb['o'][i]; C[t] = cb['c'][i]
ret_co = {t: (C[t] - O[t]) / O[t] for t in O if O[t]}          # bot convention (c-o)/o
ret_oo = {t: (O[t + IVL] - O[t]) / O[t] for t in O if (t + IVL) in O and O[t]}  # open-to-open

def gate(t0, ret):
    """(ok, eff6, cnt12) with bot conventions; None,None if history not ready."""
    need = {}
    for k in range(1, 14):
        t = t0 - IVL * k
        if t not in ret: return None, None, None
        need[t] = ret[t]
    last6 = [need[t0 - IVL * k] for k in range(6, 0, -1)]
    den = sum(abs(r) for r in last6)
    net = 1.0
    for r in last6: net *= (1.0 + r)
    eff6 = (abs(net - 1.0) / den) if den > 0 else 1.0
    cnt12 = sum(1 for k in range(2, 14) if abs(need[t0 - IVL * k]) >= 0.0012)
    return (eff6 >= 0.10 and cnt12 <= 6), round(eff6, 4), cnt12

def utc(s):  # 'YYYY-mm-dd HH:MM' -> epoch
    return int(datetime.datetime.strptime(s, '%Y-%m-%d %H:%M')
               .replace(tzinfo=datetime.timezone.utc).timestamp())

res = {'generated': datetime.datetime.now(datetime.timezone.utc).isoformat()}

# --- A) feed-vs-candle convention check on the bot's OWN logged gate features -
rows = []
flips = 0
for m in st['measure']:
    f = m.get('f')
    if not f or f.get('eff6') is None: continue
    ok, e6, c12 = gate(m['t0'], ret_co)
    bot_ok = (f['eff6'] >= 0.10 and f['cnt12'] <= 6)
    cand_ok = ok
    rows.append(dict(t0=m['t0'], bot_eff6=f['eff6'], cand_eff6=e6,
                     bot_cnt12=f['cnt12'], cand_cnt12=c12,
                     bot_pass=bot_ok, cand_pass=cand_ok,
                     d_eff6=(None if e6 is None else round(e6 - f['eff6'], 4)),
                     d_cnt12=(None if c12 is None else c12 - f['cnt12'])))
    if cand_ok is not None and bot_ok != cand_ok: flips += 1
d_eff = [abs(r['d_eff6']) for r in rows if r['d_eff6'] is not None]
d_cnt = [abs(r['d_cnt12']) for r in rows if r['d_cnt12'] is not None]
res['A_convention_check'] = dict(
    n=len(rows),
    n_candle_computable=len(d_eff),
    eff6_absdiff_mean=round(sum(d_eff) / max(1, len(d_eff)), 4),
    eff6_absdiff_max=round(max(d_eff), 4) if d_eff else None,
    cnt12_absdiff_mean=round(sum(d_cnt) / max(1, len(d_cnt)), 3),
    cnt12_absdiff_max=max(d_cnt) if d_cnt else None,
    cnt12_exact_match=sum(1 for r in rows if r['d_cnt12'] == 0),
    decision_flips=flips,
    note='bot rows are all gate-PASSES (measure book); flips = bot-pass but candle-reject')
res['A_rows'] = rows

# --- B) live gate increment within reversal_v2 fills --------------------------
w0, w1 = utc('2026-07-10 16:55'), utc('2026-07-13 03:10')
rv = [t for t in trades if t['eng'] == 'reversal_v2' and w0 <= t['t0'] <= w1]
rv_settled = [t for t in rv if t['status'] == 'settled' and t.get('result') in ('win', 'loss')]
# bot-book gate classification: t0 seen in measure book or in an impulse trade
measure_t0 = {m['t0'] for m in st['measure']}
imp_t0 = {t['t0'] for t in trades if t['eng'] in ('impulse50', 'impulse_v2')}
bot_pass_t0 = measure_t0 | imp_t0

def ps(t):  # settled pnl per share, in cents
    return 100.0 * t['pnl'] / t['shares']

split = {'bot_book': {}, 'candle': {}}
disagree = []
for t in rv_settled:
    ok_c, e6, c12 = gate(t['t0'], ret_co)
    t['_cand'] = ok_c; t['_bot'] = t['t0'] in bot_pass_t0
    if ok_c is not None and t['_bot'] != ok_c:
        disagree.append(dict(t0=t['t0'], bot=t['_bot'], cand=ok_c, eff6=e6, cnt12=c12))

def do_split(key):
    P = [ps(t) for t in rv_settled if t[key]]
    R = [ps(t) for t in rv_settled if not t[key]]
    inc = (sum(P) / len(P) - sum(R) / len(R)) if (P and R) else None
    # permutation test on the increment
    pval = None
    if P and R:
        allv = P + R; nP = len(P); obs = abs(inc); hits = 0; NPERM = 20000
        for _ in range(NPERM):
            random.shuffle(allv)
            d = sum(allv[:nP]) / nP - sum(allv[nP:]) / (len(allv) - nP)
            if abs(d) >= obs - 1e-12: hits += 1
        pval = hits / NPERM
    return dict(n_pass=len(P), n_rej=len(R),
                pass_ps_c=round(sum(P) / len(P), 2) if P else None,
                rej_ps_c=round(sum(R) / len(R), 2) if R else None,
                increment_c=round(inc, 2) if inc is not None else None,
                perm_p_two_sided=pval)

res['B_live_increment'] = dict(
    window=[w0, w1], rv_in_window=len(rv), rv_settled=len(rv_settled),
    rv_excluded_unsettled=[t['t0'] for t in rv if t not in rv_settled],
    bot_book_split=do_split('_bot'),
    candle_split=do_split('_cand'),
    classification_disagreements=disagree)

# --- C) retention ------------------------------------------------------------
def retention(tlo, thi, ret, thr=0.0012, strict=False):
    sig = 0; passed = 0; details = []
    for t0 in sorted(O):
        if not (tlo <= t0 <= thi): continue
        tp = t0 - IVL
        if tp not in ret: continue
        r = ret[tp]
        trig = (abs(r) > thr) if strict else (abs(r) >= thr)
        if not trig: continue
        ok, e6, c12 = gate(t0, ret)
        if ok is None: continue
        sig += 1; passed += ok
        details.append((t0, ok, e6, c12))
    return sig, passed, details

live_s, live_p, live_det = retention(w0, w1, ret_co)
d21lo = utc('2026-06-22 00:00')
d21_s, d21_p, _ = retention(d21lo, w1, ret_co)
# sensitivities
oo_live = retention(w0, w1, ret_oo)
oo_21 = retention(d21lo, w1, ret_oo)
strict_21 = retention(d21lo, w1, ret_co, strict=True)
thr_lo_21 = retention(d21lo, w1, ret_co, thr=0.0011)
thr_hi_21 = retention(d21lo, w1, ret_co, thr=0.0013)
# boundary mass: how many gate decisions sit within observed feed-vs-candle noise
eff_noise = max(d_eff) if d_eff else 0.0
near = [d for d in live_det if (abs(d[2] - 0.10) <= eff_noise) or d[3] in (6, 7)]
# bot-side retention within reversal_v2 fills (bot's own trigger, bot's own gate)
bp = sum(1 for t in rv_settled if t['_bot'])
res['C_retention'] = dict(
    band=[0.40, 0.70],
    live_window=dict(signals=live_s, passed=live_p, retention=round(live_p / max(1, live_s), 4)),
    last_21d=dict(signals=d21_s, passed=d21_p, retention=round(d21_p / max(1, d21_s), 4)),
    sens_open_to_open=dict(live=round(oo_live[1] / max(1, oo_live[0]), 4), n_live=oo_live[0],
                           d21=round(oo_21[1] / max(1, oo_21[0]), 4), n_21=oo_21[0]),
    sens_strict_gt=dict(d21=round(strict_21[1] / max(1, strict_21[0]), 4), n=strict_21[0]),
    sens_thr_11bps=dict(d21=round(thr_lo_21[1] / max(1, thr_lo_21[0]), 4), n=thr_lo_21[0]),
    sens_thr_13bps=dict(d21=round(thr_hi_21[1] / max(1, thr_hi_21[0]), 4), n=thr_hi_21[0]),
    live_boundary_cases=len(near), eff6_noise_bound=round(eff_noise, 4),
    bot_side_retention_within_rv_fills=dict(n=len(rv_settled), passed=bp,
                                            retention=round(bp / max(1, len(rv_settled)), 4)))

# retention CI (binomial normal approx on last-21d candle count)
p = d21_p / d21_s
se = math.sqrt(p * (1 - p) / d21_s)
res['C_retention']['last_21d']['ci95'] = [round(p - 1.96 * se, 4), round(p + 1.96 * se, 4)]

# --- D) integrity checks -----------------------------------------------------
from collections import Counter
c = Counter((t['eng'], t['t0']) for t in trades)
res['D_integrity'] = dict(
    dup_eng_t0=sum(1 for v in c.values() if v > 1),
    rv_total_all_time=sum(1 for t in trades if t['eng'] == 'reversal_v2'),
    slug_t1_mismatch_rv_in_window=sum(
        1 for t in rv if t.get('slug') and t['slug'].rsplit('-', 1)[-1].isdigit()
        and int(t['slug'].rsplit('-', 1)[-1]) != t['t0']),
    btcopen_vs_candle=None)
# epoch check: btcOpen in trades vs candle open at t0
diffs = []
for t in rv_settled:
    if t.get('btcOpen') and t['t0'] in O:
        diffs.append(abs(t['btcOpen'] - O[t['t0']]) / O[t['t0']])
res['D_integrity']['btcopen_vs_candle'] = dict(
    n=len(diffs), mean_relerr=round(sum(diffs) / max(1, len(diffs)), 6),
    max_relerr=round(max(diffs), 6) if diffs else None)

# --- E) TEST-window candle increment sanity (Jun 26 -> Jul 13) -----------------
tlo, thi = utc('2026-06-26 00:00'), utc('2026-07-13 03:10')
def ev_share(pfill, win):  # cents/share after frozen cost model
    return 100.0 * ((1.0 - pfill if win else -pfill) - 0.07 * pfill * (1 - pfill))
sig = []
for t0 in sorted(O):
    if not (tlo <= t0 <= thi): continue
    tp = t0 - IVL
    if tp not in ret_co or abs(ret_co[tp]) < 0.0012: continue
    ok, e6, c12 = gate(t0, ret_co)
    if ok is None: continue
    if t0 not in ret_oo: continue           # resolution: open(t0) vs open(t0+300)
    mv = ret_oo[t0]
    if abs(mv) < 1e-12: continue            # tie -> skip (counted below)
    win = (mv < 0) if (ret_co[tp] > 0) else (mv > 0)   # contrarian
    sig.append((t0, ok, win))
ties = sum(1 for t0 in sorted(O) if tlo <= t0 <= thi and (t0 - IVL) in ret_co
           and abs(ret_co[t0 - IVL]) >= 0.0012 and t0 in ret_oo and abs(ret_oo[t0]) < 1e-12)
PF = 0.49  # flat fill assumption (prior fill model .45/.49/.51); sensitivity at .51
def arm(rows, pf):
    if not rows: return None
    e = [ev_share(pf, w) for _, _, w in rows]
    return dict(n=len(rows), wr=round(sum(w for _, _, w in rows) / len(rows), 4),
                ev_c=round(sum(e) / len(e), 2))
gp = [s for s in sig if s[1]]; gr = [s for s in sig if not s[1]]
# 1h-block bootstrap on the increment
def blockboot_inc(gp, gr, pf, B=4000):
    byh = {}
    for t0, ok, w in gp + gr: byh.setdefault(t0 // 3600, []).append((ok, w))
    hours = list(byh)
    obs = arm(gp, pf)['ev_c'] - arm(gr, pf)['ev_c']
    ge0 = 0; le0 = 0; vals = []
    for _ in range(B):
        P = []; R = []
        for _ in hours:
            for ok, w in byh[random.choice(hours)]:
                (P if ok else R).append((0, ok, w))
        if not P or not R: continue
        vals.append(arm(P, pf)['ev_c'] - arm(R, pf)['ev_c'])
    vals.sort()
    n = len(vals)
    p_le0 = sum(1 for v in vals if v <= 0) / n
    return obs, round(2 * min(p_le0, 1 - p_le0), 4), [round(vals[int(.05 * n)], 2), round(vals[int(.95 * n)], 2)]
inc49, p49, ci49 = blockboot_inc(gp, gr, 0.49)
inc51, p51, ci51 = blockboot_inc(gp, gr, 0.51)
res['E_test_candle'] = dict(
    window=['2026-06-26', '2026-07-13 03:10'], n_signals=len(sig), ties_skipped=ties,
    gate_pass=arm(gp, PF), gate_rej=arm(gr, PF),
    increment_c_at49=round(inc49, 2), blockboot_p_at49=p49, ci90_at49=ci49,
    increment_c_at51=round(inc51, 2), blockboot_p_at51=p51,
    retention_test_window=round(len(gp) / len(sig), 4),
    note='simplified flat-fill re-check of increment direction/significance; not the analyst full fill model')

json.dump(res, open(W + '/results.json', 'w'), indent=1)
print(json.dumps({k: v for k, v in res.items() if k != 'A_rows'}, indent=1))
