#!/usr/bin/env python3
"""REPRO verify (qhat-0) — Part 2: independent walk-forward harness.

Re-implements the calibrator tournament from scratch (own code structure, own
bootstrap seeds) on signals_60d.json. Conventions forced by the frozen spec:
anchors .45/.49/.51 with quartile weights x .55 availability, EV/share =
q - p - .07p(1-p), gas .004, nightly 00:10 UTC, 60s settle lag, 4dp rounding,
0.56 cap, quarter-Kelly (5% cap, $1 min, $250 breaker), bank 1000 reset at TEST.

Outputs:
  families        — TRAIN/TEST pnl for the unit's 16 families + 6 cap variants
  rank_match      — my TRAIN ranking vs the unit's claimed ranking
  boots           — winner-vs-current, spec-vs-current (base+stress),
                    hybrid-vs-current (base+stress), seed/mass decomposition
  stress_dropday  — every paired delta recomputed dropping the best TEST day
                    (and worst day, for symmetry)
  stress_jitter   — bucket edge +-1c (cost .49/.51; peff .49/.51) base+stress
  stress_halfgrid — prior grid halved (M in {25,50,100,200}), TRAIN re-ranked
  cap_grid        — caps {.54,.56,.58,.60,1.00} on 3 families
  haircut_forced  — forced-haircut deltas
stdlib only.
"""
import json, os, random

HERE = os.path.dirname(os.path.abspath(__file__))
DS = json.load(open("/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/"
                    "work-deepen/dataset/signals_60d.json"))
TEST_T0 = 1782432000
TIE_UP = 0.432
FEE, GAS = 0.07, 0.004
ANCH = [(0.45, 0.1375), (0.49, 0.275), (0.51, 0.1375)]        # weight = quartile x .55
CST = {p: round(p + FEE * p * (1 - p), 6) for p, _ in ANCH}

SIG = []
for r in DS["rows"]:
    if not (r.get("trigger") and r.get("gatePass")):
        continue
    lab = r["label"]
    if lab == "tie":
        pw = TIE_UP if r["side"] == "up" else 1 - TIE_UP
    else:
        pw = 1.0 if lab == r["side"] else 0.0
    SIG.append((r["t0"], r["split"], pw))
SIG.sort()
T0, T1 = SIG[0][0], SIG[-1][0]
NDAYS = {"train": (TEST_T0 - T0) / 86400, "test": (T1 + 300 - TEST_T0) / 86400}
TICKS = []
t = (T0 // 86400 + 1) * 86400 + 600
while t <= T1 + 86400:
    TICKS.append(t); t += 86400


def wf(bucket="peff", edge=0.50, M=200, seed=(0.5, 0.5), cap=0.56, window=30,
       decay=None, shrink=False, stress=False, forced_haircut=False, drop_days=(),
       want_rows=False):
    """My walk-forward. Returns {split:{pnl,shares,...}, rows:{t0: test pnl}}."""
    lo_of = {p: (CST[p] < edge) if bucket == "cost" else (p < edge) for p, _ in ANCH}
    book = []                      # (t0, is_lo, pwin_for_book, w, cost)
    qlo = min(cap, seed[0]); qhi = min(cap, seed[1])
    bank = 1000.0; reset_done = False
    agg = {sp: [0.0, 0.0, 0.0, {0.45: 0.0, 0.49: 0.0, 0.51: 0.0}, 0.0, 0.0]
           for sp in ("train", "test")}   # pnl, shares, sizedw, per-anchor, brier, recw
    rows = {}
    ti = 0
    qmax = 0.0; nbound = 0

    def refresh(now):
        nonlocal qlo, qhi, qmax, nbound
        ws = {True: [0.0, 0.0], False: [0.0, 0.0]}
        tot = [0.0, 0.0]
        for (s0, lo, pw, w, c) in book:
            if s0 + 360 > now:
                continue
            age = (now - s0) / 86400
            if age > window:
                continue
            wd = w * (0.5 ** (age / decay)) if decay else w
            ws[lo][0] += wd; ws[lo][1] += wd * pw
            tot[0] += wd; tot[1] += wd * pw
        if shrink:
            mean = (tot[1] + 50 * 0.5063) / (tot[0] + 50) if tot[0] else 0.5063
            slo = shi = mean
        else:
            slo, shi = seed
        rl = (ws[True][1] + M * slo) / (ws[True][0] + M)
        rh = (ws[False][1] + M * shi) / (ws[False][0] + M)
        qmax = max(qmax, rl, rh)
        if rl > cap or rh > cap:
            nbound += 1
        qlo = min(cap, round(rl, 4)); qhi = min(cap, round(rh, 4))

    for (s0, sp, pw0) in SIG:
        while ti < len(TICKS) - 1 and TICKS[ti + 1] <= s0:
            ti += 1; refresh(TICKS[ti])
        if not reset_done and s0 >= TEST_T0:
            bank = 1000.0; reset_done = True
        dropped = (s0 // 86400) in drop_days
        a = agg[sp]
        for p, w in ANCH:
            c = CST[p]; lo = lo_of[p]
            pw = 0.5 if (stress and c >= 0.50) else pw0
            q = qlo if lo else qhi
            a[5] += w; a[4] += w * (pw * (1 - q) ** 2 + (1 - pw) * q ** 2)
            book.append((s0, lo, pw, w, c))
            if bank < 250:
                continue
            qh = 0.5 + (q - 0.5) / 2 if forced_haircut else q
            f = qh - (1 - qh) * c / (1 - c)
            if f <= 0:
                continue
            stk = min(0.25 * f * bank, 0.05 * bank)
            if stk < 1.0:
                continue
            sh = stk / p
            ev = sh * (pw * (1 - c) - (1 - pw) * c) - GAS
            bank += w * ev
            if dropped:
                continue                    # excluded from scoring, not from learning
            a[0] += w * ev; a[1] += w * sh; a[2] += w
            a[3][p] += w * ev
            if sp == "test":
                rows[s0] = rows.get(s0, 0.0) + w * ev
    out = {}
    for sp in ("train", "test"):
        pnl, sh, szw, per, br, rw = agg[sp]
        out[sp] = dict(pnl=round(pnl, 2),
                       cps=round(100 * pnl / sh, 3) if sh else None,
                       brier=round(br / rw, 5),
                       sized_per_day=round(szw / NDAYS[sp], 2),
                       anchors={str(k): round(v, 2) for k, v in per.items()})
    out["q_max_raw"] = round(qmax, 4); out["nights_cap_bound"] = nbound
    if want_rows:
        out["_rows"] = rows
    return out


FAM = {"a_current": dict(bucket="cost", M=400, seed=(0.5057, 0.5068)),
       "b_spec": dict(bucket="peff", M=200, seed=(0.5, 0.5))}
for M in (50, 100, 200, 400):
    FAM[f"c_M{M}_neutral"] = dict(M=M, seed=(0.506, 0.506))
    FAM[f"c_M{M}_informed"] = dict(M=M, seed=(0.54, 0.54))
FAM["d_win10"] = dict(window=10, seed=(0.506, 0.506))
FAM["d_winInf"] = dict(window=10 ** 6, seed=(0.506, 0.506))
FAM["d_decay7"] = dict(window=10 ** 6, decay=7, seed=(0.506, 0.506))
FAM["d_decay14"] = dict(window=10 ** 6, decay=14, seed=(0.506, 0.506))
FAM["e_shrink100"] = dict(M=100, shrink=True, seed=(0.506, 0.506))
FAM["e_shrink200"] = dict(M=200, shrink=True, seed=(0.506, 0.506))
CAPV = [("a_current", 0.60), ("a_current", 1.00), ("b_spec", 0.60), ("b_spec", 1.00),
        ("c_M50_informed", 0.60), ("c_M50_informed", 1.00)]

res = {}
for nm, kw in FAM.items():
    res[nm] = wf(**kw)
for base, cap in CAPV:
    res[f"{base}_cap{int(cap * 100)}"] = wf(**{**FAM[base], "cap": cap})

mine_rank = sorted(res, key=lambda k: -res[k]["train"]["pnl"])
unit = json.load(open("/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/"
                      "work-deepen/qhat/calib_results.json"))
unit_rank = [k for k, _, _ in unit["ranked_by_train_pnl"]]
cmp_tbl = {k: dict(mine=(res[k]["train"]["pnl"], res[k]["test"]["pnl"]),
                   unit=(unit["results"][k]["train"]["pnl"], unit["results"][k]["test"]["pnl"]))
           for k in res}

# ---------------- paired boots (my own seeds: 20260713) ----------------
def boot(rowsA, rowsB, drop_days=(), seed=20260713, nb=6000):
    hrs = {}
    for t0, v in rowsA.items():
        if t0 // 86400 in drop_days: continue
        hrs.setdefault(t0 // 3600, [0.0, 0.0])[0] += v
    for t0, v in rowsB.items():
        if t0 // 86400 in drop_days: continue
        hrs.setdefault(t0 // 3600, [0.0, 0.0])[1] += v
    d = [b - a for a, b in hrs.values()]
    rng = random.Random(seed)
    n = len(d)
    xs = sorted(sum(rng.choice(d) for _ in range(n)) for _ in range(nb))
    return dict(point=round(sum(d), 2), n_blocks=n,
                ci90=[round(xs[int(0.05 * nb)], 2), round(xs[int(0.95 * nb)], 2)],
                p_le_0=round(sum(1 for x in xs if x <= 0) / nb, 4))

HYB = dict(bucket="cost", M=200, seed=(0.5, 0.5))
SEEDLED = dict(bucket="cost", M=200, seed=(0.5057, 0.5068))
WINNER = {**FAM["c_M50_informed"], "cap": 0.60}

pairs = {}
r_cur_b = wf(**FAM["a_current"], want_rows=True)["_rows"]
r_cur_s = wf(**FAM["a_current"], stress=True, want_rows=True)["_rows"]
r_spec_b = wf(**FAM["b_spec"], want_rows=True)["_rows"]
r_spec_s = wf(**FAM["b_spec"], stress=True, want_rows=True)["_rows"]
r_hyb_b = wf(**HYB, want_rows=True)["_rows"]
r_hyb_s = wf(**HYB, stress=True, want_rows=True)["_rows"]
r_sl_b = wf(**SEEDLED, want_rows=True)["_rows"]
r_win_b = wf(**WINNER, want_rows=True)["_rows"]
pairs["winner_vs_current_base"] = boot(r_cur_b, r_win_b)
pairs["spec_vs_current_base"] = boot(r_cur_b, r_spec_b)
pairs["spec_vs_current_stress"] = boot(r_cur_s, r_spec_s)
pairs["hybrid_vs_current_base"] = boot(r_cur_b, r_hyb_b)
pairs["hybrid_vs_current_stress"] = boot(r_cur_s, r_hyb_s)
pairs["seed_effect_base"] = boot(r_sl_b, r_hyb_b)
pairs["mass_effect_base"] = boot(r_cur_b, r_sl_b)

# ---------------- stress 1: drop best/worst TEST day ----------------
def daily(rows):
    d = {}
    for t0, v in rows.items():
        d[t0 // 86400] = d.get(t0 // 86400, 0.0) + v
    return d

drops = {}
for tag, (ra, rb) in dict(winner_vs_current=(r_cur_b, r_win_b),
                          hybrid_vs_current_base=(r_cur_b, r_hyb_b),
                          hybrid_vs_current_stress=(r_cur_s, r_hyb_s),
                          spec_vs_current_stress=(r_cur_s, r_spec_s)).items():
    da, db = daily(ra), daily(rb)
    dd = {k: db.get(k, 0) - da.get(k, 0) for k in set(da) | set(db)}
    best = max(dd, key=dd.get); worst = min(dd, key=dd.get)
    drops[tag] = dict(
        best_day_delta=round(dd[best], 2), worst_day_delta=round(dd[worst], 2),
        drop_best=boot(ra, rb, drop_days={best}),
        drop_worst=boot(ra, rb, drop_days={worst}))

# also: TRAIN ranking stability dropping the winner's best TRAIN day
# (recompute full wf with that day's signals excluded from scoring)
r_win_full = wf(**WINNER, want_rows=False)
# find winner's best TRAIN day by rerunning with train rows collected
def train_daily(kw):
    o = wf(**kw)
    return o
# cheap approach: recompute all families excluding the best TRAIN day of the current winner
# best TRAIN day identified from a run that logs train rows:
def wf_train_rows(kw, stress=False):
    kw2 = dict(kw); rows = {}
    o = wf(**kw2, want_rows=True)
    return o
# identify best TRAIN day for the winner via a variant run
def train_rows_of(kw):
    # rerun wf but collect train rows by temporarily treating them as test
    lo_kw = dict(kw)
    out = {}
    # quick inline: replicate wf loop minimally — reuse wf by monkey trick is messy;
    # instead approximate: daily TRAIN pnl of winner from a second wf pass below.
    return out

drop_train = {}
# direct approach: modify wf via drop_days on candidate best TRAIN days.
# find best TRAIN day by scanning daily pnl using a run with rows for train:
def wf_rows_split(kw, split="train", stress=False):
    saveT0 = None
    rows = {}
    # duplicate the core loop with split filter (kept simple: call wf twice with
    # doctored TEST boundary is risky; do a small dedicated pass)
    lo_of = {p: (CST[p] < kw.get("edge", 0.50)) if kw.get("bucket", "peff") == "cost"
             else (p < kw.get("edge", 0.50)) for p, _ in ANCH}
    book = []; qlo = min(kw.get("cap", 0.56), kw["seed"][0]); qhi = min(kw.get("cap", 0.56), kw["seed"][1])
    bank = 1000.0; reset_done = False; ti = 0
    M = kw.get("M", 200); window = kw.get("window", 30); decay = kw.get("decay")
    shrink = kw.get("shrink", False); cap = kw.get("cap", 0.56); seed = kw["seed"]
    def refresh(now):
        nonlocal qlo, qhi
        ws = {True: [0.0, 0.0], False: [0.0, 0.0]}; tot = [0.0, 0.0]
        for (s0, lo, pw, w, c) in book:
            if s0 + 360 > now: continue
            age = (now - s0) / 86400
            if age > window: continue
            wd = w * (0.5 ** (age / decay)) if decay else w
            ws[lo][0] += wd; ws[lo][1] += wd * pw; tot[0] += wd; tot[1] += wd * pw
        if shrink:
            mean = (tot[1] + 50 * 0.5063) / (tot[0] + 50) if tot[0] else 0.5063
            slo = shi = mean
        else:
            slo, shi = seed
        qlo = min(cap, round((ws[True][1] + M * slo) / (ws[True][0] + M), 4))
        qhi = min(cap, round((ws[False][1] + M * shi) / (ws[False][0] + M), 4))
    for (s0, sp, pw0) in SIG:
        while ti < len(TICKS) - 1 and TICKS[ti + 1] <= s0:
            ti += 1; refresh(TICKS[ti])
        if not reset_done and s0 >= TEST_T0:
            bank = 1000.0; reset_done = True
        for p, w in ANCH:
            c = CST[p]; lo = lo_of[p]
            pw = 0.5 if (stress and c >= 0.50) else pw0
            q = qlo if lo else qhi
            book.append((s0, lo, pw, w, c))
            if bank < 250: continue
            f = q - (1 - q) * c / (1 - c)
            if f <= 0: continue
            stk = min(0.25 * f * bank, 0.05 * bank)
            if stk < 1.0: continue
            sh = stk / p
            ev = sh * (pw * (1 - c) - (1 - pw) * c) - GAS
            bank += w * ev
            if sp == split:
                rows[s0] = rows.get(s0, 0.0) + w * ev
    return rows

win_tr = wf_rows_split(WINNER, "train")
dwin = daily(win_tr)
best_tr_day = max(dwin, key=dwin.get)
half_rank = {}
rerank = {}
for nm, kw in list(FAM.items()) + [("c_M50_informed_cap60", WINNER)]:
    o = wf(**kw, drop_days={best_tr_day})
    rerank[nm] = o["train"]["pnl"]
drop_train = dict(best_train_day_utc=best_tr_day * 86400,
                  winner_day_pnl=round(dwin[best_tr_day], 2),
                  rerank_top5=sorted(rerank.items(), key=lambda kv: -kv[1])[:5])

# ---------------- stress 2: bucket-edge jitter +-1c ----------------
jit = {}
for nm, kw in dict(a_current=FAM["a_current"], b_spec=FAM["b_spec"], hybrid=HYB).items():
    for e in (0.49, 0.50, 0.51):
        o_b = wf(**kw, edge=e)
        o_s = wf(**kw, edge=e, stress=True)
        jit[f"{nm}_edge{int(e * 100)}"] = dict(
            base=(o_b["train"]["pnl"], o_b["test"]["pnl"]),
            stress=(o_s["train"]["pnl"], o_s["test"]["pnl"]),
            stress_anchor49_test=o_s["test"]["anchors"]["0.49"])

# ---------------- stress 3: halved prior grid ----------------
for M in (25, 50, 100, 200):
    for sd, tag in ((0.506, "neutral"), (0.54, "informed")):
        half_rank[f"h_M{M}_{tag}"] = wf(M=M, seed=(sd, sd))["train"]["pnl"]
half_rank["a_current"] = res["a_current"]["train"]["pnl"]
half_rank["b_spec"] = res["b_spec"]["train"]["pnl"]
half_sorted = sorted(half_rank.items(), key=lambda kv: -kv[1])

# ---------------- cap grid + forced haircut ----------------
cap_grid = {}
for nm in ("a_current", "b_spec", "c_M400_informed"):
    for cap in (0.54, 0.56, 0.58, 0.60, 1.00):
        o = wf(**{**FAM[nm], "cap": cap})
        cap_grid[f"{nm}_cap{int(round(cap * 100))}"] = (o["train"]["pnl"], o["test"]["pnl"],
                                                        o["q_max_raw"], o["nights_cap_bound"])
hc = {}
for nm in ("a_current", "b_spec", "c_M400_informed"):
    b = wf(**FAM[nm]); h = wf(**FAM[nm], forced_haircut=True)
    hc[nm] = dict(test_delta=round(h["test"]["pnl"] - b["test"]["pnl"], 2),
                  test_delta_per_day=round((h["test"]["pnl"] - b["test"]["pnl"]) / NDAYS["test"], 2),
                  cps_base=b["test"]["cps"], cps_haircut=h["test"]["cps"])

out = dict(n_signals=len(SIG), n_train=sum(1 for s in SIG if s[1] == "train"),
           n_ticks=len(TICKS), days=NDAYS,
           families_cmp=cmp_tbl, my_rank=mine_rank, unit_rank=unit_rank,
           rank_top6_match=mine_rank[:6] == unit_rank[:6],
           boots=pairs, stress_dropday=drops, drop_best_train_day=drop_train,
           stress_jitter=jit, stress_halfgrid=half_sorted,
           cap_grid=cap_grid, haircut_forced=hc)
json.dump(out, open(os.path.join(HERE, "v_calib_results.json"), "w"), indent=1)
print(json.dumps({k: out[k] for k in ("n_signals", "n_train", "rank_top6_match",
                                      "boots", "stress_dropday", "stress_halfgrid")}, indent=1))
