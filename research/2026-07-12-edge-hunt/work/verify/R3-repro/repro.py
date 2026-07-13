#!/usr/bin/env python3
"""Independent reproduction + adversarial stress of finding R3.

CLAIM (plain English, reimplemented from scratch):
  Buy the side already >=4bps ahead (btcEntry vs btcOpen at decision time)
  when entry = ask + 1c slip is in [0.60, 0.65), Jul 7-10, deduplicated
  intervals. Claimed q=0.817 (n=71), EV +14.0c/share after frozen cost model.

Frozen cost model: EV/share = q - p - 0.07*p*(1-p); gas $0.004/trade.
Stdlib only.
"""
import json, math, random, datetime

DATA = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data/trades_unified.json"
PM   = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-10-edge-hunt/data/pm_prices_sample.json"
OUT  = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work/verify/R3-repro/results.json"

random.seed(20260712)

def utc_day(t0):
    return datetime.datetime.fromtimestamp(t0, datetime.timezone.utc).strftime("%m-%d")

def fee(p): return 0.07 * p * (1.0 - p)

def ev_share(tr):
    p = tr["entry"]; w = 1.0 if tr["result"] == "win" else 0.0
    gas = 0.004 / tr["shares"] if tr.get("shares") else 0.0
    return w - p - fee(p) - gas

def wilson(w, n, z=1.96):
    if n == 0: return (None, None)
    ph = w / n
    d = 1 + z*z/n
    c = (ph + z*z/(2*n)) / d
    e = z * math.sqrt(ph*(1-ph)/n + z*z/(4*n*n)) / d
    return (round(c-e, 4), round(c+e, 4))

def block_boot(trades, reps=20000):
    """1h-block bootstrap of mean EV/share. Blocks keyed by hour of t0."""
    blocks = {}
    for tr in trades:
        blocks.setdefault(tr["t0"] // 3600, []).append(ev_share(tr))
    keys = list(blocks.keys())
    if not keys: return None
    means = []
    for _ in range(reps):
        s = []
        for _ in range(len(keys)):
            s.extend(blocks[random.choice(keys)])
        means.append(sum(s) / len(s))
    means.sort()
    return {
        "mean_c": round(100 * sum(means) / len(means), 2),
        "ci95_c": [round(100 * means[int(0.025 * len(means))], 2),
                   round(100 * means[int(0.975 * len(means))], 2)],
        "p_le0": round(sum(1 for m in means if m <= 0) / len(means), 4),
        "n_trades": len(trades), "n_blocks": len(keys),
    }

def summarize(trades):
    n = len(trades)
    if n == 0: return {"n": 0}
    w = sum(1 for t in trades if t["result"] == "win")
    pm_ = sum(t["entry"] for t in trades) / n
    evs = [ev_share(t) for t in trades]
    return {"n": n, "wins": w, "q": round(w / n, 4), "p_mean": round(pm_, 4),
            "qstar_mean": round(pm_ + fee(pm_), 4),
            "ev_c": round(100 * sum(evs) / len(evs), 2),
            "q_wilson95": wilson(w, n)}

# ---------------- load & feature ----------------
trades = json.load(open(DATA))
settled = []
for t in trades:
    if t.get("result") not in ("win", "loss"): continue
    if t.get("entry") is None or t.get("btcOpen") is None or t.get("btcEntry") is None: continue
    t["_drift_bps"] = (t["btcEntry"] - t["btcOpen"]) / t["btcOpen"] * 1e4
    d = t["_drift_bps"]
    t["_aligned4"] = (t["side"] == "up" and d >= 4) or (t["side"] == "down" and d <= -4)
    t["_day"] = utc_day(t["t0"])
    settled.append(t)

JUL710 = {"07-07", "07-08", "07-09", "07-10"}
RETIRE_TS = int(datetime.datetime(2026, 7, 10, 15, 5, tzinfo=datetime.timezone.utc).timestamp())

def dedup_by_interval(trs):
    """Keep earliest-decision qualifying trade per interval t0."""
    best = {}
    for t in sorted(trs, key=lambda x: x["at"]):
        best.setdefault(t["t0"], t)
    return list(best.values())

def cell(lo, hi, days=JUL710, aligned=True, dedup=True, pool=settled):
    sel = [t for t in pool
           if lo <= t["entry"] < hi
           and (t["_aligned4"] if aligned else True)
           and (t["_day"] in days if days else True)]
    return dedup_by_interval(sel) if dedup else sel

R = {}

# ---------------- 1. Headline reproduction ----------------
c_band = cell(0.60, 0.65)                       # claim as literally stated
c_ge60 = cell(0.60, 1.01)                       # artifact's actual ruleA_p_ge60 construction
R["repro_band_60_65_dedup"] = summarize(c_band)
R["repro_band_60_65_boot"]  = block_boot(c_band)
R["repro_ge60_dedup"]       = summarize(c_ge60)
R["repro_ge60_boot"]        = block_boot(c_ge60)
R["repro_band_by_day"] = {d: summarize([t for t in c_band if t["_day"] == d]) for d in sorted(JUL710)}

# non-dedup for reference
R["repro_band_60_65_nodedup"] = summarize(cell(0.60, 0.65, dedup=False))

# ---------------- 2. Stress: drop the single best day ----------------
def drop_day_stress(cellset, key):
    daily = {}
    for t in cellset:
        daily.setdefault(t["_day"], []).append(ev_share(t))
    contrib = {d: sum(v) for d, v in daily.items()}
    best = max(contrib, key=contrib.get)
    rest = [t for t in cellset if t["_day"] != best]
    R[key] = {"dropped_day": best,
              "dropped_day_ev_sum_c": round(100 * contrib[best], 1),
              "remaining": summarize(rest),
              "remaining_boot": block_boot(rest)}
drop_day_stress(c_band, "stress_drop_best_day_band")
drop_day_stress(c_ge60, "stress_drop_best_day_ge60")

# ---------------- 3. Stress: halve the sample ----------------
def halve_stress(cellset, key):
    n = len(cellset)
    half = n // 2
    neg = 0; below_fees = 0
    reps = 4000
    for _ in range(reps):
        s = random.sample(cellset, half)
        m = sum(ev_share(t) for t in s) / half
        if m <= 0: neg += 1
    srt = sorted(cellset, key=lambda t: t["t0"])
    first, second = srt[:half], srt[half:]
    R[key] = {"random_halves_frac_ev_le0": round(neg / reps, 4),
              "chrono_first_half": summarize(first),
              "chrono_second_half": summarize(second)}
halve_stress(c_band, "stress_halve_band")
halve_stress(c_ge60, "stress_halve_ge60")

# ---------------- 4. Stress: jitter bucket edges +-1c ----------------
jit = {}
for lo, hi in [(0.59, 0.64), (0.61, 0.66), (0.59, 0.65), (0.60, 0.66), (0.61, 0.64), (0.59, 0.66)]:
    cs = cell(lo, hi)
    s = summarize(cs); b = block_boot(cs)
    jit[f"[{lo:.2f},{hi:.2f})"] = {"n": s["n"], "q": s.get("q"), "ev_c": s.get("ev_c"),
                                   "boot_p_le0": b["p_le0"] if b else None,
                                   "boot_ci95_c": b["ci95_c"] if b else None}
R["stress_jitter_edges"] = jit

# ---------------- 5. Reconcile with pooled 60-66c momentum ledger ----------------
pool_6066 = [t for t in settled if 0.60 <= t["entry"] < 0.66 and t["_day"] in JUL710]
R["reconcile_pooled_60_66_jul7_10"] = summarize(pool_6066)
al = [t for t in pool_6066 if t["_aligned4"]]
rest = [t for t in pool_6066 if not t["_aligned4"]]
R["reconcile_pooled_60_66_aligned4"] = summarize(al)
R["reconcile_pooled_60_66_complement"] = summarize(rest)
# whole ledger 60-66 regardless of day
pool_all = [t for t in settled if 0.60 <= t["entry"] < 0.66]
R["reconcile_pooled_60_66_alldays"] = summarize(pool_all)

# ---------------- 6. Era availability: any qualifying fills after retirement? ----------------
post = [t for t in settled if t["at"] / 1000 >= RETIRE_TS]
R["era_post_jul10_1505"] = {
    "n_settled_total": len(post),
    "n_entry_ge60": len([t for t in post if t["entry"] >= 0.60]),
    "n_band_60_65": len([t for t in post if 0.60 <= t["entry"] < 0.65]),
    "n_band_60_65_aligned4": len([t for t in post if 0.60 <= t["entry"] < 0.65 and t["_aligned4"]]),
    "max_entry": max((t["entry"] for t in post), default=None),
}

# ---------------- 7. Staleness diagnostics ----------------
# 7a. drift-magnitude split inside the band cell: if apparent EV grows with the
#     size of the just-happened move while the recorded ask stays cheap, the
#     bargain is a lagging quote, not a market offer.
mag = {}
for lab, lo, hi in [("4-8bps", 4, 8), (">=8bps", 8, 1e9)]:
    sub = [t for t in c_band if lo <= abs(t["_drift_bps"]) < hi]
    mag[lab] = summarize(sub)
R["stale_drift_magnitude_split_band"] = mag

# 7b. does the recorded price rise with drift among aligned 60-66c fills? (rank corr)
al66 = [t for t in settled if 0.60 <= t["entry"] < 0.66 and t["_aligned4"] and t["_day"] in JUL710]
def rank(xs):
    idx = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    for k, i in enumerate(idx): r[i] = k
    return r
if len(al66) > 5:
    a = rank([abs(t["_drift_bps"]) for t in al66]); b = rank([t["entry"] for t in al66])
    ma, mb = sum(a)/len(a), sum(b)/len(b)
    num = sum((x-ma)*(y-mb) for x, y in zip(a, b))
    den = math.sqrt(sum((x-ma)**2 for x in a) * sum((y-mb)**2 for y in b))
    R["stale_spearman_absdrift_vs_entry_aligned6066"] = {"rho": round(num/den, 3), "n": len(al66)}

# 7c. PM snapshot join: for cell intervals present in pm_prices_sample, compare the
#     ledger's recorded entry to the PM snapshot price of the SAME side at the
#     snapshot second nearest entrySec. Positive gap = ledger filled below where
#     the market actually was => stale ask.
pmS = {s["t0"]: s for s in json.load(open(PM))}
def snap_price(s, side, sec):
    # snapshots at 20 / 60 / 150 s of the UP side
    pts = [(20, s["p20"]), (60, s["p60"]), (150, s["p150"])]
    t, p = min(pts, key=lambda x: abs(x[0] - sec))
    if p is None: return None, t
    return (p if side == "up" else round(1 - p, 4)), t
def pm_join(cellset):
    gaps, evs, rows = [], [], []
    for t in cellset:
        s = pmS.get(t["t0"])
        if not s: continue
        sec = t.get("entrySec") or 30
        sp, snap_t = snap_price(s, t["side"], sec)
        if sp is None: continue
        gap = sp - t["entry"]
        # honest refill: pay snapshot price + 1c slip instead of ledger ask+slip
        p2 = min(sp + 0.01, 0.99)
        w = 1.0 if t["result"] == "win" else 0.0
        ev2 = w - p2 - fee(p2)
        gaps.append(gap); evs.append(ev2)
        rows.append({"t0": t["t0"], "side": t["side"], "entrySec": sec, "snap_at": snap_t,
                     "ledger_entry": t["entry"], "pm_snap_side": sp, "gap_c": round(100*gap, 1),
                     "win": int(w)})
    if not gaps: return {"n": 0}
    gaps.sort()
    return {"n": len(gaps),
            "mean_gap_c": round(100 * sum(gaps) / len(gaps), 2),
            "median_gap_c": round(100 * gaps[len(gaps)//2], 2),
            "frac_gap_gt3c": round(sum(1 for g in gaps if g > 0.03) / len(gaps), 3),
            "ev_at_snapshot_fill_c": round(100 * sum(evs) / len(evs), 2),
            "rows": rows}
R["stale_pm_snapshot_join_band"] = pm_join(c_band)
R["stale_pm_snapshot_join_ge60"] = pm_join(c_ge60)

# 7d. same join for ALL aligned>=4bps trades any price (rule A), to get more n
c_any = cell(0.0, 1.01)
R["stale_pm_snapshot_join_anyprice"] = pm_join(c_any)
R["ruleA_anyprice_dedup"] = summarize(c_any)
R["ruleA_anyprice_boot"] = block_boot(c_any)

json.dump(R, open(OUT, "w"), indent=1)

for k in R:
    v = R[k]
    print("==", k)
    print(json.dumps({kk: vv for kk, vv in v.items() if kk != "rows"} if isinstance(v, dict) else v, indent=1)[:1200] if isinstance(v, dict) else v)
