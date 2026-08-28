"""Backtest core for btc-updown-5m strategies.

Data model per market (a "row"):
  t0        interval open (unix, aligned to 300)
  outcome   "up" | "down"
  path      [[sec_into_interval, up_price], ...]  (~-48,+10,+70,+130,+190,+250)
  candles   dict minute_ts -> [t, o, h, l, c, v]  (shared, Coinbase)

Strategy protocol: fn(row, ctx) -> None | dict(side, p_mkt, at_s)
  side   "up"|"down"; p_mkt = the raw path price for the SIDE at decision time
  at_s   seconds into interval when the decision was made (info discipline is
         the strategy's job: it may only read path points with sec <= at_s and
         candles with t < t0 + at_s - 60 (candle must be CLOSED))
ctx carries rolling state (streaks etc.) built in time order.

Evaluation: fill = p_mkt + haircut (cross spread), fee = 0.07*stake*(1-fill),
win pnl/stake = (1-fill)/fill - 0.07*(1-fill), loss = -1 - 0.07*(1-fill).
"""
import json, math, os, bisect

HERE = os.path.dirname(os.path.abspath(__file__))

def load(days=None):
    rows = []
    for ln in open(os.path.join(HERE, "data", "markets.jsonl"), encoding="utf-8"):
        try: r = json.loads(ln)
        except Exception: continue
        if r.get("miss") or not r.get("path"): continue
        rows.append(r)
    rows.sort(key=lambda r: r["t0"])
    seen, out = set(), []
    for r in rows:
        if r["t0"] in seen: continue
        seen.add(r["t0"]); out.append(r)
    if days:
        cut = out[-1]["t0"] - days * 86400
        out = [r for r in out if r["t0"] >= cut]
    cd = {}
    for ln in open(os.path.join(HERE, "data", "candles.jsonl"), encoding="utf-8"):
        try:
            c = json.loads(ln); cd[c[0]] = c
        except Exception: pass
    return out, cd

def path_at(row, at_s, side="up"):
    """Latest path price at or before at_s (seconds into interval). None if no
    point yet. Returns the price of the requested side."""
    best = None
    for s, p in row["path"]:
        if s <= at_s: best = p
        else: break
    if best is None: return None
    return best if side == "up" else round(1.0 - best, 4)

def candle(cd, ts):
    return cd.get(ts // 60 * 60)

def prior_candles(cd, t0, n):
    """n CLOSED 1-min candles strictly before t0, oldest first."""
    out = []
    for i in range(n, 0, -1):
        c = cd.get(t0 - i * 60)
        if c is None: return None
        out.append(c)
    return out

FEE = 0.07
def trade_pnl(fill, won):
    fee = FEE * (1.0 - fill)          # per $1 stake
    return ((1.0 - fill) / fill - fee) if won else (-1.0 - fee)

def evaluate(rows, cd, strat, haircut=0.02, max_p=0.97, min_p=0.03):
    """Run strat over rows in time order. Returns trade list."""
    ctx = {}
    trades = []
    for row in rows:
        sig = None
        try: sig = strat(row, cd, ctx)
        except Exception: pass
        if sig:
            p = sig["p_mkt"] + haircut
            if min_p <= p <= max_p:
                won = (sig["side"] == row["outcome"])
                trades.append(dict(t0=row["t0"], side=sig["side"], fill=round(p, 4),
                                   at_s=sig.get("at_s"), won=won, r=trade_pnl(p, won)))
        post = getattr(strat, "post", None)
        if post: post(row, cd, ctx)
    return trades

def stats(trades):
    n = len(trades)
    if n == 0: return dict(n=0)
    rs = [t["r"] for t in trades]
    m = sum(rs) / n
    sd = (sum((x - m) ** 2 for x in rs) / (n - 1)) ** 0.5 if n > 1 else float("nan")
    se = sd / math.sqrt(n) if n > 1 else float("nan")
    w = sum(1 for t in trades if t["won"])
    fills = sum(t["fill"] for t in trades) / n
    be = fills + FEE * fills * (1 - fills)
    return dict(n=n, win=w / n, avg_fill=fills, breakeven=be, edge=w / n - be,
                ret=m, se=se, t=(m / se if se and se == se and se > 0 else float("nan")),
                pnl_per_100=m * 100)

def fmt(s, label=""):
    if not s or not s.get("n"): return f"{label:<26} n=0"
    return (f"{label:<26} n={s['n']:<5} win={s['win']*100:5.1f}% fill={s['avg_fill']*100:5.1f}c "
            f"be={s['breakeven']*100:5.1f}% edge={s['edge']*100:+5.1f}pp ret/$={s['ret']*100:+7.2f}% t={s['t']:+5.2f}")

def split3(rows):
    """60/20/20 time split: train/validation/test."""
    n = len(rows)
    return rows[:int(n*.6)], rows[int(n*.6):int(n*.8)], rows[int(n*.8):]
