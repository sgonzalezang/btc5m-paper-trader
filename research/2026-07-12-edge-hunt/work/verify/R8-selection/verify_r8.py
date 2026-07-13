#!/usr/bin/env python3
"""Adversarial verification of R8 (spec-deviation audit) — multiplicity/selection lens.

R8 is a deterministic code-vs-design audit, so classical multiplicity correction is
inapplicable; instead we (a) independently re-derive every numeric claim from raw
state, (b) check the design text says what R8 claims it says, (c) test the
alternative explanation for the 'restart flapping' sub-claim (self-test fixture vs
stale live state), and (d) assess the merge-agent question about mid-experiment
prior-mass changes vs the pre-registered Phase-0/1/2 verdict inputs.
Stdlib only.
"""
import json, math

ROOT = "/Users/sgonzalez/btc5m-paper-trader"
state = json.load(open(f"{ROOT}/research/2026-07-12-edge-hunt/data/state_extract.json"))
out = {}

IMP_SEED_LO, IMP_SEED_HI, IMP_PRIOR = 0.5057, 0.5068, 400  # bot line 155
NIGHTLY = 1783901401   # Jul 13 00:10:01 UTC, last real nightly per loop_metrics.jsonl
FEE = 0.07

def p_eff_from_cost(c):
    # invert c = p + 0.07 p (1-p)  =>  -0.07 p^2 + 1.07 p - c = 0
    return (1.07 - math.sqrt(1.07**2 - 4*0.07*c)) / (2*0.07)

meas = state["measure"]
out["n_measure_total"] = len(meas)

# ---- 1. Replicate bot nightly (code formula: cost<0.50 buckets, prior 400 at ledger seeds)
def bot_qhat(rows, bucket_lo):
    xs = [m for m in rows if (m["cost"] < 0.50) == bucket_lo]
    seed = IMP_SEED_LO if bucket_lo else IMP_SEED_HI
    w = sum(m["win"] for m in xs)
    return len(xs), w, round(min(0.56, (w + IMP_PRIOR*seed) / (len(xs) + IMP_PRIOR)), 4)

# records SETTLEABLE at the Jul 13 00:10:01 nightly: interval must have closed
# (t0 <= NIGHTLY-300; the t0=00:10:00 record had only just opened). One boundary
# record t0=1783901100 (00:05, closes 00:10:00) had a lagged PM resolution.
strict = [m for m in meas if m["t0"] <= NIGHTLY - 300 and m["win"] is not None]
no_lag = [m for m in strict if m["t0"] != 1783901100]

nl, wl, ql = bot_qhat(no_lag, True);  nh, wh, qh = bot_qhat(no_lag, False)
out["replication_bot_formula_excl_lagged"] = dict(n_lo=nl, w_lo=wl, qlo=ql, n_hi=nh, w_hi=wh, qhi=qh)
nl2, wl2, ql2 = bot_qhat(strict, True); nh2, wh2, qh2 = bot_qhat(strict, False)
out["replication_bot_formula_strict_cutoff"] = dict(n_lo=nl2, w_lo=wl2, qlo=ql2, n_hi=nh2, w_hi=wh2, qhi=qh2)
out["state_values"] = dict(qlo=state["impulse_cfg"].get("qlo") if "impulse_cfg" in state and isinstance(state["impulse_cfg"], dict) else None)
# state qlo/qhi live in impulse_cfg or lifetime; pull whatever exists
imp_cfg = state.get("impulse_cfg") or {}
out["state_values"] = {k: imp_cfg.get(k) for k in ("qlo", "qhi", "benched", "haircut", "bank")}
out["replication_match"] = dict(
    qlo_match=(ql == imp_cfg.get("qlo")),
    qhi_match_excl_lagged=(qh == imp_cfg.get("qhi")),
    note="R8 claimed qlo exact, qhi exact modulo one lagged-settlement record")

# ---- 2. Design formula (registered §4.2: p_eff<0.50 buckets, (w+100)/(n+200)) on same data
def design_qhat(rows, bucket_lo):
    xs = [m for m in rows if (p_eff_from_cost(m["cost"]) < 0.50) == bucket_lo]
    w = sum(m["win"] for m in xs)
    return len(xs), w, round(min(0.56, (w + 100) / (len(xs) + 200)), 4)

all_settled = [m for m in meas if m["win"] is not None]
dl = design_qhat(all_settled, True); dh = design_qhat(all_settled, False)
out["design_formula_all_settled"] = dict(n_lo=dl[0], w_lo=dl[1], qlo=dl[2], n_hi=dh[0], w_hi=dh[1], qhi=dh[2],
                                         claimed_by_R8=dict(qlo=0.4954, qhi=0.4932))

# ---- 3. Bucket-boundary geometry: cost<0.50 in p_eff terms
out["boundary"] = dict(
    code_boundary_cost=0.50,
    equals_p_eff=round(p_eff_from_cost(0.50), 4),
    registered_boundary_p_eff=0.50,
    misassigned_band="p_eff in [%.4f, 0.50) goes to HI bucket in code, LO in design" % p_eff_from_cost(0.50))
mis = [m for m in all_settled if p_eff_from_cost(m["cost"]) < 0.50 and m["cost"] >= 0.50]
out["boundary"]["settled_records_misbucketed"] = len(mis)
out["boundary"]["of_total_settled"] = len(all_settled)

# sizing threshold under each: code sizes iff cost < q(bucket-by-cost)
qlo_s, qhi_s = imp_cfg.get("qlo"), imp_cfg.get("qhi")
if qlo_s and qhi_s:
    # code: sized iff (cost<0.50 and cost<qlo) or (cost>=0.50 and cost<qhi) = cost < max(0.50-eps... )
    code_thresh = qhi_s if qhi_s > 0.50 else 0.50  # cost < 0.50 always < qlo(>0.5); sliver [0.50,qhi)
    design_thresh = qlo_s  # design: p_eff<0.50 fills compared to qlo => sized iff cost<qlo
    out["sizing_threshold"] = dict(
        code_sized_iff_cost_lt=round(code_thresh, 4), code_p_eff=round(p_eff_from_cost(code_thresh), 4),
        design_bucketing_same_qhats_iff_cost_lt=round(design_thresh, 4),
        design_p_eff=round(p_eff_from_cost(design_thresh), 4))

# ---- 4. 'Restart flapping' sub-claim: decode loop_metrics 0.4175 lines
lm = [json.loads(l) for l in open(f"{ROOT}/bot/loop_metrics.jsonl")]
test_fixture_qlo = round((90 + IMP_PRIOR*IMP_SEED_LO) / (300 + IMP_PRIOR), 4)
test_fixture_n15 = round((90*(1-0.4975) + 210*(-0.4975)) / 300, 4)
weird = [r for r in lm if r.get("measured") == 300]
out["restart_flapping"] = dict(
    selftest_fixture_prediction=dict(qlo=test_fixture_qlo, n15=test_fixture_n15,
                                     measured=300, benched=True, haircut=True),
    observed_anomalous_lines=len(weird),
    all_match_fixture=all(r["qlo"] == test_fixture_qlo and r["n15"] == test_fixture_n15
                          and r["benched"] and r["haircut"] for r in weird),
    prelaunch_ledger_n=123,
    live_state_ever_benched_in_real_nightlies=any(
        r["benched"] for r in lm if r.get("measured") != 300),
    verdict=("The qlo=0.4175/n15=-0.1975/measured=300 lines are EXACTLY the --selftest "
             "dead-regime fixture (bot line 1587: 300 rows, cost .4975, 30% win) run on a "
             "throwaway Bot object; they polluted loop_metrics.jsonl but never touched live "
             "state. The pre-launch ledger was n=123, not 300. R8's 'restarts re-ran the "
             "nightly on stale pre-launch state 5 times' misattributes the mechanism; live "
             "benched flag never flapped."))

# ---- 5. Merge-agent question: does fixing prior mass mid-run corrupt day-14/60 verdicts?
out["mid_experiment_fix_assessment"] = dict(
    day14_kill_input="measurement-book net/share mean (raw), design 7 Phase 1 - qhat-free",
    day60_phase2_input="measurement-book net EV/share + block-boot CI (raw) - qhat-free",
    day60_gate_verdict_input="paired flagship vs reversal_v2 delta on common signals - qhat-free",
    day60_cap_verdict_input=("§4.2 bucket q's = raw (n,wins) per bucket; shrinkage prior not part "
                             "of the verdict statistic; cost stored per record so registered p_eff "
                             "bucketing is recomputable retroactively"),
    phase0_status="only %d measurement records vs >=100 required; Phase 0 not closed, clock not started" % len(meas),
    phase0_rule="'Any conformance miss = code bug; fix before the clock starts' (§7 Phase 0)",
    conclusion=("Fixing IMP_PRIOR 400->200 (and the boundary) now is what the pre-registered "
                "protocol itself prescribes: all Phase verdicts read the raw measurement book, "
                "not the shrunk qhat, and Phase 0 has not closed. Leaving the deviation is the "
                "worse option; it is also NOT 'documented' - the code comment (line 152) "
                "falsely claims FINAL-DESIGN MF2/MF3 conformance."))

# ---- 6. Extra deviations found during verification (completeness check on 'three ways')
out["additional_deviations_found"] = [
    "haircut trigger (line 647) includes 15d<-1c, resurrecting the tier §5.2 explicitly deleted",
    "haircut has no release hysteresis (design: releases at 7d>=-1c; code releases at 7d>=-2c)",
    "design nightly formula shrinks to prior MEAN 0.5 with mass 200; code shrinks to the ledger "
    "seed (.5057/.5068) with mass 400 - two distinct differences, R8 named only the mass",
]

json.dump(out, open(f"{ROOT}/research/2026-07-12-edge-hunt/work/verify/R8-selection/results.json", "w"), indent=1)
print(json.dumps(out, indent=1))
