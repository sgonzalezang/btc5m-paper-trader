"""A2: Vol regime.
Trailing 1h realized vol (sum |r| over prior 12 intervals, known at t0) terciles,
cutoffs fit on TRAIN only. Tests:
 (a) resolution series: unconditional lag-1 reversal rate by vol tercile
 (b) contrarian trigger (|prior move|>=12bps) fade performance by vol tercile
 (c) pooled trade ledger: reversal-family + v3 engines by vol tercile
Stdlib only."""
import json, sys
sys.path.insert(0, "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work/regime")
from lib import *

t, o = load_cb5m()
t0s, r, up = build_series(t, o)
n = len(t0s)
t0_to_i = {t0: i for i, t0 in enumerate(t0s)}

# trailing vol: sum of |r[j]| j=i-12..i-1 (needs 12 prior intervals)
vol = [None] * n
run = 0.0
for i in range(n):
    if i >= 12:
        vol[i] = sum(abs(r[j]) for j in range(i - 12, i))

train_vols = sorted(v for i, v in enumerate(vol) if v is not None and t0s[i] < TEST_START)
c1 = train_vols[len(train_vols) // 3]
c2 = train_vols[2 * len(train_vols) // 3]
print(f"TRAIN tercile cutoffs (sum|r| over 1h): {c1*1e4:.1f}bps, {c2*1e4:.1f}bps")

def terc(v):
    if v is None: return None
    return 0 if v < c1 else (1 if v < c2 else 2)

out = {"cutoffs_bps": [round(c1 * 1e4, 2), round(c2 * 1e4, 2)]}

# (a) unconditional lag-1 reversal by tercile; (b) triggered fade by tercile
for lbl, lo_t, hi_t in [("TRAIN", 0, TEST_START), ("TEST", TEST_START, 1 << 62)]:
    sec = {}
    for tc in (0, 1, 2):
        # unconditional reversal of previous interval outcome
        unc = []
        trig = []
        for i in range(1, n):
            if not (lo_t <= t0s[i] < hi_t) or terc(vol[i]) != tc:
                continue
            if r[i - 1] == 0:
                continue
            prior_up = r[i - 1] > 0
            rev = 1.0 if up[i] != prior_up else 0.0
            unc.append((hour_block(t0s[i]), rev))
            if abs(r[i - 1]) >= 0.0012:
                trig.append((hour_block(t0s[i]), rev))
        row = {}
        for name, series in [("uncond", unc), ("trig12", trig)]:
            if not series:
                continue
            nn = len(series)
            q = sum(v for _, v in series) / nn
            evs = [(b, ev_cents(v)) for b, v in series]
            obs, lo95, hi95, ple = block_boot_mean(evs, None, B=3000, seed=41 + tc)
            row[name] = {"n": nn, "rev_rate": round(q, 4), "ev_c": round(ev_cents(q), 2),
                         "ev_ci": [round(lo95, 2), round(hi95, 2)], "p_ev_le_0": round(ple, 4)}
        sec[f"tercile_{tc}"] = row
    # gate-effect style contrast: hi-vol tercile vs rest, triggered fades
    a = [(hour_block(t0s[i]), ev_cents(1.0 if up[i] != (r[i-1] > 0) else 0.0))
         for i in range(1, n) if lo_t <= t0s[i] < hi_t and terc(vol[i]) == 2
         and r[i-1] != 0 and abs(r[i-1]) >= 0.0012]
    b = [(hour_block(t0s[i]), ev_cents(1.0 if up[i] != (r[i-1] > 0) else 0.0))
         for i in range(1, n) if lo_t <= t0s[i] < hi_t and terc(vol[i]) in (0, 1)
         and r[i-1] != 0 and abs(r[i-1]) >= 0.0012]
    d, lo95, hi95, ple = block_boot_diff(a, b, B=3000, seed=17)
    sec["hi_vs_lomid_trig_ev_diff_c"] = {"diff": round(d, 2), "ci": [round(lo95, 2), round(hi95, 2)],
                                         "p_le_0": round(ple, 4), "n_hi": len(a), "n_lomid": len(b)}
    out[lbl] = sec
    print(lbl, json.dumps(sec, indent=1))

# (c) ledger join: per-trade vol tercile
trades = json.load(open(f"{DATA}/trades_unified.json"))
fam_rev = {"reversal", "reversal2", "reversal_v2", "latentfire", "impulse_v2", "impulse50"}
led = {}
for group, engs in [("reversal_family_all", fam_rev),
                    ("v3_era", {"impulse_v2", "impulse50", "reversal_v2"}),
                    ("momentum_family", {"loose", "floor", "band", "value"})]:
    rows = {}
    for tc in (0, 1, 2, None):
        sel = []
        for x in trades:
            if x["eng"] not in engs or x.get("result") not in ("win", "loss"):
                continue
            i = t0_to_i.get(x["t0"])
            v = terc(vol[i]) if i is not None else None
            if v != tc:
                continue
            sh = x.get("shares") or 0
            if sh <= 0:
                continue
            sel.append((x.get("result") == "win", (x.get("pnl") or 0) / sh))
        if not sel:
            continue
        nn = len(sel)
        wr = sum(1 for w, _ in sel if w) / nn
        pps = sum(p for _, p in sel) / nn * 100
        rows["tercile_" + (str(tc) if tc is not None else "NA")] = {
            "n": nn, "wr": round(wr, 4), "net_pnl_c_per_share": round(pps, 2)}
    led[group] = rows
out["ledger_by_vol_tercile"] = led
print(json.dumps(led, indent=1))

json.dump(out, open("/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work/regime/a2_results.json", "w"), indent=1)
print("saved a2_results.json")
