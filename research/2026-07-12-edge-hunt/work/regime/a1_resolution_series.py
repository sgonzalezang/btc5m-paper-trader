"""A1: Resolution-series structure.
Runs test + sign autocorrelation lags 1-12, TRAIN/TEST, then reversal rate
conditional on prior |move| buckets with fee-adjusted EV. Stdlib only."""
import json, math, sys
sys.path.insert(0, "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work/regime")
from lib import *

t, o = load_cb5m()
t0s, r, up = build_series(t, o)
n = len(t0s)
print(f"intervals: {n}  ties(r==0): {sum(1 for x in r if x==0)}")

out = {"n_total": n}

def runs_test(bits):
    n1 = sum(bits); n0 = len(bits) - n1
    if n1 == 0 or n0 == 0:
        return None
    runs = 1 + sum(1 for a, b in zip(bits, bits[1:]) if a != b)
    mu = 1 + 2 * n1 * n0 / (n1 + n0)
    var = (mu - 1) * (mu - 2) / (n1 + n0 - 1)
    z = (runs - mu) / math.sqrt(var)
    return {"n": len(bits), "n_up": n1, "runs": runs, "expected": round(mu, 1),
            "z": round(z, 3), "p": round(2 * (1 - phi(abs(z))), 5)}

def sign_autocorr(bits, lag):
    x = [1.0 if b else -1.0 for b in bits]
    m = sum(x) / len(x)
    num = sum((x[i] - m) * (x[i + lag] - m) for i in range(len(x) - lag))
    den = sum((xi - m) ** 2 for xi in x)
    return num / den

for lbl, lo_t, hi_t in [("TRAIN", 0, TEST_START), ("TEST", TEST_START, 1 << 62)]:
    idx = [i for i in range(n) if lo_t <= t0s[i] < hi_t]
    bits = [up[i] for i in idx]
    sec = {"n": len(bits), "p_up": round(sum(bits) / len(bits), 4)}
    sec["runs_test"] = runs_test(bits)
    # autocorrelation lags 1..12 with block-bootstrap CI for each lag
    acs = {}
    for lag in range(1, 13):
        ac = sign_autocorr(bits, lag)
        # block bootstrap: product pairs (x_i*x_{i+lag}) attributed to hour block of i
        x = [1.0 if b else -1.0 for b in bits]
        m = sum(x) / len(x)
        vals = [(hour_block(t0s[idx[i]]), (x[i] - m) * (x[i + lag] - m))
                for i in range(len(x) - lag)]
        obs, blo, bhi, ple = block_boot_mean(vals, None, B=2000, seed=100 + lag)
        var = sum((xi - m) ** 2 for xi in x) / len(x)
        acs[lag] = {"ac": round(ac, 4),
                    "boot_ci": [round(blo / var, 4), round(bhi / var, 4)],
                    "p_le_0": round(ple, 4)}
    sec["sign_autocorr"] = acs
    out[lbl] = sec
    print(lbl, sec["runs_test"], "lag1", acs[1])

# Conditional on prior |move| buckets: P(next reverses prior)
BUCKETS = [(0, 2), (2, 4), (4, 8), (8, 12), (12, 20), (20, 9999)]
cond = {}
for lbl, lo_t, hi_t in [("TRAIN", 0, TEST_START), ("TEST", TEST_START, 1 << 62)]:
    rows = {}
    for blo, bhi in BUCKETS:
        wins = []          # (hour_block, 1/0 reversal)
        for i in range(1, n):
            if not (lo_t <= t0s[i] < hi_t):
                continue
            pm = abs(r[i - 1]) * 1e4
            if not (blo <= pm < bhi):
                continue
            if r[i - 1] == 0:
                continue
            prior_up = r[i - 1] > 0
            rev = (up[i] != prior_up)
            wins.append((hour_block(t0s[i]), 1.0 if rev else 0.0))
        if not wins:
            continue
        nn = len(wins)
        q = sum(v for _, v in wins) / nn
        # EV as contrarian trade at p=0.51, block-boot on EV series
        evs = [(b, ev_cents(v)) for b, v in wins]   # per-trade ev realization q->win indicator
        obs, lo95, hi95, ple = block_boot_mean(evs, None, B=3000, seed=7 * blo + 11)
        rows[f"{blo}-{bhi}bps"] = {
            "n": nn, "rev_rate": round(q, 4),
            "ev_c_at_51": round(ev_cents(q), 2),
            "ev_boot_ci": [round(lo95, 2), round(hi95, 2)],
            "p_ev_le_0": round(ple, 4),
            "binom_p_vs_50": round(wilson_or_binom_p(sum(v for _, v in wins), nn), 4)}
    cond[lbl] = rows
    print(lbl, json.dumps(rows, indent=1))
out["conditional_reversal_by_prior_move"] = cond

# same but split by direction of prior move (tie asymmetry check), >=12bps only
dircheck = {}
for lbl, lo_t, hi_t in [("TRAIN", 0, TEST_START), ("TEST", TEST_START, 1 << 62)]:
    for d, name in [(1, "fade_up_move"), (-1, "fade_down_move")]:
        wins = []
        for i in range(1, n):
            if not (lo_t <= t0s[i] < hi_t):
                continue
            if abs(r[i - 1]) < 0.0012 or r[i - 1] == 0:
                continue
            if (r[i - 1] > 0) != (d == 1):
                continue
            rev = (up[i] != (r[i - 1] > 0))
            wins.append(1.0 if rev else 0.0)
        q = sum(wins) / len(wins) if wins else None
        dircheck[f"{lbl}_{name}"] = {"n": len(wins), "rev_rate": round(q, 4) if q is not None else None,
                                     "ev_c_at_51": round(ev_cents(q), 2) if q is not None else None}
out["ge12bps_by_direction"] = dircheck
print(json.dumps(dircheck, indent=1))

json.dump(out, open("/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work/regime/a1_results.json", "w"), indent=1)
print("saved a1_results.json")
