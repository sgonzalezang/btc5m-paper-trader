#!/usr/bin/env python3
"""Build the 60d reversal-family signal stream from cb5m.json (buffered open-to-open),
with efficiency gate variant, TRAIN/TEST split, and fill-price realism checks.

Outputs: stream.json  (list of signal dicts, chronological)
         stream_stats.json (train/test win rates, price-realism table)
"""
import json, math, os

SCRATCH = "/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad"
D = os.path.join(SCRATCH, "data")
W = os.path.join(SCRATCH, "work", "sizing")

cb = json.load(open(os.path.join(D, "cb5m.json")))
t, o, c = cb["t"], cb["o"], cb["c"]
n = len(t)

MOVE = 0.0012      # 12 bps
EFFW = 12          # trailing intervals for Kaufman efficiency
EFFMAX = 0.48

# prior move for interval i: (o[i]-o[i-1])/o[i-1]  (shared boundary, buffered)
# outcome of interval i: up if c[i] >= o[i]
stream = []
for i in range(EFFW + 1, n):
    if t[i] - t[i-1] != 300:   # require contiguous candles
        continue
    m = (o[i] - o[i-1]) / o[i-1]
    if abs(m) < MOVE:
        continue
    # Kaufman efficiency over trailing 12 completed intervals ending at i-1..i (open-to-open moves)
    ok = all(t[i-j] - t[i-j-1] == 300 for j in range(EFFW))
    if not ok:
        continue
    net = abs(o[i] - o[i-EFFW])
    den = sum(abs(o[i-j] - o[i-j-1]) for j in range(EFFW))
    eff = net / den if den > 0 else 1.0
    side_up = 1 if m < 0 else 0          # buy the OTHER side
    up_won = 1 if c[i] >= o[i] else 0    # tie -> Up
    win = 1 if side_up == up_won else 0
    stream.append({"t0": t[i], "m": m, "eff": eff, "side_up": side_up,
                   "up_won": up_won, "win": win})

t_lo, t_hi = t[0], t[-1]
split_t = t_lo + (t_hi - t_lo) * 2 / 3
for s in stream:
    s["seg"] = "TRAIN" if s["t0"] < split_t else "TEST"

def wr(rows):
    return (len(rows), sum(r["win"] for r in rows) / len(rows) if rows else float("nan"))

stats = {}
for seg in ("TRAIN", "TEST"):
    rows = [s for s in stream if s["seg"] == seg]
    gated = [s for s in rows if s["eff"] <= EFFMAX]
    stats[seg] = {"all": wr(rows), "gated": wr(gated),
                  "ungated_hi_eff": wr([s for s in rows if s["eff"] > EFFMAX])}

# ---- fill-price realism: match pm_prices_sample markets to signals ----
pm = json.load(open(os.path.join(D, "pm_prices_sample.json")))
by_t0 = {s["t0"]: s for s in stream}
matches = []
for r in pm:
    s = by_t0.get(r["t0"])
    if s is None:
        continue
    p_up20 = r.get("p20")
    if p_up20 is None:
        continue
    p_side = p_up20 if s["side_up"] else round(1 - p_up20, 4)
    matches.append({"t0": r["t0"], "p_side20": p_side, "win": 1 if s["up_won"] == r["up_won"] and s["win"] else s["win"],
                    "agree_res": int(s["up_won"] == r["up_won"])})
# live-ledger reversal-family entry distribution
tr = json.load(open(os.path.join(D, "trades.json")))
rev_entries = sorted(x["entry"] for x in tr
                     if x["eng"] in ("reversal", "reversal2", "latentfire") and x.get("entry"))

stats["pm_match"] = {
    "n": len(matches),
    "res_agree": sum(m["agree_res"] for m in matches) / len(matches) if matches else None,
    "p_side20_sorted": [m["p_side20"] for m in sorted(matches, key=lambda x: x["p_side20"])],
}
q = lambda v, f: v[min(len(v)-1, int(f*len(v)))]
stats["live_entries"] = {"n": len(rev_entries),
                         "p10": q(rev_entries, .10), "p25": q(rev_entries, .25),
                         "p50": q(rev_entries, .50), "p75": q(rev_entries, .75),
                         "p90": q(rev_entries, .90), "mean": sum(rev_entries)/len(rev_entries)}
stats["split_t"] = split_t
stats["n_stream"] = len(stream)

json.dump(stream, open(os.path.join(W, "stream.json"), "w"))
json.dump(stats, open(os.path.join(W, "stream_stats.json"), "w"), indent=1)
print(json.dumps({k: v for k, v in stats.items() if k != "pm_match"}, indent=1, default=str))
pm_m = stats["pm_match"]
print("pm_match n=", pm_m["n"], "res_agree=", pm_m["res_agree"])
ps = pm_m["p_side20_sorted"]
if ps:
    print("signal-side p20 quantiles:", ps[0], q(ps,.25), q(ps,.5), q(ps,.75), ps[-1])
    print("mean", round(sum(ps)/len(ps), 4), " frac<=0.55:", sum(1 for x in ps if x <= 0.55)/len(ps))
