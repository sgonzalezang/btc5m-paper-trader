"""Backtest protocol runner (Fable-5 design).

  python run_protocol.py phase0      data hygiene + falsifier diagnostics
  python run_protocol.py train       sweep all configs on train (days 1-18)
  python run_protocol.py val         evaluate train survivors on validation (days 19-24)
  python run_protocol.py test        ONE-SHOT: evaluate the pre-registered set
                                     in registered.json on test (days 25-30)
  python run_protocol.py walkforward walk-forward folds for finalists

Splits are by TIME on the harvested window. Test rows are never touched by
train/val commands. Selection happens at haircut=2c; 1c/3c are sensitivity.
"""
import json, math, os, sys, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bt, candidates

HERE = os.path.dirname(os.path.abspath(__file__))

def load_all():
    rows, cd = bt.load()
    candidates.add_streaks(rows)
    F1 = candidates.F(cd)
    n = len(rows)
    d0, d1 = rows[0]["t0"], rows[-1]["t0"]
    days = (d1 - d0) / 86400.0
    # time split: 60/20/20
    tr = rows[:int(n * .6)]
    va = rows[int(n * .6):int(n * .8)]
    te = rows[int(n * .8):]
    return rows, cd, F1, tr, va, te

def run_one(strat, rows, cd, h):
    return bt.evaluate(rows, cd, strat, haircut=h)

def line(name, trades):
    s = bt.stats(trades)
    if not s.get("n"): return "%-22s n=0" % name
    ct = candidates.clustered_t(trades)
    return ("%-22s n=%-5d win=%5.1f%% fill=%5.1fc edge=%+5.1fpp ret/$=%+7.2f%% t=%+5.2f tclu=%+5.2f"
            % (name, s["n"], s["win"]*100, s["avg_fill"]*100, s["edge"]*100, s["ret"]*100, s["t"], ct))

def phase0():
    rows, cd, F1, *_ = load_all()
    print("markets=%d  candles=%d  span=%.1f days" % (len(rows), len(cd), (rows[-1]["t0"]-rows[0]["t0"])/86400))
    # complement + staleness
    stale10 = tot10 = 0
    for r in rows:
        pts = dict()
        for s, p in r["path"]: pts[s] = p
        early = [p for s, p in r["path"] if -60 <= s <= 20]
        if len(early) >= 2:
            tot10 += 1
            if abs(early[-1] - early[0]) < 0.005: stale10 += 1
    print("+10s point identical to pre-open point: %d/%d (%.0f%%)" % (stale10, tot10, 100*stale10/max(1,tot10)))
    # oracle vs coinbase outcome agreement
    agree = dis = nod = 0
    for r in rows:
        o = F1.strike_open(r["t0"])
        c = cd.get(r["t0"] + 240)
        if not o or not c: nod += 1; continue
        cb = "up" if c[4] > o else "down"
        if cb == r["outcome"]: agree += 1
        else: dis += 1
    print("coinbase-close vs oracle outcome: agree=%d disagree=%d (%.1f%% disagree) nodata=%d"
          % (agree, dis, 100*dis/max(1,agree+dis), nod))
    # streak continuation base rate
    cont = collections.Counter()
    for r in rows:
        st = r.get("streak")
        if st and st[0] and st[1] >= 3:
            cont[r["outcome"] == st[0]] += 1
    t = cont[True] + cont[False]
    if t: print("P(continuation | streak>=3): %.1f%% (n=%d)" % (100*cont[True]/t, t))
    # comeback rate vs late price
    for pmax in (0.10, 0.15, 0.20):
        n = w = 0
        for r in rows:
            u = bt.path_at(r, 190, "up")
            if u is None or not candidates.fresh_path(r, 190): continue
            side, p = ("up", u) if u <= 1-u else ("down", round(1-u, 4))
            if p <= pmax:
                n += 1; w += (r["outcome"] == side)
        if n: print("comeback rate (late side<=%dc @+190s): %.1f%% vs price-implied ~%.0f%% (n=%d)"
                    % (pmax*100, 100*w/n, pmax*100, n))

def train():
    rows, cd, F1, tr, va, te = load_all()
    C = candidates.build(F1)
    print("TRAIN: %d markets, %d configs, h=2c" % (len(tr), len(C)))
    res = {}
    for name, fn in C.items():
        t2 = run_one(fn, tr, cd, 0.02)
        res[name] = t2
        print(line(name, t2))
    json.dump({k: bt.stats(v) for k, v in res.items()},
              open(os.path.join(HERE, "out_train.json"), "w"), indent=1)
    # plateau rule: family survivors = best config whose grid neighbours agree in sign
    fams = collections.defaultdict(list)
    for k, v in res.items():
        s = bt.stats(v)
        if s.get("n", 0) >= 100:
            fams[k.split("_")[0]].append((s["ret"], k, s))
    print()
    print("=== family bests (n>=100) ===")
    for f, lst in sorted(fams.items()):
        lst.sort(reverse=True)
        best = lst[0]
        pos = sum(1 for r, _, _ in lst if r > 0)
        print("%s best=%s ret=%+.2f%% t=%+.2f  (%d/%d configs positive)"
              % (f, best[1], best[0]*100, best[2]["t"], pos, len(lst)))

def val():
    rows, cd, F1, tr, va, te = load_all()
    C = candidates.build(F1)
    picks = json.load(open(os.path.join(HERE, "picks.json")))
    print("VALIDATION: %d markets, %d picks" % (len(va), len(picks)))
    for name in picks:
        fn = C[name]
        for h, tag in ((0.01, "h1"), (0.02, "h2"), (0.03, "h3")):
            t2 = run_one(fn, va, cd, h)
            print(line("%s[%s]" % (name, tag), t2))
        print()

def test():
    reg = json.load(open(os.path.join(HERE, "registered.json")))
    stamp = os.path.join(HERE, "test_consumed.stamp")
    if os.path.exists(stamp):
        print("TEST ALREADY CONSUMED — refusing to run again."); return
    rows, cd, F1, tr, va, te = load_all()
    C = candidates.build(F1)
    print("TEST (one-shot): %d markets, %d registered rules" % (len(te), len(reg["rules"])))
    out = {}
    for name in reg["rules"]:
        fn = C[name]
        for h, tag in ((0.01, "h1"), (0.02, "h2"), (0.03, "h3")):
            t2 = run_one(fn, te, cd, h)
            print(line("%s[%s]" % (name, tag), t2))
            if tag == "h2":
                s = bt.stats(t2); s["tclu"] = candidates.clustered_t(t2)
                # per-day pnl
                pd = collections.defaultdict(float)
                for t in t2: pd[t["t0"] // 86400] += t["r"]
                s["days_pos"] = sum(1 for v in pd.values() if v > 0)
                s["days"] = len(pd)
                out[name] = s
        print()
    json.dump(out, open(os.path.join(HERE, "out_test.json"), "w"), indent=1)
    open(stamp, "w").write("consumed")

def walkforward():
    rows, cd, F1, *_ = load_all()
    C = candidates.build(F1)
    picks = json.load(open(os.path.join(HERE, "picks.json")))
    # folds live strictly inside train+val (first 80%) — the test tail stays embargoed
    n = len(rows)
    folds = []
    for i in range(4):
        a = int(n * (0.50 + 0.075 * i))
        b = int(n * (0.50 + 0.075 * (i + 1)))
        folds.append(rows[a:b])
    for name in picks:
        fn = C[name]
        rets = []
        for i, fold in enumerate(folds):
            t2 = run_one(fn, fold, cd, 0.02)
            s = bt.stats(t2)
            rets.append(s.get("ret", 0) or 0)
            print("%s fold%d %s" % (name, i, line("", t2)))
        print("%s: %d/4 folds positive" % (name, sum(1 for r in rets if r > 0)))
        print()

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "phase0"
    dict(phase0=phase0, train=train, val=val, test=test, walkforward=walkforward)[cmd]()
