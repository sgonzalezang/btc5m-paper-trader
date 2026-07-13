#!/usr/bin/env python3
"""RESOLUTION-SOURCE AUDIT: fetch gamma-api metadata for a spread of
btc-updown-5m markets and record the resolution source, exact rule text,
tie convention, and boundary-timing fields. STDLIB ONLY."""
import json, time, urllib.request, urllib.parse, re
from datetime import datetime, timezone

GAMMA = "https://gamma-api.polymarket.com"
IVL = 300

def fetch(slug):
    url = f"{GAMMA}/events?slug={urllib.parse.quote(slug)}"
    req = urllib.request.Request(url, headers={"User-Agent":"audit/1.0","Accept":"application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        if r.status != 200: return None
        j = json.loads(r.read().decode())
    return j[0] if isinstance(j,list) and j else None

def iso_s(s):
    if not s: return None
    s = s.replace("Z","+00:00")
    try: return int(datetime.fromisoformat(s).timestamp())
    except Exception: return None

# --- build a spread of t0s across days & hours ---
now = int(time.time())
recent0 = (now//IVL)*IVL
t0s = set()
# recent: last ~6h, every 20 min, plus a few closed ones just behind
for k in range(2, 40):
    t0s.add(recent0 - k*IVL*4)   # every 20 min back ~13h
# pm_res_3d span: spread across the 3-day Jul7-10 window, varied hours
res = json.load(open("/Users/sgonzalez/btc5m-paper-trader/research/2026-07-10-edge-hunt/data/pm_res_3d.json"))
res_t0 = [r[0] for r in res]
step = max(1, len(res_t0)//25)
for i in range(0, len(res_t0), step):
    t0s.add(res_t0[i])
# a couple older probes to test data availability / consistency
for extra in (res_t0[0], res_t0[-1], recent0-IVL, recent0-2*IVL):
    t0s.add(extra)

t0s = sorted(t0s)
print(f"probing {len(t0s)} slugs")

rows = []
CANON_SRC = "https://data.chain.link/streams/btc-usd"
for i,t0 in enumerate(t0s):
    slug = f"btc-updown-5m-{t0}"
    try:
        ev = fetch(slug)
    except Exception as e:
        rows.append(dict(t0=t0, slug=slug, ok=False, err=str(e)[:120]));
        time.sleep(0.4); continue
    if not ev or not ev.get("markets"):
        rows.append(dict(t0=t0, slug=slug, ok=False, err="no event/market"))
        time.sleep(0.35); continue
    m = ev["markets"][0]
    desc = m.get("description") or ev.get("description") or ""
    title = m.get("question") or ev.get("title") or ""
    endS = iso_s(m.get("endDate"))
    startS = iso_s(m.get("startDate"))
    umaS = iso_s(m.get("umaEndDate"))
    row = dict(
        t0=t0, slug=slug, ok=True,
        title=title,
        resolutionSource=m.get("resolutionSource"),
        ev_resolutionSource=ev.get("resolutionSource"),
        src_is_chainlink=(CANON_SRC in (m.get("resolutionSource") or "")) or ("chain.link" in (desc.lower())),
        desc=desc,
        outcomes=m.get("outcomes"),
        outcomePrices=m.get("outcomePrices"),
        closed=m.get("closed"), umaResolutionStatus=m.get("umaResolutionStatus"),
        secondsDelay=m.get("secondsDelay") if "secondsDelay" in m else ev.get("secondsDelay"),
        endDate=m.get("endDate"), endS=endS, end_minus_t0=(endS-t0) if endS else None,
        startDate=m.get("startDate"), startS=startS, start_minus_t0=(startS-t0) if startS else None,
        umaEndDate=m.get("umaEndDate"), umaS=umaS, uma_minus_t0=(umaS-t0) if umaS else None,
        # rule-text flags
        has_ge_rule=("greater than or equal to" in desc.lower()),
        has_up_word=("resolve to \"up\"" in desc.lower() or "resolve to up" in desc.lower()),
        mentions_coinbase=("coinbase" in desc.lower()),
        mentions_notspot=("not according to other sources or spot markets" in desc.lower()),
    )
    rows.append(row)
    if i % 10 == 0: print(f"  {i}/{len(t0s)} {slug} ok={row['ok']} chainlink={row['src_is_chainlink']}")
    time.sleep(0.3)

json.dump(rows, open("meta_rows.json","w"), indent=1)
ok = [r for r in rows if r.get("ok")]
print(f"\nfetched ok: {len(ok)}/{len(rows)}")
print("done")
