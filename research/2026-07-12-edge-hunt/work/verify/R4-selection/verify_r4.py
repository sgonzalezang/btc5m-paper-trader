#!/usr/bin/env python3
"""Adversarial verification of FINDING R4 (kill-metric semantics divergence).

Checks, independently of the flagship agent's code:
 1. Deterministic cross-match of the 36 measurement records to the unified ledger
    (eng=impulse_v2) by t0: class counts, side identity, single-trade-per-interval,
    price relationship (entered-later must be cheaper than first poll), entrySec ordering.
 2. Recompute every headline number: per-class EV c/share after the frozen cost model,
    the -6.23c first-poll book, the operated flagship book on the same signals,
    the 9.8c gap, and bootstrap CIs.
 3. Decompose the gap into (a) price-improvement on re-entered signals and
    (b) composition (never-entered rich signals excluded from the operated book),
    and test how much is mechanical vs outcome noise (win-rate permutation).
 4. Selection audit: what was searched, what is deterministic vs estimated.
"""
import json, random, statistics

D = '/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data'
FEE = 0.07
GAS = 0.004

measure = json.load(open(D + '/state_extract.json'))['measure']
trades = [t for t in json.load(open(D + '/trades_unified.json')) if t.get('eng') == 'impulse_v2']

out = {}

# ---------- 1. deterministic cross-match ----------
by_t0 = {}
for t in trades:
    by_t0.setdefault(t['t0'], []).append(t)

dup_intervals = {k: len(v) for k, v in by_t0.items() if len(v) > 1}
meas_t0s = [m['t0'] for m in measure]
dup_meas = len(meas_t0s) - len(set(meas_t0s))

classes = {'sized_first_poll': [], 'rich_first_poll_entered_later': [], 'never_entered': [], 'anomaly': []}
side_mismatch, price_not_cheaper, sec_not_later, sized_cost_mismatch = [], [], [], []

def cost_of(p):  # frozen cost model: cost/share at fill price p
    return p + FEE * p * (1 - p)

for m in measure:
    tl = by_t0.get(m['t0'], [])
    if m['sized']:
        if len(tl) == 1:
            t = tl[0]
            classes['sized_first_poll'].append((m, t))
            if t['side'] != m['side']:
                side_mismatch.append(m['t0'])
            # record cost should equal cost_of(entry) of the ledger trade
            if abs(cost_of(t['entry']) - m['cost']) > 0.0021:
                sized_cost_mismatch.append((m['t0'], m['cost'], round(cost_of(t['entry']), 4)))
        else:
            classes['anomaly'].append((m, tl))
    else:  # skip record (all skips here are f_nonpos)
        if len(tl) == 0:
            classes['never_entered'].append((m, None))
        elif len(tl) == 1:
            t = tl[0]
            classes['rich_first_poll_entered_later'].append((m, t))
            if t['side'] != m['side']:
                side_mismatch.append(m['t0'])
            if cost_of(t['entry']) >= m['cost'] - 1e-9:
                price_not_cheaper.append((m['t0'], m['cost'], round(cost_of(t['entry']), 4)))
            fsec = (m.get('f') or {}).get('sec')
            if fsec is not None and t['entrySec'] <= fsec:
                sec_not_later.append((m['t0'], fsec, t['entrySec']))
        else:
            classes['anomaly'].append((m, tl))

# ledger trades NOT covered by any measurement record (pre-measurement-era entries)
uncovered = [t for t in trades if t['t0'] not in set(meas_t0s)]

out['crossmatch'] = dict(
    n_measure=len(measure), n_ledger_impulse_v2=len(trades),
    dup_ledger_intervals=dup_intervals, dup_measure_t0=dup_meas,
    counts={k: len(v) for k, v in classes.items()},
    skips_total=sum(1 for m in measure if not m['sized']),
    side_mismatches=side_mismatch,
    entered_later_not_cheaper=price_not_cheaper,
    entered_later_not_later_sec=sec_not_later,
    sized_cost_mismatches=sized_cost_mismatch,
    ledger_trades_with_no_measure_record=[t['t0'] for t in uncovered],
)

# ---------- 2. recompute headline numbers ----------
def book_stats(rows):  # rows = list of (cost, win) settled; per-share net vs frozen model
    n = len(rows)
    if n == 0: return dict(n=0)
    wins = sum(w for _, w in rows)
    net = [ (w - c) for c, w in rows ]   # win pays $1/share; cost already includes fee
    m = sum(net) / n
    return dict(n=n, wins=wins, wr=round(wins / n, 4), ev_ps_c=round(100 * m, 2))

def boot_ci(rows, B=20000, seed=7):
    if not rows: return None
    rng = random.Random(seed)
    net = [w - c for c, w in rows]
    ms = []
    for _ in range(B):
        s = [net[rng.randrange(len(net))] for _ in net]
        ms.append(sum(s) / len(s))
    ms.sort()
    return [round(100 * ms[int(0.05 * B)], 2), round(100 * ms[int(0.95 * B)], 2)]

# first-poll book (kill-metric input): every settled measurement record at record cost
fp_all = [(m['cost'], m['win']) for m in measure if m['win'] is not None]
out['first_poll_book'] = {**book_stats(fp_all), 'ci90': boot_ci(fp_all)}

# per class at first-poll cost
for name in ('sized_first_poll', 'rich_first_poll_entered_later', 'never_entered'):
    rows = [(m['cost'], m['win']) for m, _ in classes[name] if m['win'] is not None]
    out['class_' + name + '_at_first_poll_cost'] = {**book_stats(rows), 'ci90': boot_ci(rows)}

# re-entered class at REALIZED ledger cost
rows_re = [(cost_of(t['entry']), m['win']) for m, t in classes['rich_first_poll_entered_later'] if m['win'] is not None]
out['class_reentered_at_realized_cost'] = {**book_stats(rows_re), 'ci90': boot_ci(rows_re)}

# price improvement on the 12 re-entered (deterministic, outcome-free)
impr = [m['cost'] - cost_of(t['entry']) for m, t in classes['rich_first_poll_entered_later']]
out['reentered_price_improvement_c'] = dict(
    n=len(impr), mean_c=round(100 * sum(impr) / len(impr), 2),
    min_c=round(100 * min(impr), 2), max_c=round(100 * max(impr), 2))

# operated flagship book on the SAME signals (27 measure-matched entries, realized fills)
op_rows = []
for name in ('sized_first_poll', 'rich_first_poll_entered_later'):
    for m, t in classes[name]:
        if m['win'] is not None:
            op_rows.append((cost_of(t['entry']), m['win']))
out['operated_book_same_signals'] = {**book_stats(op_rows), 'ci90': boot_ci(op_rows)}
out['gap_c_recomputed'] = round(out['operated_book_same_signals']['ev_ps_c'] - out['first_poll_book']['ev_ps_c'], 2)

# operated flagship per-share from ledger pnl directly (sanity: includes gas, settledBy)
led = [t for t in trades if t.get('status') == 'settled' and t['t0'] in set(meas_t0s)]
tot_pnl = sum(t['pnl'] for t in led); tot_sh = sum(t['shares'] for t in led)
out['operated_ledger_pnl_check'] = dict(n=len(led), total_pnl=round(tot_pnl, 2),
    stake_wtd_ps_c=round(100 * tot_pnl / tot_sh, 2),
    eq_wtd_ps_c=round(100 * sum(t['pnl'] / t['shares'] for t in led) / len(led), 2))
allf = [t for t in trades if t.get('status') == 'settled']
out['flagship_full_ledger'] = dict(n=len(allf), total_pnl=round(sum(t['pnl'] for t in allf), 2))

# ---------- 3. decomposition of the gap ----------
# gap = operated(27 settled@realized) - firstpoll(35 settled@firstpoll)
# (a) price improvement effect on the 12 re-entered, holding outcomes fixed (deterministic)
# (b) composition effect of dropping the 9 never-entered
n_op = len(op_rows); n_fp = len(fp_all)
mech = sum(impr) / n_op if n_op else 0  # cheaper fills, outcomes identical -> pure mechanics (12 improvements spread over 27 trades)
fp_mean = sum(w - c for c, w in fp_all) / n_fp
fp_entered_only = [(m['cost'], m['win']) for name in ('sized_first_poll', 'rich_first_poll_entered_later')
                   for m, _ in classes[name] if m['win'] is not None]
comp = sum(w - c for c, w in fp_entered_only) / len(fp_entered_only) - fp_mean
out['gap_decomposition_c'] = dict(
    price_improvement_component=round(100 * mech, 2),
    composition_component_dropping_never_entered=round(100 * comp, 2),
    sum_check=round(100 * (mech + comp), 2))

# permutation: is the SIGN of the gap guaranteed? Shuffle wins across records,
# recompute gap each time -> distribution of gap under outcome-exchangeability.
rng = random.Random(11)
wins_pool = [m['win'] for m in measure if m['win'] is not None]
rec = [(m, t, name) for name in ('sized_first_poll', 'rich_first_poll_entered_later', 'never_entered')
       for m, t in classes[name] if m['win'] is not None]
gaps = []
for _ in range(20000):
    perm = wins_pool[:]
    rng.shuffle(perm)
    op, fp = [], []
    for (m, t, name), w in zip(rec, perm):
        fp.append(w - m['cost'])
        if t is not None:
            op.append(w - cost_of(t['entry']))
    gaps.append(100 * (sum(op) / len(op) - sum(fp) / len(fp)))
gaps.sort()
obs_gap = out['gap_c_recomputed']
out['gap_permutation'] = dict(
    observed_c=obs_gap,
    perm_mean_c=round(sum(gaps) / len(gaps), 2),
    perm_ci90=[round(gaps[1000], 2), round(gaps[19000], 2)],
    frac_perm_gap_positive=round(sum(1 for g in gaps if g > 0) / len(gaps), 4),
    p_gap_ge_observed=round(sum(1 for g in gaps if g >= obs_gap) / len(gaps), 4))

json.dump(out, open('/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work/verify/R4-selection/results.json', 'w'), indent=1)
print(json.dumps(out, indent=1))
