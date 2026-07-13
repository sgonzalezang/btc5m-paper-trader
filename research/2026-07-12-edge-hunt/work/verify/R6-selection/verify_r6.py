"""Adversarial verification of R6 (fresh-window drought / non-stationarity).

Tests:
 T1. Day-by-day decomposition of the fresh window (gate_refresh construction,
     Jul 10 15:05 start): is the drought Jul-10-concentrated? Recompute fresh EV
     excluding Jul 10 (merge-agent flaw).
 T2. Daily gated EV over the whole 63-day series: rank of Jul 10; verify the
     -13.97c / -0.90c numbers quoted by the merge agent.
 T3. Placebo sliding windows: distribution of gated EV over all windows of the
     same trade-count (n=52) across TRAIN+TEST; where does the fresh window's
     -2.75c sit? (honest selection/"how unusual is this?" correction)
 T4. Weekly non-stationarity: is the SD of weekly gated EV larger than expected
     from binomial + hour-block dependence alone? Hour-block permutation test.
 T5. Live-ledger corroboration independence: per-day per-share EV for
     impulse50 / reversal_v2 / impulse_v2 (Jul 10 vs 11 vs 12 vs 13); overlap of
     the "corroborating" books with each other and the candle series.
Stdlib only.
"""
import json, math, random, calendar, sys
from collections import defaultdict

sys.path.insert(0, "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work/alphasweep")
from common import Table, block_bootstrap, cost, SPLIT_TS

OUT = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work/verify/R6-selection/results.json"
P = 0.51
FRESH = calendar.timegm((2026, 7, 10, 15, 5, 0))
FRESH_A3 = calendar.timegm((2026, 7, 10, 11, 55, 0))

tab = Table()

def gate(i):
    if i < 14:
        return False
    o = tab.o
    legs = [o[i - 5 + k] - o[i - 6 + k] for k in range(6)]
    denom = sum(abs(x) for x in legs)
    eff6 = abs(o[i] - o[i - 6]) / denom if denom > 0 else 1.0
    cnt12 = sum(1 for k in range(i - 13, i - 1)
                if abs(tab.o[k + 1] - tab.o[k]) / tab.o[k] >= 0.0012)
    return eff6 >= 0.10 and cnt12 <= 6

gated, ungated = [], []
for i in range(14, tab.n - 1):
    r = tab.prior_ret(i, 1)
    if r is None or abs(r) < 0.0012 or tab.up[i] is None:
        continue
    side = "down" if r > 0 else "up"
    w = 1 if ((side == "up") == (tab.up[i] == 1)) else 0
    rec = (tab.t[i], w - cost(P), w)
    ungated.append(rec)
    if gate(i):
        gated.append(rec)

def day_of(t0):
    tm = [calendar.timegm((2026, 1, 1, 0, 0, 0))]
    import time
    st = time.gmtime(t0)
    return f"{st.tm_year:04d}-{st.tm_mon:02d}-{st.tm_mday:02d}"

def stats(trades, seed=1234):
    if not trades:
        return {"n": 0}
    pairs = [(t, ev) for t, ev, w in trades]
    wins = sum(w for _, _, w in trades)
    mean, p, lo, hi = block_bootstrap(pairs, reps=4000, seed=seed)
    return {"n": len(trades), "q": round(wins / len(trades), 4),
            "ev_c": round(mean * 100, 3), "p_boot_le0": round(p, 4),
            "ci90_c": [round(lo * 100, 3), round(hi * 100, 3)]}

res = {}

# ---------- T1: fresh window day-by-day + exclusions ----------
fresh = [x for x in gated if x[0] >= FRESH]
by_day = defaultdict(list)
for x in fresh:
    by_day[day_of(x[0])].append(x)
t1 = {"fresh_full": stats(fresh), "per_day": {}}
for d in sorted(by_day):
    tr = by_day[d]
    n = len(tr); w = sum(x[2] for x in tr)
    t1["per_day"][d] = {"n": n, "wins": w,
                        "ev_c": round(100 * sum(x[1] for x in tr) / n, 2)}
jul11_on = [x for x in fresh if day_of(x[0]) >= "2026-07-11"]
t1["fresh_excl_jul10"] = stats(jul11_on, seed=777)
# same for the a3 (11:55) variant of the window start
fresh_a3 = [x for x in gated if x[0] >= FRESH_A3]
t1["fresh_a3_start_full"] = stats(fresh_a3, seed=555)
res["T1_day_decomposition"] = t1

# ---------- T2: daily EV over whole series, rank Jul 10 ----------
by_day_all = defaultdict(list)
for x in gated:
    by_day_all[day_of(x[0])].append(x)
daily = []
for d in sorted(by_day_all):
    tr = by_day_all[d]
    n = len(tr)
    daily.append((d, n, 100 * sum(x[1] for x in tr) / n))
daily_full = [x for x in daily if x[1] >= 5]  # exclude tiny partial days
worst = sorted(daily_full, key=lambda x: x[2])[:5]
jul10 = [x for x in daily if x[0] == "2026-07-10"]
res["T2_daily_rank"] = {
    "n_days_ge5": len(daily_full),
    "jul10_full_day": {"day": jul10[0][0], "n": jul10[0][1], "ev_c": round(jul10[0][2], 2)} if jul10 else None,
    "jul10_post_1505_only": {"n": len(by_day.get("2026-07-10", [])),
                             "ev_c": round(100 * sum(x[1] for x in by_day["2026-07-10"]) / len(by_day["2026-07-10"]), 2) if by_day.get("2026-07-10") else None},
    "worst5_days": [{"day": d, "n": n, "ev_c": round(e, 2)} for d, n, e in worst],
    "jul10_rank_from_worst": 1 + sum(1 for _, _, e in daily_full if e < jul10[0][2]),
}

# ---------- T3: placebo sliding windows of same trade count ----------
n_f = len(fresh)
evs_all = [x[1] for x in gated]
ts_all = [x[0] for x in gated]
obs_mean = sum(x[1] for x in fresh) / n_f * 100
placebo = []
for s in range(0, len(gated) - n_f + 1):
    m = sum(evs_all[s:s + n_f]) / n_f * 100
    placebo.append((ts_all[s], m))
# exclude windows overlapping the fresh window itself
pre = [m for t0, m in placebo if t0 + 0 < FRESH and ts_all[min(len(ts_all)-1, placebo.index((t0,m)))] ]
pre = [m for (t0, m) in placebo if t0 < FRESH - 86400 * 3]  # windows fully before fresh (window spans ~2.5d)
frac_le = sum(1 for m in pre if m <= obs_mean) / len(pre)
pre_sorted = sorted(pre)
res["T3_placebo_windows"] = {
    "window_trade_count": n_f, "obs_fresh_ev_c": round(obs_mean, 2),
    "n_placebo_windows": len(pre),
    "frac_placebo_le_obs": round(frac_le, 4),
    "placebo_p5_c": round(pre_sorted[int(0.05 * len(pre))], 2),
    "placebo_p50_c": round(pre_sorted[len(pre) // 2], 2),
    "placebo_p95_c": round(pre_sorted[int(0.95 * len(pre))], 2),
    "note": "fraction of same-size historical windows with EV <= fresh window's; high fraction => drought unremarkable",
}
# also placebo restricted to TEST era
pre_test = [m for (t0, m) in placebo if SPLIT_TS <= t0 < FRESH - 86400 * 3]
if pre_test:
    frac_le_t = sum(1 for m in pre_test if m <= obs_mean) / len(pre_test)
    res["T3_placebo_windows"]["TEST_only"] = {
        "n": len(pre_test), "frac_le_obs": round(frac_le_t, 4),
        "p5_c": round(sorted(pre_test)[int(0.05 * len(pre_test))], 2)}

# ---------- T4: weekly heterogeneity via hour-block permutation ----------
# weeks anchored Monday (May 11 2026 is a Monday)
W0 = calendar.timegm((2026, 5, 11, 0, 0, 0))
def week_of(t0):
    return (t0 - W0) // (7 * 86400)
blocks = defaultdict(list)
for t0, ev, w in gated:
    blocks[t0 // 3600].append(ev)
bl_items = [(b, vs) for b, vs in sorted(blocks.items())]
# observed weekly means (weeks with n>=50 trades to match the quoted table's scale)
wk = defaultdict(list)
for t0, ev, w in gated:
    wk[week_of(t0)].append(ev)
weeks_obs = {k: (len(v), 100 * sum(v) / len(v)) for k, v in wk.items() if len(v) >= 50}
means = [m for _, m in weeks_obs.values()]
mu = sum(means) / len(means)
sd_obs = math.sqrt(sum((m - mu) ** 2 for m in means) / (len(means) - 1))
# weighted chi-square-ish stat
stat_obs = sd_obs
# permutation: shuffle hour blocks, reassign sequentially into groups with the
# same number of BLOCKS per week (preserves within-block dependence)
block_week = defaultdict(list)
for b, vs in bl_items:
    t0b = b * 3600
    block_week[week_of(t0b)].append((b, vs))
sizes = [(k, len(v)) for k, v in sorted(block_week.items()) if k in weeks_obs]
all_blocks_used = [bv for k, v in sorted(block_week.items()) if k in weeks_obs for bv in v]
rng = random.Random(2026)
perm_sds = []
for _ in range(2000):
    rng.shuffle(all_blocks_used)
    idx = 0
    pm = []
    ok = True
    for k, nb in sizes:
        chunk = all_blocks_used[idx:idx + nb]; idx += nb
        vals = [v for _, vs in chunk for v in vs]
        if len(vals) < 10:
            ok = False; break
        pm.append(100 * sum(vals) / len(vals))
    if not ok:
        continue
    m2 = sum(pm) / len(pm)
    perm_sds.append(math.sqrt(sum((x - m2) ** 2 for x in pm) / (len(pm) - 1)))
p_hetero = sum(1 for s in perm_sds if s >= sd_obs) / len(perm_sds)
res["T4_weekly_heterogeneity"] = {
    "weeks_used": len(means), "weekly_ev_c": {str(k): [v[0], round(v[1], 2)] for k, v in sorted(weeks_obs.items())},
    "sd_obs_c": round(sd_obs, 2),
    "perm_sd_mean_c": round(sum(perm_sds) / len(perm_sds), 2),
    "perm_sd_p95_c": round(sorted(perm_sds)[int(0.95 * len(perm_sds))], 2),
    "p_perm_sd_ge_obs": round(p_hetero, 4),
    "note": "null = stationary edge with hour-block dependence; low p => real week-to-week drift",
}

# ---------- T5: live ledger per-day ----------
trades = json.load(open("/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data/trades_unified.json"))
t5 = {}
for eng in ("impulse50", "reversal_v2", "impulse_v2"):
    rows = [t for t in trades if t["eng"] == eng and t.get("status") == "settled" and t.get("shares")]
    byd = defaultdict(list)
    for t_ in rows:
        d = day_of(t_["t0"])
        byd[d].append(100.0 * t_["pnl"] / t_["shares"])
    ent = {}
    for d in sorted(byd):
        v = byd[d]
        ent[d] = {"n": len(v), "ps_c": round(sum(v) / len(v), 2)}
    allv = [x for v in byd.values() for x in v]
    ex10 = [x for d, v in byd.items() if d != "2026-07-10" for x in v]
    ent["ALL"] = {"n": len(allv), "ps_c": round(sum(allv) / len(allv), 2)}
    ent["EXCL_JUL10"] = {"n": len(ex10), "ps_c": round(sum(ex10) / len(ex10), 2) if ex10 else None}
    t5[eng] = ent
res["T5_live_ledger_daily"] = t5

json.dump(res, open(OUT, "w"), indent=1)
print(json.dumps(res, indent=1))
