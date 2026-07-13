"""Family 4: intra-interval path features from cb1m (prior interval's internal 1m path).

DATA CAVEAT: cb1m only exists Jun 26 - Jul 13 (16.7d) — entirely inside the program's
TEST window. Sub-split used here: TRAIN' = Jun 26 - Jul 5 00:00 UTC, TEST' = Jul 5 -
Jul 13. This is a SHORT split; anything found here is at best [CANDIDATE] grade.

Execution realism: all features end at t0 (1m candle [t0-60,t0) close ~ o[i]);
the trade enters in the first 45s of interval i. No look-ahead.

Grid (K4 counted):
  last1m:   |r_1m| >= {2,4,6,10} bps x dir {follow, fade}                      = 8
  z1m:      |r_1m| >= z*mean|r| trailing 15m, z in {2,3} x dir                 = 4
  shape:    |prior 5m move| >= 8bps, first-3m A vs last-2m B:
            exhausted (sign B != sign A) x dir {rev-of-move, mom-of-move}      = 2
            accelerating (sign B == sign A and |B|>|A|) x dir                  = 2
  trig12:   among >=12bps triggers (the deployed signal), contrarian side,
            split backloaded (|B|>=0.6|move|) vs frontloaded (|B|<=0.25|move|) = 2
K4 = 18
"""
import json, calendar
from common import Table, load_candles, DATA, block_bootstrap, cost

SPLIT1M = calendar.timegm((2026, 7, 5, 0, 0, 0))
P_FILL = 0.51

tab = Table()
m1 = load_candles(f"{DATA}/cb1m.json")
o1 = {t: o for t, o in zip(m1["t"], m1["o"])}

def eval_fire(fire):
    out = {}
    for split in ("TRAIN'", "TEST'"):
        trades, wins = [], 0
        for i, side in fire.items():
            if tab.up[i] is None:
                continue
            is_tr = tab.t[i] < SPLIT1M
            if (split == "TRAIN'") != is_tr:
                continue
            w = 1 if ((side == "up") == (tab.up[i] == 1)) else 0
            wins += w
            trades.append((tab.t[i], w - cost(P_FILL)))
        n = len(trades)
        if n == 0:
            out[split] = {"n": 0}
            continue
        mean, p, lo, hi = block_bootstrap(trades, reps=2000)
        out[split] = {"n": n, "q": round(wins / n, 4), "ev_c": round(mean * 100, 3),
                      "p_boot": round(p, 4), "ci90_c": [round(lo * 100, 3), round(hi * 100, 3)]}
    return out

grid = []
def run(name, fire):
    r = eval_fire(fire)
    r["name"] = name; r["fires"] = len(fire)
    grid.append(r)
    return r

def path(i):
    """Return (A, B, move) fractional returns of prior interval, or None."""
    t0 = tab.t[i]
    a0, a3 = o1.get(t0 - 300), o1.get(t0 - 120)
    if a0 is None or a3 is None or i < 1:
        return None
    cur = tab.o[i]
    A = (a3 - a0) / a0
    B = (cur - a3) / a3
    move = (cur - a0) / a0
    return A, B, move

# last1m return
for thr_bps in (2, 4, 6, 10):
    thr = thr_bps / 10000.0
    fire_f, fire_x = {}, {}
    for i in range(1, tab.n - 1):
        t0 = tab.t[i]
        a = o1.get(t0 - 60)
        if a is None:
            continue
        r = (tab.o[i] - a) / a
        if abs(r) < thr:
            continue
        side = "up" if r > 0 else "down"
        fire_f[i] = side
        fire_x[i] = "down" if side == "up" else "up"
    run(f"last1m_thr{thr_bps}bps_follow", fire_f)
    run(f"last1m_thr{thr_bps}bps_fade", fire_x)

# last1m z-score vs trailing 15 1m
for z in (2, 3):
    fire_f, fire_x = {}, {}
    for i in range(1, tab.n - 1):
        t0 = tab.t[i]
        opens = [o1.get(t0 - 60 * k) for k in range(17)]
        if any(x is None for x in opens):
            continue
        opens = opens[::-1]  # oldest -> newest; opens[-1] = o at t0
        rs = [(opens[k + 1] - opens[k]) / opens[k] for k in range(16)]
        last = rs[-1]
        base = sum(abs(x) for x in rs[:-1]) / 15
        if base <= 0 or abs(last) < z * base:
            continue
        side = "up" if last > 0 else "down"
        fire_f[i] = side
        fire_x[i] = "down" if side == "up" else "up"
    run(f"z1m_z{z}_follow", fire_f)
    run(f"z1m_z{z}_fade", fire_x)

# shape: exhausted / accelerating
fe_rev, fe_mom, fa_rev, fa_mom = {}, {}, {}, {}
for i in range(1, tab.n - 1):
    pb = path(i)
    if pb is None:
        continue
    A, B, move = pb
    if abs(move) < 0.0008 or A == 0 or B == 0:
        continue
    mom_side = "up" if move > 0 else "down"
    rev_side = "down" if move > 0 else "up"
    if (A > 0) != (B > 0):          # exhausted: tail reversed the head
        fe_rev[i] = rev_side
        fe_mom[i] = mom_side
    elif abs(B) > abs(A):           # accelerating into the boundary
        fa_rev[i] = rev_side
        fa_mom[i] = mom_side
run("shape_exhausted_rev", fe_rev)
run("shape_exhausted_mom", fe_mom)
run("shape_accel_rev", fa_rev)
run("shape_accel_mom", fa_mom)

# trig12 path split: deployed 12bps contrarian, backloaded vs frontloaded trigger
fb, ff = {}, {}
for i in range(1, tab.n - 1):
    r = tab.prior_ret(i, 1)
    if r is None or abs(r) < 0.0012:
        continue
    pb = path(i)
    if pb is None:
        continue
    A, B, move = pb
    if move == 0:
        continue
    rev_side = "down" if r > 0 else "up"
    frac_tail = B / move  # fraction of the move delivered by the last 2 minutes
    if frac_tail >= 0.6:
        fb[i] = rev_side
    elif frac_tail <= 0.25:
        ff[i] = rev_side
run("trig12_backloaded_rev", fb)
run("trig12_frontloaded_rev", ff)

K = len(grid)
picks = {}
for sub, pref in (("last1m", "last1m_"), ("z1m", "z1m_"), ("shape", "shape_"),
                  ("trig12path", "trig12_")):
    cands = [g for g in grid if g["name"].startswith(pref)
             and g["TRAIN'"].get("n", 0) >= 150]
    cands.sort(key=lambda g: g["TRAIN'"]["ev_c"], reverse=True)
    picks[sub] = cands[0] if cands else None

json.dump({"K": K, "split_note": "TRAIN'=Jun26-Jul5, TEST'=Jul5-13 (1m data limit)",
           "picks": picks, "grid": grid},
          open("family4_intra1m.json", "w"), indent=1)
print("K =", K)
for sub, p in picks.items():
    if p:
        print(sub, "->", p["name"], "TRAIN'", p["TRAIN'"], "TEST'", p["TEST'"])
    else:
        print(sub, "-> none")
