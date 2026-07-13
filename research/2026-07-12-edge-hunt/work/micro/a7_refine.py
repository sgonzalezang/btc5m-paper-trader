"""A7 refinements:
 (a) 'winners entrySec p50=9s' claim check — winners vs losers entrySec within rev family & eras.
 (b) era-controlled fast-vs-slow within old reversal era (Jul 8-10) and v3 era.
 (c) slip sensitivity at the MEASURE-BOOK gated fill mix (the deployable flagship mix).
 (d) Kelly f_nonpos skip value: impulse50 trades at t0s the flagship skipped (paired live test)
     + pooled with measure-book skips.
 (e) binomial p-values for the cap-miss counterfactual (n=13 unique t0).
"""
import json, math, collections, sys
sys.path.insert(0, "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work/micro")
from common import load_trades, mean, fee, block_boot_mean, block_boot_diff, REV_FAMILY, V3_START

DATA = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data"
res = {}
T = load_trades()
rev = [x for x in T if x["_fam"] == "rev" and x.get("entrySec") is not None]

def med(v):
    s = sorted(v)
    return s[len(s)//2] if s else None

# (a) winners vs losers entrySec
for lab, grp in [("rev_all", rev),
                 ("rev_old_era", [x for x in rev if x["t0"] < V3_START]),
                 ("rev_v3_era", [x for x in rev if x["t0"] >= V3_START])]:
    w = [x["entrySec"] for x in grp if x["_w"] == 1]
    l = [x["entrySec"] for x in grp if x["_w"] == 0]
    res[f"entrySec_medians_{lab}"] = dict(n_win=len(w), n_loss=len(l),
                                          p50_win=med(w), p50_loss=med(l))

# (b) era-controlled fast vs slow
for lab, grp in [("old_era", [x for x in rev if x["t0"] < V3_START]),
                 ("v3_era", [x for x in rev if x["t0"] >= V3_START])]:
    fast = [x for x in grp if x["entrySec"] < 15]
    slow = [x for x in grp if x["entrySec"] >= 15]
    if len(fast) >= 10 and len(slow) >= 10:
        d, lo, hi, p = block_boot_diff([x["_evps"] for x in fast], [x["_blk"] for x in fast],
                                       [x["_evps"] for x in slow], [x["_blk"] for x in slow])
        res[f"fast_vs_slow_{lab}"] = dict(n_fast=len(fast), n_slow=len(slow),
                                          wr_fast=round(mean([x["_w"] for x in fast]), 3),
                                          wr_slow=round(mean([x["_w"] for x in slow]), 3),
                                          diff_c=round(100*d, 2),
                                          ci95_c=[round(100*lo, 2), round(100*hi, 2)],
                                          p_diff_le0=round(p, 4))
    else:
        res[f"fast_vs_slow_{lab}"] = dict(n_fast=len(fast), n_slow=len(slow), note="thin")

# (c) slip sensitivity at measure-book gated mix
s = json.load(open(f"{DATA}/state_extract.json"))
masks = [x["f"]["ask"] for x in s["measure"] if "f" in x and x["f"].get("ask") is not None]
def ev_at_slip(q, ask_list, slip):
    return mean([q - (a + slip) - fee(a + slip) for a in ask_list])
def back_out_q(target, ask_list, slip=0.01):
    lo, hi = 0.3, 0.95
    for _ in range(60):
        m = (lo + hi) / 2
        if ev_at_slip(m, ask_list, slip) < target:
            lo = m
        else:
            hi = m
    return (lo + hi) / 2
mix = {}
for target, lab in [(0.015, "+1.5c"), (0.03, "+3.0c")]:
    q = back_out_q(target, masks)
    lo_s, hi_s = 0.0, 0.10
    for _ in range(60):
        m = (lo_s + hi_s) / 2
        if ev_at_slip(q, masks, m) > 0:
            lo_s = m
        else:
            hi_s = m
    mix[lab] = dict(implied_q=round(q, 4), breakeven_slip_c=round(100*(lo_s+hi_s)/2, 2),
                    ev_at_2c_slip=round(100*ev_at_slip(q, masks, 0.02), 2))
res["slip_sensitivity_measure_mix"] = dict(n_asks=len(masks), ask_mean=round(mean(masks), 4), **mix)

# (d) Kelly skip value — impulse50 fills at t0 where impulse_v2 did not trade
i50 = {x["t0"]: x for x in T if x["eng"] == "impulse50"}
iv2 = set(x["t0"] for x in T if x["eng"] == "impulse_v2")
skipped_live = [x for t0, x in i50.items() if t0 not in iv2]
taken_live = [x for t0, x in i50.items() if t0 in iv2]
def evline(g):
    if not g:
        return dict(n=0)
    return dict(n=len(g), wr=round(mean([x["_w"] for x in g]), 3),
                entry=round(mean([x["entry"] for x in g]), 4),
                evps_c=round(100*mean([x["_evps"] for x in g]), 2))
res["impulse50_at_flagship_skips"] = evline(skipped_live)
res["impulse50_at_flagship_fills"] = evline(taken_live)
if len(skipped_live) >= 5:
    ev = [x["_evps"] for x in skipped_live]; blk = [x["_blk"] for x in skipped_live]
    m, lo, hi, p = block_boot_mean(ev, blk)
    res["impulse50_at_flagship_skips"]["ci95_c"] = [round(100*lo, 2), round(100*hi, 2)]
    res["impulse50_at_flagship_skips"]["p_ge0"] = round(1 - p, 4)

# pooled skip-value: measure-book f_nonpos skips (n=21) as net EV/share
mb = [x for x in s["measure"] if x.get("win") is not None]
sk = [x["win"] - x["cost"] for x in mb if not x["sized"]]
sz = [x["win"] - x["cost"] for x in mb if x["sized"]]
res["measure_skip_vs_sized_net_c"] = dict(
    n_skip=len(sk), skipped_ev_c=round(100*mean(sk), 2),
    n_sized=len(sz), sized_ev_c=round(100*mean(sz), 2))
# simple binomial-ish bootstrap on skip mean < 0
import random
rng = random.Random(5)
cnt = 0
for _ in range(4000):
    samp = [sk[rng.randrange(len(sk))] for _ in range(len(sk))]
    if mean(samp) >= 0:
        cnt += 1
res["measure_skip_vs_sized_net_c"]["p_skipEV_ge0_iidboot"] = round(cnt/4000, 4)

# (e) binomial p for cap-miss counterfactual: 11/13 unique-t0 wins
def binom_sf(k, n, p):
    # P(X >= k)
    from math import comb
    return sum(comb(n, i) * p**i * (1-p)**(n-i) for i in range(k, n+1))
res["cap_miss_binomial"] = {
    "obs": "11/13 unique-t0 wins (q=.846)",
    "p_vs_q0.5": round(binom_sf(11, 13, 0.5), 4),
    "p_vs_q0.5874_breakeven_at_54c": round(binom_sf(11, 13, 0.5874), 4),
    "p_vs_q0.5673_breakeven_at_55c": round(binom_sf(11, 13, 0.5673), 4),
    "n_reasons_tested_multiplicity": 7,
}

json.dump(res, open("/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work/micro/a7_refine.json", "w"), indent=1)
print(json.dumps(res, indent=1))
