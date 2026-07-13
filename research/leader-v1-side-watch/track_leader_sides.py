#!/usr/bin/env python3
"""Living tracker for the leader_v1 / leader50 side-asymmetry watch.

Re-run any time to refresh the numbers as the sample grows:
    python3 research/leader-v1-side-watch/track_leader_sides.py

Reads the LIVE bot state (bot/state.json) — the leader shadow book carries every
qualifying signal (filled or missed) with its oracle outcome, and leader50's own
book carries the actual filled P&L. We slice by:
  - BET side (the drift/leader direction we alerted — known at decision time)
  - OUTCOME direction (what the interval actually did — known only at close)
  - continuation vs reversal (leader50 is a momentum bet: win == the drift continued)
and report BOTH the actual-fill P&L and the would-be-inclusive P&L (the honest
full-signal number, since our worst signals sometimes never fill).

Writes a dated snapshot to snapshots/<t>.json so the series is auditable.
Pre-registered decision rule lives in OBSERVATION.md — do not move the goalposts.
"""
import json, os, sys, time, datetime

ROOT = os.path.expanduser("~/btc5m-paper-trader")
STATE = os.path.join(ROOT, "bot/state.json")
OUTDIR = os.path.join(ROOT, "research/leader-v1-side-watch/snapshots")
OPP = {"up": "down", "down": "up"}

def load():
    with open(STATE) as f:
        return json.load(f)

def analyze(s):
    tr = s["btc"]["engines"].get("leader50", {}).get("trades", [])
    fills_by_t0 = {t["t0"]: t for t in tr}
    book = s["btc"].get("leader", {}).get("book", [])
    orc = [r for r in book if r.get("winBy") == "oracle" and r.get("win") is not None]

    def realized(r):
        """actual fill pnl if leader50 filled, else the would-be pnl (hypothetical)."""
        if r.get("l50") == "fill":
            m = fills_by_t0.get(r["t0"])
            return (m.get("pnl") or 0.0) if m else 0.0
        return r.get("wbPnl") or 0.0

    def actual_only(r):
        if r.get("l50") == "fill":
            m = fills_by_t0.get(r["t0"])
            return (m.get("pnl") or 0.0) if m else 0.0
        return None  # a miss books no real money

    def outcome(r):
        return r["side"] if r["win"] == 1 else OPP[r["side"]]

    def grp(rows):
        n = len(rows)
        w = sum(1 for r in rows if r["win"] == 1)
        pnl_all = round(sum(realized(r) for r in rows), 2)
        acts = [actual_only(r) for r in rows if actual_only(r) is not None]
        return dict(n=n, wins=w, winPct=(round(100 * w / n, 1) if n else None),
                    pnl_incl_wouldbe=pnl_all, pnl_actual_fills=round(sum(acts), 2),
                    n_filled=len(acts))

    res = dict(
        asOf=s.get("heartbeatIso"),
        n_oracle=len(orc),
        continuation_rate=(round(100 * sum(1 for r in orc if r["win"] == 1) / len(orc), 1) if orc else None),
        by_bet_side={sd: grp([r for r in orc if r["side"] == sd]) for sd in ("up", "down")},
        by_outcome={od: grp([r for r in orc if outcome(r) == od]) for od in ("up", "down")},
        signals=[dict(t0=r["t0"], bet=r["side"], filled=r.get("l50"),
                      won=bool(r["win"]), pnl=round(realized(r), 2)) for r in sorted(orc, key=lambda x: x["t0"])],
    )
    return res

def fmt(res):
    f = lambda t: datetime.datetime.utcfromtimestamp(t).strftime("%m-%d %H:%M")
    L = []
    L.append(f"leader_v1/leader50 side watch — as of {res['asOf']}")
    L.append(f"n(oracle-confirmed signals)={res['n_oracle']} · small-drift continued {res['continuation_rate']}% "
             f"(>50 = momentum, <50 = reversion)")
    L.append("")
    L.append("BY BET SIDE (drift/leader direction — the actionable, known-at-alert cut):")
    for sd in ("up", "down"):
        g = res["by_bet_side"][sd]
        L.append(f"  {sd:4s}-leader: n={g['n']:2d}  win {g['winPct']}%  "
                 f"P&L incl. would-be {g['pnl_incl_wouldbe']:+.2f}  (actual fills {g['pnl_actual_fills']:+.2f} on {g['n_filled']})")
    L.append("")
    L.append("BY OUTCOME (what the interval did — only known at close):")
    for od in ("up", "down"):
        g = res["by_outcome"][od]
        L.append(f"  went {od:4s}:  n={g['n']:2d}  we won {g['wins']}/{g['n']}  "
                 f"P&L incl. would-be {g['pnl_incl_wouldbe']:+.2f}")
    L.append("")
    tot_wb = round(sum(res["by_bet_side"][sd]["pnl_incl_wouldbe"] for sd in ("up", "down")), 2)
    tot_ac = round(sum(res["by_bet_side"][sd]["pnl_actual_fills"] for sd in ("up", "down")), 2)
    L.append(f"TOTAL: actual filled P&L {tot_ac:+.2f} · full-signal (incl. would-be) {tot_wb:+.2f}")
    L.append("")
    L.append("signals:")
    for x in res["signals"]:
        L.append(f"  {f(x['t0'])}  bet {x['bet']:4s}  {str(x['filled']):5s}  "
                 f"{'WON ' if x['won'] else 'LOST'}  {x['pnl']:+7.2f}")
    return "\n".join(L)

def main():
    s = load()
    res = analyze(s)
    print(fmt(res))
    # stamp a snapshot (no Date.now in the analysis; use file mtime-free wall clock here only for the filename)
    os.makedirs(OUTDIR, exist_ok=True)
    stamp = (s.get("heartbeatIso") or "").replace(":", "").replace("-", "")[:15] or str(int(time.time()))
    path = os.path.join(OUTDIR, f"{stamp}.json")
    with open(path, "w") as f:
        json.dump(res, f, indent=1)
    print(f"\nsnapshot -> {path}")

if __name__ == "__main__":
    main()
