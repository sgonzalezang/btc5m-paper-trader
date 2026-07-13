#!/usr/bin/env python3
"""Fold Pyth level-gap sample + framing into the final results.json."""
import json, os, statistics as st

WD = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-13-price-to-beat/work/divergence"
r = json.load(open(f"{WD}/results.json"))
summ = r["summary"]

# Pyth level-gap sample (cb_open vs pyth_open at t0) if present
pyth_gap = None
if os.path.exists(f"{WD}/pyth_gaps.json"):
    recs = json.load(open(f"{WD}/pyth_gaps.json"))  # [t0, cb, pyth, gap]
    gaps = sorted(abs(x[3]) for x in recs)
    if gaps:
        pyth_gap = {
            "n": len(gaps), "median": round(st.median(gaps),2), "mean": round(st.mean(gaps),2),
            "p90": round(gaps[int(0.9*len(gaps))],2), "max": round(max(gaps),2),
            "note": "cb_open vs Pyth(BTC/USD, Chainlink-class oracle) at interval start t0",
        }

verdict = {
    "headline": "Displayed reference is Coinbase, oracle is Chainlink. Direction agrees 97.8% (844/863). "
                "ALL 19 disagreements are within 2.4 bps of flat and 100% fall inside the site's own "
                "clearMargin dead-zone (max wrong-move $14.07 < ~$19 band).",
    "closed_verdict_correctness": "verdictOf() applies clearMargin: 0/662 confident closed calls wrong (0.00%). "
                                  "The band perfectly quarantines Coinbase-vs-Chainlink divergence in this sample.",
    "live_leader_bug": "live.html line ~840 (the '▲ Up leads / ▼ Down leads' ticker) applies NO clearMargin band "
                       "— it calls a firm side for any nonzero Coinbase move. That line is wrong 19/863 = 2.20%, "
                       "and every wrong call sits inside the dead-zone the site uses in verdictOf() a few lines up. "
                       "Internal inconsistency: the live line confidently picks a side the site's own closed logic declines.",
    "level_gap_correction": "Binance overstates the reference-price gap (median $53) due to USDT basis. "
                            "Pyth (a true oracle-class BTC/USD) puts the Coinbase-vs-oracle level gap at single-digit dollars "
                            "(see cb_vs_pyth_level_gap). The displayed price-to-beat number is off by only a few $, "
                            "immaterial to direction beyond the boundary zone already handled by clearMargin.",
    "fix": "Apply the SAME clearMargin dead-zone to the live 'Up leads/Down leads' line (line ~840) that verdictOf() "
           "already uses: inside max($15,0.03%) show 'too close to call → oracle decides' instead of a firm side. "
           "This removes 100% of the wrong-confident displays. Switching the reference source Coinbase→Pyth is "
           "cosmetic (shrinks the displayed-number gap) but does NOT fix boundary calls — sub-2bps moves are "
           "oracle-timing noise no spot feed can resolve against Chainlink (Pyth itself missed 1/3 sampled boundaries).",
}
summ["cb_vs_pyth_level_gap"] = pyth_gap
summ["verdict"] = verdict
json.dump(r, open(f"{WD}/results.json","w"), indent=1)
print(json.dumps({"cb_vs_pyth_level_gap": pyth_gap, "verdict": verdict}, indent=2))
