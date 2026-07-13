"""Diagnostic (no fitted parameters): week-by-week EV/share at 51c of
(a) the ungated 12bps contrarian and (b) the deployed gated version, over the
full May 11 - Jul 13 span. Purpose: characterize regime dependence of the LEVEL
that the live flagship is staked on. Not a hypothesis test."""
import json, time, calendar
from common import Table, cost, block_bootstrap

tab = Table()
P = 0.51

def gate(i):
    o = tab.o
    legs = [o[i - 5 + k] - o[i - 6 + k] for k in range(6)]
    denom = sum(abs(x) for x in legs)
    eff6 = abs(o[i] - o[i - 6]) / denom if denom > 0 else 1.0
    cnt12 = sum(1 for k in range(i - 13, i - 1)
                if abs(o[k + 1] - o[k]) / o[k] >= 0.0012)
    return eff6 >= 0.10 and cnt12 <= 6

gated, ungated = [], []
for i in range(14, tab.n - 1):
    r = tab.prior_ret(i, 1)
    if r is None or abs(r) < 0.0012 or tab.up[i] is None:
        continue
    side = "down" if r > 0 else "up"
    w = 1 if ((side == "up") == (tab.up[i] == 1)) else 0
    rec = (tab.t[i], w - cost(P))
    ungated.append(rec)
    if gate(i):
        gated.append(rec)

W0 = calendar.timegm((2026, 5, 11, 0, 0, 0))
def weekly(trades):
    wk = {}
    for t, ev in trades:
        wk.setdefault((t - W0) // (7 * 86400), []).append(ev)
    out = []
    for k in sorted(wk):
        xs = wk[k]
        lab = time.strftime("%m-%d", time.gmtime(W0 + k * 7 * 86400))
        out.append({"week_of": lab, "n": len(xs),
                    "ev_c": round(sum(xs) / len(xs) * 100, 2)})
    return out

out = {"ungated_weekly": weekly(ungated), "gated_weekly": weekly(gated)}
json.dump(out, open("weekly_stability.json", "w"), indent=1)
for k, rows in out.items():
    print(k)
    for r in rows:
        print("  ", r["week_of"], "n", r["n"], "ev", r["ev_c"], "c/sh")
