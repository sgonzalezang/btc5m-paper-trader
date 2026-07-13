#!/usr/bin/env python3
"""Adversarial verification of wave-2 'params' unit — independent recomputation.

Re-derives from signals_60d.json (own selection code, own bootstrap, own seeds):
  - frozen cell metrics (n, q_xt, q_tl, ev, $/day) per split
  - the three claimed cliffs: revThr=.08 (TEST), eff6Min=0/.05 (TEST), cnt12Max=8 (TRAIN)
  - adjacent-cell agreement + marginal-mass q
  - the best tightening cells (cnt12Max=3/4 TEST)
  - 2D additivity: joint (eff6=0, cnt12=8) vs sum of singles
  - consistency-check explanation (2 recomputed-only rows = 4dp rounding at .12)
Stdlib only.  B=4000, fixed integer seeds (their hash() seeds are not reproducible).
"""
import json, random, collections

BASE = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt"
ROWS = json.load(open(BASE + "/work-deepen/dataset/signals_60d.json"))["rows"]

ANCH = [(0.45, 0.467325, 0.25), (0.49, 0.507493, 0.50), (0.51, 0.527493, 0.25)]
MEAN_COST = sum(c * w for _, c, w in ANCH)
AVAIL, GAS, STAKE = 0.55, 0.004, 50.0
TRAIN_END = 1782432000
TRAIN_DAYS = (TRAIN_END - 1778500800) / 86400.0
TEST_DAYS = (1783914000 - TRAIN_END) / 86400.0
B = 4000

def sel(revThr=0.12, eff6Min=0.10, cnt12Max=6):
    """Independent selection. For eff6Min=.10 use gatePass bit where cnt12<=6
    (unrounded-authoritative), rounded eff6 otherwise — same documented fallback."""
    out = []
    for r in ROWS:
        if not r["gateReady"]:
            continue
        tm = r["trig_move"]
        if tm is None or abs(tm) < revThr - 1e-12:
            continue
        if r["cnt12"] > cnt12Max:
            continue
        if abs(eff6Min - 0.10) < 1e-12 and r["cnt12"] <= 6:
            if not r["gatePass"]:
                continue
        elif r["eff6"] < eff6Min - 1e-12:
            continue
        out.append(r)
    return out

def win(r):
    return r["label"] == ("down" if r["trig_move"] > 0 else "up")

def met(rows, days):
    n = len(rows)
    if n == 0:
        return dict(n=0)
    w = sum(1 for r in rows if win(r))
    t = sum(1 for r in rows if r["label"] == "tie")
    q_xt = w / (n - t)
    q_tl = w / n
    q_mid = (w + 0.5 * t) / n
    usd = sum(wt * ((STAKE / f) * (q_mid - c)) for f, c, wt in ANCH) - GAS
    return dict(n=n, ties=t, q_xt=round(q_xt, 4), q_tl=round(q_tl, 4),
                ev_xt_c=round((q_xt - MEAN_COST) * 100, 2),
                ev_tl_c=round((q_tl - MEAN_COST) * 100, 2),
                usd_day_mid=round(n / days * AVAIL * usd, 2))

def split(rows):
    return ([r for r in rows if r["t0"] < TRAIN_END],
            [r for r in rows if r["t0"] >= TRAIN_END])

def blocks_of(rows):
    d = collections.defaultdict(lambda: [0, 0])
    for r in rows:
        b = r["t0"] // 3600
        if r["label"] != "tie":
            d[b][1] += 1
            if win(r):
                d[b][0] += 1
    return d

def boot(cell, froz, seed):
    rng = random.Random(seed)
    ca, fa = blocks_of(cell), blocks_of(froz)
    bl = sorted(set(ca) | set(fa))
    ds = []
    for _ in range(B):
        cw = cn = fw = fn = 0
        for _ in range(len(bl)):
            b = bl[rng.randrange(len(bl))]
            if b in ca:
                cw += ca[b][0]; cn += ca[b][1]
            if b in fa:
                fw += fa[b][0]; fn += fa[b][1]
        if cn and fn:
            ds.append((cw / cn - fw / fn) * 100)
    ds.sort()
    return dict(ci90=[round(ds[int(.05 * len(ds))], 2), round(ds[int(.95 * len(ds)) - 1], 2)],
                p_le0=round(sum(1 for d in ds if d <= 0) / len(ds), 3),
                point=round((sum(1 for r in cell if win(r)) / max(1, sum(1 for r in cell if r["label"] != "tie"))
                             - sum(1 for r in froz if win(r)) / max(1, sum(1 for r in froz if r["label"] != "tie"))) * 100, 2))

froz = [r for r in ROWS if r.get("trigger") and r.get("gatePass")]
froz_tr, froz_te = split(froz)
froz_ids = {r["t0"] for r in froz}

out = dict(frozen=dict(train=met(froz_tr, TRAIN_DAYS), test=met(froz_te, TEST_DAYS)))

# consistency: my sel() vs dataset flags
mine = sel()
mine_ids = {r["t0"] for r in mine}
extra = [r for r in ROWS if r["t0"] in (mine_ids - froz_ids)]
out["consistency"] = dict(
    recomputed=len(mine), dataset=len(froz),
    only_recomputed=[dict(t0=r["t0"], trig_move=r["trig_move"], trigger=r["trigger"],
                          gatePass=r["gatePass"]) for r in extra],
    only_dataset=len(froz_ids - mine_ids))

CELLS = [
    ("revThr=.08", dict(revThr=0.08), "test", 11),
    ("revThr=.10", dict(revThr=0.10), "test", 12),
    ("eff6=0", dict(eff6Min=0.0), "test", 13),
    ("eff6=0 TRAIN", dict(eff6Min=0.0), "train", 14),
    ("eff6=.05", dict(eff6Min=0.05), "test", 15),
    ("cnt12=8 TRAIN", dict(cnt12Max=8), "train", 16),
    ("cnt12=8 TEST", dict(cnt12Max=8), "test", 17),
    ("cnt12=7 TRAIN", dict(cnt12Max=7), "train", 18),
    ("cnt12=3", dict(cnt12Max=3), "test", 19),
    ("cnt12=3 TRAIN", dict(cnt12Max=3), "train", 20),
    ("cnt12=4", dict(cnt12Max=4), "test", 21),
    ("revThr=.15", dict(revThr=0.15), "test", 22),
    ("revThr=.20", dict(revThr=0.20), "test", 23),
    ("joint e6=0,c12=8 TRAIN", dict(eff6Min=0.0, cnt12Max=8), "train", 24),
    ("rescue r8,c4 TEST", dict(revThr=0.08, cnt12Max=4), "test", 25),
    ("rescue r8,e6=.20 TEST", dict(revThr=0.08, eff6Min=0.20), "test", 26),
]
res = {}
for name, kw, sp, seed in CELLS:
    rows = sel(**kw)
    tr, te = split(rows)
    use, fz = (tr, froz_tr) if sp == "train" else (te, froz_te)
    m = met(use, TRAIN_DAYS if sp == "train" else TEST_DAYS)
    bt = boot(use, fz, seed)
    # marginal mass
    ids = {r["t0"] for r in rows}
    add = [r for r in (tr + te if False else rows) if r["t0"] not in froz_ids]
    rem = [r for r in froz if r["t0"] not in ids]
    marg = add if add else rem
    mm = met(split(marg)[0 if sp == "train" else 1], 1) if marg else None
    res[name] = dict(split=sp, cell=m, boot=bt,
                     marginal=("added" if add else "removed"),
                     marginal_m={k: mm[k] for k in ("n", "q_xt", "ev_tl_c") if mm and k in mm} if mm else None)
out["cells"] = res

# 2D additivity check (point deltas, TRAIN)
d_e6 = met(split(sel(eff6Min=0.0))[0], 1)["ev_xt_c"] - out["frozen"]["train"]["ev_xt_c"]
d_c12 = met(split(sel(cnt12Max=8))[0], 1)["ev_xt_c"] - out["frozen"]["train"]["ev_xt_c"]
d_joint = met(split(sel(eff6Min=0.0, cnt12Max=8))[0], 1)["ev_xt_c"] - out["frozen"]["train"]["ev_xt_c"]
out["additivity_train"] = dict(d_eff6=round(d_e6, 2), d_cnt12=round(d_c12, 2),
                               sum=round(d_e6 + d_c12, 2), d_joint=round(d_joint, 2),
                               interaction=round(d_joint - d_e6 - d_c12, 2))

json.dump(out, open(BASE + "/work-deepen/verify/params-1/verify_sweeps.json", "w"), indent=1)
print(json.dumps(out, indent=1))
