#!/usr/bin/env python3
"""Harvest Coinbase Exchange public candles for BTC-USD into columnar JSON."""
import json, time, sys, urllib.request, urllib.error

SCRATCH = "/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad"
BASE = "https://api.exchange.coinbase.com/products/BTC-USD/candles"
UA = {"User-Agent": "paper-research/1.0"}

def fetch(gran, start, end):
    url = f"{BASE}?granularity={gran}&start={start}&end={end}"
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())

def harvest(gran, days, out_name):
    now = int(time.time())
    end_all = now - (now % gran)           # align to granularity
    start_all = end_all - days * 86400
    step = gran * 300                       # max 300 rows per request
    rows = {}                               # t -> row
    errors = 0
    w0 = start_all
    nreq = 0
    while w0 < end_all:
        w1 = min(w0 + step, end_all)
        got = None
        for attempt in (1, 2):
            try:
                got = fetch(gran, w0, w1)
                break
            except Exception as e:
                sys.stderr.write(f"[{out_name}] window {w0}-{w1} attempt {attempt} error: {e}\n")
                time.sleep(1.0)
        if got is None:
            errors += 1
        else:
            for row in got:   # [t, low, high, open, close, vol]
                t = int(row[0])
                if start_all <= t < end_all:
                    rows[t] = row
        nreq += 1
        time.sleep(0.15)
        w0 = w1
    ts = sorted(rows)
    out = {"t": [], "o": [], "h": [], "l": [], "c": [], "v": []}
    for t in ts:
        r = rows[t]
        out["t"].append(t)
        out["l"].append(r[1]); out["h"].append(r[2])
        out["o"].append(r[3]); out["c"].append(r[4]); out["v"].append(r[5])
    path = f"{SCRATCH}/data/{out_name}"
    with open(path, "w") as f:
        json.dump(out, f)
    # gap analysis: missing intervals between first and last t
    gaps = 0
    missing = 0
    for i in range(1, len(ts)):
        d = ts[i] - ts[i-1]
        if d > gran:
            gaps += 1
            missing += d // gran - 1
    span = (ts[-1] - ts[0]) // gran + 1 if ts else 0
    rep = {"file": out_name, "granularity": gran, "requests": nreq,
           "failed_windows": errors, "rows": len(ts),
           "expected_in_span": span, "gap_runs": gaps, "missing_intervals": missing,
           "first_t": ts[0] if ts else None, "last_t": ts[-1] if ts else None}
    print(json.dumps(rep))
    return rep

if __name__ == "__main__":
    reports = []
    reports.append(harvest(300, 60, "cb5m.json"))
    reports.append(harvest(60, 14, "cb1m.json"))
    reports.append(harvest(86400, 365, "cbdaily.json"))
    with open(f"{SCRATCH}/work/harvest-cb/report.json", "w") as f:
        json.dump(reports, f, indent=1)
