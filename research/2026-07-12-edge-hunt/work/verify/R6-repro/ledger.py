#!/usr/bin/env python3
"""R6 reproduction, part 2: live-ledger corroborations + independence audit.

Recompute from trades_unified.json (fresh window Jul 10 15:05 -> end):
  - impulse50 net per-share, reversal_v2 net per-share, impulse_v2 as-operated
  - measure book wr from state_extract.json
  - OVERLAP: how many distinct t0/hours the 'corroborating' books share with the
    candle fresh window (merge-agent flag: same 2.5 days read three times)
Also: ungated daily series to locate the merge agent's '-13.97c Jul 10' figure.
"""
import json, calendar, datetime, random, math

DATA = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data"
FRESH_A = calendar.timegm((2026, 7, 10, 15, 5, 0))
GAS = 0.004

tr = json.load(open(f"{DATA}/trades_unified.json"))
st = json.load(open(f"{DATA}/state_extract.json"))


def ps_cents(t):  # realized net per-share in cents from ledger pnl
    return 100.0 * t["pnl"] / t["shares"] if t.get("shares") else None


def boot(vals_with_t0, reps=6000, seed=11):
    blocks = {}
    for t0, v in vals_with_t0:
        blocks.setdefault(t0 // 3600, []).append(v)
    keys = list(blocks.keys())
    rng = random.Random(seed)
    ms = []
    for _ in range(reps):
        tot = cnt = 0
        for _ in range(len(keys)):
            b = blocks[keys[rng.randrange(len(keys))]]
            tot += sum(b)
            cnt += len(b)
        ms.append(tot / cnt if cnt else 0.0)
    ms.sort()
    mean = sum(v for _, v in vals_with_t0) / len(vals_with_t0)
    return {"n": len(vals_with_t0), "mean_c": round(mean, 2),
            "ci90_c": [round(ms[int(.05 * len(ms))], 2), round(ms[int(.95 * len(ms)) - 1], 2)]}


out = {}
books = {}
for eng in ("impulse50", "reversal_v2", "impulse_v2"):
    rows = [t for t in tr if t["eng"] == eng and t.get("result") in ("win", "loss")
            and t["t0"] >= FRESH_A]
    vals = [(t["t0"], ps_cents(t)) for t in rows]
    wins = sum(1 for t in rows if t["result"] == "win")
    b = boot(vals) if vals else {}
    b["wr"] = round(wins / len(rows), 4) if rows else None
    b["pnl_$"] = round(sum(t["pnl"] for t in rows), 2)
    b["t0s"] = sorted({t["t0"] for t in rows})
    books[eng] = b
    out[f"ledger_{eng}_fresh"] = {k: v for k, v in b.items() if k != "t0s"}

# frozen-cost-model version (win - cost(entry)) as a cross-check on impulse50
rows50 = [t for t in tr if t["eng"] == "impulse50" and t.get("result") in ("win", "loss")
          and t["t0"] >= FRESH_A]
vals_cm = [(t["t0"], 100 * ((1 if t["result"] == "win" else 0)
            - t["entry"] - 0.07 * t["entry"] * (1 - t["entry"])) - GAS / t["shares"] * 100)
           for t in rows50]
out["impulse50_frozen_cost_model"] = boot(vals_cm, seed=12)

# measure book
ms = st["measure"]
settled = [m for m in ms if m.get("win") in (0, 1, True, False)]
out["measure_book"] = {"n_records": len(ms), "n_settled": len(settled),
                       "wins": sum(1 for m in settled if m["win"]),
                       "wr": round(sum(1 for m in settled if m["win"]) / len(settled), 4)}

# ---- independence audit: hour-block overlap between books ----
def hours(t0s):
    return {x // 3600 for x in t0s}


h50, hrev, hv2 = hours(books["impulse50"]["t0s"]), hours(books["reversal_v2"]["t0s"]), hours(books["impulse_v2"]["t0s"])
mh = {m["t0"] // 3600 for m in ms}
out["overlap_audit"] = {
    "impulse50_hours": len(h50), "reversal_v2_hours": len(hrev),
    "impulse_v2_hours": len(hv2), "measure_hours": len(mh),
    "i50_and_rev_shared_hours": len(h50 & hrev),
    "i50_and_measure_shared_hours": len(h50 & mh),
    "shared_t0_i50_rev": len(set(books["impulse50"]["t0s"]) & set(books["reversal_v2"]["t0s"])),
    "note": "all books sample the same Jul 10 15:05 - Jul 13 markets; corroboration is the same period, only fill/selection differ",
}

# span of the fresh window in days and hours
allt = sorted(set(books["impulse50"]["t0s"]) | set(books["reversal_v2"]["t0s"]))
out["fresh_window_span"] = {
    "first": datetime.datetime.utcfromtimestamp(allt[0]).isoformat(),
    "last": datetime.datetime.utcfromtimestamp(allt[-1]).isoformat(),
    "span_hours": round((allt[-1] - allt[0]) / 3600, 1)}

# ---- ungated daily series (to trace merge agent's -13.97c Jul 10) ----
cb = json.load(open(f"{DATA}/cb5m.json"))
T, O = cb["t"], cb["o"]
daily = {}
for i in range(1, len(T) - 1):
    if T[i] - T[i - 1] != 300:
        continue
    mv = (O[i] - O[i - 1]) / O[i - 1]
    if abs(mv) < 0.0012:
        continue
    win = 1 if ((mv < 0) == (O[i + 1] >= O[i])) else 0
    ev = 100 * (win - (0.51 + 0.07 * 0.51 * 0.49 + 0.00004))
    d = datetime.datetime.utcfromtimestamp(T[i]).strftime("%m-%d")
    daily.setdefault(d, []).append(ev)
ud = {k: (len(v), round(sum(v) / len(v), 2)) for k, v in sorted(daily.items())}
out["ungated_daily_jul_07_13"] = {k: ud[k] for k in ud if k >= "07-07"}
rank = sorted(((v[1], k) for k, v in ud.items() if v[0] >= 5))
out["ungated_worst5"] = rank[:5]
out["ungated_jul10_rank_from_worst"] = next((i + 1 for i, (e, k) in enumerate(rank) if k == "07-10"), None)
out["ungated_n_days"] = len(rank)

json.dump(out, open("/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work/verify/R6-repro/repro_ledger.json", "w"), indent=1)
print(json.dumps(out, indent=1))
