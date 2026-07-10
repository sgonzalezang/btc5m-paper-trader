#!/usr/bin/env python3
"""Magnitude-band variant analysis for reversal_v2.

Buckets prior-move |bps| into [12,16), [16,20), [20,25), [25,+) on cb5m 60d
(buffered open-to-open, contrarian, ties Up). Measures q per bucket on
full/TRAIN/TEST/6 folds, per-bucket contrarian fill pricing from
pm_prices_sample.json (uncensored) and the cap53-censored family ledger,
then nets band-limited (12-20) and rev20-only (>=20) books vs take-all
at bucket-specific fills with +1c/+2c sensitivity.
Block bootstrap: 1h blocks (12 candles), one-sided p vs 0.5 and paired deltas.
"""
import json, math, random

SCRATCH = "/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad"
random.seed(20260710)

cb = json.load(open(f"{SCRATCH}/data/cb5m.json"))
pm = json.load(open(f"{SCRATCH}/data/pm_prices_sample.json"))
tr = json.load(open(f"{SCRATCH}/data/trades.json"))
t, o, c = cb["t"], cb["o"], cb["c"]
N = len(t)
TRAIN_END = (N * 2) // 3          # 11520, matches a_stability.json
FOLD = N // 6                     # 2880 candles = 10d
BUCKETS = ["12-16", "16-20", "20-25", "25+"]

def bucket(bp):
    if bp < 16: return "12-16"
    if bp < 20: return "16-20"
    if bp < 25: return "20-25"
    return "25+"

def fee(p): return 0.07 * p * (1 - p)

# ---------- signals (buffered open-to-open, contiguous candles guaranteed: 17279 gaps all 300s)
sigs = []
for i in range(1, N):
    if t[i] - t[i-1] != 300:  # contiguity guard (none missing in this file)
        continue
    pr = (o[i] - o[i-1]) / o[i-1]
    bp = abs(pr) * 1e4
    if bp < 12:
        continue
    side = "down" if pr > 0 else "up"
    up_won = c[i] >= o[i]                      # ties resolve Up
    win = up_won if side == "up" else (not up_won)
    sigs.append(dict(i=i, t0=t[i], bp=bp, b=bucket(bp), side=side, win=int(win),
                     blk=i // 12, fold=min(i // FOLD, 5), tr=i < TRAIN_END))

def q(rows):
    n = len(rows)
    return (n, (sum(r["win"] for r in rows) / n) if n else None)

def boot_q(rows, reps=2000):
    """1h-block bootstrap one-sided p for q<=0.5, plus 90% CI."""
    if not rows: return None
    blocks = {}
    for r in rows: blocks.setdefault(r["blk"], []).append(r["win"])
    keys = list(blocks)
    stats = []
    for _ in range(reps):
        w = n = 0
        for k in (random.choice(keys) for _ in keys):
            w += sum(blocks[k]); n += len(blocks[k])
        stats.append(w / n)
    stats.sort()
    lo, hi = stats[int(0.05*reps)], stats[int(0.95*reps)]
    p = sum(1 for s in stats if s <= 0.5) / reps
    return dict(p_le_half=p, ci90=[round(lo,4), round(hi,4)])

# ---------- q tables
out = {"spec": {"train_end_idx": TRAIN_END, "n_candles": N, "fold_candles": FOLD}}
tab = {}
for b in BUCKETS + ["12-20", "20+", "all12"]:
    sel = [s for s in sigs if (s["b"] == b) or
           (b == "12-20" and s["bp"] < 20) or
           (b == "20+" and s["bp"] >= 20) or
           (b == "all12")]
    if b in ("12-20", "20+", "all12"):
        sel = [s for s in sigs if (b == "all12") or (b == "12-20" and s["bp"] < 20) or (b == "20+" and s["bp"] >= 20)]
    row = {}
    row["full_n"], row["full_q"] = q(sel)
    trn = [s for s in sel if s["tr"]]; tst = [s for s in sel if not s["tr"]]
    row["train_n"], row["train_q"] = q(trn)
    row["test_n"], row["test_q"] = q(tst)
    row["train_boot"] = boot_q(trn); row["test_boot"] = boot_q(tst)
    row["folds"] = [q([s for s in sel if s["fold"] == f]) for f in range(6)]
    tab[b] = row
out["q_table"] = tab

# ---------- fill pricing source 1: pm_prices_sample (uncensored, n=49 signal markets, last ~3d)
idx = {tt: i for i, tt in enumerate(t)}
pm_rows = []
for m in pm:
    i = idx.get(m["t0"])
    if not i: continue
    pr = (o[i] - o[i-1]) / o[i-1]
    bp = abs(pr) * 1e4
    if bp < 12: continue
    side = "down" if pr > 0 else "up"
    cp20 = m["p20"] if side == "up" else 1 - m["p20"]   # contrarian-side price @ t0+20s
    cost = cp20 + 0.01                                   # ask+1c slip convention
    pm_rows.append(dict(b=bucket(bp), bp=bp, cost=cost, up_won=m["up_won"],
                        win=int(m["up_won"] == 1) if side == "up" else int(m["up_won"] == 0)))
pmf = {}
allc = [r["cost"] for r in pm_rows]
cens_all = [x for x in allc if x <= 0.53 + 1e-9]
pm_overall_cens_mean = sum(cens_all) / len(cens_all)
for b in BUCKETS + ["12-20", "20+"]:
    rows = [r for r in pm_rows if r["b"] == b or (b == "12-20" and r["bp"] < 20) or (b == "20+" and r["bp"] >= 20)]
    costs = sorted(r["cost"] for r in rows)
    cens = [x for x in costs if x <= 0.53 + 1e-9]
    pmf[b] = dict(n=len(rows),
                  mean_cost=round(sum(costs)/len(costs), 4) if costs else None,
                  med_cost=costs[len(costs)//2] if costs else None,
                  avail_le53=round(len(cens)/len(costs), 3) if costs else None,
                  cens_mean=round(sum(cens)/len(cens), 4) if cens else None,
                  cens_offset_vs_all=round(sum(cens)/len(cens) - pm_overall_cens_mean, 4) if cens else None)
out["pm_fills"] = dict(overall_cens_mean=round(pm_overall_cens_mean, 4), buckets=pmf)

# ---------- fill pricing source 2: family ledger (155 settled; cap53 censored subset = the .4774 anchor)
fam = [x for x in tr if x["eng"] in ("reversal", "reversal2", "latentfire") and x.get("status") == "settled"]
led_rows = []
for x in fam:
    i = idx.get(x["t0"])
    if i is None or i < 1: continue
    pr = (o[i] - o[i-1]) / o[i-1]
    bp = abs(pr) * 1e4
    led_rows.append(dict(b=bucket(bp) if bp >= 12 else "<12", bp=bp, entry=x["entry"],
                         win=int(x.get("result") == "win")))
ledf = {}
cens_led_all = [r["entry"] for r in led_rows if r["entry"] <= 0.53 + 1e-9 and r["b"] != "<12"]
led_overall_cens_mean = sum(cens_led_all) / len(cens_led_all)
for b in BUCKETS + ["12-20", "20+", "<12"]:
    rows = [r for r in led_rows if r["b"] == b or
            (b == "12-20" and 12 <= r["bp"] < 20) or (b == "20+" and r["bp"] >= 20)]
    cens = [r["entry"] for r in rows if r["entry"] <= 0.53 + 1e-9]
    ledf[b] = dict(n=len(rows), n_cens=len(cens),
                   mean_entry=round(sum(r["entry"] for r in rows)/len(rows), 4) if rows else None,
                   cens_mean=round(sum(cens)/len(cens), 4) if cens else None,
                   cens_offset_vs_all=round(sum(cens)/len(cens) - led_overall_cens_mean, 4) if cens else None,
                   q_led=round(sum(r["win"] for r in rows)/len(rows), 4) if rows else None)
out["ledger_fills"] = dict(overall_cens_mean=round(led_overall_cens_mean, 4), buckets=ledf)

# ---------- bucket-specific fill assignment
BASE = 0.4774
# blend: ledger offset (censored, realized) primary; pm offset as cross-check. Use ledger where n_cens>=10 else pm.
fills = {}
for b in BUCKETS:
    lo_led = ledf[b]["cens_offset_vs_all"] if ledf[b]["n_cens"] and ledf[b]["n_cens"] >= 10 else None
    lo_pm = pmf[b]["cens_offset_vs_all"]
    off = lo_led if lo_led is not None else (lo_pm if lo_pm is not None else 0.0)
    fills[b] = dict(offset=round(off, 4), fill=round(min(BASE + off, 0.53), 4),
                    src="ledger" if lo_led is not None else "pm")
out["bucket_fills"] = fills

# ---------- book nets at bucket-specific fills, with sensitivity
def book_net(rows, bump=0.0, flat=None):
    """mean net/share and total net (1 share/trade) using bucket fills (+bump), or flat fill."""
    if not rows: return None
    tot = 0.0
    for r in rows:
        f = (flat if flat is not None else fills[r["b"]]["fill"]) + bump
        f = min(f, 0.53)  # cap: cost above .53 is not fillable under revEntryMax
        tot += r["win"] - f - fee(f)
    return dict(n=len(rows), net_share=round(tot/len(rows), 4), total=round(tot, 2))

books = {}
for name, cond in [("all12", lambda s: True), ("band12_20", lambda s: s["bp"] < 20),
                   ("rev20", lambda s: s["bp"] >= 20)]:
    sel = [s for s in sigs if cond(s)]
    ent = {}
    for split, rows in [("train", [s for s in sel if s["tr"]]), ("test", [s for s in sel if not s["tr"]]),
                        ("full", sel)]:
        ent[split] = {f"bump{int(b*100)}c": book_net(rows, bump=b) for b in (0.0, 0.01, 0.02)}
    ent["folds_net0"] = [book_net([s for s in sel if s["fold"] == f]) for f in range(6)]
    books[name] = ent
out["books"] = books

# rev20 with the confirmed large-move adjustment (fills 1-2c richer than its own bucket fill)
sel20 = [s for s in sigs if s["bp"] >= 20]
out["rev20_adj"] = {sp: {f"extra{int(b*100)}c": book_net(rows, bump=b)
                         for b in (0.0, 0.01, 0.02)}
                    for sp, rows in [("train", [s for s in sel20 if s["tr"]]),
                                     ("test", [s for s in sel20 if not s["tr"]])]}

# ---------- paired block-bootstrap: band vs all on TEST and TRAIN (delta net/share at bucket fills)
def paired_boot(split_flag, reps=2000):
    rows = [s for s in sigs if s["tr"] == split_flag]
    blocks = {}
    for r in rows: blocks.setdefault(r["blk"], []).append(r)
    keys = list(blocks)
    deltas_share, deltas_total = [], []
    for _ in range(reps):
        sa = na = sb = nb = 0.0
        for k in (random.choice(keys) for _ in keys):
            for r in blocks[k]:
                f = fills[r["b"]]["fill"]
                net = r["win"] - f - fee(f)
                sa += net; na += 1
                if r["bp"] < 20: sb += net; nb += 1
        if na and nb:
            deltas_share.append(sb/nb - sa/na)
            deltas_total.append(sb - sa)
    deltas_share.sort(); deltas_total.sort()
    m = len(deltas_share)
    return dict(d_share_ci90=[round(deltas_share[int(0.05*m)],4), round(deltas_share[int(0.95*m)],4)],
                d_share_p_le0=round(sum(1 for d in deltas_share if d <= 0)/m, 4),
                d_total_ci90=[round(deltas_total[int(0.05*m)],2), round(deltas_total[int(0.95*m)],2)],
                d_total_p_le0=round(sum(1 for d in deltas_total if d <= 0)/m, 4))
out["paired_band_minus_all"] = {"train": paired_boot(True), "test": paired_boot(False)}

json.dump(out, open(f"{SCRATCH}/work/variant-band/band_results.json", "w"), indent=1)
print(json.dumps(out, indent=1))
