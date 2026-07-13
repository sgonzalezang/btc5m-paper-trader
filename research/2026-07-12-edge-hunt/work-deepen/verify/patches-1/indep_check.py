#!/usr/bin/env python3
"""Independent verification of wave-2 patch-unit numbers, from raw data only.
No reuse of the unit's helpers: own join, own qhat formulas, own inversion."""
import json, math

DATA = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data"
FEE = 0.07
ex = json.load(open(DATA + "/state_extract.json"))
tr = json.load(open(DATA + "/trades_unified.json"))
ms = ex["measure"]
cfg = ex["impulse_cfg"]

print("rows in measurement book:", len(ms))
settled = [m for m in ms if m.get("win") is not None]
print("settled:", len(settled))

# 1. first-poll basis
fp = sum((1 - m["cost"]) if m["win"] else -m["cost"] for m in settled) / len(settled)
print(f"1. first-poll basis: {fp*100:+.2f}c/sh on n={len(settled)}  (claim -6.23)")

# 2. join to flagship ledger by t0 (dedupe by t0)
fl = {}
for t in tr:
    if t.get("eng") == "impulse_v2" and t.get("t0") is not None and t.get("entry") is not None:
        fl.setdefault(int(t["t0"]), t)
print("   flagship ledger trades (unique t0):", len(fl))
joined = [(m, fl[int(m["t0"])]) for m in ms if int(m["t0"]) in fl and fl[int(m["t0"])]["side"] == m["side"]]
side_mismatch = [m for m in ms if int(m["t0"]) in fl and fl[int(m["t0"])]["side"] != m["side"]]
orph = [m for m, t in joined if not m.get("sized")]
orph_fnp = [m for m in orph if m.get("skip") == "f_nonpos"]
print(f"2. joined rows: {len(joined)} (claim 27), side mismatches: {len(side_mismatch)},"
      f" orphan skips repaired: {len(orph)} (f_nonpos: {len(orph_fnp)}; claim 12)")

# 3. operated basis: fillCost for joined, first-poll cost otherwise
fcost = {int(m["t0"]): (t["entry"] + FEE * t["entry"] * (1 - t["entry"])) for m, t in joined}
op = sum(((1 - fcost.get(int(m["t0"]), m["cost"])) if m["win"] else -fcost.get(int(m["t0"]), m["cost"]))
         for m in settled) / len(settled)
print(f"3. operated basis: {op*100:+.2f}c/sh (claim -2.40), gap {(op-fp)*100:+.2f}c (claim +3.84)")

# 3b. flagship's own settled trades, realized basis (R4 cross-check +3.55c on 26)
fs = [t for t in fl.values() if t.get("result") in ("win", "loss")]
opf = sum(((1 - (t["entry"] + FEE * t["entry"] * (1 - t["entry"]))) if t["result"] == "win"
           else -(t["entry"] + FEE * t["entry"] * (1 - t["entry"]))) for t in fs) / len(fs)
print(f"3b. flagship as-operated: {opf*100:+.2f}c/sh on n={len(fs)} (R4 said +3.55 on 26)")

# 4. old (deviating) formula reproduces live state
due = cfg["lastNightly"]
sd = [m for m in settled if m["t0"] + 600 <= due]
def old_q(lo):
    xs = [m for m in sd if (m["cost"] < 0.50) == lo]
    return round(min(0.56, (sum(m["win"] for m in xs) + 400 * (0.5057 if lo else 0.5068)) / (len(xs) + 400)), 4)
print(f"4. old formula qlo={old_q(True)} qhi={old_q(False)} vs state {cfg['qlo']}/{cfg['qhi']}")

# 5. registered formula, p_eff buckets, operated basis (own quadratic inverse)
def p_from_cost(c):  # c = p + FEE*p*(1-p)
    return ((1 + FEE) - math.sqrt((1 + FEE) ** 2 - 4 * FEE * c)) / (2 * FEE)
def new_q(lo):
    xs = [m for m in settled if (round(p_from_cost(fcost.get(int(m["t0"]), m["cost"])), 6) < 0.50) == lo]
    return round(min(0.56, (sum(m["win"] for m in xs) + 100) / (len(xs) + 200)), 4), len(xs), sum(m["win"] for m in xs)
lo, hi = new_q(True), new_q(False)
print(f"5. registered qlo={lo[0]} (n={lo[1]},w={lo[2]}) qhi={hi[0]} (n={hi[1]},w={hi[2]})"
      f"  (claim 0.4934 n27/w12, 0.4952 n8/w3)")
# sized boundaries: cost < q  =>  p_eff < p_from_cost(q)
print(f"   sized boundary p_eff: before {p_from_cost(cfg['qlo']):.4f} (claim .4893),"
      f" after {p_from_cost(lo[0]):.4f} (claim .4759); ask = p_eff - 0.01")

# 6. cap diagnostic: live first polls with ask > 0.47 (use recorded feature ask)
asks = [(m.get("f") or {}).get("ask") for m in ms]
n_ask = sum(1 for a in asks if a is not None)
over = sum(1 for a in asks if a is not None and a > 0.47 + 1e-9)
print(f"6. first polls with recorded ask>{0.47}: {over}/{n_ask} of {len(ms)} rows (claim 24/36)")

# 7. seed cohort from trades_unified with the R8 locator
LAUNCH = 1783695941
fam = [t for t in tr if t.get("eng") in ("reversal", "reversal2") and t["at"] / 1000 < LAUNCH
       and t.get("result") in ("win", "loss") and t.get("entry") is not None and t["entry"] <= 0.531]
net = sum(((1 - (t["entry"] + FEE * t["entry"] * (1 - t["entry"]))) if t["result"] == "win"
           else -(t["entry"] + FEE * t["entry"] * (1 - t["entry"]))) for t in fam) / len(fam)
print(f"7. seed cohort n={len(fam)} net {net*100:+.2f}c/sh (claim 123, +2.75)")

# 8. 7d guard window with seeds at the Jul-13 nightly (operated basis, seeds at own cost)
pool = [m for m in settled if m["t0"] >= due - 7 * 86400]
seedrows = [dict(cost=(t["entry"] + FEE * t["entry"] * (1 - t["entry"])), win=1 if t["result"] == "win" else 0,
                 t0=int(t["t0"])) for t in fam]
pool7 = [(fcost.get(int(m["t0"]), m["cost"]), m["win"]) for m in pool] + \
        [(r["cost"], r["win"]) for r in seedrows if r["t0"] >= due - 7 * 86400]
n7 = sum((1 - c) if w else -c for c, w in pool7) / len(pool7)
print(f"8. seeded 7d window: {n7*100:+.2f}c on n={len(pool7)} (claim +1.61 on 158);"
      f" haircut fires: {n7 < -0.02}, bench(7d<-4c): {n7 < -0.04}")

# 9. never-entered legacy rows priced at first poll inside the operated basis
never = [m for m in settled if int(m["t0"]) not in fcost]
nv = sum((1 - m["cost"]) if m["win"] else -m["cost"] for m in never) / len(never)
print(f"9. never-entered legacy rows: n={len(never)}, {nv*100:+.2f}c at first-poll cost"
      f" (R4 said 9 rows, 3/9 wins, -19.6c)  wins={sum(m['win'] for m in never)}")
