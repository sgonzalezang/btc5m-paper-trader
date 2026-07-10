#!/usr/bin/env python3
"""Resolve pm-snapshot vs ledger contradiction.
1. Overlap ledger reversal trades with pm_prices_sample by t0: compare actual entry
   price vs p20_side + slip; win rates on the overlap.
2. Ledger q by entry-price bucket (does cheap fill -> low q inside real fills?).
3. Ledger per-$ EV with exact fee recomputation as sanity.
4. Timing: entrySec distribution of the family.
"""
import json, os

SCRATCH = "/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad"
D = os.path.join(SCRATCH, "data")
W = os.path.join(SCRATCH, "work", "verify-sizing")

def cost(p): return p + 0.07 * p * (1 - p)

tr = json.load(open(os.path.join(D, "trades.json")))
fam = [x for x in tr if x.get("eng") in ("reversal", "reversal2", "latentfire")
       and x.get("status") == "settled"]
pm = {r["t0"]: r for r in json.load(open(os.path.join(D, "pm_prices_sample.json")))}

# 1. overlap
ov = []
for x in fam:
    r = pm.get(x["t0"])
    if not r or r.get("p20") is None: continue
    side_up = 1 if x["side"] == "up" else 0
    p20_side = r["p20"] if side_up else round(1 - r["p20"], 4)
    ov.append({"t0": x["t0"], "eng": x["eng"], "entry": x["entry"], "ask": x["ask"],
               "entrySec": x.get("entrySec"), "p20_side": p20_side,
               "p20_fill": round(p20_side + 0.01, 4),
               "win": 1 if x["result"] == "win" else 0,
               "win_pm": 1 if side_up == r["up_won"] else 0})
print("overlap n =", len(ov))
if ov:
    diffs = sorted(x["p20_fill"] - x["entry"] for x in ov)
    m = len(diffs)
    print("p20fill - actual entry: p10=%.3f p50=%.3f p90=%.3f mean=%.4f" %
          (diffs[m//10], diffs[m//2], diffs[9*m//10], sum(diffs)/m))
    print("q on overlap (ledger result):", sum(x["win"] for x in ov)/len(ov),
          " mean entry:", sum(x["entry"] for x in ov)/len(ov))
    # would-be q if we'd required p20_fill <= 0.55
    f20 = [x for x in ov if x["p20_fill"] <= 0.55]
    print("subset with p20_fill<=0.55: n=%d q=%.3f" % (len(f20), sum(x["win"] for x in f20)/len(f20) if f20 else -1))

# 2. ledger q by entry bucket
buckets = [(0.0, 0.45), (0.45, 0.50), (0.50, 0.52), (0.52, 0.56)]
print("\nledger q by entry price (n=%d):" % len(fam))
for lo, hi in buckets:
    b = [x for x in fam if lo < x["entry"] <= hi]
    if not b: continue
    q = sum(1 for x in b if x["result"] == "win") / len(b)
    me = sum(x["entry"] for x in b) / len(b)
    print(f" ({lo:.2f},{hi:.2f}] n={len(b):3d} meanEntry={me:.3f} q={q:.3f} hurdle={cost(me):.3f} evshare={q-cost(me):+.3f}")

# 3. exact-fee EV recomputation from ledger fills
tot_pnl = sum(x["pnl"] for x in fam)
tot_stake = sum(x["stake"] for x in fam)
q_all = sum(1 for x in fam if x["result"] == "win") / len(fam)
me_all = sum(x["entry"] for x in fam) / len(fam)
print(f"\nledger: n={len(fam)} q={q_all:.4f} meanEntry={me_all:.4f} "
      f"hurdle(meanEntry)={cost(me_all):.4f} pnl/${tot_pnl/tot_stake:+.4f}")

# per-share EV implied at ledger q & per-trade honest fills
ev_dollar = sum(( (1 if x['result']=='win' else 0) - cost(x["entry"]) ) / cost(x["entry"]) for x in fam) / len(fam)
print("per-$ EV with exact fee at actual fills:", round(ev_dollar, 4))

# 4. timing
es = sorted(x.get("entrySec", 0) for x in fam)
print("entrySec: p10=%s p50=%s p90=%s" % (es[len(es)//10], es[len(es)//2], es[9*len(es)//10]))

json.dump({"overlap_n": len(ov)}, open(os.path.join(W, "attack_calibrate_done.json"), "w"))
