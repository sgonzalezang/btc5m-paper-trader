#!/usr/bin/env python3
"""Addendum: rev20-vs-all paired boot, availability-weighted totals, per-bucket nets."""
import json, random

SCRATCH = "/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad"
random.seed(20260711)
cb = json.load(open(f"{SCRATCH}/data/cb5m.json"))
res = json.load(open(f"{SCRATCH}/work/variant-band/band_results.json"))
t, o, c = cb["t"], cb["o"], cb["c"]
N = len(t); TRAIN_END = (N*2)//3
fills = {b: v["fill"] for b, v in res["bucket_fills"].items()}
AVAIL = {b: res["pm_fills"]["buckets"][b]["avail_le53"] for b in fills}  # pm sample, cost<=.53

def bucket(bp):
    return "12-16" if bp < 16 else "16-20" if bp < 20 else "20-25" if bp < 25 else "25+"
def fee(p): return 0.07*p*(1-p)

sigs = []
for i in range(1, N):
    pr = (o[i]-o[i-1])/o[i-1]; bp = abs(pr)*1e4
    if bp < 12: continue
    side = "down" if pr > 0 else "up"
    up = c[i] >= o[i]
    sigs.append(dict(bp=bp, b=bucket(bp), win=int(up if side == "up" else not up),
                     blk=i//12, tr=i < TRAIN_END))

def paired_boot(cond, split, reps=2000):
    rows = [s for s in sigs if s["tr"] == split]
    blocks = {}
    for r in rows: blocks.setdefault(r["blk"], []).append(r)
    keys = list(blocks)
    ds = []
    for _ in range(reps):
        sa = na = sb = nb = 0.0
        for k in (random.choice(keys) for _ in keys):
            for r in blocks[k]:
                f = fills[r["b"]]
                net = r["win"] - f - fee(f)
                sa += net; na += 1
                if cond(r): sb += net; nb += 1
        if na and nb: ds.append(sb/nb - sa/na)
    ds.sort(); m = len(ds)
    return dict(ci90=[round(ds[int(.05*m)],4), round(ds[int(.95*m)],4)],
                p_le0=round(sum(1 for d in ds if d <= 0)/m, 4))

out = {}
out["paired_rev20_minus_all"] = {
    "train": paired_boot(lambda r: r["bp"] >= 20, True),
    "test":  paired_boot(lambda r: r["bp"] >= 20, False)}

# per-bucket net/share at bucket fill, TRAIN/TEST, bumps 0/1/2c
per = {}
for b in fills:
    row = {}
    for sp, flag in (("train", True), ("test", False)):
        sel = [s for s in sigs if s["b"] == b and s["tr"] == flag]
        qq = sum(s["win"] for s in sel)/len(sel)
        row[sp] = {f"+{int(k*100)}c": round(qq - (fills[b]+k) - fee(fills[b]+k), 4) for k in (0, .01, .02)}
        row[sp]["q"] = round(qq, 4); row[sp]["n"] = len(sel)
    per[b] = row
out["bucket_nets"] = per

# availability-weighted totals (fills/60d and TEST/TRAIN total EV at 1 share per fill)
aw = {}
for name, cond in [("all12", lambda s: True), ("band12_20", lambda s: s["bp"] < 20),
                   ("rev20", lambda s: s["bp"] >= 20)]:
    ent = {}
    for sp, flag in (("train", True), ("test", False), ("full", None)):
        tot = nf = 0.0
        for s in sigs:
            if not cond(s) or (flag is not None and s["tr"] != flag): continue
            f = fills[s["b"]]
            tot += AVAIL[s["b"]] * (s["win"] - f - fee(f))
            nf += AVAIL[s["b"]]
        ent[sp] = dict(exp_fills=round(nf, 0), aw_total=round(tot, 2),
                       net_share=round(tot/nf, 4))
    aw[name] = ent
out["avail_weighted"] = aw
out["avail_used"] = AVAIL

json.dump(out, open(f"{SCRATCH}/work/variant-band/band_addendum.json", "w"), indent=1)
print(json.dumps(out, indent=1))
