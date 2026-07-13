#!/usr/bin/env python3
"""Verify cap_window.json claims from raw state_extract + trades_unified.
Independent recomputation of: implicit f>0 ask caps, cap-sweep availability
multipliers and EV poles, task-2 counts/leak numbers, window entrySec fractions.
"""
import json, math

BASE = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt"
FEE, SLIP = 0.07, 0.01
cost_of = lambda p: p + FEE * p * (1 - p)
def p_of_cost(c):
    return (1.07 - math.sqrt(1.07 ** 2 - 4 * FEE * c)) / (2 * FEE)

state = json.load(open(BASE + "/data/state_extract.json"))
trades = json.load(open(BASE + "/data/trades_unified.json"))
ms = state["measure"]
cfg = state["impulse_cfg"]
out = {}

# ---- implicit ask cap under f>0 rule ----
def skips(p, qlo, qhi):
    c = cost_of(p)
    qh = qlo if c < 0.50 else qhi
    return not (qh - (1 - qh) * c / (1 - c) > 0)
def icap(qlo, qhi):
    a = 0.60
    while a > 0.20:
        if not skips(round(a + SLIP, 4), qlo, qhi):
            return round(a, 2)
        a = round(a - 0.01, 2)
out["implicit_caps"] = dict(qlo_qhi=[cfg["qlo"], cfg["qhi"]],
                            now=icap(cfg["qlo"], cfg["qhi"]),
                            post_R8=icap(0.4954, cfg["qhi"]),
                            ceiling_056=icap(0.56, 0.56))

# ---- book reconstruction & cap sweep ----
book = []
for m in ms:
    p = round(p_of_cost(m["cost"]), 4)
    book.append(dict(p=p, ask=round(p - SLIP, 2), cost=m["cost"], sized=m["sized"],
                     skip=m.get("skip"), win=m.get("win")))
out["book_n"] = len(book)
out["book_ask_range"] = [min(b["ask"] for b in book), max(b["ask"] for b in book)]

RP, RI = 12 / 21, 0.112
def cap_avail(cap, refill):
    W = 0.0
    for b in book:
        if b["p"] <= cap + 1e-9:
            W += 1.0
        elif refill:
            W += RP
    return round(W / len(book), 3)
out["avail_refill"] = {c: cap_avail(c, True) for c in (0.47, 0.49, 0.51, 0.53)}
out["avail_norefill"] = {c: cap_avail(c, False) for c in (0.47, 0.49, 0.51, 0.53)}

def cap_ev(cap, q, refill=True):
    fills = []
    for b in book:
        if b["p"] <= cap + 1e-9:
            fills.append((b["p"], 1.0))
        elif refill:
            fills.append((min(b["p"] - RI, cap), RP))
    W = sum(w for _, w in fills)
    mc = sum(cost_of(p) * w for p, w in fills) / W
    return round((q - mc) * 100, 2)
out["ev_qflat_refill_qxt57"] = {c: cap_ev(c, 0.57) for c in (0.47, 0.49, 0.51, 0.53)}
out["ev_qflat_refill_qtl5222"] = {c: cap_ev(c, 0.5222) for c in (0.47, 0.53)}

# ---- task 2 counts ----
chg = [b for b in book if b["ask"] > 0.47 + 1e-9 and not skips(b["p"], cfg["qlo"], cfg["qhi"])]
out["cap47_blocks_but_f_sized"] = len(chg)
out["book_asks_above_47"] = sorted(b["ask"] for b in book if b["ask"] > 0.47 + 1e-9)

def pnl(ts):
    if not ts:
        return None
    return round(sum((1 if t.get("result") == "win" else 0) - cost_of(t["entry"]) for t in ts)
                 / len(ts) * 100, 2)
v3 = {}
for eng in ("impulse_v2", "impulse50", "reversal_v2"):
    v3[eng] = [t for t in trades if t.get("eng") == eng and t.get("status") == "settled"]
fa = [t for t in v3["impulse_v2"] if t.get("ask") is not None and t["ask"] > 0.47 + 1e-9]
ia = [t for t in v3["impulse50"] if t.get("ask") is not None and t["ask"] > 0.47 + 1e-9]
out["flagship_above47"] = dict(n=len(fa), of=len(v3["impulse_v2"]),
                               ev=pnl(fa), all_ev=pnl(v3["impulse_v2"]))
out["impulse50_above47"] = dict(n=len(ia), of=len(v3["impulse50"]),
                                ev=pnl(ia), all_ev=pnl(v3["impulse50"]))
sk = [b for b in book if b["skip"] == "f_nonpos" and b["win"] is not None]
out["f_nonpos"] = dict(n=len(sk), q=round(sum(b["win"] for b in sk) / len(sk), 4),
                       ev_c=round((sum(b["win"] for b in sk) / len(sk)
                                   - sum(b["cost"] for b in sk) / len(sk)) * 100, 2))

# check .49 rejection arithmetic: ask .49 -> p .50 -> cost
out["cost_of_ask49_fill"] = round(cost_of(0.50), 4)

# ---- window entrySec ----
def es(eng):
    return sorted(round(t["at"] / 1000 - t["t0"], 1) for t in v3[eng])
ff = sorted(es("impulse50") + es("reversal_v2"))
fl = es("impulse_v2")
frac = lambda xs, w: round(sum(1 for x in xs if x <= w) / len(xs), 3)
out["window"] = dict(n_ff=len(ff), p50=ff[len(ff)//2], max_ff=max(ff),
                     ff_frac={w: frac(ff, w) for w in (15, 30, 45)},
                     n_flag=len(fl), max_flag=max(fl),
                     flag_frac={w: frac(fl, w) for w in (15, 30, 45)})

json.dump(out, open(BASE + "/work-deepen/verify/params-1/verify_capwin.json", "w"), indent=1)
print(json.dumps(out, indent=1))
