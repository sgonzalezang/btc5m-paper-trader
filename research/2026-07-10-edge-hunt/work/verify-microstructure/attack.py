#!/usr/bin/env python3
"""Adversarial checks on the fill-model finding.
A) Is the join's 'ask ~2c below mid' a cap-censoring artifact? Condition d_ask_c20 on c20 level.
B) Fee audit: does ledger feeEntry match the exact formula shares*0.07*p*(1-p)? Any exit fees?
C) Availability vs live fillability consistency: which of the 82 eligible live intervals were
   skipped, and what did the ledger see there (via pm sample where joinable)?
D) What would a backtest lose if it assumed fills at c20+1c but skipped >55c: EV at wtd fill vs
   at the c20-based fill for the same intervals (join set)?
E) Missing p20s in pm sample (None dropped) — count them among >=12bps signals.
"""
import json
from collections import defaultdict

S = '/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad'
pm = json.load(open(S + '/data/pm_prices_sample.json'))
cb = json.load(open(S + '/data/cb5m.json'))
tr = json.load(open(S + '/data/trades.json'))
t = [int(x) for x in cb['t']]; o = cb['o']
idx = {tt: i for i, tt in enumerate(t)}

def prior_bps(t0):
    i = idx.get(t0); j = idx.get(t0 - 300)
    if i is None or j is None: return None
    return (o[i] - o[j]) / o[j] * 1e4

# E) None p20 among signals
none20 = 0; tot = 0
for r in pm:
    b = prior_bps(r['t0'])
    if b is None or abs(b) < 12: continue
    tot += 1
    if r['p20'] is None: none20 += 1
print(f"E) signals with missing p20: {none20}/{tot}")

sig = {}
for r in pm:
    b = prior_bps(r['t0'])
    if b is None or abs(b) < 12 or r['p20'] is None: continue
    c20 = r['p20'] if b < 0 else 1 - r['p20']
    won = r['up_won'] if b < 0 else 1 - r['up_won']
    sig[r['t0']] = (b, c20, won)

fam = [x for x in tr if x['src'] == 'current' and x['status'] == 'settled'
       and x['eng'] in ('reversal', 'reversal2', 'latentfire')]

# A) join conditioned on c20 level
lo_d, hi_d = [], []
for x in fam:
    s = sig.get(x['t0'])
    if not s: continue
    d = x['ask'] - s[1]
    (lo_d if s[1] <= 0.54 else hi_d).append((s[1], x['ask'], d))
for lbl, ds in (('c20<=.54 (uncensored-fillable)', lo_d), ('c20>.54 (above cap)', hi_d)):
    if ds:
        dd = sorted(d for _, _, d in ds)
        print(f"A) {lbl}: n={len(ds)} median d={dd[len(dd)//2]:+.4f} mean={sum(dd)/len(dd):+.4f}")
        if lbl.startswith('c20>'):
            for c, a, d in ds: print(f"     c20={c:.3f} ask={a:.3f} d={d:+.3f}")

# B) fee audit
bad = 0; mx = 0
for x in fam:
    exp = x['shares'] * 0.07 * x['entry'] * (1 - x['entry'])
    got = x.get('feeEntry') or 0
    err = abs(exp - got)
    mx = max(mx, err)
    if err > 0.02 * max(exp, 0.01): bad += 1
exf = sum(x.get('feeExit') or 0 for x in fam)
print(f"B) feeEntry mismatches>2%: {bad}/{len(fam)} max abs err ${mx:.4f}; total feeExit=${exf:.2f}")

# C) live-window skipped intervals: what does pm sample say they cost?
lo, hi = min(x['t0'] for x in fam), max(x['t0'] for x in fam)
elig = [tt for tt in t if lo <= tt <= hi and (b := prior_bps(tt)) is not None and abs(b) >= 12]
ent = set(x['t0'] for x in fam)
skipped = [tt for tt in elig if tt not in ent]
print(f"C) skipped live intervals: {len(skipped)}; of those in pm sample: "
      f"{[ (tt, round(sig[tt][1],3)) for tt in skipped if tt in sig ]}")
# entered intervals with c20>.54 (live got in below cap even though minute-mid was rich)
rich_entered = [(tt, round(sig[tt][1], 3)) for tt in ent if tt in sig and sig[tt][1] > 0.54]
print(f"   entered-despite-rich-c20: {rich_entered}")

# D) EV consequence: for join set, compare EV(q, fill) using realized outcomes at
#    ledger entry vs c20+1c fill (backtester's naive price), skipping c20+1c>.55
def ev(qwin, p): return qwin - p - 0.07 * p * (1 - p)
je, jc = [], []
for x in fam:
    s = sig.get(x['t0'])
    if not s: continue
    w = 1.0 if x['result'] == 'win' else 0.0
    je.append(w - x['entry'] - 0.07 * x['entry'] * (1 - x['entry']))
    f = s[1] + 0.01
    if f <= 0.55:
        jc.append(w - f - 0.07 * f * (1 - f))
print(f"D) join-set per-share EV: ledger-fill mean={sum(je)/len(je):+.4f} (n={len(je)}) "
      f"vs c20+1c-fill mean={sum(jc)/len(jc):+.4f} (n={len(jc)})")

# also: pooled family EV per share at actual fills (sanity vs PnL/$)
tot_sh = sum(x['shares'] for x in fam)
evps = sum(x['pnl'] for x in fam) / tot_sh
print(f"   pooled family realized EV/share = {evps:+.4f}")
