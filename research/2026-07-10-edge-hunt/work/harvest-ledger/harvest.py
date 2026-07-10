import json, os
SC="/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad"
BOT="/Users/sgonzalez/btc5m-paper-trader/bot"
files=[("current", BOT+"/state.json"),
       ("prereset", BOT+"/archive/state-2026-07-08-pre-reset.json"),
       ("bak_pretrue", BOT+"/state.json.bak-pretrue")]
seen=set(); trades=[]; per_src={}
for src,path in files:
    d=json.load(open(path))
    engines=d.get("btc",{}).get("engines",{})
    cnt=0
    for eng,ed in engines.items():
        for tr in (ed.get("trades") or []):
            t=dict(tr); t["eng"]=tr.get("eng",eng); t["src"]=src
            key=(t["eng"], t.get("t0"), t.get("at"))
            if key in seen: continue
            seen.add(key); trades.append(t); cnt+=1
    per_src[src]=cnt
trades.sort(key=lambda t:(t.get("at") or 0))
json.dump(trades, open(SC+"/data/trades.json","w"))
cur=json.load(open(BOT+"/state.json"))
json.dump(cur["btc"].get("ivlHist",[]), open(SC+"/data/ivlhist.json","w"))
json.dump(cur.get("engineCfg",{}), open(SC+"/data/englist.json","w"))

def q(vals, p):
    v=sorted(vals); n=len(v)
    if n==0: return None
    i=p*(n-1); lo=int(i); hi=min(lo+1,n-1); f=i-lo
    return round(v[lo]*(1-f)+v[hi]*f, 6)
def quants(vals):
    return {"p10":q(vals,0.10),"p50":q(vals,0.50),"p90":q(vals,0.90)} if vals else None

summary={}
for t in trades:
    key=(t["eng"], t["src"])
    summary.setdefault(key, []).append(t)
out={}
for (eng,src),ts in sorted(summary.items()):
    settled=[t for t in ts if t.get("status")=="settled"]
    wins=sum(1 for t in settled if t.get("result")=="win")
    losses=sum(1 for t in settled if t.get("result")=="loss")
    pnl=round(sum(t.get("pnl") or 0 for t in settled),2)
    asks=[t["ask"] for t in ts if t.get("ask") is not None]
    entries=[t["entry"] for t in ts if t.get("entry") is not None]
    esec=[t["entrySec"] for t in ts if t.get("entrySec") is not None]
    ff=[t["fillFrac"] for t in ts if t.get("fillFrac") is not None]
    fees=round(sum((t.get("feeEntry") or 0)+(t.get("feeExit") or 0)+(t.get("gas") or 0) for t in ts),2)
    feeds={}
    for t in ts: feeds[t.get("feed") or "?"]=feeds.get(t.get("feed") or "?",0)+1
    dr=[t["driftPct"] for t in ts if t.get("driftPct") is not None]
    out.setdefault(eng,{})[src]={"n":len(ts),"n_settled":len(settled),"wins":wins,"losses":losses,
        "pnl":pnl,"ask":quants(asks),"entry":quants(entries),"entrySec":quants(esec),
        "fillFrac_mean":round(sum(ff)/len(ff),4) if ff else None,"fees_total":fees,
        "feeds":feeds,"driftPct":quants(dr)}
json.dump(out, open(SC+"/data/ledger_summary.json","w"), indent=1)
print("per_src new trades:", per_src, "total:", len(trades))
for eng,srcs in out.items():
    for src,s in srcs.items():
        print(f"{eng:10s} {src:11s} n={s['n']:4d} w/l={s['wins']}/{s['losses']} pnl={s['pnl']:9.2f} ask_p50={s['ask']['p50'] if s['ask'] else None} fees={s['fees_total']}")
