"""Families 3 and 5.

Family 3 — ETH lead (prior DEAD as filter; cheap standalone confirmation):
  eth prior return over k in {1,3} intervals, thr in {5,10,20,30} bps, dir {follow, fade} = 16
  plus eth-minus-btc divergence: (eth_r - btc_r) over prior interval, thr {5,10,20} bps x dir = 6
K3 = 22

Family 5 — volume spikes and candle shape on cb5m (prior candle, known at t0):
  volspike: v[i-1]/mean(v[i-37..i-1]) >= m for m in {2,3,5}, side = mom/rev of prior ret = 12
            (needs prior ret sign; |prior ret| >= 2bps to define a side)
  clv:      close-location-value of prior candle (2c-h-l)/(h-l) thresholds
            {>=0.8, >=0.9, <=-0.8, <=-0.9} x dir {follow, fade} = 8
  wick:     dominant wick fraction of prior candle range >= {0.5, 0.65} on up/down candles,
            dir {follow(wick points reversal), fade} = 8
K5 = 28
Selection: best TRAIN ev_c per sub-family with TRAIN n >= 250.
"""
import json
from common import Table, eval_signal, DATA, load_candles

tab = Table()
grid = []

def run(name, fire):
    r = eval_signal(tab, fire, reps=2000)
    r["name"] = name
    r["fires"] = len(fire)
    grid.append(r)
    return r

# ---- Family 3: ETH lead
eth = load_candles(f"{DATA}/eth5m.json")
eo = {t: o for t, o in zip(eth["t"], eth["o"])}
for k in (1, 3):
    for thr_bps in (5, 10, 20, 30):
        thr = thr_bps / 10000.0
        fire_f, fire_x = {}, {}
        for i in range(k, tab.n - 1):
            t0 = tab.t[i]
            a, b = eo.get(t0), eo.get(t0 - 300 * k)
            if a is None or b is None:
                continue
            er = (a - b) / b
            if abs(er) < thr:
                continue
            side = "up" if er > 0 else "down"
            fire_f[i] = side
            fire_x[i] = "down" if side == "up" else "up"
        run(f"eth_k{k}_thr{thr_bps}bps_follow", fire_f)
        run(f"eth_k{k}_thr{thr_bps}bps_fade", fire_x)

for thr_bps in (5, 10, 20):
    thr = thr_bps / 10000.0
    fire_f, fire_x = {}, {}
    for i in range(1, tab.n - 1):
        t0 = tab.t[i]
        a, b = eo.get(t0), eo.get(t0 - 300)
        br = tab.prior_ret(i, 1)
        if a is None or b is None or br is None:
            continue
        div = (a - b) / b - br
        if abs(div) < thr:
            continue
        side = "up" if div > 0 else "down"   # ETH outran BTC -> BTC catches up
        fire_f[i] = side
        fire_x[i] = "down" if side == "up" else "up"
    run(f"ethdiv_thr{thr_bps}bps_follow", fire_f)
    run(f"ethdiv_thr{thr_bps}bps_fade", fire_x)

# ---- Family 5: volume spike
for m in (2, 3, 5):
    for dirn in ("mom", "rev"):
        fire = {}
        for i in range(38, tab.n - 1):
            vwin = tab.v[i - 37:i - 1]
            mv = sum(vwin) / len(vwin)
            if mv <= 0 or tab.v[i - 1] < m * mv:
                continue
            r = tab.prior_ret(i, 1)
            if r is None or abs(r) < 0.0002:
                continue
            mom_side = "up" if r > 0 else "down"
            fire[i] = mom_side if dirn == "mom" else ("down" if mom_side == "up" else "up")
        run(f"volspike_m{m}_{dirn}", fire)
# volspike with no direction condition on ret sign but sided by candle body
for m in (2, 3):
    for dirn in ("mom", "rev"):
        fire = {}
        for i in range(38, tab.n - 1):
            vwin = tab.v[i - 37:i - 1]
            mv = sum(vwin) / len(vwin)
            if mv <= 0 or tab.v[i - 1] < m * mv:
                continue
            body = tab.c[i - 1] - tab.o[i - 1]
            if body == 0:
                continue
            mom_side = "up" if body > 0 else "down"
            fire[i] = mom_side if dirn == "mom" else ("down" if mom_side == "up" else "up")
        run(f"volspike_body_m{m}_{dirn}", fire)

# ---- Family 5: CLV
for thr, tag in ((0.8, "ge08"), (0.9, "ge09"), (-0.8, "le08"), (-0.9, "le09")):
    for dirn in ("follow", "fade"):
        fire = {}
        for i in range(1, tab.n - 1):
            h, l, c = tab.h[i - 1], tab.l[i - 1], tab.c[i - 1]
            if h == l:
                continue
            clv = (2 * c - h - l) / (h - l)
            hit = clv >= thr if thr > 0 else clv <= thr
            if not hit:
                continue
            strong = "up" if thr > 0 else "down"   # close pinned at high -> strength
            fire[i] = strong if dirn == "follow" else ("down" if strong == "up" else "up")
        run(f"clv_{tag}_{dirn}", fire)

# ---- Family 5: dominant wick
for wthr in (0.5, 0.65):
    for dirn in ("wickrev", "wickfade"):
        fire = {}
        for i in range(1, tab.n - 1):
            o, h, l, c = tab.o[i - 1], tab.h[i - 1], tab.l[i - 1], tab.c[i - 1]
            rng = h - l
            if rng <= 0:
                continue
            up_wick = (h - max(o, c)) / rng
            dn_wick = (min(o, c) - l) / rng
            if max(up_wick, dn_wick) < wthr:
                continue
            # long upper wick = rejection of highs -> reversal side is down
            rev_side = "down" if up_wick > dn_wick else "up"
            fire[i] = rev_side if dirn == "wickrev" else ("down" if rev_side == "up" else "up")
        run(f"wick_{wthr}_{dirn}", fire)

K = len(grid)
picks = {}
for sub, pref in (("eth_lead", "eth_k"), ("eth_div", "ethdiv_"),
                  ("volspike", "volspike_"), ("clv", "clv_"), ("wick", "wick_")):
    cands = [g for g in grid if g["name"].startswith(pref)
             and g["TRAIN"].get("n", 0) >= 250]
    cands.sort(key=lambda g: g["TRAIN"]["ev_c"], reverse=True)
    picks[sub] = cands[0] if cands else None

json.dump({"K": K, "picks": picks, "grid": grid},
          open("family35_eth_shape.json", "w"), indent=1)
print("K =", K)
for sub, p in picks.items():
    if p:
        print(sub, "->", p["name"], "TRAIN", p["TRAIN"], "TEST", p["TEST"])
    else:
        print(sub, "-> none")
