#!/usr/bin/env python3
"""Adversarial verification of R1 (Kelly f>0 sizer = flagship's live edge; freeze <=47c cap).

Lens: multiplicity & selection. Recompute the paired policy delta from the raw
ledger, stress the variance estimate (block sizes, permutation, leave-one-out),
replace the anticonservative skip-leg bootstrap with exact binomials, and
decompose the headline into mechanical vs luck components under honest nulls.
Stdlib only.
"""
import json, math, random
from collections import defaultdict

DATA = '/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data/trades_unified.json'
OUT = '/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work/verify/R1-selection/results.json'

trades = json.load(open(DATA))
V3_START = 1783695900  # 07-10 15:05

def fee(p): return 0.07*p*(1-p)
def ev_share(p, win): return (1.0 if win else 0.0) - p - fee(p)

# --- pull v3-era settled impulse_v2 / impulse50 ---
books = {'impulse_v2': {}, 'impulse50': {}}
for t in trades:
    if t.get('eng') in books and t.get('t0',0) >= V3_START and t.get('status')=='settled' and t.get('result') in ('win','loss'):
        books[t['eng']][t['t0']] = t

iv2, i50 = books['impulse_v2'], books['impulse50']
union = sorted(set(iv2) | set(i50))
common = sorted(set(iv2) & set(i50))
only50 = sorted(set(i50) - set(iv2))
only_v2 = sorted(set(iv2) - set(i50))

# per-signal policy delta: v2 EV/share (0 if skipped) minus i50 EV/share
rows = []
for t0 in union:
    a = iv2.get(t0); b = i50.get(t0)
    ev_a = ev_share(a['entry'], a['result']=='win') if a else 0.0
    ev_b = ev_share(b['entry'], b['result']=='win') if b else 0.0
    kind = 'common' if (a and b) else ('skip' if b else 'v2only')
    imp = (b['entry']-a['entry']) if (a and b) else None
    rows.append(dict(t0=t0, kind=kind, delta=ev_a-ev_b, ev_v2=ev_a, ev_50=ev_b,
                     e_v2=a['entry'] if a else None, e_50=b['entry'] if b else None,
                     win=(b or a)['result']=='win', improve=imp))

deltas = [r['delta'] for r in rows]
n = len(rows)
mean_d = sum(deltas)/n

# --- block bootstrap at several block sizes ---
random.seed(1234)
def block_boot(vals_t0s, block_s, B=20000):
    blocks = defaultdict(list)
    for t0, v in vals_t0s: blocks[t0//block_s].append(v)
    bl = list(blocks.values()); nb = len(bl)
    means, ps = [], 0
    for _ in range(B):
        s = []
        for _ in range(nb): s.extend(random.choice(bl))
        m = sum(s)/len(s)
        means.append(m)
    means.sort()
    lo, hi = means[int(0.05*B)], means[int(0.95*B)-1]
    p2 = 2*min(sum(1 for m in means if m<=0), sum(1 for m in means if m>=0))/B
    return dict(nblocks=nb, mean=sum(means)/B, ci90=[lo,hi], p_two_sided=min(p2,1.0))

vt = [(r['t0'], r['delta']) for r in rows]
boots = {f'{h}h': block_boot(vt, 3600*h) for h in (1,2,3,6,12)}

# --- sign-flip permutation on the 20 nonzero deltas (exchangeability under H0: policy irrelevant) ---
nz = [r['delta'] for r in rows if abs(r['delta'])>1e-12]
obs = sum(nz)
random.seed(99)
cnt = 0; B=200000
for _ in range(B):
    s = sum(v if random.random()<0.5 else -v for v in nz)
    if abs(s) >= abs(obs)-1e-12: cnt += 1
p_signflip = cnt/B
# NOTE: sign-flip is NOT a valid null here for the improvement pairs (delta>0 by
# construction given a later cheaper fill); it bounds how much of p comes from luck vs mechanics.

# --- leave-one-out sensitivity ---
loo = []
for i in range(n):
    m = (sum(deltas)-deltas[i])/(n-1)
    loo.append((rows[i]['t0'], rows[i]['kind'], round(deltas[i]*100,2), round(m*100,3)))
loo_sorted = sorted(loo, key=lambda x: x[3])
big = max(rows, key=lambda r: abs(r['delta']))

# --- skip leg: exact binomial instead of iid bootstrap ---
skips = [r for r in rows if r['kind']=='skip']
k_wins = sum(1 for r in skips if r['win']); ns = len(skips)
mean_entry_skip = sum(r['e_50'] for r in skips)/ns
qstar_skip = mean_entry_skip + fee(mean_entry_skip)  # break-even q at the skip mix

def binom_cdf(k, nn, q):
    return sum(math.comb(nn,i)*q**i*(1-q)**(nn-i) for i in range(k+1))
p_skip_exact_qstar = binom_cdf(k_wins, ns, qstar_skip)   # P(<=k wins | q = break-even)
p_skip_exact_half  = binom_cdf(k_wins, ns, 0.5)
skip_ev_obs = sum(r['ev_50'] for r in skips)/ns

# --- luck-adjusted decomposition of the headline ---
# structural (mechanical) component: price improvement on common pairs, in c/share-signal
impr_total = sum((r['improve'] or 0) for r in rows if r['kind']=='common')
impr_per_signal = impr_total/n
# skip component expectation under q-null scenarios
def skip_component(q_null):
    # EV/share of skipping = -(EV of taking) per skip, averaged over all signals
    tot = 0
    for r in skips:
        p = r['e_50']
        tot += -(q_null - p - fee(p))
    return tot/n
# empirical q for rich fills from bigger samples (pooled v3 48-53c first fills + full reversal ledger 48-55c)
rich = [t for t in trades if t.get('status')=='settled' and t.get('result') in ('win','loss')
        and t.get('eng') in ('reversal','reversal2','reversal_v2','impulse50')
        and t.get('entry') is not None and 0.48<=t['entry']<=0.56]
q_rich_all = sum(1 for t in rich if t['result']=='win')/len(rich)
rich_v3 = [t for t in rich if t['t0']>=V3_START]
q_rich_v3 = sum(1 for t in rich_v3 if t['result']=='win')/len(rich_v3)

skip_luck_table = {f'q={q:.3f}': dict(exp_c_per_signal=round(skip_component(q)*100,2))
                   for q in (0.5, q_rich_all, q_rich_v3, qstar_skip)}
skip_obs_per_signal = -sum(r['ev_50'] for r in skips)/n

# stake-sizing residual (dollar-weighted, from ledger pnl) — reproduce flagship number
pnl_v2 = sum(iv2[t]['pnl'] for t in iv2)
pnl_50 = sum(i50[t]['pnl'] for t in i50)

# --- honest re-estimate: mechanical improvement + luck-adjusted skip + 0 sizing ---
honest = dict(
    mechanical_price_improvement_c=round(impr_per_signal*100,2),
    skip_component_observed_c=round(skip_obs_per_signal*100,2),
    skip_component_null_q50_c=round(skip_component(0.5)*100,2),
    skip_component_null_qrich_c=round(skip_component(q_rich_all)*100,2),
    headline_c=round(mean_d*100,2),
)

# --- adverse-selection check on rescued fills: does waiting fill only when market moved against you? ---
resc = [r for r in rows if r['kind']=='common' and (r['improve'] or 0)>1e-9]
resc_w = sum(1 for r in resc if r['win'])
resc_entry = sum(r['e_v2'] for r in resc)/len(resc)
resc_qstar = resc_entry + fee(resc_entry)
p_resc = 1-binom_cdf(resc_w-1, len(resc), resc_qstar)  # P(>=k | q*) upper tail

# --- non-monotone price toxicity check (R2 double-count / contradiction) ---
def band_stats(lo, hi, engs, t0min=V3_START):
    xs = [t for t in trades if t.get('eng') in engs and t.get('t0',0)>=t0min
          and t.get('status')=='settled' and t.get('result') in ('win','loss')
          and t.get('entry') is not None and lo<=t['entry']<hi]
    if not xs: return None
    w = sum(1 for t in xs if t['result']=='win')
    ev = sum(ev_share(t['entry'], t['result']=='win') for t in xs)/len(xs)
    return dict(n=len(xs), wins=w, wr=round(w/len(xs),3), ev_c=round(ev*100,2))
flat = ('impulse50','reversal_v2','reversal','reversal2')
bands = {b: band_stats(*b_rng, flat) for b, b_rng in
         {'<40':(0.0,0.40),'40-48':(0.40,0.48),'48-53':(0.48,0.535),'53-56':(0.535,0.56)}.items()}

res = dict(
  reproduction=dict(
    n_union=n, n_common=len(common), n_skips=len(only50), n_v2_only=len(only_v2),
    headline_delta_c=round(mean_d*100,2),
    claimed=10.55,
    pnl_gap_usd=round(pnl_v2-pnl_50,2),
  ),
  block_bootstrap_by_block_size={k: dict(nblocks=v['nblocks'], ci90_c=[round(v['ci90'][0]*100,2), round(v['ci90'][1]*100,2)], p=round(v['p_two_sided'],4)) for k,v in boots.items()},
  signflip_perm_nonzero=dict(n_nonzero=len(nz), p_two_sided=round(p_signflip,4),
      caveat='not a clean null for improvement pairs (positive by construction); shown as stress only'),
  leave_one_out=dict(min_mean_c=loo_sorted[0][3], max_mean_c=loo_sorted[-1][3],
      biggest_single_pair=dict(t0=big['t0'], kind=big['kind'], delta_c=round(big['delta']*100,2)),
      mean_without_biggest_c=round((sum(deltas)-big['delta'])/(n-1)*100,2)),
  skip_leg_exact=dict(n=ns, wins=k_wins, mean_entry=round(mean_entry_skip,4), qstar=round(qstar_skip,4),
      obs_ev_c=round(skip_ev_obs*100,2),
      p_exact_binom_vs_qstar=round(p_skip_exact_qstar,4),
      p_exact_binom_vs_half=round(p_skip_exact_half,4),
      claimed_p=0.0337,
      verdict='claimed 0.034 came from iid bootstrap of 8 EV values; exact binomial is 3x larger'),
  luck_adjusted_decomposition=dict(**honest, skip_null_table=skip_luck_table,
      q_rich_all_eras=dict(q=round(q_rich_all,4), n=len(rich)),
      q_rich_v3=dict(q=round(q_rich_v3,4), n=len(rich_v3))),
  rescued_fills_adverse_selection=dict(n=len(resc), wins=resc_w, mean_entry=round(resc_entry,4),
      qstar=round(resc_qstar,4), p_upper_vs_qstar=round(p_resc,4)),
  price_band_monotonicity_flat_arms_v3=bands,
)
json.dump(res, open(OUT,'w'), indent=1)
print(json.dumps(res, indent=1))
