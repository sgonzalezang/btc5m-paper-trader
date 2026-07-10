#!/usr/bin/env python3
"""Prior-interval path shape as reversal predictor. cb1m (14d) joined to cb5m.

Buffered open-to-open construction per brief:
  prior move = (o5[T] - o5[T-300]) / o5[T-300]   (consecutive 5m opens, shared boundary)
  outcome    = sign(c5[T] - o5[T]), tie -> Up
Path shape of prior interval [T-300, T) from 1m opens at T-300..T-60 plus o1m[T]:
  legs l1..l5 (open-to-open 1m), net = o1m[T] - o1m[T-300]
Features (events = prior |move| >= 8bps):
  late_frac = |l5| / |net|
  nflips    = sign changes among consecutive nonzero legs (0=monotone drift, >=2=V/zigzag)
  wick      = (max h - min l) / |net|
  volspike  = vol(prior 5min) / (trailing-hour vol / 12)
Terciles fit on TRAIN (first 2/3 chronologically), applied to TEST (last 1/3).
Block bootstrap (1h blocks) for top-vs-bottom tercile diff on TRAIN.
"""
import json, math, random

S = '/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad/'
d1 = json.load(open(S + 'data/cb1m.json'))
d5 = json.load(open(S + 'data/cb5m.json'))

i1 = {t: k for k, t in enumerate(d1['t'])}
i5 = {t: k for k, t in enumerate(d5['t'])}
o1, h1, l1, v1 = d1['o'], d1['h'], d1['l'], d1['v']
o5, c5 = d5['o'], d5['c']

events = []  # each: dict with T, prevmove(bps), dirn, rev, features
t0, t1 = d1['t'][0], d1['t'][-1]
T = ((t0 // 300) + 1) * 300 + 300  # first boundary with a full prior 5m inside 1m data
misses = 0
while T + 300 <= t1 + 60:
    ok = (T in i5) and (T - 300 in i5) and all((T - 300 + 60 * j) in i1 for j in range(6))
    if ok:
        a, b = i5[T - 300], i5[T]
        pm = (o5[b] - o5[a]) / o5[a]
        out_up = 1 if c5[b] >= o5[b] else -1
        ks = [i1[T - 300 + 60 * j] for j in range(6)]
        opens = [o1[k] for k in ks]
        legs = [opens[j + 1] - opens[j] for j in range(5)]
        net = opens[5] - opens[0]
        hh = max(h1[k] for k in ks[:5]); ll = min(l1[k] for k in ks[:5])
        vol = sum(v1[k] for k in ks[:5])
        # trailing hour volume: 60 prior 1m candles ending at T-300
        tr = [i1.get(T - 300 - 60 * j) for j in range(1, 61)]
        volsp = None
        if all(x is not None for x in tr):
            base = sum(v1[x] for x in tr) / 12.0
            volsp = vol / base if base > 0 else None
        if abs(pm) >= 8e-4 and abs(net) > 1e-9:
            dirn = 1 if pm > 0 else -1
            rev = 1 if out_up != dirn else 0
            sg = [1 if x > 0 else -1 for x in legs if x != 0]
            nflips = sum(1 for j in range(1, len(sg)) if sg[j] != sg[j - 1])
            events.append(dict(T=T, pm_bps=pm * 1e4, rev=rev,
                               late=abs(legs[4]) / abs(net),
                               nflips=nflips,
                               wick=(hh - ll) / abs(net),
                               volsp=volsp))
    else:
        misses += 1
    T += 300

events.sort(key=lambda e: e['T'])
n = len(events)
cut = events[int(n * 2 / 3)]['T']
train = [e for e in events if e['T'] < cut]
test = [e for e in events if e['T'] >= cut]
print(f"total 5m boundaries missed (gaps): {misses}")
print(f"events |move|>=8bps: n={n}  train={len(train)}  test={len(test)}  split_T={cut}")
rr = lambda ev: (sum(e['rev'] for e in ev) / len(ev)) if ev else float('nan')
print(f"baseline rev rate  TRAIN {rr(train):.4f} (n={len(train)})  TEST {rr(test):.4f} (n={len(test)})")
tr12 = [e for e in train if abs(e['pm_bps']) >= 12]
te12 = [e for e in test if abs(e['pm_bps']) >= 12]
print(f">=12bps baseline   TRAIN {rr(tr12):.4f} (n={len(tr12)})  TEST {rr(te12):.4f} (n={len(te12)})")

def terciles(vals):
    s = sorted(vals); m = len(s)
    return s[m // 3], s[2 * m // 3]

def bucket3(x, q1, q2):
    return 0 if x <= q1 else (1 if x <= q2 else 2)

def block_boot_diff(ev_lo, ev_hi, iters=3000, seed=7):
    """Bootstrap diff rr(hi)-rr(lo) with 1h blocks; returns (diff, p_two_sided)."""
    rnd = random.Random(seed)
    blocks = {}
    for tag, ev in (('lo', ev_lo), ('hi', ev_hi)):
        for e in ev:
            blocks.setdefault(e['T'] // 3600, []).append((tag, e['rev']))
    keys = list(blocks.keys())
    obs = rr(ev_hi) - rr(ev_lo)
    cnt = 0; tot = 0
    for _ in range(iters):
        samp = [blocks[rnd.choice(keys)] for _ in keys]
        s = {'lo': [0, 0], 'hi': [0, 0]}
        for bl in samp:
            for tag, r in bl:
                s[tag][0] += r; s[tag][1] += 1
        if s['lo'][1] == 0 or s['hi'][1] == 0:
            continue
        d = s['hi'][0] / s['hi'][1] - s['lo'][0] / s['lo'][1]
        tot += 1
        if (d - obs) * (1 if obs >= 0 else -1) <= -abs(obs):  # centered null: |d-obs|>=|obs| on opposite side
            pass
        # simpler: count sign-flip of centered stat
        if abs(d - obs) >= abs(obs):
            cnt += 1
    return obs, (cnt / tot if tot else float('nan'))

results = {}
for feat in ['late', 'wick', 'volsp']:
    tr = [e for e in train if e[feat] is not None]
    te = [e for e in test if e[feat] is not None]
    q1, q2 = terciles([e[feat] for e in tr])
    rows = []
    for name, ev in (('TRAIN', tr), ('TEST', te)):
        bx = [[], [], []]
        for e in ev:
            bx[bucket3(e[feat], q1, q2)].append(e)
        rows.append([name] + [f"{rr(b):.4f}/{len(b)}" for b in bx])
    # bootstrap top vs bottom tercile on TRAIN
    b0 = [e for e in tr if bucket3(e[feat], q1, q2) == 0]
    b2 = [e for e in tr if bucket3(e[feat], q1, q2) == 2]
    diff, p = block_boot_diff(b0, b2)
    # test persistence
    t0_ = [e for e in te if bucket3(e[feat], q1, q2) == 0]
    t2_ = [e for e in te if bucket3(e[feat], q1, q2) == 2]
    tdiff = rr(t2_) - rr(t0_)
    results[feat] = dict(q1=q1, q2=q2, rows=rows, train_diff=diff, train_p=p, test_diff=tdiff,
                         test_n=(len(t0_), len(t2_)))
    print(f"\n[{feat}] tercile cuts (TRAIN): {q1:.4g} / {q2:.4g}")
    for r in rows:
        print(f"  {r[0]:5s}  T1 {r[1]}  T2 {r[2]}  T3 {r[3]}   (revrate/n)")
    print(f"  top-bottom diff TRAIN {diff:+.4f} (block-boot p={p:.4f})  TEST {tdiff:+.4f} (n={results[feat]['test_n']})")

# sign flips (categorical 0,1,>=2)
print("\n[nflips] monotone(0) / one-flip(1) / zigzag(>=2)")
for name, ev in (('TRAIN', train), ('TEST', test)):
    bx = [[], [], []]
    for e in ev:
        bx[min(e['nflips'], 2)].append(e)
    print(f"  {name:5s}  0: {rr(bx[0]):.4f}/{len(bx[0])}  1: {rr(bx[1]):.4f}/{len(bx[1])}  >=2: {rr(bx[2]):.4f}/{len(bx[2])}")
b0 = [e for e in train if e['nflips'] == 0]
b2 = [e for e in train if e['nflips'] >= 2]
diff, p = block_boot_diff(b0, b2)
t0_ = [e for e in test if e['nflips'] == 0]; t2_ = [e for e in test if e['nflips'] >= 2]
print(f"  zigzag-monotone diff TRAIN {diff:+.4f} (p={p:.4f})  TEST {rr(t2_)-rr(t0_):+.4f}")

json.dump({k: {kk: vv for kk, vv in v.items() if kk != 'rows'} for k, v in results.items()},
          open(S + 'work/pathshape/pathshape_1m_results.json', 'w'), indent=1)
print("\nsaved -> work/pathshape/pathshape_1m_results.json")
