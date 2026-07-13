"""T4: Time-in-interval pricing.
(a) pm_prices_sample (Up price at 20s/60s/150s): on 12bps-trigger intervals,
    what does the CONTRARIAN side cost at each second, and what is EV at each
    entry time under the frozen model (snapshot+1c as fill)?
(b) Same for ALL intervals (does the book drift toward the eventual winner --
    how fast does information get priced?).
(c) Ledger: reversal-family q and entry price by entrySec bucket.
"""
import json, collections
import common as C

out = {}
pm = C.load_pm_prices()
cb = C.cb5m_map()
res, _ = C.resolution_map()

# --- (a) trigger intervals in the sample
trig = []
for r in pm:
    t0 = r["t0"]
    prev, cur = cb.get(t0 - 300), cb.get(t0)
    if not prev or not cur: continue
    mv = (cur["o"] - prev["o"]) / prev["o"]
    if abs(mv) < 0.0012: continue
    side_up = mv <= 0                      # contrarian: fade the prior move
    win = r["up_won"] if side_up else 1 - r["up_won"]
    row = dict(t0=t0, side="up" if side_up else "down", win=win)
    for snap in ("p20", "p60", "p150"):
        p = r.get(snap)
        row[snap] = (p if side_up else round(1 - p, 4)) if p is not None else None
    trig.append(row)
out["n_sample_triggers"] = len(trig)

def ev_at(snap, rows, cap=None):
    pairs, costs = [], []
    for r in rows:
        p = r.get(snap)
        if p is None: continue
        if cap is not None and p + 0.01 > cap: continue
        fill = p + 0.01
        pairs.append((r["t0"], r["win"] - fill - C.FEE * fill * (1 - fill)))
        costs.append(fill)
    if not pairs: return dict(n=0)
    bb = C.block_boot_mean(pairs)
    w = sum(1 for r in rows if r.get(snap) is not None
            and (cap is None or r[snap] + 0.01 <= cap) and r["win"])
    return dict(n=len(pairs), mean_fill=round(sum(costs)/len(costs), 4),
                wr=round(w/len(pairs), 4), ev_c=round(bb["mean"]*100, 2),
                ci_c=[round(bb["lo95"]*100, 2), round(bb["hi95"]*100, 2)],
                p_le_0=bb["p_le_0"])

for snap in ("p20", "p60", "p150"):
    out[f"trigger_contra_{snap}_uncapped"] = ev_at(snap, trig)
    out[f"trigger_contra_{snap}_cap53"] = ev_at(snap, trig, cap=0.53)

# --- (b) book informativeness over time, all 216 markets:
# P(eventual winner's price at snap >= 0.5) and mean winner-side price
allrows = []
for r in pm:
    row = dict(t0=r["t0"])
    for snap in ("p20", "p60", "p150", "pLast"):
        p = r.get(snap)
        row["w" + snap] = (p if r["up_won"] else (1 - p)) if p is not None else None
    allrows.append(row)
for snap in ("p20", "p60", "p150", "pLast"):
    vals = [r["w" + snap] for r in allrows if r["w" + snap] is not None]
    out[f"winner_price_{snap}"] = dict(
        n=len(vals), mean=round(sum(vals)/len(vals), 4),
        frac_ge_half=round(sum(1 for v in vals if v >= 0.5)/len(vals), 4))

# --- (c) ledger entrySec: reversal-family fills, PM settled
REV = {"reversal", "reversal2", "reversal_v2", "latentfire", "impulse_v2", "impulse50"}
rows = [t for t in C.load_trades()
        if t["eng"] in REV and t.get("status") == "settled"
        and (t.get("settledBy") or "").startswith("polymarket")
        and t.get("entrySec") is not None and t.get("entry") is not None]
BUCK = [(0, 15), (15, 45), (45, 90), (90, 300)]
tab = []
for lo, hi in BUCK:
    sel = [t for t in rows if lo <= t["entrySec"] < hi]
    if not sel:
        tab.append(dict(sec=f"[{lo},{hi})", n=0)); continue
    w = sum(1 for t in sel if t["result"] == "win")
    mp = sum(t["entry"] for t in sel) / len(sel)
    q, l, h = C.wilson(w, len(sel))
    tab.append(dict(sec=f"[{lo},{hi})", n=len(sel), mean_entry=round(mp, 4),
                    q=round(q, 4), ci=[round(l, 4), round(h, 4)],
                    ev_c=round(C.ev_share(mp, q)*100, 2)))
out["ledger_rev_by_entrysec"] = tab

json.dump(out, open("timing.json", "w"), indent=1)
print(json.dumps(out, indent=1))
