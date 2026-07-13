#!/usr/bin/env python3
"""Independent (pure-stdlib, no patched-module imports) recomputation of the
wave-2 unit's headline numbers from the raw data extracts."""
import json, math

DATA = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data"
FEE = 0.07
ex = json.load(open(DATA + "/state_extract.json"))
tr = json.load(open(DATA + "/trades_unified.json"))
measure = ex["measure"]
cfg = ex["impulse_cfg"]

print("measure rows:", len(measure))

# flagship ledger by t0 (dedup across _src)
fl = {}
for t in tr:
    if t.get("eng") == "impulse_v2" and isinstance(t.get("t0"), (int, float)) \
       and isinstance(t.get("entry"), (int, float)):
        fl.setdefault(int(t["t0"]), t)
print("flagship ledger unique t0:", len(fl))

# joins: t0 in ledger AND side matches
joins = [(m, fl[int(m["t0"])]) for m in measure
         if int(m["t0"]) in fl and fl[int(m["t0"])]["side"] == m["side"]]
side_mismatch = [m for m in measure if int(m["t0"]) in fl
                 and fl[int(m["t0"])]["side"] != m["side"]]
orphan_sk = [m for m, t in joins if not m["sized"]]
print("joins:", len(joins), "| side mismatches:", len(side_mismatch),
      "| joined rows that were recorded as skips:", len(orphan_sk),
      "| skip reasons:", sorted(set(m.get("skip") for m in orphan_sk)))

# kill preview bases on settled rows
settled = [m for m in measure if m.get("win") is not None]
def netps(rows, costf):
    return sum((1 - costf(m)) if m["win"] else -costf(m) for m in rows) / len(rows)
jt0 = {int(m["t0"]): t for m, t in joins}
def opcost(m):
    t = jt0.get(int(m["t0"]))
    if t is not None:
        e = t["entry"]
        return round(e + FEE * e * (1 - e), 4)
    return m["cost"]   # legacy never-entered: first-poll fallback (no bestCost exists)
fp = netps(settled, lambda m: m["cost"])
op = netps(settled, opcost)
print(f"settled n={len(settled)}  first-poll {fp*100:+.3f}c/sh  operated {op*100:+.3f}c/sh  gap {(op-fp)*100:+.3f}c")
never = [m for m in settled if int(m["t0"]) not in jt0]
print("settled never-entered legacy rows priced at first-poll:", len(never),
      f" their first-poll netps {netps(never, lambda m: m['cost'])*100:+.2f}c")

# old formula reproduction at the Jul-13 nightly
due = cfg["lastNightly"]
sd = [m for m in settled if m["t0"] + 600 <= due]
def qold(lo):
    xs = [m for m in sd if (m["cost"] < 0.50) == lo]
    seed = 0.5057 if lo else 0.5068
    return round(min(0.56, (sum(m["win"] for m in xs) + 400 * seed) / (len(xs) + 400)), 4)
print("old-formula qlo/qhi:", qold(True), qold(False), "state:", cfg["qlo"], cfg["qhi"])

# new registered formula on operated basis, p_eff buckets (quadratic inverse, own impl)
def p_eff(c):
    disc = (1 + FEE) ** 2 - 4 * FEE * c
    return round(((1 + FEE) - math.sqrt(disc)) / (2 * FEE), 6)
def qnew(lo):
    xs = [m for m in settled if (p_eff(opcost(m)) < 0.50) == lo]
    return round(min(0.56, (sum(m["win"] for m in xs) + 100) / (len(xs) + 200)), 4), \
           len(xs), sum(m["win"] for m in xs)
print("new qlo:", qnew(True), " new qhi:", qnew(False))

# sized boundary: f>0 iff cost < qh -> p_eff threshold
for q in (cfg["qlo"], qnew(True)[0]):
    print(f"  qh={q}: sized iff p_eff < {p_eff(q):.4f} (ask < {p_eff(q)-0.01:.4f})")

# cap diagnostic: first polls with ask > 0.47  (p_eff > 0.48)
capped = sum(1 for m in measure if p_eff(m["cost"]) > 0.48 + 1e-9)
print(f"first polls with ask>47c: {capped}/{len(measure)}")

# R4 headline sanity: wins on settled book
print("settled wins:", sum(m["win"] for m in settled), "/", len(settled))
