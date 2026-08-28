"""Base rates: P(side wins | side price at offset T). The market is efficient
iff P(win|p)=p+fees. Any systematic gap IS the raw edge (before spread).
Also: comeback rates (price<=X late), and favorite-longshot shape."""
import json, math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bt

def main():
    rows, _ = bt.load()
    print(f"markets: {len(rows)}  ({(rows[-1]['t0']-rows[0]['t0'])/86400:.1f} days)")
    for at in (10, 70, 130, 190, 250):
        print(f"\n=== UP price at +{at}s vs P(up wins) ===")
        print(f"{'price bucket':<14}{'n':>6}{'P(up)':>8}{'implied':>9}{'gap':>7}")
        buckets = [(i/100.0, (i+10)/100.0) for i in range(0, 100, 10)]
        for lo, hi in buckets:
            sel = []
            for r in rows:
                p = bt.path_at(r, at, "up")
                # only markets whose LATEST point is fresh (within 65s of `at`)
                pts = [s for s, _ in r["path"] if s <= at]
                if p is None or not pts or at - pts[-1] > 65: continue
                if lo <= p < hi: sel.append(r["outcome"] == "up")
            if len(sel) < 30: continue
            n = len(sel); w = sum(sel) / n
            mid = sum((lo, hi)) / 2
            se = math.sqrt(w * (1 - w) / n)
            print(f"{lo:.2f}-{hi:.2f}    {n:>6}{w*100:>7.1f}%{mid*100:>8.1f}%{(w-mid)*100:>+6.1f} (se {se*100:.1f})")

if __name__ == "__main__":
    main()
