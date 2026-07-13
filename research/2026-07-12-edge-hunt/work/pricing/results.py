"""Assemble results.json for the pricing/calibration dimension."""
import json

def L(f):
    try: return json.load(open(f))
    except Exception as e: return {"error": str(e)}

calib = L("calib.json"); qp = L("ledger_qp.json"); ev = L("ev_buckets.json")
dec = L("decensor.json"); tim = L("timing.json"); ties = L("ties.json")
spr = L("spread.json"); upr = L("up_rate_by_move.json")

results = {
 "dimension": "polymarket pricing & book calibration",
 "date": "2026-07-12",
 "data_notes": {
   "resolution_map": "1,078 actual PM resolutions (pm_res_3d + ledger polymarket settles), Jul 7-13; 8 conflicts resolved toward ledger",
   "pm_res_3d_offbyone": "7 of 741 large-move rows (>=4bp) in pm_res_3d match the NEXT interval's Coinbase sign (clusters Jul7 21:00-21:45, Jul9 21:35-40) -> ~0.8% off-by-one harvest contamination; pm_prices_sample is clean (215/216 agree with resolution map, 0 suspects)",
   "signals_log": "logs only FILLED signals (emissions==fills 1:1) -> NOT a de-censoring source; unique value = bid/spread per fill",
   "proxy_agreement_actual": {"overall": "97.4% (n=1078)", "ge4bp": "99.1% (734/741, NOT 100%)",
                              "1-4bp": "98.8-98.9%", "lt1bp": "76.3% (58/76)"},
 },
 "F1_ge50_fills_fee_dead": {
   "claim": "Trigger-family (12bps reversal/impulse engines) fills at effective entry >= 0.50 are fee-dead in every era",
   "pooled": ev.get("rev_all_ge50"),
   "wilson_q_ci": [0.383, 0.516], "breakeven_at_mean_fill_0.524": 0.5412,
   "era_stability": {"pre_v3": ev.get("rev_pre_v3_ge50"), "v3": ev.get("rev_v3_ge50")},
   "marginal_53_55_band_reversal55cap": {"n": 30, "q": 0.433, "wilson_ci": [0.274, 0.608],
                                          "mean_entry": 0.5452, "ev_c": -12.92},
   "lt50_comparison": ev.get("rev_all_lt50"),
   "diff_lt50_minus_ge50": ev.get("diff_lt50_minus_ge50_all"),
   "multiplicity": "bucket boundary 0.50 fixed by prior design (MF2), not fit here; 2 primary contrasts",
 },
 "F2_contradiction_resolved": {
   "claim": "verify-regime 'expensive fills win more' does NOT replicate; price is informative only ABOVE the buyable cap",
   "within_fills_reversal_family": qp.get("contrast_reversal_family"),
   "within_fills_reversal_family_dedup": qp.get("contrast_reversal_family_dedup"),
   "all_contrarian": qp.get("contrast_contrarian_ALL"),
   "decensored_fill_split_livewindow": dec.get("fillsplit_pm_livewindow"),
   "cap_rejected_misses": dec.get("cap_rejected_misses"),
   "cap_rejected_binomial_p_vs_half": 0.0017,
   "interpretation": "unfilled/cap-rejected trigger signals win more (q .573 vs .467, p=.12; explicit cap-rejects 12/13) but at asks above breakeven (53-55c band EV -12.9c); within the buyable region q is flat-to-declining in price",
 },
 "F3_book_calibration": {
   "global_at_20s": calib.get("calib_p20", {}).get("mean_up_minus_price"),
   "global_at_60s": calib.get("calib_p60", {}).get("mean_up_minus_price"),
   "cheap_side_blind_ev_60s": calib.get("cheap_side_ev_p60"),
   "fav_side_blind_ev_60s_cap65": calib.get("fav_side_ev_p60_cap65"),
   "momentum_ledger_refutation": {"fills_60_66c": qp.get("qp_ALL_momentum", {}).get("table", [{}]*8)[7] if qp.get("qp_ALL_momentum") else None,
                                   "fills_55_60c": qp.get("qp_ALL_momentum", {}).get("table", [{}]*7)[6] if qp.get("qp_ALL_momentum") else None},
   "multiplicity": "9 blind-EV cells tested (3 snapshots x {cheap,fav,fav-cap65}); nominal p .035 for fav-60s-cap65 fails K=9 correction and the 2,595-fill ledger test",
 },
 "F4_entry_timing": {
   "sample_triggers": tim.get("n_sample_triggers"),
   "contrarian_cost_by_second_uncapped": {k: tim[k] for k in ("trigger_contra_p20_uncapped","trigger_contra_p60_uncapped","trigger_contra_p150_uncapped") if k in tim},
   "executable_cap53": {k: tim[k] for k in ("trigger_contra_p20_cap53","trigger_contra_p60_cap53","trigger_contra_p150_cap53") if k in tim},
   "book_information_speed_winner_price": {k: tim[k] for k in ("winner_price_p20","winner_price_p60","winner_price_p150","winner_price_pLast") if k in tim},
   "ledger_by_entrysec": tim.get("ledger_rev_by_entrysec"),
   "verdict": "no deployable better entry second; late cheap availability is adverse selection (capped late wr .32-.33)",
 },
 "F5_ties_and_spread": {
   "neartie_freq": {"train": ties.get("ties_train"), "test": ties.get("ties_test")},
   "neartie_predictable_from_trailvol_TEST": ties.get("neartie_by_trailvol_TEST"),
   "neartie_given_trigger": ties.get("neartie_given_trigger"),
   "coin_flip_clears_fees_at_fill_mix": "q*=.4898 at share-wtd fill .4724 < 0.50 -> near-ties are NOT a fee burn at current fills",
   "up_rate_by_move": upr,
   "spread_overall": spr.get("spread_overall"),
   "spread_by_hour_effective_cost_above_mid_c": {h: v.get("eff_cost_above_mid_c") for h, v in spr.get("by_hour", {}).items()},
   "trigger_family_spread": spr.get("by_family", {}).get("trigger_family"),
 },
}
json.dump(results, open("results.json", "w"), indent=1)
print("results.json written")
