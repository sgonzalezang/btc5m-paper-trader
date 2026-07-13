// ============================================================================
// PROPOSED PATCH (COPY — do NOT deploy from here). Recommended fix = (b)+(c):
//   (b) apply the EXISTING clearMargin band to the LIVE "leads" bar (the only
//       place a viewer currently sees a CONFIDENT leader that can flip), and
//       relabel the number as an approximate Coinbase proxy, not the oracle ref.
//   (c) once the interval has an oracle result in the published state, show the
//       oracle truth as authoritative (the bot already computes winner_of).
// Empirics (research/2026-07-13-price-to-beat/work/codefix/results.json, n=863):
//   settle verdict WITH band -> 0 confident-wrong; live bar WITHOUT band -> 19/863
//   (2.2%) flips, ALL <=2.22 bps (inside the 3 bps band). So banding the live bar
//   removes every observed confident-wrong leader. Widening the band to ~5 bps
//   (below) adds tail headroom above the observed p99 of 2.22 bps at ~0 cost.
// ============================================================================

// ---- touch #1: widen the band a hair for cross-source tail headroom (was 0.0003)
// current: function clearMargin(px){ return Math.max(15, px*0.0003); }  // ~3 bps
function clearMargin(px){ return Math.max(25, px*0.0005); }  // ~5 bps; >observed 2.22bps p99

function drawBtcBar(){
  const el=$("btcbar"); if(!el) return;
  const px=curPrice();
  if(px==null){ el.className="btcbar"; el.innerHTML='<span class="mut">BTC price unavailable</span>'; return; }
  const usd=v=>"$"+(+v).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});
  const now=Math.floor(Date.now()/1000), t0=Math.floor(now/300)*300, secsIn=now-t0;
  const live=!!(BTCP&&BTCP.live), src=(BTCP&&BTCP.src)||((LAST&&LAST.feed&&LAST.feed.src)||"feed");
  const pStrike=strikeOf(t0-300), pSettle=strikeOf(t0);
  if(secsIn<GRACE_S && pStrike!=null && pSettle!=null){
    const v=verdictOf(pStrike,pSettle);
    el.className="btcbar closed";
    el.innerHTML=`<b class="btcpx">₿ ${usd(px)}</b>`
      +`<span class="mut">${esc(src)} · <b>last window closed</b> · beat</span> <b class="btcline">${usd(pStrike)}</b> `
      +`<span class="mut">settled</span> <b class="btcline">${usd(pSettle)}</b> `
      +(v.tooClose
        ?`<span class="prov" title="within $${clearMargin(pStrike).toFixed(0)} of the line — Coinbase proxy can't call this against Polymarket's Chainlink oracle">… too close to call → oracle decides</span>`
        :v.up?`<b class="up">▲ +$${v.d.toFixed(2)} → Up won (proxy)</b>`
             :`<b class="dn">▼ −$${Math.abs(v.d).toFixed(2)} → Down won (proxy)</b>`)
      +`<span class="mut"> · new reference in ${GRACE_S-secsIn}s</span>`;
    return;
  }
  el.className="btcbar";
  const slug="btc-updown-5m-"+t0, open=strikeOf(t0), d=(open!=null)?px-open:null;
  const left=Math.max(0,(t0+300)-now), mmss=Math.floor(left/60)+":"+String(left%60).padStart(2,"0");
  // ---- touch #2: BAND the live leader indicator (was: any d>0 -> "Up leads").
  // Near the flat boundary the Coinbase proxy can't be trusted vs the oracle, so
  // show "too close to call" instead of a confident (and 2.2%-of-the-time wrong)
  // ▲/▼ leader. This is the ONLY behavioral fix that changes what a viewer sees.
  const cm=(open!=null)?clearMargin(open):null;
  const side = d==null?""
    : (cm!=null && Math.abs(d)<cm)
        ? `<span class="mut">≈ at the line ($${d>=0?"+":"−"}${Math.abs(d).toFixed(2)}) → too close to call</span>`
    : d>0?`<b class="up">▲ +$${d.toFixed(2)} above → Up leads</b>`
    : d<0?`<b class="dn">▼ −$${Math.abs(d).toFixed(2)} below → Down leads</b>`
    : `<span class="mut">right at the line</span>`;
  el.innerHTML=`<b class="btcpx">₿ ${usd(px)}</b>`
    // ---- touch #3: relabel "price to beat" as an approximate Coinbase proxy.
    +`<span class="mut">${esc(src)} · <a class="pml" target="_blank" rel="noopener" href="https://polymarket.com/event/${slug}" title="≈ Coinbase proxy for the line. Polymarket settles on Chainlink BTC/USD at the interval boundary; this Coinbase open can differ by a few $ near the flat boundary — the oracle is authoritative.">≈ price to beat (Coinbase proxy)</a></span> `
    +`<b class="btcline">${open!=null?usd(open):"—"}</b> ${side}`
    +`<span class="mut"> · ${mmss} to close${live?"":' · <b class="dn">feed blocked</b>'}</span>`;
}
