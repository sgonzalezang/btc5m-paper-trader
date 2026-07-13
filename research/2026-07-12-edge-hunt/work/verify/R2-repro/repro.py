#!/usr/bin/env python3
"""Independent reproduction of FINDING R2 (fee-dead 50-53c fill zone).

Written from scratch off the plain-English claim only. stdlib only.

Claim components tested:
  C1. Pooled 50-53c fills: q=.4656 vs q*=.5282, EV -6.26c/sh, n=436, block-boot p=.0115
  C2. Trigger-family >=50c: Wilson 95% q CI [.383,.516] < breakeven .5412;
      era-stable: pre-v3 -9.24c (n=113), v3 -9.19c (n=103)
  C3. Live replication: fillable <=53c 15/35 wins vs cap-missed 10/12, Fisher 1-sided p=.016
Stresses (per verification brief): drop best day, halve sample, jitter bucket edges +-1c.
Extra: dedup by (t0,side) to kill same-interval correlation; multiplicity accounting.
"""
import json, math, random, datetime

DATA = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data"
FEE = 0.07
GAS = 0.004
V3_CUT = 1783698300  # 2026-07-10 15:05 UTC (claim's own era boundary)
TRIGGER_FAMILY = {"reversal", "reversal2", "reversal_v2", "latentfire",
                  "impulse_v2", "impulse50"}  # per claim: "trigger-family"

rng = random.Random(20260712)

# ---------- load ----------
trades = json.load(open(f"{DATA}/trades_unified.json"))
settled = [t for t in trades if t.get("result") in ("win", "loss")
           and isinstance(t.get("entry"), (int, float))]

def ev_c(t):
    """Per-trade net EV in c/share under the frozen cost model, realized outcome."""
    p = t["entry"]
    w = 1.0 if t["result"] == "win" else 0.0
    gas_c = 100.0 * GAS / t["shares"] if t.get("shares") else 0.0
    return 100.0 * (w - p - FEE * p * (1 - p)) - gas_c

def qstar(p):
    return p + FEE * p * (1 - p)

# ---------- stats helpers (own implementations) ----------
def block_boot(rows, reps=5000, blocksec=3600):
    """1h-block bootstrap of mean ev_c. Returns (mean, lo95, hi95, p_ge_0)."""
    if not rows:
        return None
    blocks = {}
    for t in rows:
        blocks.setdefault(t["t0"] // blocksec, []).append(ev_c(t))
    keys = list(blocks.keys())
    obs = sum(ev_c(t) for t in rows) / len(rows)
    means, ge0 = [], 0
    for _ in range(reps):
        samp = [v for _ in range(len(keys)) for v in blocks[rng.choice(keys)]]
        m = sum(samp) / len(samp)
        means.append(m)
        if m >= 0:
            ge0 += 1
    means.sort()
    return dict(n=len(rows), nblocks=len(keys), mean_c=round(obs, 2),
                lo=round(means[int(0.025 * reps)], 2),
                hi=round(means[int(0.975 * reps)], 2),
                p_ge0=round(ge0 / reps, 4))

def wilson(w, n, z=1.96):
    if n == 0:
        return None
    ph = w / n
    d = 1 + z * z / n
    c = (ph + z * z / (2 * n)) / d
    h = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / d
    return (round(c - h, 4), round(c + h, 4))

def fisher_onesided(a, b, c, d):
    """P(X >= a) hypergeometric: a wins of (a+b) in group1, c wins of (c+d) group2."""
    def lchoose(n, k):
        return math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)
    n1, n2, k = a + b, c + d, a + c
    p = 0.0
    for x in range(a, min(n1, k) + 1):
        if k - x < 0 or k - x > n2:
            continue
        p += math.exp(lchoose(n1, x) + lchoose(n2, k - x) - lchoose(n1 + n2, k))
    return p

def summarize(rows):
    n = len(rows)
    if n == 0:
        return dict(n=0)
    w = sum(1 for t in rows if t["result"] == "win")
    pbar = sum(t["entry"] for t in rows) / n
    return dict(n=n, wins=w, q=round(w / n, 4), p_mean=round(pbar, 4),
                qstar=round(qstar(pbar), 4),
                ev_c=round(sum(ev_c(t) for t in rows) / n, 2),
                wilson_q=wilson(w, n))

def dedup(rows):
    """One row per (t0, side): outcome is fully determined by (t0, side)."""
    seen, out = set(), []
    for t in sorted(rows, key=lambda x: x["at"]):
        k = (t["t0"], t["side"])
        if k not in seen:
            seen.add(k)
            out.append(t)
    return out

def day(t):
    return datetime.datetime.utcfromtimestamp(t["t0"]).strftime("%m-%d")

def stress(rows, label):
    """drop-best-day (most claim-favorable day removed), halves, per-day table."""
    out = {}
    days = {}
    for t in rows:
        days.setdefault(day(t), []).append(t)
    contrib = {d: sum(ev_c(t) for t in v) for d, v in days.items()}
    # claim says EV<0, so most favorable day = most negative total contribution
    worst = min(contrib, key=contrib.get)
    kept = [t for t in rows if day(t) != worst]
    out["per_day_ev_total_c"] = {d: round(v, 1) for d, v in sorted(contrib.items())}
    out["drop_best_day"] = dict(dropped=worst, **(block_boot(kept) or {}))
    srt = sorted(rows, key=lambda x: x["t0"])
    h = len(srt) // 2
    out["first_half"] = block_boot(srt[:h])
    out["second_half"] = block_boot(srt[h:])
    # random halves: fraction of 1000 random halves with mean < 0
    neg = 0
    for _ in range(1000):
        samp = rng.sample(rows, h)
        if sum(ev_c(t) for t in samp) / h < 0:
            neg += 1
    out["random_halves_frac_negative"] = round(neg / 1000, 3)
    return out

res = {"note": "independent repro of R2; own code, frozen cost model, gas included per-share"}

# ================= C1: pooled 50-53c =================
for lo, hi, tag in [(0.50, 0.53, "50_53_incl"), ]:
    rows = [t for t in settled if lo <= t["entry"] <= hi]
    res[f"C1_pooled_{tag}"] = summarize(rows)
    res[f"C1_pooled_{tag}"]["boot"] = block_boot(rows)
    dd = dedup(rows)
    res[f"C1_pooled_{tag}"]["dedup"] = summarize(dd)
    res[f"C1_pooled_{tag}"]["dedup"]["boot"] = block_boot(dd)
    res[f"C1_stress_{tag}"] = stress(rows, tag)
    res[f"C1_stress_dedup_{tag}"] = stress(dd, tag + "_dedup")

# jitter bucket edges +-1c
jit = {}
for lo in (0.49, 0.50, 0.51):
    for hi in (0.52, 0.53, 0.54):
        rows = [t for t in settled if lo <= t["entry"] <= hi]
        b = block_boot(rows, reps=2000)
        jit[f"{lo:.2f}-{hi:.2f}"] = dict(n=b["n"], ev_c=b["mean_c"],
                                         lo=b["lo"], hi=b["hi"], p_ge0=b["p_ge0"])
res["C1_jitter"] = jit

# ================= C2: trigger-family >=50c =================
fam = [t for t in settled if t["eng"] in TRIGGER_FAMILY]
ge50 = [t for t in fam if t["entry"] >= 0.50]
lt50 = [t for t in fam if t["entry"] < 0.50]
res["C2_family_ge50"] = summarize(ge50)
res["C2_family_ge50"]["boot"] = block_boot(ge50)
res["C2_family_ge50"]["dedup"] = summarize(dedup(ge50))
res["C2_family_ge50"]["dedup"]["boot"] = block_boot(dedup(ge50))
res["C2_family_lt50"] = summarize(lt50)
res["C2_family_lt50"]["boot"] = block_boot(lt50)
res["C2_era"] = {
    "pre_v3_ge50": dict(summarize([t for t in ge50 if t["t0"] < V3_CUT]),
                        boot=block_boot([t for t in ge50 if t["t0"] < V3_CUT])),
    "v3_ge50": dict(summarize([t for t in ge50 if t["t0"] >= V3_CUT]),
                    boot=block_boot([t for t in ge50 if t["t0"] >= V3_CUT])),
    "pre_v3_ge50_dedup": summarize(dedup([t for t in ge50 if t["t0"] < V3_CUT])),
    "v3_ge50_dedup": summarize(dedup([t for t in ge50 if t["t0"] >= V3_CUT])),
}
res["C2_stress"] = stress(ge50, "fam_ge50")
res["C2_stress_dedup"] = stress(dedup(ge50), "fam_ge50_dedup")
# threshold jitter on the 0.50 split
res["C2_jitter"] = {}
for cut in (0.49, 0.50, 0.51):
    rows = [t for t in fam if t["entry"] >= cut]
    b = block_boot(rows, reps=2000)
    res["C2_jitter"][f">={cut:.2f}"] = dict(n=b["n"], ev_c=b["mean_c"], lo=b["lo"],
                                            hi=b["hi"], p_ge0=b["p_ge0"],
                                            wilson_q=summarize(rows)["wilson_q"],
                                            qstar=summarize(rows)["qstar"])
# direct lt50 vs ge50 contrast (paired block bootstrap of difference)
def boot_diff(r1, r2, reps=5000):
    b1, b2 = {}, {}
    for t in r1:
        b1.setdefault(t["t0"] // 3600, []).append(ev_c(t))
    for t in r2:
        b2.setdefault(t["t0"] // 3600, []).append(ev_c(t))
    keys = sorted(set(b1) | set(b2))
    obs = sum(ev_c(t) for t in r1) / len(r1) - sum(ev_c(t) for t in r2) / len(r2)
    cnt = 0; diffs = []
    for _ in range(reps):
        s1, s2 = [], []
        for _ in range(len(keys)):
            k = rng.choice(keys)
            s1.extend(b1.get(k, [])); s2.extend(b2.get(k, []))
        if not s1 or not s2:
            continue
        d = sum(s1) / len(s1) - sum(s2) / len(s2)
        diffs.append(d)
        if d <= 0:
            cnt += 1
    diffs.sort()
    return dict(obs_diff_c=round(obs, 2), p_diff_le0=round(cnt / len(diffs), 4),
                lo=round(diffs[int(0.025 * len(diffs))], 2),
                hi=round(diffs[int(0.975 * len(diffs))], 2))
res["C2_lt50_minus_ge50"] = boot_diff(lt50, ge50)

# ================= C3: live replication check =================
res["C3_fisher_15_35_vs_10_12"] = round(fisher_onesided(10, 2, 15, 20), 5)
# verify the 12 cap-missed outcomes against Coinbase 1m candles
capmiss = [  # (t0, side, claimed_win) from misses/results.json capmiss_x_rev55
    (1783709700, "up", True), (1783719600, "down", True), (1783724700, "up", True),
    (1783798200, "up", False), (1783819200, "down", True), (1783836300, "up", False),
    (1783872900, "up", True), (1783878900, "up", True), (1783895100, "down", True),
    (1783909500, "up", True), (1783913400, "down", True), (1783913700, "up", True)]
_cb = json.load(open(f"{DATA}/cb1m.json"))
cb = {t: o for t, o in zip(_cb["t"], _cb["o"])}
chk = []
for t0, side, cw in capmiss:
    a, b = cb.get(t0), cb.get(t0 + 300)
    if a and b:
        win = (b > a) if side == "up" else (b < a)
        chk.append(dict(t0=t0, side=side, claimed=cw, candle_win=win,
                        move_bps=round(1e4 * (b - a) / a, 1),
                        agree=(win == cw)))
    else:
        chk.append(dict(t0=t0, side=side, claimed=cw, candle_win=None, agree=None))
res["C3_capmiss_candle_check"] = dict(
    n=len(chk), agree=sum(1 for c in chk if c["agree"]),
    disagree=[c for c in chk if c["agree"] is False],
    missing=[c["t0"] for c in chk if c["agree"] is None], rows=chk)

json.dump(res, open("/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work/verify/R2-repro/results.json", "w"), indent=1)
print(json.dumps({k: v for k, v in res.items() if not k.startswith("C3_capmiss")}, indent=1))
print("capmiss agree:", res["C3_capmiss_candle_check"]["agree"], "/",
      res["C3_capmiss_candle_check"]["n"],
      "disagree:", res["C3_capmiss_candle_check"]["disagree"])
