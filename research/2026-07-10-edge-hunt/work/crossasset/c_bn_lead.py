"""(c) Binance vs Coinbase lead-lag at one interval.
div[t] = bn prior open-to-open move minus cb prior move (basis change over t-1).
Convergence hypothesis: if Binance ran ahead of Coinbase in t-1, Coinbase catches up in t.
Also raw bn-prior sign vs cb outcome for comparison with cb's own prior (known reversal)."""
import sys, json
sys.path.insert(0, "/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad/work/crossasset")
from util import *

cb = load("cb5m"); bn = load("bn5m")
assert cb["t"] == bn["t"]
n = len(cb["t"])
pc = prior_oo(cb["o"]); pb = prior_oo(bn["o"])
out = outcomes(cb["o"], cb["c"])
cut = split_idx(n)
div = [None] * n
for i in range(1, n):
    div[i] = (pb[i] - pc[i]) * 1e4  # bps

absd = sorted(abs(d) for d in div[1:cut])
print(f"|div| train quantiles (bps): p50={pct(absd,0.5):.2f} p75={pct(absd,0.75):.2f} p90={pct(absd,0.9):.2f} p99={pct(absd,0.99):.2f}")

results = {}
print("\n== BTC(cb) outcome follows sign(div t-1) [convergence] by |div| threshold ==")
print(f"{'thresh(bps)':>11} {'trainRate':>9} {'nTr':>6} {'pTr':>7} {'testRate':>9} {'nTe':>6}")
for th in (0.5, 1, 1.5, 2, 3):
    tr = {}; te = {}
    for i in range(1, n):
        if div[i] is None or abs(div[i]) < th: continue
        hit = 1 if (out[i] == 1) == (div[i] > 0) else 0
        (tr if i < cut else te)[i] = hit
    r, ntr, p, ci = block_bootstrap_p(tr, n)
    kte, nte, rte = rate(list(te.values()))
    print(f"{th:>11} {r:9.4f} {ntr:6d} {p:7.4f} {rte:9.4f} {nte:6d}")
    results[f"conv_ge{th}"] = dict(train=r, n_train=ntr, p_train=p, test=rte, n_test=nte)

print("\n== Raw prior-sign follow rates at |prior|>=12bps: cb-prior vs bn-prior (context) ==")
for name, pr in (("cb", pc), ("bn", pb)):
    tr = {}; te = {}
    for i in range(1, n):
        if pr[i] is None or abs(pr[i]) * 1e4 < 12: continue
        hit = 1 if (out[i] == 1) == (pr[i] > 0) else 0
        (tr if i < cut else te)[i] = hit
    r, ntr, p, ci = block_bootstrap_p(tr, n)
    kte, nte, rte = rate(list(te.values()))
    print(f"{name}-prior>=12bps follow: train {r:.4f} (n={ntr}, p={p:.4f})  test {rte:.4f} (n={nte})  [reversal = 1-this]")
    results[f"raw_{name}_ge12"] = dict(train=r, n_train=ntr, p_train=p, test=rte, n_test=nte)

# does divergence sign ADD to the reversal setup? condition: |cb prior| >= 12 (reversal active),
# split by whether div agrees with the reversal side (bn moved less = confirms exhaustion?)
print("\n== Interaction: within |cb prior|>=12bps, reversal rate split by div sign vs prior sign ==")
for lab, condf in (("div_opposes_prior", lambda i: div[i] * pc[i] < 0),
                   ("div_confirms_prior", lambda i: div[i] * pc[i] > 0)):
    tr = {}; te = {}
    for i in range(1, n):
        if pc[i] is None or abs(pc[i]) * 1e4 < 12 or div[i] is None or div[i] == 0: continue
        if not condf(i): continue
        rev = 1 if (out[i] == 1) == (pc[i] < 0) else 0  # reversal hit
        (tr if i < cut else te)[i] = rev
    r, ntr, p, ci = block_bootstrap_p(tr, n)
    kte, nte, rte = rate(list(te.values()))
    print(f"{lab}: reversal-rate train {r:.4f} (n={ntr}, p={p:.4f})  test {rte:.4f} (n={nte})")
    results[f"inter_{lab}"] = dict(train=r, n_train=ntr, p_train=p, test=rte, n_test=nte)

json.dump(results, open("/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad/work/crossasset/c_bn_lead_results.json", "w"), indent=1)
print("\nsaved c_bn_lead_results.json")
