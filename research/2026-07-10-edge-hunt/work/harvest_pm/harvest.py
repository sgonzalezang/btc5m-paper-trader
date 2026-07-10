#!/usr/bin/env python3
"""Harvest Polymarket btc-updown-5m ground truth (last 3 days) + sampled Up-token price paths."""
import json, time, sys, threading
import urllib.request, urllib.error
from multiprocessing.pool import ThreadPool

SCRATCH = "/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad"
DATA = SCRATCH + "/data"
UA = {"User-Agent": "Mozilla/5.0 (research; paper-trading study)"}

rate_lock = threading.Lock()
stats = {"429": 0, "err": 0, "retries": 0}

def get_json(url, tries=4):
    backoff = 0.5
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                with rate_lock: stats["429"] += 1
                time.sleep(backoff); backoff *= 2
                with rate_lock: stats["retries"] += 1
                continue
            if e.code in (404,): return None
            with rate_lock: stats["err"] += 1
            time.sleep(backoff); backoff *= 2
        except Exception:
            with rate_lock: stats["err"] += 1
            time.sleep(backoff); backoff *= 2
    return None

def fetch_market(t0):
    url = f"https://gamma-api.polymarket.com/events?slug=btc-updown-5m-{t0}"
    ev = get_json(url)
    time.sleep(0.15)  # per-thread throttle
    if not ev or not isinstance(ev, list) or not ev[0].get("markets"):
        return (t0, None)
    m = ev[0]["markets"][0]
    if not m.get("closed"):
        return (t0, None)
    try:
        outcomes = json.loads(m["outcomes"])
        prices = [float(x) for x in json.loads(m["outcomePrices"])]
        tokens = json.loads(m["clobTokenIds"])
        up_idx = outcomes.index("Up")
        up_won = 1 if prices[up_idx] > 0.5 else 0
        return (t0, {"up_won": up_won, "up_token": tokens[up_idx], "up_price": prices[up_idx]})
    except Exception as e:
        return (t0, None)

def main():
    now = int(time.time())
    end_t0 = (now // 300) * 300 - 300          # last interval that has fully ended
    start_t0 = end_t0 - 3 * 86400 + 300        # 3 days = 864 intervals
    t0s = list(range(start_t0, end_t0 + 1, 300))
    print(f"span {start_t0}..{end_t0} n={len(t0s)}", flush=True)

    with ThreadPool(12) as pool:
        results = pool.map(fetch_market, t0s)

    closed = [(t0, info) for t0, info in results if info is not None]
    closed.sort(key=lambda x: x[0])
    # sanity check outcome-order verification happened inside fetch (outcomes.index("Up"))
    res = [[t0, info["up_won"]] for t0, info in closed]
    with open(DATA + "/pm_res_3d.json", "w") as f:
        json.dump(res, f)
    n_up = sum(r[1] for r in res)
    print(f"closed markets: {len(res)} / {len(t0s)}  up_rate={n_up/max(1,len(res)):.3f}", flush=True)
    print(f"gamma stats: {stats}", flush=True)

    # every 4th market, deterministic stride
    sample = closed[::4]
    print(f"sampling {len(sample)} markets for price history", flush=True)
    out = []
    clob_429 = 0
    for i, (t0, info) in enumerate(sample):
        url = (f"https://clob.polymarket.com/prices-history?market={info['up_token']}"
               f"&startTs={t0-60}&endTs={t0+310}&fidelity=1")
        d = get_json(url)
        time.sleep(0.12)
        pts = (d or {}).get("history") or []
        pts = sorted([(p["t"], p["p"]) for p in pts if "t" in p and "p" in p])
        def nearest(target):
            best, bd = None, 1e18
            for t, p in pts:
                dd = abs(t - target)
                if dd < bd: bd, best = dd, p
            return best if bd <= 90 else None
        def last_before(target):
            best_t, best_p = None, None
            for t, p in pts:
                if t < target and (best_t is None or t > best_t):
                    best_t, best_p = t, p
            if best_t is None or (target - best_t) > 90: return None
            return best_p
        out.append({"t0": t0, "up_won": info["up_won"],
                    "p20": nearest(t0+20), "p60": nearest(t0+60),
                    "p150": nearest(t0+150), "pLast": last_before(t0+300)})
        if (i+1) % 50 == 0:
            print(f"  clob {i+1}/{len(sample)}", flush=True)
    with open(DATA + "/pm_prices_sample.json", "w") as f:
        json.dump(out, f)
    n_full = sum(1 for r in out if all(r[k] is not None for k in ("p20","p60","p150","pLast")))
    print(f"price samples: {len(out)}  fully-populated={n_full}", flush=True)
    print(f"final stats: {stats}", flush=True)

if __name__ == "__main__":
    main()
