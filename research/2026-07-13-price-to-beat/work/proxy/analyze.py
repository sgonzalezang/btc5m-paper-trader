#!/usr/bin/env python3
"""Quantify displayed-leader vs oracle divergence, and compare fetchable proxies.
STDLIB ONLY. Coinbase (what the site shows) and Pyth (candidate fix) are each
scored against the Polymarket/Chainlink oracle ground truth.

Mirrors live.html:
  strikeOf(t0)   = Coinbase 1m OPEN at t0            (price to beat)
  settleOf(t0)   = strikeOf(t0+300) = next window's open  (settle instant)
  clearMargin(p) = max(15, 0.0003*p)                 (~$19 at 64k)
  verdictOf: |settle-strike| < clearMargin -> "too close, oracle decides"
Oracle: pm_res_3d [t0, up(1/0)];  Up iff Chainlink(end) >= Chainlink(start), ties->UP.
"""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
CB = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data/cb1m.json"
RES = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-10-edge-hunt/data/pm_res_3d.json"
PYTH = os.path.join(HERE, "pyth_boundaries.json")

cb = json.load(open(CB))
# columnar -> dict t->(open,close)
o_by_t = {t: o for t, o in zip(cb["t"], cb["o"])}
c_by_t = {t: c for t, c in zip(cb["t"], cb["c"])}
res = json.load(open(RES))
oracle = {t: up for t, up in res}

def cb_strike(t0):
    if o_by_t.get(t0) is not None: return o_by_t[t0]
    if c_by_t.get(t0 - 60) is not None: return c_by_t[t0 - 60]  # fallback path
    return None

def clear_margin(p): return max(15.0, p * 0.0003)

pyth = {}
if os.path.exists(PYTH):
    raw = json.load(open(PYTH))
    pyth = {int(k): v["price"] for k, v in raw.items() if isinstance(v.get("price"), (int, float))}

rows = []
for t0, up in res:
    strike = cb_strike(t0)
    settle = cb_strike(t0 + 300)          # site's settleOf = next window open
    if strike is None or settle is None: continue
    cb_move = settle - strike
    cb_bps = cb_move / strike * 1e4
    oracle_up = (up == 1)
    r = {"t0": t0, "oracle_up": oracle_up,
         "cb_strike": strike, "cb_settle": settle, "cb_move": cb_move, "cb_bps": cb_bps,
         "cb_call_up": cb_move > 0, "cb_flat": cb_move == 0,
         "margin": clear_margin(strike),
         "cb_tooclose": abs(cb_move) < clear_margin(strike)}
    ps, pe = pyth.get(t0), pyth.get(t0 + 300)
    if ps is not None and pe is not None:
        pmove = pe - ps
        r.update(py_strike=ps, py_settle=pe, py_move=pmove,
                 py_bps=pmove / ps * 1e4, py_call_up=pmove > 0,
                 py_tooclose=abs(pmove) < clear_margin(ps),
                 cb_py_strike_spread=strike - ps)   # $ Coinbase minus Pyth at t0
    rows.append(r)

n = len(rows)
def agree(call_key):
    sub = [r for r in rows if call_key in r]
    a = sum(1 for r in sub if r[call_key] == r["oracle_up"])
    return len(sub), a, (a / len(sub) * 100 if sub else 0)

# --- overall agreement, treating ties per Polymarket rule (tie -> UP) ---
# Coinbase: how the *displayed* leader (sign of move) maps to oracle. Flat (move==0)
# the site shows "right at the line" / no call; count separately.
cb_nonflat = [r for r in rows if not r["cb_flat"]]
cb_agree = sum(1 for r in cb_nonflat if r["cb_call_up"] == r["oracle_up"])
cb_flat = [r for r in rows if r["cb_flat"]]

report = {"n_intervals": n,
          "oracle_up_rate": round(sum(r["oracle_up"] for r in rows) / n * 100, 2)}

report["coinbase_vs_oracle"] = {
    "n_nonflat": len(cb_nonflat),
    "n_flat_move_exactly_0": len(cb_flat),
    "flat_oracle_up": sum(r["oracle_up"] for r in cb_flat),
    "agree_pct": round(cb_agree / len(cb_nonflat) * 100, 2),
    "disagree": len(cb_nonflat) - cb_agree,
}

# --- disagreement by |move| bucket (bps) ---
def bucket(bps):
    a = abs(bps)
    for hi, name in [(2, "0-2"), (5, "2-5"), (10, "5-10"), (20, "10-20"),
                     (50, "20-50"), (1e9, "50+")]:
        if a < hi: return name
buckets = {}
for r in cb_nonflat:
    b = bucket(r["cb_bps"])
    d = buckets.setdefault(b, {"n": 0, "wrong": 0})
    d["n"] += 1
    if r["cb_call_up"] != r["oracle_up"]: d["wrong"] += 1
for b, d in buckets.items():
    d["wrong_pct"] = round(d["wrong"] / d["n"] * 100, 1)
report["coinbase_disagree_by_bps_bucket"] = buckets

# --- inside the clearMargin band: does the site refuse to call, or call wrong? ---
band = [r for r in rows if r["cb_tooclose"]]
band_nonflat = [r for r in band if not r["cb_flat"]]
band_wrong = sum(1 for r in band_nonflat if r["cb_call_up"] != r["oracle_up"])
report["inside_clearmargin_band"] = {
    "n": len(band), "pct_of_all": round(len(band) / n * 100, 1),
    "n_with_a_directional_move": len(band_nonflat),
    "site_leader_wrong_in_band": band_wrong,
    "site_leader_wrong_in_band_pct": round(band_wrong / len(band_nonflat) * 100, 1) if band_nonflat else None,
    "note": "site labels these 'too close -> oracle decides' at settle, but the LIVE 'Up/Down leads' line still shows a directional leader that is wrong this often",
}

# --- Pyth section (if backfilled) ---
have_pyth = [r for r in rows if "py_call_up" in r]
if have_pyth:
    py_nonflat = [r for r in have_pyth if r["py_move"] != 0]
    py_agree = sum(1 for r in py_nonflat if r["py_call_up"] == r["oracle_up"])
    # head-to-head on the SAME intervals both cover
    both = [r for r in have_pyth if not r["cb_flat"] and r["py_move"] != 0]
    cb_a = sum(1 for r in both if r["cb_call_up"] == r["oracle_up"])
    py_a = sum(1 for r in both if r["py_call_up"] == r["oracle_up"])
    spreads = [abs(r["cb_py_strike_spread"]) for r in have_pyth]
    spreads.sort()
    def pct(p): return round(spreads[min(len(spreads) - 1, int(p / 100 * len(spreads)))], 2)
    # flips where Coinbase and Pyth disagree on the call, and which one the oracle backs
    flips = [r for r in both if r["cb_call_up"] != r["py_call_up"]]
    flips_py_right = sum(1 for r in flips if r["py_call_up"] == r["oracle_up"])
    report["pyth_vs_oracle"] = {
        "n_pyth_boundaries": len(pyth),
        "n_intervals_with_pyth": len(have_pyth),
        "pyth_agree_pct": round(py_agree / len(py_nonflat) * 100, 2) if py_nonflat else None,
        "head_to_head_n": len(both),
        "coinbase_agree_pct": round(cb_a / len(both) * 100, 2) if both else None,
        "pyth_agree_pct_same_set": round(py_a / len(both) * 100, 2) if both else None,
        "cb_pyth_strike_spread_usd": {"p50": pct(50), "p90": pct(90), "p99": pct(99),
                                       "max": round(spreads[-1], 2), "mean": round(sum(spreads)/len(spreads),2)},
        "n_calls_where_cb_and_pyth_disagree": len(flips),
        "of_those_pyth_matches_oracle": flips_py_right,
        "of_those_coinbase_matches_oracle": len(flips) - flips_py_right,
    }
    # by-bucket for pyth too
    pybk = {}
    for r in py_nonflat:
        b = bucket(r["py_bps"]); d = pybk.setdefault(b, {"n": 0, "wrong": 0}); d["n"] += 1
        if r["py_call_up"] != r["oracle_up"]: d["wrong"] += 1
    for b, d in pybk.items(): d["wrong_pct"] = round(d["wrong"]/d["n"]*100, 1)
    report["pyth_disagree_by_bps_bucket"] = pybk

    # basis drift = how much Coinbase's 5-min MOVE disagrees with Pyth's move.
    # A constant CB-vs-oracle basis cancels in the leader call; only drift flips signs.
    drifts = sorted(abs(r["cb_move"] - r["py_move"]) for r in have_pyth)
    def dp(p): return round(drifts[min(len(drifts)-1, int(p/100*len(drifts)))], 2)
    report["basis_drift_cb_move_minus_pyth_move_usd"] = {
        "p50": dp(50), "p90": dp(90), "p99": dp(99), "max": round(drifts[-1], 2),
        "note": "when this exceeds the true move, Coinbase flips the call vs the oracle-tracking source",
    }

    # DID PYTH FIX THE 19 COINBASE-WRONG INTERVALS?
    wrong_t0s = set(json.load(open(os.path.join(HERE, "wrong_t0s.json"))))
    fixed = covered = still_wrong = 0
    detail = []
    for r in have_pyth:
        if r["t0"] not in wrong_t0s: continue
        covered += 1
        py_right = (r["py_call_up"] == r["oracle_up"])
        if py_right: fixed += 1
        else: still_wrong += 1
        detail.append({"t0": r["t0"], "cb_move": round(r["cb_move"], 2),
                       "py_move": round(r["py_move"], 2), "oracle_up": r["oracle_up"],
                       "pyth_correct": py_right})
    report["pyth_on_the_19_coinbase_wrong_intervals"] = {
        "covered_by_pyth": covered, "pyth_fixed": fixed, "pyth_still_wrong": still_wrong,
        "detail": detail,
    }
    # NET error tally on the same sampled set (sample is near-flat ENRICHED, so
    # these rates are danger-zone-weighted, NOT the population rate). cb_only_wrong
    # = Pyth fixed it; py_only_wrong = Pyth INTRODUCED an error; both_wrong = neither
    # source can beat Chainlink at the razor's edge.
    cb_w = sum(1 for r in both if r["cb_call_up"] != r["oracle_up"])
    py_w = sum(1 for r in both if r["py_call_up"] != r["oracle_up"])
    cb_only = sum(1 for r in both if r["cb_call_up"] != r["oracle_up"] and r["py_call_up"] == r["oracle_up"])
    py_only = sum(1 for r in both if r["py_call_up"] != r["oracle_up"] and r["cb_call_up"] == r["oracle_up"])
    both_w = sum(1 for r in both if r["cb_call_up"] != r["oracle_up"] and r["py_call_up"] != r["oracle_up"])
    report["net_errors_on_sampled_set"] = {
        "n": len(both), "note": "near-flat-ENRICHED sample; not population rates",
        "coinbase_errors": cb_w, "pyth_errors": py_w,
        "pyth_fixed_a_coinbase_error": cb_only,
        "pyth_introduced_a_new_error": py_only,
        "both_wrong_razor_edge": both_w,
    }
else:
    report["pyth_vs_oracle"] = "pyth_boundaries.json not ready yet"

json.dump(report, open(os.path.join(HERE, "results.json"), "w"), indent=2)
print(json.dumps(report, indent=2))
