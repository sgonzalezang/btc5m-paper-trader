#!/usr/bin/env python3
"""Adversarial verification of FINDING R5 (cost-structure autopsy / zero residual info).

Re-derives everything from RAW inputs (trades_unified.json + cb1m.json), never from
the analyst's intermediate files. Checks:
  A. Ledger integrity: dup keys, status/result census, entry=ask+slip identity,
     epoch units, result-vs-Coinbase resolution agreement, ties.
  B. Accounting decomposition re-derived independently; reconcile to analyst numbers.
  C. Survivorship: the 70 stopped trades (excluded by autopsy, coded as losses by
     attribution). Recover their TRUE hold-to-resolution outcome from Coinbase candles
     and recompute selection-at-mid including them.
  D. Statistical strength of the '+0.55c positive selection at mid' leg:
     1h-block bootstrap CI, share-weighted, pooled + momentum family, with/without
     stopped trades, under spread assumptions {0c, 1c, 2c}.
  E. Residual-continuation re-derivation from cb1m (own code): full-interval vs
     residual-4min continuation at theta=2/4/8bps; tie accounting; Jun26-Jul10 vs
     fresh Jul10-13 split; 1h-block bootstrap CIs.
  F. Momentum directional wr re-derivation (56.8% claim) with stopped trades at
     candle-derived outcomes instead of coded-as-loss.
Stdlib only.
"""
import json, math, random, collections, statistics, datetime, os

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = '/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data'
tr = json.load(open(os.path.join(DATA, 'trades_unified.json')))
cb = json.load(open(os.path.join(DATA, 'cb1m.json')))

def fee(p): return 0.07 * p * (1 - p)

R = {}

# ---------- A. ledger integrity ----------
A = {}
A['total'] = len(tr)
A['status'] = dict(collections.Counter(t.get('status') for t in tr))
A['result'] = dict(collections.Counter(str(t.get('result')) for t in tr))
seen = collections.Counter((t['eng'], t['t0'], t['side']) for t in tr)
A['dup_eng_t0_side'] = sum(1 for v in seen.values() if v > 1)
seen2 = collections.Counter((t['eng'], t['t0']) for t in tr)
A['dup_eng_t0'] = sum(1 for v in seen2.values() if v > 1)

# candle index; t assumed SECONDS
ct, co, cc = cb['t'], cb['o'], cb['c']
idx = {ts: i for i, ts in enumerate(ct)}
A['cb1m_span_utc'] = [datetime.datetime.utcfromtimestamp(min(ct)).isoformat(),
                      datetime.datetime.utcfromtimestamp(max(ct)).isoformat()]
A['trades_t0_span_utc'] = [datetime.datetime.utcfromtimestamp(min(t['t0'] for t in tr)).isoformat(),
                           datetime.datetime.utcfromtimestamp(max(t['t0'] for t in tr)).isoformat()]
A['t0_mod300_nonzero'] = sum(1 for t in tr if t['t0'] % 300)
A['at_ms_vs_t0_ok'] = sum(1 for t in tr if abs(t['at']/1000 - t['t0']) < 900)  # entry within 15min of t0

# entry = ask + slip identity
slip_exact = sum(1 for t in tr if abs(t['entry'] - (t['ask'] + 0.01)) < 1e-9)
A['entry_eq_ask_plus_1c'] = slip_exact
A['entry_gt_ask_1c'] = len(tr) - slip_exact
A['mean_actual_slip_c'] = round(100*statistics.fmean(t['entry']-t['ask'] for t in tr), 3)

# resolution cross-check: Coinbase open(t0) vs open(t0+300) vs 'result'
S = [t for t in tr if t.get('status') == 'settled' and t.get('result') in ('win', 'loss')]
agree = disagree = nocandle = tie = 0
for t in S:
    i0, i5 = idx.get(t['t0']), idx.get(t['t0'] + 300)
    if i0 is None or i5 is None:
        nocandle += 1; continue
    mv = co[i5] - co[i0]
    if mv == 0:
        tie += 1; continue
    cb_up = mv > 0
    won = t['result'] == 'win'
    side_up = t['side'] == 'up'
    pm_up = won == side_up
    if pm_up == cb_up: agree += 1
    else: disagree += 1
A['res_crosscheck'] = dict(n_winloss=len(S), agree=agree, disagree=disagree,
                           cb_tie=tie, no_candle=nocandle,
                           agree_rate=round(agree/(agree+disagree), 4))
# btcClose internal consistency
inc = 0
for t in S:
    if t.get('btcClose') is None or t.get('btcOpen') is None: continue
    d = t['btcClose'] - t['btcOpen']
    if d == 0: continue
    if ((d > 0) == (t['side'] == 'up')) != (t['result'] == 'win'): inc += 1
A['result_vs_btcfields_mismatch'] = inc
R['A_integrity'] = A

# ---------- B. accounting decomposition (independent re-derivation) ----------
def decomp(trades, spread_c=1.0):
    sh = sum(t['shares'] for t in trades)
    q_sw = sum(t['shares'] * t['w'] for t in trades) / sh
    p_sw = sum(t['shares'] * t['entry'] for t in trades) / sh
    a_sw = sum(t['shares'] * t['ask'] for t in trades) / sh
    mid_sw = a_sw - spread_c/200.0
    fees = sum(t['shares'] * fee(t['entry']) for t in trades)
    model = sum(t['shares'] * (t['w'] - t['entry'] - fee(t['entry'])) - 0.004 for t in trades)
    logged = sum(t['pnl'] for t in trades)
    return dict(n=len(trades), shares=round(sh, 1),
                sel_at_fill_c=round(100*(q_sw - p_sw), 2),
                sel_at_ask_c=round(100*(q_sw - a_sw), 2),
                sel_at_mid_c=round(100*(q_sw - mid_sw), 2),
                fee_c=round(100*fees/sh, 2),
                slip_c=round(100*(p_sw - a_sw), 2),
                halfspread_c=round(spread_c/2, 2),
                net_c=round(100*model/sh, 2),
                pnl_model=round(model, 2), pnl_logged=round(logged, 2))

MOM = {'loose','floor','band','value','fade','strict','capless','calm'}
for t in S:
    t['w'] = 1.0 if t['result'] == 'win' else 0.0
B = {}
B['pooled_winloss'] = decomp(S)
B['momentum_winloss'] = decomp([t for t in S if t['eng'] in MOM])
R['B_decomposition'] = B

# ---------- C. stopped trades: recover hold-to-res outcome from candles ----------
ST = [t for t in tr if t.get('result') == 'stopped']
rec = []
for t in ST:
    i0, i5 = idx.get(t['t0']), idx.get(t['t0'] + 300)
    if i0 is None or i5 is None: continue
    mv = co[i5] - co[i0]
    if mv == 0: continue   # tie: skip (would resolve Down on Polymarket typically; note)
    t['w'] = 1.0 if ((mv > 0) == (t['side'] == 'up')) else 0.0
    rec.append(t)
C = {}
C['n_stopped'] = len(ST)
C['n_recovered_from_candles'] = len(rec)
C['stopped_would_have_won'] = int(sum(t['w'] for t in rec))
C['stopped_wr_hold_to_res'] = round(sum(t['w'] for t in rec)/len(rec), 4) if rec else None
C['stopped_ledger_pnl'] = round(sum(t['pnl'] for t in ST), 2)
C['stopped_hold_to_res_model_pnl'] = round(sum(
    t['shares']*(t['w']-t['entry']-fee(t['entry']))-0.004 for t in rec), 2)
# decomposition including stopped at hold-to-res outcomes
SA = S + rec
C['pooled_incl_stopped'] = decomp(SA)
C['momentum_incl_stopped'] = decomp([t for t in SA if t['eng'] in MOM])
R['C_stopped_survivorship'] = C

# ---------- D. block-bootstrap CI on selection at mid ----------
def boot_sel(trades, spread_c, nboot=4000, seed=13):
    by = collections.defaultdict(list)
    for t in trades:
        mid = t['ask'] - spread_c/200.0
        by[t['t0'] // 3600].append((t['shares']*(t['w'] - mid), t['shares']))
    blocks = list(by.values()); rng = random.Random(seed)
    pt = sum(x for b in blocks for x, _ in b) / sum(s for b in blocks for _, s in b)
    ms = []
    for _ in range(nboot):
        num = den = 0.0
        for _ in range(len(blocks)):
            b = blocks[rng.randrange(len(blocks))]
            num += sum(x for x, _ in b); den += sum(s for _, s in b)
        ms.append(num/den)
    ms.sort()
    return dict(sel_c=round(100*pt, 2),
                ci95_c=[round(100*ms[int(.025*len(ms))], 2), round(100*ms[int(.975*len(ms))], 2)],
                p_le0=round(sum(1 for m in ms if m <= 0)/len(ms), 4))

D = {}
for tag, pool in [('pooled_winloss', S), ('pooled_incl_stopped', SA),
                  ('momentum_incl_stopped', [t for t in SA if t['eng'] in MOM])]:
    D[tag] = {f'spread_{sc:.0f}c': boot_sel(pool, sc) for sc in (0.0, 1.0, 2.0)}
R['D_selection_bootstrap'] = D

# ---------- E. residual continuation, re-derived ----------
def boot_rate(by, nboot=4000, seed=29):
    blocks = list(by.values()); rng = random.Random(seed)
    ms = []
    for _ in range(nboot):
        s = []
        for _ in range(len(blocks)):
            s.extend(rng.choice(blocks))
        ms.append(statistics.fmean(s))
    ms.sort()
    return [round(ms[int(.025*len(ms))], 4), round(ms[int(.975*len(ms))], 4)]

JUN26 = int(datetime.datetime(2026, 6, 26, tzinfo=datetime.timezone.utc).timestamp())
JUL10 = int(datetime.datetime(2026, 7, 10, tzinfo=datetime.timezone.utc).timestamp())
E = {'epoch_check_jun26': JUN26}

def resid(theta, lo, hi):
    full_b, res_b = collections.defaultdict(list), collections.defaultdict(list)
    full_tie = 0
    for t0 in range(min(ct)//300*300 + 300, max(ct), 300):
        if not (lo <= t0 < hi): continue
        i0, i5 = idx.get(t0), idx.get(t0+300)
        if i0 is None or i5 is None: continue
        drift = cc[i0]/co[i0] - 1
        if abs(drift) < theta: continue
        mv = co[i5] - co[i0]
        if mv == 0:
            full_tie += 1
        else:
            full_b[t0//3600].append(1.0 if (drift > 0) == (mv > 0) else 0.0)
        r = co[i5] - cc[i0]
        if r != 0:
            res_b[t0//3600].append(1.0 if (drift > 0) == (r > 0) else 0.0)
    fv = [v for b in full_b.values() for v in b]
    rv = [v for b in res_b.values() for v in b]
    return dict(n_full=len(fv), full_cont=round(statistics.fmean(fv), 4) if fv else None,
                full_ties_excl=full_tie,
                full_ci=boot_rate(full_b),
                n_resid=len(rv), resid_cont=round(statistics.fmean(rv), 4) if rv else None,
                resid_ci=boot_rate(res_b, seed=31))

for th, tag in [(2e-4, '2bps'), (4e-4, '4bps'), (8e-4, '8bps')]:
    E[f'all_jun26plus_{tag}'] = resid(th, JUN26, 1 << 40)
for th, tag in [(2e-4, '2bps'), (4e-4, '4bps')]:
    E[f'jun26_jul10_{tag}'] = resid(th, JUN26, JUL10)
    E[f'fresh_jul10_13_{tag}'] = resid(th, JUL10, 1 << 40)
# also: is analyst tie-handling (>= counts as up) material?
R['E_residual'] = E

# ---------- F. momentum directional wr with recovered stops ----------
F = {}
FAM4 = {'loose','floor','band','value'}
def wrblock(trades):
    by = collections.defaultdict(list)
    for t in trades: by[t['t0']//3600].append(t['w'])
    v = [x for b in by.values() for x in b]
    return dict(n=len(v), wr=round(statistics.fmean(v), 4), ci=boot_rate(by, seed=17))
F['mom_dir_winloss_only'] = wrblock([t for t in S if t['eng'] in FAM4])
F['mom_dir_incl_recovered_stops'] = wrblock([t for t in SA if t['eng'] in FAM4])
F['mom_dir_stops_as_loss_analyst'] = wrblock(
    [t for t in S if t['eng'] in FAM4] +
    [dict(t, w=0.0) for t in ST if t['eng'] in FAM4])
# avg entry + breakeven
p4 = statistics.fmean(t['entry'] for t in SA if t['eng'] in FAM4)
F['avg_entry'] = round(p4, 4); F['breakeven_q'] = round(p4 + fee(p4), 4)
R['F_momentum_wr'] = F

json.dump(R, open(os.path.join(HERE, 'results.json'), 'w'), indent=1)
print(json.dumps(R, indent=1))
