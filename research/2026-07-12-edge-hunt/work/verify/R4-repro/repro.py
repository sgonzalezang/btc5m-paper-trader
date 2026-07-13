#!/usr/bin/env python3
"""Independent reproduction of FINDING R4 (kill-metric semantics divergence).

Written from the claim's plain-English statement only:
  - measurement book (state_extract.measure, 36 records) runs -6.23c/share (15/35)
  - operated flagship (impulse_v2) runs +3.57c/share on the same signals
  - 12 of 21 f_nonpos skips were entered later ~11c cheaper (6/12, +8.44c/sh realized)
  - true never-entered went 3/9 (-19.6c/sh at first-poll cost)
  - measure.sized misclassifies 12 of 27 flagship entries as skips
  - => 9.8c/share divergence between kill input and operated book

All EV in cents/share. cost in measure records is verified to equal
entry + 0.07*entry*(1-entry) with entry = ask + 1c slip (frozen cost model),
so measurement net/share = win - cost (gas ignored; $0.004 on ~$25-50 stakes
is < 0.02c/share and identical across books).
"""
import json, random, math
from collections import defaultdict

BASE = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt"
state = json.load(open(BASE + "/data/state_extract.json"))
trades = json.load(open(BASE + "/data/trades_unified.json"))

measure = state["measure"]
qlo, qhi = state["impulse_cfg"]["qlo"], state["impulse_cfg"]["qhi"]

fl = [t for t in trades if t.get("eng") == "impulse_v2"]
fl_settled = [t for t in fl if t.get("result") in ("win", "loss")]
fl_by_t0 = defaultdict(list)
for t in fl:
    fl_by_t0[t["t0"]].append(t)

# ---------- sanity: cost field really is first-poll all-in cost ----------
cost_checks = []
for m in measure:
    f = m.get("f")
    if f and f.get("ask") is not None:
        entry = f["ask"] + 0.01
        implied = entry + 0.07 * entry * (1 - entry)
        cost_checks.append(abs(implied - m["cost"]))
cost_model_ok = (max(cost_checks) < 5e-4) if cost_checks else None

# ---------- measurement book net/share ----------
ms = [m for m in measure if m.get("win") in (0, 1)]
def net_ps(recs):  # cents/share, win - cost
    return 100.0 * sum((m["win"] - m["cost"]) for m in recs) / len(recs)
meas_mean = net_ps(ms)
meas_wins = sum(m["win"] for m in ms)

# ---------- operated flagship book (matched by t0) ----------
# per-share net for a ledger trade: pnl is net USD; shares known
def trade_cps(t):
    return 100.0 * t["pnl"] / t["shares"]

matched = []          # (measure record, trade) same t0
for m in measure:
    for t in fl_by_t0.get(m["t0"], []):
        matched.append((m, t))
matched_settled = [(m, t) for (m, t) in matched if t.get("result") in ("win", "loss")]
op_recs = [t for (m, t) in matched_settled]
op_mean = sum(trade_cps(t) for t in op_recs) / len(op_recs) if op_recs else None

# flagship entries NOT present in measure book at all
fl_t0s = set(fl_by_t0)
meas_t0s = set(m["t0"] for m in measure)
fl_unmatched = sorted(fl_t0s - meas_t0s)

# ---------- classes ----------
sized_recs = [m for m in measure if m["sized"]]
skip_recs = [m for m in measure if not m["sized"]]
skip_entered, skip_never = [], []
for m in skip_recs:
    ts = fl_by_t0.get(m["t0"], [])
    (skip_entered if ts else skip_never).append((m, ts))

# per-class stats
def cls_stats(pairs, use_trade):
    out = dict(n=len(pairs))
    settled = []
    for m, ts in pairs:
        if use_trade:
            for t in ts:
                if t.get("result") in ("win", "loss"):
                    settled.append((m, t))
        else:
            if m.get("win") in (0, 1):
                settled.append((m, None))
    out["n_settled"] = len(settled)
    if not settled: return out
    if use_trade:
        out["wins"] = sum(1 for m, t in settled if t["result"] == "win")
        out["cps_realized"] = round(sum(trade_cps(t) for m, t in settled) / len(settled), 2)
        out["mean_entry_discount_c"] = round(100.0 * sum(
            (m["cost"] - (t["entry"] + 0.07 * t["entry"] * (1 - t["entry"])))
            for m, t in settled) / len(settled), 2)
    else:
        out["wins"] = sum(m["win"] for m, _ in settled)
        out["cps_at_firstpoll_cost"] = round(net_ps([m for m, _ in settled]), 2)
    return out

entered_stats = cls_stats(skip_entered, True)
never_stats = cls_stats(skip_never, False)
sized_stats_meas = cls_stats([(m, fl_by_t0.get(m["t0"], [])) for m in sized_recs], True)

# ---------- same-signal audit of the 12 (merge-agent flag) ----------
audit = []
for m, ts in skip_entered:
    for t in ts:
        fsec = (m.get("f") or {}).get("sec")
        audit.append(dict(
            t0=m["t0"], side_match=(t["side"] == m["side"]),
            n_trades_this_t0=len(ts),
            measure_first_poll_sec=fsec,
            trade_entry_sec=t.get("entrySec"),
            entered_after_first_poll=(fsec is None or (t.get("entrySec") is not None and t["entrySec"] >= fsec)),
            within_45s_window=(t.get("entrySec") is not None and t["entrySec"] <= 45),
            measure_cost=m["cost"],
            trade_allin_cost=round(t["entry"] + 0.07 * t["entry"] * (1 - t["entry"]), 4),
            result=t.get("result"),
        ))
same_signal_ok = all(a["side_match"] and a["n_trades_this_t0"] == 1 for a in audit)

# ---------- mechanism check: f-sign at first-poll cost reproduces sized/skip ----------
# f = qh - (1-qh)*cost/(1-cost), bucket by cost < 0.50 (current qlo/qhi; nightly drift caveat)
def fsign(cost, edge=0.50, ql=qlo, qh_=qhi):
    q = ql if cost < edge else qh_
    return q - (1 - q) * cost / (1 - cost)
mech = dict(agree=0, disagree=0, rows=[])
for m in measure:
    f = fsign(m["cost"])
    pred_skip = f <= 0
    ok = pred_skip == (not m["sized"])
    mech["agree" if ok else "disagree"] += 1
    if not ok:
        mech["rows"].append(dict(t0=m["t0"], cost=m["cost"], f=round(f, 4), sized=m["sized"]))

# ---------- divergence + 1h-block bootstrap ----------
# kill input: measurement book (win - cost). operated: matched ledger trades cps.
def hour(t0): return t0 // 3600
meas_by_h = defaultdict(list)
for m in ms: meas_by_h[hour(m["t0"])].append(100.0 * (m["win"] - m["cost"]))
op_by_h = defaultdict(list)
for t in op_recs: op_by_h[hour(t["t0"])].append(trade_cps(t))
hours = sorted(set(meas_by_h) | set(op_by_h))

random.seed(20260712)
B = 10000
boot_meas, boot_op, boot_div = [], [], []
for _ in range(B):
    hs = [random.choice(hours) for _ in hours]
    a = [x for h in hs for x in meas_by_h.get(h, [])]
    b = [x for h in hs for x in op_by_h.get(h, [])]
    if a: boot_meas.append(sum(a) / len(a))
    if a and b: boot_div.append(sum(b) / len(b) - sum(a) / len(a))
    if b: boot_op.append(sum(b) / len(b))
def ci90(xs):
    xs = sorted(xs); n = len(xs)
    return [round(xs[int(0.05 * n)], 2), round(xs[int(0.95 * n)], 2)]

divergence = (op_mean - meas_mean) if op_mean is not None else None

# ---------- stress tests on the divergence ----------
def div_on(meas_subset, op_subset):
    if not meas_subset or not op_subset: return None
    a = 100.0 * sum(m["win"] - m["cost"] for m in meas_subset) / len(meas_subset)
    b = sum(trade_cps(t) for t in op_subset) / len(op_subset)
    return round(b - a, 2), round(a, 2), round(b, 2)

def day(t0): return t0 // 86400
days = sorted(set(day(m["t0"]) for m in ms) | set(day(t["t0"]) for t in op_recs))
# drop single best day = the day whose removal most shrinks the divergence
stress_days = {}
for dd in days:
    r = div_on([m for m in ms if day(m["t0"]) != dd], [t for t in op_recs if day(t["t0"]) != dd])
    if r: stress_days[dd] = r
worst_drop = min(stress_days.items(), key=lambda kv: kv[1][0])  # smallest remaining divergence

# halves (by time)
all_t0 = sorted(set(m["t0"] for m in ms) | set(t["t0"] for t in op_recs))
mid = all_t0[len(all_t0) // 2]
h1 = div_on([m for m in ms if m["t0"] < mid], [t for t in op_recs if t["t0"] < mid])
h2 = div_on([m for m in ms if m["t0"] >= mid], [t for t in op_recs if t["t0"] >= mid])

# jitter bucket edge +-1c: does the f-sign mechanism classification change?
jitter = {}
for e in (0.49, 0.50, 0.51):
    flips = sum(1 for m in measure if (fsign(m["cost"], edge=e) <= 0) != (not m["sized"]))
    jitter[str(e)] = flips

results = dict(
    cost_model_ok=cost_model_ok,
    measurement_book=dict(n=len(measure), n_settled=len(ms), wins=meas_wins,
                          mean_cps=round(meas_mean, 2), ci90_1hblock=ci90(boot_meas)),
    operated_flagship=dict(n_matched=len(matched), n_settled=len(op_recs),
                           wins=sum(1 for t in op_recs if t["result"] == "win"),
                           mean_cps=round(op_mean, 2) if op_mean is not None else None,
                           ci90_1hblock=ci90(boot_op) if boot_op else None,
                           fl_trades_total=len(fl), fl_settled_total=len(fl_settled),
                           fl_t0_not_in_measure=fl_unmatched),
    classes=dict(sized=sized_stats_meas, skip_entered_later=entered_stats,
                 skip_never_entered=never_stats),
    same_signal_audit=dict(ok=same_signal_ok, rows=audit),
    mechanism_f_sign=mech,
    divergence=dict(cps=round(divergence, 2) if divergence is not None else None,
                    ci90_1hblock=ci90(boot_div) if boot_div else None,
                    frac_boot_positive=round(sum(1 for x in boot_div if x > 0) / len(boot_div), 3) if boot_div else None),
    stress=dict(drop_day_min_divergence=dict(day_utc=worst_drop[0], div_meas_op=worst_drop[1]),
                per_day=[dict(day=k, div=v[0], meas=v[1], op=v[2]) for k, v in sorted(stress_days.items())],
                half1=dict(div=h1[0], meas=h1[1], op=h1[2]) if h1 else None,
                half2=dict(div=h2[0], meas=h2[1], op=h2[2]) if h2 else None,
                bucket_edge_jitter_flips=jitter),
)
json.dump(results, open(BASE + "/work/verify/R4-repro/results.json", "w"), indent=1)
print(json.dumps(results, indent=1))
