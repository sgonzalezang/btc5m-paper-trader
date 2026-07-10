#!/usr/bin/env python3
"""Test (a): P(reversal | prior |move|>=12bps) by UTC hour / session / weekday.
Buffered open-to-open method per BRIEF: prior move = (o[t]-o[t-1])/o[t-1],
outcome = sign(c[t]-o[t]), ties count as Up.
Chronological split: first 2/3 TRAIN, last 1/3 TEST.
Headline p-values: moving-block bootstrap, block = 12 intervals (1h).
Fees: EV/share = q - p - 0.07*p*(1-p) at p=0.51 (live ledger median reversal entry).
"""
import json, time, random, math

S = '/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad'
random.seed(20260710)

d = json.load(open(f'{S}/data/cb5m.json'))
t, o, c = d['t'], d['o'], d['c']
n = len(t)

TH = 0.0012  # 12 bps
P_FILL = 0.51
QSTAR = P_FILL + 0.07 * P_FILL * (1 - P_FILL)

def session(hour):
    if hour < 7: return 'Asia'
    if hour < 13: return 'Europe'
    if hour < 21: return 'US'
    return 'Late'

# rows: one per interval index i (1..n-1)
rows = []
for i in range(1, n):
    r_prior = (o[i] - o[i-1]) / o[i-1]
    up = c[i] >= o[i]                       # tie -> Up
    trig = abs(r_prior) >= TH
    # reversal = next interval resolves opposite the prior move direction
    rev = (not up) if r_prior > 0 else (up if r_prior < 0 else False)
    tm = time.gmtime(t[i])
    rows.append(dict(i=i, trig=trig, rev=rev, hour=tm.tm_hour,
                     sess=session(tm.tm_hour), wkend=tm.tm_wday >= 5))

split = (2 * len(rows)) // 3
train, test = rows[:split], rows[split:]
print(f'n intervals={len(rows)} TRAIN={len(train)} TEST={len(test)}')
print(f'TRAIN span {time.strftime("%m-%d", time.gmtime(t[1]))}..{time.strftime("%m-%d", time.gmtime(t[split]))}, '
      f'TEST {time.strftime("%m-%d", time.gmtime(t[split+1]))}..{time.strftime("%m-%d", time.gmtime(t[-1]))}')
print(f'fill p={P_FILL} fee hurdle q*={QSTAR:.4f}')

def rate(sub):
    k = [r for r in sub if r['trig']]
    if not k: return 0, float('nan')
    return len(k), sum(r['rev'] for r in k) / len(k)

def ev(q):  # net EV per share at P_FILL
    return q - P_FILL - 0.07 * P_FILL * (1 - P_FILL)

# ---------- moving-block bootstrap ----------
def block_boot_diff(sub, in_a, B=12, R=4000):
    """Bootstrap dist of rev-rate(A) - rev-rate(not A) among triggers.
    sub: chronological rows; in_a: predicate. Returns (obs, two-sided p, boot se)."""
    m = len(sub)
    ta = [1 if (r['trig'] and in_a(r)) else 0 for r in sub]
    ra = [1 if (r['trig'] and in_a(r) and r['rev']) else 0 for r in sub]
    tb = [1 if (r['trig'] and not in_a(r)) else 0 for r in sub]
    rb = [1 if (r['trig'] and not in_a(r) and r['rev']) else 0 for r in sub]
    def pref(x):
        p = [0]
        for v in x: p.append(p[-1] + v)
        return p
    pta, pra, ptb, prb = map(pref, (ta, ra, tb, rb))
    nb = m // B
    starts_max = m - B
    def stat_from(starts):
        sta = sra = stb = srb = 0
        for s in starts:
            sta += pta[s+B] - pta[s]; sra += pra[s+B] - pra[s]
            stb += ptb[s+B] - ptb[s]; srb += prb[s+B] - prb[s]
        if sta == 0 or stb == 0: return None
        return sra/sta - srb/stb
    obs_a = (pra[m]/pta[m]) if pta[m] else float('nan')
    obs_b = (prb[m]/ptb[m]) if ptb[m] else float('nan')
    obs = obs_a - obs_b
    boots = []
    for _ in range(R):
        st = stat_from([random.randint(0, starts_max) for _ in range(nb)])
        if st is not None: boots.append(st)
    lo = sum(1 for b in boots if b <= 0) / len(boots)
    hi = sum(1 for b in boots if b >= 0) / len(boots)
    p2 = 2 * min(lo, hi)
    mu = sum(boots) / len(boots)
    se = math.sqrt(sum((b - mu) ** 2 for b in boots) / (len(boots) - 1))
    return obs, min(p2, 1.0), se

def block_boot_rate(sub, B=12, R=4000):
    """Bootstrap CI/p for rev-rate among triggers vs 0.5."""
    m = len(sub)
    tg = [1 if r['trig'] else 0 for r in sub]
    rv = [1 if (r['trig'] and r['rev']) else 0 for r in sub]
    def pref(x):
        p = [0]
        for v in x: p.append(p[-1] + v)
        return p
    ptg, prv = pref(tg), pref(rv)
    nb = m // B; starts_max = m - B
    obs = prv[m] / ptg[m] if ptg[m] else float('nan')
    boots = []
    for _ in range(R):
        stg = srv = 0
        for _ in range(nb):
            s = random.randint(0, starts_max)
            stg += ptg[s+B] - ptg[s]; srv += prv[s+B] - prv[s]
        if stg: boots.append(srv / stg)
    lo = sum(1 for b in boots if b <= 0.5) / len(boots)
    hi = sum(1 for b in boots if b >= 0.5) / len(boots)
    boots.sort()
    ci = (boots[int(0.025*len(boots))], boots[int(0.975*len(boots))])
    return obs, min(2 * min(lo, hi), 1.0), ci

out = {'meta': dict(n=len(rows), split=split, th_bps=12, p_fill=P_FILL, qstar=QSTAR)}

# ---------- unconditional baseline ----------
print('\n== Unconditional reversal rule (|prior|>=12bps) ==')
for name, sub in (('TRAIN', train), ('TEST', test), ('ALL', rows)):
    k, q = rate(sub)
    obs, p, ci = block_boot_rate(sub)
    print(f'{name}: n_trig={k} rev_rate={q:.4f} CI95=({ci[0]:.4f},{ci[1]:.4f}) p_vs_50={p:.4f} netEV/share={ev(q):+.4f}')
    out[f'uncond_{name}'] = dict(n=k, q=q, ci=ci, p_vs_50=p, net_ev=ev(q))

# ---------- by session ----------
print('\n== By session (TRAIN | TEST) ==')
out['session'] = {}
for s in ('Asia', 'Europe', 'US', 'Late'):
    ktr, qtr = rate([r for r in train if r['sess'] == s])
    kte, qte = rate([r for r in test if r['sess'] == s])
    obs, p, se = block_boot_diff(train, lambda r, s=s: r['sess'] == s, R=3000)
    print(f'{s:7s} TRAIN n={ktr:4d} q={qtr:.4f} (diff vs rest {obs:+.4f}, p={p:.4f}) | '
          f'TEST n={kte:4d} q={qte:.4f} netEV={ev(qte):+.4f}')
    out['session'][s] = dict(train_n=ktr, train_q=qtr, diff_train=obs, p_train=p,
                             test_n=kte, test_q=qte, test_ev=ev(qte))

# ---------- weekday vs weekend ----------
print('\n== Weekday vs weekend ==')
out['wk'] = {}
for lab, pred in (('weekday', lambda r: not r['wkend']), ('weekend', lambda r: r['wkend'])):
    ktr, qtr = rate([r for r in train if pred(r)])
    kte, qte = rate([r for r in test if pred(r)])
    obs, p, se = block_boot_diff(train, pred, R=3000)
    print(f'{lab:8s} TRAIN n={ktr:4d} q={qtr:.4f} (diff {obs:+.4f}, p={p:.4f}) | '
          f'TEST n={kte:4d} q={qte:.4f} netEV={ev(qte):+.4f}')
    out['wk'][lab] = dict(train_n=ktr, train_q=qtr, diff_train=obs, p_train=p,
                          test_n=kte, test_q=qte, test_ev=ev(qte))

# ---------- by hour (descriptive, TRAIN; then TEST for extremes) ----------
print('\n== By UTC hour (TRAIN n / q, TEST n / q) ==')
out['hour'] = {}
for h in range(24):
    ktr, qtr = rate([r for r in train if r['hour'] == h])
    kte, qte = rate([r for r in test if r['hour'] == h])
    out['hour'][h] = dict(train_n=ktr, train_q=qtr, test_n=kte, test_q=qte)
    print(f'h{h:02d} TRAIN {ktr:4d} {qtr:.3f} | TEST {kte:3d} {qte:.3f}')

# ---------- hour-bucket rule selected on TRAIN, evaluated on TEST ----------
# pick hours whose TRAIN q clears qstar with n>=40, evaluate that set on TEST
sel = [h for h in range(24) if out['hour'][h]['train_n'] >= 40 and out['hour'][h]['train_q'] > QSTAR]
kte, qte = rate([r for r in test if r['hour'] in sel])
print(f'\nTRAIN-selected hours (q>q*, n>=40): {sel}')
print(f'TEST on selected hours: n={kte} q={qte:.4f} netEV={ev(qte):+.4f}')
out['hour_rule'] = dict(selected=sel, test_n=kte, test_q=qte, test_ev=ev(qte))

# same for sessions: keep sessions clearing q* on TRAIN
sel_s = [s for s in ('Asia','Europe','US','Late') if out['session'][s]['train_q'] > QSTAR and out['session'][s]['train_n'] >= 100]
kte, qte = rate([r for r in test if r['sess'] in sel_s])
print(f'TRAIN-selected sessions (q>q*): {sel_s}')
print(f'TEST on selected sessions: n={kte} q={qte:.4f} netEV={ev(qte):+.4f}')
out['session_rule'] = dict(selected=sel_s, test_n=kte, test_q=qte, test_ev=ev(qte))

json.dump(out, open(f'{S}/work/seasonality/a_results.json', 'w'), indent=1)
print(f'\nsaved -> {S}/work/seasonality/a_results.json')
