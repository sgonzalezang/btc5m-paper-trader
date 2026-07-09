#!/usr/bin/env python3
"""
btc5m_bot.py — headless 24/7 PAPER trader for Polymarket crypto 5-minute
Up/Down markets. A faithful Python port of the browser trader: two engines
(strict 10/10, loose N/10) over one shared live data feed, all 10 guards,
slippage-honest fills, spot-retrace stop-loss, extreme-skew micro-hedge, and
settlement against Polymarket's own resolution.

READ-ONLY / SIMULATED. It never signs or places a real order — it fetches
public data (Gamma + CLOB order book + Coinbase/Binance/Kraken spot) and
records simulated fills to a local state.json ledger that resumes on restart.

Pure Python 3 standard library — no pip install required.

Usage:
  python3 btc5m_bot.py --selftest         # offline logic checks, no network
  python3 btc5m_bot.py                     # run forever (BTC, defaults)
  python3 btc5m_bot.py --asset ETH --loose 6 --stake 5 --slip 1
  python3 btc5m_bot.py --once              # one tick then exit (smoke test vs live)
  python3 btc5m_bot.py --publish           # git-push state.json to a data branch on cadence

State + logs live next to this file unless --state / --log point elsewhere.
"""
import argparse, hashlib, hmac, json, math, os, sys, time, urllib.request, urllib.parse, subprocess
from datetime import datetime, timezone

IVL = 300            # interval length, seconds
TICK_S = 4           # data refresh cadence
PM_GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"

ASSETS = {
    "BTC":  {"slug": "btc-updown-5m-",  "series": "btc-updown-5m",  "q": "Bitcoin Up or Down",  "cb": "BTC-USD",  "bn": "BTCUSDT",  "kr": "XBTUSD"},
    "ETH":  {"slug": "eth-updown-5m-",  "series": "eth-updown-5m",  "q": "Ethereum Up or Down", "cb": "ETH-USD",  "bn": "ETHUSDT",  "kr": "ETHUSD"},
    "SOL":  {"slug": "sol-updown-5m-",  "series": "sol-updown-5m",  "q": "Solana Up or Down",   "cb": "SOL-USD",  "bn": "SOLUSDT",  "kr": "SOLUSD"},
    "XRP":  {"slug": "xrp-updown-5m-",  "series": "xrp-updown-5m",  "q": "XRP Up or Down",      "cb": "XRP-USD",  "bn": "XRPUSDT",  "kr": "XRPUSD"},
    "DOGE": {"slug": "doge-updown-5m-", "series": "doge-updown-5m", "q": "Dogecoin Up or Down", "cb": "DOGE-USD", "bn": "DOGEUSDT", "kr": "XDGUSD"},
}
# ported from config/btc_5m_profiles.yaml
PROFILES = {
    "conservative": dict(label="Conservative", movePct=0.10, minMid=0.52, maxAsk=0.70,
        winLeftMax=150, winLeftMin=60, freshMs=8000, feedFreshMs=15000, maxSpread=0.03, minTopUsd=30,
        stopPct=0.25, hedgeAt=0.97, hedgeLeft=20, hedgeFrac=0.03,   # tightened 2026-07-07 (was 0.95/45):
        maxDay=math.inf,   # deep-ITM-only tail hedge — fired 60x for 1 save; now fires only when pinned
        dayLossPct=math.inf),  # daily loss stop OFF (2026-07-07): censors data during losing regimes, biases
    "aggressive": dict(label="Aggressive", movePct=0.07, minMid=0.52, maxAsk=0.70,  # analytics; add back only for live
        winLeftMax=150, winLeftMin=60, freshMs=8000, feedFreshMs=15000, maxSpread=0.03, minTopUsd=30,
        stopPct=0.30, hedgeAt=0.96, hedgeLeft=25, hedgeFrac=0.05,   # tightened 2026-07-07 (was 0.93/50)
        maxDay=math.inf,   # day-count cap OFF at user request 2026-07-04 "for now" — was 20
        dayLossPct=math.inf),  # loss stop OFF for paper analytics
}
# Engines run side by side over the same live data — a NESTED ABLATION where each
# engine differs from the previous by exactly one gate (reset 2026-07-08, all 0/0):
#  loose   — 7/10 + Stable2tick, fills <=65c. The unchanged CONTROL.
#  floor   — loose PLUS a drift floor (|move at entry| >= 0.02% of open). Tests
#            cutting the no-signal churn: on 1,150 full-market intervals, sub-2bps
#            drift holds to close only 53-56% (coin flip minus fees), yet was ~50%
#            of loose's volume. loose vs floor isolates the floor's effect.
#  band    — floor PLUS a drift ceiling (<= 0.04%). Tests adverse selection: big
#            movers still priced <=65c are cheap because the book disagrees —
#            recorded -9.86/t on >=4bps fills. floor vs band isolates the ceiling.
#  strict  — all 10 guards (fires almost never; kept as a legacy control)
# (retired 2026-07-08: capless — answered, >65c entries lose; calm — vol gate
#  formally dead, z=-1.1 on 1,057 intervals. Both recoverable from git history.)
ENGINES = ["loose", "floor", "band", "strict", "value", "fade", "reversal"]
ENGINE_CFG = {
    "loose":  dict(label="Loose",  tunable=True,  driftMin=None, driftMax=None, entryMax=0.65, volMax=None),
    "floor":  dict(label="Floor",  tunable=True,  driftMin=0.02, driftMax=None, entryMax=0.65, volMax=None),
    "band":   dict(label="Band",   tunable=True,  driftMin=0.02, driftMax=0.04, entryMax=0.65, volMax=None),
    "strict": dict(label="Strict", tunable=False, driftMin=None, driftMax=None, entryMax=None,  volMax=None),
    # value — fades a lagging book. Estimates P(the current lead survives to close)
    # from drift, seconds left, and trailing vol, and enters only when the ask is
    # below that fair value by a margin. First engine that gates on price-vs-fair-
    # value instead of a fixed cap; it should refuse most of what band takes.
    "value":  dict(label="Value",  tunable=True,  driftMin=None, driftMax=None, entryMax=None, volMax=None,
                   fvK=1.6, fvMargin=0.03),
    # fade — pure contrarian side engine. Mirrors loose's ENTER onto the opposite
    # token at its REAL book price (not a 1-p mirror), so paper pays the true
    # opposite spread and fee. Wins exactly when loose loses, which only pays
    # because loose overpays for its picks (~ -5.5c/share outcome edge: 53% win
    # at a 59c average entry); floor and band have positive edge and are NOT
    # fadeable. Paper side engine, never emitted to the live executor.
    "fade":   dict(label="Fade",   tunable=False, driftMin=None, driftMax=None, entryMax=None, volMax=None,
                   fadeOf="loose"),
    # reversal — the cross-interval overreaction engine, structurally UNLIKE the
    # others: it fires at the START of an interval, betting the OPPOSITE side of
    # the JUST-COMPLETED interval's move. Basis (10 days, 2,876 intervals): a
    # completed move >= 0.12% reverses in the next interval ~56% (buffered/
    # artifact-free; placebo p=0.000, block-bootstrap p=0.015). Enters near the
    # open where the reversal side is still ~50c — a ~7-point edge that clears
    # the worst-case fee, with margin up to ~55c. Holds to resolution (no stop:
    # the thesis IS reversion by close). Deploy-ready for the live bridge but
    # NOT in --signal-engines until forward paper data confirms the entry price.
    "reversal": dict(label="Reversal", tunable=False, driftMin=None, driftMax=None, entryMax=None, volMax=None,
                     revThr=0.12, revEntryMax=0.55, revWinMin=180, holdToClose=True),
}
VOL_WIN_MS = 600000   # trailing window for the volatility measure (10 min)
# Guards the loose engine must have GREEN regardless of its N/10 count. The
# backtest (2026-07-06, 21 honest trades) showed loose entries that skipped
# Stable2tick — filling on a jumpy/stale quote — lost badly (-26pp edge), while
# requiring it turned the engine from -168 to +9. It's also principled: never
# fill on an unstable quote. Configurable via --loose-must (comma-separated
# guard keys, or "none").
LOOSE_MANDATORY = ("Stable2tick",)
GUARD_KEYS = ("Market found", "Window", "Move>=thr", "Skew>=mid", "Ask<=cap",
              "Spread<=max", "Fresh", "Stable2tick", "Depth>=min", "RiskCaps")
GUARD_ABBR = {"Market found": "M", "Window": "W", "Move>=thr": "Δ", "Skew>=mid": "K", "Ask<=cap": "A",
              "Spread<=max": "S", "Fresh": "F", "Stable2tick": "T", "Depth>=min": "D", "RiskCaps": "R"}
# short, human labels for a red guard when explaining a "close miss" on the page
MISS_LBL = {"Market found": "no market", "Window": "wrong timing", "Move>=thr": "no move",
            "Skew>=mid": "crowd disagrees", "Ask<=cap": "priced over cap", "Spread<=max": "wide spread",
            "Fresh": "stale quote", "Stable2tick": "unstable quote", "Depth>=min": "thin book",
            "RiskCaps": "already in a trade"}

# ---------- small helpers ----------
def now_ms(): return int(time.time() * 1000)
def now_s():  return int(time.time())
def clampf(v, lo, hi, d):
    try: v = float(v)
    except (TypeError, ValueError): return d
    return max(lo, min(hi, v))
def p01(x):
    if x is None: return None
    try: v = float(x)
    except (TypeError, ValueError): return None
    return v if 0 <= v <= 1 else None
def num(x):
    if x is None or x == "": return None
    try: return float(x)
    except (TypeError, ValueError): return None
def jarr(x):
    """Gamma sometimes JSON-encodes arrays as strings."""
    if isinstance(x, list): return x
    if isinstance(x, str):
        try:
            a = json.loads(x); return a if isinstance(a, list) else None
        except Exception: return None
    return None
def day_key(ms):
    d = datetime.fromtimestamp(ms/1000, tz=timezone.utc)
    return f"{d.year}-{d.month}-{d.day}"
def fmt_num(v):
    if v is None: return "—"
    a = abs(v); dp = 6 if a < 0.01 else 4 if a < 1 else 2 if a < 100 else 0
    return f"{v:,.{dp}f}"

def http_json(url, timeout=11):
    req = urllib.request.Request(url, headers={"User-Agent": "btc5m-bot/1.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        if r.status != 200: return None
        return json.loads(r.read().decode("utf-8"))
def try_json(url, timeout=11):
    try: return http_json(url, timeout)
    except Exception: return None

# ---------- feeds (spot 1-min candles → interval open + latest) ----------
def feed_coinbase(A, t0):
    start = datetime.fromtimestamp(t0-120, tz=timezone.utc).isoformat()
    end = datetime.fromtimestamp(time.time()+60, tz=timezone.utc).isoformat()
    url = f"https://api.exchange.coinbase.com/products/{A['cb']}/candles?granularity=60&start={urllib.parse.quote(start)}&end={urllib.parse.quote(end)}"
    j = try_json(url)
    if not isinstance(j, list): return None
    return _pick_open_last(((int(r[0]), num(r[3]), num(r[4])) for r in j if isinstance(r, list) and len(r) >= 5), t0)
def feed_binance(A, t0):
    url = f"https://data-api.binance.vision/api/v3/klines?symbol={A['bn']}&interval=1m&startTime={(t0-120)*1000}&limit=12"
    j = try_json(url)
    if not isinstance(j, list): return None
    return _pick_open_last(((int(r[0])//1000, num(r[1]), num(r[4])) for r in j if isinstance(r, list) and len(r) >= 5), t0)
def feed_kraken(A, t0):
    url = f"https://api.kraken.com/0/public/OHLC?pair={A['kr']}&interval=1&since={t0-180}"
    j = try_json(url)
    res = j.get("result") if isinstance(j, dict) else None
    if not res: return None
    key = next((k for k in res if k != "last"), None)
    rows = res.get(key) if key else None
    if not isinstance(rows, list): return None
    return _pick_open_last(((int(r[0]), num(r[1]), num(r[4])) for r in rows if isinstance(r, list) and len(r) >= 5), t0)
def _pick_open_last(rows, t0):
    """rows: iterable of (unix_min, open, close). Return {'open','last'} for interval t0."""
    open_, last, last_t, pc, pc_t = None, None, -1, None, -1
    for t, o, c in rows:
        if t == t0 and o is not None: open_ = o
        if t < t0 and t > pc_t and c is not None: pc_t, pc = t, c
        if t > last_t and c is not None: last_t, last = t, c
    if open_ is None and pc is not None: open_ = pc   # t0 candle not printed yet
    if last is None: return None
    return {"open": open_, "last": last}
FEEDS = [("Coinbase", feed_coinbase), ("Binance", feed_binance), ("Kraken", feed_kraken)]

# ---------- market discovery + order book (Gamma / CLOB) ----------
def parse_event(ev):
    if not ev or not isinstance(ev.get("markets"), list) or not ev["markets"]: return None
    mk = ev["markets"][0]
    toks = jarr(mk.get("clobTokenIds")) or []
    outs = jarr(mk.get("outcomes")) or []
    prices = jarr(mk.get("outcomePrices")) or []
    i_up = next((i for i, o in enumerate(outs) if "up" in str(o).lower()), 0)
    i_dn = 1 if i_up == 0 else 0
    b0, a0 = p01(num(mk.get("bestBid"))), p01(num(mk.get("bestAsk")))
    up_bid, up_ask = b0, a0
    if i_up != 0:
        up_bid = round(1-a0, 4) if a0 is not None else None
        up_ask = round(1-b0, 4) if b0 is not None else None
    def at(a, i): return a[i] if i < len(a) else None
    return {
        "slug": str(ev.get("slug") or ""),
        "closed": mk.get("closed") is True or ev.get("closed") is True,
        "resolved": "resolved" in str(mk.get("umaResolutionStatus") or "").lower(),
        "tokUp": str(at(toks, i_up)) if at(toks, i_up) is not None else None,
        "tokDown": str(at(toks, i_dn)) if at(toks, i_dn) is not None else None,
        "pUp": p01(num(at(prices, i_up))), "pDown": p01(num(at(prices, i_dn))),
        "upBid": up_bid, "upAsk": up_ask,
    }
def winner_of(p):
    if not p or not (p["closed"] or p["resolved"]): return None
    if p["pUp"] is not None and p["pUp"] >= 0.99: return "up"
    if p["pDown"] is not None and p["pDown"] >= 0.99: return "down"
    return None
def gamma_by_slug(slug):
    j = try_json(f"{PM_GAMMA}/events?slug={urllib.parse.quote(slug)}")
    return j[0] if isinstance(j, list) and j else None
def sweep(A, ns):
    for url in (f"{PM_GAMMA}/events?series_slug={urllib.parse.quote(A['series'])}&closed=false&limit=25",
                f"{PM_GAMMA}/public-search?q={urllib.parse.quote(A['q'])}&limit_per_type=40&events_status=active"):
        j = try_json(url)
        arr = j if isinstance(j, list) else (j.get("events") if isinstance(j, dict) else None)
        if not arr: continue
        for e in arr:
            sl = str((e or {}).get("slug") or "")
            if not sl.startswith(A["slug"]): continue
            try: ts = int(sl[len(A["slug"]):])
            except ValueError: continue
            if ts <= ns < ts + IVL: return e, ts
    return None
def book(token_id):
    j = try_json(f"{CLOB}/book?token_id={urllib.parse.quote(token_id)}")
    if not j or (not isinstance(j.get("asks"), list) and not isinstance(j.get("bids"), list)): return None
    asks = sorted(([num(l.get("price")), num(l.get("size"))] for l in (j.get("asks") or [])
                   if num(l.get("price")) is not None and num(l.get("size")) is not None), key=lambda x: x[0])
    bids = sorted(([num(l.get("price")), num(l.get("size"))] for l in (j.get("bids") or [])
                   if num(l.get("price")) is not None and num(l.get("size")) is not None), key=lambda x: x[0], reverse=True)
    if not asks and not bids: return None
    ask, ask_sz = (asks[0] if asks else (None, None))
    bid, bid_sz = (bids[0] if bids else (None, None))
    return {"bid": bid, "ask": ask, "asks": asks, "bids": bids,
            "topAskUsd": ask*ask_sz if ask is not None else None,
            "mirrorTopUsd": (1-bid)*bid_sz if bid is not None else None,
            "at": now_ms()}
def mirror(b):
    if not b: return None
    # the complement token's book is this one reflected across 0.5: a buy of the
    # other side at price q == selling this side at 1-q, so opp ask ladder is our
    # bid ladder reflected, and opp bid ladder is our ask ladder reflected.
    asks = sorted([[round(1-p, 4), s] for p, s in (b.get("bids") or [])], key=lambda x: x[0])
    bids = sorted([[round(1-p, 4), s] for p, s in (b.get("asks") or [])], key=lambda x: x[0], reverse=True)
    return {"bid": round(1-b["ask"], 4) if b["ask"] is not None else None,
            "ask": round(1-b["bid"], 4) if b["bid"] is not None else None,
            "asks": asks, "bids": bids,
            "topAskUsd": b["mirrorTopUsd"], "mirrorTopUsd": b["topAskUsd"], "at": b["at"]}

# ---------- realistic fills: walk the order book, Polymarket taker fee --------
# Polymarket CLOB taker fee (docs.polymarket.com/trading/fees): a taker order
# pays  fee = shares * FEE_RATE * p * (1-p)  (symmetric around 50c, peaks there;
# crypto is the top category at 0.07). Makers (resting limit orders) pay 0 — but
# this bot fills immediately at the offer, so it is always a taker. Gas on
# Polygon is a fraction of a cent per trade. Both are configurable (--fee-rate,
# --gas) and published so the numbers can be checked against a real account.
FEE_RATE = 0.07
GAS_USD = 0.004
MIN_ORDER_USD = 1.0        # Polymarket minimum order size

def _levels(bk, side):
    """[[price,size],...] for 'ask' (ascending) / 'bid' (descending). Uses the
    full ladder when present, else one synthetic top level from bid/ask+size."""
    if not bk: return []
    key = "asks" if side == "ask" else "bids"
    lv = bk.get(key)
    if isinstance(lv, list) and lv:
        out = [[num(p), num(s)] for p, s in lv if num(p) is not None and num(s) is not None]
    else:
        px = bk.get("ask") if side == "ask" else bk.get("bid")
        if px is None: return []
        if side == "ask":
            usd = bk.get("topAskUsd"); sz = (usd/px) if usd else 0.0
        else:
            usd = bk.get("mirrorTopUsd"); sz = (usd/(1-px)) if (usd and px < 1) else 0.0
        out = [[px, sz]]
    out.sort(key=lambda x: x[0], reverse=(side == "bid"))
    return out

def walk_buy(levels, budget_usd, limit):
    """Spend up to budget_usd on ascending ask levels priced <= limit.
    Returns (shares, spent_usd, avg_price|None, fully_filled)."""
    shares = spent = 0.0
    for p, sz in levels:
        if p is None or sz is None or p > limit + 1e-9: break
        cost = p * sz
        if spent + cost <= budget_usd + 1e-9:
            shares += sz; spent += cost
        else:
            take = (budget_usd - spent) / p
            if take > 0: shares += take; spent = budget_usd
            break
    avg = (spent/shares) if shares > 0 else None
    return round(shares, 6), round(spent, 6), (round(avg, 6) if avg else None), spent >= budget_usd - 1e-6

def walk_sell(levels, shares, floor=0.0):
    """Sell up to `shares` into descending bid levels priced >= floor.
    Returns (proceeds_usd, sold_shares, avg_price|None)."""
    proceeds = sold = 0.0
    for p, sz in levels:
        if p is None or sz is None or p < floor - 1e-9: break
        take = min(sz, shares - sold)
        if take <= 0: break
        proceeds += take*p; sold += take
        if sold >= shares - 1e-9: break
    avg = (proceeds/sold) if sold > 0 else None
    return round(proceeds, 6), round(sold, 6), (round(avg, 6) if avg else None)

def taker_fee(shares, price):
    if not shares or shares <= 0 or price is None: return 0.0
    return round(shares * FEE_RATE * price * (1-price), 5)

# ---------- the engine (pure; mirrors the JS btcEvaluate) ----------
class Bot:
    def __init__(self, cfg, state):
        self.cfg = cfg
        self.st = state                       # persisted: config + engines[*].trades
        self.mkt = None                       # runtime shared data layer
        self.feed = {"src": None, "open": None, "last": None, "at": 0, "t0": None}
        self.feed_idx = None
        self.slug_off = 0
        self.sweep_at = 0
        self.res_at = 0
        self.prev_quote = None
        self.closes = {}                      # t0 -> interval's last spot price (for provisional settle)
        self.prev_ivl = None                  # {t0, open, close, ret} of the just-COMPLETED interval — the reversal engine's signal
        self.eng = {e: {"eval": None, "miss": None} for e in ENGINES}
        self.logs = []
        self.misses = self.st.setdefault("misses", [])   # "close but no entry" markets; persisted so the record survives restarts
        self.pxwin = []                       # rolling [t_ms, price] for the volatility measure
        self.vol = None                       # trailing 10-min BTC range as % (None until enough samples)
        self.err = None
        # --- signal bridge (OFF unless --signal-engines is set) ---------------
        # Emits an ENTER signal at DECISION time for external execution (see
        # SIGNAL-BRIDGE.md). The GitHub state.json mirror lags ~5 min behind and
        # must never be used as a signal source; this hook is the live tap.
        self.sig_engines = cfg.get("sigEngines") or []
        self.sig_file = cfg.get("sigFile") or ""
        self.sig_webhook = os.environ.get("BTC5M_SIGNAL_WEBHOOK", "")
        self.sig_secret = os.environ.get("BTC5M_SIGNAL_SECRET", "")
        self.sig_last = {}                    # eid -> t0 already emitted (one-shot per engine per interval)

    # --- config accessors ---
    def prof(self): return PROFILES[self.st["profile"]]
    def asset(self): return ASSETS[self.st["asset"]]
    def update_vol(self, now, price):        # trailing-window range% as the volatility measure
        if price is None: return
        self.pxwin.append((now, price))
        cut = now - VOL_WIN_MS
        while self.pxwin and self.pxwin[0][0] < cut: self.pxwin.pop(0)
        if len(self.pxwin) >= 30:            # ~2 min of 4s samples before we trust it
            pr = [p for _, p in self.pxwin]; lo, hi = min(pr), max(pr)
            self.vol = round((hi-lo)/lo*100, 4) if lo else None
        else:
            self.vol = None
    def eng_pass(self, eid): return int(clampf(self.st["loosePass"], 1, 10, 6)) if ENGINE_CFG[eid]["tunable"] else 10
    def eng_must(self, eid): return tuple(self.st.get("looseMust", LOOSE_MANDATORY)) if ENGINE_CFG[eid]["tunable"] else ()
    def trades(self, eid): return self.st["engines"][eid]["trades"]
    def open_trade(self, eid): return next((t for t in self.trades(eid) if t["status"] == "open"), None)
    def trade_for(self, eid, t0):
        return next((t for t in self.trades(eid) if t["t0"] == t0 and t.get("asset", "BTC") == self.st["asset"]), None)
    def day_stats(self, eid):
        k = day_key(now_ms()); n = 0; pnl = 0.0
        for t in self.trades(eid):
            if day_key(t["at"]) == k:
                n += 1
                if isinstance(t.get("pnl"), (int, float)): pnl += t["pnl"]
        return n, pnl
    def log(self, msg):
        self.logs.insert(0, {"t": now_ms(), "msg": msg})
        del self.logs[120:]
        print(f"{datetime.now().strftime('%H:%M:%S')}  {msg}", flush=True)

    def quote(self, side):
        m = self.mkt
        if not m: return None
        b = m["bookUp"] if side == "up" else m["bookDown"]
        if b and (b["bid"] is not None or b["ask"] is not None):
            return {"bid": b["bid"], "ask": b["ask"], "top": b["topAskUsd"], "at": b["at"], "src": "book"}
        if m["upBid"] is not None or m["upAsk"] is not None:
            if side == "up":
                return {"bid": m["upBid"], "ask": m["upAsk"], "top": None, "at": m["gAt"], "src": "gamma"}
            return {"bid": round(1-m["upAsk"], 4) if m["upAsk"] is not None else None,
                    "ask": round(1-m["upBid"], 4) if m["upBid"] is not None else None,
                    "top": None, "at": m["gAt"], "src": "gamma"}
        return None

    def fair_value(self, delta, open_price, left, K):
        """P(the current lead survives to the close) for a symmetric random walk:
        Phi(|move| / sigma_remaining). sigma comes from the trailing 10-min range%
        converted to an endpoint std (range ~= 1.6*sigma) and scaled to the seconds
        left. None until vol and feed are ready. This is our own estimate of the
        side's true probability, independent of what the book is charging."""
        if delta is None or not open_price or self.vol is None or not left or left <= 0:
            return None
        move = abs(delta) / open_price
        sigma_10m = (self.vol / 100.0) / K            # 10-min endpoint std, as a fraction
        sigma_rem = sigma_10m * math.sqrt(max(1, left) / 600.0)
        if sigma_rem <= 0:
            return None
        return 0.5 * (1.0 + math.erf((move / sigma_rem) / math.sqrt(2)))

    def _fade_eval(self, now, eid):
        """Derived side engine: mirror the base engine's ENTER onto the opposite
        token, priced on ITS real book (not a 1-p mirror), so paper pays the true
        opposite spread and fee. Wins exactly when the base loses, which only pays
        when the base overpays for its picks. Loose qualifies (~ -5.5c/share of
        outcome edge); floor and band have positive edge and are not fadeable.
        Same position/day guards the other engines honor, applied to this book."""
        base_id = ENGINE_CFG[eid]["fadeOf"]
        # Read the base engine's decision as CACHED earlier this tick, before it
        # entered. Re-evaluating here is wrong: once the base records its trade
        # this interval, its own RiskCaps/dup guard flips a fresh eval to
        # enter=False and the fade would never fire. The tick loop always
        # evaluates the base before this engine, so the cache is present; the
        # fallback only covers direct/test calls where it is not.
        base = self.eng.get(base_id, {}).get("eval")
        if not base or base.get("t") != now:
            base = self.evaluate(now, base_id)
        prof, m, f = self.prof(), self.mkt, self.feed
        left = base.get("left")
        bside = base.get("side")
        opp = ("down" if bside == "up" else "up") if bside in ("up", "down") else None
        q = self.quote(opp) if opp else None
        mid = (q["bid"] + q["ask"]) / 2 if (q and q["bid"] is not None and q["ask"] is not None) else None
        spread = (q["ask"] - q["bid"]) if (q and q["bid"] is not None and q["ask"] is not None) else None
        dn, dpnl = self.day_stats(eid)
        loss_cap = clampf(self.st["bank"], 10, 100000, 100) * prof["dayLossPct"] / 100
        opent, dup = self.open_trade(eid), (self.trade_for(eid, m["t0"]) if m else None)
        can_fill = bool(q and q["ask"] is not None and left is not None and left > 0
                        and not opent and not dup and dn < prof["maxDay"] and dpnl > -loss_cap)
        base_enter = bool(base.get("enter"))
        checks = [(f"{base_id} ENTER", base_enter), ("Opp fillable", can_fill)]
        passc = sum(1 for _, ok in checks if ok)
        ev = dict(t=now, side=opp, delta=base.get("delta"), q=q, mid=mid, spread=spread, left=left,
                  checks=checks, passCount=passc, need=2, must=[f"{base_id} ENTER"], mustOk=base_enter,
                  driftPct=base.get("driftPct"), fv=None, extra=[], extraOk=True,
                  all=(passc == 2), enter=(base_enter and can_fill))
        self.eng[eid]["eval"] = ev
        return ev

    def _reversal_eval(self, now, eid):
        """Cross-interval overreaction engine — fires at the START of an interval,
        betting the OPPOSITE side of the just-completed interval's move. Unlike
        every other engine (which reads the CURRENT interval mid-flight), this
        reads self.prev_ivl (the completed interval) and enters near the open at
        the reversal side's real book, while it's still cheap (<= revEntryMax).
        Holds to resolution — the thesis is reversion by close, so no stop."""
        cfg = ENGINE_CFG[eid]
        prof, m, f = self.prof(), self.mkt, self.feed
        ns = now // 1000
        left = (m["t1"] - ns) if m else None
        pv = self.prev_ivl
        contiguous = bool(pv and m and pv.get("t0") == m["t0"] - IVL and pv.get("ret") is not None)
        prior_move = abs(pv["ret"]) * 100 if (pv and pv.get("ret") is not None) else None   # % of open
        signal = bool(contiguous and prior_move is not None and prior_move >= cfg["revThr"])
        rev_side = ("down" if pv["ret"] > 0 else "up") if signal else None                   # opposite the move
        q = self.quote(rev_side) if rev_side else None
        mid = (q["bid"] + q["ask"]) / 2 if (q and q["bid"] is not None and q["ask"] is not None) else None
        spread = (q["ask"] - q["bid"]) if (q and q["bid"] is not None and q["ask"] is not None) else None
        slip = clampf(self.st["slip"], 0, 5, 1) / 100
        early = left is not None and left >= cfg["revWinMin"]                                # near the open
        priced_ok = bool(q and q["ask"] is not None and q["ask"] + slip <= cfg["revEntryMax"] + 1e-9)
        spread_ok = spread is not None and spread <= prof["maxSpread"] + 1e-9
        fresh = bool(q and q.get("at") and (now - q["at"]) <= prof["freshMs"]
                     and f["at"] and (now - f["at"]) <= prof["feedFreshMs"])
        depth_ok = bool(q and (q.get("src") == "gamma" or (q.get("top") is not None and q["top"] >= prof["minTopUsd"])))
        dn, dpnl = self.day_stats(eid)
        loss_cap = clampf(self.st["bank"], 10, 100000, 100) * prof["dayLossPct"] / 100
        opent = self.open_trade(eid); dup = self.trade_for(eid, m["t0"]) if m else None
        market_ok = bool(m and m["ev"] and not m["evClosed"])
        risk_ok = (not opent) and (not dup) and dn < prof["maxDay"] and dpnl > -loss_cap
        can_fill = bool(q and q["ask"] is not None and left is not None and left > 0 and risk_ok)
        checks = [
            ("Market found", market_ok),
            ("Prior≥%.2g%%" % cfg["revThr"], signal),
            ("Near open", early),
            ("Rev≤%dc" % round(cfg["revEntryMax"] * 100), priced_ok),
            ("Spread<=max", spread_ok),
            ("Fresh", fresh),
            ("Depth>=min", depth_ok),
            ("RiskCaps", risk_ok),
        ]
        passc = sum(1 for _, ok in checks if ok)
        enter = bool(market_ok and signal and early and priced_ok and spread_ok and fresh and depth_ok and can_fill)
        delta = (pv["ret"] * pv["open"]) if (pv and pv.get("open")) else 0.0                 # prior move in $ (for logs)
        ev = dict(t=now, side=rev_side, delta=delta, q=q, mid=mid, spread=spread, left=left,
                  checks=checks, passCount=passc, need=len(checks), must=["Prior≥thr"], mustOk=signal,
                  driftPct=prior_move, fv=None, extra=[], extraOk=True, priorMove=prior_move,
                  all=(passc == len(checks)), enter=enter)
        self.eng[eid]["eval"] = ev
        return ev

    def evaluate(self, now, eid):
        if ENGINE_CFG[eid].get("fadeOf"):
            return self._fade_eval(now, eid)
        if ENGINE_CFG[eid].get("revThr"):
            return self._reversal_eval(now, eid)
        prof, m, f = self.prof(), self.mkt, self.feed
        ns = now // 1000
        left = (m["t1"] - ns) if m else None
        delta = (f["last"] - f["open"]) if (f["open"] is not None and f["last"] is not None) else None
        side = None if (delta is None or delta == 0) else ("up" if delta > 0 else "down")
        q = self.quote(side) if side else None
        mid = (q["bid"] + q["ask"]) / 2 if (q and q["bid"] is not None and q["ask"] is not None) else None
        spread = (q["ask"] - q["bid"]) if (q and q["bid"] is not None and q["ask"] is not None) else None
        dn, dpnl = self.day_stats(eid)
        loss_cap = clampf(self.st["bank"], 10, 100000, 100) * prof["dayLossPct"] / 100
        opent = self.open_trade(eid)
        dup = self.trade_for(eid, m["t0"]) if m else None
        thr = (f["open"] * prof["movePct"] / 100) if f["open"] is not None else None
        pq = self.prev_quote
        stable = bool(pq and side and pq["side"] == side and q and q["ask"] is not None
                      and pq["ask"] is not None and abs(q["ask"] - pq["ask"]) <= 0.15)
        checks = [
            ("Market found", bool(m and m["ev"] and not m["evClosed"])),
            ("Window", left is not None and prof["winLeftMin"] <= left <= prof["winLeftMax"]),
            ("Move>=thr", delta is not None and thr is not None and abs(delta) >= thr),
            ("Skew>=mid", mid is not None and mid >= prof["minMid"]),
            ("Ask<=cap", bool(q and q["ask"] is not None and q["ask"] <= prof["maxAsk"])),
            ("Spread<=max", spread is not None and spread <= prof["maxSpread"] + 1e-9),
            ("Fresh", bool(q and (now - q["at"]) <= prof["freshMs"] and f["at"] and (now - f["at"]) <= prof["feedFreshMs"])),
            ("Stable2tick", stable),
            ("Depth>=min", bool(q and q["top"] is not None and q["top"] >= prof["minTopUsd"])),
            ("RiskCaps", (not opent) and (not dup) and dn < prof["maxDay"] and dpnl > -loss_cap),
        ]
        passc = sum(1 for _, ok in checks if ok)
        need = self.eng_pass(eid)
        must = self.eng_must(eid)
        okmap = {k: o for k, o in checks}
        must_ok = all(okmap.get(k, False) for k in must)   # mandatory guards must be green
        allp = passc == len(checks)
        # engine-specific extra gates (variant): early-drift ceiling + entry-price cap
        cfg = ENGINE_CFG[eid]
        drift_pct = (abs(delta) / f["open"] * 100) if (delta is not None and f["open"]) else None
        extra = []
        fv = None
        if cfg.get("driftMin") is not None:   # momentum floor: no entry on sub-signal noise
            extra.append(("drift≥%.2g%%" % cfg["driftMin"], drift_pct is not None and drift_pct >= cfg["driftMin"]))
        if cfg["driftMax"] is not None:       # ceiling: big movers still priced cheap = adverse selection
            extra.append(("drift≤%.2g%%" % cfg["driftMax"], drift_pct is not None and drift_pct <= cfg["driftMax"]))
        if cfg["entryMax"] is not None:
            slip = clampf(self.st["slip"], 0, 5, 1) / 100                    # gate on the expected FILL (ask+slip),
            extra.append(("entry≤%dc" % round(cfg["entryMax"]*100),          # so the realized price stays under the cap
                          bool(q and q["ask"] is not None and q["ask"] + slip <= cfg["entryMax"] + 1e-9)))
        if cfg.get("volMax") is not None:
            extra.append(("calm≤%.2g%%" % cfg["volMax"], self.vol is not None and self.vol <= cfg["volMax"]))
        if cfg.get("fvMargin") is not None:   # value: only enter when the book lags our fair value
            fv = self.fair_value(delta, f["open"], left, cfg.get("fvK", 1.6))
            slipv = clampf(self.st["slip"], 0, 5, 1) / 100
            extra.append(("ask<fv−%d%%" % round(cfg["fvMargin"] * 100),
                          bool(fv is not None and q and q["ask"] is not None
                               and (q["ask"] + slipv) < fv - cfg["fvMargin"])))
        extra_ok = all(o for _, o in extra)
        can_fill = bool(q and q["ask"] is not None and left is not None and left > 0
                        and not opent and not dup and dn < prof["maxDay"] and dpnl > -loss_cap)
        ev = dict(t=now, side=side, delta=delta, q=q, mid=mid, spread=spread, left=left,
                  checks=checks, passCount=passc, need=need, must=list(must), mustOk=must_ok,
                  driftPct=drift_pct, fv=fv, extra=extra, extraOk=extra_ok,
                  all=allp, enter=(passc >= need and must_ok and extra_ok and can_fill))
        self.eng[eid]["eval"] = ev
        return ev

    def side_book(self, side):
        m = self.mkt
        return (m["bookUp"] if side == "up" else m["bookDown"]) if m else None

    KEEP = 600   # trades kept per engine in the scrollable list; older ones fold into the forever lifetime totals + equity curve
    @staticmethod
    def _trade_fees(t):
        return t.get("feeEntry", 0)+t.get("feeExit", 0)+t.get("gas", 0)+(t["hedge"].get("fee", 0) if t.get("hedge") else 0)
    EQ_CAP = 3000  # persisted equity points per engine — the forever P&L curve; only the deep past is decimated when exceeded
    def _trim(self, eid):
        trs = self.trades(eid)
        if len(trs) <= self.KEEP: return
        agg = self.st.setdefault("lifetime", {}).setdefault(eid, _zero_life())
        eq = self.st.setdefault("equity", {}).setdefault(eid, [])
        for t in reversed(trs[self.KEEP:]):       # oldest first → chronological equity points
            agg["trimmed"] += 1
            if isinstance(t.get("entry"), (int, float)): agg["entrySum"] += t["entry"]; agg["entryN"] += 1
            agg["fees"] += self._trade_fees(t)
            r = t.get("result")
            if r in ("win", "loss", "stopped"):
                agg["settled"] += 1; agg[{"win": "wins", "loss": "losses", "stopped": "stopped"}[r]] += 1
                if isinstance(t.get("pnl"), (int, float)): agg["pnl"] += t["pnl"]
                agg["staked"] += t.get("stake", 0)
                eq.append([t["at"], round(agg["pnl"], 2)])   # cumulative lifetime P&L at this trade's time
            elif r == "unknown": agg["unknown"] += 1
        if len(eq) > self.EQ_CAP:                 # decimate but always keep the last point (== agg pnl)
            self.st["equity"][eid] = eq[::2] + ([eq[-1]] if len(eq) % 2 == 0 else [])
        del trs[self.KEEP:]

    def paper_enter(self, eid, ev):
        m, f, prof = self.mkt, self.feed, self.prof()
        side = ev["side"]
        req = clampf(self.st["stake"], 1, 1000, 5)
        slip = clampf(self.st["slip"], 0, 5, 1) / 100
        # a real limit order: willing to pay up to the ask cap (+latency slip).
        # Walk the actual book depth for that budget — a $50 order does NOT fill
        # at the top ask if only a few dollars rest there.
        limit = min(0.99, prof["maxAsk"] + slip)
        bk = self.side_book(side) or {"ask": ev["q"]["ask"], "topAskUsd": ev["q"].get("top")}
        shares, spent, avg, fully = walk_buy(_levels(bk, "ask"), req, limit)
        if spent < MIN_ORDER_USD or not avg:
            self.log(f"[{eid.upper()}] SKIP {side.upper()} — book too thin at ≤{limit*100:.0f}c "
                     f"(only ${spent:.2f} fillable of ${req:g}) ({ev['passCount']}/10)")
            return False
        entry = min(0.99, round(avg + slip, 4))     # latency: realized avg a touch worse
        shares = round(spent/entry, 4)
        fee = taker_fee(shares, entry)
        entered = now_ms()
        tr = dict(at=entered, t0=m["t0"], t1=m["t1"], slug=m["slug"], profile=self.st["profile"],
                  entrySec=max(0, int(round(entered/1000 - m["t0"]))),   # seconds into the 5-min interval at fill
                  asset=self.st["asset"], eng=eid, passCount=ev["passCount"], need=ev["need"],
                  side=side, entry=entry, ask=ev["q"]["ask"], slip=slip*100,
                  stake=round(spent, 2), reqStake=req, fillFrac=round(spent/req, 3),
                  shares=shares, feeEntry=fee, feeExit=0.0, gas=GAS_USD,
                  btcOpen=f["open"], btcEntry=f["last"], btcClose=None, driftPct=ev.get("driftPct"),
                  feed=f["src"], status="open", hedge=None, pnl=None, result=None, settledBy=None,
                  guards=[[k, 1 if ok else 0] for k, ok in ev["checks"]])
        self.trades(eid).insert(0, tr)
        self._trim(eid)
        part = "" if fully else f" partial {tr['fillFrac']*100:.0f}%"
        self.log(f"[{eid.upper()}] ENTER {self.st['asset']} {side.upper()} @ {entry*100:.1f}c avg "
                 f"${spent:.0f}{part} fee ${fee:.2f} ({ev['passCount']}/10) +{tr['entrySec']}s into interval "
                 f"d {'+' if ev['delta']>=0 else '-'}${fmt_num(abs(ev['delta']))}")
        return True

    # Track WHY an engine didn't enter this interval. A "close miss" is any no-entry
    # that either (a) cleared the guard threshold but was blocked by the stability
    # guard, a filter/cap, or thin book, OR (b) came within 2 guards of the threshold
    # on a real move — those are the ones worth surfacing. Dead-flat intervals and
    # far-from-threshold ones (the boring norm) are skipped so the panel stays useful.
    def _track_miss(self, eid, ev, entered):
        if entered: self.eng[eid]["miss"] = None; return
        passc, need, side = ev["passCount"], ev["need"], ev.get("side")
        if ev["enter"]:                                        # signal+filters ok, but fill was skipped
            cap = ENGINE_CFG[eid]["entryMax"] or self.prof()["maxAsk"]
            lvl, note = 4, "book too thin to fill ≤%d¢" % round(cap*100)
        elif passc >= need and ev.get("mustOk") and not ev.get("extraOk"):
            why = []
            for lbl, o in ev.get("extra", []):
                if not o: why.append("priced over cap" if "entry" in lbl else ("move too small" if "drift≥" in lbl else ("move too big" if "drift≤" in lbl else ("too choppy (vol)" if "calm" in lbl else lbl))))
            lvl, note = 3, "filter: " + ", ".join(why)
        elif passc >= need and not ev.get("mustOk"):
            lvl, note = 2, "unstable quote (stability guard red)"
        elif side and passc >= need - 2:                       # near-miss: real move, a guard or two short
            red = [MISS_LBL.get(k, k) for k, ok in ev["checks"] if not ok]
            lvl, note = 2, "%d/%d guards — short: %s" % (passc, need, ", ".join(red[:2]))
        else:
            return                                             # no move, or far below threshold — the boring norm
        cur = self.eng[eid].get("miss")
        if not cur or lvl >= cur["level"]:
            self.eng[eid]["miss"] = {"level": lvl, "side": side, "passc": passc, "need": need, "note": note}

    # Emit an ENTER signal for external (live) execution the moment an engine's
    # gate passes — independent of the paper fill, which models a $50 order and
    # can fail on a book a small live order would clear. One-shot per engine per
    # interval. Side effects must NEVER crash the tick: all I/O is best-effort.
    def emit_signal(self, eid, ev):
        m, q = self.mkt, ev.get("q")
        if not (m and q and q.get("ask") is not None): return
        if self.sig_last.get(eid) == m["t0"]: return
        self.sig_last[eid] = m["t0"]
        now = now_ms()
        cap = ENGINE_CFG[eid].get("revEntryMax") or ENGINE_CFG[eid]["entryMax"] or self.prof()["maxAsk"]
        sig = dict(v=1, signalId=f"{eid}-{m['t0']}", engine=eid, emittedAt=now,
                   asset=self.st["asset"], slug=m["slug"], t0=m["t0"], t1=m["t1"],
                   secLeft=max(0, int(m["t1"] - now/1000)), side=ev["side"],
                   tokenId=(m.get("tokUp") if ev["side"] == "up" else m.get("tokDown")),
                   ask=q["ask"], bid=q.get("bid"), limitCap=cap,
                   driftPct=ev.get("driftPct"), passCount=ev["passCount"], need=ev["need"])
        if self.sig_secret:   # executor MUST verify: hmac_sha256(secret, canonical-json-without-hmac)
            canon = json.dumps(sig, sort_keys=True, separators=(",", ":"))
            sig["hmac"] = hmac.new(self.sig_secret.encode(), canon.encode(), hashlib.sha256).hexdigest()[:32]
        try:
            if self.sig_file:
                tmp = self.sig_file + ".tmp"
                with open(tmp, "w") as f: json.dump(sig, f, separators=(",", ":"))
                os.replace(tmp, self.sig_file)
                # append-only log: the multi-engine transport. A single atomic
                # write per line means two engines firing on the same tick both
                # land, where the single file above would keep only the last.
                log_path = os.path.join(os.path.dirname(self.sig_file), "signals.log")
                with open(log_path, "a") as lf:
                    lf.write(json.dumps(sig, separators=(",", ":")) + "\n")
        except Exception as e:
            self.log(f"signal file error: {e}")
        if self.sig_webhook:
            try:
                body = (f"🎯 **{eid.upper()} ENTER** {ev['side'].upper()} `{m['slug']}` "
                        f"ask {q['ask']*100:.0f}c · cap {cap*100:.0f}c · {sig['secLeft']}s left\n"
                        f"```json\n{json.dumps(sig)}\n```")
                req = urllib.request.Request(self.sig_webhook, data=json.dumps({"content": body}).encode(),
                                             headers={"Content-Type": "application/json", "User-Agent": "btc5m-bot"})
                urllib.request.urlopen(req, timeout=3).read()
            except Exception as e:
                self.log(f"signal webhook error: {e}")
        self.log(f"[SIGNAL] {eid} {ev['side']} {m['slug']} ask {q['ask']*100:.0f}c → bridge")

    def manage_open(self, eid, now):
        tr = self.open_trade(eid)
        if not tr: return
        prof = PROFILES.get(tr["profile"], self.prof())
        ns = now // 1000
        if ns >= tr["t1"]:
            tr["status"] = "pending"
            if self.feed["t0"] == tr["t0"] and self.feed["last"] is not None:
                tr["btcClose"] = self.feed["last"]
            elif self.closes.get(tr["t0"]) is not None:      # feed already rolled — use stashed close
                tr["btcClose"] = self.closes[tr["t0"]]
            self.log(f"[{eid.upper()}] interval closed — {tr['side'].upper()} awaiting resolution"); return
        if not self.mkt or self.mkt["t0"] != tr["t0"] or tr.get("asset", "BTC") != self.st["asset"]: return
        if ENGINE_CFG.get(eid, {}).get("holdToClose"): return   # reversal: hold to resolution — no stop, no hedge
        q, f = self.quote(tr["side"]), self.feed
        sbk, obk = self.side_book(tr["side"]), self.side_book("down" if tr["side"] == "up" else "up")
        slip = clampf(self.st["slip"], 0, 5, 1) / 100
        if f["last"] is not None and tr["btcEntry"] is not None and q and q["bid"] is not None:
            adverse = (tr["btcEntry"] - f["last"]) if tr["side"] == "up" else (f["last"] - tr["btcEntry"])
            if adverse >= tr["btcEntry"] * prof["stopPct"] / 100:
                # sell the position into the real bid ladder (a touch worse for latency)
                proceeds, sold, savg = walk_sell(_levels(sbk or {"bid": q["bid"]}, "bid"), tr["shares"])
                fee_exit = taker_fee(sold, max(0.01, (savg or q["bid"]) - slip))
                pnl = proceeds - tr["stake"] - tr.get("feeEntry", 0) - fee_exit - tr.get("gas", 0)
                if tr["hedge"]:                       # close the hedge into its own bid ladder
                    hp, hs, ha = walk_sell(_levels(obk or {"bid": round(1-(q["ask"] or q["bid"]), 4)}, "bid"), tr["hedge"]["shares"])
                    pnl += hp - tr["hedge"]["stake"] - taker_fee(hs, ha) - tr["hedge"].get("fee", 0)
                tr.update(pnl=round(pnl, 2), result="stopped", status="settled", settledBy="stop-loss",
                          feeExit=round(fee_exit, 5))
                self.log(f"[{eid.upper()}] STOP-LOSS {tr['side'].upper()} @ {(savg or q['bid'])*100:.0f}c "
                         f"P&L {'+' if pnl>=0 else ''}{pnl:.2f}"); return
        if self.st.get("hedgeOn", False) and not tr["hedge"] and q and q["bid"] is not None:
            left = tr["t1"] - ns
            if q["bid"] >= prof["hedgeAt"] and left <= prof["hedgeLeft"]:
                hstake = round(max(1, tr["stake"] * prof["hedgeFrac"]), 2)
                hbk = obk or {"ask": round(1-q["bid"], 4)}
                hsh, hsp, havg, _ = walk_buy(_levels(hbk, "ask"), hstake, 0.99)
                if hsp >= 0.5 and havg:
                    hpx = min(0.99, round(havg + slip, 4)); hsh = round(hsp/hpx, 4)
                    tr["hedge"] = dict(stake=round(hsp, 2), px=hpx, shares=hsh, fee=taker_fee(hsh, hpx), at=now)
                    self.log(f"[{eid.upper()}] HEDGE {'DOWN' if tr['side']=='up' else 'UP'} ${hsp:.2g} @ {hpx*100:.0f}c ({left}s left)")

    def _pnl_for(self, tr, w):
        pnl = (tr["shares"] - tr["stake"]) if tr["side"] == w else -tr["stake"]
        if tr["hedge"]:
            pnl += (tr["hedge"]["shares"] - tr["hedge"]["stake"]) if w != tr["side"] else -tr["hedge"]["stake"]
            pnl -= tr["hedge"].get("fee", 0)
        pnl -= tr.get("feeEntry", 0) + tr.get("feeExit", 0) + tr.get("gas", 0)
        return round(pnl, 2)

    def apply_settle(self, tr, w, by, provisional=False):
        pnl = self._pnl_for(tr, w)
        tr.update(pnl=pnl, result=("win" if tr["side"] == w else "loss"),
                  status="settled", settledBy=by, provisional=provisional)
        self.log(f"[{(tr.get('eng') or 'strict').upper()}] {'WIN' if tr['result']=='win' else 'LOSS'} "
                 f"{tr['side'].upper()} ({by}) P&L {'+' if pnl>=0 else ''}{pnl:.2f}")

    # Provisional settle fires as soon as the interval's move is clearly
    # decisive — comfortably beyond exchange-vs-oracle divergence — so a clean
    # win/loss shows immediately instead of waiting minutes for the oracle.
    # A near-flat close (within the margin) is "too close to call": we hold it
    # pending for the official result. Provisional settles are always rechecked
    # against Polymarket and confirmed or corrected below.
    def _clear_margin(self, open_px):
        return max(15.0, open_px * 0.0003)      # ~$19 at $64k BTC

    def settle_pending(self, now):
        pend = [t for e in ENGINES for t in self.trades(e) if t["status"] == "pending"]
        prov = [t for e in ENGINES for t in self.trades(e) if t.get("provisional")]
        if not pend and not prov: return
        if now - self.res_at < 8000: return
        self.res_at = now
        cache = {}
        def official(slug):
            if slug not in cache: cache[slug] = winner_of(parse_event(gamma_by_slug(slug)))
            return cache[slug]
        opp = lambda s: "up" if s == "down" else "down"
        # 1) confirm or correct earlier provisional settles against the oracle
        for tr in prov:
            w = official(tr["slug"])
            if not w: continue
            prov_w = tr["side"] if tr["result"] == "win" else opp(tr["side"])
            if w == prov_w:
                tr.update(settledBy="polymarket", provisional=False)
                self.log(f"[{(tr.get('eng') or 'strict').upper()}] confirmed {tr['side'].upper()} by oracle")
            else:
                pnl = self._pnl_for(tr, w)
                tr.update(pnl=pnl, result=("win" if tr["side"] == w else "loss"),
                          settledBy="polymarket (corrected)", provisional=False)
                self.log(f"[{(tr.get('eng') or 'strict').upper()}] CORRECTED to "
                         f"{tr['result'].upper()} by oracle P&L {'+' if pnl>=0 else ''}{pnl:.2f}")
        # 2) settle pending trades — oracle first, else clear price action
        for tr in pend:
            w = official(tr["slug"])
            if w: self.apply_settle(tr, w, "polymarket"); continue
            if tr["btcClose"] is None and self.closes.get(tr["t0"]) is not None:
                tr["btcClose"] = self.closes[tr["t0"]]         # backfill if missed
            age = now/1000 - tr["t1"]
            if tr["btcOpen"] is not None and tr["btcClose"] is not None:
                gap = tr["btcClose"] - tr["btcOpen"]
                clear = abs(gap) >= self._clear_margin(tr["btcOpen"])
                if clear or (age > 180 and abs(gap) >= 2):     # clear now, or marginal after a short wait
                    self.apply_settle(tr, "up" if gap > 0 else "down", "feed (provisional)", provisional=True)
                    continue
            if age > 900:
                tr.update(status="settled", result="unknown", pnl=None, settledBy="unresolved")
                self.log(f"could not resolve {tr['slug']} — unsettled")

    # --- market fetch for this tick ---
    def find_market(self, t0):
        raw = gamma_by_slug(self.asset()["slug"] + str(t0 + self.slug_off))
        if raw: return parse_event(raw)
        if now_ms() - self.sweep_at > 30000:
            self.sweep_at = now_ms()
            hit = sweep(self.asset(), now_s())
            if hit:
                ev, ts = hit; self.slug_off = ts - t0; return parse_event(ev)
        return None
    def feed_tick(self, t0):
        if self.feed["t0"] != t0:
            self.feed = {"src": self.feed["src"], "open": None, "last": None, "at": 0, "t0": t0}
        order = ([self.feed_idx] if self.feed_idx is not None else []) + \
                [i for i in range(len(FEEDS)) if i != self.feed_idx]
        for i in order:
            name, fn = FEEDS[i]
            r = fn(self.asset(), t0)
            if r and r["last"] is not None:
                self.feed_idx = i; self.feed["src"] = name
                if r["open"] is not None: self.feed["open"] = r["open"]
                self.feed["last"] = r["last"]; self.feed["at"] = now_ms(); return
    def rollover(self, t0, t1):
        prev = self.mkt
        if prev and prev.get("t0") is not None:            # finalize the interval that just ended
            for e in ENGINES:
                if self.trade_for(e, prev["t0"]): continue  # entered → not a miss
                miss = self.eng[e].get("miss")
                if miss and miss["level"] >= 2:
                    self.misses.insert(0, dict(t0=prev["t0"], eng=e, **miss)); del self.misses[80:]
        for e in ENGINES: self.eng[e] = {"eval": None, "miss": None}
        self.prev_quote = None
        self.mkt = dict(t0=t0, t1=t1, ev=False, evClosed=False, slug=self.asset()["slug"]+str(t0+self.slug_off),
                        tokUp=None, tokDown=None, upBid=None, upAsk=None, pUp=None, gAt=0, bookUp=None, bookDown=None)

    def tick(self):
        try:
            ns = now_s(); t0 = (ns // IVL) * IVL; t1 = t0 + IVL
            if not self.mkt or self.mkt["t0"] != t0:
                # remember the closing spot of the interval we're leaving, so a
                # trade that flips to 'pending' this same tick can still record
                # its btcClose after the feed has rolled to the new interval.
                if self.feed.get("t0") is not None and self.feed.get("last") is not None:
                    self.closes[self.feed["t0"]] = self.feed["last"]
                    for k in sorted(self.closes)[:-20]: del self.closes[k]
                    # capture the just-completed interval's move — the reversal engine's signal
                    if self.feed.get("open"):
                        self.prev_ivl = dict(t0=self.feed["t0"], open=self.feed["open"], close=self.feed["last"],
                                             ret=(self.feed["last"] - self.feed["open"]) / self.feed["open"])
                self.rollover(t0, t1)
            m = self.mkt
            p = self.find_market(t0)
            if p and p["slug"]:
                m.update(ev=True, slug=p["slug"], evClosed=p["closed"], tokUp=p["tokUp"], tokDown=p["tokDown"],
                         upBid=p["upBid"], upAsk=p["upAsk"], pUp=p["pUp"], gAt=now_ms())
            self.feed_tick(t0)
            self.update_vol(now_ms(), self.feed["last"])
            delta = (self.feed["last"]-self.feed["open"]) if (self.feed["open"] is not None and self.feed["last"] is not None) else None
            opent = next((self.open_trade(e) for e in ENGINES if self.open_trade(e)), None)
            side = opent["side"] if opent else (None if not delta else ("up" if delta > 0 else "down"))
            if side and m["ev"]:
                tok = m["tokUp"] if side == "up" else m["tokDown"]
                if tok:
                    b = book(tok)
                    if b:
                        if side == "up": m["bookUp"], m["bookDown"] = b, mirror(b)
                        else: m["bookDown"], m["bookUp"] = b, mirror(b)
            # reversal engine buys the OPPOSITE side of the prior move, near the open,
            # when there's often no directional move yet — so fetch its real book too.
            if m["ev"] and self.prev_ivl and self.prev_ivl.get("t0") == t0 - IVL:
                rs = "down" if self.prev_ivl["ret"] > 0 else "up"
                rtok = m["tokUp"] if rs == "up" else m["tokDown"]
                if rtok and (m["bookUp"] if rs == "up" else m["bookDown"]) is None:
                    rb = book(rtok)
                    if rb:
                        if rs == "up": m["bookUp"], m["bookDown"] = rb, (m["bookDown"] or mirror(rb))
                        else: m["bookDown"], m["bookUp"] = rb, (m["bookUp"] or mirror(rb))
            now = now_ms()
            for e in ENGINES:
                ev = self.evaluate(now, e)
                if ev["enter"] and e in self.sig_engines: self.emit_signal(e, ev)   # live tap first — never behind the paper book-walk
                entered = False
                if ev["enter"] and self.st.get("auto", True): entered = bool(self.paper_enter(e, ev))
                self._track_miss(e, ev, entered)
                self.manage_open(e, now)
            cs = None if not delta else ("up" if delta > 0 else "down")
            cq = self.quote(cs) if cs else None
            self.prev_quote = {"side": cs, "ask": cq["ask"], "t": now} if (cs and cq and cq["ask"] is not None) else None
            self.settle_pending(now)
            self.err = None
        except Exception as e:
            self.err = str(e)
            self.log(f"tick error: {e}")


# ---------- persistence ----------
def _zero_life(): return dict(trimmed=0, settled=0, wins=0, losses=0, stopped=0, unknown=0,
                              pnl=0.0, fees=0.0, staked=0.0, entrySum=0.0, entryN=0)
def default_state(args):
    return {"on": True, "auto": True, "profile": "conservative", "asset": args.asset,
            "stake": args.stake, "bank": args.bank, "slip": args.slip, "loosePass": args.loose,
            "looseMust": list(getattr(args, "loose_must", None) or LOOSE_MANDATORY),
            "hedgeOn": bool(getattr(args, "hedge", False)),   # micro-hedge OFF by default (2026-07-07: ~15% tax on edge, 1 payout in 71)
            "startedAt": now_ms(),
            "lifetime": {e: _zero_life() for e in ENGINES},   # totals for trades trimmed out of the list
            "equity": {e: [] for e in ENGINES},               # [t_ms, cumPnl] curve for trimmed trades
            "misses": [],                                      # rolling "close but no entry" record (persisted)
            "engines": {e: {"trades": []} for e in ENGINES}}
def sanitize(o, args):
    d = default_state(args)
    if isinstance(o, dict):
        for k in ("profile", "asset"):
            if o.get(k) in (PROFILES if k == "profile" else ASSETS): d[k] = o[k]
        for k in ("stake", "bank", "slip", "loosePass", "startedAt"):
            if isinstance(o.get(k), (int, float)): d[k] = o[k]
        if isinstance(o.get("looseMust"), list):
            d["looseMust"] = [k for k in GUARD_KEYS if k in o["looseMust"]]
        if isinstance(o.get("hedgeOn"), bool): d["hedgeOn"] = o["hedgeOn"]
        lf = o.get("lifetime")
        if isinstance(lf, dict):
            for e in ENGINES:
                if isinstance(lf.get(e), dict): d["lifetime"][e].update({k: lf[e][k] for k in _zero_life() if isinstance(lf[e].get(k), (int, float))})
        eq = o.get("equity")
        if isinstance(eq, dict):
            for e in ENGINES:
                if isinstance(eq.get(e), list):
                    d["equity"][e] = [[p[0], p[1]] for p in eq[e]
                                      if isinstance(p, list) and len(p) == 2 and all(isinstance(x, (int, float)) for x in p)]
        ms = o.get("misses")
        if isinstance(ms, list):
            d["misses"] = [m for m in ms if isinstance(m, dict) and isinstance(m.get("t0"), (int, float))][:80]
        eng = o.get("engines")
        if isinstance(eng, dict):
            for e in ENGINES:
                tr = (eng.get(e) or {}).get("trades")
                if isinstance(tr, list): d["engines"][e]["trades"] = tr[:Bot.KEEP]
    return d
def load_state(path, args):
    try:
        with open(path) as f: return sanitize(json.load(f).get("btc"), args)
    except Exception: return default_state(args)
def snapshot(bot):
    """Full state.json: config + ledgers + rolled-up summary + heartbeat + recent log."""
    st = bot.st
    def summ(eid):
        # lifetime = trimmed-out aggregate + everything still in the list, so the
        # totals stay complete no matter how many trades scroll off over 24/7.
        a = st.get("lifetime", {}).get(eid, _zero_life())
        trs = bot.trades(eid)
        settled = [t for t in trs if t["result"] in ("win", "loss", "stopped")]
        wins = a["wins"] + sum(1 for t in settled if t["result"] == "win")
        n_settled = a["settled"] + len(settled)
        pnl = round(a["pnl"] + sum((t["pnl"] or 0) for t in settled), 2)
        fees = round(a["fees"] + sum(Bot._trade_fees(t) for t in trs), 2)
        priced = [t["entry"] for t in trs if isinstance(t.get("entry"), (int, float))]
        entry_sum, entry_n = a["entrySum"] + sum(priced), a["entryN"] + len(priced)
        avg_e = round(entry_sum/entry_n*100, 1) if entry_n else None
        return dict(trades=a["trimmed"]+len(trs), shown=len(trs), settled=n_settled, wins=wins,
                    winPct=(round(wins/n_settled*100, 1) if n_settled else None),
                    avgEntry=avg_e, pnl=pnl, feesPaid=fees, need=bot.eng_pass(eid))
    return {"version": 2, "heartbeat": now_ms(),
            "heartbeatIso": datetime.now(timezone.utc).isoformat(),
            "publishEvery": bot.cfg.get("publishEvery", 1800),
            "feeRate": FEE_RATE, "gas": GAS_USD,
            "asset": st["asset"], "profile": st["profile"], "stake": st["stake"],
            "bank": st["bank"], "startedAt": st.get("startedAt"),
            "slip": st["slip"], "loosePass": st["loosePass"],
            "looseMust": st.get("looseMust", list(LOOSE_MANDATORY)),
            "hedgeOn": st.get("hedgeOn", False),
            "engineCfg": {e: {"entryMax": ENGINE_CFG[e]["entryMax"], "driftMin": ENGINE_CFG[e].get("driftMin"),
                              "driftMax": ENGINE_CFG[e]["driftMax"], "volMax": ENGINE_CFG[e].get("volMax")} for e in ENGINES},
            "vol": bot.vol,
            "feed": {"src": bot.feed.get("src"), "price": bot.feed.get("last"),
                     "open": bot.feed.get("open"), "t0": bot.feed.get("t0"), "at": bot.feed.get("at")},
            "market": ({"slug": bot.mkt.get("slug"), "t0": bot.mkt.get("t0"),
                        "up": bot.mkt.get("pUp"), "upBid": bot.mkt.get("upBid"), "upAsk": bot.mkt.get("upAsk")}
                       if bot.mkt and bot.mkt.get("ev") else None),
            "summary": {e: summ(e) for e in ENGINES},
            "log": bot.logs[:30],
            "misses": bot.misses[:30],
            "btc": {k: st[k] for k in ("on", "auto", "profile", "asset", "stake", "bank", "slip",
                                       "loosePass", "looseMust", "startedAt", "lifetime", "equity", "misses", "engines")}}
def save_state(path, bot):
    tmp = path + ".tmp"
    with open(tmp, "w") as f: json.dump(snapshot(bot), f, separators=(",", ":"))
    os.replace(tmp, path)   # atomic

# ---------- git publish (low cadence, isolated data branch) ----------
def publish(state_path, branch, repo_dir, remote="origin"):
    """Force-update `branch` with a single ORPHAN commit holding only state.json.

    Uses git plumbing so it never touches the checked-out branch, index, or
    working tree — main stays clean, and the data branch never grows history
    (each publish replaces it with one parent-less commit)."""
    try:
        def g(*a, ok=(0,)):
            r = subprocess.run(("git",)+a, cwd=repo_dir, capture_output=True, text=True)
            if r.returncode not in ok:
                raise RuntimeError(f"git {' '.join(a)}: {r.stderr.strip()}")
            return r.stdout.strip()
        with open(state_path, "rb") as f: data = f.read()
        # write the blob into the object store from stdin (no index involvement)
        r = subprocess.run(("git", "hash-object", "-w", "--stdin"), cwd=repo_dir,
                           input=data, capture_output=True)
        if r.returncode != 0: raise RuntimeError(r.stderr.decode().strip())
        blob = r.stdout.decode().strip()
        tree = subprocess.run(("git", "mktree"), cwd=repo_dir,
                              input=f"100644 blob {blob}\tstate.json\n".encode(), capture_output=True)
        if tree.returncode != 0: raise RuntimeError(tree.stderr.decode().strip())
        tree_sha = tree.stdout.decode().strip()
        commit = g("commit-tree", tree_sha, "-m", "state update")   # orphan: no -p parent
        g("push", "--force", remote, f"{commit}:refs/heads/{branch}")
        return True
    except Exception as e:
        print(f"publish failed: {e}", flush=True); return False


# ================= SELF TEST (offline, no network) =================
def selftest():
    fails = 0
    def ok(cond, name, extra=""):
        nonlocal fails
        print(("PASS" if cond else "FAIL") + "  " + name + (f"  [{extra}]" if extra else ""))
        if not cond: fails += 1
    class A: asset="BTC"; stake=5; bank=100; slip=1; loose=6
    st = default_state(A)
    bot = Bot({}, st)
    now = now_ms(); ns = now // 1000
    # full-pass market for strict
    bot.mkt = dict(t0=ns-210, t1=ns+90, ev=True, evClosed=False, slug="btc-updown-5m-test",
                   tokUp="1", tokDown="2", upBid=0.64, upAsk=0.66, pUp=0.65, gAt=now,
                   bookUp={"bid":0.64,"ask":0.66,"topAskUsd":132,"mirrorTopUsd":54,"at":now},
                   bookDown={"bid":0.34,"ask":0.36,"topAskUsd":54,"mirrorTopUsd":132,"at":now})
    bot.feed = {"src":"Coinbase","open":100000,"last":100130,"at":now,"t0":bot.mkt["t0"]}
    bot.prev_quote = {"side":"up","ask":0.66,"t":now-4000}
    ev = bot.evaluate(now, "strict")
    ok(ev["all"] and ev["enter"], "strict passes all 10 and enters",
       ",".join(k for k,o in ev["checks"] if not o))
    ok(ev["side"] == "up", "momentum side = up")
    bot.paper_enter("strict", ev)
    tr = bot.trades("strict")[0]
    ok(abs(tr["entry"] - 0.67) < 1e-9, "entry = 66c ask + 1c slip", str(tr["entry"]))
    ok(abs(tr["shares"] - 5/0.67) < 1e-3, "shares = stake/fill")
    # loose threshold: an 8/10 scenario (cheap fill) should NOT enter strict but SHOULD enter loose
    st2 = default_state(A); b2 = Bot({}, st2)
    b2.mkt = dict(bot.mkt); b2.mkt["upBid"]=0.57; b2.mkt["upAsk"]=0.58
    b2.mkt["bookUp"]={"bid":0.57,"ask":0.58,"asks":[[0.58,300]],"bids":[[0.57,300]],"topAskUsd":174,"mirrorTopUsd":129,"at":now}
    b2.mkt["bookDown"]=mirror(b2.mkt["bookUp"]); b2.mkt["t1"]=ns+400   # window red
    b2.feed = dict(bot.feed); b2.feed["last"]=100010                  # tiny move → Move red → 8/10 (window+move red)
    b2.prev_quote = {"side":"up","ask":0.58,"t":now-4000}             # stable
    es = b2.evaluate(now, "strict"); el = b2.evaluate(now, "loose")
    ok(es["passCount"] == el["passCount"], "both engines see same guard count", str(es["passCount"]))
    ok(not es["enter"] and es["passCount"] < 10, "strict rejects sub-10/10", str(es["passCount"]))
    ok(el["enter"] == (el["passCount"] >= 6), "loose enters iff >=6/10",
       f"{el['passCount']}/10 enter={el['enter']}")
    # loose mandatory guard (Stable2tick): 7/10 with a jumpy quote must NOT enter
    bm = Bot({}, default_state(A))
    base = dict(t0=ns-210, t1=ns+400, ev=True, evClosed=False, slug="m", tokUp="1", tokDown="2",  # t1 far → Window red
                upBid=0.57, upAsk=0.58, pUp=0.575, gAt=now,                                        # cheap fill (under 65c cap)
                bookUp={"bid":0.57,"ask":0.58,"asks":[[0.58,300]],"bids":[[0.57,300]],"topAskUsd":174,"mirrorTopUsd":129,"at":now})
    base["bookDown"]=mirror(base["bookUp"])
    bm.mkt = base
    bm.feed = {"src":"Coinbase","open":100000,"last":100010,"at":now,"t0":base["t0"]}   # tiny move → Move red
    bm.prev_quote = {"side":"up","ask":0.40,"t":now-4000}                                # ask jumped → Stable red
    eA = bm.evaluate(now, "loose")
    ok(eA["passCount"] >= 6 and not eA["mustOk"] and not eA["enter"],
       "loose blocks entry when Stable2tick red", f"pass={eA['passCount']} mustOk={eA['mustOk']}")
    bm.prev_quote = {"side":"up","ask":0.58,"t":now-4000}                                # stable now → Stable green
    eB = bm.evaluate(now, "loose")
    ok(eB["mustOk"] and eB["enter"], "loose enters when Stable2tick green", f"pass={eB['passCount']} enter={eB['enter']}")
    # floor + band engines: nested ablation on the drift gate (loose = no gate,
    # floor = >=0.02%, band = 0.02-0.04%). Fixture move sizes control driftPct.
    bv = Bot({}, default_state(A))
    def mkmkt(ask, bid):
        mk = dict(t0=ns-210, t1=ns+400, ev=True, evClosed=False, slug="v", tokUp="1", tokDown="2",  # window red
                  upBid=bid, upAsk=ask, pUp=(ask+bid)/2, gAt=now,
                  bookUp={"bid":bid,"ask":ask,"asks":[[ask,300]],"bids":[[bid,300]],"topAskUsd":ask*300,"mirrorTopUsd":(1-bid)*300,"at":now})
        mk["bookDown"] = mirror(mk["bookUp"]); return mk
    bv.mkt = mkmkt(0.58, 0.57); bv.prev_quote = {"side":"up","ask":0.58,"t":now-4000}      # cheap 58c fill
    bv.feed = {"src":"Coinbase","open":100000,"last":100010,"at":now,"t0":bv.mkt["t0"]}    # 1bps: sub-floor noise
    l1, f1, n1 = bv.evaluate(now,"loose"), bv.evaluate(now,"floor"), bv.evaluate(now,"band")
    ok(l1["enter"] and not f1["enter"] and not n1["enter"],
       "1bps noise: loose takes it, floor+band block", f"loose={l1['enter']} floor={f1['enter']} band={n1['enter']}")
    bv.feed = {"src":"Coinbase","open":100000,"last":100030,"at":now,"t0":bv.mkt["t0"]}    # 3bps: in the band
    l2, f2, n2 = bv.evaluate(now,"loose"), bv.evaluate(now,"floor"), bv.evaluate(now,"band")
    ok(l2["enter"] and f2["enter"] and n2["enter"],
       "3bps move: all three enter", f"loose={l2['enter']} floor={f2['enter']} band={n2['enter']}")
    fd2 = bv.evaluate(now, "fade")   # loose entered UP → fade enters DOWN on the opposite book
    ok(fd2["enter"] and fd2["side"] == "down",
       "fade mirrors loose onto the opposite side", f"loose={l2['side']} fade={fd2['side']} enter={fd2['enter']}")
    # regression: fade must STILL fire after loose has actually ENTERED this
    # interval. The tick loop enters loose before evaluating fade, so a fresh
    # re-eval of loose would see its open trade and wrongly stand down. This test
    # (unlike the ones above) records loose's trade first, so it guards the fix.
    bvr = Bot({}, default_state(A))
    bvr.mkt = mkmkt(0.58, 0.57); bvr.prev_quote = {"side": "up", "ask": 0.58, "t": now-4000}
    bvr.feed = {"src": "Coinbase", "open": 100000, "last": 100030, "at": now, "t0": bvr.mkt["t0"]}
    lr = bvr.evaluate(now, "loose"); bvr.paper_enter("loose", lr)   # loose takes the trade first
    fr = bvr.evaluate(now, "fade")
    ok(fr["enter"] and fr["side"] == "down" and bool(bvr.open_trade("loose")),
       "fade still fires after loose has entered this interval",
       f"loose_open={bool(bvr.open_trade('loose'))} fade={fr['side']} enter={fr['enter']}")
    bv.feed = {"src":"Coinbase","open":100000,"last":100060,"at":now,"t0":bv.mkt["t0"]}    # 6bps: over the ceiling
    f3, n3 = bv.evaluate(now,"floor"), bv.evaluate(now,"band")
    ok(f3["enter"] and not n3["enter"],
       "6bps mover: floor takes it, band's ceiling blocks (adverse selection)", f"floor={f3['enter']} band={n3['enter']}")
    bv.mkt = mkmkt(0.68, 0.67); bv.prev_quote = {"side":"up","ask":0.68,"t":now-4000}      # RICH 68c, 3bps move
    bv.feed = {"src":"Coinbase","open":100000,"last":100030,"at":now,"t0":bv.mkt["t0"]}
    n4 = bv.evaluate(now,"band")
    ok(not n4["enter"], "band blocks a 68c fill (65c cap shared with loose)", f"enter={n4['enter']}")
    lf4, ff4 = bv.evaluate(now, "loose"), bv.evaluate(now, "fade")   # 68c blocks loose → fade must stand down too
    ok(not lf4["enter"] and not ff4["enter"],
       "fade stands down when loose stands down", f"loose={lf4['enter']} fade={ff4['enter']}")
    # --- reversal engine: cross-interval overreaction (fires at the open on the prior move) ---
    def mkrev(dask, dbid, left=240):
        t0r = ns - (300 - left)                                     # so t1-ns == left (near-open window)
        mk = dict(t0=t0r, t1=t0r+300, ev=True, evClosed=False, slug="btc-updown-5m-rev", tokUp="U", tokDown="D",
                  upBid=round(1-dask,2), upAsk=round(1-dbid,2), pUp=0.5, gAt=now,
                  bookDown={"bid":dbid,"ask":dask,"asks":[[dask,300]],"bids":[[dbid,300]],
                            "topAskUsd":dask*300,"mirrorTopUsd":(1-dbid)*300,"at":now})
        mk["bookUp"]=mirror(mk["bookDown"]); return mk
    brv = Bot({}, default_state(A)); brv.feed = {"src":"Coinbase","open":100000,"last":100010,"at":now,"t0":ns-60}
    brv.mkt = mkrev(0.50, 0.49)                                     # reversal (down) side cheap at 50c, 240s left
    brv.prev_ivl = dict(t0=brv.mkt["t0"]-IVL, open=100000, close=100200, ret=0.0020)   # prior interval +20bps UP
    rv = brv.evaluate(now, "reversal")
    ok(rv["enter"] and rv["side"]=="down",
       "reversal fires DOWN after a big UP prior interval", f"side={rv['side']} enter={rv['enter']} prior={rv['priorMove']:.3f}%")
    brv.prev_ivl = dict(t0=brv.mkt["t0"]-IVL, open=100000, close=100050, ret=0.0005)   # prior +5bps, below 12bps
    ok(not brv.evaluate(now,"reversal")["enter"], "reversal stands down when prior move < 12bps")
    brv.prev_ivl = dict(t0=brv.mkt["t0"]-2*IVL, open=100000, close=100200, ret=0.0020)  # not the immediately-prior interval
    ok(not brv.evaluate(now,"reversal")["enter"], "reversal requires the immediately-prior interval (contiguity)")
    brv.prev_ivl = dict(t0=brv.mkt["t0"]-IVL, open=100000, close=100200, ret=0.0020)
    brv.mkt = mkrev(0.60, 0.59)                                     # reversal side now RICH at 60c (> 55c cap)
    ok(not brv.evaluate(now,"reversal")["enter"], "reversal blocks when the reversal side is above 55c")
    brv.mkt = mkrev(0.50, 0.49, left=90)                           # too late in the interval (90s left < 180)
    ok(not brv.evaluate(now,"reversal")["enter"], "reversal blocks when not near the open")
    # holdToClose: a reversal position must NOT stop out on an adverse move — it holds to resolution
    brv.mkt = mkrev(0.50, 0.49); brv.prev_ivl = dict(t0=brv.mkt["t0"]-IVL, open=100000, close=100200, ret=0.0020)
    rvh = brv.evaluate(now,"reversal"); brv.paper_enter("reversal", rvh)
    brv.feed["last"] = 100500                                       # +50bps: strongly adverse for the DOWN bet
    brv.manage_open("reversal", now)
    trh = brv.open_trade("reversal")
    ok(trh is not None and trh["result"] is None,
       "reversal holds through an adverse move (no stop-loss)", f"open={trh is not None} result={trh and trh['result']}")
    # miss tracking: an enter that can't fill (thin book) records a level-4 miss
    bmz = Bot({}, default_state(A)); bmz.eng["loose"]={"eval":None,"miss":None}
    bmz._track_miss("loose", {"enter":True,"side":"up","passCount":8,"need":7,"mustOk":True,"extraOk":True,"extra":[],"checks":[]}, False)
    ok(bmz.eng["loose"]["miss"] and bmz.eng["loose"]["miss"]["level"]==4, "thin-book skip records a miss")
    # signal bridge: emits once per engine per interval, atomic file, HMAC verifies, bad webhook never raises
    import tempfile
    sf = os.path.join(tempfile.gettempdir(), "btc5m_sig_test.json")
    bsg = Bot({"sigEngines":["band"], "sigFile":sf}, default_state(A))
    bsg.sig_secret = "testkey"; bsg.sig_webhook = "http://127.0.0.1:1/nope"   # refused instantly → must be swallowed
    bsg.mkt = dict(t0=ns-60, t1=ns+240, ev=True, evClosed=False, slug="btc-updown-5m-test",
                   tokUp="TOKUP", tokDown="TOKDN", upBid=0.53, upAsk=0.54, pUp=0.535, gAt=now)
    evs = dict(side="down", q={"bid":0.53,"ask":0.54,"at":now}, driftPct=0.025, passCount=8, need=7, enter=True)
    bsg.emit_signal("band", evs); bsg.emit_signal("band", evs)               # second call = duplicate, ignored
    with open(sf) as f: sj = json.load(f)
    canon = json.dumps({k:v for k,v in sj.items() if k!="hmac"}, sort_keys=True, separators=(",", ":"))
    good = hmac.new(b"testkey", canon.encode(), hashlib.sha256).hexdigest()[:32]
    ok(sj["signalId"]==f"band-{ns-60}" and sj["side"]=="down" and sj["tokenId"]=="TOKDN"
       and sj["limitCap"]==0.65 and sj["hmac"]==good and bsg.sig_last["band"]==ns-60,
       "signal bridge: schema + tokenId + HMAC + one-shot + webhook failure swallowed",
       f"id={sj['signalId']} tok={sj['tokenId']} hmacOK={sj['hmac']==good}")
    os.remove(sf)
    # hedge toggle: a pinned position in the hedge zone hedges only when hedgeOn
    def pinned_bot(hedge_on):
        b = Bot({}, default_state(A)); b.st["hedgeOn"] = hedge_on
        b.mkt = dict(t0=ns-280, t1=ns+15, ev=True, evClosed=False, slug="h", tokUp="1", tokDown="2",  # 15s left
                     upBid=0.98, upAsk=0.99, pUp=0.98, gAt=now,
                     bookUp={"bid":0.98,"ask":0.99,"asks":[[0.99,300]],"bids":[[0.98,300]],"topAskUsd":297,"mirrorTopUsd":6,"at":now})
        b.mkt["bookDown"] = mirror(b.mkt["bookUp"])
        b.feed = {"src":"Coinbase","open":100000,"last":100200,"at":now,"t0":b.mkt["t0"]}
        b.trades("loose").insert(0, dict(at=now,t0=b.mkt["t0"],t1=b.mkt["t1"],slug="h",profile="conservative",
            asset="BTC",eng="loose",side="up",entry=0.55,ask=0.55,slip=1,stake=50,shares=90,
            btcOpen=100000,btcEntry=100010,btcClose=None,feed="Coinbase",status="open",hedge=None,pnl=None,result=None,settledBy=None))
        b.manage_open("loose", now); return b.trades("loose")[0]["hedge"]
    ok(pinned_bot(False) is None, "hedge OFF → no hedge in the pin zone")
    ok(pinned_bot(True) is not None, "hedge ON → hedges in the pin zone")
    # stop-loss
    st3 = default_state(A); b3 = Bot({}, st3)
    b3.mkt = dict(t0=ns-100, t1=ns+200, ev=True, evClosed=False, slug="s", tokUp="1", tokDown="2",
                  upBid=0.6, upAsk=0.62, pUp=0.6, gAt=now,
                  bookUp={"bid":0.45,"ask":0.5,"topAskUsd":100,"mirrorTopUsd":100,"at":now},
                  bookDown={"bid":0.5,"ask":0.55,"topAskUsd":100,"mirrorTopUsd":100,"at":now})
    b3.feed = {"src":"Coinbase","open":100000,"last":100130,"at":now,"t0":b3.mkt["t0"]}
    b3.trades("strict").insert(0, dict(at=now,t0=b3.mkt["t0"],t1=b3.mkt["t1"],slug="s",profile="conservative",
        asset="BTC",eng="strict",side="up",entry=0.62,ask=0.62,slip=1,stake=5,shares=round(5/0.62,4),
        btcOpen=100000,btcEntry=100130,btcClose=None,feed="Coinbase",status="open",hedge=None,pnl=None,result=None,settledBy=None))
    b3.feed["last"] = 100130 - 260   # 0.26% retrace > 0.25% stop
    b3.manage_open("strict", now)
    t3 = b3.trades("strict")[0]
    sh3 = round(5/0.62, 4)
    exp = round(sh3*0.45 - 5 - taker_fee(sh3, 0.44), 2)   # sell into 45c bid, minus exit taker fee
    ok(t3["result"] == "stopped" and abs(t3["pnl"]-exp) < 0.03, "stop-loss walks bid ladder + fee", f"{t3['pnl']} vs {exp}")
    # settlement win P&L (with hedge)
    st4 = default_state(A); b4 = Bot({}, st4)
    b4.trades("strict").insert(0, dict(at=now,t0=1,t1=2,slug="x",profile="conservative",asset="BTC",eng="strict",
        side="up",entry=0.67,ask=0.66,slip=1,stake=5,shares=round(5/0.67,4),btcOpen=1,btcEntry=1,btcClose=None,
        feed="x",status="pending",hedge=dict(stake=1,px=0.05,shares=round(1/0.05,4),at=now),pnl=None,result=None,settledBy=None))
    b4.apply_settle(b4.trades("strict")[0], "up", "polymarket")
    t4 = b4.trades("strict")[0]
    exp4 = round(5/0.67 - 5 - 1, 2)
    ok(t4["result"] == "win" and abs(t4["pnl"]-exp4) < 0.011, "settle win incl hedge loss", f"{t4['pnl']} vs {exp4}")
    # --- realistic fills: depth walking + taker fee ---
    # deep book: $50 fills near the top ask
    sh, sp, avg, full = walk_buy([[0.60, 500], [0.62, 500]], 50, 0.71)
    ok(full and abs(avg-0.60) < 1e-6, "deep book fills at top ask", f"avg={avg}")
    # thin book: top level only $6, next level higher — $50 walks up and averages worse
    sh, sp, avg, full = walk_buy([[0.60, 10], [0.66, 200]], 50, 0.71)
    ok(full and 0.60 < avg < 0.66, "thin top → fill walks up the book", f"avg={avg}")
    # too thin under the limit → partial fill only
    sh, sp, avg, full = walk_buy([[0.60, 10], [0.90, 500]], 50, 0.71)
    ok(not full and abs(sp-6.0) < 1e-6, "book too thin under limit → partial", f"spent={sp}")
    # sell walks the bid ladder
    pr, sold, savg = walk_sell([[0.50, 10], [0.48, 100]], 60)
    ok(abs(pr-(0.50*10+0.48*50)) < 1e-6 and abs(sold-60) < 1e-6, "sell walks bid ladder", f"proceeds={pr}")
    # taker fee: shares*rate*p*(1-p), symmetric around 0.5
    ok(abs(taker_fee(100, 0.5) - 100*FEE_RATE*0.25) < 1e-9, "taker fee peaks at 50c")
    ok(abs(taker_fee(100, 0.3) - taker_fee(100, 0.7)) < 1e-9, "taker fee symmetric 30c=70c")
    # winner detection + feed parse
    ok(winner_of({"closed":True,"resolved":True,"pUp":1.0,"pDown":0.0}) == "up", "winner_of reads resolved up")
    fl = _pick_open_last([(ns-60,None,99998),(ns,100000,100050)], ns)
    ok(fl and fl["open"] == 100000 and fl["last"] == 100050, "feed picks interval open+last")
    fl2 = _pick_open_last([(ns-60,99990,99998)], ns)   # t0 candle missing → prev close is open
    ok(fl2 and fl2["open"] == 99998, "feed falls back to prev close for open")
    # daily loss cap is OFF (paper analytics): a big day loss must NOT block entry
    st5 = default_state(A); b5 = Bot({}, st5)
    b5.trades("strict").insert(0, dict(at=now,t0=1,t1=2,slug="x",profile="conservative",asset="BTC",eng="strict",
        side="up",entry=0.6,ask=0.6,slip=0,stake=5,shares=8,btcOpen=1,btcEntry=1,btcClose=None,feed="x",
        status="settled",hedge=None,pnl=-999,result="loss",settledBy="t"))   # huge day loss
    b5.mkt = dict(bot.mkt); b5.feed = dict(bot.feed); b5.prev_quote = {"side":"up","ask":0.66,"t":now-4000}
    e5 = b5.evaluate(now, "strict")
    ok(e5["checks"][9][1] and e5["enter"], "daily loss cap OFF — big loss does not halt entry")
    # lifetime totals survive trimming (24/7: trades scroll off but totals stay whole)
    b6 = Bot({}, default_state(A)); b6.KEEP = 2
    for i, (res, pnl, entry) in enumerate([("win",10,0.6),("loss",-50,0.7),("win",20,0.65),("win",5,0.55)]):
        b6.trades("loose").insert(0, dict(at=now,t0=i,t1=i+1,slug="x",profile="conservative",asset="BTC",eng="loose",
            side="up",entry=entry,ask=entry,slip=1,stake=50,shares=1,feeEntry=1.0,feeExit=0,gas=0.004,
            btcOpen=1,btcEntry=1,btcClose=None,feed="x",status="settled",hedge=None,pnl=pnl,result=res,settledBy="t"))
        b6._trim("loose")
    s6 = snapshot(b6)["summary"]["loose"]
    ok(s6["settled"]==4 and s6["wins"]==3 and abs(s6["pnl"]-(-15))<0.01 and s6["trades"]==4 and s6["shown"]==2,
       "lifetime totals survive trimming", f"settled={s6['settled']} wins={s6['wins']} pnl={s6['pnl']} shown={s6['shown']}")
    eq6 = b6.st["equity"]["loose"]   # oldest-folded first: cum 10 (win), then 10-50=-40 (loss); ends at lifetime pnl
    ok(len(eq6)==2 and abs(eq6[0][1]-10)<1e-6 and abs(eq6[1][1]-(-40))<1e-6,
       "equity curve records cumulative P&L on trim", f"eq={eq6}")
    print("\n" + ("ALL PASS" if fails == 0 else f"{fails} FAILURES"))
    return 1 if fails else 0


def main():
    global FEE_RATE, GAS_USD
    ap = argparse.ArgumentParser(description="Polymarket 5-minute crypto PAPER trader (headless).")
    ap.add_argument("--asset", default="BTC", choices=list(ASSETS))
    ap.add_argument("--profile", default="conservative", choices=list(PROFILES))
    ap.add_argument("--stake", type=float, default=5)
    ap.add_argument("--bank", type=float, default=100)
    ap.add_argument("--slip", type=float, default=1)
    ap.add_argument("--loose", type=int, default=6, help="loose engine enters at N/10 guards")
    ap.add_argument("--state", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json"))
    ap.add_argument("--once", action="store_true", help="one tick then exit")
    ap.add_argument("--selftest", action="store_true", help="offline logic checks, no network")
    ap.add_argument("--publish", action="store_true", help="git-push state.json to --branch on cadence")
    ap.add_argument("--branch", default="data")
    ap.add_argument("--repo-dir", default=os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument("--publish-every", type=int, default=1800, help="min seconds between publishes")
    ap.add_argument("--fee-rate", type=float, default=FEE_RATE, help="Polymarket taker fee rate (crypto 0.07)")
    ap.add_argument("--gas", type=float, default=GAS_USD, help="per-trade gas (USD)")
    ap.add_argument("--loose-must", default=",".join(LOOSE_MANDATORY),
                    help="guards loose must have green (comma-separated keys, or 'none')")
    ap.add_argument("--hedge", action="store_true", help="enable the late micro-hedge (OFF by default)")
    ap.add_argument("--signal-engines", default="", help="engines whose ENTER signals are emitted for the live "
                    "execution bridge (comma-separated, e.g. 'band'); empty = bridge OFF. See SIGNAL-BRIDGE.md")
    ap.add_argument("--signal-file", default="", help="atomic JSON file each signal is written to (optional)")
    args = ap.parse_args()
    FEE_RATE, GAS_USD = args.fee_rate, args.gas
    args.loose_must = [] if args.loose_must.strip().lower() == "none" else \
                      [k for k in GUARD_KEYS if k in [x.strip() for x in args.loose_must.split(",")]]
    if args.selftest: sys.exit(selftest())

    st = load_state(args.state, args)
    st["profile"] = args.profile
    st["asset"] = args.asset if args.asset else st["asset"]
    st["stake"], st["bank"], st["slip"], st["loosePass"] = args.stake, args.bank, args.slip, args.loose
    st["looseMust"] = args.loose_must
    st["hedgeOn"] = bool(args.hedge)
    sig_engines = [e for e in (x.strip() for x in args.signal_engines.split(",")) if e in ENGINES]
    bot = Bot({"publishEvery": args.publish_every, "sigEngines": sig_engines, "sigFile": args.signal_file}, st)
    must_lbl = (" +" + "/".join(GUARD_ABBR.get(k, k) for k in st["looseMust"]) + " req") if st["looseMust"] else ""
    bot.log(f"bot started — {st['asset']} · {st['profile']} · loose {args.loose}/10{must_lbl} + fill≤65c · "
            f"floor (+drift≥0.02%) · band (drift 0.02-0.04%) · strict 10/10 · hedge {'ON' if st['hedgeOn'] else 'OFF'} · "
            f"${st['stake']:g} stake · +{st['slip']:g}c slip · state={args.state}")
    if sig_engines:
        bot.log(f"SIGNAL BRIDGE ON — engines={','.join(sig_engines)} file={args.signal_file or '—'} "
                f"webhook={'set' if bot.sig_webhook else 'UNSET'} hmac={'set' if bot.sig_secret else 'UNSET'}")
    last_pub = 0
    def positions_sig():   # changes when any trade opens, settles, or goes pending → publish promptly
        return {e: (sum(1 for t in bot.trades(e) if t["status"] == "settled"),
                    (bot.open_trade(e) or {}).get("at"),
                    sum(1 for t in bot.trades(e) if t["status"] == "pending")) for e in ENGINES}
    last_sig = positions_sig()
    if args.once:
        # self-verifying smoke test: fetch one tick and report exactly what
        # each live source returned, so you can confirm data is flowing.
        bot.tick(); save_state(args.state, bot)
        m, f = bot.mkt, bot.feed
        print("\n===== LIVE DATA CHECK (" + st["asset"] + ") =====")
        print(f"  Gamma market : {'OK  ' + m['slug'] if (m and m['ev']) else 'NOT FOUND'}"
              f"{'' if (m and m['ev']) else '  (market may not be listed this second — retry)'}")
        print(f"  Spot feed    : {f['src'] or 'NONE'}"
              f"{'  open=' + fmt_num(f['open']) + ' last=' + fmt_num(f['last']) if f['last'] is not None else '  (no price!)'}")
        bu = (m or {}).get("bookUp"); bd = (m or {}).get("bookDown")
        def bk(b): return (f"bid {b['bid']} / ask {b['ask']} / top-ask ${round(b['topAskUsd']) if b['topAskUsd'] else '—'}"
                           if b else "none")
        print(f"  CLOB book Up : {bk(bu)}")
        print(f"  CLOB book Dn : {bk(bd)}")
        # realistic-fill preview: what a full-stake order actually does to the book
        for e in ENGINES:
            ev = bot.eng[e]["eval"]
            if ev and ev.get("side") and (m or {}).get("book"+ev["side"].capitalize()):
                prof = bot.prof(); bk_e = bot.side_book(ev["side"])
                lim = min(0.99, prof["maxAsk"] + clampf(st["slip"],0,5,1)/100)
                sh, sp, avg, full = walk_buy(_levels(bk_e, "ask"), st["stake"], lim)
                if avg:
                    fee = taker_fee(round(sp/min(0.99,avg),4), avg)
                    print(f"  fill ${st['stake']:g} {ev['side'].upper():4}: avg {avg*100:.1f}c, "
                          f"{sp/st['stake']*100:.0f}% filled, taker fee ${fee:.2f}"
                          + ("" if full else "  ← book too thin for full size"))
        for e in ENGINES:
            ev = bot.eng[e]["eval"]
            print(f"  {e:<6} eval  : {ev['passCount']}/10 guards, needs {ev['need']}, enter={ev['enter']}" if ev else f"  {e}: no eval")
        healthy = bool(m and m["ev"] and f["last"] is not None)
        print("  RESULT       : " + ("HEALTHY — live data is flowing." if healthy
              else "INCOMPLETE — see above; if this persists, check network/DNS on this machine."))
        print(f"  state.json   : written to {args.state}")
        sys.exit(0 if healthy else 2)

    while True:
        bot.tick()
        save_state(args.state, bot)
        if args.publish:
            sig_now = positions_sig()
            if sig_now != last_sig or (time.time() - last_pub) >= args.publish_every:
                if publish(args.state, args.branch, args.repo_dir):
                    last_pub = time.time(); last_sig = sig_now
        time.sleep(TICK_S)


if __name__ == "__main__":
    main()
