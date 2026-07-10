#!/usr/bin/env python3
"""Follow-up: (e1) direction of proxy-vs-actual disagreements in flattest bucket;
(e2) pooled quiet deciles D0-D2 P(Up) on TRAIN/TEST with block bootstrap;
(e3) quiet-AND-session interaction quick look on TEST."""
import json, math, random

SCRATCH = '/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad'
D, W = SCRATCH + '/data/', SCRATCH + '/work/tieflat/'
cb = json.load(open(D + 'cb5m.json'))
t, o, c = cb['t'], cb['o'], cb['c']
n = len(t); idx = {tt: i for i, tt in enumerate(t)}
mv = [(c[i]-o[i])/o[i]*1e4 for i in range(n)]
def tvol(i):
    if i < 12 or t[i]-t[i-12] != 3600: return None
    return sum(abs(mv[j]) for j in range(i-12, i))/12.0
rows = [(i, tvol(i)) for i in range(12, n)]
rows = [(i, tv) for i, tv in rows if tv is not None]
split = int(len(rows)*2/3)
tv_train = sorted(tv for _, tv in rows[:split])
edges = [tv_train[int(len(tv_train)*k/10)] for k in range(1, 10)]
def dec(tv):
    d = 0
    for e in edges:
        if tv >= e: d += 1
        else: break
    return d

out = {}
# (e1) disagreement direction, |move|<1bps
pm = json.load(open(D + 'pm_res_3d.json'))
p2a_upDown = a2p_downUp = 0  # proxy Up/actual Down ; proxy Down/actual Up
sub = []
for t0, upw in pm:
    i = idx.get(t0)
    if i is None: continue
    if abs(mv[i]) < 1.0:
        proxy = 1 if c[i] >= o[i] else 0
        sub.append((t0, mv[i], proxy, upw))
        if proxy == 1 and upw == 0: p2a_upDown += 1
        if proxy == 0 and upw == 1: a2p_downUp += 1
print(f'(e1) |move|<1bps n={len(sub)}: proxyUp/actualDown={p2a_upDown}, proxyDown/actualUp={a2p_downUp}')
out['e1'] = {'n': len(sub), 'proxyUp_actualDown': p2a_upDown, 'proxyDown_actualUp': a2p_downUp}
# among proxy-near-tie (|move|<0.25bps) what does the oracle do?
tiny = [(t0, m, pr, uw) for t0, m, pr, uw in sub if abs(m) < 0.25]
print(f'     |move|<0.25bps n={len(tiny)} actualUp={sum(x[3] for x in tiny)}')
out['e1_tiny'] = {'n': len(tiny), 'actual_up': sum(x[3] for x in tiny)}

# (e2) pooled D0-D2 quiet, TRAIN/TEST, block bootstrap
def block_boot(sub_iu, nboot=4000, seed=17):
    rnd = random.Random(seed); blocks = {}
    for i, u in sub_iu: blocks.setdefault(i//12, []).append(u)
    bids = list(blocks.values()); B = len(bids); st = []
    for _ in range(nboot):
        tot = w = 0
        for _ in range(B):
            b = bids[rnd.randrange(B)]; tot += len(b); w += sum(b)
        if tot: st.append(w/tot)
    st.sort(); return st

train, test = rows[:split], rows[split:]
for name, part in (('train', train), ('test', test)):
    s = [(i, 1 if c[i] >= o[i] else 0) for i, tv in part if dec(tv) <= 2]
    m = len(s); w = sum(u for _, u in s)
    bs = block_boot(s)
    pv = sum(1 for x in bs if x <= 0.5)/len(bs)
    print(f'(e2) D0-D2 {name}: n={m} P(Up)={w/m:.4f} bootP(>0.5)={pv:.4f} ci=[{bs[100]:.3f},{bs[3899]:.3f}]')
    out[f'e2_{name}'] = {'n': m, 'p_up': w/m, 'boot_p': pv, 'ci': [bs[100], bs[3899]]}

# (e3) quiet (D0-D2) x session on TEST
def sess(h):
    return 'Asia' if h < 8 else ('EU' if h < 16 else 'US')
for s_ in ('Asia', 'EU', 'US'):
    sub2 = [(i, 1 if c[i] >= o[i] else 0) for i, tv in test if dec(tv) <= 2 and sess((t[i]//3600) % 24) == s_]
    m = len(sub2); w = sum(u for _, u in sub2)
    print(f'(e3) TEST quiet x {s_}: n={m} P(Up)={w/m if m else float("nan"):.4f}')
    out[f'e3_{s_}'] = {'n': m, 'p_up': w/m if m else None}

json.dump(out, open(W + 'result_e.json', 'w'), indent=1)
print('saved', W + 'result_e.json')
