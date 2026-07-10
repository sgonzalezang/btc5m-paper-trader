#!/usr/bin/env python3
"""(d) Entry timing: does waiting (better info, worse price) improve net EV?

Test 1 (market data, selection-free): buy the current favorite at 20s vs 60s vs 150s
using pm_prices_sample.json actual Up-token snapshots. Fill = fav price + 1c slip,
exact taker fee. Chronological 2/3-1/3 split.
Test 2 (ledger, observational): momentum engines pooled, net pnl/trade by entrySec bucket.
Output: work/exits/entry_timing.json
"""
import json, math, random

SCRATCH = "/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad"
pm = json.load(open(SCRATCH + "/data/pm_prices_sample.json"))
pm = [m for m in pm if all(m.get(k) is not None for k in ("p20", "p60", "p150", "up_won"))]
pm.sort(key=lambda m: m["t0"])
n = len(pm)
split = pm[0]["t0"] + (pm[-1]["t0"] - pm[0]["t0"]) * 2 / 3
print(f"pm markets n={n}, span {(pm[-1]['t0']-pm[0]['t0'])/86400:.2f}d, split t0={split:.0f}")

def ev_rows(ms, snap):
    out = []
    for m in ms:
        p = m[snap]
        fav_up = p >= 0.5
        fill = (p if fav_up else 1 - p) + 0.01  # ask + 1c slip
        if fill >= 0.99:
            continue  # unbuyable
        win = 1 if (m["up_won"] == 1) == fav_up else 0
        ev = win - fill - 0.07 * fill * (1 - fill)
        out.append((m["t0"], fill, win, ev))
    return out

def summarize(rows):
    k = len(rows)
    if k == 0:
        return None
    mf = sum(r[1] for r in rows) / k
    wr = sum(r[2] for r in rows) / k
    ev = sum(r[3] for r in rows) / k
    qstar = mf + 0.07 * mf * (1 - mf)
    return {"n": k, "mean_fill": round(mf, 3), "win_rate": round(wr, 3),
            "breakeven_q": round(qstar, 3), "ev_per_share": round(ev, 4)}

def boot_p(rows, iters=4000, seed=11):
    """block bootstrap (1h blocks) P(sign flip) of mean EV"""
    blocks = {}
    for t0, f, w, e in rows:
        blocks.setdefault(t0 // 3600, []).append(e)
    bl = list(blocks.values())
    obs = sum(e for _, _, _, e in rows) / len(rows)
    rng = random.Random(seed)
    flip = 0
    for _ in range(iters):
        s, c = 0.0, 0
        for _ in range(len(bl)):
            b = bl[rng.randrange(len(bl))]
            s += sum(b); c += len(b)
        m = s / c
        if (obs < 0 and m >= 0) or (obs >= 0 and m <= 0):
            flip += 1
    return obs, flip / iters

res = {}
print("\nBuy-the-favorite at snapshot T (net EV/share after fee+slip):")
for snap in ("p20", "p60", "p150"):
    tr = ev_rows([m for m in pm if m["t0"] < split], snap)
    te = ev_rows([m for m in pm if m["t0"] >= split], snap)
    al = ev_rows(pm, snap)
    obs, p = boot_p(al)
    res[snap] = {"train": summarize(tr), "test": summarize(te), "all": summarize(al),
                 "all_boot_p": p}
    print(f"  {snap}: TRAIN {summarize(tr)}")
    print(f"        TEST  {summarize(te)}")
    print(f"        ALL   {summarize(al)}  boot_p={p:.3f}")

# paired diff on same markets: EV(p60) - EV(p20), EV(p150) - EV(p20)
print("\nPaired per-market EV differences (same markets):")
for late in ("p60", "p150"):
    diffs = []
    for m in pm:
        a = ev_rows([m], "p20")
        b = ev_rows([m], late)
        if a and b:
            diffs.append((m["t0"], 0, 0, b[0][3] - a[0][3]))
    obs, p = boot_p(diffs)
    res[f"paired_{late}_minus_p20"] = {"n": len(diffs), "mean": round(obs, 4), "boot_p": p}
    print(f"  {late} - p20: n={len(diffs)} mean={obs:+.4f}/share boot_p={p:.3f}")

# Test 2: ledger entrySec buckets, momentum engines pooled (current era only for consistency)
rows = json.load(open(SCRATCH + "/work/exits/joined.json"))
mom = [r for r in rows if r["eng"] in ("loose", "floor", "band", "value")
       and r["entrySec"] is not None and r["src"] == "current"]
buckets = [(0, 20), (21, 45), (46, 90), (91, 300)]
print(f"\nLedger momentum engines pooled (n={len(mom)}): net pnl/trade by entrySec")
res["ledger_entrySec"] = []
for lo, hi in buckets:
    sub = [r for r in mom if lo <= r["entrySec"] <= hi]
    if not sub:
        continue
    mp = sum(r["pnl_hold"] for r in sub) / len(sub)
    wr = sum(r["win"] for r in sub) / len(sub)
    me = sum(r["entry"] for r in sub) / len(sub)
    qs = me + 0.07 * me * (1 - me)
    row = {"bucket": f"{lo}-{hi}s", "n": len(sub), "mean_pnl": round(mp, 2),
           "win_rate": round(wr, 3), "mean_entry": round(me, 3), "breakeven_q": round(qs, 3)}
    res["ledger_entrySec"].append(row)
    print(f"  {lo:>3}-{hi:<3}s n={len(sub):>4} pnl/tr={mp:+.2f} win={wr:.3f} entry={me:.3f} q*={qs:.3f}")

json.dump(res, open(SCRATCH + "/work/exits/entry_timing.json", "w"), indent=1)
print("\nwrote work/exits/entry_timing.json")
