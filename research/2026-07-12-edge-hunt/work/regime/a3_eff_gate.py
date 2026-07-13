"""A3: Efficiency-regime gates on the resolution series.
Evaluates on candle history (buffered construction, exact bot conventions):
 - ungated contrarian trigger |r[i-1]| >= 12bps, fade, fill p=0.51
 - impulse gate (live calibration): eff6 >= 0.10 AND cnt12 <= 6 (trigger-inclusive eff6,
   trigger-exclusive cnt12)
 - impulse gate (train calibration): eff6 >= 0.32 AND cnt12 <= 6
 - latentfire gate: eff12 <= 0.48 (trigger-inclusive)
Windows: TRAIN (May 11-Jun 25), TEST (Jun 26-Jul 13), FRESH (Jul 10 11:55 -> Jul 13
03:40 = data no prior analysis ever saw; the gate was frozen 2026-07-10, so FRESH is a
true out-of-sample read on both level and increment).
Stdlib only."""
import json, sys
sys.path.insert(0, "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work/regime")
from lib import *

t, o = load_cb5m()
t0s, r, up = build_series(t, o)
n = len(t0s)

# Precompute per-trigger features
triggers = []   # dicts: i, t0, win(0/1), eff6, cnt12, eff12
for i in range(13, n):
    if abs(r[i - 1]) < 0.0012 or r[i - 1] == 0:
        continue
    prior_up = r[i - 1] > 0
    win = 1.0 if up[i] != prior_up else 0.0
    last6 = r[i - 6:i]
    e6 = eff(last6)
    e12 = eff(r[i - 12:i])
    c12 = sum(1 for j in range(i - 13, i - 1) if abs(r[j]) >= 0.0012)
    triggers.append({"i": i, "t0": t0s[i], "win": win, "eff6": e6, "cnt12": c12, "eff12": e12})

print(f"triggers: {len(triggers)}")

GATES = {
    "ungated": lambda g: True,
    "impulse_live_A010_B6": lambda g: g["eff6"] >= 0.10 and g["cnt12"] <= 6,
    "impulse_train_A032_B6": lambda g: g["eff6"] >= 0.32 and g["cnt12"] <= 6,
    "latentfire_eff12_le048": lambda g: g["eff12"] <= 0.48,
}

WINDOWS = {
    "TRAIN": (0, TEST_START),
    "TEST": (TEST_START, 1 << 62),
    "FRESH_jul10_13": (FRESH_START, 1 << 62),
}

out = {"n_triggers_total": len(triggers), "conventions": "buffered open-to-open; fade prior >=12bps move; fill p=0.51; ev=q-0.527493"}
for wname, (lo_t, hi_t) in WINDOWS.items():
    sub = [g for g in triggers if lo_t <= g["t0"] < hi_t]
    sec = {"n_triggers": len(sub)}
    for gname, fn in GATES.items():
        sel = [g for g in sub if fn(g)]
        if not sel:
            sec[gname] = {"n": 0}
            continue
        nn = len(sel)
        q = sum(g["win"] for g in sel) / nn
        evs = [(hour_block(g["t0"]), ev_cents(g["win"])) for g in sel]
        obs, lo95, hi95, ple = block_boot_mean(evs, None, B=4000, seed=hash(gname) % 9999)
        row = {"n": nn, "wr": round(q, 4), "ev_c": round(ev_cents(q), 2),
               "ev_ci": [round(lo95, 2), round(hi95, 2)], "p_ev_le_0": round(ple, 4),
               "retention": round(nn / len(sub), 3)}
        # gate increment vs complementary set (gated minus ungated-rest)
        if gname != "ungated":
            rest = [g for g in sub if not fn(g)]
            if rest:
                a = [(hour_block(g["t0"]), ev_cents(g["win"])) for g in sel]
                b = [(hour_block(g["t0"]), ev_cents(g["win"])) for g in rest]
                dd, dl, dh, dp = block_boot_diff(a, b, B=4000, seed=hash(gname) % 7777)
                row["increment_vs_excluded"] = {"diff_c": round(dd, 2), "ci": [round(dl, 2), round(dh, 2)],
                                                "p_le_0": round(dp, 4), "n_excluded": len(rest),
                                                "wr_excluded": round(sum(g['win'] for g in rest)/len(rest), 4)}
        sec[gname] = row
    out[wname] = sec
    print(wname, json.dumps(sec, indent=1))

json.dump(out, open("/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work/regime/a3_results.json", "w"), indent=1)
print("saved a3_results.json")
