#!/usr/bin/env python3
"""Generate impulse_guard_seed.json — the M2 (FINAL-DESIGN §5.3) guard-window
seed cohort. Deterministic reconstruction of the pre-launch cap-censored live
family ledger, exactly as located and verified in wave 1
(work/verify/R8-repro/repro.py, D_seed_ledger: n=123, span 07-09 02:35 →
07-10 14:35 UTC, net/share +2.75c).

Definition (verbatim from the R8-repro locator):
  eng ∈ {reversal, reversal2}, entered before the v3 launch nightly
  (1783695941 = 2026-07-10 15:05:41Z), settled win/loss, entry ≤ 0.531.
Cost basis: frozen model, cost = entry + 0.07·entry·(1−entry) (entry already
includes the 1c slip). Rows are flagged seed=True so they count toward the
guard n-minimums (netps windows) but never enter qhat (MF3: the launch seeds
already encode this ledger).
"""
import json, os

FEE = 0.07
LAUNCH = 1783695941  # 2026-07-10 15:05:41Z, first v3 nightly line in loop_metrics.jsonl
DATA = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data/trades_unified.json"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seed_regen.json")

tr = json.load(open(DATA))
fam = [t for t in tr if t.get("eng") in ("reversal", "reversal2") and t["at"] / 1000 < LAUNCH
       and t.get("result") in ("win", "loss") and t.get("entry") is not None and t["entry"] <= 0.531]
fam.sort(key=lambda t: t["at"])

rows = []
for t in fam:
    e = t["entry"]
    rows.append(dict(t0=int(t["t0"]), side=t["side"],
                     cost=round(e + FEE * e * (1 - e), 4),
                     win=1 if t["result"] == "win" else 0,
                     seed=True))

net = sum((1 - r["cost"]) if r["win"] else -r["cost"] for r in rows) / len(rows)
assert len(rows) == 123, f"expected the R8-verified n=123 cohort, got {len(rows)}"
assert abs(net * 100 - 2.75) < 0.02, f"expected +2.75c/share (R8-repro D_seed_ledger), got {net*100:.2f}"

with open(OUT, "w") as f:
    json.dump(rows, f, separators=(",", ":"))
print(f"wrote {OUT}: n={len(rows)}, net/share {net*100:+.2f}c, "
      f"span {min(r['t0'] for r in rows)}..{max(r['t0'] for r in rows)}")
