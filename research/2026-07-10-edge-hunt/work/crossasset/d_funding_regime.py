"""(d) Funding / premium-index tercile as a slow regime dial.
For each 5m interval, attach latest funding (hourly deribit, ts<=t0) and premium index
(binance.vision premiumIndexKlines close of candle ending at t0, i.e. candle t = t0-300).
Tercile cutoffs from TRAIN only. Within each tercile compute:
  - reversal rate after buffered |cb prior| >= 12bps (the confirmed edge's conditioning)
  - momentum hold rate for |cb prior| in [2,12) bps
Report train (with block-bootstrap p vs the unconditional train rate) and test."""
import sys, json
sys.path.insert(0, "/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad/work/crossasset")
from util import *
import bisect

cb = load("cb5m")
n = len(cb["t"]); t5 = cb["t"]
pc = prior_oo(cb["o"]); out = outcomes(cb["o"], cb["c"])
cut = split_idx(n)

fund = load("funding")["rows"]          # [[ts, rate]] hourly
fts = [r[0] for r in fund]; fv = [r[1] for r in fund]
prem = load("premium5m")               # t = candle open; close known at t+300
pmap = {t + 300: c for t, c in zip(prem["t"], prem["c"])}

def fund_at(t0):
    j = bisect.bisect_right(fts, t0) - 1
    return fv[j] if j >= 0 else None

fund_series = [fund_at(t) for t in t5]
prem_series = [pmap.get(t) for t in t5]
print(f"coverage: funding {sum(v is not None for v in fund_series)}/{n}, premium {sum(v is not None for v in prem_series)}/{n}")

def terciles(vals):
    s = sorted(vals)
    return pct(s, 1/3), pct(s, 2/3)

results = {}
for name, series in (("funding", fund_series), ("premium", prem_series)):
    tvals = [series[i] for i in range(1, cut) if series[i] is not None]
    q1, q2 = terciles(tvals)
    print(f"\n### {name}: train tercile cuts = {q1:.3e} / {q2:.3e}")
    def terc(v):
        if v is None: return None
        return 0 if v <= q1 else (1 if v <= q2 else 2)
    for setup, sel, hitf in (
        ("reversal(|prior|>=12bps)", lambda i: abs(pc[i]) * 1e4 >= 12,
         lambda i: 1 if (out[i] == 1) == (pc[i] < 0) else 0),
        ("mom_hold(|prior| 2-12bps)", lambda i: 2 <= abs(pc[i]) * 1e4 < 12,
         lambda i: 1 if (out[i] == 1) == (pc[i] > 0) else 0)):
        # unconditional train rate for this setup (the comparison null)
        base_tr = {i: hitf(i) for i in range(1, cut) if pc[i] is not None and sel(i)}
        base_te = {i: hitf(i) for i in range(cut, n) if pc[i] is not None and sel(i)}
        b_r, b_n, _, _ = block_bootstrap_p(base_tr, n, B=200)
        kte, nte, b_rte = rate(list(base_te.values()))
        print(f"  {setup}: ALL train {b_r:.4f} (n={b_n})  test {b_rte:.4f} (n={nte})")
        for tc in (0, 1, 2):
            tr = {i: h for i, h in base_tr.items() if terc(series[i]) == tc}
            te = {i: h for i, h in base_te.items() if terc(series[i]) == tc}
            r, ntr, p, ci = block_bootstrap_p(tr, n, null=b_r)
            k2, n2, rte = rate(list(te.values()))
            print(f"    T{tc}: train {r:.4f} (n={ntr}, p_vs_all={p:.4f})  test {rte:.4f} (n={n2})")
            results[f"{name}_{setup}_T{tc}"] = dict(train=r, n_train=ntr, p_vs_all=p,
                                                    test=rte, n_test=n2,
                                                    all_train=b_r, all_test=b_rte)

json.dump(results, open("/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad/work/crossasset/d_funding_regime_results.json", "w"), indent=1)
print("\nsaved d_funding_regime_results.json")
