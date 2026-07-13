#!/usr/bin/env python3
"""
Independent reproduction of FINDING R5, leg 1: the accounting identity.

Claim (plain English): across the 3,495 settled trades, per-share net PnL of
-2.74c decomposes as fees -1.68c + slip -1.10c + half-spread -0.50c against
POSITIVE gross selection at mid of +0.55c/share; momentum engines won 56.8%
directionally but paid ~59c where break-even q* = .596.

Written from scratch, from the claim statement only. Definitions I use:
  p_fill = entry (ledger says entry = ask + 1c slip)
  slip_c = 100*(entry - ask)
  mid    = ask - 0.005   (spread assumed 1c; empirically 32/33 decision-time
                          spreads in state_extract are exactly 1c)
  q      = 1{win} for hold-to-resolution trades.
For 'stopped' (stop-loss) trades I compute a COUNTERFACTUAL q from
btcClose vs btcOpen + side, and I run every headline number three ways:
  (A) clean holds only (no hedge, no stop): pure, no counterfactuals at all
  (B) + stopped w/ counterfactual q
  (C) + hedged (hedge leg ignored, main leg treated as hold)
so the merge-agent's flaw ("selection rests on counterfactuals for 68+71
trades") is directly measurable.

Selection is also reported AT ASK and AT FILL, removing the mid assumption.
1h-block bootstrap CIs on selection (share-weighted, blocks by hour of `at`).
"""
import json, math, random
from collections import defaultdict

DATA = '/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data/trades_unified.json'
MOMENTUM = {'loose', 'floor', 'band', 'value', 'fade'}

def qstar(p):
    return p + 0.07 * p * (1 - p)

def load():
    trades = json.load(open(DATA))
    out = []
    for t in trades:
        if t.get('status') != 'settled':
            continue
        res = t.get('result')
        if res not in ('win', 'loss', 'stopped'):
            continue
        ask, entry, shares = t['ask'], t['entry'], t['shares']
        if not shares or shares <= 0:
            continue
        if res == 'stopped':
            # counterfactual hold-to-resolution outcome from btc feed
            if t.get('btcClose') is None or t.get('btcOpen') is None:
                continue  # cannot form counterfactual; dropped (count is tiny)
            up = t['btcClose'] > t['btcOpen']
            q = 1.0 if ((t['side'] == 'up') == up) else 0.0
            cf = True
        else:
            q = 1.0 if res == 'win' else 0.0
            cf = False
        out.append(dict(at=t['at'], eng=t['eng'], ask=ask, entry=entry,
                        shares=shares, q=q, cf=cf, pnl=t.get('pnl'),
                        feeE=t.get('feeEntry'), feeX=t.get('feeExit'),
                        gas=t.get('gas'), hedged=bool(t.get('hedge')),
                        stopped=(res == 'stopped')))
    return out

def sharewtd(rows, f):
    S = sum(r['shares'] for r in rows)
    return sum(r['shares'] * f(r) for r in rows) / S

def decomposition(rows, label):
    S = sum(r['shares'] for r in rows)
    q = sharewtd(rows, lambda r: r['q'])
    fill = sharewtd(rows, lambda r: r['entry'])
    ask = sharewtd(rows, lambda r: r['ask'])
    mid = ask - 0.005
    # frozen fee model per share on the fill price
    fee_c = sharewtd(rows, lambda r: 0.07 * r['entry'] * (1 - r['entry'])) * 100
    slip_c = (fill - ask) * 100
    half_c = 0.5
    sel_fill_c = (q - fill) * 100
    sel_ask_c = (q - ask) * 100
    sel_mid_c = (q - mid) * 100
    net_model_c = sel_fill_c - fee_c            # excl. gas
    gas_c = sum((r['gas'] or 0) for r in rows) / S * 100
    # reconciliation vs logged pnl where fields exist
    pnl_logged = sum(r['pnl'] for r in rows if r['pnl'] is not None)
    pnl_model = sum(r['shares'] * (r['q'] - r['entry'])
                    - (r['feeE'] or 0) - (r['feeX'] or 0) - (r['gas'] or 0)
                    for r in rows)
    return dict(label=label, n=len(rows), shares=round(S, 1),
                q_sw=round(q, 4), fill_sw=round(fill, 4), ask_sw=round(ask, 4),
                sel_at_fill_c=round(sel_fill_c, 3),
                sel_at_ask_c=round(sel_ask_c, 3),
                sel_at_mid_c=round(sel_mid_c, 3),
                fee_c=round(fee_c, 3), slip_c=round(slip_c, 3),
                halfspread_c=half_c, gas_c=round(gas_c, 4),
                net_c_model=round(net_model_c - gas_c, 3),
                identity_check=round(sel_mid_c - half_c - slip_c - fee_c
                                     - gas_c - (net_model_c - gas_c), 4),
                pnl_logged=round(pnl_logged, 2), pnl_model=round(pnl_model, 2),
                recon_gap_c_per_share=round((pnl_logged - pnl_model) / S * 100, 3))

def block_bootstrap_sel(rows, bench, B=4000, seed=7):
    """1h-block bootstrap of share-weighted selection (q - bench) in cents."""
    blocks = defaultdict(list)
    for r in rows:
        blocks[int(r['at'] // 3600000)].append(r)
    keys = list(blocks.keys())
    rng = random.Random(seed)
    stats = []
    for _ in range(B):
        samp = [blocks[rng.choice(keys)] for _ in keys]
        num = den = 0.0
        for blk in samp:
            for r in blk:
                num += r['shares'] * (r['q'] - bench(r))
                den += r['shares']
        stats.append(num / den * 100)
    stats.sort()
    return (round(stats[int(0.025 * B)], 3), round(stats[int(0.975 * B)], 3))

def main():
    rows = load()
    holds = [r for r in rows if not r['cf'] and not r['hedged']]
    hold_plus_stop = [r for r in rows if not r['hedged']]
    everything = rows

    out = {'universes': {}}
    for label, rs in (('A_clean_holds', holds),
                      ('B_plus_stopped_cf', hold_plus_stop),
                      ('C_all_incl_hedged', everything)):
        d = decomposition(rs, label)
        d['ci95_sel_at_mid'] = block_bootstrap_sel(rs, lambda r: r['ask'] - 0.005)
        d['ci95_sel_at_ask'] = block_bootstrap_sel(rs, lambda r: r['ask'])
        d['ci95_sel_at_fill'] = block_bootstrap_sel(rs, lambda r: r['entry'])
        out['universes'][label] = d

    # momentum sub-claim: won 56.8% at ~59c where q* = .596
    mom = [r for r in everything if r['eng'] in MOMENTUM]
    wr = sum(r['q'] for r in mom) / len(mom)
    wr_sw = sharewtd(mom, lambda r: r['q'])
    fill_sw = sharewtd(mom, lambda r: r['entry'])
    out['momentum'] = dict(n=len(mom), winrate_unwtd=round(wr, 4),
                           winrate_sharewtd=round(wr_sw, 4),
                           fill_sharewtd=round(fill_sw, 4),
                           qstar_at_fill=round(qstar(fill_sw), 4))

    # mid-assumption sensitivity: half-spread 0 / 0.5 / 1.0c
    A = out['universes']['A_clean_holds']
    out['mid_sensitivity_cleanholds'] = {
        'halfspread_0c(sel_at_ask)': A['sel_at_ask_c'],
        'halfspread_0.5c(sel_at_mid)': A['sel_at_mid_c'],
        'halfspread_1c': round(A['sel_at_ask_c'] + 1.0, 3)}

    json.dump(out, open('accounting_results.json', 'w'), indent=1)
    print(json.dumps(out, indent=1))

if __name__ == '__main__':
    main()
