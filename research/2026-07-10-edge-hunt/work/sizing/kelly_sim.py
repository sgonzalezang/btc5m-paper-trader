#!/usr/bin/env python3
"""(a) Fee-adjusted Kelly for the reversal edge + block-bootstrap sizing simulation.

Kelly setup: buy 1 share of a binary at fill price p (slip included), entry fee
0.07*p*(1-p) per share (bot's exact model). Cost/share c = p + 0.07*p*(1-p).
Win pays $1/share. Net odds b = (1-c)/c. Kelly fraction f* = q - (1-q)/b.

Simulation: latentfire-style gated 60d signal stream (work/sizing/stream.json).
Stakes: flat $50 vs quarter/half/full Kelly (fraction of CURRENT bankroll, $1,000 start).
Kelly design point: q=0.56 (verified prior), fill p per-trade drawn from the live
reversal-family empirical entry distribution (n=155, median 0.51) -> f computed at the
DESIGN point (q=0.56, p=0.51), constant fraction. Gas $0.004/trade.
Resolution noise: outcomes with |c-o| < 2bps flipped with prob 0.11 in bootstrap draws.
Block bootstrap: 1-hour calendar blocks (12 intervals), 4000 resamples.
Metrics on TEST (last 1/3) and full 60d: terminal wealth, max drawdown, P(B<500).
"""
import json, math, random, os

SCRATCH = "/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad"
W = os.path.join(SCRATCH, "work", "sizing")
D = os.path.join(SCRATCH, "data")
random.seed(7)

# ---------- Kelly table ----------
def cost(p): return p + 0.07 * p * (1 - p)
def kelly(q, p):
    c = cost(p); b = (1 - c) / c
    return q - (1 - q) / b, c, b

table = []
for q in (0.56, 0.563, 0.54, 0.52):
    for p in (0.47, 0.49, 0.51, 0.53, 0.55):
        f, c, b = kelly(q, p)
        ev = q - c
        table.append({"q": q, "p": p, "cost": round(c, 4), "ev_per_share": round(ev, 4),
                      "f_kelly": round(f, 4), "stake_at_1k": round(max(f, 0) * 1000, 2)})
json.dump(table, open(os.path.join(W, "kelly_table.json"), "w"), indent=1)
print("Kelly design point q=0.56 p=0.51:", kelly(0.56, 0.51)[0])

# ---------- data ----------
stream = json.load(open(os.path.join(W, "stream.json")))
cb = json.load(open(os.path.join(D, "cb5m.json")))
o_by_t = dict(zip(cb["t"], cb["o"]))
c_by_t = dict(zip(cb["t"], cb["c"]))
gated = [s for s in stream if s["eff"] <= 0.48]
for s in gated:
    op, cl = o_by_t[s["t0"]], c_by_t[s["t0"]]
    s["tiny"] = 1 if abs(cl - op) / op < 0.0002 else 0
print("gated n:", len(gated), "tiny(|move|<2bps) frac:", sum(s["tiny"] for s in gated) / len(gated))

tr = json.load(open(os.path.join(D, "trades.json")))
fills = [x["entry"] for x in tr if x["eng"] in ("reversal", "reversal2", "latentfire") and x.get("entry")]

split_t = json.load(open(os.path.join(W, "stream_stats.json")))["split_t"]

# hour blocks
def blocks_of(rows):
    blk = {}
    for s in rows:
        blk.setdefault(s["t0"] // 3600, []).append(s)
    return [blk[k] for k in sorted(blk)]

F_FULL = kelly(0.56, 0.51)[0]          # 0.0688 design-point fraction
GAS = 0.004
STRATS = {"flat50": ("flat", 50.0),
          "kelly_q": ("frac", F_FULL / 4),
          "kelly_h": ("frac", F_FULL / 2),
          "kelly_f": ("frac", F_FULL)}

def run_path(seq, mode, val, b0=1000.0):
    B, peak, maxdd = b0, b0, 0.0
    for (win, p) in seq:
        c = cost(p)
        stake = min(val, B) if mode == "flat" else val * B
        if stake <= 0 or B <= 1.0:
            stake = 0.0
        shares = stake / c
        pnl = shares * 1.0 - stake if win else -stake
        B += pnl - (GAS if stake > 0 else 0)
        if B > peak: peak = B
        dd = (peak - B) / peak
        if dd > maxdd: maxdd = dd
    return B, maxdd

def bootstrap(rows, nboot=4000):
    blks = blocks_of(rows)
    nb = len(blks)
    out = {k: {"tw": [], "dd": []} for k in STRATS}
    for _ in range(nboot):
        seq = []
        for _ in range(nb):
            for s in random.choice(blks):
                w = s["win"]
                if s["tiny"] and random.random() < 0.11:
                    w = 1 - w
                seq.append((w, random.choice(fills)))
        for k, (mode, val) in STRATS.items():
            twv, ddv = run_path(seq, mode, val)
            out[k]["tw"].append(twv); out[k]["dd"].append(ddv)
    res = {}
    for k in STRATS:
        tw = sorted(out[k]["tw"]); dd = sorted(out[k]["dd"])
        n = len(tw)
        res[k] = {"tw_p5": tw[int(.05*n)], "tw_med": tw[n//2], "tw_p95": tw[int(.95*n)],
                  "tw_mean": sum(tw)/n,
                  "dd_med": dd[n//2], "dd_p95": dd[int(.95*n)],
                  "p_below_500": sum(1 for x in tw if x < 500)/n,
                  "p_loss": sum(1 for x in tw if x < 1000)/n}
    return res

test_rows = [s for s in gated if s["t0"] >= split_t]
train_rows = [s for s in gated if s["t0"] < split_t]
print("TEST rows:", len(test_rows), " TRAIN rows:", len(train_rows))

results = {"design_f_full": F_FULL,
           "TEST_full_freq": bootstrap(test_rows),
           "TRAIN_full_freq": bootstrap(train_rows)}

# frequency-matched variant: live reversal ran ~20 trades/day vs stream ~51/day.
# Thin the TEST stream to ~40% to match observed live cadence (cap/liquidity losses).
random.seed(11)
thin = [s for s in test_rows if random.random() < 0.40]
print("thinned TEST rows:", len(thin))
results["TEST_live_freq"] = bootstrap(thin)

json.dump(results, open(os.path.join(W, "kelly_sim_results.json"), "w"), indent=1)
for seg in ("TEST_full_freq", "TEST_live_freq", "TRAIN_full_freq"):
    print("\n==", seg)
    for k, v in results[seg].items():
        print(f" {k:8s} med={v['tw_med']:9.0f} p5={v['tw_p5']:8.0f} p95={v['tw_p95']:9.0f} "
              f"ddMed={v['dd_med']:.2%} ddP95={v['dd_p95']:.2%} P(<500)={v['p_below_500']:.3f} P(loss)={v['p_loss']:.3f}")
