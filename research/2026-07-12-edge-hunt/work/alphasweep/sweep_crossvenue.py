"""Family 2: cross-venue standalone signals (prior work only tested these as filters).

2a gap:     bn5m minus cb5m prior-interval open-to-open return gap. Binance candle open
            at t0 = first trade at/after t0, known at decision time. Data ends Jul 10
            11:50 UTC -> TEST is Jun 26 - Jul 10 (shortened, stated).
2b premium: perp premium index (binance.vision premiumIndexKlines). Candle with open
            time t0-300 closes exactly at t0; the index is computed from live mark/index
            prices, so its close is known at t0. Level (vs trailing 1d distribution)
            and change tested. Data ends Jul 9 23:55.
2c oi:      open-interest 5m samples come from Binance daily metric files with
            publication delay -> lagged one full interval (use delta ending t0-300).
            Data Jun 10 - Jul 10: TRAIN here is Jun 10-25 (short, stated).

Grid counted toward K:
  gap:     thr in {1,2,3,5,8} bps x dir {follow_gap, fade_gap}                = 10
  premchg: change over prior candle thr in {0.5,1,2,3} bps x dir              = 8
  premlvl: level percentile vs trailing 288 candles, {>=90,>=75,<=25,<=10} x dir = 8
  oi:      delta over {1,3} intervals sign x prior cb ret sign combos, 4 combos x dir = 16
K_family2 = 42
Selection: best TRAIN ev_c per sub-family with TRAIN n >= 250.
"""
import json
from common import Table, eval_signal, DATA10, load_candles

tab = Table()
grid = []

def run(name, fire):
    r = eval_signal(tab, fire, reps=2000)
    r["name"] = name
    r["fires"] = len(fire)
    grid.append(r)
    return r

# ---- 2a: Binance-Coinbase gap
bn = load_candles(f"{DATA10}/bn5m.json")
bn_o = {t: o for t, o in zip(bn["t"], bn["o"])}
for thr_bps in (1, 2, 3, 5, 8):
    thr = thr_bps / 10000.0
    fire_f, fire_x = {}, {}
    for i in range(1, tab.n - 1):
        t0, tm1 = tab.t[i], tab.t[i - 1]
        if t0 not in bn_o or tm1 not in bn_o:
            continue
        cb_r = tab.prior_ret(i, 1)
        bn_r = (bn_o[t0] - bn_o[tm1]) / bn_o[tm1]
        gap = bn_r - cb_r
        if abs(gap) < thr:
            continue
        side = "up" if gap > 0 else "down"   # Binance led up -> Coinbase catches up
        fire_f[i] = side
        fire_x[i] = "down" if side == "up" else "up"
    run(f"gap_thr{thr_bps}bps_follow", fire_f)
    run(f"gap_thr{thr_bps}bps_fade", fire_x)

# ---- 2b: premium index
prem = load_candles(f"{DATA10}/premium5m.json")
pc = {t: c for t, c in zip(prem["t"], prem["c"])}
prem_ts = prem["t"]
prem_c = prem["c"]
idx_of = {t: j for j, t in enumerate(prem_ts)}
# change over prior candle: close(t0-300) - close(t0-600)
for thr_bps in (0.5, 1, 2, 3):
    thr = thr_bps / 10000.0
    fire_f, fire_x = {}, {}
    for i in range(2, tab.n - 1):
        t0 = tab.t[i]
        j = idx_of.get(t0 - 300)
        if j is None or j < 1 or prem_ts[j - 1] != t0 - 600:
            continue
        chg = prem_c[j] - prem_c[j - 1]
        if abs(chg) < thr:
            continue
        side = "up" if chg > 0 else "down"   # premium rising = perp bid firming -> follow
        fire_f[i] = side
        fire_x[i] = "down" if side == "up" else "up"
    run(f"premchg_thr{thr_bps}bps_follow", fire_f)
    run(f"premchg_thr{thr_bps}bps_fade", fire_x)

# level percentile vs trailing 288 (1 day)
for pct, tag in ((90, "ge90"), (75, "ge75"), (25, "le25"), (10, "le10")):
    fire_f, fire_x = {}, {}
    for i in range(2, tab.n - 1):
        t0 = tab.t[i]
        j = idx_of.get(t0 - 300)
        if j is None or j < 288:
            continue
        window = prem_c[j - 288:j]
        cur = prem_c[j]
        rank = sum(1 for x in window if x <= cur) / 288.0 * 100
        hit = (rank >= pct) if tag.startswith("ge") else (rank <= pct)
        if not hit:
            continue
        # high premium = leveraged longs stretched -> fade = down; low premium -> fade = up
        side_f = "up" if tag.startswith("ge") else "down"   # follow the crowd
        fire_f[i] = side_f
        fire_x[i] = "down" if side_f == "up" else "up"
    run(f"premlvl_{tag}_follow", fire_f)
    run(f"premlvl_{tag}_fade", fire_x)

# ---- 2c: OI delta (lagged one interval for publication delay)
oi = load_candles(f"{DATA10}/oi5m.json")
oi_v = {t: x for t, x in zip(oi["t"], oi["oi"])}
for lag_k in (1, 3):
    for combo in ("oiup_retup", "oiup_retdn", "oidn_retup", "oidn_retdn"):
        fire_f, fire_x = {}, {}
        for i in range(4, tab.n - 1):
            t0 = tab.t[i]
            a, b = oi_v.get(t0 - 300), oi_v.get(t0 - 300 - 300 * lag_k)
            if a is None or b is None:
                continue
            d = a - b
            cb_r = tab.prior_ret(i, 1)
            if cb_r is None or d == 0 or cb_r == 0:
                continue
            oi_up = d > 0
            ret_up = cb_r > 0
            key = ("oiup" if oi_up else "oidn") + "_" + ("retup" if ret_up else "retdn")
            if key != combo:
                continue
            # follow = new money confirms the move -> momentum side of prior ret
            side_f = "up" if ret_up else "down"
            fire_f[i] = side_f
            fire_x[i] = "down" if side_f == "up" else "up"
        run(f"oi_lag{lag_k}_{combo}_follow", fire_f)
        run(f"oi_lag{lag_k}_{combo}_fade", fire_x)

K = len(grid)
picks = {}
for sub, pref in (("gap", "gap_"), ("premium_chg", "premchg_"),
                  ("premium_lvl", "premlvl_"), ("oi", "oi_")):
    cands = [g for g in grid if g["name"].startswith(pref)
             and g["TRAIN"].get("n", 0) >= 250]
    cands.sort(key=lambda g: g["TRAIN"]["ev_c"], reverse=True)
    picks[sub] = cands[0] if cands else None

json.dump({"K": K, "picks": picks, "grid": grid},
          open("family2_crossvenue.json", "w"), indent=1)
print("K =", K)
for sub, p in picks.items():
    if p:
        print(sub, "->", p["name"], "TRAIN", p["TRAIN"], "TEST", p["TEST"])
    else:
        print(sub, "-> no candidate with TRAIN n>=250")
