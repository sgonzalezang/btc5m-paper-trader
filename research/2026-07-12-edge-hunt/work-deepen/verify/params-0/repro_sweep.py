#!/usr/bin/env python3
"""ADVERSARIAL REPRO (params-0): rebuild the revThr and eff6Min sweep axes from RAW
cb5m.json candles — independent gate implementation, independent metrics, independent
paired 1h-block bootstrap (different seed, different code path). Does NOT read
signals_60d.json or sweep1d.py logic. Stdlib only.
"""
import json, math, random, collections

BASE = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt"
cb = json.load(open(BASE + "/data/cb5m.json"))
T, O = cb["t"], cb["o"]
idx = {t: i for i, t in enumerate(T)}
IVL = 300

# open-to-open return (fraction) of interval starting at t
def ret(t):
    i = idx.get(t)
    j = idx.get(t + IVL)
    if i is None or j is None:
        return None
    return (O[j] - O[i]) / O[i]

TRAIN_END = 1782432000
TRAIN_DAYS = (TRAIN_END - 1778500800) / 86400.0
TEST_DAYS = (1783914000 - TRAIN_END) / 86400.0

# ---- build the trigger universe with my own gate ----
rows = []
for t0 in T:
    tm = ret(t0 - IVL)                    # trigger = prior completed interval
    if tm is None:
        continue
    if abs(tm) * 100.0 < 0.12:            # bot: prior |move|% >= revThr, exact compare
        pass                              # keep sub-threshold rows for revThr=8/10 sweep
    r0 = ret(t0)                          # label return
    if r0 is None:
        continue
    hist = [ret(t0 - IVL * k) for k in range(1, 14)]  # k=1 trigger .. k=13 oldest
    if any(h is None for h in hist):
        continue                          # gate not ready
    last6 = hist[:6][::-1]                # 6 moves ending at trigger, trigger INCLUDED
    den = sum(abs(r) for r in last6)
    net = 1.0
    for r in last6:
        net *= (1.0 + r)
    eff6 = (abs(net - 1.0) / den) if den > 0 else 1.0
    cnt12 = sum(1 for k in range(2, 14) if abs(hist[k - 1]) >= 0.0012)
    lab = "tie" if abs(r0) * 100.0 < 0.01 else ("up" if r0 > 0 else "down")
    side = "down" if tm > 0 else "up"     # contrarian
    rows.append((t0, abs(tm) * 100.0, eff6, cnt12, side, lab))

FROZEN = dict(revThr=0.12, eff6Min=0.10, cnt12Max=6)

def select(revThr, eff6Min, cnt12Max):
    return [r for r in rows
            if r[1] >= revThr and r[2] >= eff6Min and r[3] <= cnt12Max]

ANCH = [(0.45, 0.45 + 0.07 * 0.45 * 0.55, 0.25),
        (0.49, 0.49 + 0.07 * 0.49 * 0.51, 0.50),
        (0.51, 0.51 + 0.07 * 0.51 * 0.49, 0.25)]
MEAN_COST = sum(c * w for _, c, w in ANCH)
AVAIL, GAS, STAKE = 0.55, 0.004, 50.0

def metrics(sel, days):
    n = len(sel)
    if n == 0:
        return dict(n=0)
    wins = sum(1 for r in sel if r[5] == r[4])
    ties = sum(1 for r in sel if r[5] == "tie")
    q_xt = wins / (n - ties) if n > ties else None
    q_tl = wins / n
    q_mid = (wins + 0.5 * ties) / n
    usd = sum(w * (STAKE / f) * (q_mid - c) for f, c, w in ANCH) - GAS
    return dict(n=n, ties=ties,
                q_xt=round(q_xt, 4), q_tl=round(q_tl, 4),
                ev_xt_c=round((q_xt - MEAN_COST) * 100, 2),
                ev_tl_c=round((q_tl - MEAN_COST) * 100, 2),
                usd_day_mid=round(n / days * AVAIL * usd, 2))

def split(sel):
    return [r for r in sel if r[0] < TRAIN_END], [r for r in sel if r[0] >= TRAIN_END]

# ---- my own paired 1h-block bootstrap on the ex-tie c/share delta ----
def boot(cell, froz, B=2000, seed=99173):
    rng = random.Random(seed)
    agg = collections.defaultdict(lambda: [0, 0, 0, 0])   # cw, cn, fw, fn per block
    for r in cell:
        a = agg[r[0] // 3600]
        if r[5] != "tie":
            a[0] += (1 if r[5] == r[4] else 0); a[1] += 1
    for r in froz:
        a = agg[r[0] // 3600]
        if r[5] != "tie":
            a[2] += (1 if r[5] == r[4] else 0); a[3] += 1
    blocks = list(agg.values())
    nb = len(blocks)
    ds = []
    for _ in range(B):
        cw = cn = fw = fn = 0
        for _ in range(nb):
            a = blocks[rng.randrange(nb)]
            cw += a[0]; cn += a[1]; fw += a[2]; fn += a[3]
        if cn and fn:
            ds.append((cw / cn - fw / fn) * 100)
    ds.sort()
    lo, hi = ds[int(0.05 * len(ds))], ds[int(0.95 * len(ds)) - 1]
    return dict(d_ci90=[round(lo, 2), round(hi, 2)],
                p_le0=round(sum(1 for d in ds if d <= 0) / len(ds), 3),
                d_point=None)

froz = select(**FROZEN)
ftr, fte = split(froz)
out = dict(frozen=dict(train=metrics(ftr, TRAIN_DAYS), test=metrics(fte, TEST_DAYS)),
           sweeps={})

def run_axis(name, key, values):
    cells = []
    for v in values:
        p = dict(FROZEN); p[key] = v
        sel = select(**p)
        tr, te = split(sel)
        cell = dict(value=v, train=metrics(tr, TRAIN_DAYS), test=metrics(te, TEST_DAYS))
        if abs(v - FROZEN[key]) > 1e-12:
            ids = {r[0] for r in sel}
            fids = {r[0] for r in froz}
            add = [r for r in sel if r[0] not in fids]
            rem = [r for r in froz if r[0] not in ids]
            for tag, sub in (("added", add), ("removed", rem)):
                if sub:
                    a, b = split(sub)
                    cell["marg_" + tag] = dict(train=metrics(a, TRAIN_DAYS),
                                               test=metrics(b, TEST_DAYS))
            cell["boot"] = dict(train=boot(tr, ftr, seed=hash((name, v, 1)) & 0xfffff),
                                test=boot(te, fte, seed=hash((name, v, 2)) & 0xfffff))
            cell["boot"]["train"]["d_point"] = round(
                (cell["train"]["q_xt"] - out["frozen"]["train"]["q_xt"]) * 100, 2)
            cell["boot"]["test"]["d_point"] = round(
                (cell["test"]["q_xt"] - out["frozen"]["test"]["q_xt"]) * 100, 2)
        cells.append(cell)
    out["sweeps"][name] = cells

run_axis("revThr", "revThr", [0.08, 0.10, 0.12, 0.15, 0.20])
run_axis("eff6Min", "eff6Min", [0.0, 0.05, 0.10, 0.15, 0.20, 0.30])

# additivity spot-check (2D claim): joint eff6Min=0 & cnt12Max=8 vs singles
j = select(0.12, 0.0, 8)
e0 = select(0.12, 0.0, 6)
c8 = select(0.12, 0.10, 8)
jt, _ = split(j); e0t, _ = split(e0); c8t, _ = split(c8)
mj, me, mc = metrics(jt, TRAIN_DAYS), metrics(e0t, TRAIN_DAYS), metrics(c8t, TRAIN_DAYS)
f0 = out["frozen"]["train"]["ev_xt_c"]
out["additivity_2d_train"] = dict(
    joint_delta=round(mj["ev_xt_c"] - f0, 2),
    sum_singles=round((me["ev_xt_c"] - f0) + (mc["ev_xt_c"] - f0), 2))

json.dump(out, open(BASE + "/work-deepen/verify/params-0/repro_sweep.json", "w"), indent=1)

print("frozen TRAIN", out["frozen"]["train"])
print("frozen TEST ", out["frozen"]["test"])
for name, cells in out["sweeps"].items():
    print("\n==", name)
    for c in cells:
        b = c.get("boot", {})
        print(" %5s TR n=%5d ev_xt=%+5.2f | TE n=%4d ev_xt=%+5.2f q_xt=%.4f %s" % (
            c["value"], c["train"]["n"], c["train"]["ev_xt_c"],
            c["test"]["n"], c["test"]["ev_xt_c"], c["test"]["q_xt"],
            ("dTE CI90 %s p<=0 %.3f" % (b["test"]["d_ci90"], b["test"]["p_le0"])) if b else "FROZEN"))
        if "marg_added" in c and c["marg_added"].get("test", {}).get("n"):
            print("        added TEST: n=%d q_xt=%s" % (
                c["marg_added"]["test"]["n"], c["marg_added"]["test"]["q_xt"]))
print("\nadditivity:", out["additivity_2d_train"])
