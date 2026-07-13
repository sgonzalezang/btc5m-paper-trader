#!/usr/bin/env python3
"""Adversarial re-derivation of the boundary-timing CLAIM, STDLIB only.
Recomputes everything from meta_rows.json raw ISO strings (does NOT trust the
precomputed *_minus_t0 fields) and cross-checks t0<->title<->endDate alignment."""
import json, statistics as st
from datetime import datetime, timezone

rows = json.load(open("/Users/sgonzalez/btc5m-paper-trader/research/2026-07-13-price-to-beat/work/source/meta_rows.json"))
ok = [r for r in rows if r.get("ok")]

def iso_s(s):
    if not s: return None
    s=s.replace("Z","+00:00")
    # normalize fractional seconds to 6 digits (handles 5-digit micros)
    if "." in s:
        head,rest=s.split(".",1)
        tz=""
        for i,c in enumerate(rest):
            if c in "+-":
                tz=rest[i:]; rest=rest[:i]; break
        rest=(rest+"000000")[:6]
        s=head+"."+rest+tz
    return int(datetime.fromisoformat(s).timestamp())

end_diffs=[]; uma_diffs=[]; start_diffs=[]; sd_vals=set()
slug_t0_mismatch=[]; end_ne_300=[]; title_align_fail=[]
for r in ok:
    t0=r["t0"]
    # 1) slug encodes t0?
    slug_t0=int(r["slug"].split("-")[-1])
    if slug_t0!=t0: slug_t0_mismatch.append((r["slug"],t0))
    # 2) recompute from raw ISO, ignore cached fields
    endS=iso_s(r["endDate"]); startS=iso_s(r["startDate"]); umaS=iso_s(r["umaEndDate"])
    ed=endS-t0
    end_diffs.append(ed)
    if ed!=300: end_ne_300.append((r["slug"],ed))
    if umaS is not None: uma_diffs.append(umaS-t0)
    if startS is not None: start_diffs.append(startS-t0)
    sd_vals.add(r.get("secondsDelay"))
    # 3) title window-start alignment: t0 should be the "beginning" minute in ET
    # derive UTC minute-of-t0 and confirm endDate = t0+300 lands on a 5-min UTC boundary
    dt=datetime.fromtimestamp(t0,tz=timezone.utc)
    if dt.second!=0 or dt.minute%5!=0:
        title_align_fail.append((r["slug"],dt.isoformat()))

out={
 "n_ok":len(ok),
 "secondsDelay_distinct":[str(v) for v in sd_vals],
 "endDate_minus_t0":{"distinct":sorted(set(end_diffs)),"all_300":all(e==300 for e in end_diffs),"n_ne_300":len(end_ne_300),"examples_ne":end_ne_300[:5]},
 "umaEndDate_minus_t0":{"n":len(uma_diffs),"min":min(uma_diffs),"max":max(uma_diffs),"median":st.median(uma_diffs)},
 "startDate_minus_t0":{"n":len(start_diffs),"min":min(start_diffs),"max":max(start_diffs),"median":st.median(start_diffs)},
 "slug_t0_mismatch":slug_t0_mismatch,
 "t0_not_on_5min_utc_boundary":title_align_fail,
}
print(json.dumps(out,indent=2))
json.dump(out,open("/Users/sgonzalez/btc5m-paper-trader/research/2026-07-13-price-to-beat/work/verify/boundary_recomputed.json","w"),indent=2)
