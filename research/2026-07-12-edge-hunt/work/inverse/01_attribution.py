#!/usr/bin/env python3
"""Retired-engine forensics, item 1: per-engine loss attribution.

Decomposition (exact, per-share, means over settled trades):
    EV/share = qhat - pbar - feebar
             = (qhat - 0.5)      [SIDE: directional value of the signal]
             + (0.5 - pbar)      [PRICE: premium paid vs 50c fair-coin anchor]
             - feebar            [FEE drag, frozen model 0.07*p*(1-p)]
Everything computed from the frozen cost model on hold-to-resolution
(result field = Polymarket settlement), NOT from ledger pnl (which includes
stop-loss salvage and hedges); ledger pnl reported alongside as cross-check.

Block bootstrap (1h blocks on t0) for the wr CI per engine.
"""
import json, math, random, statistics
from collections import defaultdict

DATA = '/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data/trades_unified.json'
OUT = '/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work/inverse/attribution.json'
FAM = ['loose', 'floor', 'band', 'value', 'fade']
JUL8 = 1783468800  # 2026-07-08 00:00 UTC reset

def fee(p):
    return 0.07 * p * (1 - p)

def block_boot_mean(vals_by_block, nboot=4000, seed=7):
    """1h-block bootstrap of the mean of per-trade values."""
    rng = random.Random(seed)
    blocks = list(vals_by_block.values())
    if not blocks:
        return None
    means = []
    for _ in range(nboot):
        sample = []
        for _ in range(len(blocks)):
            sample.extend(rng.choice(blocks))
        means.append(statistics.fmean(sample))
    means.sort()
    return means

def ci(means, lo=0.025, hi=0.975):
    return (means[int(lo * len(means))], means[int(hi * len(means))])

def p_less_than_zero(means):
    """two-sided-ish: fraction of bootstrap means >= 0 (for a loss claim)."""
    return sum(1 for m in means if m >= 0) / len(means)

def analyze(trades, label):
    n = len(trades)
    if n == 0:
        return None
    q = statistics.fmean(1.0 if t['result'] == 'win' else 0.0 for t in trades)
    p = statistics.fmean(t['entry'] for t in trades)
    f = statistics.fmean(fee(t['entry']) for t in trades)
    ev = q - p - f
    # per-trade EV/share values for bootstrap
    by_block = defaultdict(list)
    for t in trades:
        w = 1.0 if t['result'] == 'win' else 0.0
        by_block[t['t0'] // 3600].append(w - t['entry'] - fee(t['entry']))
    means = block_boot_mean(by_block)
    lo, hi = ci(means)
    # wr bootstrap
    by_block_w = defaultdict(list)
    for t in trades:
        by_block_w[t['t0'] // 3600].append(1.0 if t['result'] == 'win' else 0.0)
    wmeans = block_boot_mean(by_block_w, seed=11)
    wlo, whi = ci(wmeans)
    # dollar attribution
    tot_pnl = sum(t['pnl'] for t in trades)
    tot_shares = sum(t['shares'] for t in trades)
    # counterfactual hold-to-resolution dollars per frozen model
    hold = sum(t['shares'] * ((1.0 if t['result'] == 'win' else 0.0) - t['entry'] - fee(t['entry'])) - 0.004 for t in trades)
    dollars_fee = -sum(t['shares'] * fee(t['entry']) for t in trades)
    dollars_side = sum(t['shares'] * ((1.0 if t['result'] == 'win' else 0.0) - 0.5) for t in trades)
    dollars_price = sum(t['shares'] * (0.5 - t['entry']) for t in trades)
    return {
        'label': label, 'n': n,
        'wr': round(q, 4), 'wr_ci95_blockboot': [round(wlo, 4), round(whi, 4)],
        'avg_entry': round(p, 4),
        'avg_fee_share': round(f, 4),
        'ev_share_c': round(ev * 100, 2),
        'ev_share_ci95_c': [round(lo * 100, 2), round(hi * 100, 2)],
        'p_ev_ge_0': round(p_less_than_zero(means), 4),
        'decomp_c': {
            'side_(q-0.5)': round((q - 0.5) * 100, 2),
            'price_(0.5-p)': round((0.5 - p) * 100, 2),
            'fee_(-f)': round(-f * 100, 2),
        },
        'dollars': {
            'ledger_pnl': round(tot_pnl, 2),
            'hold_to_res_frozen_model': round(hold, 2),
            'side_component': round(dollars_side, 2),
            'price_component': round(dollars_price, 2),
            'fee_component': round(dollars_fee, 2),
        },
        'breakeven_q_at_avg_entry': round(p + fee(p), 4),
    }

def main():
    d = json.load(open(DATA))
    settled = [t for t in d if t['status'] == 'settled' and t['eng'] in FAM]
    out = {'note': 'momentum-family forensics; hold-to-resolution frozen cost model; 1h-block bootstrap 4000 reps', 'engines': {}}
    for e in FAM:
        sub = [t for t in settled if t['eng'] == e]
        pre = [t for t in sub if t['t0'] < JUL8]
        post = [t for t in sub if t['t0'] >= JUL8]
        out['engines'][e] = analyze(sub, e)
        if pre:
            out['engines'][e + '_pre_reset'] = analyze(pre, e + ' pre-Jul8')
        if post and pre:
            out['engines'][e + '_post_reset'] = analyze(post, e + ' post-Jul8')
    out['pooled_momentum_dir'] = analyze([t for t in settled if t['eng'] in ('loose', 'floor', 'band', 'value')], 'pooled momentum-direction engines')
    out['pooled_all5'] = analyze(settled, 'all 5 retired engines')
    json.dump(out, open(OUT, 'w'), indent=1)
    # console summary
    for k, v in out.items():
        if not isinstance(v, dict) or 'n' not in v:
            continue
        print(f"{k:22s} n={v['n']:4d} wr={v['wr']:.3f} {v['wr_ci95_blockboot']} p̄={v['avg_entry']:.3f} "
              f"EV/sh={v['ev_share_c']:+.2f}c CI{v['ev_share_ci95_c']} "
              f"side={v['decomp_c']['side_(q-0.5)']:+.1f} price={v['decomp_c']['price_(0.5-p)']:+.1f} fee={v['decomp_c']['fee_(-f)']:+.1f} "
              f"$ledger={v['dollars']['ledger_pnl']:+.0f} $hold={v['dollars']['hold_to_res_frozen_model']:+.0f}")

if __name__ == '__main__':
    main()
