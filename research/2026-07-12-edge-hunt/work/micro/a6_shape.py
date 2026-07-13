"""A6: pre-trigger 1m microstructure shape. Does the SHAPE of the prior-interval 12bps move
(monotone drift vs single spike, early vs late) separate winners from losers for the
contrarian trade — beyond entry price?

No look-ahead: all features use 1m opens in [t0-300, t0], complete strictly before entry
(entrySec >= 0; the trigger itself needs o(t0), known at t0).

Design:
  TRAIN = cb1m candle simulation Jun 26 -> Jul 7 01:00 UTC (pre-ledger). Contrarian signal on
  |prior open-to-open move| >= 12bps; outcome = o(t0+300) >= o(t0) (tie Up), gross q only.
  Feature scan (K = 8 candidate splits, counted) on TRAIN delta-q.
  TEST = the live reversal-family ledger Jul 7-13 (deduped by t0), realized EV/share after
  the frozen cost model at actual entry prices; 1h-block bootstrap on the split difference.
"""
import json, math, collections, sys
sys.path.insert(0, "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work/micro")
from common import load_trades, mean, fee, block_boot_diff, REV_FAMILY

DATA = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data"
cb = json.load(open(f"{DATA}/cb1m.json"))
om = dict(zip(cb["t"], cb["o"]))

FIRST_TRADE_T0 = 1783386300  # 2026-07-07 01:05 UTC

def features(t0):
    """Five 1m legs of the prior interval; None if not contiguous."""
    ts = [t0 - 300 + 60 * k for k in range(6)]
    if any(t not in om for t in ts):
        return None
    o = [om[t] for t in ts]
    legs = [o[k + 1] - o[k] for k in range(5)]
    R = o[5] - o[0]
    if R == 0:
        return None
    absum = sum(abs(l) for l in legs)
    if absum == 0:
        return None
    sgn = 1 if R > 0 else -1
    maxshare = max(abs(l) for l in legs) / absum
    dircount = sum(1 for l in legs if l * sgn > 0)
    late_frac = legs[4] * sgn / abs(R)     # signed fraction of net move delivered in final minute
    early_frac = legs[0] * sgn / abs(R)
    eff5 = abs(R) / absum                  # 1m-level efficiency of the trigger move
    return dict(maxshare=maxshare, dircount=dircount, late_frac=late_frac,
                early_frac=early_frac, eff5=eff5, prior_bps=abs(R) / o[0] * 1e4)

# ---------- TRAIN: candle sim ----------
train = []
t_min, t_max = cb["t"][0], cb["t"][-1]
t0 = ((t_min + 300) // 300 + 1) * 300
while t0 + 300 <= t_max:
    if t0 < FIRST_TRADE_T0:
        a, b, c = om.get(t0 - 300), om.get(t0), om.get(t0 + 300)
        if a and b and c:
            r = (b - a) / a
            if abs(r) >= 0.0012:
                f = features(t0)
                if f:
                    contrarian_up = r < 0
                    up_won = 1 if c >= b else 0
                    win = up_won if contrarian_up else 1 - up_won
                    train.append(dict(t0=t0, win=win, **f))
    t0 += 300
print(f"TRAIN signals: {len(train)}, base contrarian q = {mean([x['win'] for x in train]):.4f}")

# K=8 pre-registered splits
SPLITS = [
    ("maxshare>=0.5 (spike)", lambda f: f["maxshare"] >= 0.5),
    ("maxshare<0.4 (distributed)", lambda f: f["maxshare"] < 0.4),
    ("dircount>=4 (monotone)", lambda f: f["dircount"] >= 4),
    ("dircount<=2 (choppy path)", lambda f: f["dircount"] <= 2),
    ("late_frac>=0.5 (late spike)", lambda f: f["late_frac"] >= 0.5),
    ("late_frac<0.2 (early move)", lambda f: f["late_frac"] < 0.2),
    ("eff5>=0.8 (clean drift)", lambda f: f["eff5"] >= 0.8),
    ("early_frac>=0.5 (early spike)", lambda f: f["early_frac"] >= 0.5),
]

def scan(rows, wkey="win"):
    out = {}
    base = mean([x[wkey] for x in rows])
    for name, pred in SPLITS:
        g1 = [x for x in rows if pred(x)]
        g0 = [x for x in rows if not pred(x)]
        if len(g1) < 20 or len(g0) < 20:
            out[name] = dict(n1=len(g1), note="thin")
            continue
        q1, q0 = mean([x[wkey] for x in g1]), mean([x[wkey] for x in g0])
        se = math.sqrt(q1 * (1 - q1) / len(g1) + q0 * (1 - q0) / len(g0))
        out[name] = dict(n1=len(g1), n0=len(g0), q1=round(q1, 4), q0=round(q0, 4),
                         dq=round(q1 - q0, 4), z=round((q1 - q0) / se, 2) if se else None)
    return dict(base_q=round(base, 4), n=len(rows), splits=out)

res = {"K_splits_scanned": len(SPLITS)}
res["train_scan"] = scan(train)

# ---------- TEST 1: candle sim on ledger period (gross q, sanity) ----------
test_c = []
t0 = FIRST_TRADE_T0 // 300 * 300
while t0 + 300 <= t_max:
    a, b, c = om.get(t0 - 300), om.get(t0), om.get(t0 + 300)
    if a and b and c:
        r = (b - a) / a
        if abs(r) >= 0.0012:
            f = features(t0)
            if f:
                contrarian_up = r < 0
                up_won = 1 if c >= b else 0
                win = up_won if contrarian_up else 1 - up_won
                test_c.append(dict(t0=t0, win=win, **f))
    t0 += 300
res["test_candles_scan"] = scan(test_c)

# ---------- TEST 2: the live reversal-family ledger, realized EV ----------
T = [x for x in load_trades() if x["eng"] in REV_FAMILY]
# dedupe by t0: engines shadow one another on the same signal; prefer widest-cap engine record
pref = {"reversal": 0, "reversal2": 1, "reversal_v2": 2, "impulse50": 3, "impulse_v2": 4, "latentfire": 5}
by_t0 = {}
for x in T:
    k = x["t0"]
    if k not in by_t0 or pref.get(x["eng"], 9) < pref.get(by_t0[k]["eng"], 9):
        by_t0[k] = x
led = []
for x in by_t0.values():
    f = features(x["t0"])
    if f:
        led.append(dict(win=int(x["_w"]), evps=x["_evps"], entry=x["entry"], blk=x["_blk"], eng=x["eng"], **f))
res["ledger_n_unique_t0"] = len(led)
res["ledger_scan_q"] = scan(led)

# EV-based test for each split on ledger, with block bootstrap
ev_tests = {}
for name, pred in SPLITS:
    g1 = [x for x in led if pred(x)]
    g0 = [x for x in led if not pred(x)]
    if len(g1) < 15 or len(g0) < 15:
        ev_tests[name] = dict(n1=len(g1), note="thin")
        continue
    d, lo, hi, p = block_boot_diff([x["evps"] for x in g1], [x["blk"] for x in g1],
                                   [x["evps"] for x in g0], [x["blk"] for x in g0])
    ev_tests[name] = dict(n1=len(g1), n0=len(g0),
                          entry1=round(mean([x["entry"] for x in g1]), 4),
                          entry0=round(mean([x["entry"] for x in g0]), 4),
                          ev1_c=round(100 * mean([x["evps"] for x in g1]), 2),
                          ev0_c=round(100 * mean([x["evps"] for x in g0]), 2),
                          diff_c=round(100 * d, 2), ci95_c=[round(100 * lo, 2), round(100 * hi, 2)],
                          p_diff_le0=round(p, 4))
res["ledger_ev_tests"] = ev_tests

json.dump(res, open("/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work/micro/a6_shape.json", "w"), indent=1)
print(json.dumps(res, indent=1))
