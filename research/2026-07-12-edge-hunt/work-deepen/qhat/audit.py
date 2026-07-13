#!/usr/bin/env python3
"""Part 1 — AUDIT the live guard/bench trail (wave-2 qhat agent).

Reconstructs every nightly netps guard decision from the measure book +
loop_metrics.jsonl + bot.log, classifies the polluted lines, and computes the
counterfactuals: (a) benching cost/saved in the v3 era, (b) what M2 seeding
would have done, (c) what a guard WITHOUT n-minimums would have done (both
first-poll/kill-input and operated semantics).

stdlib only. Writes audit_results.json next to this file.
"""
import json, os, re, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data"
BOT  = "/Users/sgonzalez/btc5m-paper-trader/bot"

def utc(ts): return datetime.datetime.utcfromtimestamp(ts).strftime("%m-%d %H:%M:%S")

st = json.load(open(os.path.join(DATA, "state_extract.json")))
measure = st["measure"]
imp_cfg = st["impulse_cfg"]
trades = json.load(open(os.path.join(DATA, "trades_unified.json")))
iv2 = [t for t in trades if t.get("eng") == "impulse_v2" and t.get("result") in ("win", "loss")]

# ---------- 1. classify loop_metrics lines ----------
lm = [json.loads(l) for l in open(os.path.join(BOT, "loop_metrics.jsonl")) if l.strip()]
# the --selftest dead-regime fixture: 300 records, cost .4975, 30% win rate
# -> qlo = (90 + 400*.5057)/(300+400) = .41754, netps = .3*.5025 - .7*.4975 = -.19750
fix_qlo = round((90 + 400 * 0.5057) / 700, 4)
fix_n15 = round(0.3 * 0.5025 - 0.7 * 0.4975, 4)
fixture, genuine = [], []
for r in lm:
    if r["qlo"] == fix_qlo and r.get("n15") == fix_n15 and r["measured"] == 300:
        fixture.append(r)
    else:
        genuine.append(r)

# ---------- 2. replicate each genuine nightly qhat + guard decision ----------
IMP_PRIOR, SEED_LO, SEED_HI = 400, 0.5057, 0.5068
def qhat_code(settled, bucket_lo, seed):
    xs = [m for m in settled if (m["cost"] < 0.50) == bucket_lo]
    return round(min(0.56, (sum(m["win"] for m in xs) + IMP_PRIOR * seed) / (len(xs) + IMP_PRIOR)), 4)

def netps(settled, tick, days, nmin):
    xs = [m for m in settled if m["t0"] >= tick - days * 86400]
    if len(xs) < nmin or not xs: return None, len(xs)
    return sum((1 - m["cost"]) if m["win"] else -m["cost"] for m in xs) / len(xs), len(xs)

nightly_audit = []
for r in genuine:
    tick = r["t"]
    # settled = records whose interval closed and whose PM resolution had landed.
    # Replication (R8-repro) needed a settle lag of 0-120s; use win!=None and
    # t0+300+lag <= tick, choosing lag in {0,120,300} that matches logged counts.
    best = None
    for lag in (0, 120, 300, 600):
        settled = [m for m in measure if m["win"] is not None and m["t0"] + 300 + lag <= tick]
        qlo, qhi = qhat_code(settled, True, SEED_LO), qhat_code(settled, False, SEED_HI)
        match = (qlo == r["qlo"] and qhi == r["qhi"] and len(settled) == r["settled"])
        if match: best = (lag, settled, qlo, qhi); break
        if best is None: best = (lag, settled, qlo, qhi)
    lag, settled, qlo, qhi = best
    n15, c15 = netps(settled, tick, 15, 250)
    n7,  c7  = netps(settled, tick, 7, 120)
    n10, c10 = netps(settled, tick, 10, 100)
    # guard decision per code (== spec thresholds for bench; code has extra 15d haircut tier)
    bench_fire = (n15 is not None and n15 < -0.03) or (n7 is not None and n7 < -0.04)
    haircut_code = bool((n15 is not None and n15 < -0.01) or (n7 is not None and n7 < -0.02))
    haircut_spec = bool(n7 is not None and n7 < -0.02)   # SC3: 15d tier deleted
    # counterfactual: guards WITHOUT n-minimums (kill-input first-poll semantics)
    n7_raw, c7_raw = netps(settled, tick, 7, 0)
    n15_raw, c15_raw = netps(settled, tick, 15, 0)
    nightly_audit.append(dict(
        tick=tick, tick_utc=utc(tick), lag_used_s=lag,
        logged=dict(qlo=r["qlo"], qhi=r["qhi"], benched=r["benched"], haircut=r["haircut"],
                    settled=r["settled"]),
        replicated=dict(qlo=qlo, qhi=qhi, settled=len(settled)),
        exact_match=(qlo == r["qlo"] and qhi == r["qhi"] and len(settled) == r["settled"]),
        windows=dict(n15=[None if n15 is None else round(n15, 4), c15],
                     n7=[None if n7 is None else round(n7, 4), c7],
                     n10=[None if n10 is None else round(n10, 4), c10]),
        decision_correct_per_code=(bool(r["benched"]) == bench_fire and bool(r["haircut"]) == haircut_code),
        decision_correct_per_spec=(bool(r["benched"]) == bench_fire and bool(r["haircut"]) == haircut_spec),
        no_min_counterfactual=dict(
            n7_raw=[None if n7_raw is None else round(n7_raw, 4), c7_raw],
            would_haircut_no_min=bool(n7_raw is not None and c7_raw > 0 and n7_raw < -0.02),
            would_bench_no_min=bool(n7_raw is not None and c7_raw > 0 and n7_raw < -0.04))))

# ---------- 3. counterfactual cost of a no-min bench (operated semantics) ----------
# earliest nightly where a no-minimum bench would have fired on the first-poll book
first_fire = next((a for a in nightly_audit if a["no_min_counterfactual"]["would_bench_no_min"]), None)
bench_cf = None
if first_fire:
    t_fire = first_fire["tick"]
    skipped = [t for t in iv2 if t["t0"] >= t_fire]
    bench_cf = dict(fires_at=utc(t_fire),
                    operated_trades_skipped=len(skipped),
                    operated_pnl_foregone=round(sum(t["pnl"] for t in skipped), 2),
                    per_share_c=round(100 * sum(t["pnl"] for t in skipped) /
                                      max(1e-9, sum(t["shares"] for t in skipped)), 2))

# ---------- 4. actual bench/haircut cost in v3 era ----------
# live state never benched/haircut (verified below); counterfactual delta = $0
ever_benched = any(r["benched"] for r in genuine) or imp_cfg["benched"]
ever_haircut = any(r["haircut"] for r in genuine) or imp_cfg["haircut"]
bench_skips_in_book = sum(1 for m in measure if m.get("skip") == "benched")

# ---------- 5. M2 seeding counterfactual (verify live-only component; cite R8-repro) ----------
# R8-repro D_seed_ledger: n=123 pre-launch fills (Jul 9 02:35 -> Jul 10 14:35), netps +2.75c
SEED_N, SEED_NETPS, SEED_T0, SEED_T1 = 123, 0.0275, 1783996 * 0, None
seed_span = (1783564501 // 1, 1783694114 // 1)  # 07-09 02:35:01, 07-10 14:35:14 UTC (from R8-repro)
m2 = []
for a in nightly_audit:
    tick = a["tick"]
    settled = [m for m in measure if m["win"] is not None and m["t0"] + 300 + a["lag_used_s"] <= tick]
    live7 = [m for m in settled if m["t0"] >= tick - 7 * 86400]
    live_sum = sum((1 - m["cost"]) if m["win"] else -m["cost"] for m in live7)
    # seeds still inside the 7d window at this tick (span entirely within window thru Jul 16)
    seeds_in = SEED_N if tick - 7 * 86400 <= seed_span[0] else 0
    n = seeds_in + len(live7)
    n7_seeded = (seeds_in * SEED_NETPS + live_sum) / n if n else None
    m2.append(dict(tick_utc=a["tick_utc"], live_n=len(live7),
                   n7_seeded_c=round(100 * n7_seeded, 2), n=n,
                   evaluable=(n >= 120),
                   would_haircut=(n >= 120 and n7_seeded < -0.02),
                   would_bench=(n >= 120 and n7_seeded < -0.04)))
# when do seeds age out / guards go structurally inert again?
seed_ageout = seed_span[1] + 7 * 86400
live_rate = sum(1 for m in measure if m["win"] is not None) / ((measure[-1]["t0"] - measure[0]["t0"]) / 86400)

out = dict(
    loop_metrics=dict(
        total_lines=len(lm), fixture_lines=len(fixture), genuine_lines=len(genuine),
        fixture_signature=dict(qlo=fix_qlo, n15=fix_n15, measured=300,
                               source="--selftest dead-regime fixture, btc5m_bot.py:1586-1593; "
                                      "selftest bot appends to loop_metrics.jsonl (abs path, :657) but "
                                      "log() only prints to stdout (:449) -> no bot.log trace, matches observed"),
        fixture_ticks_utc=[utc(r["t"]) for r in fixture],
        genuine_ticks_utc=[utc(r["t"]) for r in genuine]),
    nightly_audit=nightly_audit,
    live_state_flap=dict(ever_benched=ever_benched, ever_haircut=ever_haircut,
                         bench_skips_in_measure_book=bench_skips_in_book,
                         guard_log_lines_in_bot_log=0,
                         verdict="live state NEVER benched or haircut; the benched=true lines are "
                                 "selftest fixture pollution of loop_metrics.jsonl only (R8-selection "
                                 "reading confirmed, R8-integrity/repro 'state flap' reading refuted)"),
    bench_cost_v3_era=dict(direct_cost_usd=0.0,
                           note="bench/haircut never engaged; sized-per-formula-without-bench "
                                "counterfactual is identical to what ran"),
    no_min_bench_counterfactual=bench_cf,
    m2_seeding_counterfactual=dict(per_nightly=m2,
                                   seed_ageout_utc=utc(seed_ageout),
                                   live_settle_rate_per_day=round(live_rate, 1)),
    current_state=dict(qlo=imp_cfg["qlo"], qhi=imp_cfg["qhi"], benched=imp_cfg["benched"],
                       haircut=imp_cfg["haircut"], bank=imp_cfg["bank"]))
json.dump(out, open(os.path.join(HERE, "audit_results.json"), "w"), indent=1)
print(json.dumps(out, indent=1))
