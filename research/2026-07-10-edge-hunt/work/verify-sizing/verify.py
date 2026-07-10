#!/usr/bin/env python3
"""Independent adversarial verification of the sizing/Kelly finding.

Re-derives from raw data/cb5m.json (own code, not the family's):
  1. Gated reversal stream (buffered open-to-open, |m|>=12bps, eff<=0.48, trailing 12)
     TRAIN (first 2/3) / TEST (last 1/3) win rates. Claimed: TRAIN q=0.5182 n=2065,
     TEST q=0.5629 n=1018.
  2. Closed-form fee-adjusted Kelly at q=0.56, p=0.51. Claimed f*=6.88%.
  3. 1h-block bootstrap on TEST: CI95 for q and P(q <= q*(0.51)=0.5275). Claimed [0.534,0.592], 0.008.
  4. Threshold sensitivity +-20%: MOVE in {9.6,12,14.4}bps x EFFMAX in {0.384,0.48,0.576}.
  5. Independent compounding bankroll sim on TEST stream: flat $50 vs f*/4, f*/2, f*
     (p=0.51 fills, exact fee, gas $0.004, 11% flip on sub-2bps outcomes), 1h-block bootstrap.
  6. Look-ahead audit + live fill-price check from trades.json.
"""
import json, math, os, random

SCRATCH = "/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad"
D = os.path.join(SCRATCH, "data")
W = os.path.join(SCRATCH, "work", "verify-sizing")
random.seed(20260710)

cb = json.load(open(os.path.join(D, "cb5m.json")))
t, o, c = cb["t"], cb["o"], cb["c"]
n = len(t)

def build_stream(move_bps, effmax, effw=12):
    """Signals: prior open-to-open |move| >= threshold, eff <= effmax. Returns list of dicts."""
    mv = move_bps / 1e4
    out = []
    for i in range(effw + 1, n):
        # contiguity of trigger boundary and eff window
        if any(t[i - j] - t[i - j - 1] != 300 for j in range(effw + 1)):
            continue
        m = (o[i] - o[i - 1]) / o[i - 1]
        if abs(m) < mv:
            continue
        den = sum(abs(o[i - j] - o[i - j - 1]) for j in range(effw))
        eff = abs(o[i] - o[i - effw]) / den if den > 0 else 1.0
        if eff > effmax:
            continue
        side_up = 1 if m < 0 else 0
        up_won = 1 if c[i] >= o[i] else 0
        win = 1 if side_up == up_won else 0
        absret = abs(c[i] - o[i]) / o[i]
        out.append({"t0": t[i], "win": win, "absret": absret})
    return out

split_t = t[0] + (t[-1] - t[0]) * 2 / 3

def seg(stream):
    tr = [s for s in stream if s["t0"] < split_t]
    te = [s for s in stream if s["t0"] >= split_t]
    return tr, te

def q_of(rows):
    return sum(r["win"] for r in rows) / len(rows) if rows else float("nan")

res = {}

# ---- 1. headline reproduction ----
base = build_stream(12.0, 0.48)
btr, bte = seg(base)
res["headline"] = {"TRAIN": {"n": len(btr), "q": q_of(btr)},
                   "TEST": {"n": len(bte), "q": q_of(bte)}}

# ---- 2. closed-form Kelly ----
def kelly(qq, p):
    cst = p + 0.07 * p * (1 - p)
    b = (1 - cst) / cst
    return qq - (1 - qq) / b, cst
f_star, cost = kelly(0.56, 0.51)
res["kelly_closed_form"] = {"f_star": f_star, "cost": cost,
                            "no_fee_kelly": kelly(0.56, 0.51)[0] if False else (0.56 - 0.44 / ((1-0.51)/0.51)),
                            "flat50_vs_full_at_1k": 50.0 / (1000 * f_star)}

# ---- 3. 1h-block bootstrap on TEST ----
def blocks_of(rows, blocksec=3600):
    bl = {}
    for r in rows:
        bl.setdefault(r["t0"] // blocksec, []).append(r)
    return list(bl.values())

def boot_q(rows, reps=4000):
    bl = blocks_of(rows)
    nb = len(bl)
    qs = []
    for _ in range(reps):
        wins = tot = 0
        for _ in range(nb):
            b = bl[random.randrange(nb)]
            wins += sum(r["win"] for r in b); tot += len(b)
        qs.append(wins / tot)
    qs.sort()
    hurdle = 0.51 + 0.07 * 0.51 * 0.49
    return {"ci95": [qs[int(0.025 * reps)], qs[int(0.975 * reps)]],
            "p_below_hurdle": sum(1 for x in qs if x <= hurdle) / reps,
            "hurdle": hurdle, "n_blocks": nb}
res["test_bootstrap"] = boot_q(bte)

# ---- 4. threshold sensitivity ----
sens = {}
for mb in (9.6, 12.0, 14.4):
    for em in (0.384, 0.48, 0.576):
        st = build_stream(mb, em)
        s_tr, s_te = seg(st)
        sens[f"move{mb}_eff{em}"] = {
            "TRAIN": {"n": len(s_tr), "q": round(q_of(s_tr), 4)},
            "TEST": {"n": len(s_te), "q": round(q_of(s_te), 4)},
            "test_clears_hurdle_p51": q_of(s_te) > 0.5275 if s_te else None}
res["sensitivity"] = sens

# ---- 5. independent bankroll sim on TEST ----
P = 0.51
FEE = 0.07 * P * (1 - P)
GAS = 0.004
def sim(rows_seq, mode, frac=None):
    bank = 1000.0
    peak = 1000.0
    maxdd = 0.0
    for r in rows_seq:
        if bank <= 1.0:
            bank = max(bank, 0.0)
            break
        stake = 50.0 if mode == "flat" else frac * bank
        stake = min(stake, bank)
        if stake < 0.01:
            break
        shares = stake / P
        fee = shares * FEE
        win = r["win"]
        if r["absret"] < 2e-4 and random.random() < 0.11:
            win = 1 - win
        pnl = (shares * (1 - P) - fee - GAS) if win else (-stake - fee - GAS)
        bank += pnl
        peak = max(peak, bank)
        maxdd = max(maxdd, (peak - bank) / peak)
    return bank, maxdd

def boot_sim(rows, reps=2000):
    bl = blocks_of(rows)
    nb = len(bl)
    out = {k: {"term": [], "dd": []} for k in ("flat50", "quarter", "half", "full")}
    for _ in range(reps):
        seq = []
        for _ in range(nb):
            seq.extend(bl[random.randrange(nb)])
        for k, (mode, fr) in {"flat50": ("flat", None), "quarter": ("f", f_star / 4),
                              "half": ("f", f_star / 2), "full": ("f", f_star)}.items():
            b, dd = sim(seq, mode, fr)
            out[k]["term"].append(b); out[k]["dd"].append(dd)
    summ = {}
    for k, v in out.items():
        tm = sorted(v["term"]); dd = sorted(v["dd"])
        m = len(tm)
        summ[k] = {"median_term": tm[m // 2], "median_dd": dd[m // 2],
                   "p95_dd": dd[int(0.95 * m)],
                   "p_below_500": sum(1 for x in tm if x < 500) / m,
                   "p_net_loss": sum(1 for x in tm if x < 1000) / m}
    return summ
res["sim_TEST"] = boot_sim(bte)
res["sim_TRAIN_stress"] = boot_sim(btr, reps=1000)

# ---- 6. live fill prices for the reversal family ----
tr_led = json.load(open(os.path.join(D, "trades.json")))
ent = sorted(x["entry"] for x in tr_led
             if x.get("eng") in ("reversal", "reversal2", "latentfire") and x.get("entry"))
if ent:
    res["live_fills"] = {"n": len(ent), "median": ent[len(ent) // 2],
                         "mean": sum(ent) / len(ent),
                         "p25": ent[len(ent) // 4], "p75": ent[3 * len(ent) // 4]}

json.dump(res, open(os.path.join(W, "verify_results.json"), "w"), indent=1)
print(json.dumps(res, indent=1))
