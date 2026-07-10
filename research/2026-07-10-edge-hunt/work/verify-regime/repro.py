#!/usr/bin/env python3
"""Independent re-derivation of the 'isolated impulse' gate finding.

Written from scratch by the adversarial verifier from data/cb5m.json + the
finding's stated definitions (NOT by importing the family's scripts).

Strategy: prior open-to-open |move| >= 12bps -> buy other side at p=0.51,
exact fee 0.07*p*(1-p), hold to resolution, tie -> Up.
Gate: eff6 >= A AND cnt12 <= B, calibrated on TRAIN (first 40d), frozen on TEST.
"""
import json, random

SCRATCH = "/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad"
d = json.load(open(SCRATCH + "/data/cb5m.json"))
t, o, c = d["t"], d["o"], d["c"]
n = len(t)
assert all(t[i+1]-t[i] == 300 for i in range(n-1)), "not gapless"

P = 0.51
FEE = 0.07 * P * (1 - P)
WINP = (1 - P) - FEE          # +0.472507 per share
LOSP = -P - FEE               # -0.527493 per share
THR = 0.0012

def build(warm, thr=THR):
    trades = []
    for i in range(warm, n):
        pm = (o[i] - o[i-1]) / o[i-1]          # trigger move (completed at t0)
        if abs(pm) < thr:
            continue
        up = c[i] >= o[i]                       # tie -> Up
        win = (not up) if pm > 0 else up        # fade: buy the other side
        num = abs(o[i] - o[i-6])
        den = sum(abs(o[j+1] - o[j]) for j in range(i-6, i))
        eff6 = num / den if den > 0 else 0.0
        # cnt12: |move|>=12bps among the 12 moves BEFORE the trigger move
        cnt = sum(1 for j in range(i-13, i-1)
                  if abs(o[j+1] - o[j]) / o[j] >= thr)
        trades.append({"i": i, "t": t[i], "win": win,
                       "pnl": WINP if win else LOSP,
                       "eff6": eff6, "cnt": cnt,
                       "day": (t[i] - t[0]) / 86400.0,
                       "blk": i // 12})
    return trades

def st(sub):
    if not sub: return dict(n=0)
    nn = len(sub); w = sum(x["win"] for x in sub)
    return dict(n=nn, wr=round(w/nn, 4),
                pps_c=round(sum(x["pnl"] for x in sub)/nn*100, 3))

def calib(sub, agrid, bgrid):
    best = None
    min_n = max(20, int(0.25 * len(sub)))
    for a in agrid:
        for b in bgrid:
            g = [x for x in sub if x["eff6"] >= a and x["cnt"] <= b]
            if len(g) < min_n: continue
            tot = sum(x["pnl"] for x in g)
            if best is None or tot > best[0]:
                best = (tot, a, b, len(g))
    return best

def boot_p_pnl(sub, reps=10000, seed=11):
    blocks = {}
    for x in sub: blocks.setdefault(x["blk"], []).append(x)
    bl = list(blocks.values()); nb = len(bl)
    rng = random.Random(seed); cnt = 0
    for _ in range(reps):
        s = 0.0; m = 0
        for _ in range(nb):
            for x in bl[rng.randrange(nb)]:
                s += x["pnl"]; m += 1
        if s / m <= 0: cnt += 1
    return cnt / reps

def boot_p_gate_effect(allsub, a, b, reps=10000, seed=13):
    """P(wr(gated) - wr(all) <= 0) under 1h block bootstrap of the full set."""
    blocks = {}
    for x in allsub: blocks.setdefault(x["blk"], []).append(x)
    bl = list(blocks.values()); nb = len(bl)
    rng = random.Random(seed); cnt = 0; used = 0
    for _ in range(reps):
        flat = [x for _ in range(nb) for x in bl[rng.randrange(nb)]]
        g = [x for x in flat if x["eff6"] >= a and x["cnt"] <= b]
        if len(g) < 10: continue
        used += 1
        eff = sum(x["win"] for x in g)/len(g) - sum(x["win"] for x in flat)/len(flat)
        if eff <= 0: cnt += 1
    return cnt / used

AGRID = [round(0.06 + 0.02*k, 2) for k in range(18)]
BGRID = list(range(0, 9))

for warm, tag in [(312, "warm=312 (match family)"), (14, "warm=14 (minimal)")]:
    trades = build(warm)
    TR = [x for x in trades if x["day"] < 40]
    TE = [x for x in trades if x["day"] >= 40]
    print(f"--- {tag}: total triggers {len(trades)}  TRAIN {len(TR)}  TEST {len(TE)}")
    cal = calib(TR, AGRID, BGRID)
    _, A, B, ng = cal
    print(f"  TRAIN-calibrated gate: A={A} B={B} (gated n TRAIN={ng})")
    gTR = [x for x in TR if x["eff6"] >= A and x["cnt"] <= B]
    gTE = [x for x in TE if x["eff6"] >= A and x["cnt"] <= B]
    print("  TRAIN all:", st(TR), "gated:", st(gTR))
    print("  TEST  all:", st(TE), "gated:", st(gTE),
          "retention:", round(len(gTE)/len(TE), 3))
    if tag.startswith("warm=312"):
        print("  boot p TEST gated pnl<=0:", boot_p_pnl(gTE))
        print("  boot p TRAIN gate-effect<=0:", boot_p_gate_effect(TR, A, B))
        print("  boot p TEST gate-effect<=0:", boot_p_gate_effect(TE, A, B))
