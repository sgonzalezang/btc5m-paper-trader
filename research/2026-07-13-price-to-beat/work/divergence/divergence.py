#!/usr/bin/env python3
"""Coinbase-derived direction vs Polymarket (Chainlink) oracle truth."""
import json, datetime

DATA12 = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-12-edge-hunt/data"
DATA10 = "/Users/sgonzalez/btc5m-paper-trader/research/2026-07-10-edge-hunt/data"

cb = json.load(open(f"{DATA12}/cb1m.json"))
cb_o = {t: o for t, o in zip(cb["t"], cb["o"])}
cb_c = {t: c for t, c in zip(cb["t"], cb["c"])}
bn = json.load(open(f"{DATA10}/bn5m.json"))
bn_o = {t: o for t, o in zip(bn["t"], bn["o"])}   # 5m open keyed by t0
bn_c = {t: c for t, c in zip(bn["t"], bn["c"])}
res = json.load(open(f"{DATA10}/pm_res_3d.json"))  # [[t0, up(1/0)], ...]

# clearMargin from live.html: max(15, 0.03% of price)
def clear_margin(px): return max(15.0, px * 0.0003)

rows = []
miss_open = miss_settle = 0
for t0, up in res:
    o = cb_o.get(t0)                 # strikeOf(t0): coinbase 1m open at t0
    s = cb_o.get(t0 + 300)           # settleOf: next interval open = boundary instant
    if o is None:
        miss_open += 1; continue
    if s is None:
        # fallback to close of the last candle in the window (t0+240) if next open missing
        s = cb_c.get(t0 + 240)
        if s is None:
            miss_settle += 1; continue
    move = s - o
    bps = (move / o) * 1e4
    dir_strict = 1 if s > o else 0            # up iff settle > open
    dir_ge     = 1 if s >= o else 0           # up iff settle >= open (ties->up, oracle rule)
    rows.append({
        "t0": t0, "oracle_up": up,
        "cb_open": o, "cb_settle": s, "move": move, "abps": abs(bps),
        "dir_strict": dir_strict, "dir_ge": dir_ge,
        "cm": clear_margin(o),
        "confident": abs(move) >= clear_margin(o),
    })

n = len(rows)
agree_strict = sum(1 for r in rows if r["dir_strict"] == r["oracle_up"])
agree_ge     = sum(1 for r in rows if r["dir_ge"] == r["oracle_up"])

# bps buckets
buckets = [(0,1),(1,2),(2,4),(4,8),(8,15),(15,1e9)]
def bname(lo,hi): return f"{lo}-{hi}" if hi<1e9 else f"{lo}+"
table = []
for lo,hi in buckets:
    sub = [r for r in rows if lo <= r["abps"] < hi]
    if not sub:
        table.append({"bucket":bname(lo,hi),"n":0}); continue
    dis_strict = sum(1 for r in sub if r["dir_strict"] != r["oracle_up"])
    dis_ge     = sum(1 for r in sub if r["dir_ge"]     != r["oracle_up"])
    table.append({
        "bucket": bname(lo,hi), "n": len(sub),
        "disagree_strict": dis_strict, "disagree_strict_pct": round(100*dis_strict/len(sub),2),
        "disagree_ge": dis_ge, "disagree_ge_pct": round(100*dis_ge/len(sub),2),
    })

# ---- User-facing harm: confident leader (|move|>=clearMargin) that resolved the OTHER way
conf = [r for r in rows if r["confident"]]
conf_wrong = [r for r in conf if r["dir_strict"] != r["oracle_up"]]
# also raw-sign confident (what the LIVE 'leads' line actually shows: any nonzero move)
allsign = [r for r in rows if r["move"] != 0]
allsign_wrong = [r for r in allsign if r["dir_strict"] != r["oracle_up"]]

# distribution of the confident-wrong by bps
cw_by_bucket = {}
for lo,hi in buckets:
    cw_by_bucket[bname(lo,hi)] = sum(1 for r in conf_wrong if lo <= r["abps"] < hi)

# ---- Ties: intervals where cb says exactly 0 move (right at the line)
ties = [r for r in rows if r["move"] == 0]
ties_oracle_up = sum(r["oracle_up"] for r in ties)

# ---- Price-LEVEL gap Coinbase vs Binance at 5m boundaries (proxy for cb vs chainlink spread)
# cb boundary price at t0 = cb_o[t0]; bn boundary open at t0 = bn_o[t0]
gaps = []
for t0,_ in res:
    co = cb_o.get(t0); bo = bn_o.get(t0)
    if co is None or bo is None: continue
    gaps.append(abs(co - bo))
gaps.sort()
def pct(a,p):
    if not a: return None
    i = min(len(a)-1, int(p/100*len(a)))
    return a[i]
gap_stats = {
    "n": len(gaps),
    "median": round(pct(gaps,50),2) if gaps else None,
    "p75": round(pct(gaps,75),2) if gaps else None,
    "p90": round(pct(gaps,90),2) if gaps else None,
    "p95": round(pct(gaps,95),2) if gaps else None,
    "max": round(max(gaps),2) if gaps else None,
    "mean": round(sum(gaps)/len(gaps),2) if gaps else None,
}
# gap AT boundaries (near-flat oracle-decisive zone): confident-wrong intervals
gap_at_wrong = []
for r in conf_wrong:
    bo = bn_o.get(r["t0"])
    if bo is not None: gap_at_wrong.append(abs(r["cb_open"]-bo))

out = {
    "n_joined": n,
    "miss_open": miss_open, "miss_settle": miss_settle,
    "oracle_up_frac": round(sum(r["oracle_up"] for r in rows)/n, 4),
    "cb_up_frac_strict": round(sum(r["dir_strict"] for r in rows)/n, 4),
    "cb_up_frac_ge": round(sum(r["dir_ge"] for r in rows)/n, 4),
    "agreement": {
        "strict_pct": round(100*agree_strict/n, 3), "strict_n": agree_strict,
        "ge_pct": round(100*agree_ge/n, 3), "ge_n": agree_ge,
        "disagree_strict": n-agree_strict, "disagree_ge": n-agree_ge,
    },
    "bps_table": table,
    "confident_leader": {
        "definition": "|cb_move| >= clearMargin(=max($15,0.03%)) — site shows a firm Up/Down verdict",
        "n_confident": len(conf),
        "n_confident_wrong": len(conf_wrong),
        "confident_wrong_pct": round(100*len(conf_wrong)/len(conf),3) if conf else None,
        "confident_wrong_by_bps": cw_by_bucket,
    },
    "live_leads_no_deadzone": {
        "note": "live.html line 840 shows Up/Down leads for ANY nonzero move (no clearMargin band)",
        "n_nonzero": len(allsign),
        "n_wrong": len(allsign_wrong),
        "wrong_pct": round(100*len(allsign_wrong)/len(allsign),3) if allsign else None,
    },
    "ties": {"n": len(ties), "oracle_up_of_ties": ties_oracle_up},
    "cb_vs_binance_gap_usd": gap_stats,
    "gap_at_confident_wrong": {
        "n": len(gap_at_wrong),
        "median": round(sorted(gap_at_wrong)[len(gap_at_wrong)//2],2) if gap_at_wrong else None,
        "max": round(max(gap_at_wrong),2) if gap_at_wrong else None,
    },
}
print(json.dumps(out, indent=2))
json.dump({"summary":out,"rows":rows}, open("/Users/sgonzalez/btc5m-paper-trader/research/2026-07-13-price-to-beat/work/divergence/results.json","w"), indent=1)
