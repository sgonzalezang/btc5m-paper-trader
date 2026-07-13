"""A4: partial fills — frequency of fillFrac<1 / stake<reqStake, and whether partial-fill
signals (thin book at the touch) perform differently from full fills.
"""
import json, collections, sys
sys.path.insert(0, "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work/micro")
from common import load_trades, mean, block_boot_diff

T = [x for x in load_trades() if x.get("fillFrac") is not None]

res = {}
ff = [x["fillFrac"] for x in T]
res["n_with_fillFrac"] = len(T)
res["frac_partial_lt1"] = round(sum(1 for v in ff if v < 0.999) / len(ff), 4)
res["fillFrac_dist"] = dict(collections.Counter(
    "1.0" if v >= 0.999 else ("0.75-1" if v >= 0.75 else ("0.5-0.75" if v >= 0.5 else "<0.5")) for v in ff))

# reqStake vs stake mismatch
mism = [x for x in T if x.get("reqStake") is not None and abs(x["stake"] - x["reqStake"]) > 0.01]
res["n_stake_lt_reqStake"] = len(mism)

part = [x for x in T if x["fillFrac"] < 0.999]
full = [x for x in T if x["fillFrac"] >= 0.999]
if len(part) >= 10:
    d, lo, hi, p = block_boot_diff([x["_evps"] for x in part], [x["_blk"] for x in part],
                                   [x["_evps"] for x in full], [x["_blk"] for x in full])
    res["partial_vs_full"] = dict(
        n_partial=len(part), n_full=len(full),
        wr_partial=round(mean([x["_w"] for x in part]), 4),
        wr_full=round(mean([x["_w"] for x in full]), 4),
        entry_partial=round(mean([x["entry"] for x in part]), 4),
        entry_full=round(mean([x["entry"] for x in full]), 4),
        evps_partial_c=round(100*mean([x["_evps"] for x in part]), 2),
        evps_full_c=round(100*mean([x["_evps"] for x in full]), 2),
        diff_c=round(100*d, 2), ci95_c=[round(100*lo, 2), round(100*hi, 2)], p_diff_le0=round(p, 4),
        by_eng_partial=dict(collections.Counter(x["eng"] for x in part)))
else:
    res["partial_vs_full"] = dict(n_partial=len(part), note="too few partial fills for inference")

json.dump(res, open("/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work/micro/a4_fillfrac.json", "w"), indent=1)
print(json.dumps(res, indent=1))
