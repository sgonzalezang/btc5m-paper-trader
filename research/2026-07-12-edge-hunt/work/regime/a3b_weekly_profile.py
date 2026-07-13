"""A3b: week-by-week (and TEST day-by-day) EV profile of the ungated and live-gated
contrarian trigger, to expose regime nonstationarity behind the pooled numbers."""
import json, sys, datetime
sys.path.insert(0, "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work/regime")
from lib import *

t, o = load_cb5m()
t0s, r, up = build_series(t, o)
n = len(t0s)

rows = []
for i in range(13, n):
    if abs(r[i - 1]) < 0.0012 or r[i - 1] == 0:
        continue
    win = 1.0 if up[i] != (r[i - 1] > 0) else 0.0
    e6 = eff(r[i - 6:i])
    c12 = sum(1 for j in range(i - 13, i - 1) if abs(r[j]) >= 0.0012)
    rows.append((t0s[i], win, e6 >= 0.10 and c12 <= 6))

def bucket_stats(sel):
    if not sel:
        return None
    nn = len(sel)
    q = sum(w for _, w, _ in sel) / nn
    return {"n": nn, "wr": round(q, 4), "ev_c": round(ev_cents(q), 2)}

weekly, daily = {}, {}
for t0, w, g in rows:
    wk = datetime.datetime.utcfromtimestamp(t0).strftime("%G-W%V")
    weekly.setdefault(wk, {"all": [], "gated": []})
    weekly[wk]["all"].append((t0, w, g))
    if g:
        weekly[wk]["gated"].append((t0, w, g))
    if t0 >= TEST_START:
        dy = datetime.datetime.utcfromtimestamp(t0).strftime("%m-%d")
        daily.setdefault(dy, {"all": [], "gated": []})
        daily[dy]["all"].append((t0, w, g))
        if g:
            daily[dy]["gated"].append((t0, w, g))

out = {"weekly": {}, "test_daily": {}}
print("week        ungated              gated(A=.10,B=6)")
for wk in sorted(weekly):
    a = bucket_stats(weekly[wk]["all"]); g = bucket_stats(weekly[wk]["gated"])
    out["weekly"][wk] = {"ungated": a, "gated": g}
    print(f"{wk}  n={a['n']:>4} wr={a['wr']:.3f} ev={a['ev_c']:+6.2f}c | n={g['n'] if g else 0:>4} " +
          (f"wr={g['wr']:.3f} ev={g['ev_c']:+6.2f}c" if g else ""))
print("\nTEST day     ungated              gated")
for dy in sorted(daily):
    a = bucket_stats(daily[dy]["all"]); g = bucket_stats(daily[dy]["gated"])
    out["test_daily"][dy] = {"ungated": a, "gated": g}
    print(f"{dy}  n={a['n']:>3} wr={a['wr']:.3f} ev={a['ev_c']:+6.2f}c | n={g['n'] if g else 0:>3} " +
          (f"wr={g['wr']:.3f} ev={g['ev_c']:+6.2f}c" if g else ""))

json.dump(out, open("/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work/regime/a3b_results.json", "w"), indent=1)
print("saved a3b_results.json")
