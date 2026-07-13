"""Locate the merge agent's quoted numbers (Jul 10 = -13.97c worst day; Jul 11-13 = -0.90c)
across the candidate constructions: a3 lib construction (gated/ungated) and
gate_refresh construction (gated/ungated). Also fresh-excl-Jul10 for a3 gated."""
import json, sys, time, calendar
from collections import defaultdict

sys.path.insert(0, "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work/regime")
from lib import load_cb5m, build_series, eff, BREAKEVEN

t, o = load_cb5m()
t0s, r, up = build_series(t, o)
n = len(t0s)

trigs = []
for i in range(13, n):
    if abs(r[i - 1]) < 0.0012 or r[i - 1] == 0:
        continue
    prior_up = r[i - 1] > 0
    win = 1.0 if up[i] != prior_up else 0.0
    e6 = eff(r[i - 6:i])
    c12 = sum(1 for j in range(i - 13, i - 1) if abs(r[j]) >= 0.0012)
    trigs.append((t0s[i], win, e6 >= 0.10 and c12 <= 6))

def day_of(t0):
    st = time.gmtime(t0)
    return f"{st.tm_year:04d}-{st.tm_mon:02d}-{st.tm_mday:02d}"

def daily(rows):
    byd = defaultdict(list)
    for t0, w in rows:
        byd[day_of(t0)].append(w - BREAKEVEN)
    return {d: (len(v), round(100 * sum(v) / len(v), 2)) for d, v in sorted(byd.items())}

out = {}
for name, rows in (("a3_gated", [(t0, w) for t0, w, g in trigs if g]),
                   ("a3_ungated", [(t0, w) for t0, w, g in trigs])):
    dd = daily(rows)
    out[name + "_jul10_13"] = {d: dd[d] for d in dd if d >= "2026-07-10"}
    # worst days n>=5
    worst = sorted(((d, nv, e) for d, (nv, e) in dd.items() if nv >= 5), key=lambda x: x[2])[:3]
    out[name + "_worst3"] = worst
    # Jul 11-13 pooled
    sub = [(t0, w) for t0, w in rows if day_of(t0) >= "2026-07-11"]
    ev = sum(w - BREAKEVEN for _, w in sub) / len(sub) * 100
    out[name + "_jul11_13_pooled"] = {"n": len(sub), "ev_c": round(ev, 2)}
    # fresh from 11:55 excl Jul 10
    FRESH = 1783685700
    fr = [(t0, w) for t0, w in rows if t0 >= FRESH]
    fr_ex = [(t0, w) for t0, w in fr if day_of(t0) != "2026-07-10"]
    out[name + "_fresh"] = {"n": len(fr), "ev_c": round(sum(w - BREAKEVEN for _, w in fr) / len(fr) * 100, 2)}
    out[name + "_fresh_excl_jul10"] = {"n": len(fr_ex), "ev_c": round(sum(w - BREAKEVEN for _, w in fr_ex) / len(fr_ex) * 100, 2)}

json.dump(out, open("/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work/verify/R6-selection/merge_numbers.json", "w"), indent=1)
print(json.dumps(out, indent=1))
