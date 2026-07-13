#!/usr/bin/env python3
"""Build the unified dataset for the 2026-07-12 edge hunt.

Sources merged (deduped on (eng, t0)):
  - bot/state.json           btc.engines[*].trades   (Jul 8-13, live)
  - bot/archive/state-2026-07-08-pre-reset.json      (Jul 7-8, old engines)
  - research/2026-07-10-edge-hunt/data/trades.json   (Jul 7-10 snapshot; recovers
                                                      loose trades rotated out of the 600-cap)
Also extracted: measurement book, misses, and fresh Coinbase candles to cover
Jul 10 -> now (BTC 1m, BTC 5m, ETH 5m).
"""
import json, os, sys, time, datetime, urllib.request

ROOT = os.path.expanduser("~/btc5m-paper-trader")
OLD = os.path.join(ROOT, "research/2026-07-10-edge-hunt/data")
OUT = os.path.join(ROOT, "research/2026-07-12-edge-hunt/data")
os.makedirs(OUT, exist_ok=True)

def load(p):
    with open(p) as f:
        return json.load(f)

# ---------- 1. unified trades ----------
seen = {}
def add(tr, source):
    key = (tr.get("eng"), tr.get("t0"))
    if key in seen:
        # prefer the richer record (live state has guards/fillFrac etc.)
        if len(tr) > len(seen[key]):
            src0 = seen[key].get("_src")
            tr = dict(tr); tr["_src"] = src0 + "+" + source
            seen[key] = tr
        else:
            seen[key]["_src"] += "+" + source
        return
    tr = dict(tr); tr["_src"] = source
    seen[key] = tr

state = load(os.path.join(ROOT, "bot/state.json"))
for eng, e in state["btc"]["engines"].items():
    for tr in e.get("trades", []):
        add(tr, "live")

arch = load(os.path.join(ROOT, "bot/archive/state-2026-07-08-pre-reset.json"))
for eng, e in arch.get("btc", {}).get("engines", {}).items():
    for tr in e.get("trades", []):
        add(tr, "archive")

for tr in load(os.path.join(OLD, "trades.json")):
    add(tr, "research")

trades = sorted(seen.values(), key=lambda t: (t.get("t0") or 0, t.get("eng") or ""))
with open(os.path.join(OUT, "trades_unified.json"), "w") as f:
    json.dump(trades, f)
settled = [t for t in trades if t.get("result") in ("win", "loss")]
print(f"unified trades: {len(trades)} ({len(settled)} settled)")
by_eng = {}
for t in trades:
    by_eng[t["eng"]] = by_eng.get(t["eng"], 0) + 1
print(" per engine:", json.dumps(by_eng))

# ---------- 2. measurement book / misses / summary ----------
extras = {
    "measure": state["btc"]["impulse"].get("measure", []),
    "misses_btc": state["btc"].get("misses", []),
    "misses_top": state.get("misses", []),
    "summary": state.get("summary", {}),
    "lifetime": state["btc"].get("lifetime", {}),
    "equity": state["btc"].get("equity", {}),
    "ivlHist": state["btc"].get("ivlHist", []),
    "ivlHist2": state["btc"].get("ivlHist2", []),
    "impulse_cfg": {k: v for k, v in state["btc"]["impulse"].items() if k != "measure"},
    "engineCfg": state.get("engineCfg", {}),
    "feeRate": state.get("feeRate"), "gas": state.get("gas"),
    "vol": state.get("vol"), "heartbeatIso": state.get("heartbeatIso"),
}
with open(os.path.join(OUT, "state_extract.json"), "w") as f:
    json.dump(extras, f)
print(f"measure book: {len(extras['measure'])}, misses: {len(extras['misses_btc'])}+{len(extras['misses_top'])}")

# ---------- 3. candle refresh (Coinbase Exchange public API) ----------
def fetch_candles(product, granularity, start_s, end_s):
    """Coinbase Exchange API: max 300 candles per request."""
    out = []
    step = granularity * 300
    s = start_s
    while s < end_s:
        e = min(s + step, end_s)
        iso = lambda x: datetime.datetime.utcfromtimestamp(x).strftime("%Y-%m-%dT%H:%M:%SZ")
        url = (f"https://api.exchange.coinbase.com/products/{product}/candles"
               f"?granularity={granularity}&start={iso(s)}&end={iso(e)}")
        req = urllib.request.Request(url, headers={"User-Agent": "edge-hunt/1.0"})
        for attempt in range(4):
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    rows = json.load(r)
                break
            except Exception as ex:
                if attempt == 3:
                    raise
                time.sleep(1.5 * (attempt + 1))
        out.extend(rows)  # rows: [t, low, high, open, close, volume], newest first
        s = e
        time.sleep(0.25)
    return out

def merge_candles(old_path, product, granularity, out_name):
    old = load(old_path)
    have = dict(zip(old["t"], zip(old["o"], old["h"], old["l"], old["c"], old["v"])))
    last = max(old["t"])
    now = int(time.time() // granularity * granularity)
    rows = fetch_candles(product, granularity, last, now)
    added = 0
    for t, lo, hi, o, c, v in rows:
        if t not in have:
            added += 1
        have[t] = (o, hi, lo, c, v)
    ts = sorted(have)
    merged = {"t": ts,
              "o": [have[t][0] for t in ts], "h": [have[t][1] for t in ts],
              "l": [have[t][2] for t in ts], "c": [have[t][3] for t in ts],
              "v": [have[t][4] for t in ts]}
    with open(os.path.join(OUT, out_name), "w") as f:
        json.dump(merged, f)
    f2 = lambda x: datetime.datetime.utcfromtimestamp(x).strftime("%m-%d %H:%M")
    print(f"{out_name}: {len(ts)} candles ({added} new) {f2(ts[0])} -> {f2(ts[-1])}")

merge_candles(os.path.join(OLD, "cb1m.json"), "BTC-USD", 60, "cb1m.json")
merge_candles(os.path.join(OLD, "cb5m.json"), "BTC-USD", 300, "cb5m.json")
merge_candles(os.path.join(OLD, "eth5m.json"), "ETH-USD", 300, "eth5m.json")

print("DONE")
