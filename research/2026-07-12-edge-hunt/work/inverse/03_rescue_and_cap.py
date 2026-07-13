#!/usr/bin/env python3
"""Items 3 + 4: conditional rescue grid (original direction) and the
momentum-with-price-cap question, plus fade-vs-loose reconciliation.

Rescue grid: 3 dims max, pre-declared:
  scope: each of 5 engines + pooled-momentum(4 engines) + pooled-all5  (7 scopes)
  entry cap X in {0.45, 0.50, 0.53, 0.55, 0.60, 1.00}                  (6)
  side in {up, down, both}                                             (3)
  passCount >= Y in {any, 7, 8, 9}                                     (4)
K = all evaluated cells with n >= 30. Best cell reported with 1h-block
bootstrap p and Bonferroni x K. Everything is in-sample on Jul 7-10; there is
no TEST period for this family, so the bar is: survive Bonferroni AND make
economic sense - otherwise dead.

Calibration: pooled momentum-engine trades bucketed by entry price:
does realized q(p) ever clear q*(p) = p + 0.07 p(1-p)?

Momentum+cap (item 4):
  (a) real momentum-engine fills with entry <= 0.50
  (b) momentum side of fade's triggers = invert fade at 1-bid+1c, cap 0.50
Fade-vs-loose reconciliation: same-t0 overlap, side agreement, outcome.
"""
import json, random, statistics
from collections import defaultdict

DATA = '/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data/trades_unified.json'
SIGLOG = '/Users/sgonzalez/btc5m-paper-trader/bot/signals.log'
OUTDIR = '/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work/inverse'
FAM = ['loose', 'floor', 'band', 'value', 'fade']
MOM = ['loose', 'floor', 'band', 'value']

def fee(p):
    return 0.07 * p * (1 - p)

def ev_rows(trades):
    return [(t, (1.0 if t['result'] == 'win' else 0.0) - t['entry'] - fee(t['entry'])) for t in trades]

def block_boot_p(rows, nboot=4000, seed=17):
    """P(mean EV <= 0) complement: returns fraction of bootstrap means <= 0 (one-sided p for EV>0 claim)."""
    by_block = defaultdict(list)
    for t, e in rows:
        by_block[t['t0'] // 3600].append(e)
    rng = random.Random(seed)
    blocks = list(by_block.values())
    means = []
    for _ in range(nboot):
        s = []
        for _ in range(len(blocks)):
            s.extend(rng.choice(blocks))
        means.append(statistics.fmean(s))
    means.sort()
    p_le0 = sum(1 for m in means if m <= 0) / len(means)
    return p_le0, means[int(0.025 * len(means))], means[int(0.975 * len(means))]

def main():
    d = json.load(open(DATA))
    settled = [t for t in d if t['status'] == 'settled' and t['eng'] in FAM]

    # ---------- rescue grid ----------
    scopes = {e: [t for t in settled if t['eng'] == e] for e in FAM}
    scopes['POOL_MOM'] = [t for t in settled if t['eng'] in MOM]
    scopes['POOL_ALL'] = settled
    caps = [0.45, 0.50, 0.53, 0.55, 0.60, 1.00]
    sides = ['up', 'down', 'both']
    pcs = [None, 7, 8, 9]
    cells = []
    K = 0
    for sc, trades in scopes.items():
        for cap in caps:
            for side in sides:
                for pc in pcs:
                    sub = [t for t in trades if t['entry'] <= cap
                           and (side == 'both' or t['side'] == side)
                           and (pc is None or t['passCount'] >= pc)]
                    if len(sub) < 30:
                        continue
                    K += 1
                    rows = ev_rows(sub)
                    ev = statistics.fmean(r[1] for r in rows)
                    cells.append({'scope': sc, 'cap': cap, 'side': side, 'pc': pc,
                                  'n': len(sub), 'ev_c': round(ev * 100, 2),
                                  'wr': round(statistics.fmean(1.0 if t['result'] == 'win' else 0.0 for t in sub), 4),
                                  '_rows': rows})
    cells.sort(key=lambda c: -c['ev_c'])
    top = []
    for c in cells[:8]:
        p, lo, hi = block_boot_p(c['_rows'])
        c2 = {k: v for k, v in c.items() if k != '_rows'}
        c2['p_blockboot_1sided'] = round(p, 4)
        c2['p_bonferroni_K'] = round(min(1.0, p * K), 4)
        c2['ci95_c'] = [round(lo * 100, 2), round(hi * 100, 2)]
        top.append(c2)
    n_pos = sum(1 for c in cells if c['ev_c'] > 0)
    grid_out = {'K_cells_evaluated': K, 'n_cells_ev_positive': n_pos, 'top8_by_ev': top}

    # ---------- calibration q(p) on momentum engines ----------
    calib = []
    mom = [t for t in settled if t['eng'] in MOM]
    buckets = [(0.30, 0.45), (0.45, 0.50), (0.50, 0.55), (0.55, 0.60), (0.60, 0.65), (0.65, 0.70), (0.70, 1.0)]
    for lo, hi in buckets:
        sub = [t for t in mom if lo < t['entry'] <= hi]
        if len(sub) < 20:
            calib.append({'bucket': f'{lo}-{hi}', 'n': len(sub)})
            continue
        q = statistics.fmean(1.0 if t['result'] == 'win' else 0.0 for t in sub)
        p = statistics.fmean(t['entry'] for t in sub)
        calib.append({'bucket': f'{lo}-{hi}', 'n': len(sub), 'q': round(q, 4), 'pbar': round(p, 4),
                      'q_star': round(p + fee(p), 4), 'net_c': round((q - p - fee(p)) * 100, 2)})

    # ---------- item 4a: real momentum fills <= 50c ----------
    m50 = [t for t in mom if t['entry'] <= 0.50]
    rows = ev_rows(m50)
    p1, lo1, hi1 = block_boot_p(rows)
    item4a = {'n': len(m50), 'wr': round(statistics.fmean(1.0 if t['result'] == 'win' else 0.0 for t in m50), 4),
              'avg_entry': round(statistics.fmean(t['entry'] for t in m50), 4),
              'ev_c': round(statistics.fmean(r[1] for r in rows) * 100, 2),
              'ci95_c': [round(lo1 * 100, 2), round(hi1 * 100, 2)], 'p_1sided': round(p1, 4)}

    # ---------- item 4b: momentum side of fade triggers, capped 50c ----------
    fade = [t for t in settled if t['eng'] == 'fade']
    rows_b = []
    for t in fade:
        p_inv = 1 - (t['ask'] - 0.01) + 0.01  # 1c spread fallback (fade not in signals.log)
        if p_inv > 0.50:
            continue
        w = 0.0 if t['result'] == 'win' else 1.0
        rows_b.append((t, w - p_inv - fee(p_inv)))
    item4b = {'n': len(rows_b)}
    if len(rows_b) >= 20:
        p2, lo2, hi2 = block_boot_p(rows_b)
        item4b.update({'ev_c': round(statistics.fmean(r[1] for r in rows_b) * 100, 2),
                       'inv_wr': round(statistics.fmean(r[1] + 0 for r in [(t, w) for (t, w) in []] or [0]) if False else 0, 4),
                       'ci95_c': [round(lo2 * 100, 2), round(hi2 * 100, 2)], 'p_1sided': round(p2, 4)})
        item4b['inv_wr'] = round(statistics.fmean(1.0 if t['result'] == 'loss' else 0.0 for t, _ in rows_b), 4)

    # ---------- fade vs loose reconciliation ----------
    loose_by_t0 = {t['t0']: t for t in settled if t['eng'] == 'loose'}
    both = [(loose_by_t0[t['t0']], t) for t in fade if t['t0'] in loose_by_t0]
    opp = sum(1 for l, f in both if l['side'] != f['side'])
    mom_won = sum(1 for l, f in both if l['result'] == 'win' and l['side'] != f['side'])
    recon = {'n_shared_t0': len(both), 'n_opposite_side': opp,
             'loose_wr_on_shared': round(statistics.fmean(1.0 if l['result'] == 'win' else 0.0 for l, f in both), 4) if both else None,
             'loose_avg_entry_shared': round(statistics.fmean(l['entry'] for l, f in both), 4) if both else None,
             'fade_avg_entry_shared': round(statistics.fmean(f['entry'] for l, f in both), 4) if both else None,
             'entry_sum_shared': round(statistics.fmean(l['entry'] + f['entry'] for l, f in both), 4) if both else None}

    out = {'rescue_grid': grid_out, 'calibration_q_of_p_momentum': calib,
           'item4a_momentum_fills_le50c': item4a, 'item4b_fade_inverted_le50c': item4b,
           'fade_vs_loose': recon}
    json.dump(out, open(f'{OUTDIR}/rescue_and_cap.json', 'w'), indent=1)
    print(json.dumps(out, indent=1))

if __name__ == '__main__':
    main()
