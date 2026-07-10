#!/usr/bin/env python3
"""(a)+(e): P(reversal | prior |move|>=thr) on cb5m 60d, buffered open-to-open method,
ties->Up. Full period, per-10d-window stability, circular block bootstrap (12-ivl blocks).
Also move-size buckets 12-20bps vs 20+bps. TRAIN=first 40d, TEST=last 20d.
Output: a_stability.json + printed tables."""
import json, math, random

S = "/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad"
d = json.load(open(f"{S}/data/cb5m.json"))
t, o, c = d["t"], d["o"], d["c"]
N = len(t)

# buffered construction: prior move uses consecutive OPENS (shared boundary)
# signal index i (1..N-1): m_i = (o[i]-o[i-1])/o[i-1]; outcome_i = 1 if c[i]>=o[i] else 0 (tie->Up)
mv = [0.0]*N   # prior move in bps at index i
up = [0]*N
for i in range(1, N):
    mv[i] = (o[i]-o[i-1])/o[i-1]*1e4
    up[i] = 1 if c[i] >= o[i] else 0

def rev_win(i):
    """1 if contrarian side wins at interval i (requires mv[i]!=0)."""
    if mv[i] > 0:   # fade up-move -> buy Down; Down wins only if c<o (tie goes Up)
        return 1 - up[i]
    else:           # fade down-move -> buy Up; wins if c>=o
        return up[i]

FEE = lambda p: 0.07*p*(1-p)
P51 = 0.51
QSTAR = P51 + FEE(P51)          # 0.527493 break-even win rate at 51c
WIN, LOSE = (1-P51)-FEE(P51), -(P51)-FEE(P51)

def net_per_trade(q):
    return q*WIN + (1-q)*LOSE   # per share, at 51c fill

idx_all = list(range(1, N))
TRAIN_END = 1 + int((N-1)*2/3)          # chronological 2/3
def stats(indices, thr):
    sig = [i for i in indices if abs(mv[i]) >= thr]
    n = len(sig)
    if n == 0: return n, None
    w = sum(rev_win(i) for i in sig)
    return n, w/n

def block_boot(indices, thr, B=2000, blk=12, seed=7):
    """circular block bootstrap over the index range; returns (lo,hi,p_gt_half,p_gt_qstar)"""
    rng = random.Random(seed)
    lo_i, hi_i = indices[0], indices[-1]
    span = hi_i - lo_i + 1
    nblk = math.ceil(span/blk)
    qs = []
    for _ in range(B):
        wins = tot = 0
        for _ in range(nblk):
            s = lo_i + rng.randrange(span)
            for k in range(blk):
                i = lo_i + ((s - lo_i + k) % span)
                if abs(mv[i]) >= thr:
                    tot += 1; wins += rev_win(i)
        if tot: qs.append(wins/tot)
    qs.sort()
    B2 = len(qs)
    lo, hi = qs[int(0.025*B2)], qs[int(0.975*B2)-1]
    p_half  = sum(1 for q in qs if q <= 0.5)/B2
    p_qstar = sum(1 for q in qs if q <= QSTAR)/B2
    return lo, hi, p_half, p_qstar

THRS = [6, 8, 10, 12, 14, 16, 20, 25]
out = {"qstar_at_51c": QSTAR, "N": N, "train_end_idx": TRAIN_END}

print(f"break-even q at 51c = {QSTAR:.6f}; per-share win {WIN:.6f} lose {LOSE:.6f}")
print("\n== (a) full period / TRAIN / TEST, block bootstrap on TRAIN and TEST ==")
rows = []
for thr in THRS:
    nF, qF = stats(idx_all, thr)
    tr = [i for i in idx_all if i < TRAIN_END]; te = [i for i in idx_all if i >= TRAIN_END]
    nTr, qTr = stats(tr, thr); nTe, qTe = stats(te, thr)
    loT, hiT, pT_half, pT_q = block_boot(tr, thr, B=1500)
    loE, hiE, pE_half, pE_q = block_boot(te, thr, B=1500, seed=11)
    row = dict(thr=thr, n_full=nF, q_full=qF, n_train=nTr, q_train=qTr,
               train_ci=[loT,hiT], train_p_vs_half=pT_half, train_p_vs_qstar=pT_q,
               n_test=nTe, q_test=qTe, test_ci=[loE,hiE], test_p_vs_half=pE_half,
               test_p_vs_qstar=pE_q, net51_test=net_per_trade(qTe) if qTe else None)
    rows.append(row)
    print(f"thr={thr:>3}bps full n={nF:>5} q={qF:.4f} | TRAIN n={nTr:>5} q={qTr:.4f} "
          f"CI[{loT:.3f},{hiT:.3f}] p(q<=.5)={pT_half:.4f} p(q<=q*)={pT_q:.4f} | "
          f"TEST n={nTe:>4} q={qTe:.4f} CI[{loE:.3f},{hiE:.3f}] p={pE_half:.4f}/{pE_q:.4f} "
          f"net51={net_per_trade(qTe):+.4f}")
out["thresholds"] = rows

print("\n== per-10d-window stability (6 windows) ==")
W = (N-1)//6
wins_tbl = []
for thr in THRS:
    line = []
    for w in range(6):
        lo_i = 1 + w*W; hi_i = 1 + (w+1)*W if w < 5 else N
        nw, qw = stats(range(lo_i, hi_i), thr)
        line.append([nw, qw])
    wins_tbl.append({"thr": thr, "windows": line})
    print(f"thr={thr:>3}: " + " | ".join(f"n={n:>4} q={q:.3f}" for n,q in line))
out["windows_10d"] = wins_tbl

print("\n== (e) move-size buckets ==")
bucket_rows = []
for name, lo_b, hi_b in [("6-12", 6, 12), ("12-20", 12, 20), ("20+", 20, 1e9), ("12+",12,1e9), ("25+",25,1e9)]:
    for split, indices in [("TRAIN", [i for i in idx_all if i < TRAIN_END]),
                           ("TEST",  [i for i in idx_all if i >= TRAIN_END])]:
        sig = [i for i in indices if lo_b <= abs(mv[i]) < hi_b]
        n = len(sig)
        q = sum(rev_win(i) for i in sig)/n if n else None
        bucket_rows.append(dict(bucket=name, split=split, n=n, q=q,
                                net51=net_per_trade(q) if q else None))
        if q is not None:
            print(f"{name:>6} {split:>5} n={n:>5} q={q:.4f} net51={net_per_trade(q):+.4f}")
out["buckets"] = bucket_rows

json.dump(out, open(f"{S}/work/reversal60/a_stability.json","w"), indent=1)
print("\nsaved a_stability.json")
