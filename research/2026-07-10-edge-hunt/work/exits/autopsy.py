#!/usr/bin/env python3
"""(a) Adverse-excursion autopsy of settled win/loss trades.

For each trade, fv_side at checkpoints 60/120/180/240s (post-entry only).
- Losers: 'recoverable' = fv_side >= thresh at some post-entry checkpoint
  (could have exited at salvage value). Salvage = best sell proceeds/cost.
- Winners: 'dipped hard' = fv_side <= thresh at some post-entry checkpoint
  (a stop would have fired on a winner).
Output: work/exits/autopsy.json + printed table.
"""
import json

SCRATCH = "/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad"
rows = json.load(open(SCRATCH + "/work/exits/joined.json"))

def post_entry_cps(r):
    es = r["entrySec"] if r["entrySec"] is not None else 30
    out = []
    for s in (60, 120, 180, 240):
        if s > es:
            f = r["fv_up"][str(s)] if r["side"] == "up" else 1 - r["fv_up"][str(s)]
            out.append((s, f))
    return out

def sell_proceeds_per_share(f):
    q = max(0.01, f - 0.02)          # 2c spread haircut
    return q - 0.07 * q * (1 - q)    # minus second taker fee

losers = [r for r in rows if not r["win"]]
winners = [r for r in rows if r["win"]]
print(f"n trades: {len(rows)}  winners: {len(winners)}  losers: {len(losers)}")

res = {"n": len(rows), "winners": len(winners), "losers": len(losers)}

print("\nLOSERS: fraction with fv_side >= X at some post-entry checkpoint (recoverable)")
for X in (0.45, 0.50, 0.55, 0.60, 0.70):
    frac = sum(1 for r in losers if any(f >= X for _, f in post_entry_cps(r))) / len(losers)
    print(f"  X={X:.2f}: {frac:.3f}")
    res[f"losers_recoverable_{X}"] = round(frac, 4)

# average best salvage fraction of cost for losers (sell at best checkpoint vs lose all)
sal = []
for r in losers:
    cps = post_entry_cps(r)
    if not cps:
        continue
    best = max(sell_proceeds_per_share(f) for _, f in cps)
    sal.append(best / r["entry"])  # fraction of cost recoverable at best exit
sal.sort()
print(f"  best-salvage/cost for losers: median {sal[len(sal)//2]:.2f}, "
      f"mean {sum(sal)/len(sal):.2f}, p25 {sal[len(sal)//4]:.2f}, p75 {sal[3*len(sal)//4]:.2f}")
res["loser_salvage_median"] = round(sal[len(sal)//2], 3)
res["loser_salvage_mean"] = round(sum(sal)/len(sal), 3)

print("\nWINNERS: fraction with fv_side <= X at some post-entry checkpoint (dipped hard)")
for X in (0.20, 0.25, 0.30, 0.35, 0.40, 0.45):
    frac = sum(1 for r in winners if any(f <= X for _, f in post_entry_cps(r))) / len(winners)
    print(f"  X={X:.2f}: {frac:.3f}")
    res[f"winners_dipped_{X}"] = round(frac, 4)

# conditional forward win rate: given fv_side <= X at checkpoint s, P(win) — the number a stop bets against
print("\nP(win | fv_side <= X at s)  [what a stop at (X, s) throws away]")
for X in (0.20, 0.30, 0.40):
    line = []
    for s in (60, 120, 180, 240):
        w = n = 0
        for r in rows:
            es = r["entrySec"] if r["entrySec"] is not None else 30
            if s <= es:
                continue
            f = r["fv_up"][str(s)] if r["side"] == "up" else 1 - r["fv_up"][str(s)]
            if f <= X:
                n += 1
                w += r["win"]
        line.append(f"s={s}: {w/n:.3f} (n={n})" if n else f"s={s}: n=0")
    print(f"  X={X:.2f}  " + "  ".join(line))

# EV comparison at the decision point: hold EV/share = P(win|state); sell EV/share = proceeds(f)
print("\nAt each (X,s) trigger: mean sell proceeds/share vs realized hold value/share")
tbl = []
for X in (0.20, 0.30, 0.40):
    for s in (60, 120, 180, 240):
        sells, holds = [], []
        for r in rows:
            es = r["entrySec"] if r["entrySec"] is not None else 30
            if s <= es:
                continue
            f = r["fv_up"][str(s)] if r["side"] == "up" else 1 - r["fv_up"][str(s)]
            if f <= X:
                sells.append(sell_proceeds_per_share(f))
                holds.append(float(r["win"]))
        if sells:
            ms, mh = sum(sells)/len(sells), sum(holds)/len(holds)
            tbl.append({"X": X, "s": s, "n": len(sells), "sell": round(ms, 3),
                        "hold": round(mh, 3), "delta": round(ms - mh, 3)})
            print(f"  X={X:.2f} s={s}: n={len(sells)} sell={ms:.3f} hold={mh:.3f} delta={ms-mh:+.3f}/share")
res["trigger_table"] = tbl
json.dump(res, open(SCRATCH + "/work/exits/autopsy.json", "w"), indent=1)
print("\nwrote work/exits/autopsy.json")
