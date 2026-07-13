"""T6: Effective spread from signals.log (bid+ask at fill decision, n=1,622,
Jul 8-13). Frozen model charges ask+1c; realistic taker fill = ask.
'Effective cost above mid' = (ask - mid) + 1c slip = spread/2 + 1c.
By hour of day (UTC), by engine family, by secLeft.
"""
import json, collections, datetime
import common as C

sigs = C.load_signals()
out = {"n": len(sigs)}
rows = []
for s in sigs:
    if s.get("ask") is None or s.get("bid") is None: continue
    sp = round(s["ask"] - s["bid"], 4)
    if sp < 0: continue
    hour = datetime.datetime.utcfromtimestamp(s["t0"]).hour
    rows.append(dict(t0=s["t0"], eng=s["engine"], hour=hour, spread=sp,
                     secleft=s.get("secLeft"), ask=s["ask"]))
out["n_with_book"] = len(rows)

def pct(vals, p):
    if not vals: return None
    vals = sorted(vals); i = min(len(vals)-1, int(p*len(vals)))
    return vals[i]

# overall
sp = [r["spread"] for r in rows]
out["spread_overall"] = dict(n=len(sp), p50=pct(sp, .5), p90=pct(sp, .9),
                             p95=pct(sp, .95), mean=round(sum(sp)/len(sp), 4),
                             frac_1c=round(sum(1 for v in sp if v <= 0.0101)/len(sp), 4))

# by hour
byh = collections.defaultdict(list)
for r in rows: byh[r["hour"]].append(r["spread"])
out["by_hour"] = {h: dict(n=len(v), p50=pct(v, .5), p95=pct(v, .95),
                          mean=round(sum(v)/len(v), 4),
                          frac_gt_1c=round(sum(1 for x in v if x > 0.0101)/len(v), 3),
                          eff_cost_above_mid_c=round((sum(v)/len(v)/2 + 0.01)*100, 2))
                  for h, v in sorted(byh.items())}

# by engine family
fam = lambda e: "trigger_family" if e in ("reversal", "impulse_v2") else "momentum"
byf = collections.defaultdict(list)
for r in rows: byf[fam(r["eng"])].append(r["spread"])
out["by_family"] = {f: dict(n=len(v), p50=pct(v, .5), p95=pct(v, .95),
                            mean=round(sum(v)/len(v), 4),
                            frac_1c=round(sum(1 for x in v if x <= 0.0101)/len(v), 3))
                    for f, v in byf.items()}

# by secLeft for trigger family (entry window position)
trig = [r for r in rows if fam(r["eng"]) == "trigger_family" and r["secleft"] is not None]
bins = [(255, 301), (150, 255), (0, 150)]
out["trigger_by_secleft"] = {}
for lo, hi in bins:
    v = [r["spread"] for r in trig if lo <= r["secleft"] < hi]
    if v:
        out["trigger_by_secleft"][f"secLeft[{lo},{hi})"] = dict(
            n=len(v), p50=pct(v, .5), p95=pct(v, .95), mean=round(sum(v)/len(v), 4))

# hour x spread>1c interaction for trigger family only
byh_t = collections.defaultdict(list)
for r in trig: byh_t[r["hour"]].append(r["spread"])
out["trigger_by_hour"] = {h: dict(n=len(v), mean=round(sum(v)/len(v), 4),
                                  frac_gt_1c=round(sum(1 for x in v if x > 0.0101)/len(v), 3))
                          for h, v in sorted(byh_t.items()) if len(v) >= 3}

json.dump(out, open("spread.json", "w"), indent=1)
print(json.dumps(out, indent=1))
