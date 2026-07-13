"""Shared helpers for regime & temporal structure analyses (stdlib only).

Conventions (frozen, from FINAL-DESIGN v3 + bot code):
- Buffered open-to-open moves: r[i] = (o[i+1]-o[i])/o[i] for interval i (t0 = t[i]).
  Interval i resolves UP iff o[i+1] >= o[i] (tie -> Up, matches Polymarket tie rule).
- Trigger for the contrarian family: |r[i-1]| >= 12 bps (the just-completed interval).
  Fade side = opposite of sign(r[i-1]). Win = resolution opposite to prior move
  (fading an UP move loses ties, fading a DOWN move wins ties -- asymmetry kept).
- eff6 (trigger-INCLUSIVE): over intervals i-6 .. i-1,
  eff6 = |prod(1+r)-1| / sum|r|  (den==0 -> 1.0).
- cnt12 (trigger-EXCLUSIVE): count of |r[j]| >= 12bps for j = i-13 .. i-2.
- eff12 (latentfire form, trigger-inclusive): over intervals i-12 .. i-1.
- Cost model: EV/share = q - p - 0.07*p*(1-p). Standard fill p = 0.51
  (pm_prices_sample p20 median .495 + 1c slip). Breakeven q*(0.51) = 0.527493.
- TRAIN: t0 < 2026-06-26 00:00 UTC (1782432000). TEST: t0 >= that.
- Block bootstrap: 1h blocks = 12 consecutive intervals.
"""
import json, math, random, calendar

DATA = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data"
DATA10 = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-10-edge-hunt/data"
TEST_START = 1782432000          # 2026-06-26 00:00 UTC
FRESH_START = 1783685700         # 2026-07-10 11:55 UTC (first t0 after prior round's data end)
FEE = 0.07
P_FILL = 0.51
BREAKEVEN = P_FILL + FEE * P_FILL * (1 - P_FILL)   # 0.527493


def load_cb5m():
    d = json.load(open(f"{DATA}/cb5m.json"))
    return d["t"], d["o"]


def build_series(t, o):
    """Return (t0s, r, up) for intervals 0..n-2.
    r[i] = open-to-open move of interval i; up[i] = resolves Up (tie->Up)."""
    n = len(t)
    t0s, r, up = [], [], []
    for i in range(n - 1):
        if t[i + 1] - t[i] != 300:   # only contiguous intervals (gap hist says all are)
            continue
        t0s.append(t[i])
        m = (o[i + 1] - o[i]) / o[i]
        r.append(m)
        up.append(o[i + 1] >= o[i])
    return t0s, r, up


def eff(rs):
    den = sum(abs(x) for x in rs)
    if den == 0:
        return 1.0
    net = 1.0
    for x in rs:
        net *= (1.0 + x)
    return abs(net - 1.0) / den


def ev_cents(q, p=P_FILL):
    """EV per share in cents at fill price p with true win prob q, frozen model."""
    return 100.0 * (q - p - FEE * p * (1 - p))


def wilson_or_binom_p(w, n, p0=0.5):
    """Two-sided normal-approx binomial p-value vs p0."""
    if n == 0:
        return 1.0
    se = math.sqrt(p0 * (1 - p0) / n)
    z = (w / n - p0) / se
    return 2 * (1 - phi(abs(z)))


def phi(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def block_boot_mean(vals, blocks_of, B=4000, seed=1234):
    """1h-block bootstrap for the mean of a per-interval value series.
    vals: list of (block_id, value). Resamples block ids with replacement.
    Returns (mean, lo95, hi95, p_le_0) where p_le_0 = P(boot mean <= 0)."""
    from collections import defaultdict
    by = defaultdict(list)
    for b, v in vals:
        by[b].append(v)
    bids = list(by.keys())
    if not bids:
        return None, None, None, None
    rng = random.Random(seed)
    obs = sum(v for _, v in vals) / len(vals)
    means = []
    nb = len(bids)
    for _ in range(B):
        tot, cnt = 0.0, 0
        for _ in range(nb):
            b = bids[rng.randrange(nb)]
            for v in by[b]:
                tot += v
                cnt += 1
        if cnt:
            means.append(tot / cnt)
    means.sort()
    lo = means[int(0.025 * len(means))]
    hi = means[int(0.975 * len(means))]
    p_le = sum(1 for m in means if m <= 0) / len(means)
    return obs, lo, hi, p_le


def block_boot_diff(vals_a, vals_b, B=4000, seed=99):
    """Block bootstrap for mean(a) - mean(b), items are (block_id, value).
    Blocks resampled jointly (same block universe) to respect shared time.
    Returns (obs_diff, lo95, hi95, p_le_0)."""
    from collections import defaultdict
    A, Bb = defaultdict(list), defaultdict(list)
    for b, v in vals_a:
        A[b].append(v)
    for b, v in vals_b:
        Bb[b].append(v)
    bids = sorted(set(A) | set(Bb))
    if not bids or not vals_a or not vals_b:
        return None, None, None, None
    rng = random.Random(seed)
    obs = sum(v for _, v in vals_a) / len(vals_a) - sum(v for _, v in vals_b) / len(vals_b)
    diffs = []
    nb = len(bids)
    for _ in range(B):
        ta = tb = 0.0
        ca = cb = 0
        for _ in range(nb):
            b = bids[rng.randrange(nb)]
            for v in A.get(b, ()):
                ta += v; ca += 1
            for v in Bb.get(b, ()):
                tb += v; cb += 1
        if ca and cb:
            diffs.append(ta / ca - tb / cb)
    diffs.sort()
    lo = diffs[int(0.025 * len(diffs))]
    hi = diffs[int(0.975 * len(diffs))]
    p_le = sum(1 for d in diffs if d <= 0) / len(diffs)
    return obs, lo, hi, p_le


def hour_block(t0):
    return t0 // 3600


def split_label(t0):
    return "TEST" if t0 >= TEST_START else "TRAIN"
