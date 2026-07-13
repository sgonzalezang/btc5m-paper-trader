"""Family 1: multi-lag momentum/reversal on cb5m opens, raw and vol-normalized.

Grid (all counted toward K):
  raw:      horizon k in {1,3,6,12} intervals x threshold thr in
            {2,5,8,12,20,30} bps (scaled: on |prior_ret|) x dir in {mom, rev}
  volnorm:  same horizons x z in {0.5,1,1.5,2,3} (|prior_ret| >= z * vol36 * sqrt(k)) x dir
Selection: per sub-family, best TRAIN ev_c with TRAIN n >= 250; evaluate that pick on TEST.
All grid cells' TRAIN+TEST stats are dumped for audit (TEST numbers of non-picks are
diagnostic only and do not become claims).
"""
import json
from common import Table, eval_signal

tab = Table()
grid = []

def run(name, fire):
    r = eval_signal(tab, fire, reps=2000)
    r["name"] = name
    r["fires"] = len(fire)
    grid.append(r)
    return r

# raw momentum/reversal
for k in (1, 3, 6, 12):
    for thr_bps in (2, 5, 8, 12, 20, 30):
        thr = thr_bps / 10000.0
        fire_m, fire_r = {}, {}
        for i in range(12, tab.n - 1):
            r = tab.prior_ret(i, k)
            if r is None or abs(r) < thr:
                continue
            side_mom = "up" if r > 0 else "down"
            fire_m[i] = side_mom
            fire_r[i] = "down" if side_mom == "up" else "up"
        run(f"raw_k{k}_thr{thr_bps}bps_mom", fire_m)
        run(f"raw_k{k}_thr{thr_bps}bps_rev", fire_r)

# vol-normalized
for k in (1, 3, 6, 12):
    for z in (0.5, 1, 1.5, 2, 3):
        fire_m, fire_r = {}, {}
        for i in range(40, tab.n - 1):
            r = tab.prior_ret(i, k)
            vol = tab.trailing_vol(i)
            if r is None or vol is None or vol <= 0:
                continue
            if abs(r) < z * vol * (k ** 0.5):
                continue
            side_mom = "up" if r > 0 else "down"
            fire_m[i] = side_mom
            fire_r[i] = "down" if side_mom == "up" else "up"
        run(f"vnorm_k{k}_z{z}_mom", fire_m)
        run(f"vnorm_k{k}_z{z}_rev", fire_r)

K = len(grid)
picks = {}
for sub, pref in (("momrev_raw", "raw_"), ("momrev_volnorm", "vnorm_")):
    cands = [g for g in grid if g["name"].startswith(pref)
             and g["TRAIN"].get("n", 0) >= 250]
    cands.sort(key=lambda g: g["TRAIN"]["ev_c"], reverse=True)
    picks[sub] = cands[0] if cands else None

json.dump({"K": K, "picks": picks, "grid": grid},
          open("family1_momrev.json", "w"), indent=1)
print("K =", K)
for sub, p in picks.items():
    print(sub, "->", p["name"], "TRAIN", p["TRAIN"], "TEST", p["TEST"])
