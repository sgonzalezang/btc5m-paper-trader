#!/usr/bin/env python3
"""ADVERSARIAL REPRO (params-0): verify the <=47c firstFillMax claims and the cap-sweep
inputs against the REAL v3-era ledger (trades_unified.json) and the live measurement
book (state_extract.json). Independent code — does not import cap_window.py logic.
"""
import json, math

BASE = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt"
FEE, SLIP = 0.07, 0.01
cost_of = lambda p: p + FEE * p * (1 - p)

st = json.load(open(BASE + "/data/state_extract.json"))
tr = json.load(open(BASE + "/data/trades_unified.json"))
cfg = st["impulse_cfg"]

# invert cost -> fill price p (quadratic: .07p^2 - 1.07p + c = 0, small root)
def p_of(c):
    return (1.07 - math.sqrt(1.07 ** 2 - 4 * FEE * c)) / (2 * FEE)

book = []
for m in st["measure"]:
    p = p_of(m["cost"])
    book.append(dict(t0=m["t0"], ask=round(p - SLIP, 2), p=round(p, 4),
                     cost=m["cost"], sized=m["sized"], skip=m.get("skip"),
                     win=m.get("win")))

# f>0 rule exactly as bot _impulse_stake (haircut currently False in state)
def f_sizes(p, qlo=cfg["qlo"], qhi=cfg["qhi"], haircut=cfg["haircut"]):
    c = cost_of(p)
    qh = qlo if c < 0.50 else qhi
    if haircut:
        qh = 0.5 + (qh - 0.5) / 2
    return qh - (1 - qh) * c / (1 - c) > 0

def implicit_cap(qlo, qhi):
    best = None
    a = 0.20
    while a <= 0.60:
        if f_sizes(round(a + SLIP, 4), qlo, qhi, False):
            best = round(a, 2)
        a = round(a + 0.01, 2)
    return best

# --- task2 checks ---
blocked_but_sized = [b for b in book if b["ask"] > 0.47 + 1e-9 and f_sizes(b["p"])]
sized_flag_agree = sum(1 for b in book if f_sizes(b["p"]) == b["sized"])
asks = sorted(b["ask"] for b in book)

def led(eng):
    return [t for t in tr if t.get("eng") == eng and t.get("status") == "settled"]

def ev_c(ts):
    if not ts:
        return None
    return round(sum((1 if t["result"] == "win" else 0) - cost_of(t["entry"]))
                 * 100 / len(ts), 2) if False else round(
        sum(((1 if t["result"] == "win" else 0) - cost_of(t["entry"])) for t in ts)
        / len(ts) * 100, 2)

flag = led("impulse_v2"); i50 = led("impulse50"); rev = led("reversal_v2")
flag_hi = [t for t in flag if t.get("ask") is not None and t["ask"] > 0.47 + 1e-9]
i50_hi = [t for t in i50 if t.get("ask") is not None and t["ask"] > 0.47 + 1e-9]
skipb = [b for b in book if b["skip"] == "f_nonpos" and b["win"] is not None]

# --- cap-sweep availability recheck, BOTH semantics (ask<=cap vs fill p<=cap) ---
def avail(cap, on_ask):
    n = sum(1 for b in book if (b["ask"] if on_ask else b["p"]) <= cap + 1e-9)
    return round(n / len(book), 3)

# --- window: entrySec straight from the ledger field ---
def esec(ts):
    return sorted(t["entrySec"] for t in ts if t.get("entrySec") is not None)

ff = esec(i50) + esec(rev); ff.sort()
fl = esec(flag)
frac = lambda xs, w: round(sum(1 for x in xs if x <= w) / len(xs), 3)

out = dict(
    implicit_cap=dict(now=implicit_cap(cfg["qlo"], cfg["qhi"]),
                      post_r8_qlo_4954=implicit_cap(0.4954, cfg["qhi"]),
                      qhat_ceiling_056=implicit_cap(0.56, 0.56),
                      haircut_state=cfg["haircut"]),
    measure_book=dict(n=len(book), ask_min=asks[0], ask_max=asks[-1],
                      n_ask_gt47=sum(1 for a in asks if a > 0.47 + 1e-9),
                      blocked_by_47_but_f_sized=len(blocked_but_sized),
                      f_rule_matches_sized_stamp=sized_flag_agree,
                      mean_cost=round(sum(b["cost"] for b in book) / len(book), 4)),
    f_nonpos_cohort=dict(n=len(skipb),
                         q=round(sum(b["win"] for b in skipb) / len(skipb), 4),
                         ev_c=round((sum(b["win"] for b in skipb) / len(skipb)
                                     - sum(b["cost"] for b in skipb) / len(skipb)) * 100, 2)),
    ledger=dict(flagship=dict(n=len(flag), n_ask_gt47=len(flag_hi),
                              max_ask=max((t["ask"] for t in flag if t.get("ask") is not None), default=None),
                              ev_all=ev_c(flag)),
                impulse50=dict(n=len(i50), n_ask_gt47=len(i50_hi),
                               ev_gt47=ev_c(i50_hi), ev_all=ev_c(i50)),
                ask49_cost=round(cost_of(0.49 + SLIP), 4)),
    cap_avail_semantics=dict(
        on_fill_p={c: avail(c, False) for c in (0.47, 0.49, 0.51, 0.53)},
        on_ask={c: avail(c, True) for c in (0.47, 0.49, 0.51, 0.53)}),
    window=dict(first_fill=dict(n=len(ff), p50=ff[len(ff) // 2], max=max(ff),
                                le15=frac(ff, 15), le30=frac(ff, 30), le45=frac(ff, 45)),
                flagship=dict(n=len(fl), max=max(fl), le45=frac(fl, 45))),
)
json.dump(out, open(BASE + "/work-deepen/verify/params-0/repro_cap.json", "w"), indent=1)
print(json.dumps(out, indent=1))
