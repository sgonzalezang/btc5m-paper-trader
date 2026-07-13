#!/usr/bin/env python3
"""REPRO verify (qhat-0) — Part 1: independent re-audit of the guard/bench trail.

Written from scratch against the bot code (btc5m_bot.py nightly at ~line 615-660),
NOT copied from the unit's audit.py. Checks:
  A. loop_metrics.jsonl line classification (fixture vs genuine) from raw signatures
  B. bot.log guard-line count
  C. replication of every genuine nightly (qlo/qhi/settled) from the measure book,
     scanning settle lag 0..600s in 15s steps (finer than the unit's {0,120,300,600})
  D. no-n-minimum bench counterfactual (first fire + operated PnL foregone)
  E. M2 seeding counterfactual (recomputing the n=123 cohort from trades_unified
     independently, not just citing R8-repro)
  F. guard reachability arithmetic
  G. live-book family table (deployed / spec / hybrid / informed) + jitter of the
     bucket edge +-1c on the REAL cost distribution
stdlib only.
"""
import json, os, math, datetime, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data"
BOT = "/Users/sgonzalez/btc5m-paper-trader/bot"

def utc(ts): return datetime.datetime.utcfromtimestamp(ts).strftime("%m-%d %H:%M:%S")

st = json.load(open(os.path.join(DATA, "state_extract.json")))
ms = st["measure"]
cfg = st["impulse_cfg"]
trades = json.load(open(os.path.join(DATA, "trades_unified.json")))

out = {}

# ---- A. classify loop_metrics from raw content, no precomputed signature ----
lm = [json.loads(l) for l in open(os.path.join(BOT, "loop_metrics.jsonl")) if l.strip()]
# Independent derivation of the selftest fixture line: btc5m_bot.py ~1585-1593 builds
# 300 records cost .4975, win = 1 if i%10<3 (30%), then _impulse_nightly.
fx_qlo = round(min(0.56, (sum(1 for i in range(300) if i % 10 < 3) + 400 * 0.5057) / (300 + 400)), 4)
fx_n15 = round((90 * (1 - 0.4975) - 210 * 0.4975) / 300, 4)
fixture = [r for r in lm if r["measured"] == 300 and r["qlo"] == fx_qlo and r["benched"] and r["haircut"]]
genuine = [r for r in lm if r not in fixture]
out["A_loop_metrics"] = dict(
    total=len(lm), fixture=len(fixture), genuine=len(genuine),
    fixture_qlo_derived=fx_qlo, fixture_n15_derived=fx_n15,
    fixture_all_match_derived=all(r["n15"] == fx_n15 and r["settled"] == 300 and r["bank"] == 1000.0
                                  for r in fixture),
    genuine_ticks=[utc(r["t"]) for r in genuine],
    genuine_all_unbenched=all((not r["benched"]) and (not r["haircut"]) for r in genuine),
    one_genuine_per_nightly_due=len({(r["t"] - 600) // 86400 for r in genuine}) == len(genuine))

# ---- B. bot.log guard lines ----
g = subprocess.run(["grep", "-c", "-i", "guard", os.path.join(BOT, "bot.log")],
                   capture_output=True, text=True)
b = subprocess.run(["grep", "-c", "BENCHED", os.path.join(BOT, "bot.log")],
                   capture_output=True, text=True)
n_nightly = subprocess.run(["grep", "-c", "nightly:", os.path.join(BOT, "bot.log")],
                           capture_output=True, text=True)
out["B_bot_log"] = dict(guard_lines=int(g.stdout.strip() or 0) if g.returncode in (0, 1) else None,
                        benched_lines=int(b.stdout.strip() or 0) if b.returncode in (0, 1) else None,
                        nightly_lines=int(n_nightly.stdout.strip() or 0))

# ---- C. replicate genuine nightlies (my own code) ----
def qhat(settled_recs, lo, seed):
    xs = [m for m in settled_recs if (m["cost"] < 0.50) == lo]
    return round(min(0.56, (sum(m["win"] for m in xs) + 400 * seed) / (len(xs) + 400)), 4)

def netps(xs):
    return sum((1 - m["cost"]) if m["win"] else -m["cost"] for m in xs) / len(xs) if xs else None

nightly = []
for r in genuine:
    tick = r["t"]
    hit = None
    for lag in range(0, 601, 15):
        stl = [m for m in ms if m["win"] is not None and m["t0"] + 300 + lag <= tick]
        if (qhat(stl, True, 0.5057) == r["qlo"] and qhat(stl, False, 0.5068) == r["qhi"]
                and len(stl) == r["settled"]):
            hit = (lag, stl); break
    match = hit is not None
    lag, stl = hit if hit else (None, [m for m in ms if m["win"] is not None and m["t0"] + 300 <= tick])
    x7 = [m for m in stl if m["t0"] >= tick - 7 * 86400]
    n7 = netps(x7)
    nightly.append(dict(
        tick=utc(tick), replicated=match, lag_s=lag,
        n7_raw=[None if n7 is None else round(n7, 4), len(x7)],
        guard_would_fire_per_code=bool(len(x7) >= 120 and n7 < -0.04) or
                                  bool(len([m for m in stl if m["t0"] >= tick - 15 * 86400]) >= 250),
        nomin_bench=bool(x7 and n7 < -0.04), nomin_haircut=bool(x7 and n7 < -0.02)))
out["C_nightly_replication"] = nightly

# ---- D. no-min bench counterfactual ----
fire = next((r for r, a in zip(genuine, nightly) if a["nomin_bench"]), None)
if fire:
    iv2 = [t for t in trades if t.get("eng") == "impulse_v2" and t.get("result") in ("win", "loss")]
    sk = [t for t in iv2 if t["t0"] >= fire["t"]]
    pnl = sum(t["pnl"] for t in sk)
    shares = sum(t["shares"] for t in sk)
    out["D_nomin_bench_cf"] = dict(fires=utc(fire["t"]), trades_skipped=len(sk),
                                   pnl_foregone=round(pnl, 2), cps=round(100 * pnl / shares, 2))

# ---- E. M2 seed cohort recomputed from trades_unified ----
# FINAL-DESIGN 5.3 / MF3: pre-launch cap-censored reversal-family ledger
# (engines reversal/reversal2, entry <= .531, at < launch) — per R8-repro's
# verified construction; recomputed here from the raw ledger.
launch_s = 1783695941
cand = [t for t in trades if t.get("eng") in ("reversal", "reversal2")
        and t.get("result") in ("win", "loss")
        and t.get("entry") is not None and t["entry"] <= 0.531
        and t["at"] / 1000 < launch_s]
n123 = len(cand)
net = sum((1 - (t["entry"] + 0.07 * t["entry"] * (1 - t["entry"]))) if t["result"] == "win"
          else -(t["entry"] + 0.07 * t["entry"] * (1 - t["entry"])) for t in cand) / max(1, n123)
# seeded n7 at each genuine nightly
m2 = []
for r, a in zip(genuine, nightly):
    tick = r["t"]
    stl = [m for m in ms if m["win"] is not None and m["t0"] + 300 + (a["lag_s"] or 0) <= tick]
    x7 = [m for m in stl if m["t0"] >= tick - 7 * 86400]
    live = sum((1 - m["cost"]) if m["win"] else -m["cost"] for m in x7)
    n = 123 + len(x7)
    v = (123 * 0.0275 + live) / n
    m2.append(dict(tick=utc(tick), n=n, seeded_n7_c=round(100 * v, 2),
                   evaluable=n >= 120, fires=bool(n >= 120 and (v < -0.02))))
out["E_m2"] = dict(cohort_recount=n123, cohort_netps_c=round(100 * net, 2),
                   expected=(123, 2.75), per_nightly=m2)

# ---- F. reachability arithmetic ----
settled = [m for m in ms if m["win"] is not None]
span_d = (ms[-1]["t0"] - ms[0]["t0"]) / 86400.0
rate = len(settled) / span_d
x7 = [m for m in settled if m["t0"] >= ms[-1]["t0"] - 7 * 86400]
out["F_reach"] = dict(rate_per_day=round(rate, 2),
                      needs=dict(h7=round(120 / 7, 1), b15=round(250 / 15, 1), u10=10.0),
                      reachable=dict(h7=rate >= 120 / 7, b15=rate >= 250 / 15, u10=rate >= 10),
                      n7_now_c=round(100 * netps(x7), 2), n7_n=len(x7),
                      rescale_check=dict(h7_80=round(80 / 7, 1), b15_170=round(170 / 15, 1)))

# ---- G. live-book table + boundary jitter on REAL costs ----
def peff(c): return (1.07 - math.sqrt(1.07 ** 2 - 0.28 * c)) / 0.14
def live_q(bucket, edge, M, seed):
    lo = [m for m in settled if (m["cost"] if bucket == "cost" else peff(m["cost"])) < edge]
    hi = [m for m in settled if m not in lo]
    return (round(min(0.56, (sum(m["win"] for m in lo) + M * seed[0]) / (len(lo) + M)), 4),
            round(min(0.56, (sum(m["win"] for m in hi) + M * seed[1]) / (len(hi) + M)), 4))
def decs(qlo, qhi, bucket, edge):
    o = []
    for m in ms:
        q = qlo if (m["cost"] if bucket == "cost" else peff(m["cost"])) < edge else qhi
        o.append(q - (1 - q) * m["cost"] / (1 - m["cost"]) > 0)
    return o
d_cur = decs(cfg["qlo"], cfg["qhi"], "cost", 0.50)
G = dict(deployed_n_sized=sum(d_cur))
for nm, (bucket, edge, M, seed) in dict(
        b_spec=("peff", 0.50, 200, (0.5, 0.5)),
        hybrid=("cost", 0.50, 200, (0.5, 0.5)),
        informed_M200=("peff", 0.50, 200, (0.54, 0.54)),
        hybrid_edge49=("cost", 0.49, 200, (0.5, 0.5)),
        hybrid_edge51=("cost", 0.51, 200, (0.5, 0.5))).items():
    qlo, qhi = live_q(bucket, edge, M, seed)
    d = decs(qlo, qhi, bucket, edge)
    fl = [i for i in range(len(ms)) if d[i] != d_cur[i]]
    ev = sum(((1 - ms[i]["cost"]) if ms[i]["win"] else -ms[i]["cost"]) * (1 if d[i] else -1)
             for i in fl if ms[i]["win"] is not None)
    G[nm] = dict(qlo=qlo, qhi=qhi, n_sized=sum(d), flips=len(fl), flip_ev_sum=round(ev, 3))
out["G_live_table"] = G

json.dump(out, open(os.path.join(HERE, "v_audit_results.json"), "w"), indent=1)
print(json.dumps(out, indent=1))
