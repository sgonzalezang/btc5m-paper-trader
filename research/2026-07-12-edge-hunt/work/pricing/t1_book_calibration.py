"""T1: Is the PM book itself miscalibrated? (favorite-longshot bias etc.)
Sources: pm_prices_sample.json (216 markets, Up price at 20/60/150s/last),
independent of our fills. Outcome = up_won (cross-checked vs resolution map).
Also cross-checks off-by-one contamination found in pm_res_3d.
"""
import json, math, collections
import common as C

out = {}
pm = C.load_pm_prices()
res, _ = C.resolution_map()
cb = C.cb5m_map()

# --- 0. integrity: up_won vs resolution map / off-by-one screen
n_chk = agree = shifted = 0
for r in pm:
    t0 = r["t0"]
    if t0 in res:
        n_chk += 1
        agree += (res[t0] == r["up_won"])
    cd, cn = cb.get(t0), cb.get(t0 + 300)
    if cd and cn and r["up_won"] is not None:
        mv = (cd["c"] - cd["o"]) / cd["o"]
        nx = (cn["c"] - cn["o"]) / cn["o"]
        if abs(mv) >= 4e-4 and (1 if mv >= 0 else 0) != r["up_won"] \
           and (1 if nx >= 0 else 0) == r["up_won"]:
            shifted += 1
out["integrity"] = dict(n_overlap_resmap=n_chk, agree_resmap=agree,
                        offbyone_suspects=shifted, n_sample=len(pm))

# Exclude off-by-one suspects from calibration
def is_suspect(r):
    t0 = r["t0"]
    cd, cn = cb.get(t0), cb.get(t0 + 300)
    if cd and cn:
        mv = (cd["c"] - cd["o"]) / cd["o"]
        nx = (cn["c"] - cn["o"]) / cn["o"]
        if abs(mv) >= 4e-4 and (1 if mv >= 0 else 0) != r["up_won"] \
           and (1 if nx >= 0 else 0) == r["up_won"]:
            return True
    return False

clean = [r for r in pm if not is_suspect(r)]
out["n_clean"] = len(clean)

# --- 1. calibration by snapshot time
BINS = [(0.0, 0.35), (0.35, 0.45), (0.45, 0.50), (0.50, 0.55), (0.55, 0.65), (0.65, 1.01)]
def calib(snap):
    rows = []
    pairs_dev = []   # (t0, up_won - p) for mean calibration deviation
    for lo, hi in BINS:
        w = n = 0; psum = 0.0
        for r in clean:
            p = r.get(snap)
            if p is None: continue
            if lo <= p < hi:
                n += 1; w += r["up_won"]; psum += p
        ph, l95, h95 = C.wilson(w, n)
        rows.append(dict(bin=f"[{lo},{hi})", n=n, mean_p=round(psum/n, 4) if n else None,
                         q=round(ph, 4) if n else None,
                         ci=[round(l95, 4), round(h95, 4)] if n else None,
                         q_minus_p=round(ph - psum/n, 4) if n else None))
    for r in clean:
        p = r.get(snap)
        if p is not None:
            pairs_dev.append((r["t0"], r["up_won"] - p))
    bb = C.block_boot_mean(pairs_dev)
    return dict(bins=rows, mean_up_minus_price=bb)

for snap in ("p20", "p60", "p150"):
    out[f"calib_{snap}"] = calib(snap)

# --- 2. favorite-longshot: expensive side (max(p,1-p)) win rate vs its price
def flb(snap):
    rows = []
    fav_bins = [(0.50, 0.55), (0.55, 0.60), (0.60, 0.70), (0.70, 0.85), (0.85, 1.01)]
    for lo, hi in fav_bins:
        w = n = 0; psum = 0.0
        for r in clean:
            p = r.get(snap)
            if p is None: continue
            fav_p = max(p, 1 - p)
            fav_is_up = p >= 0.5
            if lo <= fav_p < hi:
                n += 1; psum += fav_p
                w += (r["up_won"] == 1) if fav_is_up else (r["up_won"] == 0)
        ph, l95, h95 = C.wilson(w, n)
        rows.append(dict(fav_bin=f"[{lo},{hi})", n=n,
                         mean_fav_p=round(psum/n, 4) if n else None,
                         fav_q=round(ph, 4) if n else None,
                         ci=[round(l95, 4), round(h95, 4)] if n else None,
                         q_minus_p=round(ph - psum/n, 4) if n else None))
    return rows

for snap in ("p20", "p60", "p150"):
    out[f"flb_{snap}"] = flb(snap)

# --- 3. EV of blindly buying the CHEAP side at each snapshot (frozen cost model,
#     price treated as ask, +1c slip) — does raw favorite-longshot bias clear fees?
def cheap_ev(snap):
    pairs = []
    for r in clean:
        p = r.get(snap)
        if p is None: continue
        cheap_p = min(p, 1 - p)
        cheap_is_up = p < 0.5
        win = (r["up_won"] == 1) if cheap_is_up else (r["up_won"] == 0)
        fill = cheap_p + 0.01
        pairs.append((r["t0"], (1.0 if win else 0.0) - fill - C.FEE * fill * (1 - fill)))
    return C.block_boot_mean(pairs)

for snap in ("p20", "p60", "p150"):
    out[f"cheap_side_ev_{snap}"] = cheap_ev(snap)

# --- 4. EV of blindly buying the FAVORITE side (frozen model, snapshot+1c as fill),
#     all favorites and capped subset fav_p <= 0.65 (tradeable zone)
def fav_ev(snap, cap=None):
    pairs = []
    for r in clean:
        p = r.get(snap)
        if p is None: continue
        fav_p = max(p, 1 - p)
        if fav_p < 0.5:  # exact 0.5 handled as up-favorite
            continue
        if cap is not None and fav_p > cap:
            continue
        fav_is_up = p >= 0.5
        win = (r["up_won"] == 1) if fav_is_up else (r["up_won"] == 0)
        fill = fav_p + 0.01
        pairs.append((r["t0"], (1.0 if win else 0.0) - fill - C.FEE * fill * (1 - fill)))
    return C.block_boot_mean(pairs)

for snap in ("p20", "p60", "p150"):
    out[f"fav_side_ev_{snap}"] = fav_ev(snap)
    out[f"fav_side_ev_{snap}_cap65"] = fav_ev(snap, cap=0.65)

json.dump(out, open("calib.json", "w"), indent=1)
print(json.dumps(out, indent=1))
