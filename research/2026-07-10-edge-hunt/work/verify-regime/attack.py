#!/usr/bin/env python3
"""Adversarial attacks on the isolated-impulse gate finding."""
import json, random, statistics

SCRATCH = "/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad"
d = json.load(open(SCRATCH + "/data/cb5m.json"))
t, o, c = d["t"], d["o"], d["c"]
n = len(t)

def make(P, thr):
    FEE = 0.07 * P * (1 - P)
    WINP = (1 - P) - FEE; LOSP = -P - FEE
    trades = []
    for i in range(312, n):
        pm = (o[i] - o[i-1]) / o[i-1]
        if abs(pm) < thr: continue
        up = c[i] >= o[i]
        win = (not up) if pm > 0 else up
        num = abs(o[i] - o[i-6])
        den = sum(abs(o[j+1]-o[j]) for j in range(i-6, i))
        eff6 = num/den if den > 0 else 0.0
        cnt = sum(1 for j in range(i-13, i-1) if abs(o[j+1]-o[j])/o[j] >= thr)
        trades.append(dict(i=i, win=win, pnl=WINP if win else LOSP,
                           eff6=eff6, cnt=cnt, pm=pm,
                           day=(t[i]-t[0])/86400.0, blk=i//12,
                           mv=abs(c[i]-o[i])/o[i], up=up))
    return trades

def st(sub):
    if not sub: return dict(n=0)
    nn=len(sub); w=sum(x["win"] for x in sub)
    return dict(n=nn, wr=round(w/nn,4), pps_c=round(sum(x["pnl"] for x in sub)/nn*100,2))

base = make(0.51, 0.0012)
TR = [x for x in base if x["day"] < 40]
TE = [x for x in base if x["day"] >= 40]

print("=== 1) threshold sensitivity +-20% on TEST (gate frozen A=0.32,B=6 baseline) ===")
print("baseline A=0.32 B=6:", st([x for x in TE if x["eff6"]>=0.32 and x["cnt"]<=6]))
for A in [0.256, 0.384]:
    print(f"A={A} B=6:", st([x for x in TE if x["eff6"]>=A and x["cnt"]<=6]))
for B in [4, 5, 7]:
    print(f"A=0.32 B={B}:", st([x for x in TE if x["eff6"]>=0.32 and x["cnt"]<=B]))
print("gate off (ungated TEST):", st(TE))

print("\n=== trigger threshold +-20% (rebuild trades; gate kept A=0.32, B=6) ===")
for thr in [0.00096, 0.00144]:
    tt = make(0.51, thr)
    te = [x for x in tt if x["day"] >= 40]
    g = [x for x in te if x["eff6"]>=0.32 and x["cnt"]<=6]
    print(f"thr={thr*1e4:.1f}bps ungated:", st(te), " gated:", st(g))

print("\n=== 2) fill-price sensitivity (gated TEST wr fixed, vary p) ===")
gTE = [x for x in TE if x["eff6"]>=0.32 and x["cnt"]<=6]
wr = sum(x["win"] for x in gTE)/len(gTE)
for P in [0.50, 0.51, 0.52, 0.53, 0.54]:
    FEE = 0.07*P*(1-P)
    pps = (wr*(1-P-FEE) + (1-wr)*(-P-FEE))*100
    print(f"p={P}: breakeven {100*(P+FEE):.2f}% -> gated TEST pps {pps:+.2f} c/share")

print("\n=== 3) tie / near-tie & direction decomposition of gated TEST ===")
ties = [x for x in gTE if c[x["i"]] == o[x["i"]]]
sub2 = [x for x in gTE if x["mv"] < 0.0002]
print(f"exact ties: {len(ties)}  |outcome move|<2bps: {len(sub2)} ({len(sub2)/len(gTE):.3f}) wr_in<2bps: {st(sub2)}")
print("fade-up (bought Down):", st([x for x in gTE if x["pm"] > 0]))
print("fade-down (bought Up):", st([x for x in gTE if x["pm"] < 0]))
# worst case: flip all sub-2bps wins that are 'coin flips' -- 11% label noise bound
flips = int(round(0.11 * len(sub2)))
w = sum(x["win"] for x in gTE)
wr_lo = (w - flips) / len(gTE)
P=0.51; FEE=0.07*P*(1-P)
print(f"11% label-noise worst case: wr {wr_lo:.4f} -> pps {(wr_lo*(1-P-FEE)+(1-wr_lo)*(-P-FEE))*100:+.2f} c/share")

print("\n=== 4) selection-inflation null: circular-shift features vs outcomes, recalibrate on TRAIN ===")
AGRID=[round(0.06+0.02*k,2) for k in range(18)]; BGRID=list(range(9))
def calib(sub):
    best=None; min_n=max(20,int(0.25*len(sub)))
    for a in AGRID:
        for b in BGRID:
            g=[x for x in sub if x["eff6"]>=a and x["cnt"]<=b]
            if len(g)<min_n: continue
            tot=sum(x["pnl"] for x in g)
            if best is None or tot>best[0]: best=(tot,a,b,len(g))
    return best
# precompute per-trade features & pnl arrays for TRAIN
feats=[(x["eff6"],x["cnt"]) for x in TR]; pnls=[x["pnl"] for x in TR]; wins=[x["win"] for x in TR]
m=len(TR)
rng=random.Random(99)
null_edge=[]
REPS=300
for r in range(REPS):
    off=rng.randrange(24, m-24)   # circular shift, keeps feature autocorr
    sub=[dict(eff6=feats[(k+off)%m][0], cnt=feats[(k+off)%m][1], pnl=pnls[k], win=wins[k]) for k in range(m)]
    cb=calib(sub)
    if cb is None: continue
    tot,a,b,ng=cb
    base_pps=sum(pnls)/m
    null_edge.append(tot/ng*100 - base_pps*100)   # gated pps minus ungated pps (cents)
null_edge.sort()
obs = 3.195 - (-0.612)
ge = sum(1 for v in null_edge if v >= obs)
print(f"null reps={len(null_edge)}: median calibrated gate-edge {statistics.median(null_edge):.2f}c, "
      f"p95 {null_edge[int(0.95*len(null_edge))]:.2f}c, max {null_edge[-1]:.2f}c; "
      f"observed TRAIN gate-edge {obs:.2f}c; p_null={ge/len(null_edge):.4f}")

print("\n=== 5) TEST-period base-rate context ===")
print("TEST ungated:", st(TE), " -> gate adds", round(st(gTE)['pps_c']-st(TE)['pps_c'],2), "c/share on TEST")
# gate-effect on TEST significance was p~0.126 (reproduced in repro.py)

print("\n=== 6) pm_prices_sample p20 fill realism ===")
pm = json.load(open(SCRATCH + "/data/pm_prices_sample.json"))
rows = pm if isinstance(pm, list) else pm.get("rows", pm.get("data"))
p20s = sorted(r["p20"] for r in rows if r.get("p20") is not None)
print(f"n={len(p20s)} p20 median {p20s[len(p20s)//2]:.3f} p25 {p20s[len(p20s)//4]:.3f} p75 {p20s[3*len(p20s)//4]:.3f}")
