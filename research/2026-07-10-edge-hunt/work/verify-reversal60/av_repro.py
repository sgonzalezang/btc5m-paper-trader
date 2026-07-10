#!/usr/bin/env python3
"""Adversarial verifier: independent reproduction of reversal60 best-spec headline.
Spec under attack: buffered |open-to-open prior move| >= 12bps on Coinbase 5m ->
buy other side, hold to resolution, headline at 51c fill.
Claimed: full n=4023 q=0.5334 | TRAIN(first 40d) n=2649 q=0.5228 | TEST(last 20d)
n=1374 q=0.5539, +0.0264/share at 51c, block-boot p vs 0.5 = 0.000, vs breakeven 0.025.
"""
import json, random, math

DATA = '/Users/sgonzalez/btc5m-paper-trader/research/2026-07-10-edge-hunt/data/cb5m.json'
d = json.load(open(DATA))
t, o, c = d['t'], d['o'], d['c']
n = len(t)

# integrity: spacing / gaps
gaps = [t[i+1]-t[i] for i in range(n-1)]
bad = [g for g in gaps if g != 300]
print('candles', n, 'span_days %.2f' % ((t[-1]-t[0])/86400), 'non-300s gaps:', len(bad), bad[:10])

THR = 0.0012
def fee(p): return 0.07*p*(1-p)
def qstar(p): return p + fee(p)

# build signals: at interval i (i>=1), prior move = (o[i]-o[i-1])/o[i-1]
# contrarian side wins if outcome opposes prior move sign; tie (c==o) resolves Up.
def build(thr):
    sig = []  # (t0, win, |move|)
    for i in range(1, n):
        if t[i]-t[i-1] != 300:   # candle gap: prior interval not truly adjacent
            continue
        mv = (o[i]-o[i-1])/o[i-1]
        if abs(mv) < thr: continue
        up = c[i] >= o[i]
        win = (not up) if mv > 0 else up   # fade: prior up -> buy Down
        sig.append((t[i], 1 if win else 0, abs(mv)))
    return sig

sig = build(THR)
t0 = t[0]
train = [s for s in sig if s[0]-t0 < 40*86400]
test  = [s for s in sig if s[0]-t0 >= 40*86400]

def stats(rows, p=0.51):
    if not rows: return {}
    q = sum(r[1] for r in rows)/len(rows)
    return {'n': len(rows), 'q': round(q,4), 'net_at_%dc'%int(p*100): round(q - p - fee(p),4)}

print('FULL ', stats(sig))
print('TRAIN', stats(train))
print('TEST ', stats(test))

# block bootstrap, 1-hour blocks (12 intervals): recentered one-sided p
# H0: q = null. Bootstrap dist of qb around obs; p = P(qb - obs >= obs - null).
def boot_p(rows, null, nboot=4000, seed=7):
    blocks = {}
    for ts, w, m in rows:
        blocks.setdefault(ts//3600, []).append(w)
    bl = list(blocks.values())
    rng = random.Random(seed)
    obs = sum(w for _,w,_ in rows)/len(rows)
    B = len(bl)
    hits = 0
    for _ in range(nboot):
        s = []
        for _ in range(B):
            s.extend(rng.choice(bl))
        qb = sum(s)/len(s)
        hits += 1 if (qb - obs) >= (obs - null) else 0
    return hits/nboot

for name, rows in (('TRAIN', train), ('TEST', test)):
    p05 = boot_p(rows, 0.5)
    pbe = boot_p(rows, qstar(0.51))
    print('%s block-boot one-sided p vs 0.5 = %.4f | vs q*(0.51)=%.4f -> p = %.4f'
          % (name, p05, qstar(0.51), pbe))

# walk-forward span days 10-60 at 51c
wf = [s for s in sig if s[0]-t0 >= 10*86400]
print('WF days10-60', stats(wf))

# move-size buckets on TRAIN/TEST
for name, rows in (('TRAIN', train), ('TEST', test)):
    small = [r for r in rows if r[2] < 0.0020]
    big   = [r for r in rows if r[2] >= 0.0020]
    print(name, '12-20bps', stats(small), '| 20+bps', stats(big))

json.dump({'full': stats(sig), 'train': stats(train), 'test': stats(test)},
          open('/Users/sgonzalez/btc5m-paper-trader/research/2026-07-10-edge-hunt/work/verify-reversal60/av_repro_out.json','w'), indent=1)
