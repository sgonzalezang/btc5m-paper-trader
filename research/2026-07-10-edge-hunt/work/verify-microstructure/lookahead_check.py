#!/usr/bin/env python3
"""Look-ahead attack: for a sample of the pm_prices_sample markets, re-fetch the
CLOB prices-history and record the actual timestamp of the point used as 'p20'
(nearest to t0+20, tolerance 90s). If points are stamped AFTER t0+20, the '20s'
snapshot contains future information relative to a ~t0+20s decision."""
import json, time, urllib.request

S = '/private/tmp/claude-501/-Users-sgonzalez/4f584d6e-5c8f-4a76-8bd9-6dcf248c8bf8/scratchpad'
UA = {"User-Agent": "Mozilla/5.0 (research; paper-trading study)"}

def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())

pm = json.load(open(S + '/data/pm_prices_sample.json'))
sample = pm[::18][:12]   # ~12 spread across the file
out = []
for r in sample:
    t0 = r['t0']
    try:
        ev = get(f"https://gamma-api.polymarket.com/events?slug=btc-updown-5m-{t0}")
        time.sleep(0.2)
        m = ev[0]['markets'][0]
        outcomes = json.loads(m['outcomes']); tokens = json.loads(m['clobTokenIds'])
        up_tok = tokens[outcomes.index('Up')]
        d = get(f"https://clob.polymarket.com/prices-history?market={up_tok}&startTs={t0-60}&endTs={t0+310}&fidelity=1")
        time.sleep(0.2)
        pts = sorted([(p['t'], p['p']) for p in d.get('history', [])])
        if not pts:
            out.append({'t0': t0, 'err': 'no pts'}); continue
        best = min(pts, key=lambda x: abs(x[0] - (t0 + 20)))
        off = best[0] - (t0 + 20)
        out.append({'t0': t0, 'p20_stored': r['p20'], 'p20_refetch': best[1],
                    'pt_offset_from_t0+20': off, 'n_pts': len(pts),
                    'pt_offsets_all': [p[0] - t0 for p in pts][:8]})
    except Exception as e:
        out.append({'t0': t0, 'err': str(e)})

for o in out: print(o)
offs = [o['pt_offset_from_t0+20'] for o in out if 'pt_offset_from_t0+20' in o]
post = sum(1 for x in offs if x > 0)
print(f"\npoints stamped AFTER t0+20: {post}/{len(offs)}; offsets: {sorted(offs)}")
match = [o for o in out if 'p20_refetch' in o and o['p20_stored'] is not None]
agree = sum(1 for o in match if abs(o['p20_refetch'] - o['p20_stored']) < 1e-9)
print(f"stored p20 equals refetch: {agree}/{len(match)}")
json.dump(out, open(S + '/work/verify-microstructure/lookahead_check.json', 'w'), indent=1)
