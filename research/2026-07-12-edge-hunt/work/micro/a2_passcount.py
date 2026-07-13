"""A2: passCount margin (passCount - need). Is EV monotone in margin?
Counterfactual: would requiring need+1 have cleared fees for any retired engine?
Caveat stated in results: filtering the as-fired ledger by passCount>=need+1 selects trades
that already had margin at their actual fire time; a real need+1 engine could also fire later
at different prices. This is the best available approximation from the ledger.
"""
import json, collections, sys
sys.path.insert(0, "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work/micro")
from common import load_trades, mean, block_boot_mean, block_boot_diff

T = load_trades()
for x in T:
    x["_marg"] = x["passCount"] - x["need"]

res = {"note": "margin = passCount - need at fire time; need+1 counterfactual = subset with margin>=1 (approximation, see docstring)"}

def evline(g):
    ev = [x["_evps"] for x in g]; blk = [x["_blk"] for x in g]
    m, lo, hi, p = block_boot_mean(ev, blk)
    return dict(n=len(g), wr=round(mean([x["_w"] for x in g]), 4),
                entry=round(mean([x["entry"] for x in g]), 4),
                evps_c=round(100*m, 2), ci95_c=[round(100*lo, 2), round(100*hi, 2)],
                p_le0=round(p, 4))

# margin distribution + EV by margin, pooled and per engine (n>=100 engines)
res["pooled_by_margin"] = {}
for mg in sorted(set(x["_marg"] for x in T)):
    g = [x for x in T if x["_marg"] == mg]
    if len(g) >= 20:
        res["pooled_by_margin"][str(mg)] = evline(g)

res["per_engine"] = {}
for e in sorted(set(x["eng"] for x in T)):
    g = [x for x in T if x["eng"] == e]
    if len(g) < 100:
        continue
    ent = {}
    for mg in sorted(set(x["_marg"] for x in g)):
        gg = [x for x in g if x["_marg"] == mg]
        if len(gg) >= 15:
            ent[str(mg)] = evline(gg)
    # margin>=1 vs margin==0 contrast (the need+1 counterfactual)
    m0 = [x for x in g if x["_marg"] == 0]
    m1 = [x for x in g if x["_marg"] >= 1]
    if len(m0) >= 15 and len(m1) >= 15:
        d, lo, hi, p = block_boot_diff([x["_evps"] for x in m1], [x["_blk"] for x in m1],
                                       [x["_evps"] for x in m0], [x["_blk"] for x in m0])
        ent["need_plus1_vs_exact"] = dict(n1=len(m1), n0=len(m0), diff_c=round(100*d, 2),
                                          ci95_c=[round(100*lo, 2), round(100*hi, 2)],
                                          p_diff_le0=round(p, 4),
                                          evps_need_plus1_c=round(100*mean([x["_evps"] for x in m1]), 2))
    res["per_engine"][e] = ent

# monotonicity: spearman-ish — pooled margin vs evps rank corr with block permutation
import math, random
def rank(v):
    idx = sorted(range(len(v)), key=lambda i: v[i])
    r = [0.0]*len(v)
    i = 0
    while i < len(idx):
        j = i
        while j+1 < len(idx) and v[idx[j+1]] == v[idx[i]]:
            j += 1
        rr = (i+j)/2.0
        for k in range(i, j+1):
            r[idx[k]] = rr
        i = j+1
    return r
def spear(a, b):
    ra, rb = rank(a), rank(b)
    ma, mb = mean(ra), mean(rb)
    num = sum((x-ma)*(y-mb) for x, y in zip(ra, rb))
    da = math.sqrt(sum((x-ma)**2 for x in ra)); db = math.sqrt(sum((y-mb)**2 for y in rb))
    return num/(da*db) if da*db else float("nan")

margs = [x["_marg"] for x in T]; evs = [x["_evps"] for x in T]
rho = spear(margs, evs)
# block permutation: shuffle margins between 1h blocks (keep ev fixed) — 1000 reps
blocks = collections.defaultdict(list)
for i, x in enumerate(T):
    blocks[x["_blk"]].append(i)
rng = random.Random(3)
bl = list(blocks.values())
cnt = 0; reps = 1000
for _ in range(reps):
    perm = bl[:]
    rng.shuffle(perm)
    pm = [0]*len(T)
    for src, dst in zip(bl, perm):
        for k in range(min(len(src), len(dst))):
            pm[dst[k]] = margs[src[k]]
        for k in range(len(src), len(dst)):
            pm[dst[k]] = margs[src[rng.randrange(len(src))]]
    if abs(spear(pm, evs)) >= abs(rho):
        cnt += 1
res["pooled_margin_ev_spearman"] = dict(rho=round(rho, 4), block_perm_p=round(cnt/reps, 3))

json.dump(res, open("/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work/micro/a2_passcount.json", "w"), indent=1)
# compact print
print("pooled by margin:")
for k, v in res["pooled_by_margin"].items():
    print(" ", k, v)
print("spearman:", res["pooled_margin_ev_spearman"])
for e, ent in res["per_engine"].items():
    print(e)
    for k, v in ent.items():
        print("  ", k, v)
