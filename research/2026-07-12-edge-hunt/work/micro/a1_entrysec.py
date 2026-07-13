"""A1: entrySec — does speed-to-entry itself carry EV, or is it a price/engine proxy?

Bins: 0-15, 15-30, 30-45, 45+ seconds into interval at entry.
Outputs: win rate, mean realized EV/share (frozen cost model), n per bin — pooled, per family,
per engine; plus an entry-price-stratified fast-vs-slow contrast to strip the price confound.
"""
import json, collections, sys
sys.path.insert(0, "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work/micro")
from common import load_trades, mean, block_boot_mean, block_boot_diff, REV_FAMILY

T = [x for x in load_trades() if x.get("entrySec") is not None]

def binlab(s):
    if s < 15: return "00-15"
    if s < 30: return "15-30"
    if s < 45: return "30-45"
    return "45+"

def table(rows, key=lambda x: True, label=""):
    out = {}
    sub = [x for x in rows if key(x)]
    for b in ("00-15", "15-30", "30-45", "45+"):
        g = [x for x in sub if binlab(x["entrySec"]) == b]
        if not g:
            continue
        ev = [x["_evps"] for x in g]; blk = [x["_blk"] for x in g]
        m, lo, hi, p = block_boot_mean(ev, blk)
        out[b] = dict(n=len(g), wr=round(mean([x["_w"] for x in g]), 4),
                      entry_mean=round(mean([x["entry"] for x in g]), 4),
                      evps_c=round(100*m, 2), ci95_c=[round(100*lo, 2), round(100*hi, 2)])
    return out

res = {}
res["pooled"] = table(T)
res["rev_family"] = table(T, lambda x: x["_fam"] == "rev")
res["mom_family"] = table(T, lambda x: x["_fam"] == "mom")
res["per_engine"] = {}
for e in sorted(set(x["eng"] for x in T)):
    g = [x for x in T if x["eng"] == e]
    if len(g) >= 40:
        res["per_engine"][e] = table(g)

# ---- fast (<15s) vs slow (>=15s), price-stratified, within reversal family ----
# strata: entry price in 2c bins; compute per-stratum diff, combine inverse-n-weighted
rev = [x for x in T if x["_fam"] == "rev"]
fast = [x for x in rev if x["entrySec"] < 15]
slow = [x for x in rev if x["entrySec"] >= 15]
d, lo, hi, p = block_boot_diff([x["_evps"] for x in fast], [x["_blk"] for x in fast],
                               [x["_evps"] for x in slow], [x["_blk"] for x in slow])
res["rev_fast_vs_slow_raw"] = dict(n_fast=len(fast), n_slow=len(slow),
                                   entry_fast=round(mean([x["entry"] for x in fast]), 4),
                                   entry_slow=round(mean([x["entry"] for x in slow]), 4),
                                   diff_c=round(100*d, 2), ci95_c=[round(100*lo, 2), round(100*hi, 2)],
                                   p_diff_le0=round(p, 4))

# stratified by 2c price bin (only strata with >=5 in each arm)
strata = collections.defaultdict(lambda: ([], []))
for x in rev:
    k = round(x["entry"] * 50) / 50  # 2c bins
    strata[k][0 if x["entrySec"] < 15 else 1].append(x)
wsum = wn = 0.0
detail = {}
for k in sorted(strata):
    f, s = strata[k]
    if len(f) >= 5 and len(s) >= 5:
        df = mean([x["_evps"] for x in f]) - mean([x["_evps"] for x in s])
        w = 1.0 / (1.0/len(f) + 1.0/len(s))
        wsum += w * df; wn += w
        detail[f"{k:.2f}"] = dict(n_fast=len(f), n_slow=len(s), diff_c=round(100*df, 2))
res["rev_fast_vs_slow_price_stratified"] = dict(strata=detail,
    combined_diff_c=round(100*wsum/wn, 2) if wn else None)

# permutation p for stratified diff: shuffle fast/slow labels within strata, 2000 reps
import random
rng = random.Random(11)
obs = wsum / wn if wn else 0.0
cnt = 0; reps = 2000
usable = [(k, strata[k][0] + strata[k][1], len(strata[k][0])) for k in strata
          if len(strata[k][0]) >= 5 and len(strata[k][1]) >= 5]
for _ in range(reps):
    ws = wn2 = 0.0
    for k, pool, nf in usable:
        idx = list(range(len(pool)))
        rng.shuffle(idx)
        f = [pool[i]["_evps"] for i in idx[:nf]]
        s = [pool[i]["_evps"] for i in idx[nf:]]
        df = mean(f) - mean(s)
        w = 1.0/(1.0/len(f)+1.0/len(s))
        ws += w*df; wn2 += w
    if ws/wn2 >= obs:
        cnt += 1
res["rev_fast_vs_slow_price_stratified"]["perm_p_ge_obs"] = round(cnt/reps, 4)

# same contrast for momentum family (context only)
mom = [x for x in T if x["_fam"] == "mom"]
fastm = [x for x in mom if x["entrySec"] < 15]
slowm = [x for x in mom if x["entrySec"] >= 15]
d, lo, hi, p = block_boot_diff([x["_evps"] for x in fastm], [x["_blk"] for x in fastm],
                               [x["_evps"] for x in slowm], [x["_blk"] for x in slowm])
res["mom_fast_vs_slow_raw"] = dict(n_fast=len(fastm), n_slow=len(slowm),
                                   entry_fast=round(mean([x["entry"] for x in fastm]), 4),
                                   entry_slow=round(mean([x["entry"] for x in slowm]), 4),
                                   diff_c=round(100*d, 2), ci95_c=[round(100*lo, 2), round(100*hi, 2)],
                                   p_diff_le0=round(p, 4))

# entrySec vs entry price correlation (is speed just cheapness?)
import math
def corr(a, b):
    ma, mb = mean(a), mean(b)
    num = sum((x-ma)*(y-mb) for x, y in zip(a, b))
    da = math.sqrt(sum((x-ma)**2 for x in a)); db = math.sqrt(sum((y-mb)**2 for y in b))
    return num/(da*db) if da*db else float("nan")
res["corr_entrySec_entry"] = dict(
    rev=round(corr([x["entrySec"] for x in rev], [x["entry"] for x in rev]), 3),
    mom=round(corr([x["entrySec"] for x in mom], [x["entry"] for x in mom]), 3))

json.dump(res, open("/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work/micro/a1_entrysec.json", "w"), indent=1)
print(json.dumps(res, indent=1))
