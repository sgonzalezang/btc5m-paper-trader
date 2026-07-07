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
import argparse, json, math, os, sys, time, urllib.request, urllib.parse, subprocess
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
        stopPct=0.25, hedgeAt=0.95, hedgeLeft=45, hedgeFrac=0.03,
        maxDay=math.inf,   # day-count cap OFF at user request 2026-07-04 "for now" — was 12
        dayLossPct=10),
    "aggressive": dict(label="Aggressive", movePct=0.07, minMid=0.52, maxAsk=0.70,
        winLeftMax=150, winLeftMin=60, freshMs=8000, feedFreshMs=15000, maxSpread=0.03, minTopUsd=30,
        stopPct=0.30, hedgeAt=0.93, hedgeLeft=50, hedgeFrac=0.05,
        maxDay=math.inf,   # day-count cap OFF at user request 2026-07-04 "for now" — was 20
        dayLossPct=15),
}
ENGINES = ["strict", "loose"]

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
    ask = ask_sz = bid = bid_sz = None
    for l in j.get("asks") or []:
        pp, sz = num(l.get("price")), num(l.get("size"))
        if pp is None or sz is None: continue
        if ask is None or pp < ask: ask, ask_sz = pp, sz
    for l in j.get("bids") or []:
        pp, sz = num(l.get("price")), num(l.get("size"))
        if pp is None or sz is None: continue
        if bid is None or pp > bid: bid, bid_sz = pp, sz
    if ask is None and bid is None: return None
    return {"bid": bid, "ask": ask,
            "topAskUsd": ask*ask_sz if ask is not None else None,
            "mirrorTopUsd": (1-bid)*bid_sz if bid is not None else None,
            "at": now_ms()}
def mirror(b):
    if not b: return None
    return {"bid": round(1-b["ask"], 4) if b["ask"] is not None else None,
            "ask": round(1-b["bid"], 4) if b["bid"] is not None else None,
            "topAskUsd": b["mirrorTopUsd"], "mirrorTopUsd": b["topAskUsd"], "at": b["at"]}

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
        self.eng = {e: {"eval": None} for e in ENGINES}
        self.logs = []
        self.err = None

    # --- config accessors ---
    def prof(self): return PROFILES[self.st["profile"]]
    def asset(self): return ASSETS[self.st["asset"]]
    def eng_pass(self, eid): return int(clampf(self.st["loosePass"], 1, 10, 6)) if eid == "loose" else 10
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

    def evaluate(self, now, eid):
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
        allp = passc == len(checks)
        can_fill = bool(q and q["ask"] is not None and left is not None and left > 0
                        and not opent and not dup and dn < prof["maxDay"] and dpnl > -loss_cap)
        ev = dict(t=now, side=side, delta=delta, q=q, mid=mid, spread=spread, left=left,
                  checks=checks, passCount=passc, need=need, all=allp, enter=(passc >= need and can_fill))
        self.eng[eid]["eval"] = ev
        return ev

    def paper_enter(self, eid, ev):
        m, f = self.mkt, self.feed
        stake = clampf(self.st["stake"], 1, 1000, 5)
        slip = clampf(self.st["slip"], 0, 5, 1) / 100
        px = min(0.99, round(ev["q"]["ask"] + slip, 4))
        tr = dict(at=now_ms(), t0=m["t0"], t1=m["t1"], slug=m["slug"], profile=self.st["profile"],
                  asset=self.st["asset"], eng=eid, passCount=ev["passCount"], need=ev["need"],
                  side=ev["side"], entry=px, ask=ev["q"]["ask"], slip=slip*100, stake=stake,
                  shares=round(stake/px, 4), btcOpen=f["open"], btcEntry=f["last"], btcClose=None,
                  feed=f["src"], status="open", hedge=None, pnl=None, result=None, settledBy=None,
                  guards=[[k, 1 if ok else 0] for k, ok in ev["checks"]])   # which of the 10 were green at entry
        self.trades(eid).insert(0, tr)
        del self.trades(eid)[250:]
        self.log(f"[{eid.upper()}] ENTER {self.st['asset']} {tr['side'].upper()} @ {px*100:.1f}c "
                 f"({ev['passCount']}/10) ${stake:g} d {'+' if ev['delta']>=0 else '-'}${fmt_num(abs(ev['delta']))}")

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
        q, f = self.quote(tr["side"]), self.feed
        if f["last"] is not None and tr["btcEntry"] is not None and q and q["bid"] is not None:
            adverse = (tr["btcEntry"] - f["last"]) if tr["side"] == "up" else (f["last"] - tr["btcEntry"])
            if adverse >= tr["btcEntry"] * prof["stopPct"] / 100:
                pnl = tr["shares"] * q["bid"] - tr["stake"]
                if tr["hedge"]:
                    hb = max(0.01, 1 - (q["ask"] if q["ask"] is not None else q["bid"]))
                    pnl += tr["hedge"]["shares"] * hb - tr["hedge"]["stake"]
                tr.update(pnl=round(pnl, 2), result="stopped", status="settled", settledBy="stop-loss")
                self.log(f"[{eid.upper()}] STOP-LOSS {tr['side'].upper()} @ {q['bid']*100:.0f}c bid "
                         f"P&L {'+' if pnl>=0 else ''}{pnl:.2f}"); return
        if not tr["hedge"] and q and q["bid"] is not None:
            left = tr["t1"] - ns
            if q["bid"] >= prof["hedgeAt"] and left <= prof["hedgeLeft"]:
                hstake = round(max(1, tr["stake"] * prof["hedgeFrac"]), 2)
                hslip = clampf(self.st["slip"], 0, 5, 1) / 100
                hpx = max(0.01, min(0.99, round(1 - q["bid"] + hslip, 4)))
                tr["hedge"] = dict(stake=hstake, px=hpx, shares=round(hstake/hpx, 4), at=now)
                self.log(f"[{eid.upper()}] HEDGE {'DOWN' if tr['side']=='up' else 'UP'} ${hstake:g} @ {hpx*100:.0f}c ({left}s left)")

    def _pnl_for(self, tr, w):
        pnl = (tr["shares"] - tr["stake"]) if tr["side"] == w else -tr["stake"]
        if tr["hedge"]:
            pnl += (tr["hedge"]["shares"] - tr["hedge"]["stake"]) if w != tr["side"] else -tr["hedge"]["stake"]
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
        for e in ENGINES: self.eng[e]["eval"] = None
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
                self.rollover(t0, t1)
            m = self.mkt
            p = self.find_market(t0)
            if p and p["slug"]:
                m.update(ev=True, slug=p["slug"], evClosed=p["closed"], tokUp=p["tokUp"], tokDown=p["tokDown"],
                         upBid=p["upBid"], upAsk=p["upAsk"], pUp=p["pUp"], gAt=now_ms())
            self.feed_tick(t0)
            delta = (self.feed["last"]-self.feed["open"]) if (self.feed["open"] is not None and self.feed["last"] is not None) else None
            opent = self.open_trade("strict") or self.open_trade("loose")
            side = opent["side"] if opent else (None if not delta else ("up" if delta > 0 else "down"))
            if side and m["ev"]:
                tok = m["tokUp"] if side == "up" else m["tokDown"]
                if tok:
                    b = book(tok)
                    if b:
                        if side == "up": m["bookUp"], m["bookDown"] = b, mirror(b)
                        else: m["bookDown"], m["bookUp"] = b, mirror(b)
            now = now_ms()
            for e in ENGINES:
                ev = self.evaluate(now, e)
                if ev["enter"] and self.st.get("auto", True): self.paper_enter(e, ev)
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
def default_state(args):
    return {"on": True, "auto": True, "profile": "conservative", "asset": args.asset,
            "stake": args.stake, "bank": args.bank, "slip": args.slip, "loosePass": args.loose,
            "startedAt": now_ms(),
            "engines": {e: {"trades": []} for e in ENGINES}}
def sanitize(o, args):
    d = default_state(args)
    if isinstance(o, dict):
        for k in ("profile", "asset"):
            if o.get(k) in (PROFILES if k == "profile" else ASSETS): d[k] = o[k]
        for k in ("stake", "bank", "slip", "loosePass", "startedAt"):
            if isinstance(o.get(k), (int, float)): d[k] = o[k]
        eng = o.get("engines")
        if isinstance(eng, dict):
            for e in ENGINES:
                tr = (eng.get(e) or {}).get("trades")
                if isinstance(tr, list): d["engines"][e]["trades"] = tr[:250]
    return d
def load_state(path, args):
    try:
        with open(path) as f: return sanitize(json.load(f).get("btc"), args)
    except Exception: return default_state(args)
def snapshot(bot):
    """Full state.json: config + ledgers + rolled-up summary + heartbeat + recent log."""
    st = bot.st
    def summ(eid):
        trs = bot.trades(eid)
        settled = [t for t in trs if t["result"] in ("win", "loss", "stopped")]
        wins = sum(1 for t in settled if t["result"] == "win")
        pnl = round(sum((t["pnl"] or 0) for t in settled), 2)
        priced = [t["entry"] for t in trs if isinstance(t.get("entry"), (int, float))]
        avg_e = round(sum(priced)/len(priced)*100, 1) if priced else None
        return dict(trades=len(trs), settled=len(settled), wins=wins,
                    winPct=(round(wins/len(settled)*100, 1) if settled else None),
                    avgEntry=avg_e, pnl=pnl, need=bot.eng_pass(eid))
    return {"version": 2, "heartbeat": now_ms(),
            "heartbeatIso": datetime.now(timezone.utc).isoformat(),
            "publishEvery": bot.cfg.get("publishEvery", 1800),
            "asset": st["asset"], "profile": st["profile"], "stake": st["stake"],
            "bank": st["bank"], "startedAt": st.get("startedAt"),
            "slip": st["slip"], "loosePass": st["loosePass"],
            "summary": {e: summ(e) for e in ENGINES},
            "log": bot.logs[:30],
            "btc": {k: st[k] for k in ("on", "auto", "profile", "asset", "stake", "bank", "slip", "loosePass", "engines")}}
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
    # loose threshold: an 8/10 scenario should NOT enter strict but SHOULD enter loose
    st2 = default_state(A); b2 = Bot({}, st2)
    b2.mkt = dict(bot.mkt); b2.mkt["upAsk"]=0.80; b2.mkt["bookUp"]={"bid":0.78,"ask":0.82,"topAskUsd":160,"mirrorTopUsd":40,"at":now}
    b2.mkt["bookDown"]=mirror(b2.mkt["bookUp"]); b2.mkt["t1"]=ns+400   # ask>cap AND outside window → ~8/10
    b2.feed = dict(bot.feed); b2.prev_quote = {"side":"up","ask":0.82,"t":now-4000}
    es = b2.evaluate(now, "strict"); el = b2.evaluate(now, "loose")
    ok(es["passCount"] == el["passCount"], "both engines see same guard count", str(es["passCount"]))
    ok(not es["enter"] and es["passCount"] < 10, "strict rejects sub-10/10", str(es["passCount"]))
    ok(el["enter"] == (el["passCount"] >= 6), "loose enters iff >=6/10",
       f"{el['passCount']}/10 enter={el['enter']}")
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
    exp = round((5/0.62)*0.45 - 5, 2)
    ok(t3["result"] == "stopped" and abs(t3["pnl"]-exp) < 0.011, "stop-loss exits at bid", f"{t3['pnl']} vs {exp}")
    # settlement win P&L (with hedge)
    st4 = default_state(A); b4 = Bot({}, st4)
    b4.trades("strict").insert(0, dict(at=now,t0=1,t1=2,slug="x",profile="conservative",asset="BTC",eng="strict",
        side="up",entry=0.67,ask=0.66,slip=1,stake=5,shares=round(5/0.67,4),btcOpen=1,btcEntry=1,btcClose=None,
        feed="x",status="pending",hedge=dict(stake=1,px=0.05,shares=round(1/0.05,4),at=now),pnl=None,result=None,settledBy=None))
    b4.apply_settle(b4.trades("strict")[0], "up", "polymarket")
    t4 = b4.trades("strict")[0]
    exp4 = round(5/0.67 - 5 - 1, 2)
    ok(t4["result"] == "win" and abs(t4["pnl"]-exp4) < 0.011, "settle win incl hedge loss", f"{t4['pnl']} vs {exp4}")
    # winner detection + feed parse
    ok(winner_of({"closed":True,"resolved":True,"pUp":1.0,"pDown":0.0}) == "up", "winner_of reads resolved up")
    fl = _pick_open_last([(ns-60,None,99998),(ns,100000,100050)], ns)
    ok(fl and fl["open"] == 100000 and fl["last"] == 100050, "feed picks interval open+last")
    fl2 = _pick_open_last([(ns-60,99990,99998)], ns)   # t0 candle missing → prev close is open
    ok(fl2 and fl2["open"] == 99998, "feed falls back to prev close for open")
    # day loss cap gate
    st5 = default_state(A); b5 = Bot({}, st5)
    b5.trades("strict").insert(0, dict(at=now,t0=1,t1=2,slug="x",profile="conservative",asset="BTC",eng="strict",
        side="up",entry=0.6,ask=0.6,slip=0,stake=5,shares=8,btcOpen=1,btcEntry=1,btcClose=None,feed="x",
        status="settled",hedge=None,pnl=-20,result="loss",settledBy="t"))   # -20 > 10% of 100
    b5.mkt = dict(bot.mkt); b5.feed = dict(bot.feed); b5.prev_quote = {"side":"up","ask":0.66,"t":now-4000}
    e5 = b5.evaluate(now, "strict")
    ok(not e5["enter"] and not e5["checks"][9][1], "daily loss cap blocks entry")
    print("\n" + ("ALL PASS" if fails == 0 else f"{fails} FAILURES"))
    return 1 if fails else 0


def main():
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
    args = ap.parse_args()
    if args.selftest: sys.exit(selftest())

    st = load_state(args.state, args)
    st["profile"] = args.profile
    st["asset"] = args.asset if args.asset else st["asset"]
    st["stake"], st["bank"], st["slip"], st["loosePass"] = args.stake, args.bank, args.slip, args.loose
    bot = Bot({"publishEvery": args.publish_every}, st)
    bot.log(f"bot started — {st['asset']} · {st['profile']} · strict 10/10 + loose {args.loose}/10 · "
            f"${st['stake']:g} stake · +{st['slip']:g}c slip · state={args.state}")
    last_pub = 0
    last_settled = {e: sum(1 for t in bot.trades(e) if t["status"] == "settled") for e in ENGINES}
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
            settled_now = {e: sum(1 for t in bot.trades(e) if t["status"] == "settled") for e in ENGINES}
            trade_event = settled_now != last_settled
            if trade_event or (time.time() - last_pub) >= args.publish_every:
                if publish(args.state, args.branch, args.repo_dir):
                    last_pub = time.time(); last_settled = settled_now
        time.sleep(TICK_S)


if __name__ == "__main__":
    main()
