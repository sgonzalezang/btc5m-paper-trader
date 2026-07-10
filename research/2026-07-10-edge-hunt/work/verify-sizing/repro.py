#!/usr/bin/env python3
"""Independent reproduction of the sizing/Kelly finding from raw data/cb5m.json.
Own implementation of stream construction, Kelly closed form, and the p=0.51
fixed-fill bootstrap sizing sim. Compare against the finding's claimed numbers.
"""
import json, math, random, os

SCRATCH = "/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad"
D = os.path.join(SCRATCH, "data")
V = os.path.join(SCRATCH, "work", "verify-sizing")

cb = json.load(open(os.path.join(D, "cb5m.json")))
t, o, c = cb["t"], cb["o"], cb["c"]
n = len(t)
print("cb5m candles:", n, "span days:", (t[-1]-t[0])/86400)

# --- independent stream build (buffered open-to-open, |m|>=12bps, eff<=0.48 gate) ---
sig = []
for i in range(13, n):
    if t[i] - t[i-1] != 300:
        continue
    if any(t[i-j] - t[i-j-1] != 300 for j in range(12)):
        continue
    m = (o[i] - o[i-1]) / o[i-1]
    if abs(m) < 0.0012:
        continue
    den = sum(abs(o[i-j] - o[i-j-1]) for j in range(12))
    eff = abs(o[i] - o[i-12]) / den if den > 0 else 1.0
    side_up = 1 if m < 0 else 0
    up_won = 1 if c[i] >= o[i] else 0
    tiny = 1 if abs(c[i] - o[i]) / o[i] < 0.0002 else 0
    sig.append((t[i], eff, 1 if side_up == up_won else 0, tiny))

split_t = t[0] + (t[-1] - t[0]) * 2 / 3
gated = [s for s in sig if s[1] <= 0.48]
tr_g = [s for s in gated if s[0] < split_t]
te_g = [s for s in gated if s[0] >= split_t]
def wr(rows): return (len(rows), sum(r[2] for r in rows) / len(rows) if rows else float("nan"))
print("TRAIN gated:", wr(tr_g), " claimed (2065, 0.5182)")
print("TEST  gated:", wr(te_g), " claimed (1018, 0.5629)")

# --- Kelly closed form ---
def cost(p): return p + 0.07 * p * (1 - p)
def kelly(q, p):
    cc = cost(p); b = (1 - cc) / cc
    return q - (1 - q) / b
f_full = kelly(0.56, 0.51)
f_nofee = 0.56 - (1 - 0.56) / ((1 - 0.51) / 0.51)
print("f* fee-adj (q=.56,p=.51):", round(f_full, 4), " claimed 0.0688;  no-fee:", round(f_nofee, 4), " claimed 0.102")

# --- bootstrap sizing sim, fixed p=0.51, own code ---
random.seed(123)
GAS = 0.004
STRATS = {"flat50": ("flat", 50.0), "kelly_q": ("frac", f_full/4),
          "kelly_h": ("frac", f_full/2), "kelly_f": ("frac", f_full)}

def run_path(seq, mode, val, pfill, b0=1000.0):
    B, peak, mdd = b0, b0, 0.0
    cc = cost(pfill)
    for win in seq:
        stake = min(val, B) if mode == "flat" else val * B
        if stake <= 0 or B <= 1.0:
            stake = 0.0
        pnl = (stake / cc - stake) if win else -stake
        B += pnl - (GAS if stake > 0 else 0)
        if B > peak: peak = B
        d = (peak - B) / peak
        if d > mdd: mdd = d
    return B, mdd

def boot(rows, pfill, nboot=1500):
    blk = {}
    for s in rows:
        blk.setdefault(s[0] // 3600, []).append(s)
    blks = [blk[k] for k in sorted(blk)]
    out = {k: {"tw": [], "dd": []} for k in STRATS}
    for _ in range(nboot):
        seq = []
        for _ in range(len(blks)):
            for s in random.choice(blks):
                w = s[2]
                if s[3] and random.random() < 0.11:
                    w = 1 - w
                seq.append(w)
        for k, (mode, val) in STRATS.items():
            twv, ddv = run_path(seq, mode, val, pfill)
            out[k]["tw"].append(twv); out[k]["dd"].append(ddv)
    res = {}
    for k in STRATS:
        tw = sorted(out[k]["tw"]); dd = sorted(out[k]["dd"]); m = len(tw)
        res[k] = {"tw_med": tw[m//2], "dd_med": dd[m//2], "dd_p95": dd[int(.95*m)],
                  "p_below_500": sum(1 for x in tw if x < 500)/m,
                  "p_loss": sum(1 for x in tw if x < 1000)/m}
    return res

claim = {"flat50": (4333, .409, .935, .041), "kelly_q": (2752, .278, .438, .001),
         "kelly_h": (5799, .498, None, None), "kelly_f": (11510, .791, None, None)}
res = boot(te_g, 0.51)
print("\nTEST p=0.51 fixed-fill sim (mine vs claimed):")
for k, v in res.items():
    cl = claim[k]
    print(f" {k:8s} med={v['tw_med']:8.0f} (cl {cl[0]})  ddMed={v['dd_med']:.3f} (cl {cl[1]})"
          f"  ddP95={v['dd_p95']:.3f}  P(<500)={v['p_below_500']:.4f}  P(loss)={v['p_loss']:.4f}")

res_tr = boot(tr_g, 0.51)
print("\nTRAIN p=0.51 (overbet stress; claimed kelly_f med ~$1, P(<500)=.985; kelly_q med ~$381):")
for k, v in res_tr.items():
    print(f" {k:8s} med={v['tw_med']:8.1f} ddMed={v['dd_med']:.3f} P(<500)={v['p_below_500']:.4f}")

json.dump({"train_gated": wr(tr_g), "test_gated": wr(te_g), "f_full": f_full,
           "TEST_p51": res, "TRAIN_p51": res_tr},
          open(os.path.join(V, "repro_results.json"), "w"), indent=1)
