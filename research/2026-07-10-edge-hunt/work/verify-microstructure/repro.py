#!/usr/bin/env python3
"""Independent reproduction of the FILL MODEL finding (microstructure family).
Recomputes from raw data/: uncensored c20 distribution, availability <=55c,
ledger fill quantiles, share-wtd mean, join delta, fillability, pooled PnL/fees,
and the last-third win rate. Written from scratch (not copied from ledger_fill.py logic
beyond the shared definitions in BRIEF.md)."""
import json, math
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

def q(xs, ps):
    xs = sorted(xs); n = len(xs); out = {}
    for p in ps:
        k = p * (n - 1); f = int(k); c = min(f + 1, n - 1)
        out[p] = xs[f] + (k - f) * (xs[c] - xs[f])
    return out

def qstar(p): return p + 0.07 * p * (1 - p)

# --- 1. uncensored contrarian c20 distribution ---
sig = []
for r in pm:
    b = prior_bps(r['t0'])
    if b is None or abs(b) < 12: continue
    if r['p20'] is None: continue
    c20 = r['p20'] if b < 0 else 1 - r['p20']
    won = r['up_won'] if b < 0 else 1 - r['up_won']
    sig.append((r['t0'], b, c20, won))
print(f"signals n={len(sig)} of {len(pm)}")
c20s = [s[2] for s in sig]
qq = q(c20s, [.05, .25, .5, .75, .95])
print("c20 quantiles:", {k: round(v, 4) for k, v in qq.items()})
avail = sum(1 for s in sig if s[2] + 0.01 <= 0.55) / len(sig)
print(f"avail (c20+1c <= 55c): {avail:.4f}")
print(f"contrarian win rate in sample: {sum(s[3] for s in sig)/len(sig):.4f}")
# by move size
for lo, hi in ((12, 16), (16, 1e9)):
    sub = sorted(s[2] for s in sig if lo <= abs(s[1]) < hi)
    if sub: print(f"  prior {lo}-{hi}: n={len(sub)} median c20={sub[len(sub)//2]:.4f}")

# --- 2. ledger reversal-family fills ---
fam = [x for x in tr if x['src'] == 'current' and x['status'] == 'settled'
       and x['eng'] in ('reversal', 'reversal2', 'latentfire')]
print(f"\nledger family n={len(fam)}")
ents = [x['entry'] for x in fam]
qq = q(ents, [.05, .1, .25, .5, .75, .9, .95])
print("entry quantiles:", {k: round(v, 4) for k, v in qq.items()})
sh = sum(x['shares'] for x in fam)
wtd = sum(x['shares'] * x['entry'] for x in fam) / sh
print(f"share-wtd mean entry: {wtd:.4f}  q*: {qstar(wtd):.4f}")
clean = [x for x in fam if x.get('result') in ('win', 'loss') and not x.get('hedge')]
wr = sum(1 for x in clean if x['result'] == 'win') / len(clean)
pnl = sum(x['pnl'] for x in clean)
fee = sum((x.get('feeEntry') or 0) + (x.get('feeExit') or 0) + (x.get('gas') or 0) for x in clean)
mis = sum(x['shares'] * ((1 if x['result'] == 'win' else 0) - x['entry']) for x in clean)
print(f"clean n={len(clean)} winrate={wr:.4f} PnL=${pnl:.0f} = misprice ${mis:.0f} - fee ${fee:.0f}")
# results / fillFrac / entrySec / hedges / stops audit
resc = defaultdict(int)
for x in fam: resc[x.get('result')] += 1
print("results:", dict(resc), " hedged:", sum(1 for x in fam if x.get('hedge')))
ff = [x.get('fillFrac') for x in fam if x.get('fillFrac') is not None]
if ff: print(f"fillFrac: n={len(ff)} min={min(ff)} mean={sum(ff)/len(ff):.3f} frac<1: {sum(1 for f in ff if f<0.999)/len(ff):.3f}")
secs = sorted(x['entrySec'] for x in fam if x.get('entrySec') is not None)
print(f"entrySec median: {secs[len(secs)//2]}")
# entries above cap+slip?
print(f"entries > .56: {sum(1 for e in ents if e > 0.56)}  asks > .55: {sum(1 for x in fam if x['ask'] > 0.55001)}")

# --- 3. last-third win rate ---
fam_sorted = sorted(clean, key=lambda x: x['t0'])
n3 = len(fam_sorted) // 3
last = fam_sorted[-n3:]
wl = sum(1 for x in last if x['result'] == 'win') / len(last)
print(f"\nlast-third: n={len(last)} winrate={wl:.4f}")
# chronological 2/3-1/3 split fill median stability
tw = [x['entry'] for x in fam_sorted[:2 * len(fam_sorted) // 3]]
te = [x['entry'] for x in fam_sorted[2 * len(fam_sorted) // 3:]]
print(f"entry median train={sorted(tw)[len(tw)//2]:.3f} test={sorted(te)[len(te)//2]:.3f}")

# --- 4. join ledger fills to pm-sample c20 at same t0 ---
sig_by = {s[0]: s for s in sig}
ds = []
for x in fam:
    s = sig_by.get(x['t0'])
    if s: ds.append(x['ask'] - s[2])
if ds:
    qq = q(ds, [.25, .5, .75])
    print(f"\njoin n={len(ds)} ask-c20 median={qq[.5]:+.4f} mean={sum(ds)/len(ds):+.4f}")

# --- 5. fillability in live window ---
lo, hi = min(x['t0'] for x in fam), max(x['t0'] for x in fam)
elig = [tt for tt in t if lo <= tt <= hi and (b := prior_bps(tt)) is not None and abs(b) >= 12]
ent = set(x['t0'] for x in fam)
print(f"\nlive window eligible={len(elig)} entered={len(ent)} rate={len(ent)/len(elig):.3f}")
