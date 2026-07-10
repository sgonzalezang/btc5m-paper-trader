#!/usr/bin/env python3
"""Adversarial attacks on reversal60 best spec. Stdlib only."""
import json, random

SC = "/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad"
d = json.load(open(SC + "/data/cb5m.json"))
t, o, c = d["t"], d["o"], d["c"]
n = len(t)
gaps = sum(1 for i in range(1, n) if t[i] - t[i - 1] != 300)
print("non-consecutive gaps:", gaps)

sigs = []
for i in range(1, n):
    if t[i] - t[i - 1] != 300 or o[i - 1] <= 0:
        continue
    mv = (o[i] - o[i - 1]) / o[i - 1]
    up_won = 1 if c[i] >= o[i] else 0
    win = (1 - up_won) if mv > 0 else up_won
    cur_bps = abs(c[i] - o[i]) / o[i] * 1e4
    sigs.append((t[i], win, abs(mv) * 1e4, cur_bps))

t0s, span = t[0], t[-1] - t[0]
def fee(p): return 0.07 * p * (1 - p)
def net(q, p): return q - p - fee(p)
def split(sel):
    return ([s for s in sel if s[0] < t0s + span * 2 / 3],
            [s for s in sel if s[0] >= t0s + span * 2 / 3])
def q_of(rows): return sum(r[1] for r in rows) / len(rows) if rows else float("nan")

print("\n== A. threshold sensitivity (+-20%): 9.6 / 12 / 14.4 bps ==")
for thr in (9.6, 12.0, 14.4):
    sel = [s for s in sigs if s[2] >= thr]
    tr, te = split(sel)
    print("thr=%.1f TRAIN n=%d q=%.4f net@51=%+.4f | TEST n=%d q=%.4f net@51=%+.4f"
          % (thr, len(tr), q_of(tr), net(q_of(tr), .51), len(te), q_of(te), net(q_of(te), .51)))

print("\n== B. fill-price realism from pm_prices_sample.json ==")
pm = json.load(open(SC + "/data/pm_prices_sample.json"))
rows = pm if isinstance(pm, list) else pm.get("rows", pm.get("data", []))
print("pm sample rows:", len(rows), "fields:", sorted(rows[0].keys()) if rows else None)
# map cb5m signals by t0 to find contrarian side cost at t0+20s (p20 is Up-token price)
sig_by_t0 = {s[0]: s for s in sigs if s[2] >= 12.0}
costs = []
for r in rows:
    s = sig_by_t0.get(r["t0"])
    if s is None or r.get("p20") is None:
        continue
    # contrarian side: prior move sign -> we need it; recompute from cb
    # s stored abs move; recover sign via lookup
    costs.append((r["t0"], r["p20"], r["up_won"]))
# recover sign of prior move for matched markets
sign_by_t0 = {}
for i in range(1, n):
    if t[i] - t[i - 1] != 300: continue
    sign_by_t0[t[i]] = 1 if o[i] >= o[i - 1] else -1
matched = []
for (tt, p20, up_won) in costs:
    sgn = sign_by_t0.get(tt, 0)
    if sgn == 0: continue
    # prior up -> buy Down: down ask ~ 1 - p20(up bid-ish); treat p20 as Up price
    cost = (1 - p20) if sgn > 0 else p20
    eff = cost + 0.01  # ask + 1c slip per brief
    win = (1 - up_won) if sgn > 0 else up_won
    matched.append((tt, eff, win))
if matched:
    effs = sorted(m[1] for m in matched)
    med = effs[len(effs)//2]
    fr_over_53 = sum(1 for e in effs if e > 0.53) / len(effs)
    fr_over_51 = sum(1 for e in effs if e > 0.51) / len(effs)
    print("matched signal-markets: %d | median eff cost %.3f | frac>0.51: %.2f | frac>0.53: %.2f"
          % (len(matched), med, fr_over_51, fr_over_53))
    # EV with cap 53c using TEST q
    q_test = 0.5539
    fills = [m for m in matched if m[1] <= 0.53]
    if fills:
        ev = sum(q_test - e - fee(e) for (_, e, _) in fills) / len(fills)
        print("under cap<=0.53: %d/%d fill (%.0f%%), mean EV/share at q_TEST=0.5539: %+.4f"
              % (len(fills), len(matched), 100*len(fills)/len(matched), ev))
        # realized win-rate of the actually-fillable subset
        qw = sum(w for (_, _, w) in fills) / len(fills)
        evr = sum(qw - e - fee(e) for (_, e, _) in fills) / len(fills)
        print("realized q on fillable subset: %.4f -> realized EV/share %+.4f (small n)" % (qw, evr))

print("\n== C. cap sensitivity +-20%: 0.424 / 0.53 / 0.636 with pm fills ==")
for cap in (0.424, 0.53, 0.636):
    fills = [m for m in matched if m[1] <= cap]
    if not fills:
        print("cap=%.3f: no fills" % cap); continue
    ev = sum(0.5539 - e - fee(e) for (_, e, _) in fills) / len(fills)
    print("cap=%.3f: fill %d/%d (%.0f%%), EV/share at q_TEST %+.4f"
          % (cap, len(fills), len(matched), 100*len(fills)/len(matched), ev))

print("\n== D. tie/resolution-noise exposure (sub-2bps outcome moves) ==")
sel = [s for s in sigs if s[2] >= 12.0]
tr, te = split(sel)
for lab, rows2 in (("TRAIN", tr), ("TEST", te)):
    f = sum(1 for s in rows2 if s[3] < 2.0) / len(rows2)
    qs = q_of([s for s in rows2 if s[3] < 2.0])
    print("%s: frac outcome |move|<2bps = %.3f (q on those = %.3f); adversarial q shift = -%.4f"
          % (lab, f, qs, f * 0.11))

print("\n== E. 10-day window stability ==")
for k in range(6):
    w = [s for s in sel if t0s + k*10*86400 <= s[0] < t0s + (k+1)*10*86400]
    print("days %2d-%2d: n=%4d q=%.4f net@51=%+.4f" % (k*10, (k+1)*10, len(w), q_of(w), net(q_of(w), .51)))

print("\n== F. multiplicity: TEST p vs breakeven under Bonferroni ==")
def block_boot_p(wins, target, nboot=6000, block=12, seed=11):
    rng = random.Random(seed); m = len(wins)
    nb = (m + block - 1) // block; cnt = 0
    for _ in range(nboot):
        s = 0; k = 0
        while k < m:
            st = rng.randrange(0, m - block + 1)
            take = min(block, m - k)
            s += sum(wins[st:st + take]); k += take
        if s / k <= target: cnt += 1
    return cnt / nboot
wins_te = [s[1] for s in te]
be = 0.51 + fee(0.51)
p = block_boot_p(wins_te, be)
print("TEST p vs q*(0.51): %.4f ; x5 tests -> %.3f ; x10 -> %.3f" % (p, min(1, p*5), min(1, p*10)))

print("\n== G. contrarian entry NOT at 50/50: does 51c even apply on TEST? ==")
# distribution of eff cost among TEST-period matched markets
te_matched = [m for m in matched if m[0] >= t0s + span * 2 / 3]
print("pm sample matched in TEST period: %d (pm sample covers last ~3d only)" % len(te_matched))
