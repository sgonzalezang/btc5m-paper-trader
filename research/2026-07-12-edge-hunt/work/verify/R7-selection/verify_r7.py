#!/usr/bin/env python3
"""Adversarial verification of finding R7 (gate increment null + retention conformance).

Parts:
 A) Recompute the live gate increment inside reversal_v2's own fills (claim: -2.57c, p=0.79).
 B) Convention check (merge-agent flaw): bot-logged eff6/cnt12 (33 measure f-records +
    7 gate-rejected reversal_v2 rows from flagship/results.json) vs candle recomputation
    under BOTH the bot convention and the deploy_spec open-to-open convention.
 C) Retention recomputation across a grid of conventions x windows: does ANY plausible
    convention put retention back inside [0.40,0.70] for the deployed A=0.10/B=6 gate?
    Plus A=0.32/B=6 retention to test the band-anchor hypothesis.
 D) TEST-increment sanity recompute (claim p~=0.06) + selection-contamination note.
Stdlib only.
"""
import json, math, random, datetime

random.seed(20260712)
D = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data"
W = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work"
IVL = 300

def utc(ts): return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime("%m-%d %H:%M")
def ts(s):  # "2026-07-10 16:55"
    return int(datetime.datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=datetime.timezone.utc).timestamp())

trades = json.load(open(f"{D}/trades_unified.json"))
state  = json.load(open(f"{D}/state_extract.json"))
flag   = json.load(open(f"{W}/flagship/results.json"))
cb     = json.load(open(f"{D}/cb5m.json"))

# candle maps
T = cb["t"]; O = cb["o"]; C = cb["c"]
idx = {t: i for i, t in enumerate(T)}
def contiguous(t0, k):
    return all((t0 - IVL*j) in idx for j in range(1, k+1))

def rets_bot(t0):
    """bot convention: per-interval (close-open)/open, intervals t0-13..t0-1"""
    return {t0-IVL*k: (C[idx[t0-IVL*k]]-O[idx[t0-IVL*k]])/O[idx[t0-IVL*k]] for k in range(1,14)}

def rets_o2o(t0):
    """deploy_spec convention: open-to-open (o[t+1]-o[t])/o[t]"""
    out = {}
    for k in range(1,14):
        t = t0-IVL*k
        t_next = t+IVL
        if t_next not in idx: return None
        out[t] = (O[idx[t_next]]-O[idx[t]])/O[idx[t]]
    return out

def gate(need, t0, conv_eff="incl", conv_cnt="excl", A=0.10, B=6):
    last6 = [need[t0-IVL*k] for k in range(6,1-1,-1)][:6] if conv_eff=="incl" else \
            [need[t0-IVL*k] for k in range(7,2-1,-1)][:6]
    # incl: intervals t0-6IVL..t0-IVL (trigger=t0-IVL included); excl: t0-7IVL..t0-2IVL
    den = sum(abs(r) for r in last6)
    net = 1.0
    for r in last6: net *= (1.0+r)
    eff6 = abs(net-1.0)/den if den>0 else 1.0
    ks = range(2,14) if conv_cnt=="excl" else range(1,13)
    cnt12 = sum(1 for k in ks if abs(need[t0-IVL*k]) >= 0.0012)
    return (eff6 >= A and cnt12 <= B), round(eff6,4), cnt12

def gate_o2o_ratio(need, t0, A=0.10, B=6):
    """deploy_spec eff6: |o[i]-o[i-6]|/sum|moves| (net displacement ratio, additive)"""
    last6 = [need[t0-IVL*k] for k in range(6,0,-1)]
    den = sum(abs(r) for r in last6)
    # additive ratio using compounded displacement equivalent: use sum of rets as approx of net
    net = 1.0
    for r in last6: net *= (1.0+r)
    eff6 = abs(net-1.0)/den if den>0 else 1.0
    cnt12 = sum(1 for k in range(2,14) if abs(need[t0-IVL*k]) >= 0.0012)
    return (eff6 >= A and cnt12 <= B), eff6, cnt12

results = {}

# ---------------- A) live gate increment inside reversal_v2 fills ----------------
p0, p1 = ts("2026-07-10 16:55"), ts("2026-07-13 03:10")
gate_t0 = set()
for tr in trades:
    if tr["eng"] in ("impulse_v2","impulse50"):
        gate_t0.add(tr["t0"])
for m in state["measure"]:
    gate_t0.add(m["t0"])

rv = [tr for tr in trades if tr["eng"]=="reversal_v2" and tr.get("result") in ("win","loss")
      and p0 <= tr["t0"] <= p1]
ps  = lambda tr: 100.0*tr["pnl"]/tr["shares"]
grp_pass = [ps(tr) for tr in rv if tr["t0"] in gate_t0]
grp_rej  = [ps(tr) for tr in rv if tr["t0"] not in gate_t0]
rej_rows = [tr for tr in rv if tr["t0"] not in gate_t0]

def mean(x): return sum(x)/len(x) if x else float("nan")
obs = mean(grp_pass) - mean(grp_rej)
pool = grp_pass + grp_rej
n1 = len(grp_pass)
cnt = 0; NP = 20000
for _ in range(NP):
    random.shuffle(pool)
    d = mean(pool[:n1]) - mean(pool[n1:])
    if abs(d) >= abs(obs) - 1e-12: cnt += 1
perm_p = cnt/NP
# bootstrap CI on the increment (unpaired, simple resample within groups)
boots = []
for _ in range(4000):
    a = [random.choice(grp_pass) for _ in grp_pass]
    b = [random.choice(grp_rej) for _ in grp_rej]
    boots.append(mean(a)-mean(b))
boots.sort()
ci90 = (boots[int(0.05*len(boots))], boots[int(0.95*len(boots))])

results["A_live_increment"] = dict(
    n_pass=len(grp_pass), n_rej=len(grp_rej),
    ps_pass_c=round(mean(grp_pass),2), ps_rej_c=round(mean(grp_rej),2),
    increment_c=round(obs,2), perm_p_two_sided=round(perm_p,4),
    increment_ci90_c=[round(ci90[0],2), round(ci90[1],2)],
    claimed=dict(n_pass=34,n_rej=7,ps_pass=-7.79,ps_rej=-5.21,inc=-2.57,p=0.79))

# ---------------- B) convention check vs bot-logged gate decisions ----------------
recs = [m for m in state["measure"] if "f" in m]
rej7 = flag["gate_rejected_verification"]["rows"]
comp = dict(n_pass_logged=len(recs), n_rej_logged=len(rej7),
            eff6_absdiff_max=0.0, cnt12_mismatch=0, decision_mismatch_bot_conv=0,
            decision_mismatch_o2o_conv=0, rows_checked=0, skipped_no_candles=0)
for m in recs + [dict(t0=r["t0"], f=dict(eff6=r["eff6"], cnt12=r["cnt12"]), _rej=True) for r in rej7]:
    t0 = m["t0"]
    if not contiguous(t0, 14):
        comp["skipped_no_candles"] += 1; continue
    need = rets_bot(t0)
    ok_b, e_b, c_b = gate(need, t0)
    nd2 = rets_o2o(t0)
    ok_o = None
    if nd2: ok_o, e_o, c_o = gate(nd2, t0)
    logged_e, logged_c = m["f"]["eff6"], m["f"]["cnt12"]
    expect_pass = not m.get("_rej", False)
    comp["rows_checked"] += 1
    comp["eff6_absdiff_max"] = max(comp["eff6_absdiff_max"], abs(e_b - logged_e))
    if c_b != logged_c: comp["cnt12_mismatch"] += 1
    if ok_b != expect_pass: comp["decision_mismatch_bot_conv"] += 1
    if ok_o is not None and ok_o != expect_pass: comp["decision_mismatch_o2o_conv"] += 1
comp["eff6_absdiff_max"] = round(comp["eff6_absdiff_max"], 4)
results["B_convention_check"] = comp

# ---------------- C) retention grid: conventions x windows x params ----------------
windows = {
 "live_0710_0713": (p0, p1),
 "last21d":        (ts("2026-06-22 03:10"), ts("2026-07-13 03:10")),
 "TEST_0626_0713": (ts("2026-06-26 00:00"), ts("2026-07-13 03:40")),
 "TRAIN_0511_0625":(ts("2026-05-11 00:00"), ts("2026-06-26 00:00")),
}
convs = {
 "bot(c-o,inclEff,exclCnt)":  ("bot","incl","excl"),
 "o2o,inclEff,exclCnt":       ("o2o","incl","excl"),
 "bot,exclEff,exclCnt":       ("bot","excl","excl"),
 "bot,inclEff,inclCnt":       ("bot","incl","incl"),
 "o2o,exclEff,inclCnt":       ("o2o","excl","incl"),
}
params = {"A010_B6": (0.10,6), "A032_B6": (0.32,6)}
grid = {}
for wname,(w0,w1) in windows.items():
    grid[wname] = {}
    for cname,(src,ce,cc) in convs.items():
        for pname,(A,B) in params.items():
            n_trig=0; n_gated=0
            for t0 in T:
                if not (w0 <= t0 <= w1): continue
                if not contiguous(t0,14): continue
                need = rets_bot(t0) if src=="bot" else rets_o2o(t0)
                if need is None: continue
                trig = abs(need[t0-IVL]) >= 0.0012
                if not trig: continue
                ok,_,_ = gate(need, t0, ce, cc, A, B)
                n_trig += 1; n_gated += ok
            grid[wname][f"{cname}|{pname}"] = dict(n=n_trig, gated=n_gated,
                retention=round(n_gated/n_trig,4) if n_trig else None)
results["C_retention_grid"] = grid

# live-window retention z-test vs TEST-wide baseline (bot conv, A010)
lw = grid["live_0710_0713"]["bot(c-o,inclEff,exclCnt)|A010_B6"]
tw = grid["TEST_0626_0713"]["bot(c-o,inclEff,exclCnt)|A010_B6"]
p_hat, p_base, n = lw["retention"], tw["retention"], lw["n"]
z = (p_hat-p_base)/math.sqrt(p_base*(1-p_base)/n) if n else None
results["C_live_vs_test_z"] = dict(live=p_hat, n=n, test_baseline=p_base, z=round(z,2))

# ---------------- D) TEST increment sanity (fixed p=0.51 fill) ----------------
BE = 0.527493
w0,w1 = windows["TEST_0626_0713"]
rows = []  # (hourblock, gated, win)
for t0 in T:
    if not (w0 <= t0 <= w1): continue
    if not contiguous(t0,14) or (t0+IVL) not in idx: continue
    need = rets_bot(t0)
    if abs(need[t0-IVL]) < 0.0012: continue
    ok,_,_ = gate(need, t0)
    side_up = need[t0-IVL] < 0          # fade the move
    mv = O[idx[t0+IVL]] - O[idx[t0]]
    if mv == 0: continue
    win = (mv > 0) == side_up
    rows.append((t0//3600, ok, 1 if win else 0))
g = [r for r in rows if r[1]]; x = [r for r in rows if not r[1]]
wr_g = mean([r[2] for r in g]); wr_x = mean([r[2] for r in x])
inc_obs = (wr_g - wr_x)*100
# 1h-block bootstrap for the increment
from collections import defaultdict
blocks = defaultdict(list)
for r in rows: blocks[r[0]].append(r)
bkeys = list(blocks)
cnt_le0 = 0; NB = 4000
for _ in range(NB):
    gs=[]; xs=[]
    for _ in bkeys:
        for r in blocks[random.choice(bkeys)]:
            (gs if r[1] else xs).append(r[2])
    if not gs or not xs: continue
    if mean(gs)-mean(xs) <= 0: cnt_le0 += 1
results["D_test_increment"] = dict(
    n_gated=len(g), n_rej=len(x), wr_gated=round(wr_g,4), wr_rej=round(wr_x,4),
    increment_c=round(inc_obs,2), block_boot_p_le_0=round(cnt_le0/NB,4),
    gated_ev_c=round((wr_g-BE)*100,2),
    note="fixed 0.51 fill; ties excluded; a3 claimed +4.69c p=0.0625 on its trigger set")

json.dump(results, open(f"{W}/verify/R7-selection/results.json","w"), indent=1)
print(json.dumps(results, indent=1))
