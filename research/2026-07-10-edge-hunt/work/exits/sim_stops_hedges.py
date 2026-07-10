#!/usr/bin/env python3
"""(b)+(c) Walk-forward stop-loss and hedge overlays on the settled ledger.

Stop: at first post-entry checkpoint s>=s_min where fv_side < X, sell all shares
      at (fv_side - 2c), paying a second taker fee.
Hedge: at first post-entry checkpoint s>=s_min where fv_side < Y, buy equal shares
       of the opposite side at (1 - fv_side + 2c) ask, paying a second taker fee.
Sweep (X, s_min) / (Y, s_min) on TRAIN (first 2/3 by t0); quote the TRAIN-chosen
config on TEST. Block bootstrap (1-hour blocks) on the TEST per-trade delta.
Outputs: work/exits/sim_results.json
"""
import json, math, random

SCRATCH = "/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad"
rows = json.load(open(SCRATCH + "/work/exits/joined.json"))
rows.sort(key=lambda r: r["t0"])
t0min, t0max = rows[0]["t0"], rows[-1]["t0"]
tsplit = t0min + (t0max - t0min) * 2 / 3
TRAIN = [r for r in rows if r["t0"] < tsplit]
TEST = [r for r in rows if r["t0"] >= tsplit]
print(f"train n={len(TRAIN)}  test n={len(TEST)}  split t0={tsplit:.0f}")

def fv_side(r, s):
    f = r["fv_up"][str(s)]
    return f if r["side"] == "up" else 1 - f

def cps(r, s_min):
    es = r["entrySec"] if r["entrySec"] is not None else 30
    return [s for s in (60, 120, 180, 240) if s > es and s >= s_min]

def pnl_stop(r, X, s_min):
    """(pnl, fired) under stop rule; falls back to hold pnl."""
    for s in cps(r, s_min):
        f = fv_side(r, s)
        if f < X:
            q = max(0.01, f - 0.02)
            sh = r["shares"]
            proceeds = sh * q - sh * 0.07 * q * (1 - q)
            return proceeds - sh * r["entry"] - r["feeEntry"] - r["gas"], True
    return r["pnl_hold"], False

def pnl_hedge(r, Y, s_min):
    for s in cps(r, s_min):
        f = fv_side(r, s)
        if f < Y:
            h = min(0.99, (1 - f) + 0.02)
            sh = r["shares"]
            cost_h = sh * h + sh * 0.07 * h * (1 - h)
            # one of the two sides pays sh * $1 at resolution
            return sh - sh * r["entry"] - r["feeEntry"] - cost_h - 2 * r["gas"], True
    return r["pnl_hold"], False

def book_stats(pnls):
    n = len(pnls)
    tot = sum(pnls)
    mean = tot / n
    var = sum((p - mean) ** 2 for p in pnls) / (n - 1) if n > 1 else 0.0
    cum = peak = 0.0
    mdd = 0.0
    for p in pnls:
        cum += p
        peak = max(peak, cum)
        mdd = max(mdd, peak - cum)
    return {"n": n, "total": round(tot, 1), "mean": round(mean, 3),
            "sd": round(math.sqrt(var), 2), "maxDD": round(mdd, 1)}

def run(sub, fn, param, s_min):
    pnls, fired = [], 0
    for r in sub:
        p, f = fn(r, param, s_min)
        pnls.append(p)
        fired += f
    st = book_stats(pnls)
    st["fired"] = fired
    return st, pnls

def block_bootstrap_p(rows_sub, deltas, iters=4000, seed=7):
    """P(mean block-resampled delta <= 0) two-ish sided; blocks = 1h of trades."""
    blocks = {}
    for r, d in zip(rows_sub, deltas):
        blocks.setdefault(r["t0"] // 3600, []).append(d)
    bl = list(blocks.values())
    if not bl:
        return None
    obs = sum(deltas) / len(deltas)
    rng = random.Random(seed)
    cnt_ge0 = 0
    for _ in range(iters):
        s, n = 0.0, 0
        for _ in range(len(bl)):
            b = bl[rng.randrange(len(bl))]
            s += sum(b)
            n += len(b)
        m = s / n
        if (obs < 0 and m >= 0) or (obs >= 0 and m <= 0):
            cnt_ge0 += 1
    return obs, cnt_ge0 / iters

results = {"split_t0": tsplit, "n_train": len(TRAIN), "n_test": len(TEST)}
hold_tr, _ = run(TRAIN, lambda r, p, s: (r["pnl_hold"], False), None, 0)
hold_te, hold_te_pnls = run(TEST, lambda r, p, s: (r["pnl_hold"], False), None, 0)
print("\nHOLD baseline  TRAIN:", hold_tr, " TEST:", hold_te)
results["hold_train"] = hold_tr
results["hold_test"] = hold_te

for name, fn, grid in (
    ("STOP", pnl_stop, [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45]),
    ("HEDGE", pnl_hedge, [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45]),
):
    print(f"\n=== {name} sweep on TRAIN (delta vs hold total) ===")
    best = None
    tbl = []
    for s_min in (60, 120, 180):
        for X in grid:
            st, _ = run(TRAIN, fn, X, s_min)
            d = st["total"] - hold_tr["total"]
            tbl.append({"X": X, "s_min": s_min, **st, "delta_total": round(d, 1)})
            if best is None or d > best[0]:
                best = (d, X, s_min)
    for row in tbl:
        print(f"  X={row['X']:.2f} s_min={row['s_min']}: total={row['total']:>8} "
              f"delta={row['delta_total']:>7} fired={row['fired']:>4} sd={row['sd']} maxDD={row['maxDD']}")
    d, X, s_min = best
    print(f"TRAIN best: X={X} s_min={s_min} delta_total={d:+.1f}")
    st_te, pnls_te = run(TEST, fn, X, s_min)
    d_te = st_te["total"] - hold_te["total"]
    deltas = [a - b for a, b in zip(pnls_te, hold_te_pnls)]
    obs, pboot = block_bootstrap_p(TEST, deltas)
    print(f"TEST  @ TRAIN-best: total={st_te['total']} (hold {hold_te['total']}) "
          f"delta={d_te:+.1f} fired={st_te['fired']} sd={st_te['sd']} vs {hold_te['sd']} "
          f"maxDD={st_te['maxDD']} vs {hold_te['maxDD']}")
    print(f"TEST  mean delta/trade={obs:+.4f}  block-bootstrap p={pboot:.4f}")
    results[name] = {"train_table": tbl, "train_best": {"X": X, "s_min": s_min, "delta": d},
                     "test": {**st_te, "delta_total": round(d_te, 1),
                              "mean_delta": round(obs, 4), "boot_p": pboot}}

# --- reversal-family only (the live edge book) ---
fam = [r for r in rows if r["eng"] in ("reversal", "reversal2", "latentfire")]
print(f"\n=== reversal-family only (n={len(fam)}) — same TRAIN-best configs ===")
fam_tr = [r for r in fam if r["t0"] < tsplit]
fam_te = [r for r in fam if r["t0"] >= tsplit]
h_tr = sum(r["pnl_hold"] for r in fam_tr)
h_te = sum(r["pnl_hold"] for r in fam_te)
print(f"hold: TRAIN total {h_tr:+.1f} (n={len(fam_tr)})  TEST total {h_te:+.1f} (n={len(fam_te)})")
fam_out = {"n_train": len(fam_tr), "n_test": len(fam_te),
           "hold_train": round(h_tr, 1), "hold_test": round(h_te, 1), "rows": []}
for name, fn in (("STOP", pnl_stop), ("HEDGE", pnl_hedge)):
    for X in (0.20, 0.30, 0.40):
        for s_min in (60, 120, 180):
            tr = sum(fn(r, X, s_min)[0] for r in fam_tr)
            te = sum(fn(r, X, s_min)[0] for r in fam_te)
            fam_out["rows"].append({"rule": name, "X": X, "s_min": s_min,
                                    "train": round(tr, 1), "test": round(te, 1)})
            print(f"  {name} X={X} s_min={s_min}: TRAIN {tr:+.1f} (d {tr-h_tr:+.1f})  "
                  f"TEST {te:+.1f} (d {te-h_te:+.1f})")
results["reversal_family"] = fam_out
json.dump(results, open(SCRATCH + "/work/exits/sim_results.json", "w"), indent=1)
print("\nwrote work/exits/sim_results.json")
