#!/usr/bin/env python3
"""Live 3-source snapshot at the current instant: Coinbase spot + 1m open,
Pyth latest, onchain Chainlink push feed. Demonstrates real-time fetchability
and the live $ spread between what the site shows (Coinbase) and the oracle-
tracking source (Pyth). STDLIB ONLY."""
import json, time, urllib.request

BTC = "e62df6c8b4a85fe1a67db44dc12de5db330f7ac66b72dc658afedf0f4a415b43"
def j(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "x"}), timeout=15) as r:
        return json.loads(r.read().decode())

now = int(time.time()); t0 = now // 300 * 300
snap = {"now": now, "interval_t0": t0}

# Coinbase current 1m candle (open = this-minute open ~ live price to beat), and spot
try:
    cstart = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t0 - 60))
    cb = j(f"https://api.exchange.coinbase.com/products/BTC-USD/candles?granularity=60&start={cstart}")
    # rows [time,low,high,open,close,vol] newest first
    o_t0 = next((r[3] for r in cb if int(r[0]) == t0), None)
    spot = j("https://api.exchange.coinbase.com/products/BTC-USD/ticker")
    snap["coinbase_open_t0"] = o_t0
    snap["coinbase_spot"] = float(spot["price"])
except Exception as e:
    snap["coinbase_error"] = str(e)[:80]

# Pyth latest
try:
    d = j(f"https://hermes.pyth.network/v2/updates/price/latest?ids[]={BTC}")
    p = d["parsed"][0]["price"]
    snap["pyth_latest"] = round(int(p["price"]) * 10 ** p["expo"], 2)
    snap["pyth_publish_time"] = int(p["publish_time"])
    snap["pyth_age_s"] = now - int(p["publish_time"])
except Exception as e:
    snap["pyth_error"] = str(e)[:80]

# Onchain Chainlink push feed (different product from Data Streams)
try:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_call",
                       "params": [{"to": "0xF4030086522a5bEEa4988F8cA5B36dbC97BeE88c",
                                   "data": "0xfeaf968c"}, "latest"]}).encode()
    req = urllib.request.Request("https://ethereum-rpc.publicnode.com", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        out = json.loads(r.read().decode())["result"][2:]
    words = [out[i:i + 64] for i in range(0, len(out), 64)]
    snap["chainlink_onchain_push"] = int(words[1], 16) / 1e8
    snap["chainlink_onchain_updatedAt"] = int(words[3], 16)
    snap["chainlink_onchain_age_s"] = now - int(words[3], 16)
except Exception as e:
    snap["chainlink_error"] = str(e)[:80]

if snap.get("coinbase_open_t0") and snap.get("pyth_latest"):
    snap["cb_minus_pyth_strike_usd"] = round(snap["coinbase_open_t0"] - snap["pyth_latest"], 2)
print(json.dumps(snap, indent=2))
