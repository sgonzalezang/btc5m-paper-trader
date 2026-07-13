"""A5: Weekend effect on the resolution series and the ledger.
Weekend = Saturday/Sunday UTC. 9 weekends in cb5m span. Tests:
 (a) activity: trigger frequency + median |move| weekend vs weekday
 (b) triggered fade EV weekend vs weekday, TRAIN and TEST
 (c) unconditional lag-1 reversal weekend vs weekday
 (d) ledger: live weekend (Jul 11-12) vs live weekdays for v3 engines. Stdlib only."""
import json, sys, datetime
sys.path.insert(0, "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work/regime")
from lib import *

t, o = load_cb5m()
t0s, r, up = build_series(t, o)
n = len(t0s)

def is_weekend(t0):
    return datetime.datetime.utcfromtimestamp(t0).weekday() >= 5

out = {}
for lbl, lo_t, hi_t in [("TRAIN", 0, TEST_START), ("TEST", TEST_START, 1 << 62)]:
    sec = {}
    for we in (True, False):
        moves = []
        fades = []
        unc = []
        n_ivl = 0
        for i in range(13, n):
            if not (lo_t <= t0s[i] < hi_t) or is_weekend(t0s[i]) != we:
                continue
            n_ivl += 1
            moves.append(abs(r[i]) * 1e4)
            if r[i - 1] != 0:
                rev = 1.0 if up[i] != (r[i - 1] > 0) else 0.0
                unc.append((hour_block(t0s[i]), ev_cents(rev)))
                if abs(r[i - 1]) >= 0.0012:
                    fades.append((hour_block(t0s[i]), ev_cents(rev)))
        moves.sort()
        med = moves[len(moves) // 2] if moves else None
        row = {"n_intervals": n_ivl,
               "median_abs_move_bps": round(med, 2),
               "trigger_rate": round(len(fades) / n_ivl, 4) if n_ivl else None,
               "n_triggers": len(fades)}
        if fades:
            q = (sum(v for _, v in fades) / len(fades))
            obs, lo95, hi95, ple = block_boot_mean(fades, None, B=3000, seed=5 + we)
            row["fade_ev_c"] = round(q, 2)
            row["fade_ev_ci"] = [round(lo95, 2), round(hi95, 2)]
            row["fade_p_ev_le_0"] = round(ple, 4)
        if unc:
            row["uncond_rev_ev_c"] = round(sum(v for _, v in unc) / len(unc), 2)
        sec["weekend" if we else "weekday"] = row
    # weekend-vs-weekday fade contrast
    a = [(hour_block(t0s[i]), ev_cents(1.0 if up[i] != (r[i-1] > 0) else 0.0))
         for i in range(13, n) if lo_t <= t0s[i] < hi_t and is_weekend(t0s[i])
         and r[i-1] != 0 and abs(r[i-1]) >= 0.0012]
    b = [(hour_block(t0s[i]), ev_cents(1.0 if up[i] != (r[i-1] > 0) else 0.0))
         for i in range(13, n) if lo_t <= t0s[i] < hi_t and not is_weekend(t0s[i])
         and r[i-1] != 0 and abs(r[i-1]) >= 0.0012]
    if a and b:
        d, dl, dh, dp = block_boot_diff(a, b, B=3000, seed=77)
        sec["weekend_minus_weekday_fade_diff_c"] = {"diff": round(d, 2), "ci": [round(dl, 2), round(dh, 2)],
                                                    "p_le_0": round(dp, 4)}
    out[lbl] = sec
    print(lbl, json.dumps(sec, indent=1))

# ledger: v3-era engines weekend vs weekday
trades = json.load(open(f"{DATA}/trades_unified.json"))
led = {}
for group, engs in [("v3_era", {"impulse_v2", "impulse50", "reversal_v2"}),
                    ("reversal_family_all", {"reversal", "reversal2", "reversal_v2", "latentfire", "impulse_v2", "impulse50"})]:
    rows = {}
    for we in (True, False):
        sel = []
        for x in trades:
            if x["eng"] not in engs or x.get("result") not in ("win", "loss"):
                continue
            if is_weekend(x["t0"]) != we:
                continue
            sh = x.get("shares") or 0
            if sh <= 0:
                continue
            sel.append(((x.get("result") == "win"), (x.get("pnl") or 0) / sh))
        if sel:
            nn = len(sel)
            rows["weekend" if we else "weekday"] = {
                "n": nn, "wr": round(sum(1 for w, _ in sel if w) / nn, 4),
                "net_pnl_c_per_share": round(sum(p for _, p in sel) / nn * 100, 2)}
    led[group] = rows
out["ledger"] = led
print(json.dumps(led, indent=1))

json.dump(out, open("/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work/regime/a5_results.json", "w"), indent=1)
print("saved a5_results.json")
