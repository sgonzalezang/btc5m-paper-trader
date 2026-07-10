#!/usr/bin/env python3
"""(a) Book informativeness / calibration of early PM prices; (b) tie-rule pricing in flat regimes.
Data: pm_prices_sample.json (n=216, every 4th market over ~3d), pm_res_3d.json (n=863), cb5m.json.
Methodology: chronological 2/3 TRAIN / 1/3 TEST; block bootstrap with 1-hour blocks.
Outputs: calib_tie_results.json + printed tables.
"""
import json, math, random

S = '/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad'
W = S + '/work/microstructure'

pm  = json.load(open(S + '/data/pm_prices_sample.json'))   # dicts t0,up_won,p20,p60,p150,pLast
res = json.load(open(S + '/data/pm_res_3d.json'))          # [[t0, up_won],...]
cb  = json.load(open(S + '/data/cb5m.json'))                # columnar

# --- index coinbase 5m by t0 (seconds) ---
cbt, cbo, cbc = cb['t'], cb['o'], cb['c']
cbi = {int(t): i for i, t in enumerate(cbt)}

def prior_move_bps(t0):
    """buffered open-to-open prior move for interval starting at t0"""
    i = cbi.get(t0); j = cbi.get(t0 - 300)
    if i is None or j is None: return None
    return (cbo[i] - cbo[j]) / cbo[j] * 1e4

def own_move_bps(t0):
    i = cbi.get(t0)
    if i is None: return None
    return (cbc[i] - cbo[i]) / cbo[i] * 1e4

def quantiles(xs, qs=(0.1, 0.25, 0.5, 0.75, 0.9)):
    xs = sorted(xs); n = len(xs)
    out = {}
    for q in qs:
        if n == 0: out[q] = None; continue
        k = q * (n - 1); f = int(math.floor(k)); c = min(f + 1, n - 1)
        out[q] = xs[f] + (k - f) * (xs[c] - xs[f])
    return out

def block_boot_mean(pairs, blocksec, nboot=4000, seed=7):
    """pairs: list of (t0, x). Returns bootstrap dist of mean(x) resampling 1-h blocks."""
    blocks = {}
    for t0, x in pairs:
        blocks.setdefault(t0 // blocksec, []).append(x)
    bl = list(blocks.values()); B = len(bl)
    rng = random.Random(seed); means = []
    for _ in range(nboot):
        acc = []
        for _ in range(B):
            acc.extend(bl[rng.randrange(B)])
        means.append(sum(acc) / len(acc))
    means.sort()
    return means

def boot_p_greater(pairs, null, blocksec=3600, nboot=4000, seed=7):
    """two-sided p for mean != null via block bootstrap centered at observed mean"""
    m = sum(x for _, x in pairs) / len(pairs)
    dist = block_boot_mean(pairs, blocksec, nboot, seed)
    # p-value: fraction of bootstrap means on the other side of null, doubled (percentile method)
    lo = sum(1 for d in dist if d <= null) / len(dist)
    hi = sum(1 for d in dist if d >= null) / len(dist)
    return m, min(1.0, 2 * min(lo, hi)), (dist[int(0.025 * len(dist))], dist[int(0.975 * len(dist))])

results = {}

# ---------- (a) calibration of p20 / p60 / p150 ----------
pm.sort(key=lambda r: r['t0'])
n = len(pm); cut = pm[int(n * 2 / 3) - 1]['t0']
train = [r for r in pm if r['t0'] <= cut]; test = [r for r in pm if r['t0'] > cut]
print(f"pm sample n={n} train={len(train)} test={len(test)} cut_t0={cut}")

def calib_table(rows, field, edges=(0.0, 0.40, 0.45, 0.50, 0.55, 0.60, 1.001)):
    tab = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        sub = [r for r in rows if lo <= r[field] < hi]
        if not sub: tab.append((lo, hi, 0, None, None)); continue
        w = sum(r['up_won'] for r in sub)
        mp = sum(r[field] for r in sub) / len(sub)
        tab.append((lo, hi, len(sub), w / len(sub), mp))
    return tab

def brier(rows, field):
    return sum((r[field] - r['up_won']) ** 2 for r in rows) / len(rows)

for split, rows in (('TRAIN', train), ('TEST', test), ('ALL', pm)):
    print(f"\n== calibration {split} ==")
    for f in ('p20', 'p60', 'p150', 'pLast'):
        b = brier(rows, f)
        base = sum((0.5 - r['up_won']) ** 2 for r in rows) / len(rows)
        print(f"  {f}: brier={b:.4f} (0.5-const={base:.4f}) skill={1-b/base:+.3f}")
    print(f"  p20 buckets: (lo,hi,n,up_rate,mean_p)")
    for row in calib_table(rows, 'p20'):
        lo, hi, m, w, mp = row
        print(f"    [{lo:.2f},{hi:.2f}) n={m:3d} up_rate={'-' if w is None else f'{w:.3f}'} mean_p={'-' if mp is None else f'{mp:.3f}'}")

# favorite-longshot framing on p20: favorite = side priced > 0.5
def favlong(rows, field='p20'):
    out = []
    for r in rows:
        p = r[field]
        if p is None or abs(p - 0.5) < 1e-9: continue
        fav_up = p > 0.5
        pf = p if fav_up else 1 - p
        fav_won = r['up_won'] if fav_up else 1 - r['up_won']
        out.append((r['t0'], pf, fav_won))
    return out

for split, rows in (('TRAIN', train), ('TEST', test), ('ALL', pm)):
    fl = favlong(rows)
    edges = (0.5, 0.55, 0.60, 0.70, 1.001)
    print(f"\n== favorite-longshot {split} (p20 favorite) ==")
    for lo, hi in zip(edges[:-1], edges[1:]):
        sub = [(t, pf, fw) for t, pf, fw in fl if lo < pf <= hi]
        if not sub: continue
        wr = sum(fw for _, _, fw in sub) / len(sub)
        mp = sum(pf for _, pf, _ in sub) / len(sub)
        print(f"    fav_p in ({lo:.2f},{hi:.2f}] n={len(sub):3d} fav_win={wr:.3f} mean_p={mp:.3f} gap={wr-mp:+.3f}")

# residual edge of p20 overall: mean(up_won - p20)
for split, rows in (('TRAIN', train), ('TEST', test)):
    pairs = [(r['t0'], r['up_won'] - r['p20']) for r in rows]
    m, p, ci = boot_p_greater(pairs, 0.0)
    print(f"{split}: mean(up_won - p20) = {m:+.4f}  p={p:.3f} ci95=({ci[0]:+.4f},{ci[1]:+.4f})")
    results[f'up_minus_p20_{split}'] = {'mean': m, 'p': p, 'ci': ci, 'n': len(rows)}

# ---------- (b) tie rule / flat-regime pricing ----------
# base up rate on full 863 resolutions
pairs = [(t0, w) for t0, w in res]
m, p, ci = boot_p_greater(pairs, 0.5)
print(f"\nALL 863 resolutions: up_rate={m:.4f} vs 0.5 p={p:.3f} ci=({ci[0]:.4f},{ci[1]:.4f})")
results['up_rate_all'] = {'mean': m, 'p': p, 'ci': ci, 'n': len(pairs)}

# flat regime ex ante: prior interval |move| < 4 bps (also try <8)
res.sort(key=lambda r: r[0])
rcut = res[int(len(res) * 2 / 3) - 1][0]
for thr in (4.0, 8.0, 12.0):
    for split, lo_t, hi_t in (('TRAIN', 0, rcut), ('TEST', rcut, 1 << 60), ('ALL', 0, 1 << 60)):
        sub = []
        for t0, w in res:
            if not (lo_t < t0 <= hi_t): continue
            pm_bps = prior_move_bps(t0)
            if pm_bps is None or abs(pm_bps) >= thr: continue
            sub.append((t0, w))
        if len(sub) < 20:
            print(f"flat(prior<{thr}bps) {split}: n={len(sub)} (too small)"); continue
        m, p, ci = boot_p_greater(sub, 0.5)
        print(f"flat(prior<{thr}bps) {split}: n={len(sub)} up_rate={m:.4f} p={p:.3f} ci=({ci[0]:.4f},{ci[1]:.4f})")
        results[f'flat_up_rate_thr{thr}_{split}'] = {'mean': m, 'p': p, 'ci': ci, 'n': len(sub)}

# what does the book charge for Up in ex-ante flat intervals? (pm sample)
for thr in (4.0, 8.0):
    sub = [r for r in pm if (lambda b: b is not None and abs(b) < thr)(prior_move_bps(r['t0']))]
    if len(sub) < 15:
        print(f"book-in-flat thr={thr}: n={len(sub)} too small"); continue
    mp20 = sum(r['p20'] for r in sub) / len(sub)
    up = sum(r['up_won'] for r in sub) / len(sub)
    pairs = [(r['t0'], r['up_won'] - r['p20']) for r in sub]
    m, p, ci = boot_p_greater(pairs, 0.0)
    print(f"flat(prior<{thr}bps) pm-sample: n={len(sub)} mean_p20={mp20:.4f} up_rate={up:.4f} "
          f"mean(up-p20)={m:+.4f} p={p:.3f}")
    results[f'flat_book_thr{thr}'] = {'n': len(sub), 'mean_p20': mp20, 'up_rate': up, 'edge': m, 'p': p}

# near-50c books: up rate when p20 in [0.45,0.55]
for split, rows in (('TRAIN', train), ('TEST', test), ('ALL', pm)):
    sub = [r for r in rows if 0.45 <= r['p20'] <= 0.55]
    if len(sub) < 10: continue
    pairs = [(r['t0'], r['up_won'] - r['p20']) for r in sub]
    m, p, ci = boot_p_greater(pairs, 0.0)
    up = sum(r['up_won'] for r in sub) / len(sub)
    print(f"p20 in [.45,.55] {split}: n={len(sub)} up_rate={up:.4f} mean(up-p20)={m:+.4f} p={p:.3f}")
    results[f'near50_{split}'] = {'n': len(sub), 'up_rate': up, 'edge': m, 'p': p}

# exact-tie frequency on coinbase 60d (c == o) and sub-2bps share
tot = flat2 = ties = upn = 0
for i in range(len(cbt)):
    mv = (cbc[i] - cbo[i]) / cbo[i] * 1e4
    tot += 1
    if cbc[i] >= cbo[i]: upn += 1
    if abs(mv) < 2: flat2 += 1
    if cbc[i] == cbo[i]: ties += 1
print(f"\ncb5m 60d: n={tot} P(close>=open)={upn/tot:.4f} sub-2bps share={flat2/tot:.4f} exact ties={ties} ({ties/tot:.5f})")
results['cb60d'] = {'n': tot, 'p_up': upn / tot, 'sub2bps': flat2 / tot, 'ties': ties}

json.dump(results, open(W + '/calib_tie_results.json', 'w'), indent=1)
print('\nsaved', W + '/calib_tie_results.json')
