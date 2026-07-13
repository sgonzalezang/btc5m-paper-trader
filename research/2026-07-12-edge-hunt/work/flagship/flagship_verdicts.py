#!/usr/bin/env python3
"""
FLAGSHIP LIVE VERDICT — pre-registered paired comparisons, live data Jul 10-13.
Evaluates (per FINAL-DESIGN.md section 7 and the 2026-07-12 edge-hunt brief):
  1. SIZING verdict: impulse_v2 (quarter-Kelly) vs impulse50 (flat $50 twin)
  2. GATE verdict:   gated arms vs reversal_v2 (ungated control)
  3. CAP verdict:    reversal (55c) vs reversal_v2 (53c)
  4. Measurement book autopsy (36 records) + qhat/bench status
  5. Posterior combine with the prior TEST estimate (+1.6c/share, SE 1.9c)

Frozen cost model: EV/share = q - p - 0.07*p*(1-p); p = fill = ask + 1c slip.
Stdlib only. Outputs results.json in this dir.
"""
import json, math, random, collections, datetime

DATA = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data"
OUT  = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work/flagship/results.json"
random.seed(20260712)

def load(fn):
    with open(f"{DATA}/{fn}") as f: return json.load(f)

trades = load("trades_unified.json")
state  = load("state_extract.json")

def cost_of(p): return p + 0.07*p*(1-p)          # total cost per share incl fee
def qstar(p):   return p + 0.07*p*(1-p)          # break-even win prob

def iso(t0): return datetime.datetime.utcfromtimestamp(t0).strftime("%m-%d %H:%M")

# per-share net pnl from the frozen model (win pays 1)
def ps(tr):
    p = tr["entry"]
    return (1 - cost_of(p)) if tr["result"] == "win" else -cost_of(p)

# sanity: ledger pnl vs frozen model
def pnl_check(sub):
    diffs = []
    for t in sub:
        model = ps(t) * t["shares"] - 0.004
        diffs.append(abs(model - t["pnl"]))
    return max(diffs) if diffs else None

# ---------- stats helpers (stdlib) ----------
def binom_pmf(k, n, p):
    return math.comb(n, k) * p**k * (1-p)**(n-k)
def binom_cdf(k, n, p):
    return sum(binom_pmf(i, n, p) for i in range(0, k+1))
def binom_test_le(k, n, p):
    "P(X <= k | p) one-sided lower tail"
    return binom_cdf(k, n, p)
def binom_test_ge(k, n, p):
    return 1 - binom_cdf(k-1, n, p) if k > 0 else 1.0
def clopper_pearson(k, n, alpha=0.10):
    "exact CI via bisection on binomial tails"
    if n == 0: return (0.0, 1.0)
    def solve(f, lo, hi):
        for _ in range(200):
            mid = (lo+hi)/2
            if f(mid): lo = mid
            else: hi = mid
        return (lo+hi)/2
    lo = 0.0 if k == 0 else solve(lambda p: 1-binom_cdf(k-1, n, p) < alpha/2, 0, k/n)
    hi = 1.0 if k == n else solve(lambda p: binom_cdf(k, n, p) >= alpha/2, k/n, 1)
    return (lo, hi)
def mean(xs): return sum(xs)/len(xs) if xs else float("nan")
def sd(xs):
    if len(xs) < 2: return float("nan")
    m = mean(xs); return math.sqrt(sum((x-m)**2 for x in xs)/(len(xs)-1))
def se(xs): return sd(xs)/math.sqrt(len(xs)) if len(xs) > 1 else float("nan")

def block_boot_ci(pairs, B=10000, alpha=0.10, blocksec=3600):
    """pairs = [(t0, value)]; resample 1h blocks with replacement; CI on the mean."""
    blocks = collections.defaultdict(list)
    for t0, v in pairs: blocks[t0 // blocksec].append(v)
    keys = list(blocks.keys())
    if not keys: return (float("nan"),)*3
    means = []
    for _ in range(B):
        samp = [random.choice(keys) for _ in keys]
        vals = [v for k in samp for v in blocks[k]]
        means.append(mean(vals))
    means.sort()
    lo = means[int(alpha/2*B)]; hi = means[int((1-alpha/2)*B)-1]
    return (mean([v for _, v in pairs]), lo, hi)

def perm_test_diff(a, b, B=20000):
    """two-sided permutation test on difference of means"""
    obs = mean(a) - mean(b)
    pool = a + b; na = len(a); cnt = 0
    for _ in range(B):
        random.shuffle(pool)
        d = mean(pool[:na]) - mean(pool[na:])
        if abs(d) >= abs(obs) - 1e-12: cnt += 1
    return obs, (cnt+1)/(B+1)

R = {"generated": datetime.datetime.utcnow().isoformat()+"Z",
     "cost_model": "EV/share = q - p - 0.07*p*(1-p); fill = ask+1c; gas $0.004"}

# ---------- ledgers ----------
def eng(e, settled=True):
    return sorted([t for t in trades if t["eng"] == e and (t["status"] == "settled" if settled else True)],
                  key=lambda t: t["t0"])

iv2, i50, rv2, rv55 = eng("impulse_v2"), eng("impulse50"), eng("reversal_v2"), eng("reversal")
R["ledger_check_max_pnl_diff"] = {e: pnl_check(x) for e, x in
    [("impulse_v2", iv2), ("impulse50", i50), ("reversal_v2", rv2), ("reversal", rv55)]}

bt = {e: {t["t0"]: t for t in x} for e, x in
      [("impulse_v2", iv2), ("impulse50", i50), ("reversal_v2", rv2), ("reversal", rv55)]}

# =====================================================================
# 1. SIZING VERDICT: impulse_v2 vs impulse50
# =====================================================================
t_start = max(min(t["t0"] for t in iv2), min(t["t0"] for t in i50))  # common live period
iv2c = [t for t in iv2 if t["t0"] >= t_start]
i50c = [t for t in i50 if t["t0"] >= t_start]
common = sorted(set(bt["impulse_v2"]) & set(bt["impulse50"]))
common = [t0 for t0 in common if t0 >= t_start]
skip_t0 = sorted(t0 for t0 in bt["impulse50"] if t0 >= t_start and t0 not in bt["impulse_v2"]
                 and bt["impulse50"][t0]["status"] == "settled")
only_v2 = sorted(t0 for t0 in bt["impulse_v2"] if t0 >= t_start and t0 not in bt["impulse50"])

# paired per-share delta on common signals (entries can differ: v2 re-polls for cheap fills)
paired = []
for t0 in common:
    a, b = bt["impulse_v2"][t0], bt["impulse50"][t0]
    if a["status"] == "settled" and b["status"] == "settled":
        paired.append((t0, a, b))
d_ps    = [(t0, ps(a) - ps(b)) for t0, a, b in paired]
d_entry = [a["entry"] - b["entry"] for _, a, b in paired]
same_result = sum(1 for _, a, b in paired if a["result"] == b["result"])

skips = [bt["impulse50"][t0] for t0 in skip_t0]
skip_wins = sum(1 for t in skips if t["result"] == "win")
skip_ps = [(t["t0"], ps(t)) for t in skips]
skip_mix = mean([t["entry"] for t in skips]) if skips else float("nan")

# decomposition of the live pnl gap
pnl_v2 = sum(t["pnl"] for t in iv2c); pnl_50 = sum(t["pnl"] for t in i50c)
gap = pnl_v2 - pnl_50
skip_contrib = -sum(t["pnl"] for t in skips)                 # $ impulse50 lost on signals v2 never took
price_contrib = sum((ps(a) - ps(b)) * b["shares"] for _, a, b in paired)  # cheaper fills at impulse50's share count
stake_contrib = gap - skip_contrib - price_contrib           # residual = variable-stake effect (+only_v2 trades)

m_common, lo_c, hi_c = block_boot_ci(d_ps)
m_skip, lo_s, hi_s = block_boot_ci(skip_ps) if skip_ps else (float("nan"),)*3

R["sizing_verdict"] = {
 "period": [iso(t_start), iso(max(t["t0"] for t in i50c))],
 "impulse_v2": {"n": len(iv2c), "wins": sum(1 for t in iv2c if t["result"]=="win"),
                "pnl": round(pnl_v2,2), "avg_entry": round(mean([t["entry"] for t in iv2c]),4),
                "avg_stake": round(mean([t["stake"] for t in iv2c]),2),
                "ps_mean_c": round(100*mean([ps(t) for t in iv2c]),2)},
 "impulse50": {"n": len(i50c), "wins": sum(1 for t in i50c if t["result"]=="win"),
               "pnl": round(pnl_50,2), "avg_entry": round(mean([t["entry"] for t in i50c]),4),
               "ps_mean_c": round(100*mean([ps(t) for t in i50c]),2)},
 "common_signals": {"n": len(paired), "same_result": same_result,
    "mean_entry_v2": round(mean([a["entry"] for _,a,_ in paired]),4),
    "mean_entry_50": round(mean([b["entry"] for _,_,b in paired]),4),
    "mean_entry_advantage_c": round(-100*mean(d_entry),2),
    "paired_delta_ps_c": {"mean": round(100*m_common,2), "ci90_blockboot": [round(100*lo_c,2), round(100*hi_c,2)]},
    "note": "entries differ on common signals because the Kelly f>0 rule makes v2 wait within the 45s window for a price below ~qhat-implied cost; impulse50 fills at first poll"},
 "kelly_skips": {"n": len(skips), "wins": skip_wins, "wr": round(skip_wins/len(skips),4) if skips else None,
    "avg_entry": round(skip_mix,4) if skips else None,
    "qstar_at_mix": round(qstar(skip_mix),4) if skips else None,
    "ps_mean_c": {"mean": round(100*m_skip,2), "ci90_blockboot": [round(100*lo_s,2), round(100*hi_s,2)]},
    "pnl_dollars": round(sum(t["pnl"] for t in skips),2),
    "binom_p_vs_qstar_two_sided_note": "exact binomial vs break-even at the skip mix",
    "binom_p_le": round(binom_test_le(skip_wins, len(skips), qstar(skip_mix)),4) if skips else None},
 "only_v2_t0s": only_v2,
 "gap_decomposition_dollars": {
    "total_gap_v2_minus_50": round(gap,2),
    "skip_avoidance": round(skip_contrib,2),
    "price_improvement_on_common": round(price_contrib,2),
    "stake_sizing_residual": round(stake_contrib,2)},
}

# =====================================================================
# 2. GATE VERDICT: gated (impulse50 flat control) vs reversal_v2 (ungated flat)
# =====================================================================
tg = max(min(t["t0"] for t in i50), min(t["t0"] for t in rv2))
rv2c = [t for t in rv2 if t["t0"] >= tg]
gated_t0 = set(bt["impulse50"]) | set(bt["impulse_v2"]) | {r["t0"] for r in state["measure"]}
gate_pass = [t for t in rv2c if t["t0"] in gated_t0]
gate_rej  = [t for t in rv2c if t["t0"] not in gated_t0]

gp_ps = [ps(t) for t in gate_pass]; gr_ps = [ps(t) for t in gate_rej]
gp_w = sum(1 for t in gate_pass if t["result"]=="win"); gr_w = sum(1 for t in gate_rej if t["result"]=="win")
obs_inc, p_perm = perm_test_diff(gp_ps, gr_ps) if gp_ps and gr_ps else (float("nan"), float("nan"))
m_gp, lo_gp, hi_gp = block_boot_ci([(t["t0"], ps(t)) for t in gate_pass]) if gate_pass else (float("nan"),)*3
m_gr, lo_gr, hi_gr = block_boot_ci([(t["t0"], ps(t)) for t in gate_rej]) if gate_rej else (float("nan"),)*3

# pre-registered form: paired flagship-vs-rv2 delta on common signal stream
# (flagship contribution 0 when it did not enter). Per-share basis on rv2's fills.
pre_reg_pairs = []
for t in rv2c:
    fv = bt["impulse_v2"].get(t["t0"])
    fps = ps(fv) if (fv and fv["status"]=="settled") else 0.0
    pre_reg_pairs.append((t["t0"], fps - ps(t)))
m_pr, lo_pr, hi_pr = block_boot_ci(pre_reg_pairs)

R["gate_verdict"] = {
 "period": [iso(tg), iso(max(t["t0"] for t in rv2c))],
 "construction": "reversal_v2 (ungated flat $50) split by whether the gate fired at that t0 (t0 in impulse50/impulse_v2/measure book). Same engine, same fills -> isolates the gate.",
 "gate_pass": {"n": len(gate_pass), "wins": gp_w, "wr": round(gp_w/len(gate_pass),4) if gate_pass else None,
    "avg_entry": round(mean([t["entry"] for t in gate_pass]),4) if gate_pass else None,
    "ps_mean_c": round(100*m_gp,2), "ci90": [round(100*lo_gp,2), round(100*hi_gp,2)]},
 "gate_rejected": {"n": len(gate_rej), "wins": gr_w, "wr": round(gr_w/len(gate_rej),4) if gate_rej else None,
    "avg_entry": round(mean([t["entry"] for t in gate_rej]),4) if gate_rej else None,
    "ps_mean_c": round(100*m_gr,2), "ci90": [round(100*lo_gr,2), round(100*hi_gr,2)]},
 "gate_increment_c": {"pass_minus_rejected": round(100*obs_inc,2), "perm_p_two_sided": round(p_perm,4),
                      "n_pass": len(gp_ps), "n_rej": len(gr_ps)},
 "pre_registered_paired_delta_c": {"mean": round(100*m_pr,2), "ci90_blockboot": [round(100*lo_pr,2), round(100*hi_pr,2)],
    "n_pairs": len(pre_reg_pairs),
    "note": "flagship ps (0 if not entered) minus reversal_v2 ps per common signal; includes sizing-policy effects, not gate alone"},
}

# =====================================================================
# 3. CAP VERDICT: reversal (55c cap, 120s window) vs reversal_v2 (53c, 45s)
# =====================================================================
tc = max(min(t["t0"] for t in rv55), min(t["t0"] for t in rv2))
rv55c = [t for t in rv55 if t["t0"] >= tc]
both  = [(bt["reversal"][t0], bt["reversal_v2"][t0]) for t0 in sorted(set(bt["reversal"]) & set(bt["reversal_v2"]))
         if t0 >= tc and bt["reversal"][t0]["status"]=="settled" and bt["reversal_v2"][t0]["status"]=="settled"]
only55 = [t for t in rv55c if t["t0"] not in bt["reversal_v2"]]
# why only55: cap (entry in 53-55c band) vs window (entrySec > 45) vs other
o55_cap    = [t for t in only55 if t["entry"] > 0.53 + 1e-9 and (t.get("entrySec") or 999) <= 45]
o55_window = [t for t in only55 if (t.get("entrySec") or 999) > 45]
o55_other  = [t for t in only55 if t not in o55_cap and t not in o55_window]

def subset_stats(sub, label):
    if not sub: return {"label": label, "n": 0}
    w = sum(1 for t in sub if t["result"]=="win"); mx = mean([t["entry"] for t in sub])
    m, lo, hi = block_boot_ci([(t["t0"], ps(t)) for t in sub])
    return {"label": label, "n": len(sub), "wins": w, "wr": round(w/len(sub),4),
            "avg_entry": round(mx,4), "qstar_at_mix": round(qstar(mx),4),
            "ps_mean_c": round(100*m,2), "ci90": [round(100*lo,2), round(100*hi,2)]}

# non-paired larger-n cap read on the whole reversal ledger (Jul 9-13)
r_all_cheap = [t for t in rv55 if t["entry"] <= 0.53 + 1e-9]
r_all_rich  = [t for t in rv55 if 0.53 + 1e-9 < t["entry"] <= 0.56 + 1e-9]
obs_cap, p_cap = perm_test_diff([ps(t) for t in r_all_rich], [ps(t) for t in r_all_cheap]) \
                 if r_all_rich and r_all_cheap else (float("nan"), float("nan"))

R["cap_verdict"] = {
 "period_overlap": [iso(tc), iso(max(t["t0"] for t in rv55c))],
 "confound_warning": "the live 55c arm is the OLD reversal spec (revWinMin=180 -> first 120s), not the pre-registered cap55_shadow (45s). Cap and window effects are entangled; subsets below separate them.",
 "n_reversal_overlap": len(rv55c), "n_common_both": len(both),
 "common_entry_diff_c": round(100*mean([a["entry"]-b["entry"] for a,b in both]),2) if both else None,
 "common_same_result": sum(1 for a,b in both if a["result"]==b["result"]) if both else None,
 "only55_split": {
    "cap_skipped_53_55_within45s": subset_stats(o55_cap, "53-55c entries inside 45s (pure cap effect)"),
    "late_window_45_120s": subset_stats(o55_window, "entered after 45s (window effect)"),
    "other": subset_stats(o55_other, "other (book/timing)")},
 "full_ledger_unpaired": {
    "entries_le53": subset_stats(r_all_cheap, "reversal ledger <=53c (n incl. pre-overlap)"),
    "entries_53_55": subset_stats(r_all_rich, "reversal ledger 53-55c"),
    "rich_minus_cheap_c": round(100*obs_cap,2), "perm_p": round(p_cap,4)},
}

# =====================================================================
# 4. MEASUREMENT BOOK AUTOPSY + qhat/bench status
# =====================================================================
meas = state["measure"]; icfg = state["impulse_cfg"]
# reclassify: first-poll-sized / rich-then-entered / never-entered
cls = []
for r in meas:
    t0 = r["t0"]; tr = bt["impulse_v2"].get(t0)
    if r["sized"]: k = "sized_first_poll"
    elif tr is not None: k = "rich_first_poll_entered_later"
    else: k = "never_entered"
    cls.append((k, r, tr))
groups = collections.defaultdict(list)
for k, r, tr in cls: groups[k].append((r, tr))

def meas_stats(items, use_trade_price):
    sett = [(r, tr) for r, tr in items if r["win"] is not None]
    if not sett: return {"n": len(items), "settled": 0}
    wins = sum(r["win"] for r, _ in sett)
    evs = []
    for r, tr in sett:
        c = cost_of(tr["entry"]) if (use_trade_price and tr and tr["status"]=="settled") else r["cost"]
        evs.append((r["t0"], r["win"] - c))
    m, lo, hi = block_boot_ci(evs)
    return {"n": len(items), "settled": len(sett), "wins": wins, "wr": round(wins/len(sett),4),
            "ev_ps_c": round(100*m,2), "ci90": [round(100*lo,2), round(100*hi,2)]}

# qhat trajectory check: bucketed shrinkage over measurement fills at MEASURE cost
lo_fills = [(r, None) for r in meas if r["win"] is not None and r["cost"] < cost_of(0.50) - 1e-9]
hi_fills = [(r, None) for r in meas if r["win"] is not None and r["cost"] >= cost_of(0.50) - 1e-9]
lo_w = sum(r["win"] for r, _ in lo_fills); hi_w = sum(r["win"] for r, _ in hi_fills)
q_lo_pred = (lo_w + 100) / (len(lo_fills) + 200); q_hi_pred = (hi_w + 100) / (len(hi_fills) + 200)

sett_all = [r for r in meas if r["win"] is not None]
net_all = [(r["t0"], r["win"] - r["cost"]) for r in sett_all]
m_all, lo_all, hi_all = block_boot_ci(net_all)

R["measurement_book"] = {
 "n": len(meas), "state_impulse_cfg": icfg,
 "bench_haircut_actual": {"benched": icfg["benched"], "haircut": icfg.get("haircut"),
   "note": "state says NOT benched, NO haircut. Guard minimums (>=120 signals 7d) unreachable at n=36; guards cannot fire yet."},
 "first_poll_semantics_bug": "measure.sized flags the FIRST fillable poll only; 12 of 21 f_nonpos records were entered later in-window at cheaper prices by impulse_v2. Availability/skip accounting in the nightly job undercounts sized intervals if it reads this flag naively.",
 "classes": {k: meas_stats(v, use_trade_price=(k != "never_entered")) for k, v in groups.items()},
 "never_entered_at_first_poll_cost": meas_stats(groups.get("never_entered", []), use_trade_price=False),
 "all_records_at_first_poll_cost": {"n_settled": len(sett_all), "wins": sum(r["win"] for r in sett_all),
    "wr": round(sum(r["win"] for r in sett_all)/len(sett_all),4),
    "net_ps_c": round(100*m_all,2), "ci90": [round(100*lo_all,2), round(100*hi_all,2)],
    "note": "counterfactual 'take every gated cap-compliant signal at first-poll price' book = phase-1 kill metric input"},
 "phase1_kill_check": {"rule": "day-14 kill if measurement net/share <= -2c (min 200 fills)",
    "current_net_ps_c": round(100*m_all,2), "n": len(sett_all),
    "verdict": "n far below the 200 minimum; kill not evaluable yet"},
 "qhat_check": {"state_qlo": icfg["qlo"], "state_qhi": icfg["qhi"],
    "recomputed_qlo": round(q_lo_pred,4), "recomputed_qhi": round(q_hi_pred,4),
    "lo_fills": [len(lo_fills), lo_w], "hi_fills": [len(hi_fills), hi_w],
    "note": "recomputed from the 36-record extract with seed prior (wins+100)/(n+200); state uses trailing-30d book which includes the same records + seeds"},
}

# =====================================================================
# 5. POSTERIOR COMBINE with prior TEST estimate
# =====================================================================
# prior: honest central +1.6c/share, SE 1.9c (verify-regime decomposition, FINAL-DESIGN 3.3)
prior_mu, prior_se = 1.6, 1.9
# live gated level at live fills: impulse50 book (flat, takes all gated signals)
live_ps = [(t["t0"], 100*ps(t)) for t in i50]
live_mu, live_lo, live_hi = block_boot_ci(live_ps)
live_se_val = (live_hi - live_lo) / (2*1.645)
post_var = 1/(1/prior_se**2 + 1/live_se_val**2)
post_mu = post_var*(prior_mu/prior_se**2 + live_mu/live_se_val**2)
# same for the flagship as operated (price-filtered fills)
fl_ps = [(t["t0"], 100*ps(t)) for t in iv2]
fl_mu, fl_lo, fl_hi = block_boot_ci(fl_ps)
fl_se_val = (fl_hi - fl_lo)/(2*1.645)
post_var_f = 1/(1/prior_se**2 + 1/fl_se_val**2)
post_mu_f = post_var_f*(prior_mu/prior_se**2 + fl_mu/fl_se_val**2)

R["posterior"] = {
 "prior_test_estimate_c": {"mu": prior_mu, "se": prior_se, "source": "FINAL-DESIGN 3.3 verify-regime decomposition"},
 "live_gated_flat_book_c": {"mu": round(live_mu,2), "se": round(live_se_val,2), "n": len(i50),
    "ci90": [round(live_lo,2), round(live_hi,2)], "book": "impulse50 (takes every gated signal at first fill)"},
 "posterior_gated_level_c": {"mu": round(post_mu,2), "se": round(math.sqrt(post_var),2),
    "note": "inverse-variance normal combine; assumes prior and live sample the same regime (they may not)"},
 "flagship_as_operated_c": {"mu": round(fl_mu,2), "se": round(fl_se_val,2), "n": len(iv2),
    "ci90": [round(fl_lo,2), round(fl_hi,2)],
    "posterior_mu": round(post_mu_f,2), "posterior_se": round(math.sqrt(post_var_f),2),
    "note": "the Kelly f>0 price filter makes the flagship's fill mix cheaper (41c) than anything the prior estimate modeled; combine is indicative only"},
}

R["multiplicity"] = ("Three pre-registered verdicts (sizing, gate, cap) + one pre-registered measurement metric. "
                     "Exploratory additions: gap decomposition (3 terms), cap subset split (3), unpaired cap read (1). "
                     "K approx 8 comparisons total in this module; none was selected post-hoc as a best-of.")

with open(OUT, "w") as f: json.dump(R, f, indent=1)
print(json.dumps(R, indent=1))
