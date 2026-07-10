#!/usr/bin/env python3
"""Tie rule / flat-interval structure — parts (a) and (b).

(a) fraction of intervals with |move|<1bps and <2bps, by session and trailing-vol decile
(b) P(Up) (c>=o, ties Up) by trailing-vol decile, TRAIN/TEST chronological split,
    block bootstrap (12-interval blocks) p-values for quietest deciles.

Stdlib only. Outputs JSON + text table to work/tieflat/.
"""
import json, math, random, statistics as st

SCRATCH = '/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad'
D = SCRATCH + '/data/'
W = SCRATCH + '/work/tieflat/'

cb = json.load(open(D + 'cb5m.json'))
t, o, c = cb['t'], cb['o'], cb['c']
n = len(t)

# --- continuity check ---
gaps = sum(1 for i in range(1, n) if t[i] - t[i-1] != 300)
print(f'candles={n} gaps={gaps}')

# --- build rows: for each interval i with 12 contiguous prior intervals ---
# move_bps: intra-interval (c-o)/o ; trailing vol: mean |move_bps| of prior 12 intervals
rows = []  # (i, t0, move_bps, up, tie_exact, tvol, hour)
move_bps = [ (c[i] - o[i]) / o[i] * 1e4 for i in range(n) ]
for i in range(12, n):
    if t[i] - t[i-12] != 3600:
        continue  # require contiguous trailing hour
    tv = sum(abs(move_bps[j]) for j in range(i-12, i)) / 12.0
    up = 1 if c[i] >= o[i] else 0
    tie = 1 if c[i] == o[i] else 0
    hour = (t[i] // 3600) % 24
    rows.append((i, t[i], move_bps[i], up, tie, tv, hour))

N = len(rows)
split = int(N * 2 / 3)
train, test = rows[:split], rows[split:]
print(f'usable={N} train={len(train)} test={len(test)}')
print(f'train span {train[0][1]}..{train[-1][1]}  test span {test[0][1]}..{test[-1][1]}')

# exact ties (Coinbase c==o)
ties_all = sum(r[4] for r in rows)
print(f'exact Coinbase ties c==o: {ties_all} ({ties_all/N*100:.3f}%)')

# --- decile edges from TRAIN trailing vol ---
tv_train = sorted(r[5] for r in train)
edges = [tv_train[int(len(tv_train) * k / 10)] for k in range(1, 10)]
def decile(tv):
    d = 0
    for e in edges:
        if tv >= e: d += 1
        else: break
    return d

def sess(hour):
    if hour < 8: return 'Asia(00-08utc)'
    if hour < 16: return 'EU(08-16utc)'
    return 'US(16-24utc)'

# --- (a) flat fractions by session and by decile (full 60d, also test-only) ---
def flat_frac(sub):
    m = len(sub)
    f1 = sum(1 for r in sub if abs(r[2]) < 1.0) / m
    f2 = sum(1 for r in sub if abs(r[2]) < 2.0) / m
    return m, f1, f2

out = {'edges_bps': edges, 'gaps': gaps, 'n_usable': N,
       'exact_ties': ties_all, 'sessions': {}, 'deciles': {}, 'p_up': {}}

print('\n(a) flat fractions by session (full 60d):')
for s in ['Asia(00-08utc)', 'EU(08-16utc)', 'US(16-24utc)']:
    sub = [r for r in rows if sess(r[6]) == s]
    m, f1, f2 = flat_frac(sub)
    out['sessions'][s] = {'n': m, 'lt1bps': f1, 'lt2bps': f2}
    print(f'  {s:16s} n={m:6d}  |mv|<1bps={f1*100:5.2f}%  <2bps={f2*100:5.2f}%')

print('\n(a) flat fractions by trailing-vol decile (train-edges, full 60d):')
for d in range(10):
    sub = [r for r in rows if decile(r[5]) == d]
    m, f1, f2 = flat_frac(sub)
    out['deciles'][d] = {'n': m, 'lt1bps': f1, 'lt2bps': f2}
    print(f'  D{d} n={m:5d}  <1bps={f1*100:5.2f}%  <2bps={f2*100:5.2f}%')

# session x decile flat<2bps grid (compact)
print('\n(a) <2bps fraction, session x decile:')
grid = {}
for s in ['Asia(00-08utc)', 'EU(08-16utc)', 'US(16-24utc)']:
    line = []
    for d in range(10):
        sub = [r for r in rows if sess(r[6]) == s and decile(r[5]) == d]
        line.append(round(sum(1 for r in sub if abs(r[2]) < 2.0) / max(1, len(sub)), 4))
    grid[s] = line
    print(f'  {s:16s} ' + ' '.join(f'{x*100:5.1f}' for x in line))
out['grid_lt2bps'] = grid

# --- (b) P(Up) by decile, TRAIN and TEST ---
def block_boot_pup(sub_idx_up, nboot=4000, seed=7):
    """sub_idx_up: list of (row_index_in_series, up). Blocks = consecutive 12-interval
    chunks of the underlying series; resample blocks, keep members of subset."""
    if not sub_idx_up: return None
    rnd = random.Random(seed)
    # map block id -> ups in subset within that block
    blocks = {}
    for idx, up in sub_idx_up:
        b = idx // 12
        blocks.setdefault(b, []).append(up)
    bids = list(blocks.values())
    B = len(bids)
    stats = []
    for _ in range(nboot):
        tot = w = 0
        for _ in range(B):
            blk = bids[rnd.randrange(B)]
            tot += len(blk); w += sum(blk)
        if tot: stats.append(w / tot)
    stats.sort()
    return stats

print('\n(b) P(Up) by trailing-vol decile:')
print('      TRAIN                 TEST')
for d in range(10):
    res = {}
    for name, sub in (('train', train), ('test', test)):
        s2 = [(r[0], r[3]) for r in sub if decile(r[5]) == d]
        m = len(s2); w = sum(u for _, u in s2)
        pup = w / m if m else float('nan')
        # block bootstrap p-value for pup > 0.5 (one-sided): fraction of boot <= 0.5
        boots = block_boot_pup(s2)
        pval = sum(1 for x in boots if x <= 0.5) / len(boots) if boots else None
        lo = boots[int(0.025 * len(boots))] if boots else None
        hi = boots[int(0.975 * len(boots))] if boots else None
        res[name] = {'n': m, 'p_up': pup, 'boot_p_gt_half': pval, 'ci': [lo, hi]}
    out['p_up'][d] = res
    a, b = res['train'], res['test']
    print(f'  D{d} n={a["n"]:5d} pUp={a["p_up"]:.4f} p={a["boot_p_gt_half"]:.4f} | '
          f'n={b["n"]:4d} pUp={b["p_up"]:.4f} p={b["boot_p_gt_half"]:.4f} '
          f'ci=[{b["ci"][0]:.3f},{b["ci"][1]:.3f}]')

# P(Up) conditioned on realized flatness (diagnostic; NOT tradable — uses future info)
print('\n(diag) P(Up) among realized |move|<1bps and <2bps (full / train / test):')
for lbl, cut in (('<1bps', 1.0), ('<2bps', 2.0)):
    for name, sub in (('full', rows), ('train', train), ('test', test)):
        s2 = [r for r in sub if abs(r[2]) < cut]
        m = len(s2); w = sum(r[3] for r in s2)
        print(f'  {lbl} {name:5s} n={m:5d} P(Up)={w/m:.4f}')
        out.setdefault('pup_realized_flat', {})[f'{lbl}_{name}'] = {'n': m, 'p_up': w/m}

json.dump(out, open(W + 'result_a_b.json', 'w'), indent=1)
print('\nsaved', W + 'result_a_b.json')
