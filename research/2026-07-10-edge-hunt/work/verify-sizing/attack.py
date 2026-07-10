#!/usr/bin/env python3
"""Adversarial re-splits: weekly folds, first/last thirds, Kaufman-efficiency regimes,
Kelly-parameter stability across folds, and per-fold flat50 vs quarter-Kelly outcomes
(actual chronological sequences, no bootstrap) at p=0.51 fills.
"""
import json, math, random, os

SCRATCH = "/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad"
D = os.path.join(SCRATCH, "data")
V = os.path.join(SCRATCH, "work", "verify-sizing")

cb = json.load(open(os.path.join(D, "cb5m.json")))
t, o, c = cb["t"], cb["o"], cb["c"]
n = len(t)

sig = []
for i in range(13, n):
    if t[i] - t[i-1] != 300 or any(t[i-j] - t[i-j-1] != 300 for j in range(12)):
        continue
    m = (o[i] - o[i-1]) / o[i-1]
    if abs(m) < 0.0012:
        continue
    den = sum(abs(o[i-j] - o[i-j-1]) for j in range(12))
    eff = abs(o[i] - o[i-12]) / den if den > 0 else 1.0
    side_up = 1 if m < 0 else 0
    up_won = 1 if c[i] >= o[i] else 0
    sig.append({"t0": t[i], "eff": eff, "win": 1 if side_up == up_won else 0})

gated = [s for s in sig if s["eff"] <= 0.48]
t0g, t1g = t[0], t[-1]
split_t = t0g + (t1g - t0g) * 2 / 3

P = 0.51
def cost(p): return p + 0.07 * p * (1 - p)
HURDLE = cost(P)                       # 0.5275 break-even q at p=0.51
def kelly(q, p=P):
    cc = cost(p); b = (1 - cc) / cc
    return q - (1 - q) / b

def wr(rows):
    k = len(rows)
    return k, (sum(r["win"] for r in rows) / k if k else float("nan"))

def wilson_lo(w, k, z=1.96):
    if k == 0: return float("nan")
    ph = w / k
    den = 1 + z*z/k
    ctr = ph + z*z/(2*k)
    rad = z * math.sqrt(ph*(1-ph)/k + z*z/(4*k*k))
    return (ctr - rad) / den

GAS = 0.004
def run_seq(rows, mode, val, b0=1000.0):
    B, peak, mdd = b0, b0, 0.0
    cc = cost(P)
    for s in rows:
        stake = min(val, B) if mode == "flat" else val * B
        if stake <= 0 or B <= 1.0: stake = 0.0
        B += ((stake/cc - stake) if s["win"] else -stake) - (GAS if stake > 0 else 0)
        peak = max(peak, B); mdd = max(mdd, (peak - B) / peak)
    return B, mdd

F = kelly(0.56)
out = {"hurdle": HURDLE, "f_full_design": F}

# ---------- weekly folds ----------
print(f"hurdle q*({P}) = {HURDLE:.4f}   design f* = {F:.4f}\n")
print("== WEEKLY folds (gated stream), q, Wilson95 lower bound, fold Kelly f*, actual-seq flat50 vs f*/4 ==")
weeks = {}
for s in gated:
    weeks.setdefault(int((s["t0"] - t0g) // (7*86400)), []).append(s)
wk_rows = []
for wk in sorted(weeks):
    rows = weeks[wk]
    k, q = wr(rows)
    lo = wilson_lo(sum(r["win"] for r in rows), k)
    fk = kelly(q)
    tw_f, dd_f = run_seq(rows, "flat", 50.0)
    tw_q, dd_q = run_seq(rows, "frac", F/4)
    seg = "TEST" if rows[0]["t0"] >= split_t else ("TRAIN" if rows[-1]["t0"] < split_t else "MIX")
    effs = sorted(r["eff"] for r in rows)
    med_eff = effs[len(effs)//2]
    wk_rows.append({"week": wk, "seg": seg, "n": k, "q": round(q,4), "wilson_lo": round(lo,4),
                    "clears_hurdle": q > HURDLE, "fold_kelly": round(fk,4), "med_eff": round(med_eff,3),
                    "flat50_tw": round(tw_f), "flat50_dd": round(dd_f,3),
                    "kq_tw": round(tw_q), "kq_dd": round(dd_q,3)})
    print(f" wk{wk} {seg:5s} n={k:4d} q={q:.4f} lo={lo:.4f} {'CLEAR' if q>HURDLE else 'below'} "
          f"f*={fk:+.4f} medEff={med_eff:.3f} | flat50 tw={tw_f:7.0f} dd={dd_f:.2f} | f*/4 tw={tw_q:7.0f} dd={dd_q:.2f}")
out["weekly"] = wk_rows

# ---------- first/last thirds of full span ----------
print("\n== FIRST/MIDDLE/LAST thirds of full 60d (gated) ==")
thirds = []
for lab, a, b in (("first", 0, 1/3), ("middle", 1/3, 2/3), ("last", 2/3, 1.0)):
    lo_t = t0g + (t1g - t0g) * a; hi_t = t0g + (t1g - t0g) * b
    rows = [s for s in gated if lo_t <= s["t0"] < hi_t or (b == 1.0 and s["t0"] == hi_t)]
    k, q = wr(rows)
    fk = kelly(q)
    thirds.append({"seg": lab, "n": k, "q": round(q,4), "fold_kelly": round(fk,4),
                   "clears": q > HURDLE})
    print(f" {lab:6s} n={k:4d} q={q:.4f} f*={fk:+.4f} {'CLEAR' if q>HURDLE else 'below'}")
out["thirds_full"] = thirds

# ---------- halves of TEST itself ----------
print("\n== TEST split into halves and thirds (gated) ==")
te = [s for s in gated if s["t0"] >= split_t]
te_lo, te_hi = te[0]["t0"], te[-1]["t0"]
sub = []
for lab, a, b in (("T-half1", 0, .5), ("T-half2", .5, 1.0),
                  ("T-third1", 0, 1/3), ("T-third2", 1/3, 2/3), ("T-third3", 2/3, 1.0)):
    lo_t = te_lo + (te_hi - te_lo) * a; hi_t = te_lo + (te_hi - te_lo) * b + 1
    rows = [s for s in te if lo_t <= s["t0"] < hi_t]
    k, q = wr(rows)
    wl = wilson_lo(sum(r["win"] for r in rows), k)
    tw_f, dd_f = run_seq(rows, "flat", 50.0)
    tw_q, dd_q = run_seq(rows, "frac", F/4)
    sub.append({"seg": lab, "n": k, "q": round(q,4), "wilson_lo": round(wl,4), "clears": q > HURDLE,
                "flat50": [round(tw_f), round(dd_f,3)], "kq": [round(tw_q), round(dd_q,3)]})
    print(f" {lab:9s} n={k:4d} q={q:.4f} lo={wl:.4f} {'CLEAR' if q>HURDLE else 'below'} "
          f"| flat50 tw={tw_f:7.0f} dd={dd_f:.2f} | f*/4 tw={tw_q:7.0f} dd={dd_q:.2f}")
out["test_sub"] = sub

# ---------- Kaufman efficiency regimes within gated ----------
print("\n== Efficiency regime segmentation ==")
for seg_lab, rows in (("TRAIN", [s for s in gated if s["t0"] < split_t]), ("TEST", te)):
    effs = sorted(r["eff"] for r in rows)
    t1_, t2_ = effs[len(effs)//3], effs[2*len(effs)//3]
    for lab, f in (("calm(lowEff)", lambda s: s["eff"] <= t1_),
                   ("mid", lambda s: t1_ < s["eff"] <= t2_),
                   ("nearGate(hiEff)", lambda s: s["eff"] > t2_)):
        rr = [s for s in rows if f(s)]
        k, q = wr(rr)
        print(f" {seg_lab} {lab:16s} n={k:4d} q={q:.4f} {'CLEAR' if q>HURDLE else 'below'}")
# trending = ungated (eff>0.48) as would-be trades if gate failed
for seg_lab, lo_t, hi_t in (("TRAIN", t0g, split_t), ("TEST", split_t, t1g+1)):
    rr = [s for s in sig if s["eff"] > 0.48 and lo_t <= s["t0"] < hi_t]
    k, q = wr(rr)
    print(f" {seg_lab} TRENDING(eff>.48) n={k:4d} q={q:.4f} {'CLEAR' if q>HURDLE else 'below'} (excluded by gate)")

# ---------- day-level trend regime: daily |net|/sum ratio ----------
print("\n== Day-regime: gated q on trending days vs calm days (daily Kaufman eff of 5m opens) ==")
days = {}
for i in range(1, n):
    if t[i] - t[i-1] != 300: continue
    d = int((t[i] - t0g) // 86400)
    days.setdefault(d, []).append((o[i-1], o[i]))
day_eff = {}
for d, mv in days.items():
    net = abs(mv[-1][1] - mv[0][0]); den = sum(abs(b-a) for a, b in mv)
    day_eff[d] = net/den if den else 0
de_sorted = sorted(day_eff.values())
med_de = de_sorted[len(de_sorted)//2]
for seg_lab, lo_t, hi_t in (("TRAIN", t0g, split_t), ("TEST", split_t, t1g+1)):
    for lab, f in (("calm days", lambda d: day_eff.get(d, 0) <= med_de),
                   ("trending days", lambda d: day_eff.get(d, 0) > med_de)):
        rr = [s for s in gated if lo_t <= s["t0"] < hi_t and f(int((s["t0"]-t0g)//86400))]
        k, q = wr(rr)
        print(f" {seg_lab} {lab:14s} n={k:4d} q={q:.4f} {'CLEAR' if k and q>HURDLE else 'below'}")

json.dump(out, open(os.path.join(V, "attack_results.json"), "w"), indent=1)
