#!/usr/bin/env python3
"""Independent adversarial reproduction (lens: fees, fills, market reality).
Recomputes every headline number of the FILL MODEL finding from data/ only,
then attacks: exact fee formula, fillFrac, exit/hedge legs, censoring bias in
the ask-vs-c20 join, and net edge vs q*(p) at honest fills."""
import json, math
from collections import defaultdict

B = '/Users/sgonzalez/btc5m-paper-trader/research/2026-07-10-edge-hunt'
pm = json.load(open(B+'/data/pm_prices_sample.json'))
tr = json.load(open(B+'/data/trades.json'))
cb = json.load(open(B+'/data/cb5m.json'))
cbt, cbo, cbc = cb['t'], cb['o'], cb['c']
cbi = {int(t): i for i, t in enumerate(cbt)}

def prior_bps(t0):
    i, j = cbi.get(t0), cbi.get(t0-300)
    if i is None or j is None: return None
    return (cbo[i]-cbo[j])/cbo[j]*1e4

def q(xs, qs=(0.05,0.1,0.25,0.5,0.75,0.9,0.95)):
    xs = sorted(xs); n = len(xs); out = {}
    for qq in qs:
        k = qq*(n-1); f = int(math.floor(k)); c = min(f+1, n-1)
        out[f'p{int(qq*100)}'] = round(xs[f]+(k-f)*(xs[c]-xs[f]), 4)
    return out

def qstar(p): return p + 0.07*p*(1-p)

R = {}
# ---- 1) pm-sample uncensored contrarian distribution ----
sig = []
for r in pm:
    b = prior_bps(r['t0'])
    if b is None or abs(b) < 12: continue
    c20 = r['p20'] if b < 0 else round(1-r['p20'],4)
    won = r['up_won'] if b < 0 else 1-r['up_won']
    sig.append(dict(t0=r['t0'], bps=b, c20=c20, won=won))
c20s = [s['c20'] for s in sig]
avail = sum(1 for s in sig if s['c20']+0.01 <= 0.55)/len(sig)
R['pm_sample'] = dict(n=len(sig), of=len(pm), c20_q=q(c20s), avail=round(avail,4),
                      win=round(sum(s['won'] for s in sig)/len(sig),4))
sub1 = sorted(s['c20'] for s in sig if 12<=abs(s['bps'])<16)
sub2 = sorted(s['c20'] for s in sig if abs(s['bps'])>=16)
R['by_move'] = dict(med_12_16=sub1[len(sub1)//2], med_ge16=sub2[len(sub2)//2],
                    n1=len(sub1), n2=len(sub2))

# ---- 2) ledger family ----
fam = [t for t in tr if t['eng'] in ('reversal','reversal2','latentfire')
       and t['src']=='current' and t['status']=='settled']
ents = [t['entry'] for t in fam]; asks = [t['ask'] for t in fam]
sh = sum(t['shares'] for t in fam)
pbar = sum(t['shares']*t['entry'] for t in fam)/sh
wr = sum(1 for t in fam if t['result']=='win')/len(fam)
pnl = sum(t['pnl'] for t in fam)
mis = sum(t['shares']*((1.0 if t['result']=='win' else 0.0)-t['entry']) for t in fam)
fee = sum((t.get('feeEntry') or 0)+(t.get('feeExit') or 0)+(t.get('gas') or 0) for t in fam)
R['ledger'] = dict(n=len(fam), entry_q=q(ents), ask_q=q(asks), wtd_entry=round(pbar,4),
                   qstar=round(qstar(pbar),4), winrate=round(wr,4), pnl=round(pnl,2),
                   misprice=round(mis,2), fees=round(fee,2))

# ---- 3) fee-formula exactness, fillFrac, exit legs ----
maxerr = max(abs((t.get('feeEntry') or 0) - t['shares']*0.07*t['entry']*(1-t['entry'])) for t in fam)
R['fee_check'] = dict(max_abs_fee_err=round(maxerr,6),
                      fillfrac_all_1=all(t.get('fillFrac')==1.0 for t in fam),
                      n_feeExit_pos=sum(1 for t in fam if (t.get('feeExit') or 0)>0),
                      n_hedge=sum(1 for t in fam if t.get('hedge')),
                      n_stopped=sum(1 for t in fam if t.get('result')=='stopped'),
                      n_entry_gt_56=sum(1 for t in fam if t['entry']>0.56),
                      n_ask_gt_55=sum(1 for t in fam if t['ask']>0.55),
                      slip_vals=sorted(set(round(t['entry']-t['ask'],4) for t in fam)))

# ---- 4) join + censoring attack ----
fam_by = defaultdict(list)
for t in fam: fam_by[t['t0']].append(t)
join = []
for s in sig:
    for t in fam_by.get(s['t0'], []):
        join.append(dict(d=round(t['ask']-s['c20'],4), c20=s['c20'], ask=t['ask'],
                         entry=t['entry'], won=1 if t['result']=='win' else 0))
ds = sorted(j['d'] for j in join)
R['join'] = dict(n=len(join), med=ds[len(ds)//2] if ds else None,
                 mean=round(sum(ds)/len(ds),4) if ds else None)
# censoring: join is conditioned on the fill existing (ask+1c<=55c).
lo = [j['d'] for j in join if j['c20'] <= 0.54]
hi = [j['d'] for j in join if j['c20'] > 0.54]
R['join_censor'] = dict(n_lo=len(lo), lo_mean=round(sum(lo)/len(lo),4) if lo else None,
                        lo_med=sorted(lo)[len(lo)//2] if lo else None,
                        n_hi=len(hi), hi_mean=round(sum(hi)/len(hi),4) if hi else None)

# ---- 5) fillability ----
t0lo = min(t['t0'] for t in fam); t0hi = max(t['t0'] for t in fam)
elig = [t0 for t0 in (int(x) for x in cbt) if t0lo <= t0 <= t0hi
        and (lambda b: b is not None and abs(b)>=12)(prior_bps(t0))]
R['fillability'] = dict(eligible=len(elig), entered=len(set(t['t0'] for t in fam)),
                        rate=round(len(set(t['t0'] for t in fam))/len(elig),4))

# ---- 6) chronological last-third win rate ----
fam_s = sorted(fam, key=lambda t: t['t0'])
n3 = len(fam_s)//3
last = fam_s[-n3:]; last50 = fam_s[-50:]
R['last_third'] = dict(n=len(last), win=round(sum(1 for t in last if t['result']=='win')/len(last),4),
                       n50_win=round(sum(1 for t in last50 if t['result']=='win')/50,4))

# ---- 7) NET EDGE at honest fills (the refute test) ----
# (a) live realized: wr vs qstar(pbar)
R['edge_live'] = dict(wr=round(wr,4), qstar=round(qstar(pbar),4),
                      edge_pp=round((wr-qstar(pbar))*100,2))
# (b) uncensored pm-sample: contrarian win rate vs cost at c20+1c honest fill, with >55c = skip
fills = [(s['c20']+0.01, s['won']) for s in sig if s['c20']+0.01 <= 0.55]
ev = sum(w - p - 0.07*p*(1-p) for p, w in fills)/len(fills)
pbar2 = sum(p for p,_ in fills)/len(fills)
wr2 = sum(w for _,w in fills)/len(fills)
R['edge_uncensored_pm'] = dict(n=len(fills), fill_mean=round(pbar2,4), win=round(wr2,4),
                               qstar=round(qstar(pbar2),4), ev_per_share=round(ev,4))
# (c) join-set: EV at real ledger fills vs at c20+1c model fills (conservatism direction)
if join:
    ev_led = sum(j['won'] - j['entry'] - 0.07*j['entry']*(1-j['entry']) for j in join)/len(join)
    ev_mod = sum(j['won'] - (j['c20']+0.01) - 0.07*(j['c20']+0.01)*(1-(j['c20']+0.01)) for j in join)/len(join)
    R['edge_join'] = dict(n=len(join), ev_ledger=round(ev_led,4), ev_model_c20=round(ev_mod,4))

print(json.dumps(R, indent=1))
json.dump(R, open(B+'/work/verify-microstructure/repro_feesfills_v2.json','w'), indent=1)
