#!/usr/bin/env python3
"""Wave-2 params task 3: 2D interactions ONLY where the 1D sweeps showed a cliff.

Cliffs found in sweep1d.json (delta = cell - frozen, ex-tie c/share, 1h-block boot):
  C1 revThr LOW side: 8bps TEST delta CI90 [-4.47,-0.40] (p<=0 .975); marginal added
     mass fee-dead both splits (TEST added q_xt .5125). Cliff below 12bps.
  C2 eff6Min LOW side: 0.0 TEST CI90 [-2.57,-0.26], 0.05 TEST CI90 [-1.85,-0.38]
     (p<=0 .982/.991; 0.0 also TRAIN-significant). Cliff below 0.10.
  C3 cnt12Max HIGH side: 8 TRAIN delta CI90 [-1.82,-0.16] (p<=0 .981). Mild cliff at 8.
Tightening directions (revThr 15/20, eff6 .15-.30, cnt12 3-5) are plateaus, not cliffs.

Three pre-declared pairs (max allowed = 3):
  P1 revThr x eff6Min  {8,10,12} x {.10,.15,.20}: does a tighter eff6 gate rescue the
     sub-12bps trigger mass? (rescue = cliff mass is low-eff6 mass)
  P2 revThr x cnt12Max {8,10,12} x {4,5,6}: does a tighter cnt12 rescue it?
  P3 eff6Min x cnt12Max {0,.05,.10} x {6,7,8}: are the two loosening cliffs the same
     rows (choppy-regime overlap) or additive?

Same engine as sweep1d: frozen fill anchors, ex-tie / ties-as-loss bounds, 1h-block
bootstrap (B=2000) of the cell-minus-frozen delta per split. Stdlib only.
K: 12 NEW backtest cells (per-grid 9 minus frozen minus 4 already counted in 1D).
"""
import json, random, collections

BASE = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt"
DS   = json.load(open(BASE + "/work-deepen/dataset/signals_60d.json"))
ROWS = DS["rows"]

FROZEN = dict(revThr=0.12, eff6Min=0.10, cnt12Max=6)
ANCH = [(0.45, 0.467325, 0.25), (0.49, 0.507493, 0.50), (0.51, 0.527493, 0.25)]
MEAN_COST = sum(c * w for _, c, w in ANCH)
AVAIL, GAS, STAKE = 0.55, 0.004, 50.0
TRAIN_END = 1782432000
TRAIN_DAYS = (TRAIN_END - 1778500800) / 86400.0
TEST_DAYS  = (1783914000 - TRAIN_END) / 86400.0
B_BOOT = 2000
random.seed(20260713)

def side_of(tm): return "down" if tm > 0 else "up"

def select(revThr, eff6Min, cnt12Max):
    out = []
    at_frozen_e6 = abs(eff6Min - 0.10) < 1e-12
    for r in ROWS:
        if not r["gateReady"]: continue
        tm = r["trig_move"]
        if tm is None or abs(tm) < revThr - 1e-12: continue
        if r["cnt12"] > cnt12Max: continue
        if at_frozen_e6 and r["cnt12"] <= 6:
            if not r["gatePass"]: continue
        elif r["eff6"] < eff6Min - 1e-12:
            continue
        out.append(r)
    return out

def ev_c(q): return (q - MEAN_COST) * 100.0
def ev_usd(q): return sum(w * ((STAKE / f) * (q - c)) for f, c, w in ANCH) - GAS

def metrics(sel, days):
    n = len(sel)
    if n == 0: return dict(n=0)
    wins = sum(1 for r in sel if r["label"] == side_of(r["trig_move"]))
    ties = sum(1 for r in sel if r["label"] == "tie")
    nx = n - ties
    q_xt = wins / nx if nx else None
    q_tl = wins / n
    q_mid = (wins + 0.5 * ties) / n
    return dict(n=n, ties=ties, n_per_day=round(n / days, 2),
                q_xt=round(q_xt, 4) if q_xt is not None else None,
                q_tl=round(q_tl, 4),
                ev_xt_c=round(ev_c(q_xt), 2) if q_xt is not None else None,
                ev_tl_c=round(ev_c(q_tl), 2),
                usd_day_mid=round(n / days * AVAIL * ev_usd(q_mid), 2))

def split_rows(rows):
    return ([r for r in rows if r["t0"] < TRAIN_END],
            [r for r in rows if r["t0"] >= TRAIN_END])

def block_stats(rows):
    d = collections.defaultdict(lambda: [0, 0, 0])
    for r in rows:
        b = r["t0"] // 3600
        w = 1 if r["label"] == side_of(r["trig_move"]) else 0
        t = 1 if r["label"] == "tie" else 0
        s = d[b]; s[0] += w; s[1] += (1 - t); s[2] += 1
    return d

def boot_delta(cell_rows, froz_rows, seed):
    rng = random.Random(seed)
    ca, fa = block_stats(cell_rows), block_stats(froz_rows)
    blocks = sorted(set(ca) | set(fa))
    if not blocks: return None
    nb = len(blocks); dx = []
    for _ in range(B_BOOT):
        cw = cn = fw = fn = 0
        for _ in range(nb):
            b = blocks[rng.randrange(nb)]
            if b in ca: s = ca[b]; cw += s[0]; cn += s[1]
            if b in fa: s = fa[b]; fw += s[0]; fn += s[1]
        if cn and fn: dx.append((cw / cn - fw / fn) * 100.0)
    if not dx: return None
    dx.sort()
    ci = [round(dx[int(0.05 * len(dx))], 2), round(dx[min(len(dx) - 1, int(0.95 * len(dx)))], 2)]
    return dict(d_xt_ci90=ci, p_xt_le0=round(sum(1 for d in dx if d <= 0) / len(dx), 3), B=len(dx))

froz = [r for r in ROWS if r.get("trigger") and r.get("gatePass")]
froz_ids = {r["t0"] for r in froz}
froz_tr, froz_te = split_rows(froz)

ALREADY_1D = {("P1", 0.08, 0.10), ("P1", 0.10, 0.10), ("P1", 0.12, 0.15), ("P1", 0.12, 0.20),
              ("P2", 0.08, 6), ("P2", 0.10, 6), ("P2", 0.12, 4), ("P2", 0.12, 5),
              ("P3", 0.0, 6), ("P3", 0.05, 6), ("P3", 0.10, 7), ("P3", 0.10, 8)}

K_new = 0
def grid(tag, akey, avals, bkey, bvals):
    global K_new
    cells = []
    for a in avals:
        for b in bvals:
            p = dict(FROZEN); p[akey] = a; p[bkey] = b
            is_froz = (abs(a - FROZEN[akey]) < 1e-12 and abs(b - FROZEN[bkey]) < 1e-12)
            rows = froz if is_froz else select(**p)
            counted_1d = (tag, a, b) in ALREADY_1D
            if not is_froz and not counted_1d:
                K_new += 1
            tr, te = split_rows(rows)
            cell = dict({akey: a, bkey: b}, frozen=is_froz, counted_in_1d=counted_1d,
                        train=metrics(tr, TRAIN_DAYS), test=metrics(te, TEST_DAYS))
            # marginal mass vs frozen: what this cell ADDS beyond frozen (rescue metric)
            add = [r for r in rows if r["t0"] not in froz_ids]
            ids = {r["t0"] for r in rows}
            rem = [r for r in froz if r["t0"] not in ids]
            if add:
                atr, ate = split_rows(add)
                cell["added_vs_frozen"] = dict(train=metrics(atr, TRAIN_DAYS),
                                               test=metrics(ate, TEST_DAYS))
            if rem:
                rtr, rte = split_rows(rem)
                cell["removed_vs_frozen"] = dict(train=metrics(rtr, TRAIN_DAYS),
                                                 test=metrics(rte, TEST_DAYS))
            if not is_froz:
                cell["boot_vs_frozen"] = dict(
                    train=boot_delta(tr, froz_tr, seed=hash((tag, a, b, "tr")) & 0xffff),
                    test=boot_delta(te, froz_te, seed=hash((tag, a, b, "te")) & 0xffff))
            cells.append(cell)
    return cells

OUT = dict(
    meta=dict(
        desc="2D interaction grids at the three 1D cliffs (task 3). Same frozen fill "
             "model and boot machinery as sweep1d.py; deltas are vs the frozen cell.",
        cliffs="C1 revThr<12 (TEST-sig), C2 eff6Min<.10 (TEST-sig), C3 cnt12Max=8 (TRAIN-sig)",
        K_new_backtest_cells=None, K_cumulative_with_sweep1d=None),
    grids=dict(
        P1_revThr_x_eff6Min=grid("P1", "revThr", [0.08, 0.10, 0.12], "eff6Min", [0.10, 0.15, 0.20]),
        P2_revThr_x_cnt12Max=grid("P2", "revThr", [0.08, 0.10, 0.12], "cnt12Max", [4, 5, 6]),
        P3_eff6Min_x_cnt12Max=grid("P3", "eff6Min", [0.0, 0.05, 0.10], "cnt12Max", [6, 7, 8])))

OUT["meta"]["K_new_backtest_cells"] = K_new
OUT["meta"]["K_cumulative_with_sweep1d"] = 14 + K_new
json.dump(OUT, open(BASE + "/work-deepen/params/sweep2d.json", "w"), indent=1)

for gname, cells in OUT["grids"].items():
    print("\n====", gname, "====")
    for c in cells:
        keys = [k for k in c if k not in ("frozen", "counted_in_1d", "train", "test",
                                          "added_vs_frozen", "removed_vs_frozen", "boot_vs_frozen")]
        lab = " ".join("%s=%s" % (k, c[k]) for k in keys)
        te, tr = c["test"], c["train"]
        bt = (c.get("boot_vs_frozen") or {}).get("test") or {}
        btr = (c.get("boot_vs_frozen") or {}).get("train") or {}
        add = c.get("added_vs_frozen", {}).get("test", {})
        print("%s %-24s TR n=%4d ev_xt=%+5.2f | TE n=%4d ev_xt=%+5.2f dCI90=%s p<=0=%s | dTR CI90=%s | addTE n=%s q_xt=%s"
              % ("*" if c["frozen"] else " ", lab, tr["n"], tr["ev_xt_c"] or 0,
                 te["n"], te["ev_xt_c"] or 0, bt.get("d_xt_ci90"), bt.get("p_xt_le0"),
                 btr.get("d_xt_ci90"), add.get("n"), add.get("q_xt")))
print("\nK_new =", K_new, " cumulative =", 14 + K_new)
