#!/usr/bin/env python3
"""Independent verification checks for wave-2 qhat unit (verify/qhat-1).
stdlib only."""
import json, math, datetime

DS = json.load(open("/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/"
                    "work-deepen/dataset/signals_60d.json"))
ST = json.load(open("/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/"
                    "data/state_extract.json"))
TR = json.load(open("/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/"
                    "data/trades_unified.json"))
TEST_T0 = 1782432000
TIE_UP = 0.432
out = {}

# ---------- 1. circularity: 60d gated q ----------
gated = [r for r in DS["rows"] if r["trigger"] and r["gatePass"]]
def pwin(r):
    if r["side"] == "up":
        return 1.0 if r["label"] == "up" else (TIE_UP if r["label"] == "tie" else 0.0)
    return 1.0 if r["label"] == "down" else ((1 - TIE_UP) if r["label"] == "tie" else 0.0)
allq = sum(pwin(r) for r in gated) / len(gated)
nontie = [r for r in gated if r["label"] != "tie"]
exq = sum(pwin(r) for r in nontie) / len(nontie)
trq = [pwin(r) for r in gated if r["t0"] < TEST_T0]
teq = [pwin(r) for r in gated if r["t0"] >= TEST_T0]
out["gated_q"] = dict(n=len(gated), q_all=round(allq, 4), q_ex_tie=round(exq, 4),
                      q_train=round(sum(trq)/len(trq), 4), n_train=len(trq),
                      q_test=round(sum(teq)/len(teq), 4), n_test=len(teq),
                      informed_seed=0.54,
                      note="is .54 seed ~ the 60d gated q (circular)?")

# ---------- 2. guard reachability: rolling 7d gated-signal counts ----------
t0s = sorted(r["t0"] for r in gated)
best7 = 0; besti = 0
j = 0
for i in range(len(t0s)):
    while t0s[i] - t0s[j] > 7 * 86400: j += 1
    if i - j + 1 > best7: best7, besti = i - j + 1, i
span_days = (t0s[-1] - t0s[0]) / 86400.0
out["reachability"] = dict(
    gated_signals_total=len(t0s), span_days=round(span_days, 2),
    mean_per_day=round(len(t0s) / span_days, 2),
    max_rolling_7d_count=best7,
    max_7d_per_day=round(best7 / 7.0, 2),
    needed_for_haircut_7d=120,
    ever_reaches_120_in_7d=bool(best7 >= 120),
    note="upper bound: every gated signal becomes a settled measure record "
         "(really only cap-compliant ones do)")

# ---------- 3. measure-book direct checks ----------
ms = ST["measure"]
settled = [m for m in ms if m["win"] is not None]
lo = [m for m in settled if m["cost"] < 0.50]
hi = [m for m in settled if m["cost"] >= 0.50]
out["live_book"] = dict(
    n_records=len(ms), n_settled=len(settled),
    lo=(sum(m["win"] for m in lo), len(lo)), hi=(sum(m["win"] for m in hi), len(hi)),
    firstpoll_netps_c=round(100 * sum((1 - m["cost"]) if m["win"] else -m["cost"]
                                      for m in settled) / len(settled), 2),
    hybrid_qlo=round((sum(m["win"] for m in lo) + 100) / (len(lo) + 200), 4),
    hybrid_qhi=round((sum(m["win"] for m in hi) + 100) / (len(hi) + 200), 4),
    binom_se_on_35=round(math.sqrt(0.5 * 0.5 / 35), 3))

# n7 at Jul-11 nightly (n=4)
t = 1783728604
s4 = [m for m in ms if m["win"] is not None and m["t0"] + 300 <= t]
out["jul11_n4"] = dict(n=len(s4),
                       netps_c=round(100 * sum((1 - m["cost"]) if m["win"] else -m["cost"]
                                               for m in s4) / len(s4), 2))

# ---------- 4. no-min bench counterfactual from ledger ----------
iv2 = [x for x in TR if x.get("eng") == "impulse_v2" and x.get("result") in ("win", "loss")]
sk = [x for x in iv2 if x["t0"] >= t]
out["no_min_bench_cf"] = dict(n=len(sk), pnl=round(sum(x["pnl"] for x in sk), 2),
                              cps=round(100 * sum(x["pnl"] for x in sk) /
                                        sum(x["shares"] for x in sk), 2),
                              n_iv2_total=len(iv2))

# ---------- 5. informed-family flip records: costs and per-record EV ----------
def peff_of(c): return (1.07 - math.sqrt(1.07 * 1.07 - 0.28 * c)) / 0.14
qlo_i = min(0.56, round((sum(m["win"] for m in settled if peff_of(m["cost"]) < 0.50) + 400 * 0.54) /
                        (sum(1 for m in settled if peff_of(m["cost"]) < 0.50) + 400), 4))
qhi_i = min(0.56, round((sum(m["win"] for m in settled if peff_of(m["cost"]) >= 0.50) + 400 * 0.54) /
                        (sum(1 for m in settled if peff_of(m["cost"]) >= 0.50) + 400), 4))
def dec(qlo, qhi, bucket):
    d = []
    for m in ms:
        c = m["cost"]
        isl = (c < 0.50) if bucket == "cost" else (peff_of(c) < 0.50)
        q = qlo if isl else qhi
        d.append(bool(q - (1 - q) * c / (1 - c) > 0))
    return d
d_cur = dec(ST["impulse_cfg"]["qlo"], ST["impulse_cfg"]["qhi"], "cost")
d_inf = dec(qlo_i, qhi_i, "peff")
flips = [i for i in range(len(ms)) if d_cur[i] != d_inf[i]]
det = []
tot = 0.0; nsett = 0
for i in flips:
    m = ms[i]
    if m["win"] is None:
        det.append((round(m["cost"], 4), None)); continue
    net = ((1 - m["cost"]) if m["win"] else -m["cost"]) * (1 if d_inf[i] else -1)
    tot += net; nsett += 1
    det.append((round(m["cost"], 4), round(net, 4)))
out["informed_M400_flips"] = dict(
    qlo=qlo_i, qhi=qhi_i, n_flips=len(flips), n_flips_settled=nsett,
    sum_net_per_share_usd=round(tot, 3),
    mean_net_per_share_c=round(100 * tot / nsett, 2) if nsett else None,
    all_newly_sized=all(d_inf[i] for i in flips),
    flip_costs=[d[0] for d in det])

print(json.dumps(out, indent=1))
json.dump(out, open("/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/"
                    "work-deepen/verify/qhat-1/indep_checks.json", "w"), indent=1)
