import json, time, urllib.request, urllib.error, sys

SCRATCH = "/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad"
HOSTS = ["https://data-api.binance.vision", "https://api.binance.com"]

end_ms = int(time.time() // 300 * 300) * 1000          # align to 5m boundary (now)
start_ms = end_ms - 60 * 86400 * 1000                  # 60 days back

def fetch(host, start):
    url = f"{host}/api/v3/klines?symbol=BTCUSDT&interval=5m&limit=1000&startTime={start}&endTime={end_ms}"
    req = urllib.request.Request(url, headers={"User-Agent": "research/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

host_used = None
rows = {}
cur = start_ms
errors = []
while cur < end_ms:
    got = None
    for host in ([host_used] if host_used else HOSTS):
        try:
            got = fetch(host, cur)
            host_used = host
            break
        except Exception as e:
            errors.append(f"{host} @ {cur}: {e}")
            time.sleep(1.0)
    if got is None:
        # try both hosts once more before giving up
        print("FATAL: both hosts failed", file=sys.stderr)
        print("\n".join(errors[-4:]), file=sys.stderr)
        sys.exit(2)
    if not got:
        break
    for k in got:
        t = int(k[0]) // 1000
        if t * 1000 >= end_ms:
            continue
        rows[t] = (float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5]))
    cur = int(got[-1][0]) + 300000
    time.sleep(0.2)

ts = sorted(rows.keys())
out = {
    "t": ts,
    "o": [rows[t][0] for t in ts],
    "h": [rows[t][1] for t in ts],
    "l": [rows[t][2] for t in ts],
    "c": [rows[t][3] for t in ts],
    "v": [rows[t][4] for t in ts],
}
path = SCRATCH + "/data/bn5m.json"
with open(path, "w") as f:
    json.dump(out, f)

# gap report
gaps = []
for a, b in zip(ts, ts[1:]):
    if b - a != 300:
        gaps.append((a, b, (b - a) // 300 - 1))
expected = (ts[-1] - ts[0]) // 300 + 1 if ts else 0
print(json.dumps({
    "host": host_used, "rows": len(ts),
    "first": ts[0] if ts else None, "last": ts[-1] if ts else None,
    "first_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts[0])) if ts else None,
    "last_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts[-1])) if ts else None,
    "expected": expected, "missing": expected - len(ts),
    "gaps": gaps[:20], "n_gaps": len(gaps),
    "n_fetch_errors": len(errors),
}))
