#!/usr/bin/env python3
"""Harvest perp derivatives context: funding (Deribit), premium 5m + OI 5m (binance.vision).

Binance fapi.binance.com is georestricted from this host ("restricted location"),
so per the brief we use the allowed public mirrors instead:
  - funding: Deribit get_funding_rate_history (hourly; rate = interest_8h)
  - premium5m: data.binance.vision futures/um premiumIndexKlines 5m archives
  - oi5m: data.binance.vision futures/um daily metrics archives (5m sampling)
All GETs, >=0.15s sleep between calls.
"""
import json, time, io, zipfile, csv, sys, urllib.request, datetime as dt

SCRATCH = "/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad"
UA = {"User-Agent": "python-urllib/3 research"}
NOW = int(time.time())
report = {}

def get(url, timeout=40):
    time.sleep(0.16)
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()

def get_ok(url):
    try:
        return get(url), None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"

# ---------- 1) Funding: Deribit, ~60d hourly ----------
try:
    start_ms = (NOW - 60*86400) * 1000
    end_ms = NOW * 1000
    rows = []
    cur = start_ms
    CHUNK = 7*86400*1000  # 7d = 168 hourly records per call, well under limits
    while cur < end_ms:
        ce = min(cur + CHUNK, end_ms)
        url = ("https://www.deribit.com/api/v2/public/get_funding_rate_history"
               f"?instrument_name=BTC-PERPETUAL&start_timestamp={cur}&end_timestamp={ce}")
        body = get(url)
        res = json.loads(body).get("result", [])
        for rec in res:
            rows.append([rec["timestamp"] // 1000, rec["interest_8h"]])
        cur = ce
    # dedupe + sort
    d = {t: r for t, r in rows}
    rows = sorted([[t, r] for t, r in d.items()])
    out = {"source": "deribit get_funding_rate_history BTC-PERPETUAL (hourly samples; "
                     "rate = interest_8h, the trailing-8h funding rate). "
                     "Binance fapi georestricted from this host.",
           "rows": rows}
    with open(f"{SCRATCH}/data/funding.json", "w") as f:
        json.dump(out, f)
    report["funding"] = {"rows": len(rows),
                         "span_days": round((rows[-1][0]-rows[0][0])/86400, 1) if rows else 0}
except Exception as e:
    report["funding"] = {"error": f"{type(e).__name__}: {e}"}

# ---------- helpers for vision zips ----------
def vision_csv_rows(url):
    """Return list of csv rows (list of str) from a vision zip, or None if unavailable."""
    body, err = get_ok(url)
    if body is None:
        return None, err
    zf = zipfile.ZipFile(io.BytesIO(body))
    name = zf.namelist()[0]
    text = zf.read(name).decode()
    return list(csv.reader(io.StringIO(text))), None

# ---------- 2) Premium index klines 5m, ~60d ----------
try:
    today = dt.datetime.now(dt.timezone.utc).date()
    start_date = today - dt.timedelta(days=60)
    # months fully/partially covered before current month -> monthly zips; current month -> daily zips
    t_, o_, h_, l_, c_ = [], [], [], [], []
    errs = []
    def ingest(rows):
        for r in rows:
            if not r or not r[0].replace(".", "").isdigit():
                continue  # header line
            ts = int(r[0])
            ts = ts // 1000000 if ts > 10**14 else ts // 1000  # some archives use microseconds
            t_.append(ts); o_.append(float(r[1])); h_.append(float(r[2]))
            l_.append(float(r[3])); c_.append(float(r[4]))
    months = sorted({(d.year, d.month) for d in (start_date + dt.timedelta(days=i)
                     for i in range((today - start_date).days)) })
    for (y, m) in months:
        if (y, m) == (today.year, today.month):
            d = dt.date(y, m, 1)
            while d < today:  # daily files exist through yesterday
                url = (f"https://data.binance.vision/data/futures/um/daily/premiumIndexKlines/"
                       f"BTCUSDT/5m/BTCUSDT-5m-{d.isoformat()}.zip")
                rows, err = vision_csv_rows(url)
                if rows is None:
                    errs.append(f"{d}: {err}")
                else:
                    ingest(rows)
                d += dt.timedelta(days=1)
        else:
            url = (f"https://data.binance.vision/data/futures/um/monthly/premiumIndexKlines/"
                   f"BTCUSDT/5m/BTCUSDT-5m-{y:04d}-{m:02d}.zip")
            rows, err = vision_csv_rows(url)
            if rows is None:
                errs.append(f"{y}-{m:02d}: {err}")
            else:
                ingest(rows)
    # sort/dedupe and trim to 60d
    cutoff = NOW - 60*86400
    packed = sorted({t: (o, h, l, c) for t, o, h, l, c in zip(t_, o_, h_, l_, c_)
                     if t >= cutoff}.items())
    out = {"source": "binance.vision futures/um premiumIndexKlines BTCUSDT 5m "
                     "(monthly+daily archives; fapi georestricted). Values are premium index "
                     "(perp mark vs index, fractional).",
           "t": [p[0] for p in packed], "o": [p[1][0] for p in packed],
           "h": [p[1][1] for p in packed], "l": [p[1][2] for p in packed],
           "c": [p[1][3] for p in packed]}
    with open(f"{SCRATCH}/data/premium5m.json", "w") as f:
        json.dump(out, f)
    report["premium5m"] = {"rows": len(packed), "errors": errs,
                           "span_days": round((packed[-1][0]-packed[0][0])/86400, 1) if packed else 0}
except Exception as e:
    report["premium5m"] = {"error": f"{type(e).__name__}: {e}"}

# ---------- 3) Open interest 5m, 30d ----------
try:
    t_, oi_, oiv_ = [], [], []
    errs = []
    today = dt.datetime.now(dt.timezone.utc).date()
    for i in range(30, 0, -1):  # 30 days back through yesterday
        d = today - dt.timedelta(days=i)
        url = (f"https://data.binance.vision/data/futures/um/daily/metrics/"
               f"BTCUSDT/BTCUSDT-metrics-{d.isoformat()}.zip")
        rows, err = vision_csv_rows(url)
        if rows is None:
            errs.append(f"{d}: {err}")
            continue
        hdr = rows[0]
        idx_t = hdr.index("create_time")
        idx_oi = hdr.index("sum_open_interest")
        idx_oiv = hdr.index("sum_open_interest_value")
        for r in rows[1:]:
            if not r:
                continue
            ts = int(dt.datetime.strptime(r[idx_t], "%Y-%m-%d %H:%M:%S")
                     .replace(tzinfo=dt.timezone.utc).timestamp())
            t_.append(ts); oi_.append(float(r[idx_oi])); oiv_.append(float(r[idx_oiv]))
    packed = sorted({t: (a, b) for t, a, b in zip(t_, oi_, oiv_)}.items())
    out = {"source": "binance.vision futures/um daily metrics BTCUSDT (5m sampling; "
                     "fapi georestricted). oi = sum_open_interest (BTC), "
                     "oi_value = sum_open_interest_value (USDT).",
           "t": [p[0] for p in packed],
           "oi": [p[1][0] for p in packed],
           "oi_value": [p[1][1] for p in packed]}
    with open(f"{SCRATCH}/data/oi5m.json", "w") as f:
        json.dump(out, f)
    report["oi5m"] = {"rows": len(packed), "errors": errs,
                      "span_days": round((packed[-1][0]-packed[0][0])/86400, 1) if packed else 0}
except Exception as e:
    report["oi5m"] = {"error": f"{type(e).__name__}: {e}"}

print(json.dumps(report, indent=1))
