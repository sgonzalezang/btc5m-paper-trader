#!/usr/bin/env python3
"""Lens-specific attacks: weekly re-split, thirds, Kaufman efficiency regimes
(calm vs trending, incl. within-TEST), fold-wise best-threshold stability,
trending-day stress. Stdlib only."""
import json

SC = "/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad"
d = json.load(open(SC + "/data/cb5m.json"))
t, o, c = d["t"], d["o"], d["c"]
n = len(t)
t0s, span = t[0], t[-1] - t[0]
cut = t0s + span * 2 / 3

def fee(p): return 0.07 * p * (1 - p)
def net(q, p): return q - p - fee(p)
BE51 = 0.51 + fee(0.51)

# close-to-close 5m returns for efficiency
rets = [None] * n
for i in range(1, n):
    if t[i] - t[i-1] == 300:
        rets[i] = (c[i] - c[i-1]) / c[i-1]

def eff_at(i):
    """Kaufman efficiency over trailing 12 completed intervals ending at candle i-1."""
    lo = i - 12
    if lo < 1: return None
    seq = rets[lo:i]
    if any(r is None for r in seq): return None
    den = sum(abs(r) for r in seq)
    return abs(sum(seq)) / den if den > 0 else None

sigs = []  # (t0, win, absmove_bps, eff)
allsigs6 = []
for i in range(1, n):
    if t[i] - t[i-1] != 300: continue
    mv = (o[i] - o[i-1]) / o[i-1]
    ab = abs(mv) * 1e4
    up_won = 1 if c[i] >= o[i] else 0
    win = (1 - up_won) if mv > 0 else up_won
    if ab >= 6.0: allsigs6.append((t[i], win, ab))
    if ab >= 12.0: sigs.append((t[i], win, ab, eff_at(i)))

def q_of(xs): return sum(x[1] for x in xs) / len(xs) if xs else float("nan")
def line(lab, xs):
    if not xs: print("%-34s EMPTY" % lab); return
    q = q_of(xs)
    print("%-34s n=%5d q=%.4f net@51c=%+.4f %s" % (lab, len(xs), q, net(q, .51),
          "CLEARS" if q > BE51 else "fails"))

print("== 1. thirds re-split (20d each) ==")
for k in range(3):
    lo = t0s + span * k / 3; hi = t0s + span * (k+1) / 3 + (1 if k == 2 else 0)
    line("third %d" % (k+1), [s for s in sigs if lo <= s[0] < hi])

print("\n== 2. weekly re-split ==")
pos_w = tot_w = 0
for wk in range(9):
    lo = t0s + wk * 604800; hi = lo + 604800
    xs = [s for s in sigs if lo <= s[0] < hi]
    if not xs: continue
    line("week %d" % wk, xs)
    tot_w += 1
    if q_of(xs) > BE51: pos_w += 1
print("weeks clearing fee hurdle at 51c: %d/%d" % (pos_w, tot_w))

print("\n== 3. Kaufman efficiency regimes (gate known-valid <=0.48) ==")
for lab, f in [("calm eff<=0.48", lambda e: e is not None and e <= 0.48),
               ("trending eff>0.48", lambda e: e is not None and e > 0.48),
               ("strong trend eff>0.65", lambda e: e is not None and e > 0.65)]:
    xs = [s for s in sigs if f(s[3])]
    line("FULL  " + lab, xs)
    line("TRAIN " + lab, [s for s in xs if s[0] < cut])
    line("TEST  " + lab, [s for s in xs if s[0] >= cut])

print("\n== 4. best threshold per 10d fold (sweep 8-24bps, min n=30) ==")
for k in range(6):
    lo = t0s + k * 10 * 86400; hi = lo + 10 * 86400
    fold = [s for s in allsigs6 if lo <= s[0] < hi]
    best = None; q12 = None
    for thr in (8, 10, 12, 14, 16, 20, 24):
        xs = [s for s in fold if s[2] >= thr]
        if len(xs) < 30: continue
        q = q_of(xs); e = net(q, .51)
        if thr == 12: q12 = (q, len(xs), e)
        if best is None or e > best[1]: best = (thr, e, q, len(xs))
    print("fold %d (d%2d-%2d): q@12=%.4f n=%d net=%+.4f | best thr=%2d net=%+.4f (n=%d)" %
          (k, k*10, (k+1)*10, q12[0], q12[1], q12[2], best[0], best[1], best[3]))

print("\n== 5. trending-day stress: day-level mean eff vs pnl ==")
days = {}
for s in sigs:
    days.setdefault(int((s[0] - t0s) // 86400), []).append(s)
rows = []
for dk in sorted(days):
    xs = days[dk]
    effs = [s[3] for s in xs if s[3] is not None]
    me = sum(effs)/len(effs) if effs else None
    pnl = sum(s[1] - 0.51 - fee(0.51) for s in xs)
    rows.append((dk, me, len(xs), q_of(xs), pnl))
rs = sorted([r for r in rows if r[1] is not None], key=lambda r: -r[1])
print("5 trendiest days (day, meanEff, n, q, pnl/share-sum):")
for r in rs[:5]: print("  d%02d eff=%.3f n=%3d q=%.3f pnl=%+.2f" % r)
print("5 calmest days:")
for r in rs[-5:]: print("  d%02d eff=%.3f n=%3d q=%.3f pnl=%+.2f" % r)
# correlation day eff vs day q (rank-ish: split by median)
med = rs[len(rs)//2][1]
hi = [r for r in rs if r[1] > med]; loq = [r for r in rs if r[1] <= med]
qhi = sum(r[2]*r[3] for r in hi)/sum(r[2] for r in hi)
qlo = sum(r[2]*r[3] for r in loq)/sum(r[2] for r in loq)
print("signal-weighted q on trendier-half days: %.4f ; calmer-half days: %.4f" % (qhi, qlo))

print("\n== 6. TEST pnl concentration by day ==")
te = [r for r in rows if t0s + r[0]*86400 >= cut]
tot = sum(r[4] for r in te)
pos = sum(1 for r in te if r[4] > 0)
srt = sorted(te, key=lambda r: -r[4])
top3 = sum(r[4] for r in srt[:3])
print("TEST days=%d positive=%d total=%.2f top3=%.2f (%.0f%%)" % (len(te), pos, tot, top3, 100*top3/tot))
for r in srt[:3]: print("  d%02d n=%3d q=%.3f pnl=%+.2f" % (r[0], r[2], r[3], r[4]))

print("\n== 7. TEST minus its best week: does edge survive? ==")
# drop each TEST week in turn
te_s = [s for s in sigs if s[0] >= cut]
wk_of = lambda s: int((s[0] - t0s) // 604800)
wks = sorted(set(wk_of(s) for s in te_s))
for w in wks:
    xs = [s for s in te_s if wk_of(s) != w]
    line("TEST minus week %d" % w, xs)
