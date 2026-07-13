"""T2: q(p) on the pooled 3,490 PM-settled ledger, sliced by era/family/side.
Resolves the verify-regime ("expensive fills win more") vs ledger-autopsy
("q flat in price") contradiction with 3x more data.
Units: individual fills; CIs via 1h-block bootstrap (handles same-interval
cross-engine duplication as within-block correlation); dedup sensitivity too.
"""
import json, collections
import common as C

trades = C.load_trades()
out = {}

ERA = lambda t0: ("pre_reset" if t0 < 1783562400 else
                  "momentum_era" if t0 < C.V3_CUT else "v3")

def usable(tr):
    if tr.get("status") != "settled": return False
    if not (tr.get("settledBy") or "").startswith("polymarket"): return False
    if tr.get("result") not in ("win", "loss"): return False
    if tr.get("entry") is None: return False
    return True

U = [tr for tr in trades if usable(tr)]
out["n_usable"] = len(U)
out["excluded"] = collections.Counter(
    (tr.get("settledBy") or "none") for tr in trades
    if tr.get("status") == "settled" and not usable(tr))

BUCKETS = [(0.05,0.40),(0.40,0.45),(0.45,0.475),(0.475,0.50),
           (0.50,0.525),(0.525,0.55),(0.55,0.60),(0.60,0.66),(0.66,0.95)]

def fam(tr): return "contrarian" if tr["eng"] in C.CONTRARIAN else "momentum"

def table(rows, label):
    res = []
    for lo, hi in BUCKETS:
        sel = [t for t in rows if lo <= t["entry"] < hi]
        n = len(sel); w = sum(1 for t in sel if t["result"] == "win")
        if n == 0:
            res.append(dict(bucket=f"[{lo},{hi})", n=0)); continue
        pbar = sum(t["entry"] for t in sel) / n
        q, l, h = C.wilson(w, n)
        ev = C.ev_share(pbar, q)
        res.append(dict(bucket=f"[{lo},{hi})", n=n, mean_p=round(pbar,4),
                        q=round(q,4), ci=[round(l,4),round(h,4)],
                        ev_c_per_share=round(ev*100,2),
                        qstar=round(C.qstar(pbar),4)))
    return res

# --- full tables per era x family
for era in ("pre_reset","momentum_era","v3","ALL"):
    for f in ("momentum","contrarian"):
        rows = [t for t in U if fam(t)==f and (era=="ALL" or ERA(t["t0"])==era)]
        out[f"qp_{era}_{f}"] = dict(n=len(rows), table=table(rows, f"{era}/{f}"))

# --- side slices (contrarian only, the family that matters live)
for side in ("up","down"):
    rows = [t for t in U if fam(t)=="contrarian" and t["side"]==side]
    out[f"qp_contrarian_side_{side}"] = dict(n=len(rows), table=table(rows, side))

# --- THE KEY CONTRAST: within contrarian, cheap (<50c) vs expensive (>=50c)
def contrast(rows, label):
    lo_rows = [t for t in rows if t["entry"] < 0.50]
    hi_rows = [t for t in rows if t["entry"] >= 0.50]
    wl = sum(1 for t in lo_rows if t["result"]=="win")
    wh = sum(1 for t in hi_rows if t["result"]=="win")
    z, pv = C.two_prop_z(wh, len(hi_rows), wl, len(lo_rows))
    bb = C.block_boot_diff(
        [(t["t0"], 1.0 if t["result"]=="win" else 0.0) for t in hi_rows],
        [(t["t0"], 1.0 if t["result"]=="win" else 0.0) for t in lo_rows]) \
        if lo_rows and hi_rows else None
    return dict(label=label,
        lo=dict(n=len(lo_rows), w=wl, q=round(wl/len(lo_rows),4) if lo_rows else None,
                mean_p=round(sum(t["entry"] for t in lo_rows)/len(lo_rows),4) if lo_rows else None),
        hi=dict(n=len(hi_rows), w=wh, q=round(wh/len(hi_rows),4) if hi_rows else None,
                mean_p=round(sum(t["entry"] for t in hi_rows)/len(hi_rows),4) if hi_rows else None),
        two_prop_z=round(z,3), p=round(pv,4), block_boot_qhi_minus_qlo=bb)

cont = [t for t in U if fam(t)=="contrarian"]
out["contrast_contrarian_ALL"] = contrast(cont, "contrarian all eras")
out["contrast_contrarian_momentum_era"] = contrast(
    [t for t in cont if ERA(t["t0"])=="momentum_era"], "contrarian momentum-era")
out["contrast_contrarian_v3"] = contrast(
    [t for t in cont if ERA(t["t0"])=="v3"], "contrarian v3 era")
out["contrast_momentum_ALL"] = contrast(
    [t for t in U if fam(t)=="momentum"], "momentum all eras")

# dedup sensitivity: one contrarian fill per interval (first at-time)
byt0 = {}
for t in sorted(cont, key=lambda x: x["at"]):
    byt0.setdefault(t["t0"], t)
out["contrast_contrarian_dedup"] = contrast(list(byt0.values()), "contrarian dedup per t0")

# --- reversal-family only (12bps trigger engines), the live-relevant subset
REV = {"reversal","reversal2","reversal_v2","latentfire","impulse_v2","impulse50"}
rev = [t for t in U if t["eng"] in REV]
out["qp_reversal_family"] = dict(n=len(rev), table=table(rev, "rev-family"))
out["contrast_reversal_family"] = contrast(rev, "reversal family (12bps trigger)")
byt0r = {}
for t in sorted(rev, key=lambda x: x["at"]):
    byt0r.setdefault(t["t0"], t)
out["contrast_reversal_family_dedup"] = contrast(list(byt0r.values()), "rev family dedup")

json.dump(out, open("ledger_qp.json","w"), indent=1, default=str)
print("written; n_usable =", len(U))
