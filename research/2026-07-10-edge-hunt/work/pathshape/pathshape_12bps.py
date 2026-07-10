#!/usr/bin/env python3
"""Shape features WITHIN the >=12bps trigger set (the actual reversal-engine universe).
Also signed late fraction (late leg in move direction vs against).
Same construction as pathshape_1m.py."""
import json, random

S = '/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad/'
d1 = json.load(open(S + 'data/cb1m.json'))
d5 = json.load(open(S + 'data/cb5m.json'))
i1 = {t: k for k, t in enumerate(d1['t'])}
i5 = {t: k for k, t in enumerate(d5['t'])}
o1, h1, l1, v1 = d1['o'], d1['h'], d1['l'], d1['v']
o5, c5 = d5['o'], d5['c']

events = []
t0, t1 = d1['t'][0], d1['t'][-1]
T = ((t0 // 300) + 1) * 300 + 300
while T + 300 <= t1 + 60:
    if (T in i5) and (T - 300 in i5) and all((T - 300 + 60 * j) in i1 for j in range(6)):
        a, b = i5[T - 300], i5[T]
        pm = (o5[b] - o5[a]) / o5[a]
        out_up = 1 if c5[b] >= o5[b] else -1
        ks = [i1[T - 300 + 60 * j] for j in range(6)]
        opens = [o1[k] for k in ks]
        legs = [opens[j + 1] - opens[j] for j in range(5)]
        net = opens[5] - opens[0]
        hh = max(h1[k] for k in ks[:5]); ll = min(l1[k] for k in ks[:5])
        tr = [i1.get(T - 300 - 60 * j) for j in range(1, 61)]
        volsp = None
        if all(x is not None for x in tr):
            base = sum(v1[x] for x in tr) / 12.0
            volsp = sum(v1[k] for k in ks[:5]) / base if base > 0 else None
        if abs(pm) >= 12e-4 and abs(net) > 1e-9:
            dirn = 1 if pm > 0 else -1
            sg = [1 if x > 0 else -1 for x in legs if x != 0]
            events.append(dict(T=T, rev=1 if out_up != dirn else 0,
                               late=abs(legs[4]) / abs(net),
                               slate=(legs[4] * dirn) / abs(net),
                               nflips=sum(1 for j in range(1, len(sg)) if sg[j] != sg[j - 1]),
                               wick=(hh - ll) / abs(net),
                               volsp=volsp))
    T += 300

events.sort(key=lambda e: e['T'])
cutT = 1783315800  # same split as pathshape_1m.py
train = [e for e in events if e['T'] < cutT]
test = [e for e in events if e['T'] >= cutT]
rr = lambda ev: (sum(e['rev'] for e in ev) / len(ev)) if ev else float('nan')
print(f">=12bps events: train={len(train)} test={len(test)}")
print(f"baseline TRAIN {rr(train):.4f}  TEST {rr(test):.4f}")

def terciles(vals):
    s = sorted(vals); m = len(s)
    return s[m // 3], s[2 * m // 3]

def bucket3(x, q1, q2):
    return 0 if x <= q1 else (1 if x <= q2 else 2)

def block_boot_diff(ev_lo, ev_hi, iters=3000, seed=11):
    rnd = random.Random(seed)
    blocks = {}
    for tag, ev in (('lo', ev_lo), ('hi', ev_hi)):
        for e in ev:
            blocks.setdefault(e['T'] // 3600, []).append((tag, e['rev']))
    keys = list(blocks.keys())
    obs = rr(ev_hi) - rr(ev_lo)
    cnt = tot = 0
    for _ in range(iters):
        s = {'lo': [0, 0], 'hi': [0, 0]}
        for bl in (blocks[rnd.choice(keys)] for _ in keys):
            for tag, r in bl:
                s[tag][0] += r; s[tag][1] += 1
        if s['lo'][1] == 0 or s['hi'][1] == 0:
            continue
        d = s['hi'][0] / s['hi'][1] - s['lo'][0] / s['lo'][1]
        tot += 1
        if abs(d - obs) >= abs(obs):
            cnt += 1
    return obs, (cnt / tot if tot else float('nan'))

out = {}
for feat in ['late', 'slate', 'wick', 'volsp']:
    tr = [e for e in train if e[feat] is not None]
    te = [e for e in test if e[feat] is not None]
    q1, q2 = terciles([e[feat] for e in tr])
    print(f"\n[{feat}] cuts {q1:.4g}/{q2:.4g}")
    for name, ev in (('TRAIN', tr), ('TEST', te)):
        bx = [[], [], []]
        for e in ev:
            bx[bucket3(e[feat], q1, q2)].append(e)
        print(f"  {name:5s}  T1 {rr(bx[0]):.4f}/{len(bx[0])}  T2 {rr(bx[1]):.4f}/{len(bx[1])}  T3 {rr(bx[2]):.4f}/{len(bx[2])}")
    b0 = [e for e in tr if bucket3(e[feat], q1, q2) == 0]
    b2 = [e for e in tr if bucket3(e[feat], q1, q2) == 2]
    diff, p = block_boot_diff(b0, b2)
    t0_ = [e for e in te if bucket3(e[feat], q1, q2) == 0]
    t2_ = [e for e in te if bucket3(e[feat], q1, q2) == 2]
    print(f"  top-bottom TRAIN {diff:+.4f} (p={p:.4f})  TEST {rr(t2_)-rr(t0_):+.4f}")
    out[feat] = dict(cuts=[q1, q2], train_diff=diff, train_p=p, test_diff=rr(t2_) - rr(t0_))

print("\n[nflips] within >=12bps")
for name, ev in (('TRAIN', train), ('TEST', test)):
    bx = [[], [], []]
    for e in ev:
        bx[min(e['nflips'], 2)].append(e)
    print(f"  {name:5s}  0: {rr(bx[0]):.4f}/{len(bx[0])}  1: {rr(bx[1]):.4f}/{len(bx[1])}  >=2: {rr(bx[2]):.4f}/{len(bx[2])}")

json.dump(out, open(S + 'work/pathshape/pathshape_12bps_results.json', 'w'), indent=1)
print("\nsaved -> work/pathshape/pathshape_12bps_results.json")
