"""Pre-registered refresh (NOT a new hypothesis; zero fitted parameters):
the deployed impulse_v2 signal — 12bps buffered contrarian trigger + isolation gate
eff6 >= 0.10 AND cnt12 <= 6 (constants frozen from deploy_spec.json) — evaluated on
candle data at the 51c fill assumption:
  (a) full TEST window Jun 26 - Jul 13,
  (b) the truly fresh Jul 10 15:05 -> Jul 13 slice (post v3 launch, unseen by prior work),
  (c) gated vs ungated increment on TEST (diagnostic).
eff6 includes the trigger leg; cnt12 counts the 12 moves BEFORE the trigger (bot §3.2).
"""
import json, calendar
from common import Table, block_bootstrap, cost, SPLIT_TS

tab = Table()
P = 0.51
FRESH = calendar.timegm((2026, 7, 10, 15, 5, 0))

def gate(i):
    if i < 14:
        return None, None, None
    o = tab.o
    legs = [o[i - 5 + k] - o[i - 6 + k] for k in range(6)]  # 6 legs ending at o[i]
    denom = sum(abs(x) for x in legs)
    eff6 = abs(o[i] - o[i - 6]) / denom if denom > 0 else 1.0
    cnt12 = sum(1 for k in range(i - 13, i - 1)
                if abs(o[k + 1] - o[k]) / o[k] >= 0.0012)
    return eff6, cnt12, (eff6 >= 0.10 and cnt12 <= 6)

gated, ungated = [], []
for i in range(14, tab.n - 1):
    r = tab.prior_ret(i, 1)
    if r is None or abs(r) < 0.0012 or tab.up[i] is None:
        continue
    side = "down" if r > 0 else "up"
    w = 1 if ((side == "up") == (tab.up[i] == 1)) else 0
    rec = (tab.t[i], w - cost(P))
    ungated.append(rec)
    _, _, ok = gate(i)
    if ok:
        gated.append(rec)

def stats(trades):
    if not trades:
        return {"n": 0}
    wins = sum(1 for _, ev in trades if ev > 0)
    mean, p, lo, hi = block_bootstrap(trades, reps=4000)
    return {"n": len(trades), "q": round(wins / len(trades), 4),
            "ev_c": round(mean * 100, 3), "p_boot": round(p, 4),
            "ci90_c": [round(lo * 100, 3), round(hi * 100, 3)]}

def window(trades, a, b=None):
    return [x for x in trades if x[0] >= a and (b is None or x[0] < b)]

out = {
    "gated_TEST": stats(window(gated, SPLIT_TS)),
    "ungated_TEST": stats(window(ungated, SPLIT_TS)),
    "gated_fresh_jul10_13": stats(window(gated, FRESH)),
    "ungated_fresh_jul10_13": stats(window(ungated, FRESH)),
    "gated_TRAIN": stats([x for x in gated if x[0] < SPLIT_TS]),
    "ungated_TRAIN": stats([x for x in ungated if x[0] < SPLIT_TS]),
}
# paired-days note: gate increment on TEST = mean(gated) - mean(ungated) is NOT a paired
# stat here; the shadow books answer that. This is a signal-level health check only.
json.dump(out, open("gate_refresh.json", "w"), indent=1)
print(json.dumps(out, indent=1))
