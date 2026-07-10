"""Shared lib: load candles, EWMA vol, FV model, block bootstrap. stdlib only."""
import json, math, random

SC = '/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad'
DATA = SC + '/data'

def phi(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2)))

def load_candles(name):
    d = json.load(open(f'{DATA}/{name}.json'))
    return d  # columnar t,o,h,l,c,v ascending

def cb5m_series():
    d = load_candles('cb5m')
    t, o, c = d['t'], d['o'], d['c']
    # intra-interval log return (what FV needs the distribution of)
    r = [math.log(c[i] / o[i]) for i in range(len(t))]
    up = [1 if c[i] >= o[i] else 0 for i in range(len(t))]
    return t, o, c, r, up

def ewma_sigma(t, r, lam, warmup=50):
    """sigma[i] = forecast std of r[i] using r[0..i-1]. sigma[i]=None during warmup."""
    n = len(r)
    sig2 = [None] * n
    # initialize with variance of first `warmup` returns
    v0 = sum(x * x for x in r[:warmup]) / warmup
    s = v0
    for i in range(1, n):
        s = lam * s + (1 - lam) * r[i - 1] ** 2
        if i >= warmup:
            sig2[i] = s
    return [None if v is None else math.sqrt(v) for v in sig2]

def qmle_loss(r, sig, lo, hi, t):
    """Gaussian QMLE loss sum(ln sig^2 + r^2/sig^2) over t in [lo,hi)."""
    L, n = 0.0, 0
    for i in range(len(r)):
        if sig[i] is None or not (lo <= t[i] < hi):
            continue
        v = sig[i] ** 2
        L += math.log(v) + r[i] ** 2 / v
        n += 1
    return L / max(1, n), n

def block_bootstrap_pvalue(vals, block=12, B=2000, seed=7):
    """Two-sided p-value that mean(vals) != 0 via circular block bootstrap of centered vals."""
    n = len(vals)
    if n < block * 2:
        return None
    m = sum(vals) / n
    cent = [v - m for v in vals]
    rng = random.Random(seed)
    nb = (n + block - 1) // block
    cnt = 0
    for _ in range(B):
        s = 0.0
        for _ in range(nb):
            st = rng.randrange(n)
            for k in range(block):
                s += cent[(st + k) % n]
        bm = s / (nb * block)
        if abs(bm) >= abs(m):
            cnt += 1
    return (cnt + 1) / (B + 1)

def fee(p):
    return 0.07 * p * (1 - p)

def breakeven(p):
    return p + fee(p)
