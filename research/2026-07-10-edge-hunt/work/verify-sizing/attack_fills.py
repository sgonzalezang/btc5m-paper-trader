#!/usr/bin/env python3
"""Adversarial attack: fees, fills, market reality.

A. Match pm_prices_sample.json (216 markets, ~3d) to the gated reversal stream.
   Fill model: side price at 20s + 1c slip, bot cap 0.55 (revEntryMax).
   - fillable fraction, q conditional on fillable vs not (adverse selection)
   - realized EV/$ using per-market honest fills + exact fee, outcome = pm up_won
B. Kelly f* sensitivity across the live fill distribution (p=0.45..0.55).
C. Live ledger reality: reversal-family PnL per $ staked vs claimed +6.7%/$.
D. Simulated-vs-live edge cross-check on the same 3d window.
"""
import json, os

SCRATCH = "/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad"
D = os.path.join(SCRATCH, "data")
W = os.path.join(SCRATCH, "work", "verify-sizing")

def cost(p): return p + 0.07 * p * (1 - p)
def kelly(q, p):
    c = cost(p)
    return (q - c) / (1 - c)

# rebuild gated stream (same construction as repro.py)
cb = json.load(open(os.path.join(D, "cb5m.json")))
t, o, c = cb["t"], cb["o"], cb["c"]
n = len(t)
sig = {}
for i in range(13, n):
    if t[i] - t[i-1] != 300: continue
    if any(t[i-j] - t[i-j-1] != 300 for j in range(12)): continue
    m = (o[i] - o[i-1]) / o[i-1]
    if abs(m) < 0.0012: continue
    den = sum(abs(o[i-j] - o[i-j-1]) for j in range(12))
    eff = abs(o[i] - o[i-12]) / den if den > 0 else 1.0
    side_up = 1 if m < 0 else 0
    up_won = 1 if c[i] >= o[i] else 0
    sig[t[i]] = {"eff": eff, "side_up": side_up, "cb_up_won": up_won,
                 "gated": eff <= 0.48}

pm = json.load(open(os.path.join(D, "pm_prices_sample.json")))
CAP = 0.55
SLIP = 0.01
rows = []
for r in pm:
    s = sig.get(r["t0"])
    if s is None or r.get("p20") is None: continue
    p_side = r["p20"] if s["side_up"] else round(1 - r["p20"], 4)
    fill = round(p_side + SLIP, 4)
    win_pm = 1 if (s["side_up"] == r["up_won"]) else 0
    win_cb = 1 if (s["side_up"] == s["cb_up_won"]) else 0
    rows.append({"t0": r["t0"], "gated": s["gated"], "p_side": p_side, "fill": fill,
                 "fillable": fill <= CAP, "win_pm": win_pm, "win_cb": win_cb})

def summarize(rr, tag):
    if not rr:
        print(tag, "EMPTY"); return None
    nn = len(rr)
    fillable = [x for x in rr if x["fillable"]]
    unfill = [x for x in rr if not x["fillable"]]
    out = {"tag": tag, "n": nn, "n_fillable": len(fillable),
           "q_all_pm": sum(x["win_pm"] for x in rr) / nn,
           "q_all_cb": sum(x["win_cb"] for x in rr) / nn}
    if fillable:
        qf = sum(x["win_pm"] for x in fillable) / len(fillable)
        mean_fill = sum(x["fill"] for x in fillable) / len(fillable)
        ev = sum((x["win_pm"] - cost(x["fill"])) for x in fillable) / len(fillable)
        ev_per_dollar = sum((x["win_pm"] - cost(x["fill"])) / cost(x["fill"]) for x in fillable) / len(fillable)
        out.update({"q_fillable_pm": qf,
                    "q_fillable_cb": sum(x["win_cb"] for x in fillable) / len(fillable),
                    "mean_fill": mean_fill, "median_fill": sorted(x["fill"] for x in fillable)[len(fillable)//2],
                    "ev_per_share": ev, "ev_per_dollar": ev_per_dollar,
                    "kelly_at_emp": kelly(qf, mean_fill)})
    if unfill:
        out["q_unfillable_pm"] = sum(x["win_pm"] for x in unfill) / len(unfill)
    print(json.dumps(out, indent=1))
    return out

res = {"matched_all": summarize(rows, "ALL matched signals"),
       "matched_gated": summarize([x for x in rows if x["gated"]], "GATED matched signals")}

# B. Kelly sensitivity to fill price at q=0.56 and q=0.5629
sens = []
for q in (0.56, 0.5629):
    for p in (0.45, 0.47, 0.49, 0.51, 0.53, 0.55):
        sens.append({"q": q, "p": p, "hurdle": round(cost(p), 4), "f_star": round(kelly(q, p), 4)})
res["kelly_price_sens"] = sens
print("\nKelly f* vs fill price:")
for x in sens:
    print(f" q={x['q']} p={x['p']:.2f} hurdle={x['hurdle']:.4f} f*={x['f_star']:+.4f}")

# C. live ledger PnL per $ staked, reversal family (current book, $50 stakes)
tr = json.load(open(os.path.join(D, "trades.json")))
fam = [x for x in tr if x.get("eng") in ("reversal", "reversal2", "latentfire")]
cur = [x for x in fam if x.get("src") and "prereset" not in str(x.get("src"))]
def led(rr, tag):
    settled = [x for x in rr if x.get("pnl") is not None]
    if not settled: return None
    tot = sum(x["pnl"] for x in settled)
    stakes = [x.get("stake") or 50.0 for x in settled]
    d = {"tag": tag, "n": len(settled), "pnl": round(tot, 2),
         "pnl_per_trade": round(tot / len(settled), 3),
         "pnl_per_dollar": round(tot / sum(stakes), 4)}
    print(json.dumps(d))
    return d
print("\nLive ledger reversal family:")
res["ledger_all"] = led(fam, "all(incl prereset)")
res["ledger_current"] = led(cur, "current")

json.dump(res, open(os.path.join(W, "attack_fills_results.json"), "w"), indent=1)
