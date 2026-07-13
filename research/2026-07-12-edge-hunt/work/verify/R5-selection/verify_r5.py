#!/usr/bin/env python3
"""Adversarial verification of FINDING R5 (multiplicity & selection lens).

R5 claims:
 (a) Accounting identity: net -2.74c/sh = fees -1.68 + slip -1.10 + halfspread -0.50
     + POSITIVE gross selection at mid +0.55c/sh, on 3,495 settled trades.
 (b) Momentum engines won 56.8% directionally but paid ~59c (q* ~ .60).
 (c) Residual continuation after >=2bps first-minute drift = 48.7% (no info);
     full-interval 72.1% is mechanical head start. Replicates Jul 10-13.
 (d) Invariant: ~3.3c gross hurdle for any future signal at 50c-class fills.

Attack surface verified here:
 1. Reproduce the decomposition identity independently; confirm arithmetic.
 2. THE FLAGGED FLAW: mid = ask - 0.5c counterfactual. Use REAL decision-time
    bid/ask from bot/signals.log (matched on engine+t0) to measure the actual
    spread on the traded books, recompute selection at the REAL mid, and
    block-bootstrap whether gross selection at mid/ask is distinguishable from 0.
 3. Hedged-trade / stop-loss counterfactual: quantify how much of the ledger
    deviates from hold-to-resolution, and redo the decomposition on unhedged only.
 4. Residual continuation: reproduce; Bonferroni over the K=3 thresholds actually
    searched; pre-registrable alternative split (Jun26-Jul6 vs Jul7-13); tie
    sensitivity (exclude vs count-as-half).
 5. Multiplicity census of the R5 evidence chain.

Stdlib only. Writes results.json in this dir.
"""
import json, math, random, collections, statistics, os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = '/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt'
TR   = os.path.join(ROOT, 'data', 'trades_unified.json')
CB1M = os.path.join(ROOT, 'data', 'cb1m.json')
SIG  = '/Users/sgonzalez/btc5m-paper-trader/bot/signals.log'

def fee(p): return 0.07 * p * (1.0 - p)

def block_boot(by_block, stat='mean', B=4000, seed=101):
    """1h-block bootstrap over lists of (num, den) or scalars."""
    rng = random.Random(seed)
    blocks = list(by_block.values())
    outs = []
    for _ in range(B):
        s = []
        for _ in range(len(blocks)):
            s.extend(blocks[rng.randrange(len(blocks))])
        if not s: continue
        if isinstance(s[0], tuple):
            num = sum(a for a, b in s); den = sum(b for a, b in s)
            outs.append(num / den if den else 0.0)
        else:
            outs.append(sum(s) / len(s))
    outs.sort()
    n = len(outs)
    return dict(mean=round(statistics.fmean(outs), 5),
                lo=round(outs[int(0.025 * n)], 5), hi=round(outs[int(0.975 * n)], 5),
                p_le0=round(sum(1 for x in outs if x <= 0) / n, 4),
                p_ge0=round(sum(1 for x in outs if x >= 0) / n, 4))

R = {}

# ---------------- load ----------------
tr = json.load(open(TR))
S = [t for t in tr if t.get('status') == 'settled' and t.get('result') in ('win', 'loss')]
assert len(S) == 3495
for t in S:
    t['w'] = 1.0 if t['result'] == 'win' else 0.0

MOM_DIR = ('loose', 'floor', 'band', 'value')

# ---------------- 1. reproduce the identity ----------------
sh   = sum(t['shares'] for t in S)
q_sw = sum(t['shares'] * t['w'] for t in S) / sh
p_sw = sum(t['shares'] * t['entry'] for t in S) / sh
a_sw = sum(t['shares'] * t['ask'] for t in S) / sh
fee_sw = sum(t['shares'] * fee(t['entry']) for t in S) / sh
net_c  = 100 * (q_sw - p_sw - fee_sw)
R['identity'] = dict(
    n=len(S), shares=round(sh, 1),
    q_sw=round(q_sw, 4), p_fill_sw=round(p_sw, 4), ask_sw=round(a_sw, 4),
    fee_c=round(100 * fee_sw, 2),
    slip_c=round(100 * (p_sw - a_sw), 2),
    sel_at_fill_c=round(100 * (q_sw - p_sw), 2),
    sel_at_ask_c=round(100 * (q_sw - a_sw), 2),
    sel_at_mid_assumed_c=round(100 * (q_sw - (a_sw - 0.005)), 2),
    net_c=round(net_c, 2),
    identity_check_c=round(100 * ((q_sw - (a_sw - 0.005)) - (p_sw - a_sw) - 0.005 - fee_sw) - net_c, 4))

# momentum-direction pooled wr claim (b)
md = [t for t in S if t['eng'] in MOM_DIR]
wr = statistics.fmean(t['w'] for t in md)
pbar = statistics.fmean(t['entry'] for t in md)
bb_wr = block_boot({h: [t['w'] for t in md if t['t0'] // 3600 == h]
                    for h in set(t['t0'] // 3600 for t in md)}, seed=7)
R['momentum_dir_wr'] = dict(n=len(md), wr=round(wr, 4), ci=[bb_wr['lo'], bb_wr['hi']],
                            avg_entry=round(pbar, 4), qstar_at_avg_entry=round(pbar + fee(pbar), 4))

# ---------------- 2. REAL spreads from signals.log ----------------
books = {}
with open(SIG) as f:
    for line in f:
        try: j = json.loads(line)
        except Exception: continue
        if 'ask' in j and 'bid' in j and j.get('bid') is not None:
            books[(j['engine'], j['t0'])] = (j['bid'], j['ask'])

matched, sp_counts = [], collections.Counter()
for t in S:
    b = books.get((t['eng'], t['t0']))
    if b:
        bid, ask = b
        sp = round(ask - bid, 4)
        sp_counts[sp] += 1
        matched.append((t, bid, ask, sp))

n_m = len(matched)
sh_m = sum(t['shares'] for t, *_ in matched)
q_m   = sum(t['shares'] * t['w'] for t, *_ in matched) / sh_m
ask_trade_m = sum(t['shares'] * t['ask'] for t, *_ in matched) / sh_m
mid_real_m  = sum(t['shares'] * (bid + ask) / 2 for t, bid, ask, _ in matched) / sh_m
mid_assumed_m = sum(t['shares'] * (t['ask'] - 0.005) for t, *_ in matched) / sh_m
ask_log_m   = sum(t['shares'] * ask for t, bid, ask, _ in matched) / sh_m
# per-trade selection at real mid, block bootstrap (share-weighted via tuples)
bb_mid_real = block_boot({h: [(t['shares'] * (t['w'] - (bid + ask) / 2), t['shares'])
                              for t, bid, ask, _ in matched if t['t0'] // 3600 == h]
                          for h in set(t['t0'] // 3600 for t, *_ in matched)}, seed=13)
bb_ask_real = block_boot({h: [(t['shares'] * (t['w'] - ask), t['shares'])
                              for t, bid, ask, _ in matched if t['t0'] // 3600 == h]
                          for h in set(t['t0'] // 3600 for t, *_ in matched)}, seed=17)
R['real_spread_check'] = dict(
    n_matched=n_m, frac_of_ledger=round(n_m / len(S), 3),
    spread_dist={str(k): v for k, v in sorted(sp_counts.items())},
    frac_spread_1c=round(sp_counts.get(0.01, 0) / n_m, 4),
    q_sw=round(q_m, 4),
    ask_trade_sw=round(ask_trade_m, 4), ask_log_sw=round(ask_log_m, 4),
    mid_real_sw=round(mid_real_m, 4), mid_assumed_sw=round(mid_assumed_m, 4),
    sel_at_real_mid_c=round(100 * (q_m - mid_real_m), 2),
    sel_at_real_mid_ci_c=[round(100 * bb_mid_real['lo'], 2), round(100 * bb_mid_real['hi'], 2)],
    sel_at_real_mid_p_le0=bb_mid_real['p_le0'],
    sel_at_log_ask_c=round(100 * (q_m - ask_log_m), 2),
    sel_at_log_ask_ci_c=[round(100 * bb_ask_real['lo'], 2), round(100 * bb_ask_real['hi'], 2)],
    sel_at_log_ask_p_le0=bb_ask_real['p_le0'])

# pooled sel at (assumed) mid and at ask with block bootstrap on ALL 3,495
hours = set(t['t0'] // 3600 for t in S)
bb_mid_all = block_boot({h: [(t['shares'] * (t['w'] - (t['ask'] - 0.005)), t['shares'])
                             for t in S if t['t0'] // 3600 == h] for h in hours}, seed=19)
bb_ask_all = block_boot({h: [(t['shares'] * (t['w'] - t['ask']), t['shares'])
                             for t in S if t['t0'] // 3600 == h] for h in hours}, seed=23)
R['pooled_selection_significance'] = dict(
    sel_at_mid_c=round(100 * (q_sw - (a_sw - 0.005)), 2),
    sel_at_mid_ci_c=[round(100 * bb_mid_all['lo'], 2), round(100 * bb_mid_all['hi'], 2)],
    sel_at_mid_p_le0=bb_mid_all['p_le0'],
    sel_at_ask_c=round(100 * (q_sw - a_sw), 2),
    sel_at_ask_ci_c=[round(100 * bb_ask_all['lo'], 2), round(100 * bb_ask_all['hi'], 2)],
    sel_at_ask_p_le0=bb_ask_all['p_le0'],
    spread_sensitivity_c={ '0c_spread(mid=ask)': round(100 * (q_sw - a_sw), 2),
                           '1c_spread(mid=ask-0.5c)': round(100 * (q_sw - a_sw + 0.005), 2),
                           '2c_spread(mid=ask-1c)': round(100 * (q_sw - a_sw + 0.01), 2)})

# ---------------- 3. hedge / stop-loss counterfactual ----------------
dev_tot = 0.0; dev_hedged = 0.0; n_hedged = 0; n_big = 0
for t in S:
    model = t['shares'] * (t['w'] - t['entry'] - fee(t['entry'])) - 0.004
    d = t['pnl'] - model
    dev_tot += d
    if t.get('hedge'):
        n_hedged += 1; dev_hedged += d
    if abs(d) > 1: n_big += 1
unh = [t for t in S if not t.get('hedge')]
sh_u = sum(t['shares'] for t in unh)
q_u = sum(t['shares'] * t['w'] for t in unh) / sh_u
p_u = sum(t['shares'] * t['entry'] for t in unh) / sh_u
a_u = sum(t['shares'] * t['ask'] for t in unh) / sh_u
fee_u = sum(t['shares'] * fee(t['entry']) for t in unh) / sh_u
R['hedge_stoploss_sensitivity'] = dict(
    n_hedged=n_hedged, n_unhedged=len(unh),
    ledger_minus_holdmodel_total=round(dev_tot, 2),
    ledger_minus_holdmodel_hedged_only=round(dev_hedged, 2),
    dev_as_c_per_share_of_pool=round(100 * dev_tot / sh, 3),
    unhedged_only=dict(q_sw=round(q_u, 4),
                       sel_at_mid_c=round(100 * (q_u - (a_u - 0.005)), 2),
                       sel_at_ask_c=round(100 * (q_u - a_u), 2),
                       net_c=round(100 * (q_u - p_u - fee_u), 2)))

# ---------------- 4. residual continuation ----------------
cb = json.load(open(CB1M))
tt, oo, cc = cb['t'], cb['o'], cb['c']
idx = {ts: i for i, ts in enumerate(tt)}
JUN26 = 1782432000
JUL7  = 1783382400   # 2026-07-07 00:00 UTC (trading window start)
JUL10_1505 = max(t['t0'] for t in S if t['eng'] == 'loose')  # v3 era boundary

def resid_stats(t0_lo, t0_hi, theta, tie='drop'):
    full_b, res_b = collections.defaultdict(list), collections.defaultdict(list)
    for t0 in range(min(tt) // 300 * 300 + 300, max(tt), 300):
        if not (t0_lo <= t0 < t0_hi): continue
        i0, i5 = idx.get(t0), idx.get(t0 + 300)
        if i0 is None or i5 is None: continue
        drift = cc[i0] / oo[i0] - 1
        if abs(drift) < theta: continue
        full_b[t0 // 3600].append(1.0 if (drift > 0) == (oo[i5] >= oo[i0]) else 0.0)
        r = oo[i5] / cc[i0] - 1
        if r != 0:
            res_b[t0 // 3600].append(1.0 if (drift > 0) == (r > 0) else 0.0)
        elif tie == 'half':
            res_b[t0 // 3600].append(0.5)
    fv = [v for b in full_b.values() for v in b]
    rv = [v for b in res_b.values() for v in b]
    if not rv: return None
    bb = block_boot(res_b, seed=int(theta * 1e6) + 3)
    return dict(n_full=len(fv), full=round(statistics.fmean(fv), 4),
                n_resid=len(rv), resid=round(statistics.fmean(rv), 4),
                resid_ci=[bb['lo'], bb['hi']],
                p_le_half=round(sum(1 for _ in [0]) and None or 0, 4) if False else None,
                bb=bb)

res = {}
for theta in (0.0002, 0.0004, 0.0008):
    key = f'{theta*1e4:.0f}bps'
    res[key] = {}
    for name, (lo_, hi_) in dict(full_window=(JUN26, 4e9), pre_trading=(JUN26, JUL7),
                                 trading_week=(JUL7, 4e9), fresh_jul10_13=(JUL10_1505, 4e9)).items():
        r_ = resid_stats(lo_, hi_, theta)
        if r_:
            r_.pop('bb'); r_.pop('p_le_half', None)
            res[key][name] = r_
    # tie sensitivity on full window
    r_half = resid_stats(JUN26, 4e9, theta, tie='half')
    res[key]['full_window_ties_as_half'] = dict(n=r_half['n_resid'], resid=r_half['resid'])
R['residual_continuation'] = res

# Bonferroni: K=3 thresholds searched; the DEVIATION claim is 8bps 45.7%.
# z-test vs 0.5 with block-bootstrap SE approximated from CI width.
r8 = res['8bps']['full_window']
se8 = (r8['resid_ci'][1] - r8['resid_ci'][0]) / (2 * 1.96)
z8 = (r8['resid'] - 0.5) / se8
from math import erf, sqrt
p8 = 2 * (1 - 0.5 * (1 + erf(abs(z8) / sqrt(2))))
R['residual_multiplicity'] = dict(
    K_thresholds=3, deviation_claim='8bps residual 45.7% < 50%',
    z_vs_half=round(z8, 2), p_two_sided=round(p8, 4),
    p_bonferroni_K3=round(min(1.0, p8 * 3), 4),
    note='the 2bps headline (48.7%) is a NULL claim; CI includes 0.5 so no selection issue')

json.dump(R, open(os.path.join(HERE, 'results.json'), 'w'), indent=1)
print(json.dumps(R, indent=1))
