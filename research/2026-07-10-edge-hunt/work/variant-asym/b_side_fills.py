"""(b) Side-conditional fill realism for the reversal family.

1. pm_prices_sample.json: for markets whose t0 sits on the cb5m grid with a completed
   prior |move| >= 12bps, what does the CONTRARIAN side cost at t0+20s?
   fade-after-up  -> Down token ~ (1 - p20); fade-after-down -> Up token ~ p20.
   (p20 is the Up-token price snapshot; no bid/ask, so treat as cost proxy like
   work/crossasset/b2_pm_pricing.py did. Availability at effective <= .525 mirrors
   checks.json avail_pm_le_525.)
2. trades.json: 155-fill live reversal family (reversal/reversal2/latentfire),
   win rate + entry stats by side.
"""
import sys, json
SCR = "/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad"
sys.path.insert(0, SCR + "/work/crossasset")
from util import load, prior_oo, outcomes, pct

cb = load("cb5m")
t0map = {t: i for i, t in enumerate(cb["t"])}
pb = prior_oo(cb["o"])
out = outcomes(cb["o"], cb["c"])
pm = load("pm_prices_sample")
res = {}

rows = []
for mkt in pm:
    i = t0map.get(mkt["t0"])
    if i is None or i == 0 or pb[i] is None:
        continue
    m = abs(pb[i]) * 1e4
    if m < 12:
        continue
    if mkt.get("p20") is None:
        continue
    if pb[i] > 0:   # fade up -> buy Down
        side, cost = "down", 1.0 - mkt["p20"]
        won = 1 - mkt["up_won"]
    else:
        side, cost = "up", mkt["p20"]
        won = mkt["up_won"]
    rows.append(dict(t0=mkt["t0"], side=side, cost=cost, won=won, move=m))

print(f"pm sample: {len(rows)} reversal signals with p20 snapshots (of {len(pm)} markets)")
res["pm_side_pricing"] = {}
for side in ("down", "up"):
    cs = [r["cost"] for r in rows if r["side"] == side]
    ws = [r["won"] for r in rows if r["side"] == side]
    if not cs:
        continue
    avail = sum(1 for c in cs if c <= 0.525) / len(cs)
    d = {"n": len(cs), "mean_cost20": sum(cs) / len(cs),
         "p25": pct(cs, .25), "p50": pct(cs, .5), "p75": pct(cs, .75),
         "avail_le_525": avail, "won_rate_in_sample": sum(ws) / len(ws)}
    res["pm_side_pricing"][side] = d
    print(f"  contrarian {side:4s}: n={d['n']:3d} cost20 mean={d['mean_cost20']:.4f} "
          f"p25/50/75={d['p25']:.3f}/{d['p50']:.3f}/{d['p75']:.3f} avail<=.525={avail:.3f} won={d['won_rate_in_sample']:.3f}")

both = [r["cost"] for r in rows]
res["pm_side_pricing"]["pooled"] = {"n": len(both), "mean": sum(both) / len(both),
                                    "p50": pct(both, .5),
                                    "avail_le_525": sum(1 for c in both if c <= 0.525) / len(both)}

# ---- live family ledger by side ----
tr = load("trades")
fam = [x for x in tr if x.get("eng") in ("reversal", "reversal2", "latentfire")
       and x.get("status") == "settled"]
print(f"\nlive family fills: {len(fam)}")
res["ledger_side"] = {}
for side in ("down", "up"):
    s = [x for x in fam if x.get("side") == side]
    wins = sum(1 for x in s if x.get("result") == "win")
    entries = [x["entry"] for x in s if x.get("entry") is not None]
    pnl = sum(x.get("pnl", 0) for x in s)
    d = {"n": len(s), "wins": wins, "q": wins / len(s) if s else float("nan"),
         "entry_mean": sum(entries) / len(entries) if entries else None,
         "entry_p50": pct(entries, .5), "pnl_usd": round(pnl, 2)}
    res["ledger_side"][side] = d
    print(f"  side {side:4s}: n={d['n']:3d} q={d['q']:.4f} entry mean={d['entry_mean']:.4f} p50={d['entry_p50']:.3f} pnl=${d['pnl_usd']}")

# censored <=.53 effective-cost subset by side (matches MF2 anchors)
res["ledger_side_cap53"] = {}
for side in ("down", "up"):
    s = [x for x in fam if x.get("side") == side and x.get("entry") is not None
         and x["entry"] <= 0.53]
    wins = sum(1 for x in s if x.get("result") == "win")
    entries = [x["entry"] for x in s]
    d = {"n": len(s), "wins": wins, "q": wins / len(s) if s else float("nan"),
         "entry_mean": sum(entries) / len(entries) if entries else None}
    res["ledger_side_cap53"][side] = d
    print(f"  cap53 {side:4s}: n={d['n']:3d} q={d['q']:.4f} entry mean={d['entry_mean'] and round(d['entry_mean'],4)}")

json.dump(res, open(SCR + "/work/variant-asym/b_side_fills_results.json", "w"), indent=1)
print("\nsaved b_side_fills_results.json")
