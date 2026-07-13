#!/usr/bin/env python3
"""Part 2/3 — qhat calibrator families, walk-forward on signals_60d.json.

Frozen fill model (meta.fill_model): fills at anchors .45/.49/.51 w/ quartile
weights .25/.50/.25, availability .55, EV/share = q - p - .07p(1-p), gas .004.
Expected-book mode (deterministic): each gated signal contributes 3 weighted
fill scenarios; the measurement book, qhat updates, Kelly stakes, bank and
Brier all use scenario weights. MC mode (25 seeds) cross-checks rankings.

Scoring: Brier on the measurement book + realized quarter-Kelly PnL (the
metric that pays). Pick by TRAIN (May 11-Jun 25), report TEST (Jun 26-Jul 13).
Ties: pwin = .432 (up) / .568 (down) per live PM joins; bounds as sensitivity.

stdlib only. Writes calib_results.json.
"""
import json, os, math, random

HERE = os.path.dirname(os.path.abspath(__file__))
DS = json.load(open("/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/"
                    "work-deepen/dataset/signals_60d.json"))
TEST_T0 = 1782432000
FEE, GAS, MINORD = 0.07, 0.004, 1.0
ANCHORS = [(0.45, 0.25 * 0.55), (0.49, 0.50 * 0.55), (0.51, 0.25 * 0.55)]
COST = {p: p + FEE * p * (1 - p) for p, _ in ANCHORS}
TIE_UP = 0.432   # P(PM resolves up | candle tie), live join 32/74

signals = []
for r in DS["rows"]:
    if not (r["trigger"] and r["gatePass"]):
        continue
    if r["side"] == "up":
        pwin = 1.0 if r["label"] == "up" else (TIE_UP if r["label"] == "tie" else 0.0)
    else:
        pwin = 1.0 if r["label"] == "down" else ((1 - TIE_UP) if r["label"] == "tie" else 0.0)
    signals.append(dict(t0=r["t0"], split=r["split"], pwin=pwin, tie=(r["label"] == "tie")))
signals.sort(key=lambda s: s["t0"])
T0, T1 = signals[0]["t0"], signals[-1]["t0"]
DAYS = dict(train=(TEST_T0 - T0) / 86400.0, test=(T1 + 300 - TEST_T0) / 86400.0)

def nightly_ticks():
    t = ((T0 // 86400) + 1) * 86400 + 600
    out = []
    while t <= T1 + 86400:
        out.append(t); t += 86400
    return out
TICKS = nightly_ticks()

# ---------------- family definitions ----------------
def fam(name, bucket, M, seed, window=30, decay_hl=None, shrink=None, cap=0.56,
        guards=None, tie_mode="frac", note=""):
    return dict(name=name, bucket=bucket, M=M, seed=seed, window=window,
                decay_hl=decay_hl, shrink=shrink, cap=cap, guards=guards,
                tie_mode=tie_mode, note=note)

FAMILIES = [
    fam("a_current", "cost", 400, (0.5057, 0.5068), note="deployed impl"),
    fam("b_spec", "peff", 200, (0.5, 0.5), note="registered FINAL-DESIGN 4.2"),
]
for M in (50, 100, 200, 400):
    for sd, tag in ((0.506, "neutral"), (0.54, "informed")):
        FAMILIES.append(fam(f"c_M{M}_{tag}", "peff", M, (sd, sd)))
FAMILIES += [
    fam("d_win10", "peff", 200, (0.506, 0.506), window=10),
    fam("d_winInf", "peff", 200, (0.506, 0.506), window=10**6),
    fam("d_decay7", "peff", 200, (0.506, 0.506), window=10**6, decay_hl=7),
    fam("d_decay14", "peff", 200, (0.506, 0.506), window=10**6, decay_hl=14),
    fam("e_shrink100", "peff", 100, (0.506, 0.506), shrink="pooled"),
    fam("e_shrink200", "peff", 200, (0.506, 0.506), shrink="pooled"),
]
# cap variants (selection-counted) applied to the two structural finalists,
# plus the one family whose raw qhat actually reaches the .56 cap (M50 informed)
CAP_VARIANTS = [("a_current", 0.60), ("a_current", 1.00), ("b_spec", 0.60), ("b_spec", 1.00),
                ("c_M50_informed", 0.60), ("c_M50_informed", 1.00)]

def bucket_is_lo(famc, p):
    cost = COST[p]
    return (cost < 0.50) if famc["bucket"] == "cost" else (p < 0.50)

# ---------------- walk-forward engine (expected-book) ----------------
def run(famc, tie_mode="frac", guards=None, collect_rows=False):
    """guards: None | 'code' | 'spec'. Returns metrics dict."""
    book = []          # (t0, lo_bucket, pwin_used, w, cost)
    qlo, qhi = min(famc["cap"], famc["seed"][0]), min(famc["cap"], famc["seed"][1])
    bank, bank_reset = 1000.0, False
    benched, haircut = False, False
    tick_i = 0
    stats = {sp: dict(pnl=0.0, shares=0.0, sized_w=0.0, rec_w=0.0, brier=0.0,
                      stake_w=0.0, pnl_anchor={0.45: 0.0, 0.49: 0.0, 0.51: 0.0})
             for sp in ("train", "test")}
    caps_bound = 0; nights = 0; q_traj = []
    rows = [] if collect_rows else None

    def upd():
        nonlocal qlo, qhi, caps_bound, benched, haircut, nights
        tick = TICKS[tick_i]
        lo_w = lo_s = hi_w = hi_s = all_w = all_s = 0.0
        n7 = n7w = n15 = n15w = n10 = n10w = 0.0
        for (t0, lo, pw, w, c) in book:
            if t0 + 360 > tick: continue
            age = (tick - t0) / 86400.0
            if age > famc["window"]: continue
            wd = w * (0.5 ** (age / famc["decay_hl"]) if famc["decay_hl"] else 1.0)
            all_w += wd; all_s += wd * pw
            if lo: lo_w += wd; lo_s += wd * pw
            else:  hi_w += wd; hi_s += wd * pw
            net = pw * (1 - c) - (1 - pw) * c
            if age <= 7:  n7 += w * net;  n7w += w
            if age <= 10: n10 += w * net; n10w += w
            if age <= 15: n15 += w * net; n15w += w
        if famc["shrink"] == "pooled":
            qbar = (all_s + 50 * 0.5063) / (all_w + 50) if all_w else 0.5063
            slo, shi = qbar, qbar
        else:
            slo, shi = famc["seed"]
        M = famc["M"]
        raw_lo = (lo_s + M * slo) / (lo_w + M)
        raw_hi = (hi_s + M * shi) / (hi_w + M)
        if raw_lo > famc["cap"] or raw_hi > famc["cap"]: caps_bound += 1
        qlo, qhi = min(famc["cap"], round(raw_lo, 4)), min(famc["cap"], round(raw_hi, 4))
        nights += 1
        q_traj.append((tick, qlo, qhi, round(raw_lo, 4), round(raw_hi, 4)))
        if guards:
            v7 = n7 / n7w if n7w >= 120 else None
            v15 = n15 / n15w if n15w >= 250 else None
            v10 = n10 / n10w if n10w >= 100 else None
            if (v15 is not None and v15 < -0.03) or (v7 is not None and v7 < -0.04):
                benched = True
            elif benched and v10 is not None and v10 >= 0:
                benched = False
            if guards == "code":
                haircut = bool((v15 is not None and v15 < -0.01) or (v7 is not None and v7 < -0.02))
            else:  # spec: single 7d tier w/ hysteresis
                if haircut: haircut = bool(v7 is not None and v7 < -0.01)
                else:       haircut = bool(v7 is not None and v7 < -0.02)

    for s in signals:
        while tick_i < len(TICKS) - 1 and TICKS[tick_i + 1] <= s["t0"]:
            tick_i += 1; upd()
        if not bank_reset and s["t0"] >= TEST_T0:
            bank, bank_reset = 1000.0, True
        sp = s["split"]; st = stats[sp]
        if s["tie"]:
            if tie_mode == "excl": continue
            pw = 0.0 if tie_mode == "loss" else s["pwin"]
        else:
            pw = s["pwin"]
        for p, w in ANCHORS:
            c = COST[p]; lo = bucket_is_lo(famc, p)
            q = qlo if lo else qhi
            qh = 0.5 + (q - 0.5) / 2 if haircut else q
            st["rec_w"] += w
            st["brier"] += w * (pw * (1 - q) ** 2 + (1 - pw) * q ** 2)
            book.append((s["t0"], lo, pw, w, c))
            if benched or bank < 250: continue
            f = qh - (1 - qh) * c / (1 - c)
            if f <= 0: continue
            stake = min(0.25 * f * bank, 0.05 * bank)
            if stake < MINORD: continue
            shares = stake / p
            epnl = shares * (pw * (1 - c) - (1 - pw) * c) - GAS
            st["pnl"] += w * epnl; st["shares"] += w * shares
            st["sized_w"] += w; st["stake_w"] += w * stake
            st["pnl_anchor"][p] += w * epnl
            bank += w * epnl
            if collect_rows: rows.append((s["t0"], sp, p, w * epnl))
    # final tick flush not needed (no scoring after last signal)
    out = {}
    for sp in ("train", "test"):
        st = stats[sp]
        out[sp] = dict(pnl=round(st["pnl"], 2),
                       cps=round(100 * st["pnl"] / st["shares"], 3) if st["shares"] else None,
                       brier=round(st["brier"] / st["rec_w"], 5) if st["rec_w"] else None,
                       sized_per_day=round(st["sized_w"] / DAYS[sp], 2),
                       mean_stake=round(st["stake_w"] / st["sized_w"], 2) if st["sized_w"] else None,
                       pnl_anchor={str(k): round(v, 2) for k, v in st["pnl_anchor"].items()})
    out["nights_cap_bound"] = caps_bound
    out["q_final"] = q_traj[-1][1:3] if q_traj else None
    out["q_max_raw"] = max((t[3] for t in q_traj), default=None)
    if collect_rows: out["_rows"] = rows
    return out

# ---------------- run all families (guards OFF = calibrator isolation) ----------------
results = {}
for f in FAMILIES:
    results[f["name"]] = run(f)
for base, cap in CAP_VARIANTS:
    f = dict(next(x for x in FAMILIES if x["name"] == base)); f["cap"] = cap
    results[f"{base}_cap{int(cap*100)}"] = run(f)

K = len(FAMILIES) + len(CAP_VARIANTS)

# ---------------- selection by TRAIN pnl ----------------
ranked = sorted(results.items(), key=lambda kv: -kv[1]["train"]["pnl"])
winner = ranked[0][0]

# ---------------- tie-handling bounds + guard mechanism runs (not selection) ----------
sens = {}
for nm in ("a_current", "b_spec", winner.split("_cap")[0] if "_cap" in winner else winner):
    f = next(x for x in FAMILIES if x["name"] == nm)
    for tm in ("loss", "excl"):
        sens[f"{nm}_tie_{tm}"] = {sp: run(f, tie_mode=tm)[sp] for sp in ("train", "test")}
guard_runs = {}
for nm in ("a_current", "b_spec"):
    f = next(x for x in FAMILIES if x["name"] == nm)
    for g in ("code", "spec"):
        guard_runs[f"{nm}_guards_{g}"] = run(f, guards=g)

# ---------------- paired TEST delta winner-vs-current, 1h-block bootstrap ----------
fw = next((x for x in FAMILIES if x["name"] == winner), None)
if fw is None:
    base, cap = winner.split("_cap")
    fw = dict(next(x for x in FAMILIES if x["name"] == base)); fw["cap"] = int(cap) / 100.0
ra = run(next(x for x in FAMILIES if x["name"] == "a_current"), collect_rows=True)
rw = run(fw, collect_rows=True)
da = {}
for t0, sp, p, v in ra["_rows"]:
    if sp == "test": da.setdefault(t0 // 3600, [0.0, 0.0])[0] += v
for t0, sp, p, v in rw["_rows"]:
    if sp == "test": da.setdefault(t0 // 3600, [0.0, 0.0])[1] += v
blocks = [w - a for a, w in da.values()]
rng = random.Random(7)
bs = []
for _ in range(4000):
    bs.append(sum(rng.choice(blocks) for _ in range(len(blocks))))
bs.sort()
delta_test = dict(point=round(sum(blocks), 2), n_blocks=len(blocks),
                  ci90=[round(bs[int(0.05 * len(bs))], 2), round(bs[int(0.95 * len(bs))], 2)],
                  p_le_0=round(sum(1 for x in bs if x <= 0) / len(bs), 4))

# ---------------- MC cross-check (25 seeds) on finalists ----------------
def run_mc(famc, seed):
    rng = random.Random(seed)
    book = []; qlo, qhi = min(famc["cap"], famc["seed"][0]), min(famc["cap"], famc["seed"][1])
    bank, bank_reset = 1000.0, False
    tick_i = 0
    pnl = dict(train=0.0, test=0.0); shares = dict(train=0.0, test=0.0)
    def upd():
        nonlocal qlo, qhi
        tick = TICKS[tick_i]
        lo_w = lo_s = hi_w = hi_s = 0.0
        for (t0, lo, y, c) in book:
            if t0 + 360 > tick or (tick - t0) / 86400.0 > famc["window"]: continue
            if lo: lo_w += 1; lo_s += y
            else:  hi_w += 1; hi_s += y
        M = famc["M"]; slo, shi = famc["seed"]
        qlo = min(famc["cap"], round((lo_s + M * slo) / (lo_w + M), 4))
        qhi = min(famc["cap"], round((hi_s + M * shi) / (hi_w + M), 4))
    for s in signals:
        while tick_i < len(TICKS) - 1 and TICKS[tick_i + 1] <= s["t0"]:
            tick_i += 1; upd()
        if not bank_reset and s["t0"] >= TEST_T0: bank, bank_reset = 1000.0, True
        if rng.random() >= 0.55: continue
        u = rng.random(); p = 0.45 if u < 0.25 else (0.49 if u < 0.75 else 0.51)
        c = COST[p]; lo = bucket_is_lo(famc, p)
        y = 1 if rng.random() < s["pwin"] else 0
        book.append((s["t0"], lo, y, c))
        q = qlo if lo else qhi
        f = q - (1 - q) * c / (1 - c)
        if f <= 0: continue
        stake = min(0.25 * f * bank, 0.05 * bank)
        if stake < MINORD: continue
        sh = stake / p
        v = sh * ((1 - c) if y else -c) - GAS
        pnl[s["split"]] += v; shares[s["split"]] += sh; bank += v
    return {sp: (round(pnl[sp], 2), round(100 * pnl[sp] / shares[sp], 2) if shares[sp] else None)
            for sp in ("train", "test")}

mc = {}
for nm in ("a_current", "b_spec", winner if "_cap" not in winner else winner.split("_cap")[0]):
    f = next(x for x in FAMILIES if x["name"] == nm)
    runs = [run_mc(f, 1000 + i) for i in range(25)]
    for sp in ("train", "test"):
        xs = [r[sp][0] for r in runs]
        mu = sum(xs) / len(xs)
        sd = (sum((x - mu) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5
        mc.setdefault(nm, {})[sp] = dict(pnl_mean=round(mu, 1), pnl_sd=round(sd, 1),
                                         win_frac=round(sum(1 for x in xs if x > 0) / len(xs), 2))

out = dict(K_selection=K, families={f["name"]: {k: f[k] for k in
           ("bucket", "M", "seed", "window", "decay_hl", "shrink", "cap")} for f in FAMILIES},
           results=results, ranked_by_train_pnl=[(k, v["train"]["pnl"], v["test"]["pnl"])
                                                 for k, v in ranked],
           winner_by_train=winner, winner_vs_current_test_delta=delta_test,
           tie_sensitivity=sens, guard_runs=guard_runs, mc_check=mc,
           notes=["expected-book deterministic primary; MC 25 seeds cross-check",
                  "fill model frozen + row-independent: bucket-definition differences are "
                  "under-identified offline (both buckets converge to the same pooled q); "
                  "rankings reflect prior mass / window / seed / cap only",
                  "any family whose edge comes from opening the .49/.51 anchors is flagged "
                  "vs wave-1 R2 (48-53c fee-dead) — see pnl_anchor"])
json.dump(out, open(os.path.join(HERE, "calib_results.json"), "w"), indent=1)
print(json.dumps({k: out[k] for k in ("K_selection", "ranked_by_train_pnl", "winner_by_train",
                                      "winner_vs_current_test_delta", "mc_check")}, indent=1))
