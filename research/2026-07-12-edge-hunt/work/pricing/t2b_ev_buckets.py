"""T2b: EV/share (frozen cost model) with 1h-block-boot CIs for the
reversal/trigger family, cheap vs expensive buckets, all-era and v3-only.
EV unit per fill: win - entry - 0.07*entry*(1-entry)  (entry = ask+1c already).
"""
import json
import common as C

trades = C.load_trades()
REV = {"reversal","reversal2","reversal_v2","latentfire","impulse_v2","impulse50"}

def usable(tr):
    return (tr.get("status")=="settled"
            and (tr.get("settledBy") or "").startswith("polymarket")
            and tr.get("result") in ("win","loss") and tr.get("entry") is not None)

rev = [t for t in C.load_trades() if usable(t) and t["eng"] in REV]

def ev_pairs(rows):
    out=[]
    for t in rows:
        w = 1.0 if t["result"]=="win" else 0.0
        p = t["entry"]
        out.append((t["t0"], w - p - C.FEE*p*(1-p)))
    return out

out = {}
segs = {
  "rev_all_lt50": [t for t in rev if t["entry"] < 0.50],
  "rev_all_ge50": [t for t in rev if t["entry"] >= 0.50],
  "rev_all_lt45": [t for t in rev if t["entry"] < 0.45],
  "rev_all_45_50": [t for t in rev if 0.45 <= t["entry"] < 0.50],
  "rev_all_50_55": [t for t in rev if 0.50 <= t["entry"] < 0.55],
  "rev_v3_lt50":  [t for t in rev if t["entry"] < 0.50 and t["t0"] >= C.V3_CUT],
  "rev_v3_ge50":  [t for t in rev if t["entry"] >= 0.50 and t["t0"] >= C.V3_CUT],
  "rev_pre_v3_lt50": [t for t in rev if t["entry"] < 0.50 and t["t0"] < C.V3_CUT],
  "rev_pre_v3_ge50": [t for t in rev if t["entry"] >= 0.50 and t["t0"] < C.V3_CUT],
}
for k, rows in segs.items():
    if rows:
        bb = C.block_boot_mean(ev_pairs(rows))
        wr = sum(1 for t in rows if t["result"]=="win")/len(rows)
        mp = sum(t["entry"] for t in rows)/len(rows)
        out[k] = dict(n=len(rows), wr=round(wr,4), mean_entry=round(mp,4),
                      ev_c=round(bb["mean"]*100,2),
                      ci_c=[round(bb["lo95"]*100,2), round(bb["hi95"]*100,2)],
                      p_le_0=bb["p_le_0"], blocks=bb["blocks"])
    else:
        out[k] = dict(n=0)

# paired contrast: lt50 vs ge50 EV difference, shared clock
bb = C.block_boot_diff(ev_pairs(segs["rev_all_lt50"]), ev_pairs(segs["rev_all_ge50"]))
out["diff_lt50_minus_ge50_all"] = {k: (round(v,4) if isinstance(v,float) else v) for k,v in bb.items()}

json.dump(out, open("ev_buckets.json","w"), indent=1)
for k,v in out.items(): print(k, v)
