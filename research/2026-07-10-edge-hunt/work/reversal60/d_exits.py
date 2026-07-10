#!/usr/bin/env python3
"""(d) Hold-to-close vs timed exits at +2/+3/+4 min for the 12bps reversal.
Token value at exit from a probit fair-value model P(Up)=Phi(x/sigma_rem),
sigma from trailing 12 5m intervals; model validated against pm_prices_sample
p60/p150. Exit pays second fee + 1c spread. cb1m overlap (~14d, all inside TEST).
Also: empirical sell-at-p150 vs hold check on the 49 pm signal markets, and
cap-conditional entry EV (only enter if contrarian cost <= cap) at p20.
Output: d_exits.json"""
import json, math, statistics as st

S = "/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad"
cb5 = json.load(open(f"{S}/data/cb5m.json"))
cb1 = json.load(open(f"{S}/data/cb1m.json"))
t5, o5, c5 = cb5["t"], cb5["o"], cb5["c"]
open1 = {tt: oo for tt, oo in zip(cb1["t"], cb1["o"])}
def fee(p): return 0.07*p*(1-p)
def Phi(z): return 0.5*(1+math.erf(z/math.sqrt(2)))

# sigma per interval: trailing 12 completed 5m intervals, mean |c-o|/o * sqrt(pi/2)
sig5 = [None]*len(t5)
for i in range(12, len(t5)):
    m = st.mean(abs(c5[j]-o5[j])/o5[j] for j in range(i-12, i))
    sig5[i] = m*math.sqrt(math.pi/2)

# ---- model validation vs pm_prices_sample ----
pm = json.load(open(f"{S}/data/pm_prices_sample.json"))
tix5 = {tt: i for i, tt in enumerate(t5)}
errs = {"p60": [], "p150": []}
for m_ in pm:
    i = tix5.get(m_["t0"])
    if i is None or i < 12 or sig5[i] is None: continue
    for snap, s in [("p60", 60), ("p150", 150)]:
        if s % 60 == 0:
            P = open1.get(m_["t0"]+s)
        else:  # interpolate mid-candle
            a, b = open1.get(m_["t0"]+120), open1.get(m_["t0"]+180)
            P = (a+b)/2 if a and b else None
        if P is None: continue
        x = (P-o5[i])/o5[i]
        pup = Phi(x/(sig5[i]*math.sqrt((300-s)/300)))
        errs[snap].append(pup - m_[snap])
val = {}
for k, e in errs.items():
    rmse = math.sqrt(st.mean(x*x for x in e))
    val[k] = dict(n=len(e), bias=st.mean(e), rmse=rmse)
    print(f"model vs {k}: n={len(e)} bias={st.mean(e):+.4f} rmse={rmse:.4f}")

# ---- exit simulation over cb1m overlap ----
P0 = 0.51; cost0 = P0 + fee(P0)
start_t = cb1["t"][0]
res = {"validation": val, "entry": P0}
sims = {120: [], 180: [], 240: [], "hold": []}
n_sig = 0
for i in range(12, len(t5)):
    if t5[i] < start_t or sig5[i] is None: continue
    mvb = (o5[i]-o5[i-1])/o5[i-1]*1e4
    if abs(mvb) < 12: continue
    side_up = mvb < 0
    win = (1 if c5[i] >= o5[i] else 0) if side_up else (0 if c5[i] >= o5[i] else 1)
    ok = True
    vals = {}
    for s in (120, 180, 240):
        P = open1.get(t5[i]+s)
        if P is None: ok = False; break
        x = (P-o5[i])/o5[i]
        pup = Phi(x/(sig5[i]*math.sqrt((300-s)/300)))
        v = pup if side_up else 1-pup
        ps = max(0.01, v-0.01)                 # sell at 1c inside fair
        vals[s] = ps - fee(ps) - cost0
    if not ok: continue
    n_sig += 1
    for s in (120, 180, 240): sims[s].append(vals[s])
    sims["hold"].append(win - cost0)

print(f"\n== exit sim, cb1m overlap (n={n_sig} signals at 12bps, all TEST-period) ==")
for k in ["hold", 120, 180, 240]:
    xs = sims[k]
    lbl = "hold" if k == "hold" else f"+{k//60}min"
    m = st.mean(xs); sd = st.pstdev(xs)
    res[f"exit_{lbl}"] = dict(n=len(xs), mean=m, sd=sd)
    print(f"{lbl:>6}: mean net/share {m:+.4f}  sd {sd:.3f}")

# ---- empirical: sell at p150 vs hold, pm signal markets ----
print("\n== empirical pm-sample check (sell contrarian at p150 snapshot vs hold) ==")
hold_v, sell_v = [], []
for m_ in pm:
    i = tix5.get(m_["t0"])
    if i is None or i == 0: continue
    mvb = (o5[i]-o5[i-1])/o5[i-1]*1e4
    if abs(mvb) < 12: continue
    side_up = mvb < 0
    win = m_["up_won"] if side_up else 1-m_["up_won"]
    v150 = m_["p150"] if side_up else 1-m_["p150"]
    ps = max(0.01, v150-0.01)
    hold_v.append(win - cost0)
    sell_v.append(ps - fee(ps) - cost0)
print(f"n={len(hold_v)}  hold {st.mean(hold_v):+.4f}/share  sell@p150 {st.mean(sell_v):+.4f}/share")
res["pm_check"] = dict(n=len(hold_v), hold=st.mean(hold_v), sell_p150=st.mean(sell_v))

# ---- cap-conditional entry (bot-style): enter at p20 only if contrarian cost<=cap ----
print("\n== cap-conditional entry at p20 (+1c slip), pm signal markets, thr=12 ==")
caps = {}
for cap in [0.51, 0.53, 0.55, 0.58]:
    evs = []
    for m_ in pm:
        i = tix5.get(m_["t0"])
        if i is None or i == 0: continue
        mvb = (o5[i]-o5[i-1])/o5[i-1]*1e4
        if abs(mvb) < 12: continue
        side_up = mvb < 0
        cost = m_["p20"] if side_up else 1-m_["p20"]
        if cost > cap: continue
        win = m_["up_won"] if side_up else 1-m_["up_won"]
        ps = min(0.99, cost+0.01)
        evs.append(win - ps - fee(ps))
    caps[str(cap)] = dict(n=len(evs), ev=st.mean(evs) if evs else None)
    if evs: print(f"cap<={cap:.2f}: n={len(evs):>3} EV/share={st.mean(evs):+.4f}")
res["cap_conditional_p20"] = caps
json.dump(res, open(f"{S}/work/reversal60/d_exits.json","w"), indent=1)
print("saved d_exits.json")
