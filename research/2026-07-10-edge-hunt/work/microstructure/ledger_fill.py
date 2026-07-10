#!/usr/bin/env python3
"""(c) Ledger autopsy per engine: realized win rate vs entry paid; decompose PnL into
    mispricing-paid vs fee. (d) Thin-book frequency + REALISTIC fill-price distribution
    for contrarian ~50c entries right after a >=12bps prior move.
Outputs: ledger_autopsy.json, fill_dist.json + printed tables.
"""
import json, math
from collections import Counter, defaultdict

S = '/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad'
W = S + '/work/microstructure'

tr  = json.load(open(S + '/data/trades.json'))
pm  = json.load(open(S + '/data/pm_prices_sample.json'))
cb  = json.load(open(S + '/data/cb5m.json'))
cbt, cbo, cbc = cb['t'], cb['o'], cb['c']
cbi = {int(t): i for i, t in enumerate(cbt)}

def prior_move_bps(t0):
    i = cbi.get(t0); j = cbi.get(t0 - 300)
    if i is None or j is None: return None
    return (cbo[i] - cbo[j]) / cbo[j] * 1e4

def qtiles(xs, qs=(0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95)):
    xs = sorted(xs); n = len(xs)
    out = {}
    for q in qs:
        k = q * (n - 1); f = int(math.floor(k)); c = min(f + 1, n - 1)
        out[f'p{int(q*100)}'] = round(xs[f] + (k - f) * (xs[c] - xs[f]), 4)
    return out

def qstar(p): return p + 0.07 * p * (1 - p)

# ---------------- (c) ledger autopsy ----------------
print("=" * 100)
print("(c) LEDGER AUTOPSY — settled win/loss trades, per engine (current post-reset book unless noted)")
print("=" * 100)
autopsy = {}
hdr = f"{'eng':11s}{'src':10s}{'n':>5s}{'winrate':>8s}{'meanEntry':>10s}{'q*(p̄)':>8s}{'edge_pp':>8s}" \
      f"{'PnL$':>9s}{'misprice$':>10s}{'fee$':>8s}{'stop$':>8s}{'hedge$':>8s}"
print(hdr)
rows_by = defaultdict(list)
for t in tr:
    if t['status'] != 'settled': continue
    rows_by[(t['eng'], t['src'])].append(t)
    rows_by[(t['eng'], 'ALLSRC')].append(t)

for (eng, src) in sorted(rows_by, key=lambda k: (k[0], k[1])):
    rows = rows_by[(eng, src)]
    clean = [t for t in rows if t.get('result') in ('win', 'loss') and not t.get('hedge')]
    stopped = [t for t in rows if t.get('result') == 'stopped']
    hedged = [t for t in rows if t.get('hedge') and t.get('result') in ('win', 'loss')]
    if not clean: continue
    n = len(clean)
    wr = sum(1 for t in clean if t['result'] == 'win') / n
    # share-weighted mean entry
    sh = sum(t['shares'] for t in clean)
    pbar = sum(t['shares'] * t['entry'] for t in clean) / sh
    mis = sum(t['shares'] * ((1.0 if t['result'] == 'win' else 0.0) - t['entry']) for t in clean)
    fee = sum((t.get('feeEntry') or 0) + (t.get('feeExit') or 0) + (t.get('gas') or 0) for t in clean)
    pnl = sum(t['pnl'] for t in clean)
    stp = sum(t['pnl'] for t in stopped)
    hdg = sum(t['pnl'] for t in hedged)
    edge_pp = (wr - qstar(pbar)) * 100
    autopsy[f'{eng}|{src}'] = dict(n=n, winrate=round(wr, 4), mean_entry=round(pbar, 4),
                                   qstar=round(qstar(pbar), 4), edge_pp=round(edge_pp, 2),
                                   pnl=round(pnl, 2), mispricing=round(mis, 2), fee=round(fee, 2),
                                   n_stopped=len(stopped), stopped_pnl=round(stp, 2),
                                   n_hedged=len(hedged), hedged_pnl=round(hdg, 2))
    if src in ('current', 'ALLSRC'):
        print(f"{eng:11s}{src:10s}{n:5d}{wr:8.3f}{pbar:10.3f}{qstar(pbar):8.3f}{edge_pp:8.1f}"
              f"{pnl:9.0f}{mis:10.0f}{fee:8.0f}{stp:8.0f}{hdg:8.0f}")

# momentum family pooled (current): loose+floor+band+value
mom = [t for t in tr if t['status'] == 'settled' and t['src'] == 'current'
       and t['eng'] in ('loose', 'floor', 'band', 'value')
       and t.get('result') in ('win', 'loss') and not t.get('hedge')]
n = len(mom); wr = sum(1 for t in mom if t['result'] == 'win') / n
sh = sum(t['shares'] for t in mom)
pbar = sum(t['shares'] * t['entry'] for t in mom) / sh
mis = sum(t['shares'] * ((1.0 if t['result'] == 'win' else 0.0) - t['entry']) for t in mom)
fee = sum((t.get('feeEntry') or 0) + (t.get('feeExit') or 0) + (t.get('gas') or 0) for t in mom)
pnl = sum(t['pnl'] for t in mom)
print(f"\nMOMENTUM POOLED (loose+floor+band+value, current): n={n} winrate={wr:.4f} "
      f"share-wtd entry={pbar:.4f} q*={qstar(pbar):.4f}")
print(f"  PnL ${pnl:.0f} = mispricing ${mis:.0f} + fees ${-fee:.0f}  "
      f"(mispricing share {mis/(mis-fee)*100 if (mis-fee)!=0 else 0:.0f}% of loss)")
autopsy['MOMENTUM_POOLED|current'] = dict(n=n, winrate=round(wr, 4), mean_entry=round(pbar, 4),
                                          qstar=round(qstar(pbar), 4), pnl=round(pnl, 2),
                                          mispricing=round(mis, 2), fee=round(fee, 2))

# reversal family pooled (current)
rev = [t for t in tr if t['status'] == 'settled' and t['src'] == 'current'
       and t['eng'] in ('reversal', 'reversal2', 'latentfire')
       and t.get('result') in ('win', 'loss') and not t.get('hedge')]
n = len(rev); wr = sum(1 for t in rev if t['result'] == 'win') / n
sh = sum(t['shares'] for t in rev)
pbar = sum(t['shares'] * t['entry'] for t in rev) / sh
mis = sum(t['shares'] * ((1.0 if t['result'] == 'win' else 0.0) - t['entry']) for t in rev)
fee = sum((t.get('feeEntry') or 0) + (t.get('feeExit') or 0) + (t.get('gas') or 0) for t in rev)
pnl = sum(t['pnl'] for t in rev)
print(f"REVERSAL POOLED (reversal+reversal2+latentfire, current): n={n} winrate={wr:.4f} "
      f"entry={pbar:.4f} q*={qstar(pbar):.4f}  PnL ${pnl:.0f} = misprice ${mis:.0f} - fee ${fee:.0f}")
autopsy['REVERSAL_POOLED|current'] = dict(n=n, winrate=round(wr, 4), mean_entry=round(pbar, 4),
                                          qstar=round(qstar(pbar), 4), pnl=round(pnl, 2),
                                          mispricing=round(mis, 2), fee=round(fee, 2))
json.dump(autopsy, open(W + '/ledger_autopsy.json', 'w'), indent=1)

# ---------------- (d) thin book ----------------
print("\n" + "=" * 100)
print("(d) THIN BOOK")
print("=" * 100)
revs  = {t['t0']: t for t in tr if t['eng'] == 'reversal'  and t['src'] == 'current'}
revs2 = {t['t0']: t for t in tr if t['eng'] == 'reversal2' and t['src'] == 'current'}
both = set(revs) & set(revs2)
only2 = set(revs2) - set(revs)   # thin book at open: only gamma-fallback engine could fire
only1 = set(revs) - set(revs2)
print(f"reversal n={len(revs)}  reversal2 n={len(revs2)}  both={len(both)}  only-rev2(gamma-fallback)={len(only2)}  only-rev1={len(only1)}")
# gamma-fallback share = trades reversal2 made that reversal (identical signal, real-book-only) couldn't
gamma_fallback_rate = len(only2) / len(revs2) if revs2 else None
print(f"gamma-fallback (one-sided book at open) share of reversal2 entries: {gamma_fallback_rate:.3f}")
# how do only2 fills price vs both?
for lbl, keys in (('both-books', both), ('gamma-fallback', only2)):
    if not keys: continue
    e = [revs2[k]['entry'] for k in keys]
    w = [1 if revs2[k]['result'] == 'win' else 0 for k in keys if revs2[k].get('result') in ('win', 'loss')]
    print(f"  rev2 {lbl}: n={len(e)} entry {qtiles(e)} winrate={sum(w)/len(w) if w else None:.3f}")

# ---------------- (d2) contrarian ~50c fill-price distribution ----------------
print("\n" + "=" * 100)
print("(d2) FILL-PRICE DISTRIBUTION for contrarian entries right after >=12bps prior move")
print("=" * 100)
fill = {}

# 1) uncensored book snapshot ~20-60s in (pm sample, mid-ish prices-history points)
sig = []
for r in pm:
    b = prior_move_bps(r['t0'])
    if b is None or abs(b) < 12: continue
    c20 = r['p20'] if b < 0 else round(1 - r['p20'], 4)   # contrarian side price
    c60 = r['p60'] if b < 0 else round(1 - r['p60'], 4)
    won = r['up_won'] if b < 0 else 1 - r['up_won']       # contrarian side won?
    sig.append(dict(t0=r['t0'], prior_bps=round(b, 2), c20=c20, c60=c60, won=won))
print(f"pm-sample signal intervals (|prior|>=12bps): n={len(sig)} of 216")
c20s = [s['c20'] for s in sig]; c60s = [s['c60'] for s in sig]
print(f"  contrarian mid @~20s: {qtiles(c20s)}")
print(f"  contrarian mid @~60s: {qtiles(c60s)}")
cap = 0.55
avail = sum(1 for s in sig if s['c20'] + 0.01 <= cap) / len(sig)
print(f"  share with c20+1c slip <= 55c cap: {avail:.3f}")
print(f"  contrarian win rate in sample: {sum(s['won'] for s in sig)/len(sig):.3f} (n={len(sig)})")
fill['pm_sample'] = dict(n=len(sig), c20_q=qtiles(c20s), c60_q=qtiles(c60s),
                         avail_le_55c=round(avail, 3),
                         win_rate=round(sum(s['won'] for s in sig) / len(sig), 3))
# by prior-move size
for lo, hi in ((12, 16), (16, 24), (24, 1e9)):
    sub = [s for s in sig if lo <= abs(s['prior_bps']) < hi]
    if len(sub) < 5: continue
    print(f"  prior {lo}-{hi if hi<1e9 else 'inf'}bps: n={len(sub)} c20 median={sorted(x['c20'] for x in sub)[len(sub)//2]:.3f} "
          f"win={sum(s['won'] for s in sub)/len(sub):.3f}")

# 2) actual fills from the live reversal family (real CLOB ask walks + 1c slip; censored at 55c)
fam = [t for t in tr if t['eng'] in ('reversal', 'reversal2', 'latentfire') and t['src'] == 'current'
       and t['status'] == 'settled']
asks = [t['ask'] for t in fam]; ents = [t['entry'] for t in fam]
secs = [t['entrySec'] for t in fam if t.get('entrySec') is not None]
print(f"\nledger reversal-family actual fills: n={len(fam)} (CENSORED at 55c cap)")
print(f"  ask   : {qtiles(asks)}")
print(f"  entry : {qtiles(ents)}   (entry = book-walk avg + 1c)")
print(f"  entrySec: {qtiles(secs)}")
wr = sum(1 for t in fam if t['result'] == 'win') / len(fam)
sh = sum(t['shares'] for t in fam)
pbar = sum(t['shares'] * t['entry'] for t in fam) / sh
print(f"  winrate={wr:.4f} at share-wtd entry {pbar:.4f} (q*={qstar(pbar):.4f})")
fill['ledger_family'] = dict(n=len(fam), ask_q=qtiles(asks), entry_q=qtiles(ents),
                             entrySec_q=qtiles(secs), winrate=round(wr, 4),
                             wtd_entry=round(pbar, 4))

# 3) join: same t0 in pm sample and ledger → measured (actual ask) - (contrarian p20 mid)
join = []
fam_by_t0 = defaultdict(list)
for t in fam: fam_by_t0[t['t0']].append(t)
for s in sig:
    for t in fam_by_t0.get(s['t0'], []):
        join.append(dict(t0=s['t0'], ask=t['ask'], entry=t['entry'], c20=s['c20'],
                         d_ask_c20=round(t['ask'] - s['c20'], 4), eng=t['eng'],
                         entrySec=t.get('entrySec')))
if join:
    ds = [j['d_ask_c20'] for j in join]
    print(f"\njoined t0s (ledger fill vs pm-sample c20): n={len(join)}")
    print(f"  ask - c20_mid: {qtiles(ds)}  mean={sum(ds)/len(ds):+.4f}")
    fill['join'] = dict(n=len(join), d_ask_c20_q=qtiles(ds), mean=round(sum(ds) / len(ds), 4))

# 4) fillability: eligible signals in live window vs actual entries
t0_lo = min(t['t0'] for t in fam); t0_hi = max(t['t0'] for t in fam)
elig = [t0 for t0 in (int(x) for x in cbt) if t0_lo <= t0 <= t0_hi
        and (lambda b: b is not None and abs(b) >= 12)(prior_move_bps(t0))]
ent_t0 = set(t['t0'] for t in fam)
print(f"\nlive window {t0_lo}..{t0_hi}: eligible |prior|>=12bps intervals={len(elig)}, "
      f"reversal-family entered {len(ent_t0)} distinct ({len(ent_t0)/len(elig)*100:.0f}%)")
fill['fillability'] = dict(eligible=len(elig), entered=len(ent_t0),
                           rate=round(len(ent_t0) / len(elig), 3))
json.dump(fill, open(W + '/fill_dist.json', 'w'), indent=1)
json.dump(sig, open(W + '/signal_sample.json', 'w'), indent=1)
print('\nsaved', W + '/ledger_autopsy.json', W + '/fill_dist.json', W + '/signal_sample.json')
