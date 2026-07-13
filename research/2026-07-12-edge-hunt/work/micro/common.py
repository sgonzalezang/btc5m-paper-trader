"""Shared helpers for execution-microstructure analyses (2026-07-12 edge hunt).

Frozen cost model: EV/share = q - p - 0.07*p*(1-p); p = fill price (entry, already ask+1c).
Realized per-share EV for a settled trade: w - entry - fee(entry), w in {0,1}.
Gas $0.004/trade ~ 0.004c/share at ~100sh -> ignored in per-share numbers (noted).
"""
import json, math, random, collections

DATA = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data"
DATA10 = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-10-edge-hunt/data"

REV_FAMILY = {"reversal", "reversal2", "latentfire", "reversal_v2", "impulse50", "impulse_v2"}
MOM_FAMILY = {"loose", "floor", "band", "value", "fade", "strict", "capless", "calm"}
V3_START = 1783695600  # 2026-07-10 15:00:00 UTC approx v3 cutover (impulse era)


def fee(p):
    return 0.07 * p * (1.0 - p)


def load_trades():
    t = json.load(open(f"{DATA}/trades_unified.json"))
    out = []
    for x in t:
        if x.get("status") != "settled" or x.get("result") not in ("win", "loss"):
            continue
        w = 1.0 if x["result"] == "win" else 0.0
        p = x["entry"]
        x["_w"] = w
        x["_evps"] = w - p - fee(p)  # realized net EV/share, frozen model
        x["_fam"] = "rev" if x["eng"] in REV_FAMILY else "mom"
        x["_blk"] = x["t0"] // 3600
        out.append(x)
    return out


def load_candles(path):
    d = json.load(open(path))
    return d


def candle_open_map(d):
    return dict(zip(d["t"], d["o"]))


def mean(v):
    return sum(v) / len(v) if v else float("nan")


def block_boot_mean(vals, blks, reps=4000, seed=7):
    """1h-block bootstrap of the mean. vals/blks parallel lists. Returns (mean, lo95, hi95, p_le_0)."""
    groups = collections.defaultdict(list)
    for v, b in zip(vals, blks):
        groups[b].append(v)
    keys = list(groups.keys())
    rng = random.Random(seed)
    n = len(keys)
    ms = []
    for _ in range(reps):
        s, c = 0.0, 0
        for _ in range(n):
            g = groups[keys[rng.randrange(n)]]
            s += sum(g)
            c += len(g)
        ms.append(s / c)
    ms.sort()
    m = mean(vals)
    lo = ms[int(0.025 * reps)]
    hi = ms[int(0.975 * reps) - 1]
    p_le0 = sum(1 for x in ms if x <= 0) / reps
    return m, lo, hi, p_le0


def block_boot_diff(vals_a, blks_a, vals_b, blks_b, reps=4000, seed=7):
    """Bootstrap CI/p for mean(A) - mean(B), resampling 1h blocks jointly (paired by hour where
    both exist; blocks are the union of hours, each resampled hour contributes its A and B trades)."""
    ga = collections.defaultdict(list)
    gb = collections.defaultdict(list)
    for v, b in zip(vals_a, blks_a):
        ga[b].append(v)
    for v, b in zip(vals_b, blks_b):
        gb[b].append(v)
    keys = list(set(ga) | set(gb))
    rng = random.Random(seed)
    n = len(keys)
    ds = []
    for _ in range(reps):
        sa = ca = sb = cb = 0.0
        for _ in range(n):
            k = keys[rng.randrange(n)]
            for v in ga.get(k, ()):
                sa += v; ca += 1
            for v in gb.get(k, ()):
                sb += v; cb += 1
        if ca == 0 or cb == 0:
            continue
        ds.append(sa / ca - sb / cb)
    ds.sort()
    d = mean(vals_a) - mean(vals_b)
    if not ds:
        return d, float("nan"), float("nan"), float("nan")
    r = len(ds)
    lo = ds[int(0.025 * r)]
    hi = ds[min(int(0.975 * r), r - 1)]
    p_le0 = sum(1 for x in ds if x <= 0) / r
    return d, lo, hi, p_le0


def fmt_c(x):
    return f"{100*x:+.2f}c"
