"""(a) ETH lead: does ETH's prior 5m move (t-1) predict BTC's interval-t outcome?
Buffered open-to-open priors; outcome c>=o (ties Up). 60d, train=first 2/3, test=last 1/3.
Conditional case: |ETH prior| >= 12bps while |BTC prior| < 6bps."""
import sys, json
sys.path.insert(0, "/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad/work/crossasset")
from util import *

cb = load("cb5m"); eth = load("eth5m")
assert cb["t"] == eth["t"]
n = len(cb["t"])
pb = prior_oo(cb["o"])          # BTC prior move (interval t-1)
pe = prior_oo(eth["o"])         # ETH prior move
out = outcomes(cb["o"], cb["c"])  # BTC outcome at t
cut = split_idx(n)
print(f"n={n} train=[1,{cut}) test=[{cut},{n})  base P(up) train={sum(out[1:cut])/(cut-1):.4f} test={sum(out[cut:])/(n-cut):.4f}")

def follow_events(lo, hi, idx_range, extra=None):
    """hit=1 if BTC outcome matches sign of ETH prior; selection |pe| in [lo,hi) bps."""
    d = {}
    for i in idx_range:
        if pe[i] is None or pe[i] == 0: continue
        m = abs(pe[i]) * 1e4
        if not (lo <= m < hi): continue
        if extra and not extra(i): continue
        d[i] = 1 if (out[i] == 1) == (pe[i] > 0) else 0
    return d

results = {}
print("\n== Unconditional: BTC follows sign(ETH t-1) by |ETH move| bucket ==")
print(f"{'bucket(bps)':>14} {'trainRate':>9} {'nTr':>5} {'pTr':>7} {'testRate':>9} {'nTe':>5}")
for lo, hi in [(0, 2), (2, 6), (6, 12), (12, 25), (25, 1e9), (0, 1e9)]:
    tr = follow_events(lo, hi, range(1, cut))
    te = follow_events(lo, hi, range(cut, n))
    r, ntr, p, ci = block_bootstrap_p(tr, n)
    kte, nte, rte = rate(list(te.values()))
    lab = f"[{lo},{'inf' if hi>1e8 else hi})"
    print(f"{lab:>14} {r:9.4f} {ntr:5d} {p:7.4f} {rte:9.4f} {nte:5d}")
    results[f"uncond_{lab}"] = dict(train=r, n_train=ntr, p_train=p, test=rte, n_test=nte)

print("\n== Conditional: |ETH t-1| >= 12bps AND |BTC t-1| < 6bps -> BTC follows ETH ==")
cond = lambda i: pb[i] is not None and abs(pb[i]) * 1e4 < 6
for ethlo in (8, 12, 16, 20):
    tr = follow_events(ethlo, 1e9, range(1, cut), cond)
    te = follow_events(ethlo, 1e9, range(cut, n), cond)
    r, ntr, p, ci = block_bootstrap_p(tr, n)
    kte, nte, rte = rate(list(te.values()))
    print(f"ETH>={ethlo:>2}bps BTC<6bps: train {r:.4f} (n={ntr}, p={p:.4f}, ci={ci[0]:.3f}-{ci[1]:.3f})  test {rte:.4f} (n={nte})")
    results[f"cond_eth{ethlo}_btc6"] = dict(train=r, n_train=ntr, p_train=p, test=rte, n_test=nte)

# Also the mirror: does ETH prior ADD to BTC's own reversal signal? Check ETH residual sign
# (ETH move minus its BTC-hedged component) — beta fit on train only.
sx = sy = sxx = sxy = 0.0; m = 0
for i in range(1, cut):
    if pb[i] is None: continue
    sx += pb[i]; sy += pe[i]; sxx += pb[i] * pb[i]; sxy += pb[i] * pe[i]; m += 1
beta = (m * sxy - sx * sy) / (m * sxx - sx * sx)
print(f"\nbeta(ETH~BTC) train = {beta:.3f}")
res = [None] * n
for i in range(1, n):
    res[i] = pe[i] - beta * pb[i]
print("== ETH residual sign -> BTC follows residual, by |resid| bucket ==")
for lo, hi in [(4, 8), (8, 15), (15, 1e9)]:
    tr = {}; te = {}
    for i in range(1, n):
        if res[i] is None or res[i] == 0: continue
        mm = abs(res[i]) * 1e4
        if not (lo <= mm < hi): continue
        hit = 1 if (out[i] == 1) == (res[i] > 0) else 0
        (tr if i < cut else te)[i] = hit
    r, ntr, p, ci = block_bootstrap_p(tr, n)
    kte, nte, rte = rate(list(te.values()))
    lab = f"[{lo},{'inf' if hi>1e8 else hi})"
    print(f"resid {lab:>9}: train {r:.4f} (n={ntr}, p={p:.4f})  test {rte:.4f} (n={nte})")
    results[f"resid_{lab}"] = dict(train=r, n_train=ntr, p_train=p, test=rte, n_test=nte)

json.dump(results, open("/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad/work/crossasset/a_eth_lead_results.json", "w"), indent=1)
print("\nsaved a_eth_lead_results.json")
