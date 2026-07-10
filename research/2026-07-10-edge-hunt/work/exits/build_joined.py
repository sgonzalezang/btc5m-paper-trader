#!/usr/bin/env python3
"""Join settled win/loss trades with cb1m intra-interval paths and a Phi(drift/vol) FV model.

FV model (per brief's value-engine form): at s seconds into a 5m interval,
  x = ln(P_s / O),  remvar = sigma2_per_sec * (300 - s),  fv_up = Phi(x / sqrt(remvar))
sigma2_per_sec estimated from trailing 120 one-minute log returns ending at t0.

Checkpoints s in {60,120,180,240}; price at t0+s is cb1m close of candle starting t0+s-60.
Output: work/exits/joined.json (one row per trade with fv path + validation vs pm_prices_sample).
"""
import json, math, bisect

SCRATCH = "/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad"

def phi(z):
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))

cb = json.load(open(SCRATCH + "/data/cb1m.json"))
T, O, C = cb["t"], cb["o"], cb["c"]
idx = {t: i for i, t in enumerate(T)}

# trailing sigma: rolling var of 1m log returns over 120 minutes
logret = [None] * len(T)
for i in range(1, len(T)):
    if T[i] - T[i-1] == 60 and C[i-1] > 0:
        logret[i] = math.log(C[i] / C[i-1])

def sigma2_per_sec(t0):
    """var of 1m log-returns over the 120 candles ending just before t0, per second."""
    i = idx.get(t0 - 60)
    if i is None:
        i = bisect.bisect_left(T, t0) - 1
    lo = max(1, i - 119)
    xs = [logret[j] for j in range(lo, i + 1) if logret[j] is not None]
    if len(xs) < 30:
        return None
    m = sum(xs) / len(xs)
    v = sum((x - m) ** 2 for x in xs) / (len(xs) - 1)
    return v / 60.0

trades = json.load(open(SCRATCH + "/data/trades.json"))
rows = []
miss_path = 0
miss_sig = 0
for t in trades:
    if t.get("status") != "settled" or t.get("result") not in ("win", "loss"):
        continue
    t0 = t["t0"]
    i0 = idx.get(t0)
    if i0 is None:
        miss_path += 1
        continue
    # need candles t0, t0+60, t0+120, t0+180 (closes = prices at 60..240s)
    ok = all(idx.get(t0 + k * 60) is not None for k in range(4))
    if not ok:
        miss_path += 1
        continue
    s2 = sigma2_per_sec(t0)
    if s2 is None or s2 <= 0:
        miss_sig += 1
        continue
    Op = O[i0]
    fv = {}
    px = {}
    for k, s in enumerate((60, 120, 180, 240)):
        P = C[idx[t0 + k * 60]]
        x = math.log(P / Op)
        rem = 300 - s
        z = x / math.sqrt(s2 * rem)
        f = phi(z)
        fv[str(s)] = round(f, 4)
        px[str(s)] = P
    e = t["entry"]; sh = t["shares"]
    fee = t.get("feeEntry")
    if fee is None:
        fee = sh * 0.07 * e * (1 - e)
    gas = t.get("gas", 0.004) or 0.004
    win = 1 if t["result"] == "win" else 0
    pnl_hold = sh * (1 - e) - fee - gas if win else -sh * e - fee - gas
    rows.append({
        "t0": t0, "eng": t["eng"], "side": t["side"], "entry": e, "shares": sh,
        "feeEntry": fee, "gas": gas, "entrySec": t.get("entrySec"),
        "win": win, "pnl_ledger": t["pnl"], "pnl_hold": round(pnl_hold, 4),
        "src": t["src"], "fv_up": fv, "px": px, "open": Op,
    })

rows.sort(key=lambda r: r["t0"])
print("joined rows:", len(rows), "missing path:", miss_path, "missing sigma:", miss_sig)

# --- validate FV vs actual Polymarket snapshots ---
pm = json.load(open(SCRATCH + "/data/pm_res_3d.json"))
pmp = json.load(open(SCRATCH + "/data/pm_prices_sample.json"))
pm_by_t0 = {m["t0"]: m for m in pmp}
pairs60 = []
pairs150 = []
seen = set()
for r in rows:
    if r["t0"] in pm_by_t0 and r["t0"] not in seen:
        seen.add(r["t0"])
        m = pm_by_t0[r["t0"]]
        if m.get("p60") is not None:
            pairs60.append((r["fv_up"]["60"], m["p60"]))
        if m.get("p150") is not None:
            # fv at 150s ~ interpolate 120 and 180
            f150 = 0.5 * (r["fv_up"]["120"] + r["fv_up"]["180"])
            pairs150.append((f150, m["p150"]))

def corr(pairs):
    n = len(pairs)
    if n < 3:
        return None, None
    xs = [a for a, b in pairs]; ys = [b for a, b in pairs]
    mx = sum(xs)/n; my = sum(ys)/n
    cov = sum((x-mx)*(y-my) for x, y in pairs)
    vx = sum((x-mx)**2 for x in xs); vy = sum((y-my)**2 for y in ys)
    c = cov / math.sqrt(vx*vy) if vx > 0 and vy > 0 else None
    mad = sum(abs(x-y) for x, y in pairs)/n
    return c, mad

c60, mad60 = corr(pairs60)
c150, mad150 = corr(pairs150)
print(f"FV vs PM p60: n={len(pairs60)} corr={c60:.3f} meanAbsDiff={mad60:.3f}")
print(f"FV vs PM p150: n={len(pairs150)} corr={c150:.3f} meanAbsDiff={mad150:.3f}")

# --- calibration of fv_side checkpoints vs realized outcome ---
print("\nCalibration: fv_side bucket -> realized win rate (pooled all engines)")
for s in ("60", "120", "180", "240"):
    buckets = {}
    for r in rows:
        f = r["fv_up"][s] if r["side"] == "up" else 1 - r["fv_up"][s]
        b = min(9, int(f * 10))
        buckets.setdefault(b, [0, 0])
        buckets[b][0] += r["win"]
        buckets[b][1] += 1
    line = []
    for b in sorted(buckets):
        w, n = buckets[b]
        line.append(f"{b/10:.1f}-{(b+1)/10:.1f}:{w/n:.2f}(n={n})")
    print(f"s={s}s  " + " ".join(line))

json.dump(rows, open(SCRATCH + "/work/exits/joined.json", "w"))
print("\nwrote work/exits/joined.json")
