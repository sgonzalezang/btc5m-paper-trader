// An interval's strike (price to beat) is its own open, which is the SAME instant as the
// close of the minute-candle ending at t0. So a window's strike is knowable the moment it
// turns, and — crucially — stays recoverable after it closes, from the cache.
function strikeOf(t0){
  if(CND[t0]&&CND[t0].o!=null) return CND[t0].o;
  if(CND[t0-60]&&CND[t0-60].c!=null) return CND[t0-60].c;
  if(LAST&&LAST.feed&&LAST.feed.t0===t0&&LAST.feed.open!=null) return LAST.feed.open;
  return null;
}
// A window's SETTLE price is the price at its boundary instant — which is exactly the
// next window's open. Prefer that over the bot's recorded btcClose, which is the last
// 1-min candle it had seen and can lag the boundary by up to a minute: enough to call a
// near-the-line window the wrong way.
function settleOf(t0, botClose){
  const boundary=strikeOf(t0+300);
  return (boundary!=null)?boundary:((typeof botClose==="number")?botClose:null);
}
// Mirrors the bot's _clear_margin: max($15, 0.03% of price) ≈ $19 at $64k. Inside this
// band no spot feed can be trusted against Polymarket's oracle, so we decline to call it.
function clearMargin(px){ return Math.max(15, px*0.0003); }
function verdictOf(strike, settle){
  const d=settle-strike;
  if(Math.abs(d)<clearMargin(strike)) return {d:d, tooClose:true};
  return {d:d, tooClose:false, up:d>0};
}
async function tickBtc(){ const b=await fetchBtc(); if(b) BTCP=b; drawBtcBar(); }
function drawBtcBar(){
  const el=$("btcbar"); if(!el) return;
  const px=curPrice();
  if(px==null){ el.className="btcbar"; el.innerHTML='<span class="mut">BTC price unavailable</span>'; return; }
  const usd=v=>"$"+(+v).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});
  const now=Math.floor(Date.now()/1000), t0=Math.floor(now/300)*300, secsIn=now-t0;
  const live=!!(BTCP&&BTCP.live), src=(BTCP&&BTCP.src)||((LAST&&LAST.feed&&LAST.feed.src)||"feed");
  // GRACE WINDOW: for the first GRACE_S seconds of a new interval, keep showing the one that
  // just CLOSED — its strike and where BTC settled against it — instead of swapping to the new
  // reference the instant it stops mattering. Lets a viewer actually read the outcome.
  const pStrike=strikeOf(t0-300), pSettle=strikeOf(t0);   // settle == this window's open, same instant
  if(secsIn<GRACE_S && pStrike!=null && pSettle!=null){
    const v=verdictOf(pStrike,pSettle);
    el.className="btcbar closed";
    el.innerHTML=`<b class="btcpx">₿ ${usd(px)}</b>`
      +`<span class="mut">${esc(src)} · <b>last window closed</b> · beat</span> <b class="btcline">${usd(pStrike)}</b> `
      +`<span class="mut">settled</span> <b class="btcline">${usd(pSettle)}</b> `
      +(v.tooClose
        ?`<span class="prov" title="within $${clearMargin(pStrike).toFixed(0)} of the line — no spot feed can call this against Polymarket's oracle">… too close to call → oracle decides</span>`
        :v.up?`<b class="up">▲ +$${v.d.toFixed(2)} → Up won</b>`
             :`<b class="dn">▼ −$${Math.abs(v.d).toFixed(2)} → Down won</b>`)
      +`<span class="mut"> · new reference in ${GRACE_S-secsIn}s</span>`;
    return;
  }
  el.className="btcbar";
  const slug="btc-updown-5m-"+t0, open=strikeOf(t0), d=(open!=null)?px-open:null;
  const left=Math.max(0,(t0+300)-now), mmss=Math.floor(left/60)+":"+String(left%60).padStart(2,"0");
  const side = d==null?"" : d>0?`<b class="up">▲ +$${d.toFixed(2)} above → Up leads</b>`
                            : d<0?`<b class="dn">▼ −$${Math.abs(d).toFixed(2)} below → Down leads</b>`
                            : `<span class="mut">right at the line</span>`;
  el.innerHTML=`<b class="btcpx">₿ ${usd(px)}</b>`
    +`<span class="mut">${esc(src)} · <a class="pml" target="_blank" rel="noopener" href="https://polymarket.com/event/${slug}" title="BTC must close above this for Up, below it for Down — fixed for the whole 5-min window">price to beat</a></span> `
    +`<b class="btcline">${open!=null?usd(open):"—"}</b> ${side}`
    +`<span class="mut"> · ${mmss} to close${live?"":' · <b class="dn">feed blocked</b>'}</span>`;
}
