#!/usr/bin/env python3
"""Part 3: entry-timing mechanics on common signals, stake-weighting quality,
kill-metric bias note, and qhi boundary-record reconciliation. Appends to results.json."""
import json, math, datetime

DATA = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data"
WORK = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work/flagship"
state  = json.load(open(f"{DATA}/state_extract.json"))
trades = json.load(open(f"{DATA}/trades_unified.json"))
R      = json.load(open(f"{WORK}/results.json"))

def cost_of(p): return p + 0.07*p*(1-p)
def ps(tr):
    return (1-cost_of(tr["entry"])) if tr["result"]=="win" else -cost_of(tr["entry"])

bt = {e: {t["t0"]: t for t in trades if t["eng"]==e and t["status"]=="settled"} for e in ("impulse_v2","impulse50")}
common = sorted(set(bt["impulse_v2"]) & set(bt["impulse50"]))
rows = []
for t0 in common:
    a, b = bt["impulse_v2"][t0], bt["impulse50"][t0]
    rows.append(dict(t0=t0, sec_v2=a.get("entrySec"), sec_50=b.get("entrySec"),
                     e_v2=a["entry"], e_50=b["entry"], result=a["result"]))
same_price = [r for r in rows if abs(r["e_v2"]-r["e_50"]) < 0.005]
cheaper    = [r for r in rows if r["e_v2"] < r["e_50"] - 0.005]
richer     = [r for r in rows if r["e_v2"] > r["e_50"] + 0.005]
def mn(xs): return sum(xs)/len(xs) if xs else None
R["sizing_mechanics"] = {
 "common_pairs": len(rows),
 "same_price_pairs": {"n": len(same_price), "mean_sec_v2": mn([r["sec_v2"] for r in same_price]),
                      "wins": sum(1 for r in same_price if r["result"]=="win")},
 "v2_cheaper_pairs": {"n": len(cheaper), "mean_advantage_c": round(100*mn([r["e_50"]-r["e_v2"] for r in cheaper]),2) if cheaper else None,
                      "mean_sec_v2": mn([r["sec_v2"] for r in cheaper]), "mean_sec_50": mn([r["sec_50"] for r in cheaper]),
                      "wins": sum(1 for r in cheaper if r["result"]=="win")},
 "v2_richer_pairs": {"n": len(richer)},
 "note": "v2 enters later than the flat twin only when the first poll priced above the qhat threshold; the f>0 rule = an implicit limit order at ~48.9c effective"}

# stake-weighting quality within impulse_v2's own book
iv2 = sorted(bt["impulse_v2"].values(), key=lambda t: t["t0"])
tot_stake = sum(t["stake"] for t in iv2)
sw = sum(ps(t)*t["stake"] for t in iv2)/tot_stake      # stake-weighted per-share return
ew = mn([ps(t) for t in iv2])
R["stake_weighting_quality"] = {
 "n": len(iv2), "equal_weight_ps_c": round(100*ew,2), "stake_weight_ps_c": round(100*sw,2),
 "delta_c": round(100*(sw-ew),2),
 "note": "positive delta = bigger stakes landed on better trades; magnitude at n=26 is noise-level"}

# kill-metric bias: measurement book (first-poll cost) vs operated book
meas = state["measure"]; sett=[m for m in meas if m["win"] is not None]
mnet = mn([(1-m["cost"]) if m["win"] else -m["cost"] for m in sett])
onet = ew
R["kill_metric_tension"] = {
 "measurement_book_net_ps_c": round(100*mnet,2),
 "operated_flagship_net_ps_c": round(100*onet,2),
 "gap_c": round(100*(onet-mnet),2),
 "issue": "Phase-1 kill (day-14, -2c bar) reads the measurement book at FIRST-POLL cost; the operated arm systematically fills cheaper (re-poll under the f>0 threshold). The kill metric can fire on a policy whose operated book is positive. The design intended the measurement book to BE the would-be-fill book (fast first fill); the sizer's wait behavior was not anticipated by that definition."}

# qhi boundary reconciliation: find the extra hi-bucket win around the nightly cutoff
lastN = state["impulse_cfg"]["lastNightly"]
cands = [m for m in meas if m["win"] is not None and m["cost"] >= 0.50 and abs(m["t0"]+300-lastN) <= 900]
R["qhat_reconciliation"]["qhi_boundary_note"] = {
 "records_near_cutoff": [{"t0": m["t0"], "utc": datetime.datetime.utcfromtimestamp(m["t0"]).isoformat(),
                          "cost": m["cost"], "win": m["win"]} for m in cands],
 "explanation": "state qhi=0.5030 corresponds to (6 wins,15 fills); strict t0+300<=nightly gives (5,14). One hi-bucket winner settling at the 00:10 boundary (PM resolution lag ~1-2 min, nightly tick runs on the next poll) accounts for the 0.0013 gap. qlo matches exactly."}

json.dump(R, open(f"{WORK}/results.json","w"), indent=1)
print(json.dumps({k: R[k] for k in ("sizing_mechanics","stake_weighting_quality","kill_metric_tension")}, indent=1))
print(json.dumps(R["qhat_reconciliation"]["qhi_boundary_note"], indent=1))
