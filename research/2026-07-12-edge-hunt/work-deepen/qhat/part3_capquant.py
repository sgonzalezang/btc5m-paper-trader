#!/usr/bin/env python3
"""Part 3/4 — cap & haircut quantification, R2-consistent stress, live-book
noise check, guard reachability. Extends calib_wf.py's expected-book engine
(same conventions; runs verified byte-identical on re-run before extending).

Modes added to the walk-forward engine:
  * cap grid          — caps {.54,.56,.58,.60,1.0} x {a_current,b_spec,c_M400_informed}
  * force_haircut     — haircut active every night: the $/c-per-share cost of a
                        falsely-active haircut under each family
  * stress_zone       — wave-1 R2-consistent scoring: anchors with cost>=.50
                        (.49 and .51 fills) carry ZERO edge (pw=0.5 for scoring
                        AND for what the measurement book learns from). The
                        frozen fill model otherwise applies the pooled q to all
                        anchors, which contradicts R2 (48-53c fee-dead in every
                        era). Re-ranks all families under stress.
  * live-book table   — each family's qhat on the REAL 36-record book and the
                        sized/skip decision flips vs the deployed state.

stdlib only. Writes part3_results.json.
"""
import json, os, math, random

HERE = os.path.dirname(os.path.abspath(__file__))
DS = json.load(open("/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/"
                    "work-deepen/dataset/signals_60d.json"))
ST = json.load(open("/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/"
                    "data/state_extract.json"))
TEST_T0 = 1782432000
FEE, GAS, MINORD = 0.07, 0.004, 1.0
ANCHORS = [(0.45, 0.25 * 0.55), (0.49, 0.50 * 0.55), (0.51, 0.25 * 0.55)]
COST = {p: p + FEE * p * (1 - p) for p, _ in ANCHORS}
TIE_UP = 0.432

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

def fam(name, bucket, M, seed, window=30, decay_hl=None, shrink=None, cap=0.56):
    return dict(name=name, bucket=bucket, M=M, seed=seed, window=window,
                decay_hl=decay_hl, shrink=shrink, cap=cap)

FAMILIES = [fam("a_current", "cost", 400, (0.5057, 0.5068)),
            fam("b_spec", "peff", 200, (0.5, 0.5))]
for M in (50, 100, 200, 400):
    for sd, tag in ((0.506, "neutral"), (0.54, "informed")):
        FAMILIES.append(fam(f"c_M{M}_{tag}", "peff", M, (sd, sd)))
FAMILIES += [fam("d_win10", "peff", 200, (0.506, 0.506), window=10),
             fam("d_winInf", "peff", 200, (0.506, 0.506), window=10**6),
             fam("d_decay7", "peff", 200, (0.506, 0.506), window=10**6, decay_hl=7),
             fam("d_decay14", "peff", 200, (0.506, 0.506), window=10**6, decay_hl=14),
             fam("e_shrink100", "peff", 100, (0.506, 0.506), shrink="pooled"),
             fam("e_shrink200", "peff", 200, (0.506, 0.506), shrink="pooled")]
BYNAME = {f["name"]: f for f in FAMILIES}

def bucket_is_lo(famc, p):
    return (COST[p] < 0.50) if famc["bucket"] == "cost" else (p < 0.50)

def run(famc, force_haircut=False, stress_zone=False):
    book = []
    qlo, qhi = min(famc["cap"], famc["seed"][0]), min(famc["cap"], famc["seed"][1])
    bank, bank_reset = 1000.0, False
    tick_i = 0
    stats = {sp: dict(pnl=0.0, shares=0.0, sized_w=0.0, rec_w=0.0, brier=0.0, stake_w=0.0,
                      pnl_anchor={0.45: 0.0, 0.49: 0.0, 0.51: 0.0})
             for sp in ("train", "test")}
    caps_bound = 0; q_traj = []

    def upd():
        nonlocal qlo, qhi, caps_bound
        tick = TICKS[tick_i]
        lo_w = lo_s = hi_w = hi_s = all_w = all_s = 0.0
        for (t0, lo, pw, w, c) in book:
            if t0 + 360 > tick: continue
            age = (tick - t0) / 86400.0
            if age > famc["window"]: continue
            wd = w * (0.5 ** (age / famc["decay_hl"]) if famc["decay_hl"] else 1.0)
            all_w += wd; all_s += wd * pw
            if lo: lo_w += wd; lo_s += wd * pw
            else:  hi_w += wd; hi_s += wd * pw
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
        q_traj.append((tick, qlo, qhi, round(raw_lo, 4), round(raw_hi, 4)))

    for s in signals:
        while tick_i < len(TICKS) - 1 and TICKS[tick_i + 1] <= s["t0"]:
            tick_i += 1; upd()
        if not bank_reset and s["t0"] >= TEST_T0:
            bank, bank_reset = 1000.0, True
        sp = s["split"]; st = stats[sp]
        for p, w in ANCHORS:
            c = COST[p]; lo = bucket_is_lo(famc, p)
            pw = 0.5 if (stress_zone and c >= 0.50) else s["pwin"]
            q = qlo if lo else qhi
            qh = 0.5 + (q - 0.5) / 2 if force_haircut else q
            st["rec_w"] += w
            st["brier"] += w * (pw * (1 - q) ** 2 + (1 - pw) * q ** 2)
            book.append((s["t0"], lo, pw, w, c))
            if bank < 250: continue
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
    return out

# ---------------- 1. CAP grid (sensitivity, not selection) ----------------
cap_grid = {}
for nm in ("a_current", "b_spec", "c_M400_informed"):
    base = BYNAME[nm]
    for cap in (0.54, 0.56, 0.58, 0.60, 1.00):
        f = dict(base); f["cap"] = cap
        r = run(f)
        cap_grid[f"{nm}_cap{int(round(cap*100))}"] = dict(
            train_pnl=r["train"]["pnl"], test_pnl=r["test"]["pnl"],
            test_cps=r["test"]["cps"], nights_cap_bound=r["nights_cap_bound"],
            q_max_raw=r["q_max_raw"])

# ---------------- 2. forced-haircut cost ----------------
haircut_cost = {}
for nm in ("a_current", "b_spec", "c_M400_informed"):
    b = run(BYNAME[nm]); h = run(BYNAME[nm], force_haircut=True)
    haircut_cost[nm] = {sp: dict(
        pnl_base=b[sp]["pnl"], pnl_haircut=h[sp]["pnl"],
        delta_pnl=round(h[sp]["pnl"] - b[sp]["pnl"], 2),
        delta_per_day=round((h[sp]["pnl"] - b[sp]["pnl"]) / DAYS[sp], 2),
        cps_base=b[sp]["cps"], cps_haircut=h[sp]["cps"],
        sized_per_day_base=b[sp]["sized_per_day"], sized_per_day_haircut=h[sp]["sized_per_day"])
        for sp in ("train", "test")}

# ---------------- 3. R2-consistent stress: zero edge at cost>=.50 anchors ----
stress = {}
for f in FAMILIES:
    r = run(f, stress_zone=True)
    stress[f["name"]] = dict(train_pnl=r["train"]["pnl"], test_pnl=r["test"]["pnl"],
                             test_cps=r["test"]["cps"],
                             pnl_anchor_test=r["test"]["pnl_anchor"],
                             q_final=r["q_final"], q_max_raw=r["q_max_raw"])
stress_rank = sorted(stress.items(), key=lambda kv: -kv[1]["train_pnl"])

# paired TEST bootstrap current-vs-spec under stress AND base (hour blocks)
def rows_for(famc, stress_zone=False):
    """re-run collecting per-signal test pnl (sum over anchors)"""
    book = []; qlo, qhi = min(famc["cap"], famc["seed"][0]), min(famc["cap"], famc["seed"][1])
    bank, bank_reset = 1000.0, False; tick_i = 0
    out = {}
    def upd():
        nonlocal qlo, qhi
        tick = TICKS[tick_i]
        lo_w = lo_s = hi_w = hi_s = 0.0
        for (t0, lo, pw, w, c) in book:
            if t0 + 360 > tick or (tick - t0) / 86400.0 > famc["window"]: continue
            wd = w * (0.5 ** (((tick - t0) / 86400.0) / famc["decay_hl"]) if famc["decay_hl"] else 1.0)
            if lo: lo_w += wd; lo_s += wd * pw
            else:  hi_w += wd; hi_s += wd * pw
        M = famc["M"]; slo, shi = famc["seed"]
        qlo = min(famc["cap"], round((lo_s + M * slo) / (lo_w + M), 4))
        qhi = min(famc["cap"], round((hi_s + M * shi) / (hi_w + M), 4))
    for s in signals:
        while tick_i < len(TICKS) - 1 and TICKS[tick_i + 1] <= s["t0"]:
            tick_i += 1; upd()
        if not bank_reset and s["t0"] >= TEST_T0: bank, bank_reset = 1000.0, True
        for p, w in ANCHORS:
            c = COST[p]; lo = bucket_is_lo(famc, p)
            pw = 0.5 if (stress_zone and c >= 0.50) else s["pwin"]
            book.append((s["t0"], lo, pw, w, c))
            if bank < 250: continue
            q = qlo if lo else qhi
            f = q - (1 - q) * c / (1 - c)
            if f <= 0: continue
            stake = min(0.25 * f * bank, 0.05 * bank)
            if stake < MINORD: continue
            sh = stake / p
            epnl = sh * (pw * (1 - c) - (1 - pw) * c) - GAS
            bank += w * epnl
            if s["split"] == "test": out[s["t0"]] = out.get(s["t0"], 0.0) + w * epnl
    return out

def paired_boot(nameA, nameB, stress_zone):
    ra, rb = rows_for(BYNAME[nameA], stress_zone), rows_for(BYNAME[nameB], stress_zone)
    hrs = {}
    for t0, v in ra.items(): hrs.setdefault(t0 // 3600, [0.0, 0.0])[0] += v
    for t0, v in rb.items(): hrs.setdefault(t0 // 3600, [0.0, 0.0])[1] += v
    blocks = [b - a for a, b in hrs.values()]
    rng = random.Random(11); bs = []
    for _ in range(4000):
        bs.append(sum(rng.choice(blocks) for _ in range(len(blocks))))
    bs.sort()
    return dict(point=round(sum(blocks), 2), n_blocks=len(blocks),
                ci90=[round(bs[int(0.05 * len(bs))], 2), round(bs[int(0.95 * len(bs))], 2)],
                p_le_0=round(sum(1 for x in bs if x <= 0) / len(bs), 4))

spec_vs_current = dict(base=paired_boot("a_current", "b_spec", False),
                       stress=paired_boot("a_current", "b_spec", True))
informed_vs_spec_stress = paired_boot("b_spec", "c_M400_informed", True)

# ---------------- 4. LIVE-book (n=36) family table ----------------
ms = ST["measure"]
settled = [m for m in ms if m["win"] is not None]
def live_qhat(famc):
    # book records carry first-poll cost; peff = invert cost = 1.07p - .07p^2
    def peff_of(c):
        # solve .07p^2 -1.07p + c = 0 -> p = (1.07 - sqrt(1.07^2-4*.07*c))/(2*.07)
        return (1.07 - math.sqrt(1.07 * 1.07 - 0.28 * c)) / 0.14
    lo_n = lo_w = hi_n = hi_w = 0
    for m in settled:
        is_lo = (m["cost"] < 0.50) if famc["bucket"] == "cost" else (peff_of(m["cost"]) < 0.50)
        if is_lo: lo_n += 1; lo_w += m["win"]
        else:     hi_n += 1; hi_w += m["win"]
    M = famc["M"]; slo, shi = famc["seed"]
    if famc["shrink"] == "pooled":
        qbar = (lo_w + hi_w + 50 * 0.5063) / (lo_n + hi_n + 50)
        slo, shi = qbar, qbar
    qlo = min(famc["cap"], round((lo_w + M * slo) / (lo_n + M), 4))
    qhi = min(famc["cap"], round((hi_w + M * shi) / (hi_n + M), 4))
    return qlo, qhi, (lo_w, lo_n), (hi_w, hi_n)

def decisions(qlo, qhi, famc):
    dec = []
    for m in ms:
        c = m["cost"]
        p = (1.07 - math.sqrt(1.07 * 1.07 - 0.28 * c)) / 0.14
        is_lo = (c < 0.50) if famc["bucket"] == "cost" else (p < 0.50)
        q = qlo if is_lo else qhi
        f = q - (1 - q) * c / (1 - c)
        dec.append(bool(f > 0))
    return dec

cur = BYNAME["a_current"]
cur_dec = decisions(ST["impulse_cfg"]["qlo"], ST["impulse_cfg"]["qhi"], cur)
live_table = {}
for f in FAMILIES:
    qlo, qhi, lob, hib = live_qhat(f)
    dec = decisions(qlo, qhi, f)
    flips = [i for i in range(len(ms)) if dec[i] != cur_dec[i]]
    # first-poll EV of flipped records (what the flip is worth at kill-input semantics)
    ev_flip = 0.0
    for i in flips:
        m = ms[i]
        if m["win"] is None: continue
        net = (1 - m["cost"]) if m["win"] else -m["cost"]
        ev_flip += net if dec[i] else -net   # + if family newly sizes it, - if family drops it
    live_table[f["name"]] = dict(qlo=qlo, qhi=qhi, lo_book=lob, hi_book=hib,
                                 n_sized=sum(dec), flips_vs_deployed=len(flips),
                                 flip_ev_firstpoll_usd_per_share=round(ev_flip, 3))

# ---------------- 5. guard reachability arithmetic ----------------
rate = len(settled) / ((ms[-1]["t0"] - ms[0]["t0"]) / 86400.0)
n7_now = [m for m in settled if m["t0"] >= ms[-1]["t0"] - 7 * 86400]
net7 = sum((1 - m["cost"]) if m["win"] else -m["cost"] for m in n7_now) / len(n7_now)
guard_reach = dict(
    live_settle_rate_per_day=round(rate, 2),
    tier_needs=dict(haircut_7d_120=round(120 / 7, 1), bench_15d_250=round(250 / 15, 1),
                    bench_7d_120=round(120 / 7, 1), unbench_10d_100=round(100 / 10, 1)),
    reachable=dict(haircut_7d=bool(rate >= 120 / 7), bench_15d=bool(rate >= 250 / 15),
                   unbench_10d=bool(rate >= 100 / 10)),
    current_7d_netps_firstpoll_c=round(100 * net7, 2), n_7d=len(n7_now),
    r4_bias_note="wave-1 R4: first-poll book runs -6.23c/sh vs +3.55c/sh operated on the same "
                 "signals (gap 9.79c). A reachable haircut(-2c)/bench(-4c) tier fed by the "
                 "UNAMENDED book would currently fire on a policy positive as operated.",
    nmin_rescale_if_desired=dict(
        note="to make tiers reachable at the live 14.2/day settle cadence with ~20% margin",
        haircut_7d=80, bench_15d=170, unbench_10d=100))

out = dict(K_part3_runs=dict(cap_grid=len(cap_grid), haircut=len(haircut_cost) * 2,
                             stress=len(stress), boots=3, live_table=len(live_table)),
           cap_grid=cap_grid, haircut_cost=haircut_cost,
           stress_zone=dict(results=stress,
                            ranked_by_train=[(k, v["train_pnl"], v["test_pnl"]) for k, v in stress_rank]),
           spec_vs_current_test_boot=spec_vs_current,
           informed_vs_spec_stress_test_boot=informed_vs_spec_stress,
           live_book_table=live_table, deployed_decisions_n_sized=sum(cur_dec),
           guard_reachability=guard_reach)
json.dump(out, open(os.path.join(HERE, "part3_results.json"), "w"), indent=1)
print(json.dumps(out, indent=1))
