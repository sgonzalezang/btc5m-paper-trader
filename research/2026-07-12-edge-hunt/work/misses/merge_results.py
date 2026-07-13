#!/usr/bin/env python3
"""Merge analysis.py / refine.py / policy.py outputs into the master results.json."""
import json
W = '/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work/misses'
base = json.load(open(f'{W}/results.json'))
ref  = json.load(open(f'{W}/results_refine.json'))
pol  = json.load(open(f'{W}/results_policy.json'))

master = {
 'dimension': 'misses & counterfactuals',
 'date': '2026-07-12',
 'era': 'v3 live window 2026-07-10 15:05 -> 2026-07-13 03:40 UTC (2.55 days)',
 'multiplicity': ('~35 comparisons run across this work dir (7 near-miss categories, 8 funnel fates, '
                  '3 funnel stages, 4 kelly-book splits, 5 price bands, 2 gate splits, 2 paired tests, '
                  '2 context splits). Pre-specified primaries: (1) per-signal policy delta impulse_v2 vs '
                  'impulse50, (2) fillable-vs-unfillable win rate (direction fixed by the Jul-10 round). '
                  'The cap53-miss 10/12 result came out of the 7-category near-miss scan: its p=0.013 is '
                  'best-of-7, honest adjusted ~0.09.'),
 'headline': {
   'policy_delta_sizer_vs_takefirst': pol['n_signals'] and {
      'n_signals': pol['n_signals'], 'per_signal_c': pol['policy_delta_per_signal_c'],
      'block_boot': pol['block_boot'], 'decomposition': pol['decomposition']},
   'early_book_lean_replication': ref['early_book_lean'],
   'cap53_rejected_winners': dict(near_miss=base['near_miss_by_reason']['cap53'],
                                  unique_t0_capmiss=ref['early_book_lean']['expensive_capmissed'],
                                  real_55c_fills_on_capmissed=pol['capmiss_real_fills'],
                                  full_54_56_band=ref['band_54_56_fills']),
 },
 'funnel': base['funnel'],
 'fill_selection': base['fill_selection'],
 'kelly_skips': base['kelly_skips'],
 'impulse50_by_band': base['impulse50_by_band'],
 'near_miss_by_reason': base['near_miss_by_reason'],
 'gate_increment_live': base['gate_increment_live'],
 'cap_bands_per_t0': base['cap_bands_per_t0'],
 'paired_sizing': ref['paired_sizing'],
 'capmiss_x_rev55': ref['capmiss_x_rev55'],
 'context_jun26_jul13': ref['context_jun26_jul13'],
 'funnel_holes': ref['funnel_holes'],
 'v3_books': pol['v3_books'],
 'bench_audit': base['bench_audit'],
 'signals_audit': base['signals_audit'],
 'meta': base['meta'],
}
json.dump(master, open(f'{W}/results.json','w'), indent=1)
print('merged results.json written,', len(json.dumps(master)), 'bytes')
