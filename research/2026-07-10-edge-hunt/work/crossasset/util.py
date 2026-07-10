"""Shared utilities for cross-asset lead-lag tests. stdlib only."""
import json, math, random

DATA = "/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad/data/"

def load(name):
    return json.load(open(DATA + name + ".json"))

def prior_oo(o):
    """Buffered open-to-open prior move for interval i: (o[i]-o[i-1])/o[i-1].
    Index 0 gets None."""
    out = [None] * len(o)
    for i in range(1, len(o)):
        out[i] = (o[i] - o[i - 1]) / o[i - 1]
    return out

def outcomes(o, c):
    """1 if interval resolves Up (c >= o, ties Up) else 0."""
    return [1 if c[i] >= o[i] else 0 for i in range(len(o))]

def split_idx(n, frac=2.0 / 3.0):
    return int(n * frac)

def rate(events):
    """events: list of 0/1. Returns (k, n, rate)."""
    n = len(events)
    k = sum(events)
    return k, n, (k / n if n else float("nan"))

def block_bootstrap_p(indicator_pairs, n_total, block=12, B=4000, null=0.5, seed=1234):
    """indicator_pairs: dict {interval_index: hit(0/1)} for selected events.
    Resamples the timeline in `block`-interval blocks with replacement,
    recomputes the hit rate over selected events falling inside sampled blocks.
    Returns (obs_rate, n_events, two-sided p vs null, boot 2.5/97.5 pct)."""
    rng = random.Random(seed)
    idxs = sorted(indicator_pairs)
    if not idxs:
        return float("nan"), 0, float("nan"), (float("nan"), float("nan"))
    obs = sum(indicator_pairs[i] for i in idxs) / len(idxs)
    nblocks = (n_total + block - 1) // block
    # precompute events per block
    per_block = {}
    for i in idxs:
        per_block.setdefault(i // block, []).append(indicator_pairs[i])
    block_ids = list(range(nblocks))
    rates = []
    for _ in range(B):
        k = n = 0
        for _ in range(nblocks):
            b = block_ids[rng.randrange(nblocks)]
            ev = per_block.get(b)
            if ev:
                k += sum(ev)
                n += len(ev)
        if n:
            rates.append(k / n)
    rates.sort()
    m = len(rates)
    if not m:
        return obs, len(idxs), float("nan"), (float("nan"), float("nan"))
    lo = rates[int(0.025 * m)]
    hi = rates[min(m - 1, int(0.975 * m))]
    below = sum(1 for r in rates if r <= null) / m
    above = sum(1 for r in rates if r >= null) / m
    p = 2 * min(below, above)
    return obs, len(idxs), min(p, 1.0), (lo, hi)

def fee(p):
    return 0.07 * p * (1 - p)

def qstar(p):
    """Break-even win prob at fill price p."""
    return p + fee(p)

def ev(q, p):
    """EV per share holding to resolution."""
    return q - p - fee(p)

def pct(xs, q):
    xs = sorted(xs)
    if not xs:
        return float("nan")
    k = (len(xs) - 1) * q
    f = int(k)
    c = min(f + 1, len(xs) - 1)
    return xs[f] + (xs[c] - xs[f]) * (k - f)
