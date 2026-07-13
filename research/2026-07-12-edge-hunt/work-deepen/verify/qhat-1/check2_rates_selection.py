#!/usr/bin/env python3
"""Check 2: (a) live-window gated-signal cadence vs the 14.2/day 'structural'
claim; (b) selection-corrected significance + per-share vs level decomposition
for the winner and the hybrid. stdlib only."""
import json, math, random, datetime

DS = json.load(open("/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/"
                    "work-deepen/dataset/signals_60d.json"))
ST = json.load(open("/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/"
                    "data/state_extract.json"))
TEST_T0 = 1782432000
out = {}

gated = sorted(r["t0"] for r in DS["rows"] if r["trigger"] and r["gatePass"])
ms = ST["measure"]
mb0, mb1 = ms[0]["t0"], ms[-1]["t0"]

# (a) gated candle-signal rate inside the exact live measure-book span
in_span = [t for t in gated if mb0 <= t <= mb1]
span_d = (mb1 - mb0) / 86400.0
# rolling 7d max within TEST era only
te = [t for t in gated if t >= TEST_T0]
best7 = 0; j = 0
for i in range(len(te)):
    while te[i] - te[j] > 7 * 86400: j += 1
    best7 = max(best7, i - j + 1)
out["cadence"] = dict(
    live_span_days=round(span_d, 2),
    gated_candle_signals_in_span=len(in_span),
    gated_per_day_in_span=round(len(in_span) / span_d, 2),
    measure_records=len(ms),
    record_capture_ratio=round(len(ms) / len(in_span), 3),
    fill_model_availability=0.55,
    expected_records_per_day_at_55pct=round(0.55 * len(in_span) / span_d, 1),
    test_era_max_rolling7d_gated=best7,
    test_era_max_7d_per_day=round(best7 / 7.0, 1),
    implied_records_per_day_if_capture_holds=round(
        (len(ms) / len(in_span)) * best7 / 7.0, 1),
    threshold_7d_tier=17.1)

# (b) selection-corrected significance: paired hourly-block deltas vs a_current
# for every family in the K=22 sweep; Bonferroni + sign-flip permutation.
FEE, GAS, MINORD = 0.07, 0.004, 1.0
ANCHORS = [(0.45, 0.25 * 0.55), (0.49, 0.50 * 0.55), (0.51, 0.25 * 0.55)]
COST = {p: p + FEE * p * (1 - p) for p, _ in ANCHORS}
TIE_UP = 0.432
signals = []
for r in DS["rows"]:
    if not (r["trigger"] and r["gatePass"]): continue
    if r["side"] == "up":
        pw = 1.0 if r["label"] == "up" else (TIE_UP if r["label"] == "tie" else 0.0)
    else:
        pw = 1.0 if r["label"] == "down" else ((1 - TIE_UP) if r["label"] == "tie" else 0.0)
    signals.append(dict(t0=r["t0"], split=r["split"], pwin=pw))
signals.sort(key=lambda s: s["t0"])
T0, T1 = signals[0]["t0"], signals[-1]["t0"]
TICKS = []
t = ((T0 // 86400) + 1) * 86400 + 600
while t <= T1 + 86400: TICKS.append(t); t += 86400

def run_rows(bucket, M, seed, cap=0.56, window=30, decay_hl=None, shrink=None):
    book = []; qlo, qhi = min(cap, seed[0]), min(cap, seed[1])
    bank, bank_reset = 1000.0, False; tick_i = 0
    rows = {}; shares = 0.0; pnl = 0.0
    def upd():
        nonlocal qlo, qhi
        tick = TICKS[tick_i]
        lo_w = lo_s = hi_w = hi_s = all_w = all_s = 0.0
        for (t0, lo, pw, w, c) in book:
            if t0 + 360 > tick: continue
            age = (tick - t0) / 86400.0
            if age > window: continue
            wd = w * (0.5 ** (age / decay_hl) if decay_hl else 1.0)
            all_w += wd; all_s += wd * pw
            if lo: lo_w += wd; lo_s += wd * pw
            else:  hi_w += wd; hi_s += wd * pw
        if shrink == "pooled":
            qbar = (all_s + 50 * 0.5063) / (all_w + 50) if all_w else 0.5063
            slo, shi = qbar, qbar
        else:
            slo, shi = seed
        qlo = min(cap, round((lo_s + M * slo) / (lo_w + M), 4))
        qhi = min(cap, round((hi_s + M * shi) / (hi_w + M), 4))
    for s in signals:
        while tick_i < len(TICKS) - 1 and TICKS[tick_i + 1] <= s["t0"]:
            tick_i += 1; upd()
        if not bank_reset and s["t0"] >= TEST_T0: bank, bank_reset = 1000.0, True
        for p, w in ANCHORS:
            c = COST[p]
            lo = (c < 0.50) if bucket == "cost" else (p < 0.50)
            book.append((s["t0"], lo, s["pwin"], w, c))
            if bank < 250: continue
            q = qlo if lo else qhi
            f = q - (1 - q) * c / (1 - c)
            if f <= 0: continue
            stake = min(0.25 * f * bank, 0.05 * bank)
            if stake < MINORD: continue
            sh = stake / p
            epnl = sh * (s["pwin"] * (1 - c) - (1 - s["pwin"]) * c) - GAS
            bank += w * epnl
            if s["split"] == "test":
                rows[s["t0"]] = rows.get(s["t0"], 0.0) + w * epnl
                pnl += w * epnl; shares += w * sh
    return rows, pnl, shares

FAMS = {
    "a_current": ("cost", 400, (0.5057, 0.5068), 0.56, 30, None, None),
    "b_spec": ("peff", 200, (0.5, 0.5), 0.56, 30, None, None),
    "hybrid_cost_M200": ("cost", 200, (0.5, 0.5), 0.56, 30, None, None),
    "c_M50_informed": ("peff", 50, (0.54, 0.54), 0.56, 30, None, None),
    "c_M400_informed": ("peff", 400, (0.54, 0.54), 0.56, 30, None, None),
    "c_M200_neutral": ("peff", 200, (0.506, 0.506), 0.56, 30, None, None),
}
rows = {}; lvl = {}
for nm, a in FAMS.items():
    r, pnl, sh = run_rows(*a)
    rows[nm] = r
    lvl[nm] = dict(test_pnl=round(pnl, 2), cps=round(100 * pnl / sh, 3))

def blocks(nmB):
    hrs = {}
    for t0, v in rows["a_current"].items(): hrs.setdefault(t0 // 3600, [0.0, 0.0])[0] += v
    for t0, v in rows[nmB].items(): hrs.setdefault(t0 // 3600, [0.0, 0.0])[1] += v
    return [b - a for a, b in hrs.values()]

def perm_p(bl, nperm=20000, seed=17):
    rng = random.Random(seed)
    obs = sum(bl)
    cnt = 0
    for _ in range(nperm):
        s = sum(x if rng.random() < 0.5 else -x for x in bl)
        if s >= obs: cnt += 1
    return obs, cnt / nperm

sel = {}
for nm in ("c_M50_informed", "c_M400_informed", "hybrid_cost_M200", "b_spec", "c_M200_neutral"):
    bl = blocks(nm)
    obs, p = perm_p(bl)
    sel[nm] = dict(delta_test=round(obs, 2), signflip_perm_p=p,
                   bonf22=round(min(1.0, p * 22), 4), bonf90=round(min(1.0, p * 90), 4),
                   cps=lvl[nm]["cps"], cps_current=lvl["a_current"]["cps"],
                   beats_current_per_share=bool(lvl[nm]["cps"] > lvl["a_current"]["cps"]))
out["selection_corrected"] = sel
out["levels"] = lvl

print(json.dumps(out, indent=1))
json.dump(out, open("/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/"
                    "work-deepen/verify/qhat-1/check2_results.json", "w"), indent=1)
