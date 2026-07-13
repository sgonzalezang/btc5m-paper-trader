#!/usr/bin/env python3
"""
Independent reproduction of FINDING R1 (impulse_v2 quarter-Kelly f>0 policy vs flat-$50 twin).

Implemented from the plain-English claim only:
  - Pair impulse_v2 and impulse50 by t0 (identical signal stream).
  - Policy delta = pnl(impulse_v2) - pnl(impulse50) per signal t0 (missing v2 trade => 0 for v2).
  - Decompose: skip leg / fill-price leg / stake-size leg.
  - 1h-block bootstrap of the total effect; also day-level jackknife (few days!).
  - Stress: drop best day, halve sample (chrono + random), jitter proposed cap edge +/-1c.

Frozen cost model is already baked into ledger pnl (verified below against
EV/share = q - p - 0.07 p (1-p), gas 0.004).
STDLIB ONLY.
"""
import json, random, datetime, statistics

DATA = '/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data/trades_unified.json'
OUT  = '/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work/verify/R1-repro/results.json'
random.seed(20260712)

trades = json.load(open(DATA))
iv  = {t['t0']: t for t in trades if t['eng'] == 'impulse_v2' and t['status'] == 'settled'}
i50 = {t['t0']: t for t in trades if t['eng'] == 'impulse50'  and t['status'] == 'settled'}

# ---- 0. verify ledger pnl against frozen cost model (flat-stake reconstruction) ----
def model_pnl(entry, stake, result):
    shares = stake / entry
    fee = 0.07 * entry * (1 - entry) * shares
    if result == 'win':
        return shares * (1 - entry) - fee - 0.004
    return -stake - fee - 0.004

max_dev = 0.0
for t in list(iv.values()) + list(i50.values()):
    dev = abs(model_pnl(t['entry'], t['stake'], t['result']) - t['pnl'])
    max_dev = max(max_dev, dev)

# ---- 1. pairing ----
union_t0 = sorted(set(iv) | set(i50))
common   = sorted(set(iv) & set(i50))
skips    = sorted(set(i50) - set(iv))   # twin traded, Kelly policy skipped
v2only   = sorted(set(iv) - set(i50))

rows = []  # per-signal rows
for t0 in union_t0:
    a, b = iv.get(t0), i50.get(t0)
    pnl_v2 = a['pnl'] if a else 0.0
    pnl_50 = b['pnl'] if b else 0.0
    delta = pnl_v2 - pnl_50
    # decomposition: counterfactual = v2's fill price at flat $50 stake
    if a and b:
        cf = model_pnl(a['entry'], 50.0, a['result'])
        price_leg = cf - pnl_50          # value of cheaper fill at equal stake
        stake_leg = pnl_v2 - cf          # value of Kelly stake sizing at v2's price
        skip_leg = 0.0
    elif b and not a:
        price_leg = stake_leg = 0.0
        skip_leg = -pnl_50               # value of not taking the twin's trade
    else:
        price_leg = stake_leg = skip_leg = 0.0
    shares50 = b['shares'] if b else 50.0 / a['entry']  # per-signal share basis (flat twin)
    rows.append(dict(t0=t0, delta=delta, price_leg=price_leg, stake_leg=stake_leg,
                     skip_leg=skip_leg, shares50=shares50,
                     entry50=(b['entry'] if b else None),
                     entry_v2=(a['entry'] if a else None),
                     result=(b['result'] if b else a['result']),
                     day=datetime.datetime.utcfromtimestamp(t0).strftime('%Y-%m-%d'),
                     hour_block=t0 // 3600))

n = len(rows)
tot_delta = sum(r['delta'] for r in rows)
tot_shares = sum(r['shares50'] for r in rows)
c_per_share_signal_pooled = 100.0 * tot_delta / tot_shares
c_per_share_signal_mean = 100.0 * statistics.mean(r['delta'] / r['shares50'] for r in rows)

decomp = dict(
    skip_leg_usd  = sum(r['skip_leg'] for r in rows),
    price_leg_usd = sum(r['price_leg'] for r in rows),
    stake_leg_usd = sum(r['stake_leg'] for r in rows),
)

# paired price improvement on common pairs
imp_pairs = [(iv[t0]['entry'] - i50[t0]['entry']) for t0 in common]
cheaper = [x for x in imp_pairs if x < -1e-9]
richer  = [x for x in imp_pairs if x >  1e-9]
price_leg_pairs = [r for r in rows if abs(r['price_leg']) > 1e-9]

# skip-leg stats: exact binomial on 2/8 under null q = entry price (market fair)
skip_entries = [i50[t0]['entry'] for t0 in skips]
skip_wins = sum(1 for t0 in skips if i50[t0]['result'] == 'win')
def binom_cdf_le(k, probs):
    # P(#wins <= k) with heterogeneous win probs (Poisson binomial), exact DP
    dp = [1.0]
    for p in probs:
        ndp = [0.0] * (len(dp) + 1)
        for i, v in enumerate(dp):
            ndp[i]     += v * (1 - p)
            ndp[i + 1] += v * p
        dp = ndp
    return sum(dp[:k + 1])
p_skips_le = binom_cdf_le(skip_wins, skip_entries)   # prob of seeing <=2 wins if market fair

# ---- 2. 1h-block bootstrap ----
blocks = {}
for r in rows:
    blocks.setdefault(r['hour_block'], []).append(r)
block_list = list(blocks.values())
B = len(block_list)

def boot(stat_rows_fn, nboot=20000):
    vals = []
    for _ in range(nboot):
        samp = [block_list[random.randrange(B)] for _ in range(B)]
        flat = [r for blk in samp for r in blk]
        vals.append(stat_rows_fn(flat))
    vals.sort()
    return vals

def total_c_per_share(flat):
    s = sum(r['shares50'] for r in flat)
    return 100.0 * sum(r['delta'] for r in flat) / s if s else 0.0

bv = boot(total_c_per_share)
ci = (bv[int(0.025 * len(bv))], bv[int(0.975 * len(bv))])
p_le0 = sum(1 for v in bv if v <= 0) / len(bv)

# day-level (24h block) bootstrap — merge-agent concern: few blocks understate variance
dayblocks = {}
for r in rows:
    dayblocks.setdefault(r['day'], []).append(r)
day_list = list(dayblocks.values())
D = len(day_list)
dvals = []
for _ in range(20000):
    samp = [day_list[random.randrange(D)] for _ in range(D)]
    flat = [r for blk in samp for r in blk]
    dvals.append(total_c_per_share(flat))
dvals.sort()
ci_day = (dvals[int(0.025 * len(dvals))], dvals[int(0.975 * len(dvals))])
p_le0_day = sum(1 for v in dvals if v <= 0) / len(dvals)

# ---- 3. stress tests ----
stress = {}

# 3a. drop single best day
day_tot = {d: sum(r['delta'] for r in blk) for d, blk in dayblocks.items()}
best_day = max(day_tot, key=day_tot.get)
kept = [r for r in rows if r['day'] != best_day]
stress['drop_best_day'] = dict(
    best_day=best_day, best_day_delta_usd=round(day_tot[best_day], 2),
    day_totals_usd={d: round(v, 2) for d, v in sorted(day_tot.items())},
    remaining_n=len(kept),
    remaining_total_usd=round(sum(r['delta'] for r in kept), 2),
    remaining_c_per_share=round(total_c_per_share(kept), 2),
    sign_survives=sum(r['delta'] for r in kept) > 0)

# leave-one-day-out (all days)
stress['leave_one_day_out'] = {
    d: dict(total_usd=round(tot_delta - v, 2),
            c_per_share=round(total_c_per_share([r for r in rows if r['day'] != d]), 2))
    for d, v in sorted(day_tot.items())}

# 3b. halve the sample
half = n // 2
first, second = rows[:half], rows[half:]
stress['halve_chrono'] = dict(
    first_half=dict(n=len(first), total_usd=round(sum(r['delta'] for r in first), 2),
                    c_per_share=round(total_c_per_share(first), 2)),
    second_half=dict(n=len(second), total_usd=round(sum(r['delta'] for r in second), 2),
                     c_per_share=round(total_c_per_share(second), 2)))
neg = 0
NR = 4000
for _ in range(NR):
    samp = random.sample(rows, half)
    if sum(r['delta'] for r in samp) <= 0:
        neg += 1
stress['halve_random'] = dict(draws=NR, frac_nonpositive=round(neg / NR, 4))

# 3c. jitter the proposed cap edge (recommended hard first-fill ask cap ~47c => entry<=48c).
# Evaluate explicit cap policy on the twin's 34 signals: take twin's trade iff entry <= cap+slip.
def cap_policy(cap_entry):
    taken = [i50[t0] for t0 in sorted(i50) if i50[t0]['entry'] <= cap_entry + 1e-9]
    skipped = [i50[t0] for t0 in sorted(i50) if i50[t0]['entry'] > cap_entry + 1e-9]
    return dict(cap_entry=cap_entry, n_taken=len(taken), n_skipped=len(skipped),
                pnl_taken_usd=round(sum(t['pnl'] for t in taken), 2),
                pnl_avoided_usd=round(-sum(t['pnl'] for t in skipped), 2),
                delta_vs_takeall_usd=round(-sum(t['pnl'] for t in skipped), 2))
stress['cap_jitter'] = {f'{int(c*100)}c_entry(={int(c*100)-1}c_ask)': cap_policy(c)
                        for c in (0.47, 0.48, 0.49)}

# how well do actual Kelly skips align with a price cap?
skip_entry_min = min(skip_entries); nonskip_common_max = max(i50[t0]['entry'] for t0 in common)
overlap = dict(skip_entries=sorted(skip_entries),
               common_entry50_max=nonskip_common_max,
               common_entries_ge_049=sorted(i50[t0]['entry'] for t0 in common if i50[t0]['entry'] >= 0.49))

# ---- 4. merge-agent concern: sensitivity of skip leg to one outcome flip ----
skip_leg = decomp['skip_leg_usd']
flip_one = skip_leg - (42.69 + 51.72)   # one avoided loss had actually won
sens = dict(skip_leg_usd=round(skip_leg, 2),
            skip_record=f'{skip_wins}/{len(skips)}',
            p_le_2wins_if_market_fair=round(p_skips_le, 4),
            skip_leg_if_one_loss_flips_to_win=round(flip_one, 2),
            expected_skip_leg_if_q_equals_p_usd=round(
                -sum(model_pnl(p, 50, 'win') * p + model_pnl(p, 50, 'loss') * (1 - p)
                     for p in skip_entries), 2))

results = dict(
    n_signals=n, n_common_settled=len(common), n_skips=len(skips), n_v2_only=len(v2only),
    pnl_model_max_dev_usd=round(max_dev, 4),
    total_policy_delta_usd=round(tot_delta, 2),
    c_per_share_signal_pooled=round(c_per_share_signal_pooled, 2),
    c_per_share_signal_mean_of_ratios=round(c_per_share_signal_mean, 2),
    decomposition_usd={k: round(v, 2) for k, v in decomp.items()},
    price_pairs=dict(n_cheaper=len(cheaper), n_same=len(imp_pairs) - len(cheaper) - len(richer),
                     n_richer=len(richer),
                     mean_improvement_c=round(-100 * statistics.mean(cheaper), 2) if cheaper else 0,
                     price_leg_paired_c_per_share=round(
                         100 * sum(r['price_leg'] for r in rows) /
                         sum(r['shares50'] for r in price_leg_pairs), 2) if price_leg_pairs else 0),
    bootstrap_1h=dict(n_blocks=B, ci95_c_per_share=[round(ci[0], 2), round(ci[1], 2)],
                      p_le0=round(p_le0, 4)),
    bootstrap_day=dict(n_blocks=D, ci95_c_per_share=[round(ci_day[0], 2), round(ci_day[1], 2)],
                       p_le0=round(p_le0_day, 4)),
    skip_leg_sensitivity=sens,
    stress=stress,
)
json.dump(results, open(OUT, 'w'), indent=1)
print(json.dumps(results, indent=1))
