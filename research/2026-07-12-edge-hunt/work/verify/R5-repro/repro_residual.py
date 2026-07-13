#!/usr/bin/env python3
"""
Independent reproduction of FINDING R5, leg 2: residual continuation.

Claim: after a >=2bps first-minute drift, the 5m interval closes in the drift
direction 72.1% of the time, but the REMAINING 4 minutes continue in that
direction only 48.7% (CI [.469,.506], n=2836; 45.7% at >=8bps), i.e. the
momentum trigger's hit rate is a mechanical head start, zero residual info.

Implementation from scratch on cb1m (Coinbase 1m, Jun 26 - Jul 13):
  price(t) = open of the 1m candle at t (strictly known at t; no look-ahead)
  drift1  = p(t0+60)/p(t0) - 1
  full    = sign(p(t0+300) - p(t0))   vs sign(drift1)
  resid   = sign(p(t0+300) - p(t0+60)) vs sign(drift1)
Ties (exact zero) excluded and counted. 1h-block bootstrap CIs.
Stress: (a) drop the single day most favorable to the claim (lowest residual
continuation), (b) split-half, (c) jitter theta, (d) fresh Jul 10-13 only.
"""
import json, random
from collections import defaultdict

DATA = '/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data/cb1m.json'
JUL10 = 1783641600  # 2026-07-10 00:00:00 UTC


def load_opens():
    d = json.load(open(DATA))
    return dict(zip(d['t'], d['o']))


def build_samples(opens, theta_bps):
    ts = sorted(opens)
    lo, hi = ts[0], ts[-1]
    t0 = lo + (-lo) % 300
    out = []  # (t0, full_cont or None, resid_cont or None)
    while t0 + 300 <= hi:
        a, b, c = opens.get(t0), opens.get(t0 + 60), opens.get(t0 + 300)
        t0 += 300
        s0 = t0 - 300
        if a is None or b is None or c is None:
            continue
        drift = (b - a) / a * 1e4
        if abs(drift) < theta_bps:
            continue
        sgn = 1 if drift > 0 else -1
        full = None if c == a else ((1 if c > a else -1) == sgn)
        resid = None if c == b else ((1 if c > b else -1) == sgn)
        out.append((s0, full, resid))
    return out


def rate(vals):
    vs = [v for v in vals if v is not None]
    return (sum(vs) / len(vs) if vs else None), len(vs)


def block_boot(samples, which, B=4000, seed=11):
    blocks = defaultdict(list)
    for s in samples:
        blocks[s[0] // 3600].append(s[which])
    keys = list(blocks.keys())
    rng = random.Random(seed)
    stats = []
    for _ in range(B):
        pool = []
        for _ in keys:
            pool.extend(blocks[rng.choice(keys)])
        r, _ = rate(pool)
        if r is not None:
            stats.append(r)
    stats.sort()
    return round(stats[int(.025 * len(stats))], 4), round(stats[int(.975 * len(stats))], 4)


def summarize(samples, boot=True):
    fr, fn = rate([s[1] for s in samples])
    rr, rn = rate([s[2] for s in samples])
    d = dict(n_full=fn, full=round(fr, 4) if fr is not None else None,
             n_resid=rn, resid=round(rr, 4) if rr is not None else None,
             ties_full=sum(1 for s in samples if s[1] is None),
             ties_resid=sum(1 for s in samples if s[2] is None))
    if boot and rn:
        d['resid_ci95'] = block_boot(samples, 2)
        d['full_ci95'] = block_boot(samples, 1)
    return d


def main():
    opens = load_opens()
    out = {}
    for th in (1, 2, 3, 4, 8):
        out[f'theta_{th}bps'] = summarize(build_samples(opens, th))

    s2 = build_samples(opens, 2)
    # fresh data replication
    out['fresh_jul10_13_theta2'] = summarize([s for s in s2 if s[0] >= JUL10])

    # stress a: drop single most claim-favorable day (lowest residual rate)
    bydays = defaultdict(list)
    for s in s2:
        bydays[s[0] // 86400].append(s)
    dayrates = {d: rate([x[2] for x in v])[0] for d, v in bydays.items()}
    worstday = min(dayrates, key=lambda d: dayrates[d])
    kept = [s for s in s2 if s[0] // 86400 != worstday]
    out['stress_drop_best_day'] = dict(
        dropped_day_utc=str(worstday * 86400),
        dropped_day_resid=round(dayrates[worstday], 4),
        **summarize(kept))

    # stress b: split halves
    s2s = sorted(s2)
    h = len(s2s) // 2
    out['stress_first_half'] = summarize(s2s[:h])
    out['stress_second_half'] = summarize(s2s[h:])

    # stress c: random half (seeded)
    rng = random.Random(3)
    half = rng.sample(s2s, h)
    out['stress_random_half'] = summarize(half)

    json.dump(out, open('residual_results.json', 'w'), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == '__main__':
    main()
