#!/usr/bin/env python3
"""(b) Adaptive allocation: Thompson sampling (Gaussian, full-information paper feedback)
and Hedge (exponential weights) over daily arm pnl series.

Arms (60d backtest, flat $50/trade, fixed fill p=0.51, fee 0.07*p*(1-p), gas 0.004):
  latentfire  = reversal signals gated eff<=0.48
  reversal    = all reversal signals (ungated)
  momentum    = mirror (buy SAME side as prior move) -- known-bad arm, included to test
                whether adaptivity avoids it without oracle knowledge
  cash        = 0/day
Benchmarks: 100% latentfire static, equal-weight static, oracle best static (hindsight).
Evaluated on full 60d and on TEST (last 1/3, allocator warm from TRAIN).
Also: same machinery on the REAL ledger daily pnl per engine (trades.json, ~4.5 days).
"""
import json, math, random, os
from collections import defaultdict

SCRATCH = "/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad"
W = os.path.join(SCRATCH, "work", "sizing")
D = os.path.join(SCRATCH, "data")
random.seed(3)

P_FILL = 0.51
COST = P_FILL + 0.07 * P_FILL * (1 - P_FILL)
STAKE = 50.0
GAS = 0.004
WIN_PNL = STAKE / COST - STAKE   # $44.79 at p=0.51

stream = json.load(open(os.path.join(W, "stream.json")))
split_t = json.load(open(os.path.join(W, "stream_stats.json")))["split_t"]

def daily(rows, win_key):
    d = defaultdict(float)
    for s in rows:
        day = s["t0"] // 86400
        pnl = (WIN_PNL if s[win_key] else -STAKE) - GAS
        d[day] += pnl
    return d

gated = [s for s in stream if s["eff"] <= 0.48]
allsig = stream
mom = [dict(s, win=1 - s["win"]) for s in stream]   # mirror side

days = sorted({s["t0"] // 86400 for s in stream})
arms = {}
arms["latentfire"] = daily(gated, "win")
arms["reversal"] = daily(allsig, "win")
arms["momentum"] = daily(mom, "win")
arms["cash"] = {}
NAMES = list(arms)
M = [[arms[a].get(day, 0.0) for a in NAMES] for day in days]  # day x arm
test_start_idx = next(i for i, day in enumerate(days) if day * 86400 >= split_t)
print("days:", len(days), "test days:", len(days) - test_start_idx)
print("arm totals full:", {a: round(sum(arms[a].get(d, 0) for d in days)) for a in NAMES})
print("arm totals TEST:", {a: round(sum(arms[a].get(d, 0) for d in days[test_start_idx:])) for a in NAMES})

def run_hedge(M, eta):
    K = len(M[0]); w = [1.0] * K
    pnl_seq, weights_seq = [], []
    scale = max(1.0, max(abs(x) for row in M for x in row))
    for row in M:
        tot = sum(w); ws = [x / tot for x in w]
        weights_seq.append(ws)
        pnl_seq.append(sum(ws[i] * row[i] for i in range(K)))
        for i in range(K):
            w[i] *= math.exp(eta * row[i] / scale)
    return pnl_seq, weights_seq

def run_thompson(M, reps=400):
    K = len(M[0])
    agg_pnl = [0.0] * len(M)
    agg_sw = 0.0
    for _ in range(reps):
        mean = [0.0] * K; n = [0] * K; m2 = [0.0] * K
        prior_var = 200.0 ** 2
        last = -1; sw = 0
        for t, row in enumerate(M):
            samp = []
            for i in range(K):
                var = (m2[i] / n[i] if n[i] > 1 else 150.0 ** 2)
                post_var = 1.0 / (1.0 / prior_var + n[i] / max(var, 1e-9)) if n[i] else prior_var
                post_mean = post_var * (n[i] * mean[i] / max(var, 1e-9)) if n[i] else 0.0
                samp.append(random.gauss(post_mean, math.sqrt(post_var)))
            pick = max(range(K), key=lambda i: samp[i])
            if pick != last and last >= 0: sw += 1
            last = pick
            agg_pnl[t] += row[pick] / reps
            for i in range(K):   # full-information paper feedback
                n[i] += 1
                dlt = row[i] - mean[i]; mean[i] += dlt / n[i]
                m2[i] += dlt * (row[i] - mean[i])
        agg_sw += sw / reps
    return agg_pnl, agg_sw

def summarize(name, pnl_seq, extra=""):
    full = sum(pnl_seq); test = sum(pnl_seq[test_start_idx:])
    print(f" {name:22s} full={full:9.0f}  TEST={test:9.0f} {extra}")
    return {"full": full, "test": test}

res = {}
print("\n-- 60d backtest arms --")
for a in NAMES:
    seq = [arms[a].get(d, 0.0) for d in days]
    res[f"static_{a}"] = summarize(f"static 100% {a}", seq)
eq = [sum(row) / len(row) for row in M]
res["static_equal"] = summarize("static equal-weight", eq)

T = len(M)
eta = math.sqrt(8 * math.log(len(NAMES)) / T)
for e_mult, tag in ((1.0, "eta*1"), (3.0, "eta*3"), (0.3, "eta*.3")):
    pnl_seq, wseq = run_hedge(M, eta * e_mult)
    churn = sum(sum(abs(wseq[t][i] - wseq[t-1][i]) for i in range(len(NAMES))) for t in range(1, T)) / (T - 1)
    res[f"hedge_{tag}"] = summarize(f"Hedge {tag}", pnl_seq, f"churn={churn:.3f}/day")
    res[f"hedge_{tag}"]["churn"] = churn
    if tag == "eta*1":
        res["hedge_final_w"] = dict(zip(NAMES, [round(x, 3) for x in wseq[-1]]))

ts_pnl, ts_sw = run_thompson(M)
res["thompson"] = summarize("Thompson (full-info)", ts_pnl, f"switches~{ts_sw:.1f}")
res["thompson"]["switches"] = ts_sw

# oracle static on TEST
best_test = max(NAMES, key=lambda a: sum(arms[a].get(d, 0) for d in days[test_start_idx:]))
print(" oracle best static on TEST:", best_test)

# ---- real ledger version ----
print("\n-- real ledger daily engine pnl (short window, illustrative only) --")
tr = json.load(open(os.path.join(D, "trades.json")))
led = defaultdict(lambda: defaultdict(float))
for x in tr:
    if x.get("status") != "settled" or x.get("pnl") is None: continue
    led[x["eng"]][x["t0"] // 86400] += x["pnl"]
engs = [e for e in led if sum(len(v) for v in [led[e]]) and e != "capless"]
ldays = sorted({d for e in engs for d in led[e]})
LM = [[led[e].get(d, 0.0) for e in engs] for d in ldays]
print("engines:", engs, "days:", len(ldays))
for i, e in enumerate(engs):
    print(f"  {e:10s} total={sum(r[i] for r in LM):8.0f}  daily={[round(r[i]) for r in LM]}")
lp, lw = run_hedge(LM, math.sqrt(8 * math.log(len(engs)) / len(LM)))
print(" Hedge on ledger:", round(sum(lp)), "final w:", {e: round(lw[-1][i], 2) for i, e in enumerate(engs)})
tp, tsw = run_thompson(LM, reps=400)
print(" Thompson on ledger:", round(sum(tp)), "switches~", round(tsw, 1))
res["ledger"] = {"engines": engs, "n_days": len(ldays),
                 "hedge_total": sum(lp), "thompson_total": sum(tp),
                 "best_static": max((sum(r[i] for r in LM), e) for i, e in enumerate(engs))[1]}

json.dump(res, open(os.path.join(W, "alloc_results.json"), "w"), indent=1)
print("\nsaved alloc_results.json")
