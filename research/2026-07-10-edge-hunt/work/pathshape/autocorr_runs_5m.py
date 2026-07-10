#!/usr/bin/env python3
"""cb5m 60d: (1) lag-k reversal rate vs move k back, conditioned on |move| bucket, k=1..6.
(2) runs analysis: after n=2..5 same-sign buffered moves, P(next tradable outcome continues),
conditioned on last-move magnitude. Buffered open-to-open moves; outcome = sign(c-o), tie Up.
TRAIN = first 2/3 (40d), TEST = last 1/3 (20d). Block bootstrap (1h) for key TRAIN claims."""
import json, random

S = '/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad/'
d = json.load(open(S + 'data/cb5m.json'))
t, o, c = d['t'], d['o'], d['c']
N = len(t)
# buffered moves: m[i] = move over interval i measured open-to-open (needs o[i+1])
m = [(o[i + 1] - o[i]) / o[i] for i in range(N - 1)]
out = [1 if c[i] >= o[i] else -1 for i in range(N)]  # tradable outcome, tie Up
sgn = lambda x: 1 if x > 0 else (-1 if x < 0 else 0)

split = t[0] + (t[-1] - t[0]) * 2 // 3
BUCK = [(0, 2), (2, 4), (4, 8), (8, 12), (12, 20), (20, 9e9)]

def bk(bps):
    for j, (a, b) in enumerate(BUCK):
        if a <= bps < b:
            return j
    return None

rr = lambda xs: sum(xs) / len(xs) if xs else float('nan')

print("=== lag-k reversal rate: P(out[i] != sign(m[i-k])) by |m[i-k]| bucket ===")
print("buckets(bps):", BUCK)
res = {}
for k in range(1, 7):
    for name, lo, hi in (('TRAIN', 0, split), ('TEST', split, 9e18)):
        cell = [[] for _ in BUCK]
        for i in range(k, N - 1):  # out[i] valid for i<N; m[i-k] needs i-k<N-1
            if not (lo <= t[i] < hi):
                continue
            pm = m[i - k]
            s = sgn(pm)
            if s == 0:
                continue
            cell[bk(abs(pm) * 1e4)].append(1 if out[i] != s else 0)
        res[(k, name)] = [(rr(x), len(x)) for x in cell]
    tr = res[(k, 'TRAIN')]; te = res[(k, 'TEST')]
    print(f"k={k} TRAIN " + " ".join(f"{r:.3f}/{n}" for r, n in tr))
    print(f"    TEST  " + " ".join(f"{r:.3f}/{n}" for r, n in te))

# block bootstrap for k=1, >=12bps bucket combined (12-20 + 20+), TRAIN: is revrate > 0.5?
def boot_rate(pairs, iters=3000, seed=3):
    """pairs = [(hourblock, rev)] ; bootstrap mean rate, p for rate<=0.5 (one-sided)."""
    rnd = random.Random(seed)
    blocks = {}
    for hb, r in pairs:
        blocks.setdefault(hb, []).append(r)
    keys = list(blocks.keys())
    obs = rr([r for _, r in pairs])
    cnt = tot = 0
    for _ in range(iters):
        s = []
        for _ in keys:
            s.extend(blocks[rnd.choice(keys)])
        tot += 1
        if rr(s) <= 0.5:
            cnt += 1
    return obs, cnt / tot

for k in (1, 2):
    for name, lo, hi in (('TRAIN', 0, split), ('TEST', split, 9e18)):
        pairs = []
        for i in range(k, N - 1):
            if not (lo <= t[i] < hi):
                continue
            pm = m[i - k]
            if abs(pm) >= 12e-4 and sgn(pm) != 0:
                pairs.append((t[i] // 3600, 1 if out[i] != sgn(pm) else 0))
        obs, p = boot_rate(pairs)
        print(f"k={k} |m|>=12bps {name}: revrate={obs:.4f} n={len(pairs)} block-boot P(rate<=0.5)={p:.4f}")

print("\n=== runs: after exactly n same-sign moves, P(out[i+1] continues) ===")
# run length ending at move index i: L[i]
L = [0] * (N - 1)
for i in range(N - 1):
    if sgn(m[i]) == 0:
        L[i] = 0
    elif i > 0 and sgn(m[i]) == sgn(m[i - 1]):
        L[i] = L[i - 1] + 1
    else:
        L[i] = 1

MAGB = [(0, 4), (4, 8), (8, 12), (12, 9e9)]
def mbk(bps):
    for j, (a, b) in enumerate(MAGB):
        if a <= bps < b:
            return j
    return None

runres = {}
for n_ in range(2, 6):
    for name, lo, hi in (('TRAIN', 0, split), ('TEST', split, 9e18)):
        cells = [[] for _ in MAGB]; allc = []
        for i in range(N - 1):
            # run of exactly n_ ends at move i; next tradable interval is i+1 (needs out[i+1], i+1<N)
            if L[i] != n_ or i + 1 >= N:
                continue
            if not (lo <= t[i + 1] < hi):
                continue
            cont = 1 if out[i + 1] == sgn(m[i]) else 0
            allc.append(cont)
            cells[mbk(abs(m[i]) * 1e4)].append(cont)
        runres[(n_, name)] = (rr(allc), len(allc), [(rr(x), len(x)) for x in cells])
    a = runres[(n_, 'TRAIN')]; b = runres[(n_, 'TEST')]
    print(f"n={n_} TRAIN all {a[0]:.3f}/{a[1]}  by|last|: " + " ".join(f"{r:.3f}/{m2}" for r, m2 in a[2]))
    print(f"     TEST  all {b[0]:.3f}/{b[1]}  by|last|: " + " ".join(f"{r:.3f}/{m2}" for r, m2 in b[2]))

# bootstrap: n=2 runs with last |move|>=12 TRAIN (does a 2-run kill/boost the reversal?)
for n_ in (2, 3):
    for name, lo, hi in (('TRAIN', 0, split), ('TEST', split, 9e18)):
        pairs = []
        for i in range(N - 1):
            if L[i] != n_ or i + 1 >= N or not (lo <= t[i + 1] < hi):
                continue
            if abs(m[i]) >= 12e-4:
                pairs.append((t[i + 1] // 3600, 1 if out[i + 1] != sgn(m[i]) else 0))
        if pairs:
            obs, p = boot_rate(pairs)
            print(f"run n={n_}, last|m|>=12bps {name}: REVERSAL rate={obs:.4f} n={len(pairs)} P(<=0.5)={p:.4f}")

json.dump({'lag': {f"{k}_{nm}": v for (k, nm), v in res.items()},
           'runs': {f"{k}_{nm}": v for (k, nm), v in runres.items()}},
          open(S + 'work/pathshape/autocorr_runs_results.json', 'w'), indent=1)
print("\nsaved -> work/pathshape/autocorr_runs_results.json")
