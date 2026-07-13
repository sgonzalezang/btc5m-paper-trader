#!/usr/bin/env python3
"""Full-ledger autopsy & calibration — 2026-07-12 edge hunt.

Pool of 3,495 settled win/loss trades (Jul 7-13). Frozen cost model:
EV/share = q - p - 0.07*p*(1-p), gas $0.004/trade, fill = ask + 1c slip.

Q1 PnL decomposition (fees+gas vs adverse selection vs slippage; pnl at ask / at mid)
Q2 Calibration curve q(p) vs q*(p) in 5c buckets, pooled + per side
Q3 Side asymmetry (up vs down at same price, Mantel-Haenszel stratified)
Q4 EV as a function of entry price alone (is cheapness the whole edge?)
Q5 Drift conditioning: q(p) given favorable/adverse intra-interval drift at entry

Stdlib only. Writes results.json next to this script.
"""
import json, math, random, collections, datetime, os

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, '..', '..', 'data', 'trades_unified.json')

def fee_ps(p):  return 0.07 * p * (1.0 - p)
def qstar(p):   return p + fee_ps(p)

def wilson(k, n, z=1.96):
    if n == 0: return (0.0, 1.0)
    ph = k / n
    d = 1 + z*z/n
    c = ph + z*z/(2*n)
    h = z * math.sqrt(ph*(1-ph)/n + z*z/(4*n*n))
    return ((c-h)/d, (c+h)/d)

def block_boot_mean(vals_by_block, B=4000, seed=7):
    """1h-block bootstrap of the mean of per-trade values. Returns (mean, lo95, hi95, p_gt0 one-sided p for mean<=0)."""
    blocks = list(vals_by_block.values())
    if not blocks: return None
    rng = random.Random(seed)
    nb = len(blocks)
    flat = [v for b in blocks for v in b]
    mu = sum(flat)/len(flat)
    stats = []
    for _ in range(B):
        s, c = 0.0, 0
        for _ in range(nb):
            b = blocks[rng.randrange(nb)]
            s += sum(b); c += len(b)
        if c: stats.append(s/c)
    stats.sort()
    lo = stats[int(0.025*len(stats))]; hi = stats[int(0.975*len(stats))]
    p_le0 = sum(1 for x in stats if x <= 0)/len(stats)   # bootstrap P(mean<=0)
    return (mu, lo, hi, p_le0)

def by_hour(trades, valfn):
    d = collections.defaultdict(list)
    for t in trades:
        d[t['t0']//3600].append(valfn(t))
    return d

# ---------------- load ----------------
tr = json.load(open(DATA))
S = [t for t in tr if t.get('status')=='settled' and t.get('result') in ('win','loss')]
assert len(S) == 3495, len(S)
for t in S:
    t['w'] = 1.0 if t['result']=='win' else 0.0
    t['p'] = t['entry']
    # signed drift at entry relative to side, in bps
    d = (t['btcEntry'] - t['btcOpen']) / t['btcOpen'] * 1e4
    t['sdrift'] = d if t['side']=='up' else -d
    t['ev_ps']  = t['w'] - t['p'] - fee_ps(t['p'])                    # model EV/share at fill
    t['ev_ask'] = t['w'] - t['ask'] - fee_ps(t['ask'])                # counterfactual at ask (no slip)
    mid = max(0.01, t['ask'] - 0.005)                                  # mid assumption: live spread p50=1c
    t['ev_mid'] = t['w'] - mid - fee_ps(mid)

MOM = {'loose','floor','band','value','fade','strict','capless','calm'}
REV = {'reversal','reversal2','latentfire','reversal_v2','impulse50','impulse_v2'}
V3_T0 = max(t['t0'] for t in S if t['eng']=='loose')   # momentum retirement boundary (Jul 10 15:05)
def era(t):
    return 'v3' if t['t0'] > V3_T0 else 'pre'

results = {'n_settled': len(S), 'cost_model': 'EV/share = q - p - 0.07*p*(1-p); gas 0.004/trade; fill=ask+1c',
           'mid_assumption': 'mid = ask - 0.5c (live spread p50 = 1c per prior microstructure work)'}

# ---------------- Q1: decomposition ----------------
def decomp(trades):
    n = len(trades)
    sh = sum(t['shares'] for t in trades)
    logged = sum(t['pnl'] for t in trades)
    model  = sum(t['shares']*t['ev_ps'] - 0.004 for t in trades)
    at_ask = sum(t['shares']*t['ev_ask'] - 0.004 for t in trades)
    at_mid = sum(t['shares']*t['ev_mid'] - 0.004 for t in trades)
    fees   = sum(t['shares']*fee_ps(t['p']) for t in trades)
    gas    = 0.004*n
    slip_cost = at_ask - model                    # $ lost to the +1c slip (incl. its fee delta)
    spread_cost = at_mid - at_ask                 # $ lost crossing half the spread
    # share-weighted per-share stats
    q_sw  = sum(t['shares']*t['w'] for t in trades)/sh
    p_sw  = sum(t['shares']*t['p'] for t in trades)/sh
    ask_sw= sum(t['shares']*t['ask'] for t in trades)/sh
    mid_sw= ask_sw - 0.005
    return dict(n=n, shares=round(sh,1), pnl_logged=round(logged,2), pnl_model=round(model,2),
                hedge_and_rounding=round(logged-model,2),
                pnl_at_ask=round(at_ask,2), pnl_at_mid=round(at_mid,2),
                fees=round(fees,2), gas=round(gas,2),
                slip_cost=round(slip_cost,2), halfspread_cost=round(spread_cost,2),
                adverse_selection_at_mid=round(sum(t['shares']*(t['w']-(t['ask']-0.005)) for t in trades),2),
                q_sharewtd=round(q_sw,4), p_fill_sharewtd=round(p_sw,4), ask_sharewtd=round(ask_sw,4),
                sel_at_fill_c=round(100*(q_sw-p_sw),2),      # q - p, c/share
                sel_at_mid_c=round(100*(q_sw-mid_sw),2),     # q - mid, c/share (true adverse selection)
                fee_c=round(100*fees/sh,2), slip_c=round(100*slip_cost/sh,2) if sh else None,
                net_c=round(100*model/sh,2))

deco = {'pooled': decomp(S)}
for e in sorted(set(t['eng'] for t in S)):
    deco[e] = decomp([t for t in S if t['eng']==e])
deco['momentum_family'] = decomp([t for t in S if t['eng'] in MOM])
deco['reversal_family'] = decomp([t for t in S if t['eng'] in REV])
deco['v3_era_all']      = decomp([t for t in S if era(t)=='v3'])
results['q1_decomposition'] = deco

# ---------------- Q2/Q3: calibration ----------------
def bucket(p):
    b = int(p*100)//5*5
    return f"{b:02d}-{b+5:02d}"

def calib(trades, tag):
    rows = []
    groups = collections.defaultdict(list)
    for t in trades: groups[bucket(t['p'])].append(t)
    for b in sorted(groups):
        ts = groups[b]; n = len(ts); k = sum(int(t['w']) for t in ts)
        q = k/n
        pbar = sum(t['p'] for t in ts)/n
        qs = sum(qstar(t['p']) for t in ts)/n
        ev = sum(t['ev_ps'] for t in ts)/n
        lo, hi = wilson(k, n)
        # dedupe by (t0,side): engines stack on the same interval -> correlated
        dd = {}
        for t in ts: dd.setdefault((t['t0'], t['side']), t)
        ddn = len(dd); ddk = sum(int(t['w']) for t in dd.values())
        rows.append(dict(bucket=b, n=n, wins=k, q=round(q,4), p_mean=round(pbar,4),
                         qstar=round(qs,4), ev_c=round(100*ev,2),
                         q_ci95=[round(lo,4), round(hi,4)],
                         ev_ci95_c=[round(100*(lo-qs),2), round(100*(hi-qs),2)],
                         clears_fees=bool(lo > qs),
                         n_dedup=ddn, q_dedup=round(ddk/ddn,4)))
    return rows

cal = {}
cal['pooled_all']   = calib(S, 'pooled')
cal['side_up']      = calib([t for t in S if t['side']=='up'], 'up')
cal['side_down']    = calib([t for t in S if t['side']=='down'], 'down')
cal['reversal_family'] = calib([t for t in S if t['eng'] in REV], 'rev')
cal['momentum_family'] = calib([t for t in S if t['eng'] in MOM], 'mom')
cal['v3_era']       = calib([t for t in S if era(t)=='v3'], 'v3')
results['q2_calibration'] = cal

# block-bootstrap EV for any bucket x family that looks positive (and key negatives)
boot_lines = {}
for name, subset in [('rev_35-40', [t for t in S if t['eng'] in REV and 0.35<=t['p']<0.40]),
                     ('rev_40-45', [t for t in S if t['eng'] in REV and 0.40<=t['p']<0.45]),
                     ('rev_lt45', [t for t in S if t['eng'] in REV and t['p']<0.45]),
                     ('rev_lt50', [t for t in S if t['eng'] in REV and t['p']<0.50]),
                     ('rev_45-53',[t for t in S if t['eng'] in REV and 0.45<=t['p']<=0.53]),
                     ('pooled_lt45',[t for t in S if t['p']<0.45]),
                     ('pooled_lt50',[t for t in S if t['p']<0.50]),
                     ('v3_lt50',  [t for t in S if era(t)=='v3' and t['p']<0.50]),
                     ('v3_all',   [t for t in S if era(t)=='v3']),
                     ('mom_ge55', [t for t in S if t['eng'] in MOM and t['p']>=0.55])]:
    if len(subset) >= 20:
        bb = block_boot_mean(by_hour(subset, lambda t: t['ev_ps']))
        boot_lines[name] = dict(n=len(subset), ev_c=round(100*bb[0],2),
                                ci95_c=[round(100*bb[1],2), round(100*bb[2],2)],
                                p_le0=round(bb[3],4))
results['q2_block_bootstrap'] = boot_lines

# ---------------- Q3: side asymmetry, stratified ----------------
def mh_side(trades):
    """Mantel-Haenszel-style inverse-variance combine of (q_up - q_down) across 5c strata."""
    groups = collections.defaultdict(lambda: {'up':[0,0], 'down':[0,0]})
    for t in trades:
        g = groups[bucket(t['p'])][t['side']]
        g[0] += int(t['w']); g[1] += 1
    num = den = 0.0; strata = []
    for b, g in sorted(groups.items()):
        ku,nu = g['up']; kd,nd = g['down']
        if nu >= 10 and nd >= 10:
            qu, qd = ku/nu, kd/nd
            var = qu*(1-qu)/nu + qd*(1-qd)/nd
            if var > 0:
                w = 1/var
                num += w*(qu-qd); den += w
                strata.append(dict(bucket=b, n_up=nu, q_up=round(qu,4), n_down=nd, q_down=round(qd,4),
                                   diff=round(qu-qd,4), z=round((qu-qd)/math.sqrt(var),2)))
    if den == 0: return None
    d = num/den; se = math.sqrt(1/den)
    return dict(diff_up_minus_down=round(d,4), se=round(se,4), z=round(d/se,2), strata=strata)

results['q3_side_asymmetry'] = {
    'pooled': mh_side(S),
    'reversal_family': mh_side([t for t in S if t['eng'] in REV]),
    'momentum_family': mh_side([t for t in S if t['eng'] in MOM]),
}
# baseline up-rate of settled intervals in the window (dedupe by t0)
ivl = {}
for t in S:
    up_won = (t['w']==1.0) == (t['side']=='up')
    ivl[t['t0']] = up_won
results['q3_interval_up_rate'] = dict(n=len(ivl), up_rate=round(sum(ivl.values())/len(ivl),4))

# ---------------- Q4: cheapness ----------------
# q(p) slope: logistic-free — compare q across price bands within each family; plus corr(w,p) bootstrap.
def cheap(trades):
    bands = [(0.0,0.45),(0.45,0.50),(0.50,0.55),(0.55,0.60),(0.60,1.01)]
    out = []
    for a,b in bands:
        ts = [t for t in trades if a<=t['p']<b]
        if not ts: continue
        n=len(ts); k=sum(int(t['w']) for t in ts); q=k/n
        qs=sum(qstar(t['p']) for t in ts)/n
        ev=sum(t['ev_ps'] for t in ts)/n
        lo,hi=wilson(k,n)
        out.append(dict(band=f"{a:.2f}-{b:.2f}", n=n, q=round(q,4), qstar=round(qs,4),
                        ev_c=round(100*ev,2), q_ci95=[round(lo,4),round(hi,4)]))
    return out

results['q4_cheapness'] = {
    'pooled': cheap(S),
    'reversal_family': cheap([t for t in S if t['eng'] in REV]),
    'momentum_family': cheap([t for t in S if t['eng'] in MOM]),
}
# corr(w, p) within reversal family with hour-block bootstrap of the q(p<med) - q(p>=med) diff
revts = [t for t in S if t['eng'] in REV]
med = sorted(t['p'] for t in revts)[len(revts)//2]
def qdiff_stat(ts):
    lo = [t['w'] for t in ts if t['p']<med]; hi = [t['w'] for t in ts if t['p']>=med]
    if not lo or not hi: return 0.0
    return sum(lo)/len(lo) - sum(hi)/len(hi)
blocks = collections.defaultdict(list)
for t in revts: blocks[t['t0']//3600].append(t)
bl = list(blocks.values()); rng = random.Random(11)
stats=[]
for _ in range(4000):
    samp=[]
    for _ in range(len(bl)): samp.extend(bl[rng.randrange(len(bl))])
    stats.append(qdiff_stat(samp))
stats.sort()
results['q4_rev_q_cheap_minus_exp'] = dict(
    median_split_at=round(med,3), diff=round(qdiff_stat(revts),4),
    ci95=[round(stats[int(.025*len(stats))],4), round(stats[int(.975*len(stats))],4)],
    note='q(p<median) - q(p>=median) within reversal family, 1h-block bootstrap')

# ---------------- Q5: drift conditioning ----------------
def driftbin(sd):
    if sd < -2: return 'adverse<-2bps'
    if sd > 2:  return 'favorable>+2bps'
    return 'neutral+-2bps'

def drift_table(trades):
    groups = collections.defaultdict(list)
    for t in trades: groups[driftbin(t['sdrift'])].append(t)
    out = {}
    for g, ts in sorted(groups.items()):
        n=len(ts); k=sum(int(t['w']) for t in ts); q=k/n
        qs=sum(qstar(t['p']) for t in ts)/n
        ev=sum(t['ev_ps'] for t in ts)/n
        pbar=sum(t['p'] for t in ts)/n
        lo,hi=wilson(k,n)
        out[g]=dict(n=n, q=round(q,4), p_mean=round(pbar,4), qstar=round(qs,4),
                    ev_c=round(100*ev,2), q_ci95=[round(lo,4),round(hi,4)])
    return out

# stratified (price-controlled) favorable-vs-adverse diff
def mh_drift(trades):
    groups = collections.defaultdict(lambda: {'fav':[0,0], 'adv':[0,0]})
    for t in trades:
        g = driftbin(t['sdrift'])
        if g.startswith('fav'): key='fav'
        elif g.startswith('adv'): key='adv'
        else: continue
        gg = groups[bucket(t['p'])][key]
        gg[0]+=int(t['w']); gg[1]+=1
    num=den=0.0; strata=[]
    for b,g in sorted(groups.items()):
        kf,nf=g['fav']; ka,na=g['adv']
        if nf>=10 and na>=10:
            qf,qa=kf/nf,ka/na
            var=qf*(1-qf)/nf+qa*(1-qa)/na
            if var>0:
                w=1/var; num+=w*(qf-qa); den+=w
                strata.append(dict(bucket=b,n_fav=nf,q_fav=round(qf,4),n_adv=na,q_adv=round(qa,4),
                                   diff=round(qf-qa,4)))
    if den==0: return None
    d=num/den; se=math.sqrt(1/den)
    return dict(diff_fav_minus_adv=round(d,4), se=round(se,4), z=round(d/se,2), strata=strata)

results['q5_drift'] = {
    'reversal_family_table': drift_table(revts),
    'momentum_family_table': drift_table([t for t in S if t['eng'] in MOM]),
    'reversal_family_stratified': mh_drift(revts),
    'momentum_family_stratified': mh_drift([t for t in S if t['eng'] in MOM]),
    'pooled_stratified': mh_drift(S),
}
# finer drift bins within reversal family, price<=0.53 (the live-relevant zone)
fine = collections.defaultdict(list)
for t in revts:
    if t['p']<=0.53:
        sd=t['sdrift']
        b = '<-6' if sd<-6 else '-6..-2' if sd<-2 else '-2..2' if sd<=2 else '2..6' if sd<=6 else '>6'
        fine[b].append(t)
ftab={}
for b,ts in fine.items():
    n=len(ts);k=sum(int(t['w']) for t in ts)
    ev=sum(t['ev_ps'] for t in ts)/n
    lo,hi=wilson(k,n)
    ftab[b]=dict(n=n,q=round(k/n,4),ev_c=round(100*ev,2),q_ci95=[round(lo,4),round(hi,4)],
                 p_mean=round(sum(t['p'] for t in ts)/n,4))
results['q5_rev_fine_drift_le53c'] = ftab

json.dump(results, open(os.path.join(HERE,'results.json'),'w'), indent=1)
print("wrote results.json")

# ------------- console summary -------------
print("\n=== Q1 decomposition (pooled) ===")
print(json.dumps(deco['pooled'], indent=1))
print("\n=== Q2 pooled calibration ===")
for r in cal['pooled_all']:
    print(f"{r['bucket']} n={r['n']:4d} q={r['q']:.3f} q*={r['qstar']:.3f} EV={r['ev_c']:+6.2f}c CI=[{r['ev_ci95_c'][0]:+.2f},{r['ev_ci95_c'][1]:+.2f}] clears={r['clears_fees']} qdd={r['q_dedup']:.3f}(n={r['n_dedup']})")
print("\n=== rev family calibration ===")
for r in cal['reversal_family']:
    print(f"{r['bucket']} n={r['n']:4d} q={r['q']:.3f} q*={r['qstar']:.3f} EV={r['ev_c']:+6.2f}c CI=[{r['ev_ci95_c'][0]:+.2f},{r['ev_ci95_c'][1]:+.2f}] clears={r['clears_fees']}")
print("\n=== bootstraps ===")
print(json.dumps(boot_lines, indent=1))
print("\n=== Q3 ===")
print(json.dumps({k:{kk:vv for kk,vv in v.items() if kk!='strata'} if isinstance(v,dict) and 'strata' in v else v for k,v in results['q3_side_asymmetry'].items() if v}, indent=1))
print("interval up rate:", results['q3_interval_up_rate'])
print("\n=== Q4 ===")
print(json.dumps(results['q4_cheapness'], indent=1))
print(json.dumps(results['q4_rev_q_cheap_minus_exp'], indent=1))
print("\n=== Q5 ===")
print(json.dumps({k:v for k,v in results['q5_drift'].items() if 'table' in k}, indent=1))
print(json.dumps({k:{kk:vv for kk,vv in v.items() if kk!='strata'} for k,v in results['q5_drift'].items() if v and 'strat' in k}, indent=1))
print(json.dumps(results['q5_rev_fine_drift_le53c'], indent=1))
