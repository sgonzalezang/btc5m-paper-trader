#!/usr/bin/env python3
"""
Part 2: (a) reconcile state qlo/qhi against the bot nightly's exact formula;
(b) gate-retention conformance from Coinbase 5m candles (pre-registered Phase-0
band 0.40-0.70); (c) verify the 7 'gate-rejected' reversal_v2 t0s truly fail
the gate on candle-computed eff6/cnt12. Appends to results.json.
"""
import json, datetime

DATA = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data"
WORK = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work/flagship"

state  = json.load(open(f"{DATA}/state_extract.json"))
trades = json.load(open(f"{DATA}/trades_unified.json"))
cb     = json.load(open(f"{DATA}/cb5m.json"))
R      = json.load(open(f"{WORK}/results.json"))

meas = state["measure"]; icfg = state["impulse_cfg"]
SEED_LO, SEED_HI, PRIOR = 0.5057, 0.5068, 400
lastN = icfg["lastNightly"]          # 00:10 UTC of the last nightly run

# ---- (a) qhat reconciliation: replicate _impulse_nightly at lastNightly ----
# settled by the nightly = records whose interval closed (t1 = t0+300) before it
def qhat_at(cut_ts):
    sett = [m for m in meas if m["win"] is not None and m["t0"] + 300 <= cut_ts]
    lo = [m for m in sett if m["cost"] < 0.50]; hi = [m for m in sett if m["cost"] >= 0.50]
    qlo = round(min(0.56, (sum(m["win"] for m in lo) + PRIOR*SEED_LO) / (len(lo) + PRIOR)), 4)
    qhi = round(min(0.56, (sum(m["win"] for m in hi) + PRIOR*SEED_HI) / (len(hi) + PRIOR)), 4)
    return dict(n_lo=len(lo), w_lo=sum(m["win"] for m in lo), qlo=qlo,
                n_hi=len(hi), w_hi=sum(m["win"] for m in hi), qhi=qhi)

now_est = qhat_at(10**12)   # everything settled
at_nightly = qhat_at(lastN)
# design-spec formula for contrast: (wins+100)/(n+200), bucket by p_eff<0.50 (cost<0.5175)
sett = [m for m in meas if m["win"] is not None]
dlo = [m for m in sett if m["cost"] < 0.5175]; dhi = [m for m in sett if m["cost"] >= 0.5175]
design_qlo = round((sum(m["win"] for m in dlo) + 100) / (len(dlo) + 200), 4)
design_qhi = round((sum(m["win"] for m in dhi) + 100) / (len(dhi) + 200), 4)

R["qhat_reconciliation"] = {
 "state": {"qlo": icfg["qlo"], "qhi": icfg["qhi"], "lastNightly_utc": datetime.datetime.utcfromtimestamp(lastN).isoformat()},
 "replicated_at_lastNightly": at_nightly,
 "match": (abs(at_nightly["qlo"]-icfg["qlo"]) < 5e-4 and abs(at_nightly["qhi"]-icfg["qhi"]) < 5e-4),
 "if_rerun_now_all_settled": now_est,
 "spec_deviations_in_bot": [
   "bucket boundary is cost<0.50 (= p_eff <~0.4831), NOT p_eff<0.50 as pre-registered (design MF2); the 'hi' bucket therefore contains 48-53c fills",
   "prior mass 400 PER BUCKET seeded at ledger seeds (qhat=(w+400*seed)/(n+400)); design section 4.2 pre-registered (w+100)/(n+200) per bucket (mass 200). Learning is ~2x slower than designed",
   "guard windows NOT seeded with the pre-launch n=123 ledger (design M2); netps() returns None below min-n so bench/haircut cannot fire before ~day 7-8",
 ],
 "design_formula_for_contrast": {"qlo": design_qlo, "qhi": design_qhi,
   "note": "design buckets by p_eff<0.50 and prior mass 200/bucket, on all 35 settled"},
 "sizing_threshold_implied": {
   "current": "f>0 iff cost < qlo=0.5068 iff p_eff <= 0.4886 (lo bucket); hi bucket dead (qhi=0.503 < min hi cost 0.50)",
   "comment": "the qlo threshold sits almost exactly at the design's launch geometry (~0.488)"}
}

# ---- (b) gate retention from candles ----
t = cb["t"]; o = cb["o"]
idx = {ts: i for i, ts in enumerate(t)}
def gate_at(t0):
    """eff6/cnt12 for interval starting t0, trigger = move over [t0-300, t0). Needs 14 contiguous opens ending at t0."""
    i = idx.get(t0)
    if i is None or i < 13: return None
    opens = o[i-13:i+1]
    ts = t[i-13:i+1]
    if any(ts[k+1]-ts[k] != 300 for k in range(13)): return None
    trig = (opens[-1]-opens[-2])/opens[-2]
    legs = [opens[k+1]-opens[k] for k in range(7, 13)]           # last 6 moves incl trigger
    den = sum(abs(x) for x in legs)
    eff6 = abs(opens[-1]-opens[-7])/den if den > 0 else 1.0
    cnt12 = sum(1 for k in range(0, 12) if abs(opens[k+1]-opens[k])/opens[k] >= 0.0012)
    return dict(trig=trig*100, eff6=eff6, cnt12=cnt12,
                signal=abs(trig)*100 >= 0.12, gate=(eff6 >= 0.10 and cnt12 <= 6))

# live window = impulse50 era
t_lo, t_hi = 1783702500, 1783914000     # Jul 10 16:55 -> Jul 13 03:40 UTC
def retention(a, b):
    sig = gat = 0
    for t0 in range(a, b, 300):
        g = gate_at(t0)
        if g and g["signal"]:
            sig += 1; gat += g["gate"]
    return sig, gat
sig_live, gat_live = retention(t_lo, t_hi)
# longer context: last 21 days of candles
sig_21, gat_21 = retention(t[-1] - 21*86400, t[-1])
R["gate_retention_conformance"] = {
 "preregistered_band": [0.40, 0.70],
 "live_window": {"signals": sig_live, "gated": gat_live,
                 "retention": round(gat_live/sig_live, 4) if sig_live else None},
 "last_21d": {"signals": sig_21, "gated": gat_21,
              "retention": round(gat_21/sig_21, 4) if sig_21 else None},
 "note": "computed from cb5m opens with the bot's trigger-inclusive eff6 / pre-trigger cnt12 convention; outside the band = pre-registered gate-code-bug flag (Phase 0)"
}

# ---- (c) verify gate-rejected t0s ----
bt = {}
for e in ("impulse_v2", "impulse50", "reversal_v2"):
    bt[e] = {tr["t0"]: tr for tr in trades if tr["eng"] == e}
gated_t0 = set(bt["impulse50"]) | set(bt["impulse_v2"]) | {r["t0"] for r in meas}
tg = max(min(bt["impulse50"]), min(bt["reversal_v2"]))
rej = [t0 for t0, tr in sorted(bt["reversal_v2"].items())
       if t0 >= tg and tr["status"] == "settled" and t0 not in gated_t0]
rows = []
for t0 in rej:
    g = gate_at(t0)
    tr = bt["reversal_v2"][t0]
    rows.append(dict(t0=t0, utc=datetime.datetime.utcfromtimestamp(t0).isoformat(),
                     entry=tr["entry"], result=tr["result"],
                     eff6=(round(g["eff6"], 4) if g else None), cnt12=(g["cnt12"] if g else None),
                     gate_should_fail=(not g["gate"]) if g else None))
R["gate_rejected_verification"] = {
 "n": len(rows), "rows": rows,
 "all_verified_fail": all(r["gate_should_fail"] for r in rows if r["gate_should_fail"] is not None)}

json.dump(R, open(f"{WORK}/results.json", "w"), indent=1)
print(json.dumps({k: R[k] for k in ("qhat_reconciliation", "gate_retention_conformance", "gate_rejected_verification")}, indent=1))
