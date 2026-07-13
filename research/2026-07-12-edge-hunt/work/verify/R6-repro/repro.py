#!/usr/bin/env python3
"""R6 independent reproduction — fresh-window drought of the gated contrarian edge.

Implemented from the plain-English spec only (FINAL-DESIGN 3.2 pseudocode / engine
timeline), NOT from the original analysis scripts:

  Trigger (interval i, cb5m opens o[]): prior completed interval move
      |o[i]-o[i-1]|/o[i-1] >= 0.0012 (12bps), contiguous candles required.
  Side: fade the move (prior up -> bet down).
  Gate (impulse isolation, needs 14 contiguous opens ending at o[i]):
      eff6  = |o[i]-o[i-6]| / sum_{j=i-6..i-1} |o[j+1]-o[j]|   (trigger leg INCLUDED)
      cnt12 = #{k in [i-13 .. i-2] : |o[k+1]-o[k]|/o[k] >= 0.0012}  (12 legs BEFORE trigger)
      pass iff eff6 >= 0.10 and cnt12 <= 6
  Label: up_i = 1 if o[i+1] >= o[i] (ties -> Up).
  Frozen cost model: fill p = 0.51; EV/share = win - (p + 0.07*p*(1-p)) - gas(0.004$/100sh).
  Windows: TRAIN < Jun 26 00:00 UTC <= TEST; FRESH_A = Jul 10 15:05 -> end (gate_refresh
  convention), FRESH_B = Jul 10 11:55 -> end (a3 convention).

Stresses on the fresh-window claim: drop best day, drop worst day (merge-agent flag:
Jul 10), halve sample (each half), jitter trigger threshold +-1bp, gate params +-, fill
price +-1c. 1h-block bootstrap everywhere.
"""
import json, math, random, calendar, datetime

DATA = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data"
SPLIT = calendar.timegm((2026, 6, 26, 0, 0, 0))
FRESH_A = calendar.timegm((2026, 7, 10, 15, 5, 0))
FRESH_B = calendar.timegm((2026, 7, 10, 11, 55, 0))
GAS = 0.004 / 100.0

cb = json.load(open(f"{DATA}/cb5m.json"))
T, O = cb["t"], cb["o"]
N = len(T)
IVL = 300


def cost(p):
    return p + 0.07 * p * (1 - p) + GAS


def build_trades(thr=0.0012, gA=0.10, gB=6, pfill=0.51):
    """Return (gated, ungated) lists of dicts {t0, win, ev}."""
    gated, ungated = [], []
    for i in range(1, N - 1):  # need prior candle and label
        if T[i] - T[i - 1] != IVL:
            continue  # non-contiguous prior candle
        mv = (O[i] - O[i - 1]) / O[i - 1]
        if abs(mv) < thr:
            continue
        side_up = mv < 0  # fade
        win = 1 if (side_up == (O[i + 1] >= O[i])) else 0
        ev = win - cost(pfill)
        rec = {"t0": T[i], "win": win, "ev": ev}
        ungated.append(rec)
        # gate: need 14 contiguous opens ending at o[i] -> candles i-13..i
        if i - 13 < 0 or T[i] - T[i - 13] != 13 * IVL:
            continue
        denom = sum(abs(O[j + 1] - O[j]) for j in range(i - 6, i))
        eff6 = (abs(O[i] - O[i - 6]) / denom) if denom > 0 else 1.0
        cnt12 = sum(1 for k in range(i - 13, i - 1)
                    if abs(O[k + 1] - O[k]) / O[k] >= 0.0012)
        if eff6 >= gA and cnt12 <= gB:
            gated.append(rec)
    return gated, ungated


def blockboot(trades, reps=6000, seed=7):
    if not trades:
        return None
    blocks = {}
    for r in trades:
        blocks.setdefault(r["t0"] // 3600, []).append(r["ev"])
    keys = list(blocks.keys())
    nb = len(keys)
    mean = sum(r["ev"] for r in trades) / len(trades)
    rng = random.Random(seed)
    ms = []
    for _ in range(reps):
        tot = cnt = 0
        for _ in range(nb):
            b = blocks[keys[rng.randrange(nb)]]
            tot += sum(b)
            cnt += len(b)
        ms.append(tot / cnt if cnt else 0.0)
    ms.sort()
    return {
        "n": len(trades),
        "wr": round(sum(r["win"] for r in trades) / len(trades), 4),
        "ev_c": round(mean * 100, 3),
        "ci90_c": [round(ms[int(0.05 * len(ms))] * 100, 2),
                   round(ms[int(0.95 * len(ms)) - 1] * 100, 2)],
        "p_le0": round(sum(1 for m in ms if m <= 0) / len(ms), 4),
        "p_ge0": round(sum(1 for m in ms if m >= 0) / len(ms), 4),
    }


def win(trades, a, b=1 << 62):
    return [r for r in trades if a <= r["t0"] < b]


def day(ts):
    return datetime.datetime.utcfromtimestamp(ts).strftime("%m-%d")


def monday(ts):
    d = datetime.datetime.utcfromtimestamp(ts).date()
    m = d - datetime.timedelta(days=d.weekday())
    return m.strftime("%m-%d")


out = {"data_end_utc": datetime.datetime.utcfromtimestamp(T[-1]).isoformat(),
       "n_candles": N}

gated, ungated = build_trades()

# ---- headline reproduction ----
out["repro_gated_TEST"] = blockboot(win(gated, SPLIT))
out["repro_ungated_TEST"] = blockboot(win(ungated, SPLIT))
out["repro_gated_TRAIN"] = blockboot(win(gated, 0, SPLIT))
out["repro_gated_FRESH_A_jul10_1505"] = blockboot(win(gated, FRESH_A))
out["repro_ungated_FRESH_A"] = blockboot(win(ungated, FRESH_A))
out["repro_gated_FRESH_B_jul10_1155"] = blockboot(win(gated, FRESH_B))
out["repro_ungated_FRESH_B"] = blockboot(win(ungated, FRESH_B))

# ---- weekly table (Monday weeks) ----
wk = {}
for r in gated:
    wk.setdefault(monday(r["t0"]), []).append(r)
weekly = []
for k in sorted(wk):
    rs = wk[k]
    weekly.append({"week_of": k, "n": len(rs),
                   "ev_c": round(100 * sum(x["ev"] for x in rs) / len(rs), 2)})
out["weekly_gated"] = weekly
full = [w for w in weekly if w["n"] >= 50]
evs = [w["ev_c"] for w in full]
mu = sum(evs) / len(evs)
out["weekly_summary_full_weeks"] = {
    "n_weeks": len(full),
    "range_c": [min(evs), max(evs)],
    "sd_c": round(math.sqrt(sum((e - mu) ** 2 for e in evs) / (len(evs) - 1)), 2),
    "n_fee_negative": sum(1 for e in evs if e < 0),
}
# TEST concentration: TEST EV contribution by week
tw = {}
for r in win(gated, SPLIT):
    tw.setdefault(monday(r["t0"]), []).append(r)
out["TEST_by_week"] = {k: {"n": len(v), "ev_c": round(100 * sum(x['ev'] for x in v) / len(v), 2),
                           "sum_ev_$per_share": round(sum(x['ev'] for x in v), 3)}
                       for k, v in sorted(tw.items())}

# ---- daily series & rank of Jul 10 ----
dd = {}
for r in gated:
    dd.setdefault(day(r["t0"]), []).append(r)
daily = {k: {"n": len(v), "ev_c": round(100 * sum(x["ev"] for x in v) / len(v), 2)}
         for k, v in sorted(dd.items())}
out["daily_gated_last10"] = {k: daily[k] for k in sorted(daily)[-10:]}
ranked = sorted(((v["ev_c"], k) for k, v in daily.items() if v["n"] >= 5))
out["worst5_days_n_ge5"] = ranked[:5]
out["best5_days_n_ge5"] = ranked[-5:]
out["jul10_rank_of_days"] = {
    "jul10_ev_c": daily.get("07-10"), "n_days_n_ge5": len(ranked),
    "rank_from_worst": next((i + 1 for i, (e, k) in enumerate(ranked) if k == "07-10"), None)}

# ---- merge-agent flag: exclude Jul 10 ----
JUL11 = calendar.timegm((2026, 7, 11, 0, 0, 0))
out["gated_jul11_13_only"] = blockboot(win(gated, JUL11))
out["ungated_jul11_13_only"] = blockboot(win(ungated, JUL11))
out["gated_jul10_only_full_day"] = blockboot(win(gated, calendar.timegm((2026, 7, 10, 0, 0, 0)), JUL11))
out["gated_fresh_slice_of_jul10_1505_on"] = blockboot(win(gated, FRESH_A, JUL11))

# ---- stresses on FRESH_A gated ----
fr = win(gated, FRESH_A)
stress = {}
# drop best / worst day
days_fr = sorted({day(r["t0"]) for r in fr})
by = {k: [r for r in fr if day(r["t0"]) == k] for k in days_fr}
dsum = {k: sum(r["ev"] for r in v) for k, v in by.items()}
bestd = max(dsum, key=dsum.get)
worstd = min(dsum, key=dsum.get)
stress["per_day_ev_sum_$"] = {k: round(v, 3) for k, v in dsum.items()}
stress["drop_best_day"] = {"dropped": bestd, **(blockboot([r for r in fr if day(r["t0"]) != bestd]) or {})}
stress["drop_worst_day"] = {"dropped": worstd, **(blockboot([r for r in fr if day(r["t0"]) != worstd]) or {})}
# halves (chronological)
h = len(fr) // 2
stress["first_half"] = blockboot(fr[:h])
stress["second_half"] = blockboot(fr[h:])
# jitters
for lbl, kw in [("thr_11bp", dict(thr=0.0011)), ("thr_13bp", dict(thr=0.0013)),
                ("gateA_009", dict(gA=0.09)), ("gateA_011", dict(gA=0.11)),
                ("gateB_5", dict(gB=5)), ("gateB_7", dict(gB=7)),
                ("fill_50c", dict(pfill=0.50)), ("fill_52c", dict(pfill=0.52))]:
    g2, _ = build_trades(**kw)
    stress[f"jitter_{lbl}"] = blockboot(win(g2, FRESH_A))
out["stress_FRESH_A"] = stress

# same stresses' effect on the WEEKLY nonstationarity claim: recompute SD under jitters
jit_sd = {}
for lbl, kw in [("thr_11bp", dict(thr=0.0011)), ("thr_13bp", dict(thr=0.0013)),
                ("gateA_011", dict(gA=0.11))]:
    g2, _ = build_trades(**kw)
    w2 = {}
    for r in g2:
        w2.setdefault(monday(r["t0"]), []).append(r)
    e2 = [100 * sum(x["ev"] for x in v) / len(v) for k, v in sorted(w2.items()) if len(v) >= 50]
    m2 = sum(e2) / len(e2)
    jit_sd[lbl] = {"sd_c": round(math.sqrt(sum((e - m2) ** 2 for e in e2) / (len(e2) - 1)), 2),
                   "n_neg": sum(1 for e in e2 if e < 0), "n_weeks": len(e2)}
out["weekly_sd_under_jitter"] = jit_sd

json.dump(out, open("/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work/verify/R6-repro/repro_candles.json", "w"), indent=1)
print(json.dumps(out, indent=1))
