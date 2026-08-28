"""C1-C7 candidate strategies per the Fable-5 design doc, on the bt.py core.

Shared features:
  sigma1[minute]  stdev of 1-min log returns, trailing 60 completed minutes
  d(t)            log displacement interval-open -> last completed close
  p_fair          Phi(d / (sigma*sqrt(Tr/60)))
Decisions at +10/70/130/190/250s; a decision at +60*k reads only candles
closed by then. Selection gates use p_mkt + H2 (2c) per protocol; evaluate()
adds its own haircut for sensitivity.
"""
import math, os, sys, datetime, zoneinfo
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bt

CT = zoneinfo.ZoneInfo("America/Chicago")
H2 = 0.02
def phi(x): return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

class F:
    """Precomputed features over the candle set."""
    def __init__(self, cd):
        self.cd = cd
        ts = sorted(cd)
        self.sigma = {}
        rets = []
        for i, t in enumerate(ts):
            if i:
                a, b = cd[ts[i-1]], cd[t]
                if ts[i] - ts[i-1] == 60 and a[4] > 0 and b[4] > 0:
                    rets.append((t, math.log(b[4] / a[4])))
        win = []
        for t, r in rets:
            win.append((t, r))
            while win and win[0][0] < t - 3600: win.pop(0)
            if len(win) >= 30:
                xs = [x for _, x in win]
                m = sum(xs) / len(xs)
                self.sigma[t + 60] = (sum((x - m) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5
        # sigma[key] usable for decisions at minute key (built from candles closed before it)

    def sig(self, t):  # latest sigma at or before minute t
        t = t // 60 * 60
        for k in (t, t - 60, t - 120, t - 180):
            if k in self.sigma: return self.sigma[k]
        return None

    def strike_open(self, t0):
        c = self.cd.get(t0)
        return c[1] if c else None            # open of the t0 minute

    def disp(self, t0, at_s):
        """log displacement strike-open -> last COMPLETED candle close, and
        completed minutes m. at_s=70 -> m=1, 130 -> 2, 190 -> 3, 250 -> 4."""
        m = at_s // 60
        if m < 1: return None, 0
        o = self.strike_open(t0)
        c = self.cd.get(t0 + (m - 1) * 60)
        if not o or not c or c[4] <= 0 or o <= 0: return None, m
        return math.log(c[4] / o), m

    def p_fair_up(self, t0, at_s):
        d, m = self.disp(t0, at_s)
        s = self.sig(t0)
        if d is None or not s: return None
        tr = (300 - 60 * m) / 60.0
        if tr <= 0: return None
        return phi(d / (s * math.sqrt(tr)))

    def zscores(self, t0, at_s):
        d, m = self.disp(t0, at_s)
        s = self.sig(t0)
        if d is None or not s or m < 1: return None, None
        te = m * 1.0
        tr = (300 - 60 * m) / 60.0
        ze = d / (s * math.sqrt(te))
        return ze, (d, m, s, tr)

    def prev_impulse(self, t0):
        """z_prev and CLV of the PRIOR interval (5 candles t0-300..t0-60)."""
        cs = [self.cd.get(t0 - i * 60) for i in range(5, 0, -1)]
        if any(c is None for c in cs): return None, None
        o, c = cs[0][1], cs[-1][4]
        hi = max(x[2] for x in cs)
        lo = min(x[3] for x in cs)
        if o <= 0 or c <= 0: return None, None
        r = math.log(c / o)
        s = self.sig(t0)
        if not s: return None, None
        z = r / (s * math.sqrt(5.0))
        clv = (c - lo) / (hi - lo) if hi > lo else 0.5
        return z, clv

    def last_min_ret(self, t0, at_s):
        m = at_s // 60
        if m < 1: return None
        c = self.cd.get(t0 + (m - 1) * 60)
        if not c or c[1] <= 0: return None
        return math.log(c[4] / c[1])

def session_ct(t0):
    h = datetime.datetime.fromtimestamp(t0, CT).hour
    if 20 <= h < 24: return "NIGHT"
    if 0 <= h < 6:  return "ASIA"
    if 16 <= h < 20: return "USPM"
    return "OTHER"

def fresh_path(row, at_s, max_stale=65):
    pts = [s for s, _ in row["path"] if s <= at_s]
    return bool(pts) and (at_s - pts[-1]) <= max_stale

# ---- candidate factories: return dict name -> strat fn ----------------------
def build(F1):
    C = {}
    # C1 FAIRVAL
    for m_ in (0.06, 0.09, 0.12):
        for cap in (0.45, 0.55):
            for t0s in (70, 130):
                def s(row, cd, ctx, m_=m_, cap=cap, t0s=t0s):
                    if not fresh_path(row, t0s): return None
                    pf_up = F1.p_fair_up(row["t0"], t0s)
                    if pf_up is None: return None
                    u = bt.path_at(row, t0s, "up")
                    if u is None: return None
                    best = None
                    for side, p_mkt, pf in (("up", u, pf_up), ("down", round(1 - u, 4), 1 - pf_up)):
                        gap = pf - (p_mkt + H2)
                        if gap >= m_ and (p_mkt + H2) <= cap and (best is None or gap > best[0]):
                            best = (gap, side, p_mkt)
                    if best: return dict(side=best[1], p_mkt=best[2], at_s=t0s)
                C["C1_m%d_cap%d_t%d" % (int(m_*100), int(cap*100), t0s)] = s
    # C2 TRAIL-BAND
    for l in (0.58, 0.62, 0.66):
        for zmax in (0.7, 1.2):
            for t0s in (130, 190):
                def s(row, cd, ctx, l=l, zmax=zmax, t0s=t0s):
                    if not fresh_path(row, t0s): return None
                    u = bt.path_at(row, t0s, "up")
                    if u is None: return None
                    L = max(u, 1 - u)
                    if not (l <= L <= 0.75): return None
                    ze, _ = F1.zscores(row["t0"], t0s)
                    if ze is None or abs(ze) > zmax: return None
                    side = "down" if u >= 0.5 else "up"
                    return dict(side=side, p_mkt=round(1 - L, 4), at_s=t0s)
                C["C2_l%d_z%s_t%d" % (int(l*100), zmax, t0s)] = s
    # C3 IMPULSE-OPEN
    for zi in (1.5, 2.25):
        for clv_gate in (0, 1):
            for dr in ("cont", "rev"):
                for pcap in (0.45, 0.50):
                    def s(row, cd, ctx, zi=zi, clv_gate=clv_gate, dr=dr, pcap=pcap):
                        z, clv = F1.prev_impulse(row["t0"])
                        if z is None or abs(z) < zi: return None
                        if clv_gate and not (clv >= 0.75 if z > 0 else clv <= 0.25): return None
                        imp = "up" if z > 0 else "down"
                        side = imp if dr == "cont" else ("down" if imp == "up" else "up")
                        p = bt.path_at(row, 15, side)
                        if p is None or (p + H2) > pcap: return None
                        return dict(side=side, p_mkt=p, at_s=15)
                    C["C3_z%s_clv%d_%s_p%d" % (zi, clv_gate, dr, int(pcap*100))] = s
    # C4 LATE-COLLAPSE
    for pmax in (0.12, 0.18):
        for q in (0.5, 1.0):
            for t0s in (190, 250):
                def s(row, cd, ctx, pmax=pmax, q=q, t0s=t0s):
                    if not fresh_path(row, t0s): return None
                    u = bt.path_at(row, t0s, "up")
                    if u is None: return None
                    if u <= 1 - u:
                        side, p = "up", u
                    else:
                        side, p = "down", round(1 - u, 4)
                    if p > pmax: return None
                    ze, extra = F1.zscores(row["t0"], t0s)
                    if extra is None: return None
                    d, m, s_, tr = extra
                    if abs(d) > q * s_ * math.sqrt(tr): return None
                    return dict(side=side, p_mkt=p, at_s=t0s)
                C["C4_p%d_q%s_t%d" % (int(pmax*100), q, t0s)] = s
    # C5 LEADLAG-SNAP
    for w in (1.0, 1.5):
        for g in (0.08, 0.12):
            for t0s in (70, 130, 190):
                def s(row, cd, ctx, w=w, g=g, t0s=t0s):
                    if not fresh_path(row, t0s): return None
                    rl = F1.last_min_ret(row["t0"], t0s)
                    sg = F1.sig(row["t0"])
                    ze, extra = F1.zscores(row["t0"], t0s)
                    if rl is None or not sg or extra is None: return None
                    d = extra[0]
                    if d == 0 or rl == 0 or (d > 0) != (rl > 0): return None
                    if abs(rl) < w * sg: return None
                    side = "up" if d > 0 else "down"
                    pf = F1.p_fair_up(row["t0"], t0s)
                    if pf is None: return None
                    pf = pf if side == "up" else 1 - pf
                    p = bt.path_at(row, t0s, side)
                    if p is None: return None
                    if pf - (p + H2) < g or (p + H2) > 0.60: return None
                    return dict(side=side, p_mkt=p, at_s=t0s)
                C["C5_w%s_g%d_t%d" % (w, int(g*100), t0s)] = s
    # C6 NIGHT-TRAIL (frozen C2 middle: l=.60 zmax=1.0 t=130) x session gate
    for gate in ("NIGHT", "ASIA", "NIGHTASIA", "USPM"):   # USPM = negative control
        def s(row, cd, ctx, gate=gate):
            ss = session_ct(row["t0"])
            if gate == "NIGHTASIA":
                okg = ss in ("NIGHT", "ASIA")
            else:
                okg = (ss == gate)
            if not okg or not fresh_path(row, 130): return None
            u = bt.path_at(row, 130, "up")
            if u is None: return None
            L = max(u, 1 - u)
            if not (0.60 <= L <= 0.75): return None
            ze, _ = F1.zscores(row["t0"], 130)
            if ze is None or abs(ze) > 1.0: return None
            side = "down" if u >= 0.5 else "up"
            return dict(side=side, p_mkt=round(1 - L, 4), at_s=130)
        C["C6_%s" % gate] = s
    # C7 STREAK-FADE (needs row['streak'] precomputed by add_streaks)
    for k in (3, 4):
        for pcap in (0.44, 0.47):
            def s(row, cd, ctx, k=k, pcap=pcap):
                st = row.get("streak")
                if not st or not st[0] or st[1] < k: return None
                side = "down" if st[0] == "up" else "up"
                p = bt.path_at(row, 15, side)
                if p is None or (p + H2) > pcap: return None
                return dict(side=side, p_mkt=p, at_s=15)
            C["C7_k%d_p%d" % (k, int(pcap*100))] = s
    return C

def add_streaks(rows):
    """row['streak'] = (direction, run length) of consecutive identical
    outcomes ending at the market immediately before this one. Runs reset
    across gaps in the 300s grid."""
    by_t0 = {r["t0"]: r for r in rows}
    prev_dir, run, prev_t0 = None, 0, None
    for r in rows:
        if prev_t0 is None or r["t0"] - prev_t0 != 300:
            prev_dir, run = None, 0
        r["streak"] = (prev_dir, run)
        if prev_dir == r["outcome"]:
            run += 1
        else:
            prev_dir, run = r["outcome"], 1
        prev_t0 = r["t0"]
    return rows

def clustered_t(trades):
    """Day-clustered t-stat (CR0)."""
    if len(trades) < 2: return float("nan")
    rs = [t["r"] for t in trades]
    b = sum(rs) / len(rs)
    cl = {}
    for t in trades: cl.setdefault(t["t0"] // 86400, []).append(t["r"] - b)
    se = math.sqrt(sum(sum(v) ** 2 for v in cl.values())) / len(rs)
    return b / se if se > 0 else float("nan")
