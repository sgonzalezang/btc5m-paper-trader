"""Robustness: (1) per-day follow rate of last-minute momentum (|r|>=2bps) to show sign stability;
(2) reversal-side entry cost realism from pm_prices_sample (p20) for the funding-dial EV math."""
import sys, json
sys.path.insert(0, "/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad/work/crossasset")
from util import *

cb5 = load("cb5m"); cb1 = load("cb1m")
o1 = dict(zip(cb1["t"], cb1["o"]))
out5 = {t: (1 if c >= o else 0) for t, o, c in zip(cb5["t"], cb5["o"], cb5["c"])}

daily = {}
for t0 in cb5["t"]:
    if t0 not in o1 or (t0 - 60) not in o1 or t0 not in out5: continue
    r = (o1[t0] - o1[t0 - 60]) / o1[t0 - 60] * 1e4
    if abs(r) < 2: continue
    day = t0 // 86400
    hit = 1 if (out5[t0] == 1) == (r > 0) else 0
    daily.setdefault(day, []).append(hit)
print("per-day follow rate, last-minute |r|>=2bps:")
pos = 0
for day in sorted(daily):
    k, m, rt = rate(daily[day])
    pos += rt > 0.5
    print(f"  day {day}: {rt:.3f} (n={m})")
print(f"days>50%: {pos}/{len(daily)}")

# (2) entry cost for a reversal-style ~50c entry per pm sample: distribution of p20 both sides
pm = load("pm_prices_sample")
p20 = [m["p20"] for m in pm]
print(f"\npm p20 (Up token, 20s in): q25={pct(p20,0.25):.3f} med={pct(p20,0.5):.3f} q75={pct(p20,0.75):.3f}")
# cheaper side / more expensive side cost at ~50c entries
near50 = [p for p in p20 if 0.4 <= p <= 0.6]
print(f"share of markets with p20 in [0.40,0.60]: {len(near50)/len(p20):.2f}; med of those {pct(near50,0.5):.3f}")
# EV of funding-T2-gated reversal on TEST at fill 0.51: q=0.5691
for q, lab in ((0.5539, "all-test reversal"), (0.5691, "funding-T2 test reversal"), (0.5228, "all-train reversal")):
    print(f"{lab}: q={q:.4f} fill=0.51 -> EV/share={ev(q,0.51):+.4f} (q*={qstar(0.51):.4f})")
