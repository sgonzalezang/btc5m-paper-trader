#!/usr/bin/env python3
"""Follow-up: (a) conservative PM-snapshot join using the first snapshot AT/AFTER
the decision moment (the repriced market a real taker races against), (b) the
59-60c aligned slice that drives edge-jitter sensitivity, (c) snapshot sample
coverage, (d) driftPct-field vs recomputed drift consistency."""
import json, math, datetime

DATA = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data/trades_unified.json"
PM   = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-10-edge-hunt/data/pm_prices_sample.json"
OUT  = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/work/verify/R3-repro/results2.json"

def fee(p): return 0.07*p*(1-p)
def utc_day(t0): return datetime.datetime.fromtimestamp(t0, datetime.timezone.utc).strftime("%m-%d")

trades = json.load(open(DATA))
settled = []
for t in trades:
    if t.get("result") not in ("win","loss"): continue
    if t.get("entry") is None or t.get("btcOpen") is None or t.get("btcEntry") is None: continue
    d = (t["btcEntry"]-t["btcOpen"])/t["btcOpen"]*1e4
    t["_drift_bps"]=d
    t["_aligned4"]=(t["side"]=="up" and d>=4) or (t["side"]=="down" and d<=-4)
    t["_day"]=utc_day(t["t0"])
    settled.append(t)
JUL710={"07-07","07-08","07-09","07-10"}

def dedup(trs):
    best={}
    for t in sorted(trs,key=lambda x:x["at"]): best.setdefault(t["t0"],t)
    return list(best.values())

def summ(trs):
    n=len(trs)
    if n==0: return {"n":0}
    w=sum(1 for t in trs if t["result"]=="win"); pm=sum(t["entry"] for t in trs)/n
    ev=sum((1.0 if t["result"]=="win" else 0.0)-t["entry"]-fee(t["entry"]) for t in trs)/n
    return {"n":n,"wins":w,"q":round(w/n,4),"p_mean":round(pm,4),"ev_c":round(100*ev,2)}

R={}

# (b) the slice just below the band's lower edge
c5960 = dedup([t for t in settled if 0.59<=t["entry"]<0.60 and t["_aligned4"] and t["_day"] in JUL710])
c5559 = dedup([t for t in settled if 0.55<=t["entry"]<0.59 and t["_aligned4"] and t["_day"] in JUL710])
c6566 = dedup([t for t in settled if 0.65<=t["entry"]<0.66 and t["_aligned4"] and t["_day"] in JUL710])
R["aligned_59_60"]=summ(c5960); R["aligned_55_59"]=summ(c5559); R["aligned_65_66"]=summ(c6566)

# (c) snapshot coverage
pmS={s["t0"]:s for s in json.load(open(PM))}
ts=sorted(pmS)
R["pm_sample_coverage"]={"n":len(ts),
  "first":datetime.datetime.fromtimestamp(ts[0],datetime.timezone.utc).isoformat(),
  "last":datetime.datetime.fromtimestamp(ts[-1],datetime.timezone.utc).isoformat()}

# (a) conservative join: first snapshot at/after entrySec
cell = dedup([t for t in settled if 0.60<=t["entry"]<0.65 and t["_aligned4"] and t["_day"] in JUL710])
rows=[]
for t in cell:
    s=pmS.get(t["t0"])
    if not s: continue
    sec=t.get("entrySec") or 30
    after=[(k,s[v]) for k,v in [(20,"p20"),(60,"p60"),(150,"p150")] if k>=sec and s[v] is not None]
    if not after: continue
    k,p=after[0]
    sp=p if t["side"]=="up" else round(1-p,4)
    p2=min(sp+0.01,0.99)
    w=1.0 if t["result"]=="win" else 0.0
    rows.append({"t0":t["t0"],"side":t["side"],"entrySec":sec,"snap_at":k,
                 "ledger_entry":t["entry"],"pm_after_side":sp,
                 "gap_c":round(100*(sp-t["entry"]),1),"win":int(w),
                 "ev_snapfill_c":round(100*(w-p2-fee(p2)),1)})
if rows:
    gaps=sorted(r["gap_c"] for r in rows)
    R["join_after_snapshot_band"]={
      "n":len(rows),
      "mean_gap_c":round(sum(gaps)/len(gaps),2),
      "median_gap_c":gaps[len(gaps)//2],
      "frac_market_repriced_above_entry":round(sum(1 for g in gaps if g>0)/len(gaps),3),
      "ev_if_filled_at_after_snapshot_c":round(sum(r["ev_snapfill_c"] for r in rows)/len(rows),2),
      "rows":rows}

# same, any aligned>=4bps trade any price (more n)
cellA = dedup([t for t in settled if t["_aligned4"] and t["_day"] in JUL710])
rowsA=[]
for t in cellA:
    s=pmS.get(t["t0"])
    if not s: continue
    sec=t.get("entrySec") or 30
    after=[(k,s[v]) for k,v in [(20,"p20"),(60,"p60"),(150,"p150")] if k>=sec and s[v] is not None]
    if not after: continue
    k,p=after[0]
    sp=p if t["side"]=="up" else round(1-p,4)
    p2=min(sp+0.01,0.99)
    w=1.0 if t["result"]=="win" else 0.0
    rowsA.append({"gap_c":round(100*(sp-t["entry"]),1),"ev_snapfill_c":round(100*(w-p2-fee(p2)),1),
                  "ledger_entry":t["entry"],"snap":sp,"sec":sec,"snap_at":k})
if rowsA:
    g=sorted(r["gap_c"] for r in rowsA)
    R["join_after_snapshot_anyprice"]={
      "n":len(rowsA),"mean_gap_c":round(sum(g)/len(g),2),"median_gap_c":g[len(g)//2],
      "frac_repriced_above":round(sum(1 for x in g if x>0)/len(g),3),
      "ev_if_filled_at_after_snapshot_c":round(sum(r["ev_snapfill_c"] for r in rowsA)/len(rowsA),2)}

# (d) ledger driftPct field vs recomputed drift (units check, mismatch count)
mism=0; n=0
for t in settled:
    dp=t.get("driftPct")
    if dp is None: continue
    n+=1
    # driftPct appears to be in percent; 4bps = 0.04%
    if abs(dp*100 - t["_drift_bps"]) > 0.5: mism+=1  # 0.5bp tolerance
R["driftPct_field_check"]={"n_with_field":n,"n_mismatch_gt_0p5bp":mism}

json.dump(R,open(OUT,"w"),indent=1)
print(json.dumps({k:(dict(v,rows=v["rows"][:6]) if isinstance(v,dict) and "rows" in v else v) for k,v in R.items()},indent=1))
