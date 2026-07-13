"""Shared loaders + stats for the pricing/calibration dimension. stdlib only."""
import json, math, random, os

DATA12 = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data"
DATA10 = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-10-edge-hunt/data"
BOT    = "/Users/sgonzalez/btc5m-paper-trader/bot"

FEE = 0.07
V3_CUT = 1783698300  # 2026-07-10 15:05 UTC (v3 era start, momentum family retired)
PRERESET_END = 1783562400  # 2026-07-08 ~10:00 UTC (reset; signals.log starts 10:40)

CONTRARIAN = {"fade", "reversal", "reversal2", "reversal_v2", "latentfire",
              "impulse_v2", "impulse50"}

def ev_share(p, q):
    """Frozen cost model EV/share at fill price p, win prob q."""
    return q - p - FEE * p * (1 - p)

def qstar(p):
    return p + FEE * p * (1 - p)

def load_trades():
    return json.load(open(os.path.join(DATA12, "trades_unified.json")))

def load_state():
    return json.load(open(os.path.join(DATA12, "state_extract.json")))

def load_candles(name, base=DATA12):
    d = json.load(open(os.path.join(base, name)))
    return d

def load_pm_res():
    return json.load(open(os.path.join(DATA10, "pm_res_3d.json")))

def load_pm_prices():
    return json.load(open(os.path.join(DATA10, "pm_prices_sample.json")))

def load_signals():
    out = []
    with open(os.path.join(BOT, "signals.log")) as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out

def resolution_map():
    """t0 -> up(0/1) from actual Polymarket resolutions.
    Sources: pm_res_3d (harvested) + ledger settles with settledBy polymarket.
    Returns (map, n_conflicts)."""
    res = {}
    conflicts = 0
    for t0, up in load_pm_res():
        res[t0] = up
    for tr in load_trades():
        if tr.get("status") != "settled":
            continue
        sb = tr.get("settledBy") or ""
        if not sb.startswith("polymarket"):
            continue
        r = tr.get("result")
        if r not in ("win", "loss"):
            continue
        up = 1 if ((tr["side"] == "up") == (r == "win")) else 0
        t0 = tr["t0"]
        if t0 in res and res[t0] != up:
            conflicts += 1
        res[t0] = up  # ledger (fresher/corrected) wins
    return res, conflicts

def cb5m_map(base=DATA12):
    """t0 -> dict(o,h,l,c,v) from Coinbase 5m."""
    d = load_candles("cb5m.json", base)
    return {d["t"][i]: dict(o=d["o"][i], h=d["h"][i], l=d["l"][i],
                            c=d["c"][i], v=d["v"][i]) for i in range(len(d["t"]))}

def wilson(w, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"), float("nan"))
    ph = w / n
    den = 1 + z * z / n
    ctr = (ph + z * z / (2 * n)) / den
    hw = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / den
    return (ph, ctr - hw, ctr + hw)

def two_prop_z(w1, n1, w2, n2):
    if n1 == 0 or n2 == 0:
        return float("nan"), float("nan")
    p1, p2 = w1 / n1, w2 / n2
    p = (w1 + w2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    if se == 0:
        return float("nan"), float("nan")
    z = (p1 - p2) / se
    pv = 2 * (1 - norm_cdf(abs(z)))
    return z, pv

def norm_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))

def block_boot_mean(pairs, nboot=4000, block_s=3600, seed=7):
    """pairs = [(t0, value)]; 1h-block bootstrap of the mean.
    Returns (mean, lo95, hi95, p_le_0 one-sided prob mean<=0)."""
    if not pairs:
        return None
    rng = random.Random(seed)
    blocks = {}
    for t0, v in pairs:
        blocks.setdefault(t0 // block_s, []).append(v)
    keys = list(blocks.keys())
    B = len(keys)
    mu = sum(v for _, v in pairs) / len(pairs)
    means = []
    for _ in range(nboot):
        s, n = 0.0, 0
        for _ in range(B):
            k = keys[rng.randrange(B)]
            s += sum(blocks[k]); n += len(blocks[k])
        if n:
            means.append(s / n)
    means.sort()
    lo = means[int(0.025 * len(means))]
    hi = means[int(0.975 * len(means))]
    p_le0 = sum(1 for m in means if m <= 0) / len(means)
    return dict(mean=mu, lo95=lo, hi95=hi, p_le_0=p_le0, n=len(pairs), blocks=B)

def block_boot_diff(pairs_a, pairs_b, nboot=4000, block_s=3600, seed=7):
    """Difference of means A-B with shared-clock 1h-block bootstrap
    (resample hour blocks; each draw recomputes both means)."""
    rng = random.Random(seed)
    blocks = {}
    for t0, v in pairs_a:
        blocks.setdefault(t0 // block_s, [[], []])[0].append(v)
    for t0, v in pairs_b:
        blocks.setdefault(t0 // block_s, [[], []])[1].append(v)
    keys = list(blocks.keys())
    B = len(keys)
    ma = sum(v for _, v in pairs_a) / len(pairs_a) if pairs_a else float("nan")
    mb = sum(v for _, v in pairs_b) / len(pairs_b) if pairs_b else float("nan")
    diffs = []
    for _ in range(nboot):
        sa = na = sb = nb = 0
        for _ in range(B):
            k = keys[rng.randrange(B)]
            a, b = blocks[k]
            sa += sum(a); na += len(a)
            sb += sum(b); nb += len(b)
        if na and nb:
            diffs.append(sa / na - sb / nb)
    diffs.sort()
    if not diffs:
        return None
    lo = diffs[int(0.025 * len(diffs))]
    hi = diffs[int(0.975 * len(diffs))]
    p_le0 = sum(1 for d in diffs if d <= 0) / len(diffs)
    return dict(diff=ma - mb, lo95=lo, hi95=hi, p_le_0=p_le0,
                n_a=len(pairs_a), n_b=len(pairs_b), blocks=B)
