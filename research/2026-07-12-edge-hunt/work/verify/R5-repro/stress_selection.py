#!/usr/bin/env python3
"""
Adversarial stress of the '+0.55c positive selection at mid' leg of R5.

The 3,495-trade sample = settled win/loss. It INCLUDES 71 hedged trades
(profit-lock hedges placed ~263s into the interval only when the main leg
was ~93-99c; 70/71 won) and EXCLUDES 70 stop-lossed trades (losers-
conditioned exits, result='stopped', btcClose not recorded).
That is asymmetric conditioning. Here I:
  1. reconstruct hold-to-resolution counterfactual outcomes for the 70
     stopped trades from Coinbase 1m opens (open(t0) vs open(t0+300)),
  2. recompute share-weighted selection at fill/ask/mid on the SYMMETRIC
     all-entries universe (3,494 + 70 = every signal that fired), with
     1h-block bootstrap CI,
  3. stress: drop the single best day (largest positive daily selection
     contribution), split-half, jitter the mid assumption +/-0.5c and a
     price-cap bucket edge +/-1c.
"""
import json, random
from collections import defaultdict

TR = '/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data/trades_unified.json'
CB = '/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data/cb1m.json'


def load():
    d = json.load(open(CB))
    opens = dict(zip(d['t'], d['o']))
    rows = []
    n_stop_no_cf = 0
    for t in json.load(open(TR)):
        if t.get('status') != 'settled':
            continue
        res = t.get('result')
        ask, entry, shares = t['ask'], t['entry'], t['shares']
        if not shares or shares <= 0:
            continue
        if res in ('win', 'loss'):
            q, kind = (1.0 if res == 'win' else 0.0), ('hedged' if t.get('hedge') else 'hold')
        elif res == 'stopped':
            a, c = opens.get(t['t0']), opens.get(t['t0'] + 300)
            if a is None or c is None or c == a:
                n_stop_no_cf += 1
                continue
            q, kind = (1.0 if ((t['side'] == 'up') == (c > a)) else 0.0), 'stopped_cf'
        else:
            continue
        rows.append(dict(at=t['at'], eng=t['eng'], ask=ask, entry=entry,
                         shares=shares, q=q, kind=kind))
    return rows, n_stop_no_cf


def sel(rows, bench_off):
    """share-weighted (q - (ask - bench_off)) in cents"""
    S = sum(r['shares'] for r in rows)
    return sum(r['shares'] * (r['q'] - (r['ask'] - bench_off)) for r in rows) / S * 100


def boot(rows, bench_off, B=4000, seed=17):
    blocks = defaultdict(list)
    for r in rows:
        blocks[int(r['at'] // 3600000)].append(r)
    keys = list(blocks.keys())
    rng = random.Random(seed)
    st = []
    for _ in range(B):
        pool = []
        for _ in keys:
            pool.extend(blocks[rng.choice(keys)])
        st.append(sel(pool, bench_off))
    st.sort()
    return round(st[int(.025 * B)], 3), round(st[int(.975 * B)], 3)


def panel(rows, label, ci=True):
    d = dict(label=label, n=len(rows), shares=round(sum(r['shares'] for r in rows), 1),
             sel_fill_c=round(sel(rows, -0.01), 3),   # bench = ask + 1c slip
             sel_ask_c=round(sel(rows, 0.0), 3),
             sel_mid_c=round(sel(rows, 0.005), 3))
    if ci:
        d['ci95_mid'] = boot(rows, 0.005)
    return d


def main():
    rows, n_stop_dropped = load()
    kinds = defaultdict(list)
    for r in rows:
        kinds[r['kind']].append(r)
    out = {'n_stopped_without_counterfactual': n_stop_dropped}

    artifact_universe = kinds['hold'] + kinds['hedged']          # = the 3,495
    symmetric = rows                                             # + stopped cf
    clean = kinds['hold']                                        # no cond. exits

    out['artifact_universe_3495'] = panel(artifact_universe, 'win/loss as logged')
    out['symmetric_all_entries'] = panel(symmetric, 'incl. stopped counterfactuals')
    out['clean_holds_only'] = panel(clean, 'excl. hedged AND stopped')
    out['hedged_subset'] = panel(kinds['hedged'], 'hedged only', ci=False)
    out['stopped_cf_subset'] = panel(kinds['stopped_cf'], 'stopped cf only', ci=False)
    out['stopped_cf_winrate'] = round(
        sum(r['q'] for r in kinds['stopped_cf']) / len(kinds['stopped_cf']), 4)

    # --- stresses on the symmetric universe, sel at mid ---
    daily = defaultdict(list)
    for r in symmetric:
        daily[int(r['at'] // 86400000)].append(r)
    contrib = {d: sum(r['shares'] * (r['q'] - (r['ask'] - 0.005)) for r in v)
               for d, v in daily.items()}
    best = max(contrib, key=lambda d: contrib[d])
    kept = [r for r in symmetric if int(r['at'] // 86400000) != best]
    out['stress_drop_best_day'] = dict(dropped_epoch_day=best,
                                       dropped_contrib_usd=round(contrib[best] , 2),
                                       **panel(kept, 'drop best day'))

    srt = sorted(symmetric, key=lambda r: r['at'])
    h = len(srt) // 2
    out['stress_first_half'] = panel(srt[:h], 'first half')
    out['stress_second_half'] = panel(srt[h:], 'second half')

    # jitter mid assumption
    out['mid_jitter'] = {f'halfspread_{o*100:.1f}c': round(sel(symmetric, o), 3)
                         for o in (0.0, 0.005, 0.01)}
    # jitter a 53c-style bucket edge +/-1c: selection above/below the edge
    for edge in (0.52, 0.53, 0.54):
        lo = [r for r in symmetric if r['entry'] <= edge]
        hi = [r for r in symmetric if r['entry'] > edge]
        out[f'bucket_edge_{int(edge*100)}c'] = dict(
            below=panel(lo, 'below', ci=False), above=panel(hi, 'above', ci=False))

    json.dump(out, open('selection_stress_results.json', 'w'), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == '__main__':
    main()
