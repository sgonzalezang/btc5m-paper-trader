"""A3: spread distribution (signals.log bid/ask + measure book), slip sensitivity of the
flagship's +1.5-3c/share estimate, and a limit-at-mid fill-probability breakeven table.

Slip sensitivity method: hold q fixed (backed out so EV=+1.5c and +3.0c at slip=1c on the
flagship's own live fill mix), then recompute EV/share as slip varies. Extra slip enters both
price and fee: EV(s) = q - (ask+s) - 0.07*(ask+s)*(1-(ask+s)).
Limit-at-mid: expected EV per SIGNAL = f * (q_f - m - fee(m)) where m = mid = ask - spread/2,
f = fill prob, q_f = win prob CONDITIONAL on fill. Adverse selection means q_f <= q. We report
the (f, q_f - q) frontier where limit-at-mid beats taker at +1.5c and +3c, using live spreads.
"""
import json, collections, sys
sys.path.insert(0, "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work/micro")
from common import load_trades, mean, fee

res = {}

# ---- 1. spread distribution from signals.log ----
spreads_all, spreads_rev = [], []
by_eng = collections.defaultdict(list)
with open("/Users/sgonzalez/btc5m-paper-trader/bot/signals.log") as fh:
    for line in fh:
        line = line.strip()
        if not line:
            continue
        try:
            j = json.loads(line)
        except Exception:
            continue
        if j.get("ask") is None or j.get("bid") is None:
            continue
        sp = round(j["ask"] - j["bid"], 4)
        if sp < 0:
            continue
        spreads_all.append(sp)
        by_eng[j["engine"]].append(sp)
        if j["engine"] in ("reversal", "reversal2", "reversal_v2", "impulse50", "impulse_v2", "latentfire"):
            spreads_rev.append(sp)

def qtiles(v):
    if not v:
        return None
    s = sorted(v)
    n = len(s)
    def q(p):
        return s[min(int(p*n), n-1)]
    return dict(n=n, p25=q(.25), p50=q(.50), p75=q(.75), p90=q(.90), p95=q(.95), p99=q(.99),
                mean=round(mean(s), 4), frac_le_1c=round(sum(1 for x in s if x <= 0.0101)/n, 4),
                frac_le_2c=round(sum(1 for x in s if x <= 0.0201)/n, 4))

res["spread_signals_all"] = qtiles(spreads_all)
res["spread_signals_revfamily"] = qtiles(spreads_rev)
res["spread_by_engine_p50_p95"] = {e: [qtiles(v)["p50"], qtiles(v)["p95"]] for e, v in by_eng.items() if len(v) >= 20}

# measure book spreads (gated impulse signals, decision-time)
s = json.load(open("/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data/state_extract.json"))
msp = [x["f"]["spread"] for x in s["measure"] if "f" in x and x["f"].get("spread") is not None]
res["spread_measure_book"] = qtiles(msp)

# ---- 2. slip sensitivity on the flagship's live fill mix ----
T = load_trades()
flag = [x for x in T if x["eng"] == "impulse_v2"]
asks = [x["ask"] for x in flag]
res["flagship_fill_mix"] = dict(n=len(asks), ask_mean=round(mean(asks), 4),
                                entry_mean=round(mean([x["entry"] for x in flag]), 4))

def ev_at_slip(q, ask_list, slip):
    evs = []
    for a in ask_list:
        p = a + slip
        evs.append(q - p - fee(p))
    return mean(evs)

def back_out_q(target_ev, ask_list, slip=0.01):
    lo, hi = 0.3, 0.9
    for _ in range(60):
        mid = (lo + hi) / 2
        if ev_at_slip(mid, ask_list, slip) < target_ev:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2

table = {}
for target, lab in [(0.015, "central_low_+1.5c"), (0.03, "central_high_+3.0c")]:
    q = back_out_q(target, asks)
    row = {"implied_q": round(q, 4)}
    die = None
    for slip_c in [0, 0.5, 1, 1.5, 2, 2.5, 3, 3.5, 4, 5]:
        ev = ev_at_slip(q, asks, slip_c / 100)
        row[f"slip_{slip_c}c"] = round(100 * ev, 2)
    # exact zero crossing
    lo_s, hi_s = 0.0, 0.10
    for _ in range(60):
        m = (lo_s + hi_s) / 2
        if ev_at_slip(q, asks, m) > 0:
            lo_s = m
        else:
            hi_s = m
    row["breakeven_slip_c"] = round(100 * (lo_s + hi_s) / 2, 2)
    table[lab] = row
res["slip_sensitivity"] = table

# ---- 3. limit-at-mid vs taker ----
# taker EV per signal = q - (ask+0.01) - fee(ask+0.01)   (fill prob ~1 by construction)
# limit-at-mid EV per signal = f * (q + dq - m - fee(m)), m = ask - spread/2
# with live spread p50 = 1c -> m = ask - 0.005 -> saves 1.5c of price vs taker (+ fee delta).
# Frontier: for f in grid, dq needed so limit ties taker.
ask0 = mean(asks)
sp0 = 0.01
m0 = ask0 - sp0 / 2
res["limit_at_mid_frontier"] = {}
for lab, target in [("at_+1.5c", 0.015), ("at_+3.0c", 0.03)]:
    q = back_out_q(target, asks)
    taker = target
    rows = {}
    for f in [1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3]:
        # dq solving f*(q+dq - m0 - fee(m0)) = taker
        dq = taker / f - (q - m0 - fee(m0))
        ev_no_adverse = f * (q - m0 - fee(m0))
        rows[f"fillprob_{f}"] = dict(
            ev_if_no_adverse_selection_c=round(100 * ev_no_adverse, 2),
            max_adverse_dq_to_still_beat_taker=round(-dq, 4))
    res["limit_at_mid_frontier"][lab] = dict(mid=round(m0, 4), taker_ev_c=round(100 * taker, 2), rows=rows)

# empirical hint on fill prob at mid: pm_prices_sample p20 vs p60 movement (context only)
try:
    pm = json.load(open("/Users/sgonzalez/btc5m-paper-trader/research/2026-07-10-edge-hunt/data/pm_prices_sample.json"))
    # how often does the Up price move >= 0.5c toward you between 20s and 60s? proxy for a
    # 0.5c-better limit filling within the entry window
    moves = [abs(x["p60"] - x["p20"]) for x in pm if x.get("p20") is not None and x.get("p60") is not None]
    res["pm_price_move_20to60s"] = qtiles([round(m, 4) for m in moves])
except Exception as e:
    res["pm_price_move_20to60s"] = str(e)

json.dump(res, open("/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work/micro/a3_spread_slip.json", "w"), indent=1)
print(json.dumps(res, indent=1))
