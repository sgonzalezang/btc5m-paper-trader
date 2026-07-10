import json, time, urllib.request, os, sys

SCRATCH = "/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad"
OUT = os.path.join(SCRATCH, "data", "eth5m.json")
os.makedirs(os.path.dirname(OUT), exist_ok=True)

GRAN = 300
now = int(time.time())
end = now - (now % GRAN)          # align to 300s
start = end - 60 * 86400          # 60 days
MAX = 300 * GRAN                  # 300 candles per request

def iso(ts):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))

rows = {}
t = start
req_count = 0
while t < end:
    e = min(t + MAX, end)
    url = (f"https://api.exchange.coinbase.com/products/ETH-USD/candles"
           f"?granularity={GRAN}&start={iso(t)}&end={iso(e)}")
    for attempt in range(5):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "research/1.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read())
            break
        except Exception as ex:
            code = getattr(ex, "code", None)
            wait = 2.0 * (attempt + 1) if code == 429 else 1.0 * (attempt + 1)
            sys.stderr.write(f"retry {attempt} {ex} {url}\n")
            time.sleep(wait)
    else:
        sys.stderr.write(f"FAILED window {iso(t)}..{iso(e)}\n")
        data = []
    # rows: [time, low, high, open, close, volume]
    for c in data:
        ts = int(c[0])
        if start <= ts < end:
            rows[ts] = c
    req_count += 1
    t = e
    time.sleep(0.2)

ts_sorted = sorted(rows.keys())
out = {
    "t": ts_sorted,
    "o": [float(rows[k][3]) for k in ts_sorted],
    "h": [float(rows[k][2]) for k in ts_sorted],
    "l": [float(rows[k][1]) for k in ts_sorted],
    "c": [float(rows[k][4]) for k in ts_sorted],
    "v": [float(rows[k][5]) for k in ts_sorted],
}
with open(OUT, "w") as f:
    json.dump(out, f)

n = len(ts_sorted)
gaps = 0
missing = 0
for i in range(1, n):
    d = ts_sorted[i] - ts_sorted[i-1]
    if d != GRAN:
        gaps += 1
        missing += d // GRAN - 1
expected = (end - start) // GRAN
print(json.dumps({
    "rows": n, "requests": req_count, "gaps": gaps, "missing_candles": missing,
    "expected": expected,
    "first": iso(ts_sorted[0]) if n else None,
    "last": iso(ts_sorted[-1]) if n else None,
}))
