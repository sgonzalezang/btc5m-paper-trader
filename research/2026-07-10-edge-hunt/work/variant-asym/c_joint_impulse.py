"""(c) Cross-asset CONFIRMATION of the flagship signal (not ETH-alone lead — new test).

Joint impulse: BTC prior |open-to-open move| >= 12bps AND ETH prior move SAME direction
with |move| >= 8bps in the SAME prior interval (eth5m aligned by t). Question: does a
joint (market-wide) impulse revert harder than a BTC-idiosyncratic impulse?

Paired on common timeline: q(joint) vs q(btc-only complement) vs q(all baseline signals);
retention; TRAIN/TEST; six 10d folds; 1h-block-boot p for the paired delta (joint - complement)
computed on common blocks. ETH-threshold robustness sweep {4,6,8,12,16} (8 = pre-registered
primary; sweep is monotonicity check only, NO selection).
Regime correlation for fill adjustment: mean |BTC move| and trailing eff12 for joint vs rest.
"""
import sys, json, random
SCR = "/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad"
sys.path.insert(0, SCR + "/work/crossasset")
from util import load, prior_oo, outcomes, block_bootstrap_p, ev, pct

cb = load("cb5m"); eth = load("eth5m")
assert cb["t"] == eth["t"], "grid misaligned"
n = len(cb["t"])
pb = prior_oo(cb["o"])
pe = prior_oo(eth["o"])
out = outcomes(cb["o"], cb["c"])
cut = int(n * 2 / 3)
FOLD = 2880
ETH_THR = 8.0   # primary, pre-registered

# baseline signal set + hit indicator (contrarian side wins)
ev_all, joint_of, move_of = {}, {}, {}
for i in range(1, n):
    if pb[i] is None or pe[i] is None:
        continue
    m = abs(pb[i]) * 1e4
    if m < 12:
        continue
    hit = 1 if ((out[i] == 0) if pb[i] > 0 else (out[i] == 1)) else 0
    ev_all[i] = hit
    move_of[i] = m
    joint_of[i] = (pe[i] * pb[i] > 0) and abs(pe[i]) * 1e4 >= ETH_THR

def q_of(d):
    return (len(d), sum(d.values()) / len(d)) if d else (0, float("nan"))

def parts(d):
    j = {i: v for i, v in d.items() if joint_of[i]}
    c = {i: v for i, v in d.items() if not joint_of[i]}
    return j, c

res = {"eth_thr_bps": ETH_THR}
print("== joint impulse (BTC>=12bps & ETH same-dir >=8bps) vs btc-only ==")
res["splits"] = {}
for name, lo, hi in [("full60d", 1, n), ("train", 1, cut), ("test", cut, n)]:
    d = {i: v for i, v in ev_all.items() if lo <= i < hi}
    j, c = parts(d)
    nj, qj = q_of(j); nc, qc = q_of(c); na, qa = q_of(d)
    res["splits"][name] = {"all": {"n": na, "q": qa}, "joint": {"n": nj, "q": qj},
                           "btc_only": {"n": nc, "q": qc},
                           "retention": nj / na, "delta_joint_minus_only": qj - qc}
    print(f"{name:8s} all n={na:5d} q={qa:.4f} | joint n={nj:5d} q={qj:.4f} ({nj/na:.1%} kept) | "
          f"btc-only n={nc:5d} q={qc:.4f} | delta={qj-qc:+.4f}")

print("\n== six 10d folds ==")
res["folds"] = []
for f in range(6):
    lo, hi = max(1, f * FOLD), min(n, (f + 1) * FOLD)
    d = {i: v for i, v in ev_all.items() if lo <= i < hi}
    j, c = parts(d)
    nj, qj = q_of(j); nc, qc = q_of(c)
    res["folds"].append({"fold": f, "joint": {"n": nj, "q": qj},
                         "btc_only": {"n": nc, "q": qc}, "delta": qj - qc})
    print(f"fold {f}: joint n={nj:4d} q={qj:.4f} | btc-only n={nc:4d} q={qc:.4f} | delta={qj-qc:+.4f}")

# paired-on-common-blocks bootstrap for delta
def boot_delta(d, B=4000, block=12, seed=77):
    rng = random.Random(seed)
    per_block = {}
    for i, v in d.items():
        per_block.setdefault(i // block, []).append((joint_of[i], v))
    nblocks = (n + block - 1) // block
    j, c = parts(d)
    obs = q_of(j)[1] - q_of(c)[1]
    ds = []
    for _ in range(B):
        kj = nj = kc = nc = 0
        for _ in range(nblocks):
            evs = per_block.get(rng.randrange(nblocks))
            if not evs:
                continue
            for isj, v in evs:
                if isj:
                    kj += v; nj += 1
                else:
                    kc += v; nc += 1
        if nj and nc:
            ds.append(kj / nj - kc / nc)
    ds.sort()
    m = len(ds)
    lo, hi = ds[int(.025 * m)], ds[min(m - 1, int(.975 * m))]
    p = 2 * min(sum(1 for x in ds if x <= 0) / m, sum(1 for x in ds if x >= 0) / m)
    return obs, min(1.0, p), (lo, hi)

print("\n== block-boot p for delta (joint - btc_only), common blocks ==")
res["delta_boot"] = {}
for name, lo, hi in [("full60d", 1, n), ("train", 1, cut), ("test", cut, n)]:
    d = {i: v for i, v in ev_all.items() if lo <= i < hi}
    obs, p, ci = boot_delta(d)
    res["delta_boot"][name] = {"delta": obs, "p": p, "ci": ci}
    print(f"{name:8s} delta={obs:+.4f}  p={p:.4f}  ci=({ci[0]:+.4f},{ci[1]:+.4f})")

# joint subset vs 0.5 and vs breakeven on TRAIN/TEST
print("\n== joint subset vs 0.5, block-boot ==")
res["joint_vs_half"] = {}
for name, lo, hi in [("train", 1, cut), ("test", cut, n)]:
    j = {i: v for i, v in ev_all.items() if lo <= i < hi and joint_of[i]}
    r, m, p, ci = block_bootstrap_p(j, n)
    res["joint_vs_half"][name] = {"q": r, "n": m, "p": p, "ci": ci}
    print(f"{name:5s} q={r:.4f} n={m:5d} p={p:.4f} ci=({ci[0]:.4f},{ci[1]:.4f})")

# ETH threshold sweep (monotonicity only)
print("\n== ETH same-dir threshold sweep (TRAIN | TEST), no selection ==")
res["sweep"] = {}
for thr in (4, 6, 8, 12, 16):
    row = {}
    for name, lo, hi in [("train", 1, cut), ("test", cut, n)]:
        j = {i: v for i, v in ev_all.items()
             if lo <= i < hi and pe[i] * pb[i] > 0 and abs(pe[i]) * 1e4 >= thr}
        nj, qj = q_of(j)
        row[name] = {"n": nj, "q": qj}
    res["sweep"][str(thr)] = row
    print(f"ETH>={thr:2d}bps: train q={row['train']['q']:.4f} (n={row['train']['n']:4d}) | "
          f"test q={row['test']['q']:.4f} (n={row['test']['n']:4d})")

# ALSO: divergence subset (ETH opposite >= 8bps) for completeness
print("\n== divergence subset (ETH opposite-dir >=8bps) ==")
res["divergence"] = {}
for name, lo, hi in [("train", 1, cut), ("test", cut, n)]:
    dvg = {i: v for i, v in ev_all.items()
           if lo <= i < hi and pe[i] * pb[i] < 0 and abs(pe[i]) * 1e4 >= 8}
    nd, qd = q_of(dvg)
    res["divergence"][name] = {"n": nd, "q": qd}
    print(f"{name:5s} q={qd:.4f} (n={nd})")

# regime correlation for fill adjustment: |BTC move| and eff12 for joint vs btc-only
rets = [None] + [(cb["o"][i] - cb["o"][i - 1]) / cb["o"][i - 1] for i in range(1, n)]
def eff12(i):
    h = [rets[j] for j in range(i - 12, i) if j >= 1 and rets[j] is not None]
    if len(h) < 12:
        return None
    den = sum(abs(r) for r in h)
    return abs(sum(h)) / den if den > 0 else 1.0

mj = [move_of[i] for i in ev_all if joint_of[i]]
mc = [move_of[i] for i in ev_all if not joint_of[i]]
ej = [e for i in ev_all if joint_of[i] and (e := eff12(i)) is not None]
ec = [e for i in ev_all if not joint_of[i] and (e := eff12(i)) is not None]
res["regime_corr"] = {
    "joint": {"move_mean_bps": sum(mj) / len(mj), "move_p50": pct(mj, .5),
              "eff12_mean": sum(ej) / len(ej), "eff12_p50": pct(ej, .5)},
    "btc_only": {"move_mean_bps": sum(mc) / len(mc), "move_p50": pct(mc, .5),
                 "eff12_mean": sum(ec) / len(ec), "eff12_p50": pct(ec, .5)}}
print(f"\nregime: joint |move| mean {res['regime_corr']['joint']['move_mean_bps']:.1f}bps p50 {res['regime_corr']['joint']['move_p50']:.1f} eff12 mean {res['regime_corr']['joint']['eff12_mean']:.3f}")
print(f"        btc-only    mean {res['regime_corr']['btc_only']['move_mean_bps']:.1f}bps p50 {res['regime_corr']['btc_only']['move_p50']:.1f} eff12 mean {res['regime_corr']['btc_only']['eff12_mean']:.3f}")

# EV table at fills .4774 / +1c / +2c for joint TEST/TRAIN
print("\n== EV/share (joint subset) at .4774/.4874/.4974 ==")
res["ev_table"] = {}
for name in ("train", "test"):
    q = res["joint_vs_half"][name]["q"]
    res["ev_table"][name] = {str(p): ev(q, p) for p in (0.4774, 0.4874, 0.4974)}
    print(f"{name:5s} q={q:.4f}: {ev(q,.4774)*100:+.2f}c / {ev(q,.4874)*100:+.2f}c / {ev(q,.4974)*100:+.2f}c")

json.dump(res, open(SCR + "/work/variant-asym/c_joint_impulse_results.json", "w"), indent=1)
print("\nsaved c_joint_impulse_results.json")
