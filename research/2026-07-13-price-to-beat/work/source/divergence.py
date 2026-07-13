#!/usr/bin/env python3
"""Quantify how often OUR Coinbase-derived displayed verdict/leader DISAGREES
with the Polymarket (Chainlink) oracle. STDLIB ONLY.

OUR display (live.html):
  strikeOf(t0)   = Coinbase 1m OPEN at t0  (fallback prior-candle close)
  settleOf(t0)   = strikeOf(t0+300)        (= next window's Coinbase open)
  verdictOf: d=settle-strike; tooClose if |d| < clearMargin=max(15, strike*3e-4);
             else Up iff d>0.
  live leader (drawBtcBar): sign(spot - strike), NO margin guard, tie='at the line'.

Oracle truth = pm_res_3d.json [t0, up(1/0)] (Chainlink >= rule)."""
import json

D = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data/cb1m.json"
RES = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-10-edge-hunt/data/pm_res_3d.json"
cb = json.load(open(D))
O = {t: o for t, o in zip(cb["t"], cb["o"])}
C = {t: c for t, c in zip(cb["t"], cb["c"])}
res = json.load(open(RES))

def strikeOf(t0):
    if t0 in O and O[t0] is not None: return O[t0]
    if (t0-60) in C and C[t0-60] is not None: return C[t0-60]
    return None
def clearMargin(px): return max(15.0, px*0.0003)

rows = []
for t0, up in res:
    s = strikeOf(t0); e = strikeOf(t0+300)
    if s is None or e is None: continue
    d = e - s
    bps = abs(d)/s*1e4
    margin = clearMargin(s)
    tooClose = abs(d) < margin
    cb_up = d > 0                 # OUR hard sign (ties -> down, but tooClose catches near-0)
    rows.append(dict(t0=t0, oracle_up=bool(up), s=s, e=e, d=d, bps=bps,
                     tooClose=tooClose, cb_up=cb_up, margin=margin))

n = len(rows)
# 1) NAIVE sign agreement (ignore margin) — this is the live-leader logic at close
naive_agree = sum(1 for r in rows if r["cb_up"] == r["oracle_up"])
# 2) hard-call verdict: only calls when NOT tooClose
hard = [r for r in rows if not r["tooClose"]]
hard_agree = sum(1 for r in hard if r["cb_up"] == r["oracle_up"])
deferred = [r for r in rows if r["tooClose"]]
# among deferred (display says 'oracle decides'), what would the naive leader have said?
def_naive_wrong = sum(1 for r in deferred if r["cb_up"] != r["oracle_up"])

print(f"N intervals w/ Coinbase strike+settle & oracle: {n}")
print(f"date span t0: {min(r['t0'] for r in rows)}..{max(r['t0'] for r in rows)}")
print()
print("=== (A) NAIVE sign leader (Coinbase spot vs Coinbase open, NO margin) vs oracle ===")
print(f"  agreement: {naive_agree}/{n} = {100*naive_agree/n:.2f}%   DISAGREE {n-naive_agree} = {100*(n-naive_agree)/n:.2f}%")
print()
print("=== (B) HARD-CALL verdict (display only calls when |d|>=margin ~$19) ===")
print(f"  hard-called intervals: {len(hard)} ({100*len(hard)/n:.1f}% of all)")
print(f"  hard-call agreement: {hard_agree}/{len(hard)} = {100*hard_agree/len(hard):.2f}%  DISAGREE {len(hard)-hard_agree} = {100*(len(hard)-hard_agree)/len(hard):.2f}%")
print(f"  deferred to oracle (tooClose): {len(deferred)} ({100*len(deferred)/n:.1f}%)")
print(f"    of those, Coinbase naive sign would have been WRONG: {def_naive_wrong}/{len(deferred)} = {100*def_naive_wrong/max(1,len(deferred)):.1f}%")
print()
print("=== (C) DISAGREEMENT sliced by move size (|Coinbase move| bps) ===")
buckets = [(0,1),(1,2),(2,3),(3,5),(5,8),(8,12),(12,20),(20,1e9)]
print(f"  {'bps bucket':>12} {'n':>5} {'disagree':>9} {'rate%':>7} {'medMargin$':>10}")
for lo,hi in buckets:
    b=[r for r in rows if lo<=r["bps"]<hi]
    if not b: continue
    dis=sum(1 for r in b if r["cb_up"]!=r["oracle_up"])
    import statistics
    print(f"  {f'[{lo},{hi})':>12} {len(b):>5} {dis:>9} {100*dis/len(b):>6.1f}% {statistics.median(r['margin'] for r in b):>10.1f}")
print()
# how much of total disagreement lives under the flat boundary?
tot_dis = n - naive_agree
sub2 = sum(1 for r in rows if r['bps']<2 and r['cb_up']!=r['oracle_up'])
sub3 = sum(1 for r in rows if r['bps']<3 and r['cb_up']!=r['oracle_up'])
print(f"disagreements with |move|<2bps: {sub2}/{tot_dis} = {100*sub2/max(1,tot_dis):.0f}% of all disagreements")
print(f"disagreements with |move|<3bps: {sub3}/{tot_dis} = {100*sub3/max(1,tot_dis):.0f}% of all disagreements")

out=dict(n=n, naive_agree=naive_agree, naive_agree_pct=round(100*naive_agree/n,3),
         naive_disagree=n-naive_agree, naive_disagree_pct=round(100*(n-naive_agree)/n,3),
         hard_n=len(hard), hard_agree=hard_agree, hard_agree_pct=round(100*hard_agree/len(hard),3),
         hard_disagree=len(hard)-hard_agree,
         deferred_n=len(deferred), deferred_pct=round(100*len(deferred)/n,3),
         deferred_naive_wrong=def_naive_wrong,
         sub2_share=round(100*sub2/max(1,tot_dis),1), sub3_share=round(100*sub3/max(1,tot_dis),1))
json.dump(out, open("divergence_summary.json","w"), indent=1)
