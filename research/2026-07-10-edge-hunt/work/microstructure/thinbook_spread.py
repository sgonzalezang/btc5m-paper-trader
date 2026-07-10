#!/usr/bin/env python3
"""Thin-book episode counting from bot.log (read-only), CLOB spread from signals.log,
and chronological stability check of the contrarian fill quantiles.
Output: thinbook_spread.json
"""
import json, re, math
from collections import Counter

S = '/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad'
W = S + '/work/microstructure'
BOT = '/Users/sgonzalez/btc5m-paper-trader/bot'

out = {}

# --- 1) thin-book SKIP lines in bot.log: count raw + collapse into episodes ---
pat = re.compile(r'^(\d\d):(\d\d):(\d\d)\s+\[(\w+)\] SKIP (\w+) .*book too thin at ≤(\d+)c \(only \$([\d.]+)')
raw = Counter(); episodes = Counter(); last = {}
nlines = 0
with open(BOT + '/bot.log', errors='replace') as f:
    for line in f:
        nlines += 1
        m = pat.match(line.strip())
        if not m: continue
        hh, mm, ss, eng, side, cap, avail = m.groups()
        sec = int(hh) * 3600 + int(mm) * 60 + int(ss)
        raw[eng] += 1
        # collapse: same engine within 300s (same interval) = one episode
        prev = last.get(eng)
        if prev is None or (sec - prev) % 86400 > 300:
            episodes[eng] += 1
        last[eng] = sec
print(f"bot.log lines={nlines}")
print("thin-book SKIP raw ticks by engine:", dict(raw))
print("thin-book episodes (collapsed to <=1 per 5min per engine):", dict(episodes))
out['thin_skip_raw'] = dict(raw); out['thin_skip_episodes'] = dict(episodes)

# also: total ENTER lines per engine for a denominator
epat = re.compile(r'^(\d\d):(\d\d):(\d\d)\s+\[(\w+)\] ENTER ')
enters = Counter()
with open(BOT + '/bot.log', errors='replace') as f:
    for line in f:
        m = epat.match(line.strip())
        if m: enters[m.group(4)] += 1
print("ENTER lines by engine (bot.log window):", dict(enters))
out['enters'] = dict(enters)

# --- 2) CLOB spread at signal time from signals.log ---
spreads = []; by_eng = {}
with open(BOT + '/signals.log', errors='replace') as f:
    for line in f:
        try: d = json.loads(line)
        except Exception: continue
        a, b = d.get('ask'), d.get('bid')
        if a is None or b is None: continue
        sp = round(a - b, 4)
        spreads.append(sp)
        by_eng.setdefault(d.get('engine'), []).append(sp)

def qtiles(xs, qs=(0.1, 0.25, 0.5, 0.75, 0.9, 0.95)):
    xs = sorted(xs); n = len(xs); o = {}
    for q in qs:
        k = q * (n - 1); fl = int(math.floor(k)); c = min(fl + 1, n - 1)
        o[f'p{int(q*100)}'] = round(xs[fl] + (k - fl) * (xs[c] - xs[fl]), 4)
    return o

print(f"\nsignals.log spreads: n={len(spreads)} {qtiles(spreads)}")
out['spread_all'] = dict(n=len(spreads), q=qtiles(spreads))
for e, xs in sorted(by_eng.items()):
    print(f"  {e}: n={len(xs)} median={sorted(xs)[len(xs)//2]}")
out['spread_by_engine'] = {e: dict(n=len(xs), med=sorted(xs)[len(xs) // 2]) for e, xs in by_eng.items()}

# --- 3) chronological stability of contrarian fill quantiles ---
sig = json.load(open(W + '/signal_sample.json'))
sig.sort(key=lambda s: s['t0'])
cut = sig[int(len(sig) * 2 / 3) - 1]['t0']
tr_ = [s for s in sig if s['t0'] <= cut]; te = [s for s in sig if s['t0'] > cut]
for lbl, rows in (('TRAIN', tr_), ('TEST', te)):
    c = [s['c20'] for s in rows]
    print(f"fill c20 {lbl}: n={len(rows)} {qtiles(c)} win={sum(s['won'] for s in rows)/len(rows):.3f} "
          f"avail<=55c={sum(1 for s in rows if s['c20']+0.01<=0.55)/len(rows):.3f}")
    out[f'c20_{lbl}'] = dict(n=len(rows), q=qtiles(c),
                             win=round(sum(s['won'] for s in rows) / len(rows), 3),
                             avail=round(sum(1 for s in rows if s['c20'] + 0.01 <= 0.55) / len(rows), 3))

# ledger fills split chronologically too
tr = json.load(open(S + '/data/trades.json'))
fam = sorted([t for t in tr if t['eng'] in ('reversal', 'reversal2', 'latentfire')
              and t['src'] == 'current' and t['status'] == 'settled'], key=lambda t: t['t0'])
cut2 = fam[int(len(fam) * 2 / 3) - 1]['t0']
for lbl, rows in (('TRAIN', [t for t in fam if t['t0'] <= cut2]), ('TEST', [t for t in fam if t['t0'] > cut2])):
    e = [t['entry'] for t in rows]
    w = sum(1 for t in rows if t['result'] == 'win') / len(rows)
    print(f"ledger entry {lbl}: n={len(rows)} {qtiles(e)} win={w:.3f}")
    out[f'ledger_entry_{lbl}'] = dict(n=len(rows), q=qtiles(e), win=round(w, 3))

json.dump(out, open(W + '/thinbook_spread.json', 'w'), indent=1)
print('\nsaved', W + '/thinbook_spread.json')
