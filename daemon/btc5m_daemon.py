#!/usr/bin/env python3
"""24/7 paper-trading daemon for the STRICT engine of the btc5m paper trader.

Faithful port of the strict (10/10 guards, Conservative profile) engine from
index.html: same market discovery, same feed chain, same guard math, same
slippage-honest fills, same stop-loss / micro-hedge / settlement rules.
Trades are appended to a JSON ledger on disk so the lifetime return keeps
accumulating whether or not any browser tab is open.

Usage:
  btc5m_daemon.py run       # the daemon loop (LaunchAgent runs this)
  btc5m_daemon.py status    # lifetime return summary
  btc5m_daemon.py tail      # last 20 ledger events
"""
import json, os, subprocess, sys, time, urllib.request, urllib.parse
from datetime import datetime, timezone

# --- Config (mirrors the page's strict engine / Conservative profile) -----
ASSET   = {"label": "BTC", "slug": "btc-updown-5m-", "series": "btc-updown-5m",
           "q": "Bitcoin Up or Down", "cb": "BTC-USD", "bn": "BTCUSDT", "kr": "XBTUSD"}
PROF    = {"movePct": 0.10, "minMid": 0.52, "maxAsk": 0.70,
           "winLeftMax": 150, "winLeftMin": 60, "freshMs": 8000, "feedFreshMs": 15000,
           "maxSpread": 0.03, "minTopUsd": 30, "stopPct": 0.25,
           "hedgeAt": 0.95, "hedgeLeft": 45, "hedgeFrac": 0.03,
           "maxDay": float("inf"),   # day-count cap OFF at user request 2026-07-04 "for now" — was 12
           "dayLossPct": 10}
STAKE, BANK, SLIP_C = 20.0, 1000.0, 1.0        # $ stake, $ bankroll, ¢ slippage
IVL      = 300                                  # market interval, seconds
TICK_S   = 4                                    # active polling cadence
GAMMA    = "https://gamma-api.polymarket.com"
CLOB     = "https://clob.polymarket.com"
DATA_DIR = os.path.expanduser("~/.btc5m")
LEDGER   = os.path.join(DATA_DIR, "ledger.json")
LOGFILE  = os.path.join(DATA_DIR, "daemon.log")
REPO_DIR = os.path.expanduser("~/btc5m-paper-trader")
PUB_FILE = os.path.join(REPO_DIR, "lifetime.json")

# --- Small utils -----------------------------------------------------------
def now_ms():  return int(time.time() * 1000)
def num(x):
    if x is None or x == "": return None
    try: return float(x)
    except (TypeError, ValueError): return None
def p01(p): return p if (p is not None and 0 <= p <= 1) else None
def arr(x):
    if isinstance(x, list): return x
    if isinstance(x, str):
        try:
            a = json.loads(x)
            return a if isinstance(a, list) else None
        except ValueError: return None
    return None

def log(msg):
    line = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ ") + msg
    print(line, flush=True)

def http_json(url, timeout=11):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "btc5m-paper-daemon/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None

# --- Ledger ----------------------------------------------------------------
def ledger_load():
    try:
        with open(LEDGER) as f: L = json.load(f)
        if not isinstance(L.get("trades"), list): raise ValueError
        return L
    except Exception:
        return {"version": 1, "startedAt": now_ms(), "bank": BANK, "trades": []}

def ledger_save(L):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = LEDGER + ".tmp"
    with open(tmp, "w") as f: json.dump(L, f, indent=1)
    os.replace(tmp, LEDGER)

def open_trade(L):   return next((t for t in L["trades"] if t["status"] == "open"), None)
def trade_for(L, t0): return next((t for t in L["trades"] if t["t0"] == t0), None)
def day_key(ms):
    d = datetime.fromtimestamp(ms / 1000, timezone.utc)
    return f"{d.year}-{d.month}-{d.day}"
def day_stats(L):
    k, n, pnl = day_key(now_ms()), 0, 0.0
    for t in L["trades"]:
        if day_key(t["at"]) == k:
            n += 1
            if isinstance(t.get("pnl"), (int, float)): pnl += t["pnl"]
    return n, pnl

# --- Market discovery (Gamma) ----------------------------------------------
def parse_event(ev):
    if not ev or not isinstance(ev.get("markets"), list) or not ev["markets"]: return None
    mk = ev["markets"][0]
    toks   = arr(mk.get("clobTokenIds")) or []
    outs   = arr(mk.get("outcomes")) or []
    prices = arr(mk.get("outcomePrices")) or []
    i_up = next((i for i, o in enumerate(outs) if "up" in str(o).lower()), 0)
    i_dn = 1 if i_up == 0 else 0
    b0, a0 = p01(num(mk.get("bestBid"))), p01(num(mk.get("bestAsk")))
    up_bid, up_ask = b0, a0
    if i_up != 0:
        up_bid = round(1 - a0, 4) if a0 is not None else None
        up_ask = round(1 - b0, 4) if b0 is not None else None
    return {"slug": str(ev.get("slug") or ""),
            "closed": mk.get("closed") is True or ev.get("closed") is True,
            "resolved": "resolved" in str(mk.get("umaResolutionStatus") or "").lower(),
            "tokUp": str(toks[i_up]) if len(toks) > i_up and toks[i_up] is not None else None,
            "tokDown": str(toks[i_dn]) if len(toks) > i_dn and toks[i_dn] is not None else None,
            "pUp": p01(num(prices[i_up])) if len(prices) > i_up else None,
            "pDown": p01(num(prices[i_dn])) if len(prices) > i_dn else None,
            "upBid": up_bid, "upAsk": up_ask}

def winner_of(p):
    if not p or (not p["closed"] and not p["resolved"]): return None
    if p["pUp"] is not None and p["pUp"] >= 0.99: return "up"
    if p["pDown"] is not None and p["pDown"] >= 0.99: return "down"
    return None

def gamma_by_slug(slug):
    j = http_json(GAMMA + "/events?slug=" + urllib.parse.quote(slug))
    return j[0] if isinstance(j, list) and j else None

_slug_off, _sweep_at = 0, 0.0
def sweep(now_sec):
    for get in (
        lambda: http_json(GAMMA + "/events?series_slug=" + ASSET["series"] + "&closed=false&limit=25"),
        lambda: (lambda j: j.get("events") if isinstance(j, dict) else None)(
            http_json(GAMMA + "/public-search?q=" + urllib.parse.quote(ASSET["q"]) + "&limit_per_type=40&events_status=active")),
    ):
        evs = get()
        if not isinstance(evs, list): continue
        for e in evs:
            sl = str((e or {}).get("slug") or "")
            if not sl.startswith(ASSET["slug"]): continue
            try: ts = int(sl[len(ASSET["slug"]):])
            except ValueError: continue
            if ts <= now_sec < ts + IVL: return e, ts
    return None, None

def find_market(t0):
    global _slug_off, _sweep_at
    raw = gamma_by_slug(ASSET["slug"] + str(t0 + _slug_off))
    if raw: return parse_event(raw)
    if time.time() - _sweep_at > 30:
        _sweep_at = time.time()
        ev, ts = sweep(int(time.time()))
        if ev:
            _slug_off = ts - t0
            return parse_event(ev)
    return None

# --- CLOB book ---------------------------------------------------------------
def book(token_id):
    j = http_json(CLOB + "/book?token_id=" + urllib.parse.quote(token_id))
    if not j or (not isinstance(j.get("asks"), list) and not isinstance(j.get("bids"), list)): return None
    ask = ask_sz = bid = bid_sz = None
    for l in j.get("asks") or []:
        p, s = num(l.get("price")), num(l.get("size"))
        if p is None or s is None: continue
        if ask is None or p < ask: ask, ask_sz = p, s
    for l in j.get("bids") or []:
        p, s = num(l.get("price")), num(l.get("size"))
        if p is None or s is None: continue
        if bid is None or p > bid: bid, bid_sz = p, s
    if ask is None and bid is None: return None
    return {"bid": bid, "ask": ask,
            "topAskUsd": ask * ask_sz if ask is not None else None,
            "mirrorTopUsd": (1 - bid) * bid_sz if bid is not None else None, "at": now_ms()}

def mirror(b):
    if not b: return None
    return {"bid": round(1 - b["ask"], 4) if b["ask"] is not None else None,
            "ask": round(1 - b["bid"], 4) if b["bid"] is not None else None,
            "topAskUsd": b["mirrorTopUsd"], "mirrorTopUsd": b["topAskUsd"], "at": b["at"]}

# --- Price feed: 1-min candles → open of t0 + latest ------------------------
def _scan(rows, t0, t_of, o_of, c_of):
    open_, last, last_t, pc, pc_t = None, None, -1, None, -1
    for r in rows:
        if not isinstance(r, list) or len(r) < 5: continue
        t, o, c = t_of(r), o_of(r), c_of(r)
        if t is None: continue
        if t == t0 and o is not None: open_ = o
        if t < t0 and t > pc_t and c is not None: pc_t, pc = t, c
        if t > last_t and c is not None: last_t, last = t, c
    if open_ is None and pc is not None: open_ = pc
    return None if last is None else {"open": open_, "last": last}

def feed_coinbase(t0):
    start = datetime.fromtimestamp(t0 - 120, timezone.utc).isoformat()
    end   = datetime.fromtimestamp(time.time() + 60, timezone.utc).isoformat()
    j = http_json("https://api.exchange.coinbase.com/products/" + ASSET["cb"]
                  + "/candles?granularity=60&start=" + urllib.parse.quote(start)
                  + "&end=" + urllib.parse.quote(end))
    return _scan(j, t0, lambda r: num(r[0]), lambda r: num(r[3]), lambda r: num(r[4])) if isinstance(j, list) else None

def feed_binance(t0):
    j = http_json("https://data-api.binance.vision/api/v3/klines?symbol=" + ASSET["bn"]
                  + "&interval=1m&startTime=" + str((t0 - 120) * 1000) + "&limit=12")
    return _scan(j, t0, lambda r: (num(r[0]) or 0) // 1000, lambda r: num(r[1]), lambda r: num(r[4])) if isinstance(j, list) else None

def feed_kraken(t0):
    j = http_json("https://api.kraken.com/0/public/OHLC?pair=" + ASSET["kr"] + "&interval=1&since=" + str(t0 - 180))
    res = (j or {}).get("result")
    if not isinstance(res, dict): return None
    keys = [k for k in res if k != "last"]
    rows = res.get(keys[0]) if keys else None
    return _scan(rows, t0, lambda r: num(r[0]), lambda r: num(r[1]), lambda r: num(r[4])) if isinstance(rows, list) else None

FEEDS = [("Coinbase", feed_coinbase), ("Binance", feed_binance), ("Kraken", feed_kraken)]
_feed_idx = None
def feed_tick(feed, t0):
    global _feed_idx
    if feed.get("t0") != t0:
        feed.update({"open": None, "last": None, "at": 0, "t0": t0})
    order = ([_feed_idx] if _feed_idx is not None else []) + [i for i in range(len(FEEDS)) if i != _feed_idx]
    for i in order:
        key, fn = FEEDS[i]
        try: r = fn(t0)
        except Exception: r = None
        if r and r["last"] is not None:
            _feed_idx = i
            feed["src"] = key
            if r["open"] is not None: feed["open"] = r["open"]
            feed["last"], feed["at"] = r["last"], now_ms()
            return

# --- The 10 guards (strict: all must pass) -----------------------------------
def quote_for(mkt, side):
    b = mkt.get("bookUp") if side == "up" else mkt.get("bookDown")
    if b and (b["bid"] is not None or b["ask"] is not None):
        return {"bid": b["bid"], "ask": b["ask"], "top": b["topAskUsd"], "at": b["at"]}
    if mkt.get("upBid") is not None or mkt.get("upAsk") is not None:
        if side == "up":
            return {"bid": mkt["upBid"], "ask": mkt["upAsk"], "top": None, "at": mkt["gAt"]}
        return {"bid": round(1 - mkt["upAsk"], 4) if mkt["upAsk"] is not None else None,
                "ask": round(1 - mkt["upBid"], 4) if mkt["upBid"] is not None else None,
                "top": None, "at": mkt["gAt"]}
    return None

def evaluate(L, mkt, feed, prev_quote, t_ms):
    now_sec = t_ms // 1000
    left  = mkt["t1"] - now_sec if mkt else None
    delta = (feed["last"] - feed["open"]) if (feed.get("open") is not None and feed.get("last") is not None) else None
    side  = None if (delta is None or delta == 0) else ("up" if delta > 0 else "down")
    q     = quote_for(mkt, side) if side and mkt else None
    mid    = (q["bid"] + q["ask"]) / 2 if (q and q["bid"] is not None and q["ask"] is not None) else None
    spread = (q["ask"] - q["bid"]) if (q and q["bid"] is not None and q["ask"] is not None) else None
    day_n, day_pnl = day_stats(L)
    loss_cap = BANK * PROF["dayLossPct"] / 100
    op, dup  = open_trade(L), (trade_for(L, mkt["t0"]) if mkt else None)
    usd_thr  = feed["open"] * PROF["movePct"] / 100 if feed.get("open") is not None else None
    stable = bool(prev_quote and side and prev_quote["side"] == side and q and q["ask"] is not None
                  and prev_quote["ask"] is not None and abs(q["ask"] - prev_quote["ask"]) <= 0.15)
    checks = [
        ("market",  bool(mkt and mkt.get("ev") and not mkt.get("evClosed"))),
        ("window",  left is not None and PROF["winLeftMin"] <= left <= PROF["winLeftMax"]),
        ("move",    delta is not None and usd_thr is not None and abs(delta) >= usd_thr),
        ("skew",    mid is not None and mid >= PROF["minMid"]),
        ("ask",     bool(q and q["ask"] is not None and q["ask"] <= PROF["maxAsk"])),
        ("spread",  spread is not None and spread <= PROF["maxSpread"] + 1e-9),
        ("fresh",   bool(q and (t_ms - q["at"]) <= PROF["freshMs"] and feed.get("at")
                         and (t_ms - feed["at"]) <= PROF["feedFreshMs"])),
        ("stable",  stable),
        ("depth",   bool(q and q["top"] is not None and q["top"] >= PROF["minTopUsd"])),
        ("caps",    (not op) and (not dup) and day_n < PROF["maxDay"] and day_pnl > -loss_cap),
    ]
    pass_count = sum(1 for _, ok in checks if ok)
    can_fill = bool(q and q["ask"] is not None and left is not None and left > 0
                    and not op and not dup and day_n < PROF["maxDay"] and day_pnl > -loss_cap)
    return {"side": side, "delta": delta, "q": q, "left": left, "checks": checks,
            "passCount": pass_count, "enter": pass_count == 10 and can_fill}

# --- Paper execution ---------------------------------------------------------
def paper_enter(L, mkt, feed, ev):
    slip = SLIP_C / 100
    px = min(0.99, round(ev["q"]["ask"] + slip, 4))
    tr = {"at": now_ms(), "t0": mkt["t0"], "t1": mkt["t1"], "slug": mkt["slug"],
          "profile": "conservative", "asset": "BTC", "eng": "strict",
          "pass": ev["passCount"], "need": 10, "side": ev["side"], "entry": px,
          "ask": ev["q"]["ask"], "slip": SLIP_C, "stake": STAKE,
          "shares": round(STAKE / px, 4), "btcOpen": feed["open"], "btcEntry": feed["last"],
          "btcClose": None, "feed": feed.get("src"), "status": "open",
          "hedge": None, "pnl": None, "result": None, "settledBy": None}
    L["trades"].insert(0, tr)
    ledger_save(L)
    log(f"ENTER {tr['side'].upper()} @ {px*100:.1f}c (10/10 guards, ask {ev['q']['ask']*100:.0f}c+{SLIP_C:.0f}c) "
        f"- ${STAKE:.0f} - delta {'+' if ev['delta'] >= 0 else '-'}${abs(ev['delta']):.2f}")

def manage_open(L, mkt, feed, t_ms):
    tr = open_trade(L)
    if not tr: return
    now_sec = t_ms // 1000
    if now_sec >= tr["t1"]:
        tr["status"] = "pending"
        if feed.get("t0") == tr["t0"] and feed.get("last") is not None: tr["btcClose"] = feed["last"]
        ledger_save(L)
        log(f"interval closed - {tr['side'].upper()} awaiting resolution")
        return
    if not mkt or mkt["t0"] != tr["t0"]: return
    q = quote_for(mkt, tr["side"])
    # stop-loss: BTC retraces stopPct% of entry price against the position
    if feed.get("last") is not None and tr["btcEntry"] is not None and q and q["bid"] is not None:
        adverse = (tr["btcEntry"] - feed["last"]) if tr["side"] == "up" else (feed["last"] - tr["btcEntry"])
        if adverse >= tr["btcEntry"] * PROF["stopPct"] / 100:
            pnl = tr["shares"] * q["bid"] - tr["stake"]
            if tr["hedge"]:
                hb = max(0.01, 1 - (q["ask"] if q["ask"] is not None else q["bid"]))
                pnl += tr["hedge"]["shares"] * hb - tr["hedge"]["stake"]
            tr.update(pnl=round(pnl, 2), result="stopped", status="settled", settledBy="stop-loss")
            ledger_save(L)
            log(f"STOP-LOSS - exited {tr['side'].upper()} at {q['bid']*100:.0f}c bid - P&L {tr['pnl']:+.2f}")
            return
    # micro-hedge when our side goes to an extreme late
    if not tr["hedge"] and q and q["bid"] is not None:
        left = tr["t1"] - now_sec
        if q["bid"] >= PROF["hedgeAt"] and left <= PROF["hedgeLeft"]:
            hstake = round(max(1, tr["stake"] * PROF["hedgeFrac"]), 2)
            hpx = max(0.01, min(0.99, round(1 - q["bid"] + SLIP_C / 100, 4)))
            tr["hedge"] = {"stake": hstake, "px": hpx, "shares": round(hstake / hpx, 4), "at": t_ms}
            ledger_save(L)
            log(f"HEDGE - bought {'DOWN' if tr['side'] == 'up' else 'UP'} ${hstake} @ {hpx*100:.0f}c ({left}s left)")

def apply_settle(L, tr, winner, by):
    pnl = (tr["shares"] - tr["stake"]) if tr["side"] == winner else -tr["stake"]
    if tr["hedge"]:
        pnl += (tr["hedge"]["shares"] - tr["hedge"]["stake"]) if winner != tr["side"] else -tr["hedge"]["stake"]
    tr.update(pnl=round(pnl, 2), result="win" if tr["side"] == winner else "loss",
              status="settled", settledBy=by)
    ledger_save(L)
    log(f"{'WIN' if tr['result'] == 'win' else 'LOSS'} {tr['side'].upper()} settled ({by}) - P&L {tr['pnl']:+.2f}")

_res_at = 0.0
def settle_pending(L):
    global _res_at
    pend = [t for t in L["trades"] if t["status"] == "pending"]
    if not pend or time.time() - _res_at < 8: return
    _res_at = time.time()
    cache = {}
    for tr in pend:
        if tr["slug"] not in cache:
            try: cache[tr["slug"]] = parse_event(gamma_by_slug(tr["slug"]))
            except Exception: cache[tr["slug"]] = None
        w = winner_of(cache[tr["slug"]])
        if w:
            apply_settle(L, tr, w, "polymarket")
            continue
        age = time.time() - tr["t1"]
        if age > 180 and tr["btcOpen"] is not None and tr["btcClose"] is not None \
                and abs(tr["btcClose"] - tr["btcOpen"]) >= 2:
            apply_settle(L, tr, "up" if tr["btcClose"] > tr["btcOpen"] else "down", "feed (provisional)")
        elif age > 900:
            tr.update(status="settled", result="unknown", pnl=None, settledBy="unresolved")
            ledger_save(L)
            log(f"could not resolve {tr['slug']} - marked unsettled (excluded from P&L)")

# --- Publish lifetime results to the website (GitHub Pages) -------------------
def summarize(L):
    settled = [t for t in L["trades"] if t["status"] == "settled" and isinstance(t.get("pnl"), (int, float))]
    wins    = [t for t in settled if t["result"] == "win"]
    losses  = [t for t in settled if t["result"] == "loss"]
    stopped = [t for t in settled if t["result"] == "stopped"]
    unknown = [t for t in L["trades"] if t.get("result") == "unknown"]
    live    = [t for t in L["trades"] if t["status"] in ("open", "pending")]
    pnl, staked = sum(t["pnl"] for t in settled), sum(t["stake"] for t in settled)
    n = len(wins) + len(losses)
    keep = ("at", "t0", "side", "entry", "stake", "status", "result", "pnl", "settledBy", "slug")
    return {"engine": "strict", "profile": "conservative", "asset": "BTC",
            "startedAt": L["startedAt"], "bank": BANK, "stake": STAKE,
            "settled": len(settled), "wins": len(wins), "losses": len(losses),
            "stopped": len(stopped), "unresolved": len(unknown), "liveCount": len(live),
            "winRatePct": round(100 * len(wins) / n, 1) if n else None,
            "avgEntry": round(sum(t["entry"] for t in settled) / len(settled), 4) if settled else None,
            "pnl": round(pnl, 2), "staked": round(staked, 2),
            "returnOnBankPct": round(100 * pnl / BANK, 2),
            "trades": [{k: t.get(k) for k in keep} for t in L["trades"][:40]]}

_pub_last = None      # last successfully pushed summary (JSON string, no timestamp)
_pub_at   = 0.0
def publish(L):
    """Write lifetime.json into the repo and push — only when results changed."""
    global _pub_last, _pub_at
    s = summarize(L)
    body = json.dumps(s, sort_keys=True)
    if body == _pub_last or time.time() - _pub_at < 60: return
    s["updatedAt"] = now_ms()
    try:
        with open(PUB_FILE, "w") as f: json.dump(s, f, indent=1)
        def git(*a): return subprocess.run(("/usr/bin/git", "-C", REPO_DIR) + a,
                                           capture_output=True, text=True, timeout=60)
        git("add", "lifetime.json")
        if "nothing to commit" not in git("commit", "-m", "lifetime: " + (
                f"{s['settled']} settled, P&L {s['pnl']:+.2f}")).stdout:
            r = git("push", "origin", "main")
            if r.returncode != 0:                      # racing a manual push? rebase once
                git("pull", "--rebase", "origin", "main")
                r = git("push", "origin", "main")
            if r.returncode != 0:
                log("publish push failed: " + (r.stderr or "").strip()[:200])
                _pub_at = time.time()                  # back off, retry on next change/minute
                return
        _pub_last, _pub_at = body, time.time()
        log(f"published lifetime.json ({s['settled']} settled, P&L {s['pnl']:+.2f})")
    except Exception as e:
        log(f"publish error: {e}")
        _pub_at = time.time()

# --- Main loop ----------------------------------------------------------------
def run():
    os.makedirs(DATA_DIR, exist_ok=True)
    L = ledger_load()
    if not L["trades"]: ledger_save(L)
    log(f"daemon started - strict 10/10 - Conservative - ${STAKE:.0f} stake - ${BANK:.0f} bank "
        f"- +{SLIP_C:.0f}c slip - ledger {LEDGER} ({len(L['trades'])} trades)")
    publish(L)
    mkt, feed, prev_quote = None, {"src": None, "open": None, "last": None, "at": 0, "t0": None}, None
    while True:
        try:
            now_sec = int(time.time())
            t0 = now_sec // IVL * IVL
            t1 = t0 + IVL
            # Active only when it matters: a bit before/through the entry window
            # (left 150..60 → t0+150..t0+240; warm up from t0+140 for the
            # stability guard's previous tick), or whenever a trade is open/pending.
            busy = open_trade(L) or any(t["status"] == "pending" for t in L["trades"])
            in_window = t0 + 140 <= now_sec <= t0 + 245
            if not busy and not in_window:
                prev_quote = None
                publish(L)                 # flush any change the 60s throttle deferred
                nxt = (t0 + 140) if now_sec < t0 + 140 else (t1 + 140)
                time.sleep(max(2, min(nxt - time.time(), 120)))
                continue
            if not mkt or mkt["t0"] != t0:
                mkt = {"t0": t0, "t1": t1, "ev": False, "evClosed": False,
                       "slug": ASSET["slug"] + str(t0 + _slug_off), "tokUp": None, "tokDown": None,
                       "upBid": None, "upAsk": None, "pUp": None, "gAt": 0,
                       "bookUp": None, "bookDown": None}
                prev_quote = None
            p = find_market(t0)
            if p and p["slug"]:
                mkt.update(ev=True, slug=p["slug"], evClosed=p["closed"], tokUp=p["tokUp"],
                           tokDown=p["tokDown"], upBid=p["upBid"], upAsk=p["upAsk"],
                           pUp=p["pUp"], gAt=now_ms())
            feed_tick(feed, t0)
            delta = (feed["last"] - feed["open"]) if (feed["open"] is not None and feed["last"] is not None) else None
            op = open_trade(L)
            side = op["side"] if op else ("up" if (delta or 0) > 0 else "down" if (delta or 0) < 0 else None)
            if side and mkt["ev"]:
                tok = mkt["tokUp"] if side == "up" else mkt["tokDown"]
                if tok:
                    b = book(tok)
                    if b:
                        if side == "up": mkt["bookUp"], mkt["bookDown"] = b, mirror(b)
                        else:            mkt["bookDown"], mkt["bookUp"] = b, mirror(b)
            t_ms = now_ms()
            ev = evaluate(L, mkt, feed, prev_quote, t_ms)
            if ev["enter"]: paper_enter(L, mkt, feed, ev)
            manage_open(L, mkt, feed, t_ms)
            cs = "up" if (delta or 0) > 0 else "down" if (delta or 0) < 0 else None
            cq = quote_for(mkt, cs) if cs else None
            prev_quote = {"side": cs, "ask": cq["ask"]} if (cs and cq and cq["ask"] is not None) else None
            settle_pending(L)
            publish(L)
        except Exception as e:
            log(f"tick error: {e}")
        time.sleep(TICK_S)

# --- Reporting ------------------------------------------------------------------
def status():
    L = ledger_load()
    trades  = L["trades"]
    settled = [t for t in trades if t["status"] == "settled" and isinstance(t.get("pnl"), (int, float))]
    wins    = [t for t in settled if t["result"] == "win"]
    losses  = [t for t in settled if t["result"] == "loss"]
    stopped = [t for t in settled if t["result"] == "stopped"]
    unknown = [t for t in trades if t.get("result") == "unknown"]
    live    = [t for t in trades if t["status"] in ("open", "pending")]
    pnl     = sum(t["pnl"] for t in settled)
    staked  = sum(t["stake"] for t in settled)
    since   = datetime.fromtimestamp(L["startedAt"] / 1000).strftime("%b %d %Y %H:%M")
    days    = max((now_ms() - L["startedAt"]) / 86400000, 1e-9)
    print(f"BTC 5m paper trader - STRICT engine - lifetime since {since} ({days:.1f} days)")
    if not trades:
        print("no trades yet - the strict engine is picky by design (10/10 guards)")
        return
    n = len(wins) + len(losses)
    wr = 100 * len(wins) / n if n else 0.0
    avg_entry = sum(t["entry"] for t in settled) / len(settled) if settled else None
    print(f"  trades: {len(settled)} settled ({len(wins)}W / {len(losses)}L"
          + (f" / {len(stopped)} stopped" if stopped else "")
          + (f" / {len(unknown)} unresolved" if unknown else "")
          + (f", {len(live)} live" if live else "") + ")")
    if avg_entry is not None:
        print(f"  win rate: {wr:.1f}%  (breakeven = avg entry {avg_entry*100:.1f}c)")
    print(f"  lifetime P&L: {pnl:+.2f} on ${staked:.0f} staked"
          + (f"  ({100*pnl/staked:+.1f}% per $ staked)" if staked else ""))
    print(f"  return on ${BANK:.0f} bankroll: {100*pnl/BANK:+.2f}%")
    for t in live:
        print(f"  live: {t['side'].upper()} @ {t['entry']*100:.1f}c ({t['status']}) - "
              + datetime.fromtimestamp(t["at"] / 1000).strftime("%H:%M"))

def tail():
    L = ledger_load()
    for t in L["trades"][:20]:
        when = datetime.fromtimestamp(t["at"] / 1000).strftime("%b %d %H:%M")
        pnl = f"{t['pnl']:+.2f}" if isinstance(t.get("pnl"), (int, float)) else "-"
        print(f"{when}  {t['side'].upper():4} @ {t['entry']*100:5.1f}c  {t['status']:7} {t.get('result') or '':7} {pnl}")

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "run": run()
    elif cmd == "tail": tail()
    else: status()
