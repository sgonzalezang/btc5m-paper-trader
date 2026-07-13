#!/usr/bin/env python3
"""R8 independent reproduction — written from scratch from the claim's plain-English text.

Claim components verified here:
 A. Closed-form replication of _impulse_nightly reproduces state qlo/qhi (all 3 real nightlies).
 B. Deviation 1: bucket boundary cost<0.50 (code) vs p_eff<0.50 (registered FINAL-DESIGN 4.2).
 C. Deviation 2: prior mass 400/bucket (code) vs 200/bucket (registered); quantify learning speed.
 D. Deviation 3: M2 guard seeding absent; counterfactual — would seeded guards have fired?
 E. Bench counterfactual $0 (benched=false throughout live v3).
 F. Jul 10 restart flapping: nightly re-ran on stale pre-launch state N times.
 Stress: drop best day, halve sample, jitter bucket boundary +/-1c; day-block bootstrap of the
 code-vs-design qhat gap.
"""
import json, math, random, datetime

DATA = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data"
BOTD = "/Users/sgonzalez/btc5m-paper-trader/bot"
SEED_LO, SEED_HI = 0.5057, 0.5068
MASS_CODE = 400          # per bucket, code (IMP_PRIOR)
MASS_DESIGN = 200        # per bucket, FINAL-DESIGN 4.2: (w+100)/(n+200)
FEE = 0.07

def utc(t): return datetime.datetime.utcfromtimestamp(t).strftime("%m-%d %H:%M:%S")

def p_eff_from_cost(c):
    # invert c = p + 0.07 p (1-p)  =>  0.07 p^2 - 1.07 p + c = 0
    return (1.07 - math.sqrt(1.07**2 - 4*0.07*c)) / (2*0.07)

def qhat_code(rows, lo, mass=MASS_CODE, cap=0.56):
    seed = SEED_LO if lo else SEED_HI
    xs = [m for m in rows if (m["cost"] < 0.50) == lo]
    return round(min(cap, (sum(m["win"] for m in xs) + mass*seed) / (len(xs) + mass)), 4), len(xs), sum(m["win"] for m in xs)

def qhat_design(rows, lo, mass=MASS_DESIGN, mean=0.5, boundary=0.50):
    # design buckets by p_eff < 0.50; prior mean 0.5 per the literal (w+100)/(n+200)
    xs = [m for m in rows if (p_eff_from_cost(m["cost"]) < boundary) == lo]
    return round((sum(m["win"] for m in xs) + mass*mean) / (len(xs) + mass), 4), len(xs), sum(m["win"] for m in xs)

state = json.load(open(f"{DATA}/state_extract.json"))
ms = state["measure"]
imp = state["impulse_cfg"]
lm = [json.loads(l) for l in open(f"{BOTD}/loop_metrics.jsonl")]

out = {}

# ---------- A. replicate the three genuine nightlies ----------
real_nightlies = [l for l in lm if l["t"] % 86400 < 700 and l["t"] % 86400 >= 600]  # ~00:10 UTC
rep = []
for L in real_nightlies:
    tick = L["t"]
    # settled-by-tick: interval resolves at t0+300; allow a settlement lag window [0, 120s]
    for lag in (0, 120):
        avail = [m for m in ms if m["t0"] + 300 <= tick - lag and m["win"] is not None and m["t0"] < tick]
        qlo, nlo, wlo = qhat_code(avail, True)
        qhi, nhi, whi = qhat_code(avail, False)
        if (qlo, qhi) == (L["qlo"], L["qhi"]):
            rep.append(dict(tick=utc(tick), logged=(L["qlo"], L["qhi"]), replicated=(qlo, qhi),
                            settled_used=len(avail), logged_settled=L["settled"],
                            lag_needed_s=lag, match=True,
                            buckets=dict(lo=(nlo, wlo), hi=(nhi, whi))))
            break
    else:
        rep.append(dict(tick=utc(tick), logged=(L["qlo"], L["qhi"]), replicated=(qlo, qhi),
                        settled_used=len(avail), logged_settled=L["settled"], match=False))
out["A_nightly_replication"] = rep
out["A_state_matches_last_nightly"] = (imp["qlo"], imp["qhi"]) == (real_nightlies[-1]["qlo"], real_nightlies[-1]["qhi"])

# ---------- B/C. deviations vs registered formula ----------
settled_all = [m for m in ms if m["win"] is not None]
n_all = len(settled_all)
# bucket membership disagreement band: p_eff<0.50 but cost>=0.50  <=> cost in [0.50, 0.5175)
mis = [m for m in settled_all if p_eff_from_cost(m["cost"]) < 0.50 and m["cost"] >= 0.50]
out["B_boundary"] = dict(
    n_settled=n_all,
    code_boundary="cost<0.50 (== p_eff < %.4f)" % p_eff_from_cost(0.50),
    registered_boundary="p_eff<0.50 (== cost < 0.5175)",
    misbucketed_rows=len(mis),
    misbucketed_costs=[m["cost"] for m in mis],
    note="rows with p_eff in [%.4f, 0.50) land in HI bucket under code, LO under design" % p_eff_from_cost(0.50))

variants = {}
variants["code_asis_mass400_seedmean_costbucket"] = (qhat_code(settled_all, True), qhat_code(settled_all, False))
variants["fix_mass200_seedmean_costbucket"] = (qhat_code(settled_all, True, mass=200), qhat_code(settled_all, False, mass=200))
variants["design_literal_mass200_mean0.5_peffbucket"] = (qhat_design(settled_all, True), qhat_design(settled_all, False))
variants["design_mass200_seedmean_peffbucket"] = (
    (round((sum(m["win"] for m in settled_all if p_eff_from_cost(m["cost"]) < 0.50) + 200*SEED_LO) /
           (sum(1 for m in settled_all if p_eff_from_cost(m["cost"]) < 0.50) + 200), 4),),
    (round((sum(m["win"] for m in settled_all if p_eff_from_cost(m["cost"]) >= 0.50) + 200*SEED_HI) /
           (sum(1 for m in settled_all if p_eff_from_cost(m["cost"]) >= 0.50) + 200), 4),))
out["C_formula_variants_on_all_settled"] = variants

# learning-speed: |qhat - seed| under mass 400 vs 200, same data/bucketing
q400 = qhat_code(settled_all, True)[0]; q200 = qhat_code(settled_all, True, mass=200)[0]
out["C_learning_speed"] = dict(
    qlo_mass400=q400, qlo_mass200=q200,
    move_from_seed_mass400_c=round((q400-SEED_LO)*100, 3),
    move_from_seed_mass200_c=round((q200-SEED_LO)*100, 3),
    ratio=round((q200-SEED_LO)/(q400-SEED_LO), 2) if q400 != SEED_LO else None)

# does any deviation change a SIZING decision on the observed rows? f>0 iff cost < qhat_b
def sized_decisions(qlo, qhi, boundary_is_cost=True):
    dec = []
    for m in ms:
        c = m["cost"]
        if boundary_is_cost: qb = qlo if c < 0.50 else qhi
        else: qb = qlo if p_eff_from_cost(c) < 0.50 else qhi
        dec.append(c < qb)
    return dec
d_code = sized_decisions(*variants["code_asis_mass400_seedmean_costbucket"][0][:1] + variants["code_asis_mass400_seedmean_costbucket"][1][:1])
# simpler: use scalar qhats
qc = (variants["code_asis_mass400_seedmean_costbucket"][0][0], variants["code_asis_mass400_seedmean_costbucket"][1][0])
qf = (variants["fix_mass200_seedmean_costbucket"][0][0], variants["fix_mass200_seedmean_costbucket"][1][0])
qd = (variants["design_literal_mass200_mean0.5_peffbucket"][0][0], variants["design_literal_mass200_mean0.5_peffbucket"][1][0])
dc = sized_decisions(qc[0], qc[1], True)
df = sized_decisions(qf[0], qf[1], True)
dd = sized_decisions(qd[0], qd[1], False)
out["C_sizing_decision_flips"] = dict(
    n_rows=len(ms),
    code_vs_mass200fix=sum(1 for a, b in zip(dc, df) if a != b),
    code_vs_design_literal=sum(1 for a, b in zip(dc, dd) if a != b),
    flipped_costs_vs_design=[m["cost"] for m, a, b in zip(ms, dc, dd) if a != b])

# ---------- D. M2 guard-seeding counterfactual ----------
tr = json.load(open(f"{DATA}/trades_unified.json"))
launch = 1783695941
fam = [t for t in tr if t["eng"] in ("reversal", "reversal2") and t["at"]/1000 < launch
       and t.get("result") in ("win", "loss") and t["entry"] <= 0.531]
fam.sort(key=lambda t: t["at"])
def netps(rows):
    # net per share under frozen cost model semantics: win -> 1-cost, loss -> -cost
    tot = n = 0
    for t in rows:
        c = t["entry"] + FEE*t["entry"]*(1-t["entry"])
        tot += (1-c) if t["result"] == "win" else -c
        n += 1
    return (tot/n if n else None), n
seed_net, seed_n = netps(fam)
out["D_seed_ledger"] = dict(n=seed_n, design_says_n=123,
                            span=(utc(fam[0]["at"]/1000), utc(fam[-1]["at"]/1000)) if fam else None,
                            netps_c=round(seed_net*100, 2) if seed_net is not None else None)
# would guards have fired at each real nightly with seeds counting toward minimums and aging out?
guard_ct = []
for L in real_nightlies:
    tick = L["t"]
    live = [dict(t0=m["t0"], win=m["win"], cost=m["cost"]) for m in ms
            if m["win"] is not None and m["t0"] + 300 <= tick and m["t0"] < tick]
    seedr = [dict(t0=int(t["at"]/1000), win=1 if t["result"] == "win" else 0,
                  cost=t["entry"] + FEE*t["entry"]*(1-t["entry"])) for t in fam]
    pool = seedr + live
    def w(days, nmin):
        xs = [r for r in pool if r["t0"] >= tick - days*86400]
        if len(xs) < nmin: return None, len(xs)
        return sum((1-r["cost"]) if r["win"] else -r["cost"] for r in xs)/len(xs), len(xs)
    n15, c15 = w(15, 250); n7, c7 = w(7, 120); n10, c10 = w(10, 100)
    bench = (n15 is not None and n15 < -0.03) or (n7 is not None and n7 < -0.04)
    hairc = (n7 is not None and n7 < -0.02)   # registered single haircut trigger (SC3)
    hairc_code = (n15 is not None and n15 < -0.01) or (n7 is not None and n7 < -0.02)
    guard_ct.append(dict(tick=utc(tick), n7=(round(n7*100, 2) if n7 is not None else None, c7),
                         n15=(round(n15*100, 2) if n15 is not None else None, c15),
                         would_bench=bench, would_haircut_registered=hairc,
                         would_haircut_codeformula=hairc_code))
out["D_seeded_guard_counterfactual"] = guard_ct
# and at launch itself (day 0):
tick = launch
pool = [dict(t0=int(t["at"]/1000), win=1 if t["result"] == "win" else 0,
             cost=t["entry"] + FEE*t["entry"]*(1-t["entry"])) for t in fam]
xs7 = [r for r in pool if r["t0"] >= tick - 7*86400]
n7 = sum((1-r["cost"]) if r["win"] else -r["cost"] for r in xs7)/len(xs7) if len(xs7) >= 120 else None
out["D_at_launch"] = dict(n7_c=(round(n7*100, 2) if n7 is not None else None), n7_count=len(xs7),
                          would_haircut=(n7 is not None and n7 < -0.02),
                          would_bench=(n7 is not None and n7 < -0.04))

# ---------- E. bench counterfactual ----------
out["E_bench"] = dict(benched_now=imp["benched"],
                      benched_at_real_nightlies=[l["benched"] for l in real_nightlies],
                      note="benched never true at any genuine v3 nightly; direct bench cost in live era = $0")

# ---------- F. restart flapping ----------
stale = [l for l in lm if l not in real_nightlies and l["measured"] == 300]
fresh_reset = [l for l in lm if l not in real_nightlies and l["measured"] == 0]
out["F_flapping"] = dict(
    total_lm_lines=len(lm), genuine_nightlies=len(real_nightlies),
    stale_prelaunch_nightly_runs=len(stale),
    distinct_stale_timestamps=len({l["t"] for l in stale}),
    stale_span=(utc(min(l["t"] for l in stale)), utc(max(l["t"] for l in stale))),
    stale_qlo=sorted({l["qlo"] for l in stale}),
    reset_line_then_stale_again=bool(fresh_reset and any(l["t"] > fresh_reset[0]["t"] for l in stale)),
    note="stale lines show pre-launch measure book (300 rows, qlo .4175, benched) re-run after the 15:05 reset line -> state flapped across restarts")

# ---------- Stress tests ----------
random.seed(8)
def day_of(m): return m["t0"] // 86400
days = sorted({day_of(m) for m in settled_all})
by_day = {d: [m for m in settled_all if day_of(m) == d] for d in days}

def gap(rows):
    """code qlo minus design-literal qlo, in cents (the deviation's headline contrast)"""
    if not rows: return None
    a = qhat_code(rows, True)[0]; b = qhat_design(rows, True)[0]
    return (a - b) * 100

stress = {}
# 1) drop the single best day (day contributing most wins)
best = max(days, key=lambda d: sum(m["win"] for m in by_day[d]))
sub = [m for m in settled_all if day_of(m) != best]
stress["drop_best_day"] = dict(dropped_day=str(datetime.date.fromtimestamp(best*86400)),
    code=(qhat_code(sub, True)[0], qhat_code(sub, False)[0]),
    design=(qhat_design(sub, True)[0], qhat_design(sub, False)[0]),
    gap_c=round(gap(sub), 3), sign_survives=gap(sub) > 0)
# 2) halve the sample (first/second half chronological)
h = len(settled_all)//2
for name, sub in (("first_half", settled_all[:h]), ("second_half", settled_all[h:])):
    stress[name] = dict(code=(qhat_code(sub, True)[0], qhat_code(sub, False)[0]),
                        design=(qhat_design(sub, True)[0], qhat_design(sub, False)[0]),
                        gap_c=round(gap(sub), 3), sign_survives=gap(sub) > 0)
# 3) jitter bucket boundary +/-1c
for b in (0.49, 0.50, 0.51):
    xs_lo = [m for m in settled_all if m["cost"] < b]
    q = round((sum(m["win"] for m in xs_lo) + 400*SEED_LO)/(len(xs_lo)+400), 4)
    stress.setdefault("boundary_jitter", {})[f"cost<{b}"] = {
        "n_lo": len(xs_lo), "qlo": q, "membership_changes_vs_0.50": None}
for b in (0.49, 0.51):
    ch = sum(1 for m in settled_all if (m["cost"] < b) != (m["cost"] < 0.50))
    stress["boundary_jitter"][f"cost<{b}"]["membership_changes_vs_0.50"] = ch
# 4) day-block bootstrap of the code-vs-design qlo gap (deterministic deviation, so this
#    measures data-dependence of the CONTRAST, n_days blocks)
gaps = []
for _ in range(4000):
    samp = []
    for _ in days: samp += by_day[random.choice(days)]
    gaps.append(gap(samp))
gaps.sort()
stress["bootstrap_gap_qlo_c"] = dict(n_days=len(days), B=4000,
    mean=round(sum(gaps)/len(gaps), 3),
    ci95=(round(gaps[int(0.025*len(gaps))], 3), round(gaps[int(0.975*len(gaps))], 3)),
    frac_positive=round(sum(1 for g in gaps if g > 0)/len(gaps), 3))
out["stress"] = stress

json.dump(out, open("/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work/verify/R8-repro/results.json", "w"), indent=1)
print(json.dumps(out, indent=1))
