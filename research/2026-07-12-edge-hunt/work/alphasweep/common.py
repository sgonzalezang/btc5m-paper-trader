"""Common infrastructure for the 2026-07-12 alpha sweep (stdlib only).

Conventions (frozen):
- Interval i = 5m candle i in cb5m. Decision moment = t0 + entrySec (entrySec <= 45s),
  so any feature must be computable from data strictly available at t0 (+ the open print o[i]).
- Label: up_i = 1 if o[i+1] >= o[i] else 0  (open-to-open, ties -> Up, matches PM resolution
  convention via the validated Coinbase proxy; ~11% resolution noise below 2bps moves).
- Cost model (frozen): EV/share = q - p - 0.07*p*(1-p); gas $0.004/trade (~0.004c/share at
  100-share clip, included). Default realistic fill p = 0.51 (ask 50c + 1c slip) per brief.
- TRAIN: t0 < 2026-06-26 00:00 UTC. TEST: t0 >= that. Headline numbers TEST only.
- p-values: 1h-block bootstrap (block key = t0 // 3600), one-sided vs EV<=0.
"""
import json, math, random, calendar

DATA = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data"
DATA10 = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-10-edge-hunt/data"
SPLIT_TS = calendar.timegm((2026, 6, 26, 0, 0, 0))  # 1782345600

GAS_PER_SHARE = 0.004 / 100.0  # $50-class trade ~100 shares


def load_candles(path):
    d = json.load(open(path))
    return d


def cost(p):
    return p + 0.07 * p * (1 - p) + GAS_PER_SHARE


def ev_per_share(q, p):
    return q - cost(p)


def breakeven_q(p):
    return cost(p)


class Table:
    """Aligned per-interval feature table over cb5m."""

    def __init__(self):
        cb = load_candles(f"{DATA}/cb5m.json")
        self.t, self.o, self.h, self.l, self.c, self.v = (
            cb["t"], cb["o"], cb["h"], cb["l"], cb["c"], cb["v"])
        self.n = len(self.t)
        # label for interval i uses o[i+1]; last interval unlabeled
        self.up = [None] * self.n
        self.ret = [None] * self.n  # forward open-to-open return of interval i
        for i in range(self.n - 1):
            self.up[i] = 1 if self.o[i + 1] >= self.o[i] else 0
            self.ret[i] = (self.o[i + 1] - self.o[i]) / self.o[i]
        self.idx_of_t = {t: i for i, t in enumerate(self.t)}

    def prior_ret(self, i, k):
        """Open-to-open return over the k intervals ENDING at o[i] (known at t0)."""
        if i - k < 0:
            return None
        return (self.o[i] - self.o[i - k]) / self.o[i - k]

    def trailing_vol(self, i, w=36):
        """Std of 1-interval open-to-open returns over the w intervals ending at o[i]."""
        if i - w < 0:
            return None
        rs = [(self.o[j + 1] - self.o[j]) / self.o[j] for j in range(i - w, i)]
        m = sum(rs) / len(rs)
        return math.sqrt(sum((x - m) ** 2 for x in rs) / len(rs))

    def eff(self, i, k):
        """Kaufman efficiency of the k legs ending at o[i]."""
        if i - k < 0:
            return None
        denom = sum(abs(self.o[j + 1] - self.o[j]) for j in range(i - k, i))
        if denom <= 0:
            return 1.0
        return abs(self.o[i] - self.o[i - k]) / denom


def block_bootstrap(trades, reps=4000, seed=1234):
    """trades: list of (t0, ev_realized) where ev_realized = win - cost(p).
    Returns (mean, p_onesided_le0, ci90_lo, ci90_hi) via 1h-block resampling."""
    if not trades:
        return None, None, None, None
    blocks = {}
    for t0, ev in trades:
        blocks.setdefault(t0 // 3600, []).append(ev)
    keys = list(blocks.keys())
    nb = len(keys)
    ntr = len(trades)
    mean = sum(ev for _, ev in trades) / ntr
    rng = random.Random(seed)
    means = []
    for _ in range(reps):
        tot, cnt = 0.0, 0
        for _ in range(nb):
            b = blocks[keys[rng.randrange(nb)]]
            tot += sum(b)
            cnt += len(b)
        means.append(tot / cnt if cnt else 0.0)
    means.sort()
    p = sum(1 for m in means if m <= 0) / len(means)
    lo = means[int(0.05 * len(means))]
    hi = means[int(0.95 * len(means)) - 1]
    return mean, p, lo, hi


def eval_signal(tab, fire, reps=4000, p_fill=0.51):
    """fire: dict i -> side ('up'/'down') for intervals where the signal fires.
    Returns dict of TRAIN/TEST stats. EV realized per trade = 1{side wins} - cost(p_fill)."""
    out = {}
    for split in ("TRAIN", "TEST"):
        trades = []
        wins = 0
        for i, side in fire.items():
            if tab.up[i] is None:
                continue
            is_train = tab.t[i] < SPLIT_TS
            if (split == "TRAIN") != is_train:
                continue
            w = 1 if ((side == "up") == (tab.up[i] == 1)) else 0
            wins += w
            trades.append((tab.t[i], w - cost(p_fill)))
        n = len(trades)
        if n == 0:
            out[split] = {"n": 0}
            continue
        q = wins / n
        mean, p, lo, hi = block_bootstrap(trades, reps=reps)
        out[split] = {"n": n, "q": round(q, 4), "ev_c": round(mean * 100, 3),
                      "p_boot": round(p, 4), "ci90_c": [round(lo * 100, 3), round(hi * 100, 3)]}
    return out
