#!/usr/bin/env python3
"""Quantify divergence between the DISPLAYED (Coinbase-derived) price-to-beat /
leader call and the Polymarket ORACLE settlement (Chainlink). STDLIB ONLY.

Reproduces live.html exactly:
  strikeOf(t0)  = Coinbase 1-min OPEN at t0   (fallback: prior candle close)
  settleOf(t0)  = strikeOf(t0+300) = Coinbase OPEN at t0+300
  clearMargin(px)= max(15, px*0.0003)            (== bot _clear_margin)
  verdictOf: |settle-strike| < clearMargin -> tooClose (defer to oracle)
             else up iff settle>strike
  live "leads" bar: d = spot-open, ▲Up leads iff d>0 (NO clearMargin band)
Ground truth: pm_res_3d.json  [t0, up(1/0)]  (Polymarket oracle = Chainlink).
"""
import json, math, os
D12 = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data"
D10 = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-10-edge-hunt/data"
OUT = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-13-price-to-beat/work/codefix"

cb = json.load(open(f"{D12}/cb1m.json"))
T, O, C = cb["t"], cb["o"], cb["c"]
op = {t: o for t, o in zip(T, O)}          # candle open by minute-ts
cl = {t: c for t, c in zip(T, C)}          # candle close by minute-ts
pm = json.load(open(f"{D10}/pm_res_3d.json"))

def strikeOf(t0):
    if t0 in op and op[t0] is not None: return op[t0]
    if (t0-60) in cl and cl[t0-60] is not None: return cl[t0-60]
    return None
def clearMargin(px): return max(15.0, px*0.0003)

rows = []
for t0, up in pm:
    strike = strikeOf(t0)
    settle = strikeOf(t0+300)                # == next window's open == boundary instant
    if strike is None or settle is None: continue
    move = settle - strike
    bps = move/strike*1e4
    cm = clearMargin(strike)
    # live leader indicator (no band): ties -> "right at the line" (d==0 rare); sign
    cb_up = None if move == 0 else (move > 0)
    # settle verdict (with band)
    tooClose = abs(move) < cm
    conf_up = None if tooClose else (move > 0)
    rows.append(dict(t0=t0, oracle_up=bool(up), strike=strike, settle=settle,
                     move=move, bps=bps, cm=cm, cb_up=cb_up, tooClose=tooClose,
                     conf_up=conf_up, absbps=abs(bps)))
n = len(rows)

# --- venue tie rule: Coinbase move==0 -> treat as Up (end>=start). Recompute cb_up_tie
for r in rows:
    r["cb_up_tie"] = (r["move"] >= 0)        # ties -> up, matches oracle rule

# 1) live leader indicator (sign, ties->up) vs oracle
liveg = sum(1 for r in rows if r["cb_up_tie"] == r["oracle_up"])
# 2) confident settle verdict: only rows with a confident (non-tooClose) call
conf = [r for r in rows if not r["tooClose"]]
conf_wrong = [r for r in conf if r["conf_up"] != r["oracle_up"]]
# rows the site declines (tooClose) -> "oracle decides", never a wrong confident claim
tooclose = [r for r in rows if r["tooClose"]]

def pct(a, b): return round(100.0*a/b, 3) if b else None

summary = {
    "n_intervals": n,
    "time_range": [rows[0]["t0"], rows[-1]["t0"]] if rows else None,
    "live_leader_indicator_vs_oracle": {
        "note": "live.html btcbar: ▲Up leads iff spot>open, NO clearMargin band; every viewer sees this during the window",
        "agree": liveg, "disagree": n-liveg, "agree_pct": pct(liveg, n),
        "disagree_pct": pct(n-liveg, n),
    },
    "settle_verdict_with_clearmargin": {
        "note": "verdictOf: |move|>=clearMargin -> confident Up won/Down won; else 'too close -> oracle decides'",
        "n_confident": len(conf), "confident_pct": pct(len(conf), n),
        "n_tooclose_deferred": len(tooclose), "tooclose_pct": pct(len(tooclose), n),
        "confident_WRONG_vs_oracle": len(conf_wrong),
        "confident_wrong_pct_of_confident": pct(len(conf_wrong), len(conf)),
        "confident_wrong_pct_of_all": pct(len(conf_wrong), n),
    },
}

# 3) slice by |move| bps
buckets = [(0,1),(1,2),(2,3),(3,5),(5,10),(10,20),(20,50),(50,10**9)]
slices = []
for lo, hi in buckets:
    b = [r for r in rows if lo <= r["absbps"] < hi]
    if not b: continue
    ag = sum(1 for r in b if r["cb_up_tie"] == r["oracle_up"])
    bc = [r for r in b if not r["tooClose"]]
    bcw = [r for r in bc if r["conf_up"] != r["oracle_up"]]
    slices.append({
        "bps_lo": lo, "bps_hi": (None if hi>10**8 else hi), "n": len(b),
        "sign_agree_pct": pct(ag, len(b)),
        "sign_disagree": len(b)-ag,
        "n_confident": len(bc), "confident_wrong": len(bcw),
        "confident_wrong_pct": pct(len(bcw), len(bc)) if bc else None,
    })
summary["by_move_bps"] = slices

# 4) how wide would clearMargin need to be to NEVER show a wrong confident leader?
#    = the largest |move_bps| at which oracle still disagreed with Coinbase sign.
disagree_bps = sorted([r["absbps"] for r in rows if r["cb_up_tie"] != r["oracle_up"]])
summary["disagreement_move_bps"] = {
    "n_disagreements": len(disagree_bps),
    "max_abs_bps_with_disagreement": round(disagree_bps[-1],3) if disagree_bps else None,
    "p50": round(disagree_bps[len(disagree_bps)//2],3) if disagree_bps else None,
    "p90": round(disagree_bps[int(len(disagree_bps)*0.9)],3) if disagree_bps else None,
    "p99": round(disagree_bps[int(len(disagree_bps)*0.99)],3) if disagree_bps else None,
    "note": "clearMargin (3bps) leaves confident-wrong calls whenever a disagreement's |move| exceeds 3bps",
}
# current clearMargin is 3bps (0.0003) or $15 floor. What fraction of disagreements are OUTSIDE the 3bps band (=confident wrong)?
out3 = [x for x in disagree_bps if x >= 3.0]
summary["disagreements_outside_3bps_band"] = {"count": len(out3), "pct_of_disagreements": pct(len(out3), len(disagree_bps)) if disagree_bps else None}

# 5) trade-level: bot-stored Coinbase btcOpen/btcClose vs FINAL oracle result
tu = json.load(open(f"{D12}/trades_unified.json"))
def opp(s): return "up" if s=="down" else "down"
tl = {"n_final_oracle":0, "cb_call_vs_oracle_agree":0, "cb_call_wrong":0, "provisional_still_marked":0}
prov_wrong_examples = []
for t in tu:
    sb = str(t.get("settledBy") or "")
    res = t.get("result"); side = t.get("side")
    bo, bc = t.get("btcOpen"), t.get("btcClose")
    if t.get("provisional"): tl["provisional_still_marked"] += 1
    if res not in ("win","loss") or side not in ("up","down"): continue
    if "polymarket" not in sb: continue          # only FINAL oracle-settled trades
    oracle_win = side if res=="win" else opp(side)
    if bo is None or bc is None: continue
    cb_call = "up" if bc>=bo else "down"         # ties->up
    tl["n_final_oracle"] += 1
    if cb_call == oracle_win: tl["cb_call_vs_oracle_agree"] += 1
    else:
        tl["cb_call_wrong"] += 1
        if len(prov_wrong_examples)<8:
            prov_wrong_examples.append(dict(t0=t.get("t0"), eng=t.get("eng"), side=side,
                result=res, btcOpen=bo, btcClose=bc, cb_call=cb_call, oracle_win=oracle_win,
                move=round(bc-bo,2), settledBy=sb))
tl["cb_call_agree_pct"] = pct(tl["cb_call_vs_oracle_agree"], tl["n_final_oracle"])
tl["cb_call_wrong_pct"] = pct(tl["cb_call_wrong"], tl["n_final_oracle"])
tl["note"] = ("bot btcClose lags the boundary by up to ~1 candle; this over-states display error vs "
              "the site's settleOf(next-open). Shows how often the stored Coinbase ref alone mis-calls the oracle.")
summary["trade_level_btcClose_vs_oracle"] = tl
summary["trade_level_wrong_examples"] = prov_wrong_examples

# 6) provisional-settle correction rate: how often did the FEED provisional differ from oracle
#    (settledBy 'polymarket (corrected)' means the interim feed call was WRONG and got fixed)
corr = sum(1 for t in tu if "corrected" in str(t.get("settledBy") or ""))
feedprov = sum(1 for t in tu if str(t.get("settledBy") or "").startswith("feed"))
summary["provisional_feed_settles"] = {
    "feed_provisional_or_unconfirmed": feedprov,
    "explicitly_corrected_by_oracle": corr,
    "note": "settledBy startswith 'feed' = interim Coinbase call not yet oracle-confirmed; 'corrected' = feed call was oracle-wrong",
}

json.dump(summary, open(f"{OUT}/results.json","w"), indent=2)
print(json.dumps(summary, indent=2))
