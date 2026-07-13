#!/usr/bin/env python3
"""R7 adversarial reproduction — written from scratch from the claim's plain-English statement.

Claim components verified here:
  A. LIVE increment: within reversal_v2 (ungated $50 control) fills Jul 10-13,
     gate-passed ran -7.79c/sh (n=34) vs -5.21c gate-rejected (n=7); increment -2.57c, perm p~0.79.
  B. CANDLE side (TEST Jun 26 - Jul 13, buffered open-to-open, fill p=0.51):
     gated LEVEL +4.55c (p=0.0035); increment gated-vs-rejected +4.69c (p~0.06), never significant.
  C. RETENTION: gate passes 0.766 (live window) / 0.726 (last 21d) vs pre-registered band [0.40, 0.70].
     Merge-agent flaw to address: candle-recomputed retention might mismatch the bot's
     feed-based convention -> verify against the bot's OWN logged gate decisions.

Conventions (from bot source, re-implemented independently):
  interval return r(t) = (open(t+300) - open(t)) / open(t)   [buffered open-to-open]
  trigger at t0: |r(t0-300)| >= 0.0012, fade side = opposite sign
  eff6  = |prod(1+r_i) - 1| / sum|r_i| over the 6 returns ending at the trigger (trigger INCLUDED)
  cnt12 = #{|r| >= 0.0012} over the 12 returns BEFORE the trigger (trigger EXCLUDED)
  gate pass iff eff6 >= 0.10 and cnt12 <= 6
  outcome at t0: fade wins iff sign(r(t0)) == fade side; r == 0 counted as loss (tie note reported)
  EV/share at flat fill p: win - (p + 0.07*p*(1-p));  p = 0.51 -> cost 0.527493
"""
import json, math, random, datetime

random.seed(20260712)
D = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data"
OUT = {}

def utc(t): return datetime.datetime.utcfromtimestamp(t).strftime("%m-%d %H:%M")

# ---------- candle machinery ----------
cb = json.load(open(f"{D}/cb5m.json"))
T, O = cb["t"], cb["o"]
idx = {t: i for i, t in enumerate(T)}
def ret(t):  # buffered open-to-open return of interval starting at t
    i = idx.get(t)
    if i is None or i + 1 >= len(T) or T[i+1] != t + 300: return None
    return (O[i+1] - O[i]) / O[i]

def gate(t0, eff6_min=0.10, cnt12_max=6):
    """Recompute the bot's isolated-impulse gate from candles for a signal at t0.
    Returns (ok, eff6, cnt12) or (None,None,None) if history incomplete."""
    rs = {}
    for k in range(1, 14):
        r = ret(t0 - 300 * k)
        if r is None: return None, None, None
        rs[k] = r
    last6 = [rs[k] for k in range(6, 0, -1)]
    den = sum(abs(r) for r in last6)
    net = 1.0
    for r in last6: net *= (1.0 + r)
    eff6 = (abs(net - 1.0) / den) if den > 0 else 1.0
    cnt12 = sum(1 for k in range(2, 14) if abs(rs[k]) >= 0.0012)
    return (eff6 >= eff6_min and cnt12 <= cnt12_max), eff6, cnt12

def signals(t_lo, t_hi, thr=0.0012, eff6_min=0.10, cnt12_max=6):
    """All candle triggers in [t_lo, t_hi) with outcome + gate label."""
    out = []
    for t0 in range(((t_lo + 299) // 300) * 300, t_hi, 300):
        rp = ret(t0 - 300)
        if rp is None or abs(rp) < thr: continue
        ro = ret(t0)
        if ro is None: continue
        side = "down" if rp > 0 else "up"
        win = 1 if ((side == "down" and ro < 0) or (side == "up" and ro > 0)) else 0
        ok, e6, c12 = gate(t0, eff6_min, cnt12_max)
        if ok is None: continue
        out.append(dict(t0=t0, side=side, win=win, tie=(ro == 0), gate=ok, eff6=e6, cnt12=c12))
    return out

def mean(x): return sum(x) / len(x) if x else float("nan")

def block_boot(rows, stat, n=10000):
    """1h-block bootstrap. rows: list of dicts with t0. stat(rows)->float. Returns (est, ci90, p_le_0)."""
    blocks = {}
    for r in rows: blocks.setdefault(r["t0"] // 3600, []).append(r)
    keys = list(blocks)
    est = stat(rows)
    vals = []
    for _ in range(n):
        samp = []
        for _ in range(len(keys)): samp.extend(blocks[random.choice(keys)])
        vals.append(stat(samp))
    vals.sort()
    lo, hi = vals[int(0.05 * n)], vals[int(0.95 * n) - 1]
    p = sum(1 for v in vals if v <= 0) / n
    return est, (lo, hi), p

COST51 = 0.51 + 0.07 * 0.51 * 0.49  # 0.527493
def ev_stat(rows, cost=COST51):
    return (mean([r["win"] for r in rows]) - cost) * 100

def inc_stat(rows, cost=COST51):
    g = [r for r in rows if r["gate"]]; b = [r for r in rows if not r["gate"]]
    if not g or not b: return float("nan")
    return (mean([r["win"] for r in g]) - mean([r["win"] for r in b])) * 100

# ================= A. LIVE INCREMENT (reversal_v2 fills) =================
trades = json.load(open(f"{D}/trades_unified.json"))
st = json.load(open(f"{D}/state_extract.json"))
W0, W1 = 1783702500, 1783912200  # 07-10 16:55 -> 07-13 03:10 UTC (claimed window)
rv = [t for t in trades if t.get("eng") == "reversal_v2" and t.get("result") in ("win", "loss")
      and W0 <= t["t0"] <= W1]
imp_t0 = {t["t0"] for t in trades if t.get("eng") in ("impulse_v2", "impulse50")}
meas_t0 = {m["t0"] for m in st["measure"]}
bot_pass_t0 = imp_t0 | meas_t0   # every t0 where the BOT's own gate demonstrably passed

live = []
for t in rv:
    ps = t["pnl"] / t["shares"] * 100.0
    ok, e6, c12 = gate(t["t0"])
    live.append(dict(t0=t["t0"], ps=ps, entry=t["entry"], win=1 if t["result"] == "win" else 0,
                     bot_pass=(t["t0"] in bot_pass_t0), cand_pass=ok, eff6=e6, cnt12=c12))

def perm_test(a, b, n=20000):
    obs = mean(a) - mean(b)
    pool = a + b; na = len(a); cnt = 0
    for _ in range(n):
        random.shuffle(pool)
        if abs(mean(pool[:na]) - mean(pool[na:])) >= abs(obs) - 1e-12: cnt += 1
    return obs, cnt / n

def live_split(rows, key):
    g = [r["ps"] for r in rows if r[key]]; b = [r["ps"] for r in rows if not r[key]]
    if not g or not b: return None
    obs, p = perm_test(g[:], b[:])
    return dict(n_pass=len(g), n_rej=len(b), ps_pass_c=round(mean(g), 2), ps_rej_c=round(mean(b), 2),
                increment_c=round(obs, 2), perm_p_two_sided=round(p, 4))

OUT["A_live_increment"] = {
    "n_reversal_v2_fills": len(rv),
    "by_bot_logged_gate": live_split(live, "bot_pass"),
    "by_candle_recomputed_gate": live_split(live, "cand_pass"),
    "label_agreement": {
        "n": len(live),
        "agree": sum(1 for r in live if r["bot_pass"] == bool(r["cand_pass"])),
        "disagree_rows": [dict(t0=r["t0"], utc=utc(r["t0"]), bot=r["bot_pass"], cand=r["cand_pass"],
                               eff6=round(r["eff6"], 4) if r["eff6"] is not None else None, cnt12=r["cnt12"])
                          for r in live if r["bot_pass"] != bool(r["cand_pass"])],
    },
}

# stress: drop each UTC day; halves
days = sorted({datetime.datetime.utcfromtimestamp(r["t0"]).strftime("%m-%d") for r in live})
drop = {}
for d in days:
    sub = [r for r in live if datetime.datetime.utcfromtimestamp(r["t0"]).strftime("%m-%d") != d]
    s = live_split(sub, "bot_pass")
    drop[d] = None if s is None else s["increment_c"]
h = len(live) // 2
liv_sorted = sorted(live, key=lambda r: r["t0"])
OUT["A_stress"] = {
    "drop_day_increment_c": drop,
    "first_half": live_split(liv_sorted[:h], "bot_pass"),
    "second_half": live_split(liv_sorted[h:], "bot_pass"),
}

# ================= B. CANDLE-SIDE TEST =================
TEST0 = int(datetime.datetime(2026, 6, 26, tzinfo=datetime.timezone.utc).timestamp())
TEST1 = T[-1] + 300
TRAIN0, TRAIN1 = T[0], TEST0
sig_test = signals(TEST0, TEST1)
sig_train = signals(TRAIN0, TRAIN1)

def summarize(sig, cost=COST51):
    g = [s for s in sig if s["gate"]]; b = [s for s in sig if not s["gate"]]
    lev, ci, p = block_boot(g, lambda r: ev_stat(r, cost))
    inc, ici, ip = block_boot(sig, lambda r: inc_stat(r, cost))
    return dict(n_signals=len(sig), n_gated=len(g), n_rejected=len(b),
                retention=round(len(g) / len(sig), 4), ties=sum(1 for s in sig if s["tie"]),
                q_gated=round(mean([s["win"] for s in g]), 4),
                q_rejected=round(mean([s["win"] for s in b]), 4) if b else None,
                gated_level_ev_c=round(lev, 3), level_ci90=[round(ci[0], 2), round(ci[1], 2)],
                level_p_le_0=round(p, 4),
                increment_c=round(inc, 3), inc_ci90=[round(ici[0], 2), round(ici[1], 2)],
                inc_p_le_0=round(ip, 4))

OUT["B_candle_TEST"] = summarize(sig_test)
OUT["B_candle_TRAIN_ref"] = summarize(sig_train)

# stress on TEST: drop best day (by gated-EV contribution), halves, jitters
gday = {}
for s in sig_test:
    if s["gate"]:
        d = datetime.datetime.utcfromtimestamp(s["t0"]).strftime("%m-%d")
        gday.setdefault(d, []).append(s["win"] - COST51)
best_day = max(gday, key=lambda d: sum(gday[d]))
sub = [s for s in sig_test if datetime.datetime.utcfromtimestamp(s["t0"]).strftime("%m-%d") != best_day]
OUT["B_stress"] = {"best_day": best_day, "drop_best_day": summarize(sub)}
hh = len(sig_test) // 2
OUT["B_stress"]["first_half"] = summarize(sig_test[:hh])
OUT["B_stress"]["second_half"] = summarize(sig_test[hh:])
OUT["B_stress"]["fill_p_50c"] = dict(gated_level_ev_c=round(ev_stat([s for s in sig_test if s["gate"]], 0.50 + 0.07 * 0.50 * 0.50), 3))
OUT["B_stress"]["fill_p_52c"] = dict(gated_level_ev_c=round(ev_stat([s for s in sig_test if s["gate"]], 0.52 + 0.07 * 0.52 * 0.48), 3))
for name, kw in [("thr_11bps", dict(thr=0.0011)), ("thr_13bps", dict(thr=0.0013)),
                 ("eff6_009", dict(eff6_min=0.09)), ("eff6_011", dict(eff6_min=0.11)),
                 ("cnt12_5", dict(cnt12_max=5)), ("cnt12_7", dict(cnt12_max=7))]:
    sj = signals(TEST0, TEST1, **kw)
    gj = [s for s in sj if s["gate"]]
    OUT["B_stress"][name] = dict(n_gated=len(gj), retention=round(len(gj) / len(sj), 4),
                                 gated_level_ev_c=round(ev_stat(gj), 3),
                                 increment_c=round(inc_stat(sj), 3))

# ================= C. RETENTION + CONVENTION CHECK =================
def retention(t_lo, t_hi, **kw):
    s = signals(t_lo, t_hi, **kw)
    g = sum(1 for x in s if x["gate"])
    return dict(signals=len(s), gated=g, retention=round(g / len(s), 4) if s else None)

hb = int(datetime.datetime(2026, 7, 13, 3, 40, tzinfo=datetime.timezone.utc).timestamp())
d21 = int(datetime.datetime(2026, 6, 22, tzinfo=datetime.timezone.utc).timestamp())
OUT["C_retention"] = {
    "live_window_jul10_13": retention(W0, W1 + 300),
    "last_21d": retention(d21, hb),
    "TRAIN_may11_jun25": retention(TRAIN0, TRAIN1),
    "TEST_jun26_jul13": retention(TEST0, TEST1),
    "preregistered_band": [0.40, 0.70],
}
# threshold jitter on retention (does it re-enter the band?)
OUT["C_retention_jitter"] = {
    name: retention(d21, hb, **kw)
    for name, kw in [("eff6_009", dict(eff6_min=0.09)), ("eff6_011", dict(eff6_min=0.11)),
                     ("cnt12_5", dict(cnt12_max=5)), ("cnt12_7", dict(cnt12_max=7)),
                     ("thr_11bps", dict(thr=0.0011)), ("thr_13bps", dict(thr=0.0013))]
}

# --- convention check 1: bot feed returns (ivlHist2) vs candle open-to-open ---
conv1 = []
flips = 0
for t0, r_bot in st["ivlHist2"]:
    r_c = ret(t0)
    if r_c is None: continue
    fl = (abs(r_bot) >= 0.0012) != (abs(r_c) >= 0.0012)
    flips += fl
    conv1.append(dict(t0=t0, r_bot=round(r_bot * 1e4, 2), r_cand=round(r_c * 1e4, 2),
                      diff_bps=round((r_bot - r_c) * 1e4, 2), flip12=fl))
OUT["C_convention_ivlHist2"] = {
    "n": len(conv1), "n_12bps_classification_flips": flips,
    "max_abs_diff_bps": round(max(abs(c["diff_bps"]) for c in conv1), 2),
    "mean_abs_diff_bps": round(mean([abs(c["diff_bps"]) for c in conv1]), 2),
}

# --- convention check 2: bot-logged eff6/cnt12 (measure book) vs candle recompute ---
conv2 = []
for m in st["measure"]:
    if "f" not in m: continue
    ok, e6, c12 = gate(m["t0"])
    if ok is None: continue
    conv2.append(dict(t0=m["t0"], utc=utc(m["t0"]),
                      eff6_bot=m["f"]["eff6"], eff6_cand=round(e6, 4),
                      cnt12_bot=m["f"]["cnt12"], cnt12_cand=c12,
                      bot_gate=True,  # measure book only records gate-passed signals
                      cand_gate=bool(ok)))
OUT["C_convention_measure"] = {
    "n": len(conv2),
    "gate_decision_agree": sum(1 for c in conv2 if c["cand_gate"]),
    "gate_decision_disagree_rows": [c for c in conv2 if not c["cand_gate"]],
    "eff6_max_abs_diff": round(max(abs(c["eff6_bot"] - c["eff6_cand"]) for c in conv2), 4),
    "eff6_mean_abs_diff": round(mean([abs(c["eff6_bot"] - c["eff6_cand"]) for c in conv2]), 4),
    "cnt12_exact_match": sum(1 for c in conv2 if c["cnt12_bot"] == c["cnt12_cand"]),
    "cnt12_max_abs_diff": max(abs(c["cnt12_bot"] - c["cnt12_cand"]) for c in conv2),
}

# --- convention check 3: marginality — how much could feed/candle noise move retention? ---
s21 = signals(d21, hb)
noise = OUT["C_convention_ivlHist2"]["max_abs_diff_bps"] / 1e4  # worst observed feed-candle gap
marg = [s for s in s21 if s["gate"] and (s["eff6"] < 0.10 + 0.03 or s["cnt12"] == 6)]
worst_ret = (sum(1 for s in s21 if s["gate"]) - len(marg)) / len(s21)
OUT["C_marginality"] = {
    "gated_marginal_eff6_lt_013_or_cnt12_eq6": len(marg),
    "retention_if_ALL_marginal_passes_flipped": round(worst_ret, 4),
    "note": "extreme upper bound on convention sensitivity; observed feed-candle diffs (max "
            f"{OUT['C_convention_ivlHist2']['max_abs_diff_bps']}bps) flip far fewer",
}

json.dump(OUT, open("/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work/verify/R7-repro/results.json", "w"), indent=1)
print(json.dumps(OUT, indent=1))
