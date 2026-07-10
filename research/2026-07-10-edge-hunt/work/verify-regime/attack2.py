#!/usr/bin/env python3
"""Verify walk-forward pooled OOS claim (+2.97c, beats ungated 4/5 folds, worst -3.33c),
probe the TEST-calm negative pocket, and re-check the TEST sensitivity plateau."""
import json, random

BASE = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-10-edge-hunt"
d = json.load(open(BASE + "/data/cb5m.json"))
t, o, c = d["t"], d["o"], d["c"]
n = len(t)
P = 0.51; FEE = 0.07*P*(1-P); WINP = (1-P)-FEE; LOSEP = -P-FEE; THR = 0.0012
moves = [(o[i+1]-o[i])/o[i] for i in range(n-1)]
absm = [abs(m) for m in moves]
pref = [0.0]
for i in range(n-1): pref.append(pref[-1] + abs(o[i+1]-o[i]))
def eff(i, W):
    den = pref[i]-pref[i-W]
    return abs(o[i]-o[i-W])/den if den > 0 else 0.0
WARM = 312
trades = []
for i in range(WARM, n):
    pm = moves[i-1]
    if abs(pm) < THR: continue
    up = c[i] >= o[i]
    win = (not up) if pm > 0 else up
    cnt = sum(1 for j in range(i-13, i-1) if absm[j] >= THR)
    trades.append({"win": 1 if win else 0, "pnl": WINP if win else LOSEP,
                   "eff6": eff(i,6), "cnt": cnt, "eff288": eff(i,288),
                   "day": (t[i]-t[0])/86400.0, "blk": i//12})
def st(sub):
    if not sub: return {"n":0}
    nn=len(sub); w=sum(x["win"] for x in sub); p=sum(x["pnl"] for x in sub)/nn
    return {"n":nn,"wr":round(w/nn,4),"pps_c":round(p*100,3)}

EFFG=[round(0.06+0.02*k,2) for k in range(18)]
def calib(sub):
    best=None; mn=max(20,int(0.25*len(sub)))
    for a in EFFG:
        for b in range(0,9):
            gg=[x for x in sub if x["eff6"]>=a and x["cnt"]<=b]
            if len(gg)<mn: continue
            tot=sum(x["pnl"] for x in gg)
            if best is None or tot>best[0]: best=(tot,a,b)
    return best

folds=[[x for x in trades if 10*k <= x["day"] < 10*(k+1)] for k in range(6)]
oos=[]; print("== walk-forward: calibrate fold k -> eval fold k+1 ==")
beats=0; worst=9
for k in range(5):
    cb=calib(folds[k]); a,b=cb[1],cb[2]
    gg=[x for x in folds[k+1] if x["eff6"]>=a and x["cnt"]<=b]
    oos.extend(gg)
    su, sg = st(folds[k+1]), st(gg)
    if sg["pps_c"] > su["pps_c"]: beats+=1
    worst=min(worst, sg["pps_c"])
    print(f"  fold{k}->({a},{b})-> fold{k+1}: ungated {su} gated {sg}")
base_n=sum(len(folds[k]) for k in range(1,6))
print("pooled OOS:", st(oos), "retention:", round(len(oos)/base_n,3),
      "beats ungated in", beats, "/5 folds, worst fold", worst, "c")

# TEST calm pocket: bootstrap p that TEST-calm gated pnl <= 0 / >= 0
vals=sorted(x["eff288"] for x in trades)
q1=vals[len(vals)//3]
calmTE=[x for x in trades if x["day"]>=40 and x["eff288"]<=q1 and x["eff6"]>=0.32 and x["cnt"]<=6]
def blocks(sub):
    dd={}
    for x in sub: dd.setdefault(x["blk"],[]).append(x)
    return list(dd.values())
def boot(sub, reps=5000, seed=5, sign=1):
    bl=blocks(sub); rng=random.Random(seed); cnt=0
    for _ in range(reps):
        flat=[x for _ in range(len(bl)) for x in bl[rng.randrange(len(bl))]]
        v=sum(x["pnl"] for x in flat)/len(flat)
        if sign*v <= 0: cnt+=1
    return round(cnt/reps,4)
print("\nTEST-calm gated:", st(calmTE), " boot p(pnl>=0):", boot(calmTE, sign=-1))

# TEST sensitivity plateau check
print("\n== TEST sensitivity (pps_c), n>=30 ==")
TEST=[x for x in trades if x["day"]>=40]
mn_pps=9
for a in [0.06,0.10,0.14,0.18,0.22,0.26,0.30,0.34,0.38]:
    row=[]
    for b in range(1,8):
        gg=[x for x in TEST if x["eff6"]>=a and x["cnt"]<=b]
        if len(gg)>=30:
            v=sum(x["pnl"] for x in gg)/len(gg)*100
            mn_pps=min(mn_pps,v)
            row.append(f"{v:6.2f}")
        else: row.append("   -- ")
    print(f"  a={a:4} "+" ".join(row))
print("min over grid:", round(mn_pps,2), "c")
