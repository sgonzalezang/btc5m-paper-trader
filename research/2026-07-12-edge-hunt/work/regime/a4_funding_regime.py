"""A4: Funding / OI / premium regime SHIFTS vs the 5m contrarian fade.
Uses Deribit hourly funding (May 11 - Jul 10 from prior harvest, extended to Jul 13
03:00 via fresh public GET), binance.vision OI (Jun 10 - Jul 10) and premium index
(May 11 - Jul 9). All features lagged: latest sample with ts <= t0. K=5 test families
x 2 splits, counted in the results. Stdlib only."""
import json, sys, bisect
sys.path.insert(0, "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work/regime")
from lib import *

SCRATCH = "/private/tmp/claude-501/-Users-sgonzalez/33d3ef48-d587-4455-91a3-047cebc6d6c2/scratchpad"

t, o = load_cb5m()
t0s, r, up = build_series(t, o)
n = len(t0s)

# triggered fades (the tradeable object)
trig = []
for i in range(13, n):
    if abs(r[i - 1]) < 0.0012 or r[i - 1] == 0:
        continue
    win = 1.0 if up[i] != (r[i - 1] > 0) else 0.0
    trig.append((t0s[i], win))

# ---- funding series (merged) ----
f_old = json.load(open(f"{DATA10}/funding.json"))["rows"]          # [sec, rate]
f_new = json.load(open(f"{SCRATCH}/funding_fresh.json"))["result"]  # ms rows
fund = {int(ts): rate for ts, rate in f_old}
for row in f_new:
    fund[row["timestamp"] // 1000] = row["interest_8h"]
fts = sorted(fund)
frates = [fund[k] for k in fts]
print(f"funding rows merged: {len(fts)}  span {fts[0]} -> {fts[-1]}")

def latest_idx(ts_list, t0):
    j = bisect.bisect_right(ts_list, t0) - 1
    return j if j >= 0 else None

# funding sign flips (consecutive hourly samples change sign)
flips = [fts[k] for k in range(1, len(fts))
         if frates[k] * frates[k - 1] < 0]
print(f"funding sign flips: {len(flips)}")

# funding extreme threshold from TRAIN
train_abs = sorted(abs(v) for ts, v in zip(fts, frates) if ts < TEST_START)
p90 = train_abs[int(0.9 * len(train_abs))]

# ---- OI ----
oi = json.load(open(f"{DATA10}/oi5m.json"))
oits, oiv = oi["t"], oi["oi"]
# 1h relative change series
oich = {}
for k in range(12, len(oits)):
    if oits[k] - oits[k - 12] == 3600 and oiv[k - 12]:
        oich[oits[k]] = (oiv[k] - oiv[k - 12]) / oiv[k - 12]
oich_ts = sorted(oich)
train_oi = sorted(abs(oich[k]) for k in oich_ts if k < TEST_START)
oi_p90 = train_oi[int(0.9 * len(train_oi))] if train_oi else None
print(f"OI 1h-change rows: {len(oich_ts)}  train p90 |chg|: {oi_p90}")

# ---- premium ----
pr = json.load(open(f"{DATA10}/premium5m.json"))
prts, prc = pr["t"], pr["c"]
# premium sign flip within last hour: sign(c[k]) != sign(c[k-12])
prflip = {}
prsign = {}
for k in range(12, len(prts)):
    prsign[prts[k]] = 1 if prc[k] >= 0 else -1
    prflip[prts[k]] = (prc[k] >= 0) != (prc[k - 12] >= 0)
prf_ts = sorted(prflip)

def contrast(flag_fn, name, window_bounds, min_n=25):
    lo_t, hi_t = window_bounds
    a, b = [], []
    for t0, win in trig:
        if not (lo_t <= t0 < hi_t):
            continue
        fl = flag_fn(t0)
        if fl is None:
            continue
        (a if fl else b).append((hour_block(t0), ev_cents(win)))
    if len(a) < min_n or len(b) < min_n:
        return {"name": name, "n_flag": len(a), "n_rest": len(b), "skipped": "insufficient n"}
    qa = sum(v for _, v in a) / len(a); qb = sum(v for _, v in b) / len(b)
    d, dl, dh, dp = block_boot_diff(a, b, B=3000, seed=abs(hash(name)) % 5555)
    return {"name": name, "n_flag": len(a), "n_rest": len(b),
            "ev_flag_c": round(qa, 2), "ev_rest_c": round(qb, 2),
            "diff_c": round(d, 2), "ci": [round(dl, 2), round(dh, 2)], "p_le_0": round(dp, 4)}

def f_flip24(t0):
    if not (fts[0] + 3600 <= t0 <= fts[-1] + 3600):
        return None
    j = bisect.bisect_right(flips, t0) - 1
    return j >= 0 and (t0 - flips[j]) < 86400

def f_extreme(t0):
    j = latest_idx(fts, t0)
    if j is None or t0 - fts[j] > 7200:
        return None
    return abs(frates[j]) >= p90

def f_oi_extreme(t0):
    j = latest_idx(oich_ts, t0)
    if j is None or t0 - oich_ts[j] > 3600:
        return None
    return abs(oich[oich_ts[j]]) >= oi_p90

def f_prem_flip(t0):
    j = latest_idx(prf_ts, t0)
    if j is None or t0 - prf_ts[j] > 3600:
        return None
    return prflip[prf_ts[j]]

def f_prem_neg(t0):
    j = latest_idx(prf_ts, t0)
    if j is None or t0 - prf_ts[j] > 3600:
        return None
    return prsign[prf_ts[j]] < 0

out = {"K_comparisons": "5 flag families x 2 splits = 10 contrasts", "results": {}}
FLAGS = [(f_flip24, "funding_flip_within_24h"),
         (f_extreme, "funding_abs_ge_train_p90"),
         (f_oi_extreme, "oi_1h_chg_abs_ge_train_p90"),
         (f_prem_flip, "premium_sign_flip_last_1h"),
         (f_prem_neg, "premium_negative")]
for lbl, w in [("TRAIN", (0, TEST_START)), ("TEST", (TEST_START, 1 << 62))]:
    rows = []
    for fn, name in FLAGS:
        rows.append(contrast(fn, name, w))
    out["results"][lbl] = rows
    for row in rows:
        print(lbl, json.dumps(row))

json.dump(out, open("/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work/regime/a4_results.json", "w"), indent=1)
print("saved a4_results.json")
