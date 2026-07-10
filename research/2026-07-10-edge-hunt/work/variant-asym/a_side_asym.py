"""(a) Side asymmetry of the 12bps buffered reversal (flagship reversal_v2 baseline).

fade-after-UP  : prior open-to-open move >= +12bps -> buy DOWN (tie LOSES: ties resolve Up)
fade-after-DOWN: prior move <= -12bps            -> buy UP   (tie WINS)

Outputs: 60d overall / TRAIN(first 2/3) / TEST(last 1/3) / six 10d folds, by side;
move-size interaction by side; 1h-block-bootstrap p for the side DELTA (common blocks);
tie-zone (|c-o|<2bps) contamination by side. stdlib only.
"""
import sys, json
SCR = "/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad"
sys.path.insert(0, SCR + "/work/crossasset")
from util import load, prior_oo, outcomes, block_bootstrap_p, ev, qstar, pct
import random

cb = load("cb5m")
n = len(cb["t"])
pb = prior_oo(cb["o"])
out = outcomes(cb["o"], cb["c"])          # 1 = Up (ties Up)
cut = int(n * 2 / 3)
FOLD = 2880                                # 10 days of 5m intervals

# ---- signal construction (identical to flagship baseline) ----
# ev_all[i] = 1 if contrarian side won at interval i
ev_all, side_of = {}, {}
for i in range(1, n):
    if pb[i] is None:
        continue
    m = abs(pb[i]) * 1e4
    if m < 12:
        continue
    if pb[i] > 0:                          # fade an up-move -> buy Down
        side_of[i] = "down"
        ev_all[i] = 1 if out[i] == 0 else 0
    else:                                  # fade a down-move -> buy Up
        side_of[i] = "up"
        ev_all[i] = 1 if out[i] == 1 else 0

def q_of(d):
    if not d:
        return (0, float("nan"))
    return (len(d), sum(d.values()) / len(d))

nb, qb = q_of(ev_all)
print(f"baseline reproduction: n={nb} q={qb:.4f}  (expect 4023 / .5334)")

res = {"baseline": {"n": nb, "q": qb}}

def sub(d, lo, hi):
    return {i: v for i, v in d.items() if lo <= i < hi}

def by_side(d):
    up_ev = {i: v for i, v in d.items() if side_of[i] == "up"}    # fade-after-down
    dn_ev = {i: v for i, v in d.items() if side_of[i] == "down"}  # fade-after-up
    return dn_ev, up_ev

# ---- overall / train / test by side ----
print("\n== side split (fadeUP = buy Down after +move; fadeDOWN = buy Up after -move) ==")
res["splits"] = {}
for name, lo, hi in [("full60d", 1, n), ("train", 1, cut), ("test", cut, n)]:
    d = sub(ev_all, lo, hi)
    dn, up = by_side(d)
    ndn, qdn = q_of(dn)
    nup, qup = q_of(up)
    res["splits"][name] = {"fadeUP_buyDown": {"n": ndn, "q": qdn},
                           "fadeDOWN_buyUp": {"n": nup, "q": qup},
                           "delta_up_minus_down": qdn - qup}
    print(f"{name:8s} fadeUP n={ndn:5d} q={qdn:.4f} | fadeDOWN n={nup:5d} q={qup:.4f} | delta(fadeUP-fadeDOWN)={qdn-qup:+.4f}")

# ---- six 10d folds ----
print("\n== six 10d folds ==")
res["folds"] = []
for f in range(6):
    lo, hi = max(1, f * FOLD), min(n, (f + 1) * FOLD)
    d = sub(ev_all, lo, hi)
    dn, up = by_side(d)
    ndn, qdn = q_of(dn)
    nup, qup = q_of(up)
    res["folds"].append({"fold": f, "fadeUP": {"n": ndn, "q": qdn},
                         "fadeDOWN": {"n": nup, "q": qup}, "delta": qdn - qup})
    print(f"fold {f}: fadeUP n={ndn:4d} q={qdn:.4f} | fadeDOWN n={nup:4d} q={qup:.4f} | delta={qdn-qup:+.4f}")

# ---- block bootstrap of the side DELTA on common 1h blocks ----
def boot_delta(d, n_total, block=12, B=4000, seed=99):
    rng = random.Random(seed)
    per_block = {}
    for i, v in d.items():
        per_block.setdefault(i // block, []).append((side_of[i], v))
    nblocks = (n_total + block - 1) // block
    obs_dn, obs_up = by_side(d)
    obs = (sum(obs_dn.values()) / len(obs_dn)) - (sum(obs_up.values()) / len(obs_up))
    deltas = []
    for _ in range(B):
        kd = nd = ku = nu = 0
        for _ in range(nblocks):
            evs = per_block.get(rng.randrange(nblocks))
            if not evs:
                continue
            for s, v in evs:
                if s == "down":
                    kd += v; nd += 1
                else:
                    ku += v; nu += 1
        if nd and nu:
            deltas.append(kd / nd - ku / nu)
    deltas.sort()
    m = len(deltas)
    lo, hi = deltas[int(.025 * m)], deltas[min(m - 1, int(.975 * m))]
    below = sum(1 for x in deltas if x <= 0) / m
    above = sum(1 for x in deltas if x >= 0) / m
    return obs, min(1.0, 2 * min(below, above)), (lo, hi)

print("\n== block-bootstrap p for side delta (fadeUP q - fadeDOWN q) ==")
res["delta_boot"] = {}
for name, lo, hi in [("full60d", 1, n), ("train", 1, cut), ("test", cut, n)]:
    obs, p, ci = boot_delta(sub(ev_all, lo, hi), n)
    res["delta_boot"][name] = {"delta": obs, "p": p, "ci": ci}
    print(f"{name:8s} delta={obs:+.4f}  p={p:.4f}  ci=({ci[0]:+.4f},{ci[1]:+.4f})")

# ---- move-size interaction by side ----
print("\n== move-size buckets by side (TRAIN | TEST) ==")
res["size_buckets"] = {}
for blo, bhi in [(12, 16), (16, 20), (20, 30), (30, 1e9)]:
    row = {}
    for sname, sl in [("fadeUP", "down"), ("fadeDOWN", "up")]:
        tr = {i: v for i, v in ev_all.items()
              if i < cut and side_of[i] == sl and blo <= abs(pb[i]) * 1e4 < bhi}
        te = {i: v for i, v in ev_all.items()
              if i >= cut and side_of[i] == sl and blo <= abs(pb[i]) * 1e4 < bhi}
        ntr, qtr = q_of(tr); nte, qte = q_of(te)
        row[sname] = {"train": {"n": ntr, "q": qtr}, "test": {"n": nte, "q": qte}}
    lab = f"[{blo},{'inf' if bhi > 1e8 else int(bhi)})"
    res["size_buckets"][lab] = row
    r = row
    print(f"{lab:>9} fadeUP tr {r['fadeUP']['train']['q']:.4f}({r['fadeUP']['train']['n']:4d}) te {r['fadeUP']['test']['q']:.4f}({r['fadeUP']['test']['n']:3d}) | "
          f"fadeDOWN tr {r['fadeDOWN']['train']['q']:.4f}({r['fadeDOWN']['train']['n']:4d}) te {r['fadeDOWN']['test']['q']:.4f}({r['fadeDOWN']['test']['n']:3d})")

# ---- tie-zone contamination: |c-o| < 2bps outcomes by side ----
print("\n== tie-zone (|c-o|<2bps, ~11% oracle noise + ties resolve Up) ==")
res["tiezone"] = {}
for sname, sl in [("fadeUP_buyDown", "down"), ("fadeDOWN_buyUp", "up")]:
    sel = [i for i in ev_all if side_of[i] == sl]
    tz = [i for i in sel if abs(cb["c"][i] - cb["o"][i]) / cb["o"][i] * 1e4 < 2]
    win_in_tz = sum(ev_all[i] for i in tz)
    ex = {i: ev_all[i] for i in sel if i not in set(tz)}
    nex, qex = q_of(ex)
    res["tiezone"][sname] = {"n_signals": len(sel), "n_tiezone": len(tz),
                             "tz_frac": len(tz) / len(sel), "wins_in_tz": win_in_tz,
                             "q_excl_tiezone": qex, "n_excl": nex}
    print(f"{sname}: {len(tz)}/{len(sel)} in tie-zone ({len(tz)/len(sel):.3f}), wins there {win_in_tz}; q excl-tz {qex:.4f} (n={nex})")

# ---- block-boot p vs 0.5 for each side, TRAIN (bar: p<0.01 TRAIN + TEST persistence) ----
print("\n== each side vs 0.5, block-boot (TRAIN, then TEST) ==")
res["side_vs_half"] = {}
for sname, sl in [("fadeUP", "down"), ("fadeDOWN", "up")]:
    for wname, lo, hi in [("train", 1, cut), ("test", cut, n)]:
        d = {i: v for i, v in sub(ev_all, lo, hi).items() if side_of[i] == sl}
        r, m, p, ci = block_bootstrap_p(d, n)
        res["side_vs_half"][f"{sname}_{wname}"] = {"q": r, "n": m, "p": p, "ci": ci}
        print(f"{sname:8s} {wname:5s} q={r:.4f} n={m:5d} p={p:.4f} ci=({ci[0]:.4f},{ci[1]:.4f})")

# ---- EV at the ledger fill mix and sensitivities ----
print("\n== EV/share at fill .4774 / .4874 / .4974 ==")
res["ev_table"] = {}
for sname in ["fadeUP", "fadeDOWN"]:
    key = "fadeUP_buyDown" if sname == "fadeUP" else "fadeDOWN_buyUp"
    qte = res["splits"]["test"][key]["q"]
    qtr = res["splits"]["train"][key]["q"]
    row = {}
    for p in (0.4774, 0.4874, 0.4974):
        row[str(p)] = {"train": ev(qtr, p), "test": ev(qte, p)}
    res["ev_table"][sname] = row
    print(f"{sname}: TEST q={qte:.4f} -> EV {ev(qte,.4774)*100:+.2f}c / {ev(qte,.4874)*100:+.2f}c / {ev(qte,.4974)*100:+.2f}c ; TRAIN q={qtr:.4f} -> {ev(qtr,.4774)*100:+.2f}c / {ev(qtr,.4874)*100:+.2f}c / {ev(qtr,.4974)*100:+.2f}c")

json.dump(res, open(SCR + "/work/variant-asym/a_side_asym_results.json", "w"), indent=1)
print("\nsaved a_side_asym_results.json")
