#!/usr/bin/env python3
"""Wave-2 DEEPENING / params: 1D robustness sweeps around the frozen impulse_v2 point.

Signal params (revThr, eff6Min, cnt12Max): FULL candle backtests on signals_60d.json,
frozen fill model (anchors .45/.49/.51 w .25/.5/.25, availability .55, gas $.004,
EV/share = q - cost). TRAIN (May 11-Jun 25) / TEST (Jun 26-Jul 13) reported separately.
Tie handling: q ex-tie AND ties-as-loss bounds (per dataset README; never credit ties).
Inference: 1h-block bootstrap of each cell's TEST (and TRAIN) c/share DELTA vs frozen.
Stdlib only.
"""
import json, math, random, collections

BASE = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt"
DS   = json.load(open(BASE + "/work-deepen/dataset/signals_60d.json"))
ROWS = DS["rows"]

FROZEN = dict(revThr=0.12, eff6Min=0.10, cnt12Max=6)
# fill anchors: (fill price incl slip, fee-inclusive cost, weight)
ANCH = [(0.45, 0.467325, 0.25), (0.49, 0.507493, 0.50), (0.51, 0.527493, 0.25)]
MEAN_COST = sum(c * w for _, c, w in ANCH)          # 0.502451
AVAIL, GAS, STAKE = 0.55, 0.004, 50.0
TRAIN_END = 1782432000
TRAIN_DAYS = (TRAIN_END - 1778500800) / 86400.0      # 45.5
TEST_DAYS  = (1783914000 - TRAIN_END) / 86400.0      # 17.1528
B_BOOT = 2000
random.seed(20260713)

def side_of(tm):
    return "down" if tm > 0 else "up"

def select(revThr, eff6Min, cnt12Max):
    """Rows passing trigger+gate at the given params. Returns list of row refs.

    eff6 in the file is rounded to 4dp while the dataset's gatePass used the
    UNROUNDED eff6>=.10 — so when eff6Min is the frozen .10 we defer to the
    gatePass bit (exact) wherever cnt12<=6, and fall back to rounded eff6 only
    for the cnt12 7-8 extension rows (bias <= a handful of boundary rows)."""
    out = []
    at_frozen_e6 = abs(eff6Min - 0.10) < 1e-12
    for r in ROWS:
        if not r["gateReady"]:
            continue
        tm = r["trig_move"]
        if tm is None or abs(tm) < revThr - 1e-12:
            continue
        if r["cnt12"] > cnt12Max:
            continue
        if at_frozen_e6 and r["cnt12"] <= 6:
            if not r["gatePass"]:
                continue
        elif r["eff6"] < eff6Min - 1e-12:
            continue
        out.append(r)
    return out

def ev_c(q):                       # c/share at the frozen anchor mix
    return (q - MEAN_COST) * 100.0

def ev_usd(q):                     # $ per filled $50-stake signal
    return sum(w * ((STAKE / f) * (q - c)) for f, c, w in ANCH) - GAS

def metrics(sel_rows, days):
    n = len(sel_rows)
    if n == 0:
        return dict(n=0)
    wins = sum(1 for r in sel_rows if r["label"] == side_of(r["trig_move"]))
    ties = sum(1 for r in sel_rows if r["label"] == "tie")
    nx = n - ties
    q_xt = wins / nx if nx else None
    q_tl = wins / n
    q_mid = (wins + 0.5 * ties) / n          # ties at coin-flip, $/day central
    return dict(
        n=n, ties=ties, n_per_day=round(n / days, 2),
        q_xt=round(q_xt, 4) if q_xt is not None else None,
        q_tl=round(q_tl, 4),
        ev_xt_c=round(ev_c(q_xt), 2) if q_xt is not None else None,
        ev_tl_c=round(ev_c(q_tl), 2),
        usd_day_tl=round(n / days * AVAIL * ev_usd(q_tl), 2),
        usd_day_mid=round(n / days * AVAIL * ev_usd(q_mid), 2))

def split_rows(rows):
    tr = [r for r in rows if r["t0"] < TRAIN_END]
    te = [r for r in rows if r["t0"] >= TRAIN_END]
    return tr, te

# ---- block bootstrap of Δ(cell - frozen) on ex-tie and ties-as-loss c/share ----
def block_stats(rows):
    """per 1h-block: (wins, nonties, n) for a selection."""
    d = collections.defaultdict(lambda: [0, 0, 0])
    for r in rows:
        b = r["t0"] // 3600
        w = 1 if r["label"] == side_of(r["trig_move"]) else 0
        t = 1 if r["label"] == "tie" else 0
        s = d[b]
        s[0] += w; s[1] += (1 - t); s[2] += 1
    return d

def boot_delta(cell_rows, froz_rows, seed):
    """CI90 + p-values for Δ ex-tie c/share (cell - frozen), 1h blocks."""
    rng = random.Random(seed)
    ca, fa = block_stats(cell_rows), block_stats(froz_rows)
    blocks = sorted(set(ca) | set(fa))
    if not blocks:
        return None
    nb = len(blocks)
    deltas_xt, deltas_tl = [], []
    for _ in range(B_BOOT):
        cw = cn = cN = fw = fn = fN = 0
        for _ in range(nb):
            b = blocks[rng.randrange(nb)]
            if b in ca:
                s = ca[b]; cw += s[0]; cn += s[1]; cN += s[2]
            if b in fa:
                s = fa[b]; fw += s[0]; fn += s[1]; fN += s[2]
        if cn == 0 or fn == 0 or cN == 0 or fN == 0:
            continue
        deltas_xt.append((cw / cn - fw / fn) * 100.0)
        deltas_tl.append((cw / cN - fw / fN) * 100.0)
    if not deltas_xt:
        return None
    deltas_xt.sort(); deltas_tl.sort()
    def ci(v, lo, hi):
        return [round(v[int(lo * len(v))], 2), round(v[min(len(v) - 1, int(hi * len(v)))], 2)]
    p_le0 = sum(1 for d in deltas_xt if d <= 0) / len(deltas_xt)
    return dict(d_xt_ci90=ci(deltas_xt, 0.05, 0.95),
                d_tl_ci90=ci(deltas_tl, 0.05, 0.95),
                p_xt_le0=round(p_le0, 3), B=len(deltas_xt))

# ---- consistency check vs dataset flags at the frozen point ----
# NOTE dataset semantics: gatePass = gateReady AND eff6>=.10 AND cnt12<=6 (no trigger);
# the gated-signal universe is trigger AND gatePass.
froz = select(**FROZEN)
flag = [r for r in ROWS if r.get("trigger") and r.get("gatePass")]
froz_ids = {r["t0"] for r in froz}
flag_ids = {r["t0"] for r in flag}
consistency = dict(
    recomputed=len(froz), dataset_gatePass=len(flag),
    only_recomputed=len(froz_ids - flag_ids), only_dataset=len(flag_ids - froz_ids))
# use the DATASET's gatePass rows as the frozen cell (unrounded-eff6 authoritative)
froz = flag
froz_tr, froz_te = split_rows(froz)

RESULTS = dict(
    meta=dict(
        desc="1D parameter robustness map around frozen impulse_v2 "
             "(revThr=12bps, eff6Min=.10, cnt12Max=6, cap=.53, window=45s)",
        fill_model="frozen anchors .45/.49/.51 w .25/.5/.25 (mean cost .5025), "
                   "avail .55, $50 stake, gas $.004; EV c/share=(q-.50245)*100",
        tie_handling="q_xt = ex-tie; q_tl = ties-as-loss; usd_day_mid = ties at 0.5",
        splits=dict(train_days=TRAIN_DAYS, test_days=round(TEST_DAYS, 3)),
        boot="1h-block bootstrap, B=%d, delta vs frozen cell per split" % B_BOOT,
        consistency_check=consistency),
    frozen=dict(train=metrics(froz_tr, TRAIN_DAYS), test=metrics(froz_te, TEST_DAYS)),
    sweeps={},
)

K = 0
def sweep(name, values, param_key):
    global K
    cells = []
    for v in values:
        p = dict(FROZEN); p[param_key] = v
        is_froz = (abs(v - FROZEN[param_key]) < 1e-12)
        rows = froz if is_froz else select(**p)
        if not is_froz:
            K += 1
        tr, te = split_rows(rows)
        cell = dict(value=v, frozen=is_froz,
                    train=metrics(tr, TRAIN_DAYS), test=metrics(te, TEST_DAYS))
        # marginal subset vs frozen (nested sweeps -> pure add/remove)
        ids = {r["t0"] for r in rows}
        add = [r for r in rows if r["t0"] not in froz_ids]
        rem = [r for r in froz if r["t0"] not in ids]
        for tag, sub in (("added", add), ("removed", rem)):
            if sub:
                str_, ste = split_rows(sub)
                cell["marginal_" + tag] = dict(
                    train=metrics(str_, TRAIN_DAYS), test=metrics(ste, TEST_DAYS))
        if not is_froz:
            cell["boot_vs_frozen"] = dict(
                train=boot_delta(tr, froz_tr, seed=hash((name, v, "tr")) & 0xffff),
                test=boot_delta(te, froz_te, seed=hash((name, v, "te")) & 0xffff))
        cells.append(cell)
    RESULTS["sweeps"][name] = cells

sweep("revThr_bps", [0.08, 0.10, 0.12, 0.15, 0.20], "revThr")
sweep("eff6Min", [0.0, 0.05, 0.10, 0.15, 0.20, 0.30], "eff6Min")
sweep("cnt12Max", [3, 4, 5, 6, 7, 8], "cnt12Max")

RESULTS["meta"]["K_backtest_cells"] = K
json.dump(RESULTS, open(BASE + "/work-deepen/params/sweep1d.json", "w"), indent=1)

# console summary
def line(c, split):
    m = c[split]
    if m.get("n", 0) == 0:
        return "  n=0"
    return ("  n=%5d (%5.1f/d) q_xt=%.4f ev_xt=%+6.2fc q_tl=%.4f ev_tl=%+6.2fc $mid/d=%+7.2f"
            % (m["n"], m["n_per_day"], m["q_xt"] or 0, m["ev_xt_c"] or 0,
               m["q_tl"], m["ev_tl_c"], m["usd_day_mid"]))
print("consistency:", consistency)
print("FROZEN  TRAIN" + line(RESULTS["frozen"], "train").replace("  n", " n"))
print("FROZEN  TEST " + line(RESULTS["frozen"], "test").replace("  n", " n"))
for name, cells in RESULTS["sweeps"].items():
    print("\n== %s ==" % name)
    for c in cells:
        tag = "*" if c["frozen"] else " "
        bt = c.get("boot_vs_frozen", {}).get("test")
        extra = (" dTEST_xt CI90 %s p<=0 %.3f" % (bt["d_xt_ci90"], bt["p_xt_le0"])) if bt else ""
        print("%s %-5s TRAIN%s" % (tag, c["value"], line(c, "train")))
        print("%s %-5s TEST %s%s" % (tag, c["value"], line(c, "test"), extra))
print("\nK_backtest_cells =", K)
