"""R6 adversarial verification: re-derive the fresh-window drought claim from RAW data.
Independent code (does not import analyst libs). Stdlib only.

Checks:
 A. Candle-based gated/ungated contrarian EV: TRAIN/TEST/FRESH (both boundary variants),
    per-day series, Jul-10-excluded fresh window, daily rank of Jul 10.
 B. Ledger-based: impulse50 / reversal_v2 / impulse_v2 per-share pnl in the fresh window,
    dupes, survivorship (open/pending in window), pnl-vs-frozen-cost-model consistency,
    Jul-10 exclusion.
 C. measure book win rate from state_extract.
 D. Weekly gated EV table replication (SD, negative-week count).
 E. Coinbase-proxy vs Polymarket resolution agreement on overlap (pm_res_3d).
"""
import json, math, random, calendar, time
from collections import Counter, defaultdict

DATA = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data"
DATA10 = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-10-edge-hunt/data"
OUT = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work/verify/R6-integrity"

FEE = 0.07
P = 0.51
COST = P + FEE * P * (1 - P)            # 0.527493 (gas ~0.004c/share ignored, <0.005c)
TEST_START = calendar.timegm((2026, 6, 26, 0, 0, 0))
FRESH_A = 1783685700                     # Jul 10 11:55 UTC (a3 variant)
FRESH_B = calendar.timegm((2026, 7, 10, 15, 5, 0))   # gate_refresh variant
JUL11 = calendar.timegm((2026, 7, 11, 0, 0, 0))
JUL10 = calendar.timegm((2026, 7, 10, 0, 0, 0))

def ts(t): return time.strftime("%m-%d %H:%M", time.gmtime(t))

cb = json.load(open(f"{DATA}/cb5m.json"))
t, o = cb["t"], cb["o"]
n = len(t)
assert all(t[i+1]-t[i] == 300 for i in range(n-1))

# per-interval move r[i] = (o[i+1]-o[i])/o[i]; up[i] = o[i+1] >= o[i]
r = [(o[i+1]-o[i])/o[i] for i in range(n-1)]
up = [o[i+1] >= o[i] for i in range(n-1)]

def boot(trades, reps=4000, seed=7):
    """trades: (t0, ev). 1h-block bootstrap -> mean, ci90, p(mean<=0)."""
    if not trades: return None
    by = defaultdict(list)
    for t0, ev in trades: by[t0//3600].append(ev)
    keys = list(by)
    rng = random.Random(seed)
    mean = sum(e for _, e in trades)/len(trades)
    ms = []
    for _ in range(reps):
        tot = cnt = 0
        for _ in range(len(keys)):
            b = by[keys[rng.randrange(len(keys))]]
            tot += sum(b); cnt += len(b)
        ms.append(tot/cnt if cnt else 0)
    ms.sort()
    return dict(n=len(trades), q=round(sum(1 for _,e in trades if e>0)/len(trades),4),
                ev_c=round(mean*100,2), p_le0=round(sum(1 for m in ms if m<=0)/len(ms),4),
                ci90_c=[round(ms[int(.05*len(ms))]*100,2), round(ms[int(.95*len(ms))-1]*100,2)])

# ---- A. candle triggers, two eff6 conventions ----
def eff_simple(i):   # |net|/sum legs, opens i-6..i (trigger-inclusive)
    den = sum(abs(o[j+1]-o[j]) for j in range(i-6, i))
    return abs(o[i]-o[i-6])/den if den > 0 else 1.0

def eff_comp(i):     # compounded (lib.py form) over r[i-6..i-1]
    den = sum(abs(r[j]) for j in range(i-6, i))
    if den == 0: return 1.0
    net = 1.0
    for j in range(i-6, i): net *= 1+r[j]
    return abs(net-1)/den

trig = []   # (t0, ev, gated_simple, gated_comp)
for i in range(14, n-1):
    if abs(r[i-1]) < 0.0012: continue
    prior_up = r[i-1] > 0
    win = 1 if up[i] != prior_up else 0
    cnt12 = sum(1 for j in range(i-13, i-1) if abs(r[j]) >= 0.0012)
    gs = eff_simple(i) >= 0.10 and cnt12 <= 6
    gc = eff_comp(i) >= 0.10 and cnt12 <= 6
    trig.append((t[i], win - COST, gs, gc))

def W(lo, hi=1 << 62, g=None):
    return [(t0, ev) for t0, ev, gs, gc in trig
            if lo <= t0 < hi and (g is None or (gs if g == "s" else gc))]

A = {}
A["ungated_TEST"] = boot(W(TEST_START))
A["gated_TEST"] = boot(W(TEST_START, g="s"))
A["gated_TRAIN"] = boot(W(0, TEST_START, g="s"))
A["ungated_FRESH_1155"] = boot(W(FRESH_A))
A["gated_FRESH_1155"] = boot(W(FRESH_A, g="s"))
A["gated_FRESH_1155_comp"] = boot(W(FRESH_A, g="c"))
A["ungated_FRESH_1505"] = boot(W(FRESH_B))
A["gated_FRESH_1505"] = boot(W(FRESH_B, g="s"))
# Jul 10 exclusion
A["gated_jul10_only"] = boot(W(JUL10, JUL11, g="s"))
A["ungated_jul10_only"] = boot(W(JUL10, JUL11))
A["gated_jul11_13"] = boot(W(JUL11, g="s"))
A["ungated_jul11_13"] = boot(W(JUL11))
A["gated_fresh1155_excl_jul10"] = boot([x for x in W(FRESH_A, g="s") if not (JUL10 <= x[0] < JUL11)])

# daily gated series + rank of Jul 10
daily = defaultdict(list)
for t0, ev, gs, gc in trig:
    if gs: daily[t0 // 86400].append(ev)
dser = sorted((d, len(v), sum(v)/len(v)*100) for d, v in daily.items() if len(v) >= 3)
jul10_day = JUL10 // 86400
ranked = sorted(dser, key=lambda x: x[2])
A["n_days"] = len(dser)
A["jul10_daily"] = next(({"date": ts(d*86400)[:5], "n": nn, "ev_c": round(e,2),
                          "rank_worst": k+1} for k,(d,nn,e) in enumerate(ranked) if d == jul10_day), None)
A["worst5_days"] = [{"date": ts(d*86400)[:5], "n": nn, "ev_c": round(e,2)} for d, nn, e in ranked[:5]]

# ---- B. ledger ----
tr = json.load(open(f"{DATA}/trades_unified.json"))
dupes = Counter((x["eng"], x["slug"]) for x in tr)
B = {"dup_eng_slug_pairs": sum(1 for v in dupes.values() if v > 1)}
fresh_tr = [x for x in tr if x["t0"] >= FRESH_A]
B["fresh_status"] = dict(Counter(x["status"] for x in fresh_tr))
B["fresh_unsettled_by_eng"] = dict(Counter(x["eng"] for x in fresh_tr if x["status"] != "settled"))

def book(eng, lo, hi=1 << 62):
    s = [x for x in tr if x["eng"] == eng and lo <= x["t0"] < hi
         and x["status"] == "settled" and x.get("result") in ("win", "loss")]
    if not s: return {"n": 0}
    ps = [(x["t0"], x["pnl"]/x["shares"]) for x in s]
    d = boot(ps)
    d["wins"] = sum(1 for x in s if x["result"] == "win")
    d["avg_entry"] = round(sum(x["entry"] for x in s)/len(s), 4)
    return d

for eng in ("impulse50", "reversal_v2", "impulse_v2", "reversal"):
    B[f"{eng}_fresh"] = book(eng, FRESH_A)
    B[f"{eng}_jul11_13"] = book(eng, JUL11)
    B[f"{eng}_jul10"] = book(eng, JUL10, JUL11)

# pnl vs frozen model consistency: pnl/share should = (1-entry-fee) if win, -(entry+fee) if loss
bad = []
for x in tr:
    if x["status"] != "settled" or x.get("result") not in ("win","loss") or x.get("hedge"): continue
    if x["eng"] not in ("impulse50","reversal_v2","impulse_v2","reversal","reversal2"): continue
    p = x["entry"]; fee = 0.07*p*(1-p)
    exp = (1 - p - fee) if x["result"] == "win" else (-(p + fee))
    got = x["pnl"]/x["shares"]
    if abs(got - exp) > 0.005: bad.append((x["eng"], x["slug"], round(exp,4), round(got,4)))
B["pnl_model_mismatch_n"] = len(bad)
B["pnl_model_mismatch_sample"] = bad[:5]

# result-vs-candle cross-check for v3-era engines (uses btcOpen/btcClose in ledger AND candles)
idx = {tt: i for i, tt in enumerate(t)}
mism = []
checked = 0
for x in tr:
    if x["eng"] not in ("impulse50","reversal_v2","impulse_v2") or x["status"] != "settled": continue
    i = idx.get(x["t0"])
    if i is None or i+1 >= n: continue
    checked += 1
    cb_up = o[i+1] >= o[i]
    won = x["result"] == "win"
    side_up = x["side"] == "up"
    if (side_up == cb_up) != won:
        mism.append({"slug": x["slug"], "eng": x["eng"], "side": x["side"], "result": x["result"],
                     "cb_move_bps": round((o[i+1]-o[i])/o[i]*1e4, 2)})
B["ledger_vs_candle_checked"] = checked
B["ledger_vs_candle_mismatch"] = len(mism)
B["mismatch_sample"] = mism[:8]

# ---- C. measure book ----
st = json.load(open(f"{DATA}/state_extract.json"))
meas = st.get("measure") or []
ws = [m.get("win") for m in meas if m.get("win") is not None]
C = {"n_records": len(meas), "n_settled": len(ws), "wr": round(sum(ws)/len(ws), 4) if ws else None}

# ---- D. weekly gated ----
wk = defaultdict(list)
for t0, ev, gs, gc in trig:
    if gs:
        wk[(t0 - calendar.timegm((2026,5,11,0,0,0))) // (7*86400)].append(ev)
Dw = []
for k in sorted(wk):
    v = wk[k]
    Dw.append({"week": k, "start": ts(calendar.timegm((2026,5,11,0,0,0)) + k*7*86400)[:5],
               "n": len(v), "ev_c": round(sum(v)/len(v)*100, 2)})
full = [w for w in Dw if w["n"] >= 50]
evs = [w["ev_c"] for w in full]
mu = sum(evs)/len(evs)
D = {"weeks": Dw, "full_weeks_n": len(full),
     "sd_c": round(math.sqrt(sum((e-mu)**2 for e in evs)/(len(evs)-1)), 2),
     "neg_weeks": sum(1 for e in evs if e < 0),
     "mean_c": round(mu, 2)}

# ---- E. PM resolution vs candle proxy ----
E = {}
try:
    pm = json.load(open(f"{DATA10}/pm_res_3d.json"))
    agree = tot = 0
    dis_small = 0
    for t0, pmu in pm:
        i = idx.get(t0)
        if i is None or i+1 >= n: continue
        tot += 1
        cbu = 1 if o[i+1] >= o[i] else 0
        if cbu == pmu: agree += 1
        elif abs((o[i+1]-o[i])/o[i]) < 0.0004: dis_small += 1
    E = {"n_overlap": tot, "agree": round(agree/tot, 4) if tot else None,
         "disagreements_under_4bps": dis_small,
         "pm_last_t0": ts(max(x[0] for x in pm))}
except Exception as ex:
    E = {"error": str(ex)}

out = {"A_candle": A, "B_ledger": B, "C_measure": C, "D_weekly": D, "E_pm_proxy": E}
json.dump(out, open(f"{OUT}/rederive.json", "w"), indent=1)
print(json.dumps(out, indent=1))
