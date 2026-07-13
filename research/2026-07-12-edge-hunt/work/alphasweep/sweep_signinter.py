"""Family 1b: sign-interaction of prior 5m (r1) and prior 15m (r3) returns.
Magnitude conditions fixed a priori: |r1| >= 4bps, |r3| >= 8bps.
Patterns: agree (sign r1 == sign r3) -> {mom, rev};
          disagree -> {follow_r1, follow_r3} (each implies the other's fade).
Plus the same 4 with the vol condition vol36 above/below its trailing median (x2).
K1b = 4 + 8 = 12
"""
import json
from common import Table, eval_signal

tab = Table()
grid = []

def run(name, fire):
    r = eval_signal(tab, fire, reps=2000)
    r["name"] = name; r["fires"] = len(fire)
    grid.append(r)

def base_fires():
    agree_m, agree_r, dis_f1, dis_f3 = {}, {}, {}, {}
    vols = {}
    for i in range(40, tab.n - 1):
        r1, r3 = tab.prior_ret(i, 1), tab.prior_ret(i, 3)
        if r1 is None or r3 is None or abs(r1) < 0.0004 or abs(r3) < 0.0008:
            continue
        s1 = "up" if r1 > 0 else "down"
        s3 = "up" if r3 > 0 else "down"
        vols[i] = tab.trailing_vol(i)
        if s1 == s3:
            agree_m[i] = s1
            agree_r[i] = "down" if s1 == "up" else "up"
        else:
            dis_f1[i] = s1
            dis_f3[i] = s3
    return agree_m, agree_r, dis_f1, dis_f3, vols

am, ar, d1, d3, vols = base_fires()
run("sign_agree_mom", am)
run("sign_agree_rev", ar)
run("sign_disagree_follow_r1", d1)
run("sign_disagree_follow_r3", d3)

# vol split: median of trailing vol over TRAIN period only (no look-ahead in threshold)
from common import SPLIT_TS
tr_vols = sorted(v for i, v in vols.items() if v is not None and tab.t[i] < SPLIT_TS)
vmed = tr_vols[len(tr_vols) // 2]
for tag, cond in (("hivol", lambda v: v is not None and v > vmed),
                  ("lovol", lambda v: v is not None and v <= vmed)):
    for nm, fire in (("agree_mom", am), ("agree_rev", ar),
                     ("disagree_follow_r1", d1), ("disagree_follow_r3", d3)):
        sub = {i: s for i, s in fire.items() if cond(vols.get(i))}
        run(f"sign_{nm}_{tag}", sub)

K = len(grid)
cands = [g for g in grid if g["TRAIN"].get("n", 0) >= 250]
cands.sort(key=lambda g: g["TRAIN"]["ev_c"], reverse=True)
pick = cands[0] if cands else None
json.dump({"K": K, "pick": pick, "grid": grid},
          open("family1b_signinter.json", "w"), indent=1)
print("K =", K)
if pick:
    print("pick ->", pick["name"], "TRAIN", pick["TRAIN"], "TEST", pick["TEST"])
for g in grid:
    print(f"{g['name']:32} TRAIN ev {g['TRAIN'].get('ev_c')} p {g['TRAIN'].get('p_boot')} n {g['TRAIN'].get('n')} | TEST ev {g['TEST'].get('ev_c')} p {g['TEST'].get('p_boot')} n {g['TEST'].get('n')}")
