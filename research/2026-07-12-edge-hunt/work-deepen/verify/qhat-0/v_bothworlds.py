#!/usr/bin/env python3
"""REPRO verify (qhat-0) — both-worlds robustness table + q_max_raw decomposition.

For every family (16 tournament + hybrid + seedled), TEST pnl under base and
under the R2 stress; flag which beat a_current in BOTH. Also track raw qhat
max separately per bucket (the unit's q_max_raw only tracked the LO bucket).
Plus a 15-seed MC cross-check of the a_current/b_spec/winner ordering.
stdlib only.
"""
import json, os, random
import importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("vc", os.path.join(HERE, "v_calib.py"))
# don't execute the whole tournament again — reimplement the tiny bits needed
DS = json.load(open("/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/"
                    "work-deepen/dataset/signals_60d.json"))
TEST_T0 = 1782432000
TIE_UP = 0.432
FEE, GAS = 0.07, 0.004
ANCH = [(0.45, 0.1375), (0.49, 0.275), (0.51, 0.1375)]
CST = {p: round(p + FEE * p * (1 - p), 6) for p, _ in ANCH}
SIG = []
for r in DS["rows"]:
    if not (r.get("trigger") and r.get("gatePass")):
        continue
    lab = r["label"]
    pw = (TIE_UP if r["side"] == "up" else 1 - TIE_UP) if lab == "tie" else (1.0 if lab == r["side"] else 0.0)
    SIG.append((r["t0"], r["split"], pw))
SIG.sort()
T0, T1 = SIG[0][0], SIG[-1][0]
TICKS = []
t = (T0 // 86400 + 1) * 86400 + 600
while t <= T1 + 86400:
    TICKS.append(t); t += 86400


def wf(bucket="peff", M=200, seed=(0.5, 0.5), cap=0.56, window=30, decay=None,
       shrink=False, stress=False):
    lo_of = {p: (CST[p] < 0.50) if bucket == "cost" else (p < 0.50) for p, _ in ANCH}
    book = []
    qlo, qhi = min(cap, seed[0]), min(cap, seed[1])
    bank, reset = 1000.0, False
    pnl = {"train": 0.0, "test": 0.0}
    qmax = {"lo": 0.0, "hi": 0.0}
    ti = 0

    def refresh(now):
        nonlocal qlo, qhi
        ws = {True: [0.0, 0.0], False: [0.0, 0.0]}; tot = [0.0, 0.0]
        for (s0, lo, pw, w, c) in book:
            if s0 + 360 > now: continue
            age = (now - s0) / 86400
            if age > window: continue
            wd = w * (0.5 ** (age / decay)) if decay else w
            ws[lo][0] += wd; ws[lo][1] += wd * pw
            tot[0] += wd; tot[1] += wd * pw
        if shrink:
            m = (tot[1] + 50 * 0.5063) / (tot[0] + 50) if tot[0] else 0.5063
            slo = shi = m
        else:
            slo, shi = seed
        rl = (ws[True][1] + M * slo) / (ws[True][0] + M)
        rh = (ws[False][1] + M * shi) / (ws[False][0] + M)
        qmax["lo"] = max(qmax["lo"], rl); qmax["hi"] = max(qmax["hi"], rh)
        qlo, qhi = min(cap, round(rl, 4)), min(cap, round(rh, 4))

    for (s0, sp, pw0) in SIG:
        while ti < len(TICKS) - 1 and TICKS[ti + 1] <= s0:
            ti += 1; refresh(TICKS[ti])
        if not reset and s0 >= TEST_T0:
            bank, reset = 1000.0, True
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
            bank += w * ev; pnl[sp] += w * ev
    return dict(train=round(pnl["train"], 2), test=round(pnl["test"], 2),
                qmax_lo=round(qmax["lo"], 4), qmax_hi=round(qmax["hi"], 4))


FAM = {"a_current": dict(bucket="cost", M=400, seed=(0.5057, 0.5068)),
       "b_spec": dict(bucket="peff", M=200, seed=(0.5, 0.5)),
       "hybrid_cost_M200": dict(bucket="cost", M=200, seed=(0.5, 0.5)),
       "cost_M200_seedled": dict(bucket="cost", M=200, seed=(0.5057, 0.5068)),
       "cost_M400_seedmean": dict(bucket="cost", M=400, seed=(0.5, 0.5))}
for M in (50, 100, 200, 400):
    FAM[f"c_M{M}_neutral"] = dict(M=M, seed=(0.506, 0.506))
    FAM[f"c_M{M}_informed"] = dict(M=M, seed=(0.54, 0.54))
FAM["d_win10"] = dict(window=10, seed=(0.506, 0.506))
FAM["d_winInf"] = dict(window=10 ** 6, seed=(0.506, 0.506))
FAM["d_decay7"] = dict(window=10 ** 6, decay=7, seed=(0.506, 0.506))
FAM["d_decay14"] = dict(window=10 ** 6, decay=14, seed=(0.506, 0.506))
FAM["e_shrink100"] = dict(M=100, shrink=True, seed=(0.506, 0.506))
FAM["e_shrink200"] = dict(M=200, shrink=True, seed=(0.506, 0.506))

tbl = {}
base_cur = wf(**FAM["a_current"])
str_cur = wf(**FAM["a_current"], stress=True)
for nm, kw in FAM.items():
    b = wf(**kw); s = wf(**kw, stress=True)
    tbl[nm] = dict(base_test=b["test"], stress_test=s["test"],
                   beats_current_base=b["test"] > base_cur["test"],
                   beats_current_stress=s["test"] > str_cur["test"],
                   both=(b["test"] > base_cur["test"] and s["test"] > str_cur["test"]),
                   qmax_lo=b["qmax_lo"], qmax_hi=b["qmax_hi"])
tbl["a_current"]["both"] = None

# ---- MC cross-check, my own seeds ----
def mc(kw, seed):
    rng = random.Random(seed)
    bucket = kw.get("bucket", "peff"); M = kw.get("M", 200); sd = kw["seed"]
    cap = kw.get("cap", 0.56); window = kw.get("window", 30)
    lo_of = {p: (CST[p] < 0.50) if bucket == "cost" else (p < 0.50) for p, _ in ANCH}
    book = []; qlo, qhi = sd; bank, reset = 1000.0, False; ti = 0
    pnl = {"train": 0.0, "test": 0.0}
    def refresh(now):
        nonlocal qlo, qhi
        ws = {True: [0, 0.0], False: [0, 0.0]}
        for (s0, lo, y, c) in book:
            if s0 + 360 > now or (now - s0) / 86400 > window: continue
            ws[lo][0] += 1; ws[lo][1] += y
        qlo = min(cap, round((ws[True][1] + M * sd[0]) / (ws[True][0] + M), 4))
        qhi = min(cap, round((ws[False][1] + M * sd[1]) / (ws[False][0] + M), 4))
    for (s0, sp, pw0) in SIG:
        while ti < len(TICKS) - 1 and TICKS[ti + 1] <= s0:
            ti += 1; refresh(TICKS[ti])
        if not reset and s0 >= TEST_T0: bank, reset = 1000.0, True
        if rng.random() >= 0.55: continue
        u = rng.random(); p = 0.45 if u < 0.25 else (0.49 if u < 0.75 else 0.51)
        c = CST[p]; lo = lo_of[p]
        y = 1 if rng.random() < pw0 else 0
        book.append((s0, lo, y, c))
        q = qlo if lo else qhi
        f = q - (1 - q) * c / (1 - c)
        if f <= 0: continue
        stk = min(0.25 * f * bank, 0.05 * bank)
        if stk < 1.0: continue
        sh = stk / p
        v = sh * ((1 - c) if y else -c) - GAS
        bank += v; pnl[sp] += v
    return pnl

mc_out = {}
for nm in ("a_current", "b_spec", "c_M50_informed", "hybrid_cost_M200"):
    runs = [mc(FAM[nm], 555000 + i) for i in range(15)]
    for sp in ("train", "test"):
        xs = sorted(r[sp] for r in runs)
        mc_out.setdefault(nm, {})[sp] = dict(mean=round(sum(xs) / 15, 1),
                                             med=round(xs[7], 1))

out = dict(both_worlds=tbl,
           both_worlds_winners=[k for k, v in tbl.items() if v.get("both")],
           mc_check=mc_out)
json.dump(out, open(os.path.join(HERE, "v_bothworlds_results.json"), "w"), indent=1)
print(json.dumps(out, indent=1))
