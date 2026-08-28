"""Harvest 30 days of btc-updown-5m history: outcome + in-interval price path
per market (gamma + CLOB prices-history), plus Coinbase 1-min candles.

Writes JSONL, one row per market:
  {t0, slug, outcome: "up"|"down", upTok, path: [[secs_into_interval, price], ...]}
and candles.jsonl: [t, open, high, low, close, vol] per minute.

Polite: ~3 req/s, exponential backoff on 429/5xx, resumable (skips t0s already
on disk). Read-only w.r.t. trading. Run with the btc5m venv python (VPN-pinned).
"""
import json, os, sys, time, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
OUT  = os.path.join(HERE, "data", "markets.jsonl")
CAND = os.path.join(HERE, "data", "candles.jsonl")
DAYS = 30
UA   = {"User-Agent": "pm-research/1.0"}

def get(url, tries=5):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            return json.load(urllib.request.urlopen(req, timeout=20))
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(2 ** i); continue
            raise
        except Exception:
            time.sleep(2 ** i)
    return None

def have():
    s = set()
    if os.path.exists(OUT):
        for ln in open(OUT, encoding="utf-8"):
            try: s.add(json.loads(ln)["t0"])
            except Exception: pass
    return s

def main():
    now = int(time.time()) // 300 * 300
    start = now - DAYS * 86400
    done = have()
    todo = [t for t in range(start, now - 600, 300) if t not in done]
    print(f"todo {len(todo)} markets ({len(done)} already on disk)", flush=True)
    n_ok = n_miss = 0
    f = open(OUT, "a", encoding="utf-8")
    for i, t0 in enumerate(todo):
        slug = f"btc-updown-5m-{t0}"
        ev = get(f"https://gamma-api.polymarket.com/events?slug={slug}")
        row = None
        if ev:
            try:
                mk = ev[0]["markets"][0]
                oc = json.loads(mk["outcomePrices"]) if isinstance(mk.get("outcomePrices"), str) else mk.get("outcomePrices")
                toks = json.loads(mk["clobTokenIds"]) if isinstance(mk.get("clobTokenIds"), str) else mk.get("clobTokenIds")
                if mk.get("closed") and oc and toks:
                    outcome = "up" if float(oc[0]) > 0.5 else "down"
                    h = get(f"https://clob.polymarket.com/prices-history?market={toks[0]}&startTs={t0-90}&endTs={t0+360}&fidelity=1")
                    path = [[p["t"] - t0, round(p["p"], 4)] for p in (h or {}).get("history", [])]
                    row = {"t0": t0, "slug": slug, "outcome": outcome, "upTok": toks[0], "path": path}
            except Exception:
                pass
        if row:
            f.write(json.dumps(row) + "\n"); n_ok += 1
        else:
            f.write(json.dumps({"t0": t0, "slug": slug, "miss": True}) + "\n"); n_miss += 1
        if i % 25 == 0:
            f.flush()
            print(f"[{i}/{len(todo)}] ok={n_ok} miss={n_miss}", flush=True)
        time.sleep(0.34)
    f.close()
    print(f"markets done: ok={n_ok} miss={n_miss}", flush=True)

    # Coinbase candles, resumable by last t on disk
    last = 0
    if os.path.exists(CAND):
        for ln in open(CAND, encoding="utf-8"):
            try: last = max(last, json.loads(ln)[0])
            except Exception: pass
    lo = max(start - 3600, last + 60) if last else start - 3600
    fc = open(CAND, "a", encoding="utf-8")
    t = lo
    while t < now:
        hi = min(t + 300 * 60, now)
        c = get(f"https://api.exchange.coinbase.com/products/BTC-USD/candles?granularity=60&start={t}&end={hi}")
        for row in sorted(c or [], key=lambda r: r[0]):
            if row[0] > last:
                fc.write(json.dumps([row[0], row[3], row[2], row[1], row[4], row[5]]) + "\n")  # t,open,high,low,close,vol
                last = row[0]
        fc.flush()
        print(f"candles to {hi} ({(now-hi)//3600}h left)", flush=True)
        t = hi
        time.sleep(0.4)
    fc.close()
    print("ALL DONE", flush=True)

if __name__ == "__main__":
    main()
