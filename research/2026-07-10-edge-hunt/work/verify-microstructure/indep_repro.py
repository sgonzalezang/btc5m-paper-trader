import json, math
S='/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad'

def q(xs, p):
    xs = sorted(xs); n = len(xs)
    if n == 0: return None
    k = (n-1)*p; f = math.floor(k); c = min(f+1, n-1)
    return xs[f] + (xs[c]-xs[f])*(k-f)

cb = json.load(open(S+'/data/cb5m.json'))
t, o, c = cb['t'], cb['o'], cb['c']
idx = {tt: i for i, tt in enumerate(t)}

pm = json.load(open(S+'/data/pm_prices_sample.json'))
print("pm n=", len(pm), "span_days=", (pm[-1]['t0']-pm[0]['t0'])/86400)

# buffered open-to-open prior move for each pm market t0
sig = []
for m in pm:
    i = idx.get(m['t0'])
    if i is None or i == 0 or t[i]-t[i-1] != 300: continue
    r = (o[i]-o[i-1])/o[i-1]
    m2 = dict(m); m2['prior'] = r; m2['i'] = i
    sig.append(m2)
print("pm joined to cb5m:", len(sig))

TH = 0.0012
signals = [m for m in sig if abs(m['prior']) >= TH]
print("signal intervals (|prior|>=12bps):", len(signals))

# contrarian side price at ~20s: prior up -> buy Down = 1-p20 ; prior down -> buy Up = p20
c20 = []
for m in signals:
    if m.get('p20') is None: continue
    px = (1-m['p20']) if m['prior'] > 0 else m['p20']
    c20.append((m['t0'], px, m['prior']))
print("n with p20:", len(c20))
xs = [x[1] for x in c20]
for pp in (0.05,0.25,0.5,0.75,0.95):
    print(f"  c20 p{int(pp*100)}: {q(xs,pp):.4f}")
avail = sum(1 for x in xs if x <= 0.55)/len(xs)
print(f"  availability c20<=0.55: {avail:.4f}  ({sum(1 for x in xs if x<=0.55)}/{len(xs)})")
avail56 = sum(1 for x in xs if x <= 0.56)/len(xs)
print(f"  availability c20<=0.56 (cap+slip variant): {avail56:.4f}")
# by prior-move size
small = [x[1] for x in c20 if 0.0012 <= abs(x[2]) < 0.0016]
big   = [x[1] for x in c20 if abs(x[2]) >= 0.0016]
print(f"  c20 median 12-16bps: {q(small,0.5):.4f} (n={len(small)}) | >=16bps: {q(big,0.5):.4f} (n={len(big)})")

# ---- ledger fills ----
tr = json.load(open(S+'/data/trades.json'))
rev = [x for x in tr if x.get('eng') in ('reversal','reversal2','latentfire')]
print("\nreversal-family trades total:", len(rev))
from collections import Counter
print(" by src:", Counter(x.get('src') for x in rev))
print(" by eng:", Counter(x.get('eng') for x in rev))
# "live" = current book? check src values
cur = [x for x in rev if x.get('src') and 'pre' not in str(x.get('src')) and 'bak' not in str(x.get('src'))]
print(" current-book count:", len(cur), Counter(x.get('src') for x in cur))

def led_stats(rows, label):
    e = [x['entry'] for x in rows if x.get('entry') is not None]
    if not e: print(label, "no entries"); return
    sh = [(x['entry'], x.get('shares', 0)) for x in rows if x.get('entry') is not None]
    wm = sum(a*b for a,b in sh)/sum(b for _,b in sh)
    print(f"{label}: n={len(e)} p5={q(e,.05):.3f} p10={q(e,.10):.3f} p25={q(e,.25):.3f} p50={q(e,.5):.3f} p75={q(e,.75):.3f} p90={q(e,.9):.3f} p95={q(e,.95):.3f} share-wtd mean={wm:.4f}")
led_stats(rev, "ALL rev-family")
led_stats(cur, "current-book rev-family")

# entrySec: at - t0*1000
esec = [ (x['at']/1000 - x['t0']) for x in cur if x.get('at') and x.get('t0')]
if esec: print(f"entrySec: p50={q(esec,.5):.1f} p90={q(esec,.9):.1f}")

# ---- t0-join: ledger ask vs pm minute-mid (contrarian side p20) ----
pmidx = {m['t0']: m for m in pm}
joins = []
for x in cur:
    m = pmidx.get(x.get('t0'))
    if not m or m.get('p20') is None or x.get('ask') is None: continue
    px = m['p20'] if x['side']=='up' else 1-m['p20']
    joins.append(x['ask'] - px)
if joins:
    print(f"\nt0-join ask - minute-mid: n={len(joins)} median={q(joins,.5):.4f} mean={sum(joins)/len(joins):.4f}")

# win rates for the live family
res = [x for x in cur if x.get('result') in ('win','loss')]
res.sort(key=lambda x: x['at'])
w = sum(1 for x in res if x['result']=='win')
print(f"\nlive rev-family settled: n={len(res)} win={w/len(res):.3f} pnl={sum(x.get('pnl',0) for x in res):+.0f}")
third = len(res)//3
last3 = res[-third:] if third else []
if last3:
    print(f"last-third: n={len(last3)} win={sum(1 for x in last3 if x['result']=='win')/len(last3):.3f}")
