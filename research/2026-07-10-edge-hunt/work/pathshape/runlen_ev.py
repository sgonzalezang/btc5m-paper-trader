#!/usr/bin/env python3
"""Does run-length of the prior same-sign streak modulate the lag-1 reversal (|m|>=12bps)?
L==1 (fresh move) vs L>=2 (extended streak). Plus fee-adjusted EV at realistic fills."""
import json, random

S = '/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad/'
d = json.load(open(S + 'data/cb5m.json'))
t, o, c = d['t'], d['o'], d['c']
N = len(t)
m = [(o[i + 1] - o[i]) / o[i] for i in range(N - 1)]
out = [1 if c[i] >= o[i] else -1 for i in range(N)]
sgn = lambda x: 1 if x > 0 else (-1 if x < 0 else 0)
split = t[0] + (t[-1] - t[0]) * 2 // 3
L = [0] * (N - 1)
for i in range(N - 1):
    s = sgn(m[i])
    L[i] = 0 if s == 0 else (L[i - 1] + 1 if i > 0 and s == sgn(m[i - 1]) else 1)
rr = lambda xs: sum(xs) / len(xs) if xs else float('nan')

def boot_diff(pa, pb, iters=3000, seed=5):
    rnd = random.Random(seed)
    blocks = {}
    for tag, pairs in (('a', pa), ('b', pb)):
        for hb, r in pairs:
            blocks.setdefault(hb, []).append((tag, r))
    keys = list(blocks.keys())
    obs = rr([r for _, r in pb]) - rr([r for _, r in pa])
    cnt = tot = 0
    for _ in range(iters):
        s = {'a': [], 'b': []}
        for _ in keys:
            for tag, r in blocks[rnd.choice(keys)]:
                s[tag].append(r)
        if not s['a'] or not s['b']:
            continue
        tot += 1
        if abs(rr(s['b']) - rr(s['a']) - obs) >= abs(obs):
            cnt += 1
    return obs, cnt / tot

for name, lo, hi in (('TRAIN', 0, split), ('TEST', split, 9e18)):
    fresh, ext = [], []
    for i in range(N - 1):
        if i + 1 >= N or not (lo <= t[i + 1] < hi) or abs(m[i]) < 12e-4:
            continue
        rev = 1 if out[i + 1] != sgn(m[i]) else 0
        (fresh if L[i] == 1 else ext).append((t[i + 1] // 3600, rev))
    dv, p = boot_diff(fresh, ext)
    print(f"{name}: L==1 rev={rr([r for _,r in fresh]):.4f}/{len(fresh)}  "
          f"L>=2 rev={rr([r for _,r in ext]):.4f}/{len(ext)}  diff={dv:+.4f} p={p:.4f}")

# pooled 60d lag-1 reversal rates and EV at realistic fills
for name, lo, hi in (('TRAIN', 0, split), ('TEST', split, 9e18), ('ALL60d', 0, 9e18)):
    xs = []
    for i in range(N - 1):
        if i + 1 >= N or not (lo <= t[i + 1] < hi) or abs(m[i]) < 12e-4:
            continue
        xs.append(1 if out[i + 1] != sgn(m[i]) else 0)
    q = rr(xs)
    for p_ in (0.51, 0.53, 0.55):
        ev = q - p_ - 0.07 * p_ * (1 - p_)
        print(f"{name} q={q:.4f} n={len(xs)}  fill={p_:.2f}  EV/share={ev:+.4f}  ret/$={ev/p_:+.4f}")
