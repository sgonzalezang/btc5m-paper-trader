#!/usr/bin/env python3
"""Live-ledger fill reality for reversal engines + censoring analysis."""
import json

S = "/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad"
tl = json.load(open(S + "/data/trades.json"))
d = json.load(open(S + "/data/cb5m.json"))
t, o, c = d["t"], d["o"], d["c"]
idx = {tt: i for i, tt in enumerate(t)}
THR = 0.0012

def q(xs, p):
    xs = sorted(xs); k = (len(xs)-1)*p
    f = int(k); return xs[f] + (xs[min(f+1,len(xs)-1)]-xs[f])*(k-f)

def gate_feats(i):
    num = abs(o[i]-o[i-6]); den = sum(abs(o[j+1]-o[j]) for j in range(i-6,i))
    eff6 = num/den if den>0 else 0.0
    cnt = sum(1 for j in range(i-13,i-1) if abs(o[j+1]-o[j])/o[j] >= THR)
    return eff6, cnt

revs = [x for x in tl if x.get("eng") in ("reversal","reversal2")]
print("reversal-engine rows:", len(revs), " srcs:", {x.get("src") for x in revs},
      " statuses:", {x.get("status") for x in revs})

settled = [x for x in revs if x.get("status")=="settled" and x.get("entry") is not None]
print("settled:", len(settled))
asks = [x["ask"] for x in settled if x.get("ask") is not None]
ents = [x["entry"] for x in settled]
print(f"ask:   p10={q(asks,.1):.3f} p50={q(asks,.5):.3f} mean={sum(asks)/len(asks):.4f} p90={q(asks,.9):.3f} max={max(asks):.3f}")
print(f"entry: p10={q(ents,.1):.3f} p50={q(ents,.5):.3f} mean={sum(ents)/len(ents):.4f} p90={q(ents,.9):.3f} max={max(ents):.3f}")
wins = sum(1 for x in settled if x.get("result")=="win")
tot_pnl = sum(x["pnl"] for x in settled if x.get("pnl") is not None)
tot_sh = sum(x["shares"] for x in settled if x.get("shares"))
print(f"wr={wins}/{len(settled)}={wins/len(settled):.4f}  pnl=${tot_pnl:.2f}  per-share={tot_pnl/tot_sh*100:+.2f} c")

# implied fee-adjusted EV at empirical entry mix with backtest TEST wr
ewr = 0.5676
mean_p = sum(ents)/len(ents)
mean_fee = sum(0.07*p*(1-p) for p in ents)/len(ents)
print(f"decomposition: TESTwr({ewr}) - E[entry]({mean_p:.4f}) - E[fee]({mean_fee:.4f}) = {(ewr-mean_p-mean_fee)*100:+.2f} c/share")

# gated subset of live trades
g, ug = [], []
for x in settled:
    i = idx.get(x.get("t0"))
    if i is None or i < 14: continue
    pm = (o[i]-o[i-1])/o[i-1]
    eff6, cnt = gate_feats(i)
    (g if (eff6>=0.32 and cnt<=6) else ug).append(x)
def st(sub, tag):
    if not sub: print(tag, "n=0"); return
    w = sum(1 for x in sub if x["result"]=="win")
    pn = sum(x["pnl"] for x in sub); sh = sum(x["shares"] for x in sub)
    es = [x["entry"] for x in sub]
    print(f"{tag}: n={len(sub)} wr={w/len(sub):.3f} pnl=${pn:.2f} per-share={pn/sh*100:+.2f}c entry_mean={sum(es)/len(es):.4f}")
st(g, "live gated")
st(ug, "live ungated-only")

# censoring: triggers in the live span vs trades taken (engine 'reversal' only, current src)
cur = [x for x in settled if x.get("src")!="prereset" and x["eng"]=="reversal"]
if cur:
    lo = min(x["t0"] for x in cur); hi = max(x["t0"] for x in cur)
    trig = [i for i in range(14, len(t)) if lo <= t[i] <= hi and abs((o[i]-o[i-1])/o[i-1]) >= THR]
    have = {x["t0"] for x in cur}
    matched = sum(1 for i in trig if t[i] in have)
    print(f"\nlive span {lo}..{hi} ({(hi-lo)/86400:.1f}d): cb5m triggers={len(trig)}, taken by 'reversal'={len(cur)}, matched={matched} -> skip rate {(1 - matched/len(trig))*100:.0f}%")
    # what did the skipped triggers look like on the backtest (proxy outcome, p=0.51)?
    P=0.51; F=0.07*P*(1-P)
    def bt(iis, tag):
        if not iis: return
        w=0;
        for i in iis:
            pm=(o[i]-o[i-1])/o[i-1]; up = c[i]>=o[i]
            w += (not up) if pm>0 else up
        n=len(iis)
        print(f"  {tag}: n={n} proxy wr={w/n:.4f} EV@51c={(w/n - P - F)*100:+.2f}c")
    bt([i for i in trig if t[i] in have], "taken triggers")
    bt([i for i in trig if t[i] not in have], "skipped triggers")
