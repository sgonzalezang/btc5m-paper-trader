// BTC 5m tab test harness: mocked-network Chromium run + in-page unit drives.
const { chromium } = require('playwright-core');
const IVL = 300, TOK_UP = '111111', TOK_DN = '222222';
const nowSec = () => Math.floor(Date.now() / 1000);
let FAIL = 0;
const ok = (cond, name, extra) => {
  console.log((cond ? 'PASS' : 'FAIL') + '  ' + name + (extra ? '  [' + extra + ']' : ''));
  if (!cond) FAIL++;
};

function gammaEvent(ts) {
  // Market for interval [ts, ts+300). Resolved UP once the interval is >5s past.
  const done = nowSec() > ts + IVL + 5;
  return [{
    slug: 'btc-updown-5m-' + ts,
    title: 'Bitcoin Up or Down',
    closed: done,
    endDate: new Date((ts + IVL) * 1000).toISOString(),
    markets: [{
      question: 'Bitcoin Up or Down?',
      closed: done,
      umaResolutionStatus: done ? 'resolved' : 'initialized',
      endDate: new Date((ts + IVL) * 1000).toISOString(),
      clobTokenIds: JSON.stringify([TOK_UP, TOK_DN]),
      outcomes: JSON.stringify(['Up', 'Down']),
      outcomePrices: done ? JSON.stringify(['1', '0']) : JSON.stringify(['0.72', '0.28']),
      bestBid: done ? null : '0.71',
      bestAsk: done ? null : '0.75'   // ask 75c > 70c cap: live flow must NOT auto-enter
    }]
  }];
}
function candles(t0) {
  // Coinbase-shaped [time, low, high, open, close, vol], newest first.
  const rows = [];
  for (let t = t0 - 120; t <= nowSec() - (nowSec() % 60); t += 60) {
    const isT0 = t === t0;
    rows.unshift([t, 99900, 100200, isT0 ? 100000 : 99990, t >= t0 ? 100130 : 99998, 12.3]);
  }
  return rows;
}

(async () => {
  const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' });
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors = [];
  page.on('pageerror', e => errors.push('' + e));
  page.on('console', m => { if (m.type() === 'error') errors.push('console: ' + m.text()); });

  await page.route('**/*', route => {
    const url = route.request().url();
    if (url.startsWith('file://')) return route.continue();
    let body = null;
    const slugMatch = url.match(/gamma-api\.polymarket\.com\/events\?slug=btc-updown-5m-(\d+)/);
    if (slugMatch) body = gammaEvent(parseInt(slugMatch[1], 10));
    else if (/gamma-api\.polymarket\.com\/(events\?series_slug|public-search)/.test(url)) body = [];
    else if (/clob\.polymarket\.com\/book/.test(url)) {
      const up = url.indexOf(TOK_UP) >= 0;
      body = up
        ? { bids: [{ price: '0.71', size: '150' }], asks: [{ price: '0.75', size: '200' }] }
        : { bids: [{ price: '0.25', size: '150' }], asks: [{ price: '0.29', size: '200' }] };
    } else if (/api\.exchange\.coinbase\.com\/products\/BTC-USD\/candles/.test(url)) {
      const t0 = Math.floor(nowSec() / IVL) * IVL;
      body = candles(t0);
    } else if (/espn|fifa|binance|kraken/.test(url)) body = [];
    if (body !== null) return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
    return route.fulfill({ status: 404, body: '' });
  });

  await page.goto('file://' + require('path').resolve(__dirname, '..', 'index.html'));
  await page.waitForTimeout(800);
  if (await page.locator('#introGotit').isVisible().catch(() => false)) await page.click('#introGotit');

  // --- 1. plumbing: page loads, watcher runs against mocked live APIs ---
  ok(await page.locator('#btcWrap').count() === 1, 'standalone page renders');
  await page.click('#btcStart');
  await page.waitForTimeout(6500);
  const live = await page.locator('#btcLive').innerText();
  ok(/btc-updown-5m-\d+/.test(live), 'market discovered by slug', live.match(/btc-updown-5m-\d+/)?.[0]);
  ok(/\$100,130/.test(live), 'BTC last price from candle feed');
  ok(/\+\$130/.test(live), 'intra-interval move computed (+$130)');
  ok(/Coinbase/.test(live), 'feed source sticky label');
  ok(/71¢ \/ 75¢/.test(live), 'Up book bid/ask rendered');
  ok(/25¢ \/ 29¢/.test(live), 'Down book mirrored/rendered');
  const checks1 = await page.evaluate(() => BTC.lastEval && BTC.lastEval.checks.map(c => [c.k, c.ok]));
  ok(Array.isArray(checks1) && checks1.length === 10, 'all 10 guards evaluated');
  const askGuard = checks1.find(c => /Ask ≤/.test(c[0]));
  ok(askGuard && askGuard[1] === false, 'price cap guard blocks 75¢ ask');
  ok(await page.evaluate(() => STATE.btc.engines.strict.trades.length) === 0, 'strict does NOT enter while the ask-cap guard fails (needs 10/10)');
  // loose (6/10) is allowed to fire here — that is the point of the loose engine
  const looseN = await page.evaluate(() => STATE.btc.engines.loose.trades.length);
  const looseNeed = await page.evaluate(() => btcEngPass('loose'));
  ok(typeof looseN === 'number', 'loose engine present (needs ' + looseNeed + '/10)', looseN + ' loose trade(s) so far');
  const cd1 = await page.evaluate(() => btcCountdown());
  await page.waitForTimeout(2100);
  const cd2 = await page.evaluate(() => btcCountdown());
  ok(cd1 !== cd2, 'countdown ticking', cd1 + ' -> ' + cd2);

  // --- 2. unit drive: forced full-pass entry ---
  const r2 = await page.evaluate(() => {
    const now = Date.now(), nowS = Math.floor(now / 1000);
    BTC.mkt = { t0: nowS - 210, t1: nowS + 90, ev: true, evClosed: false, slug: 'btc-updown-5m-test1',
      tokUp: '111111', tokDown: '222222', upBid: 0.64, upAsk: 0.66, pUp: 0.65, gAt: now,
      bookUp: { bid: 0.64, ask: 0.66, topAskUsd: 132, mirrorTopUsd: 54, at: now },
      bookDown: { bid: 0.34, ask: 0.36, topAskUsd: 54, mirrorTopUsd: 132, at: now } };
    BTC.feed = { src: 'Coinbase', open: 100000, last: 100130, at: now, t0: BTC.mkt.t0 };
    BTC.prevQuote = { side: 'up', ask: 0.66, t: now - 4000 };
    const ev = btcEvaluate(now, 'strict');
    if (ev.enter) btcPaperEnter('strict', ev);
    const tr = STATE.btc.engines.strict.trades[0];
    return { all: ev.all, enter: ev.enter, fails: ev.checks.filter(c => !c.ok).map(c => c.k), side: ev.side,
      trade: tr && { side: tr.side, entry: tr.entry, stake: tr.stake, shares: tr.shares, status: tr.status } };
  });
  ok(r2.all === true && r2.enter === true, 'forced strict eval passes all 10 + enters', r2.fails.join(','));
  ok(r2.side === 'up', 'momentum side = up');
  ok(r2.trade && r2.trade.status === 'open' && Math.abs(r2.trade.entry - 0.67) < 1e-9, 'paper entry at 66¢ ask + 1¢ slippage');
  ok(r2.trade && Math.abs(r2.trade.shares - 5 / 0.67) < 0.01, 'share count = stake/fill');

  // duplicate-entry guard on the same interval
  const r2b = await page.evaluate(() => { const ev = btcEvaluate(Date.now(), 'strict'); return { all: ev.all, enter: ev.enter, fails: ev.checks.filter(c => !c.ok).map(c => c.k) }; });
  ok(r2b.enter === false && r2b.fails.some(k => /Risk caps/.test(k)), 'risk guard blocks second strict entry same interval');

  // --- 3. hedge trigger at extreme late skew ---
  const r3 = await page.evaluate(() => {
    const now = Date.now(), nowS = Math.floor(now / 1000);
    BTC.mkt.t1 = nowS + 40;                              // 40s left < hedgeLeft 45
    STATE.btc.engines.strict.trades[0].t1 = nowS + 40;   // trade tracks its own interval end
    BTC.mkt.bookUp = { bid: 0.96, ask: 0.98, topAskUsd: 100, mirrorTopUsd: 100, at: now };
    BTC.mkt.bookDown = { bid: 0.02, ask: 0.04, topAskUsd: 100, mirrorTopUsd: 100, at: now };
    btcManageOpen('strict', now);
    const tr = STATE.btc.engines.strict.trades[0];
    return tr.hedge && { stake: tr.hedge.stake, px: tr.hedge.px };
  });
  ok(r3 && r3.stake === 1 && Math.abs(r3.px - 0.05) < 1e-9, 'micro-hedge $1 at 1−bid + slip', JSON.stringify(r3));

  // --- 4. settlement via resolved market (UP wins → win + hedge loss) ---
  const r4 = await page.evaluate(() => {
    const tr = STATE.btc.engines.strict.trades[0];
    tr.status = 'pending'; tr.btcClose = 100150;
    btcApplySettle(tr, 'up', 'polymarket');
    return { result: tr.result, pnl: tr.pnl, shares: tr.shares, hstake: tr.hedge.stake };
  });
  // expected: shares - stake - hedge stake = 5/0.67 - 5 - 1
  const exp4 = +(5 / 0.67 - 5 - 1).toFixed(2);
  ok(r4.result === 'win' && Math.abs(r4.pnl - exp4) < 0.011, 'settle win P&L incl. hedge', r4.pnl + ' vs ' + exp4);

  // --- 5. stop-loss on BTC retrace ---
  const r5 = await page.evaluate(() => {
    const now = Date.now(), nowS = Math.floor(now / 1000);
    BTC.mkt = { t0: nowS - 100, t1: nowS + 200, ev: true, evClosed: false, slug: 'btc-updown-5m-test2',
      tokUp: '111111', tokDown: '222222', upBid: 0.6, upAsk: 0.62, gAt: now,
      bookUp: { bid: 0.45, ask: 0.5, topAskUsd: 100, mirrorTopUsd: 100, at: now },
      bookDown: { bid: 0.5, ask: 0.55, topAskUsd: 100, mirrorTopUsd: 100, at: now } };
    BTC.feed = { src: 'Coinbase', open: 100000, last: 100130, at: now, t0: BTC.mkt.t0 };
    STATE.btc.engines.strict.trades.unshift({ at: now, t0: BTC.mkt.t0, t1: BTC.mkt.t1, slug: BTC.mkt.slug, profile: 'conservative', eng: 'strict',
      side: 'up', entry: 0.62, stake: 5, shares: +(5 / 0.62).toFixed(4), btcOpen: 100000, btcEntry: 100130,
      btcClose: null, feed: 'Coinbase', status: 'open', hedge: null, pnl: null, result: null, settledBy: null });
    BTC.feed.last = 100130 - 260;                       // 0.26% retrace > 0.25% stop
    btcManageOpen('strict', Date.now());
    const tr = STATE.btc.engines.strict.trades[0];
    return { result: tr.result, pnl: tr.pnl, by: tr.settledBy };
  });
  const exp5 = +((5 / 0.62) * 0.45 - 5).toFixed(2);
  ok(r5.result === 'stopped' && r5.by === 'stop-loss' && Math.abs(r5.pnl - exp5) < 0.011, 'stop-loss exits at bid', r5.pnl + ' vs ' + exp5);

  // --- 6. pending settlement against the mocked resolved gamma event ---
  const past = Math.floor(nowSec() / IVL) * IVL - 2 * IVL;   // interval 2 slots ago → mock says resolved UP
  const r6 = await page.evaluate(async (past) => {
    STATE.btc.engines.strict.trades.unshift({ at: Date.now(), t0: past, t1: past + 300, slug: 'btc-updown-5m-' + past,
      profile: 'conservative', eng: 'strict', side: 'up', entry: 0.6, stake: 5, shares: 8.3333, btcOpen: 100000,
      btcEntry: 100100, btcClose: 100140, feed: 'Coinbase', status: 'pending', hedge: null, pnl: null, result: null, settledBy: null });
    BTC.resAt = 0;
    await btcSettlePending();
    const tr = STATE.btc.engines.strict.trades[0];
    return { result: tr.result, by: tr.settledBy, pnl: tr.pnl };
  }, past);
  ok(r6.result === 'win' && r6.by === 'polymarket', 'pending trade settles from resolved market', JSON.stringify(r6));

  // --- 7. daily loss cap gate ---
  const r7 = await page.evaluate(() => {
    STATE.btc.engines.strict.trades.unshift({ at: Date.now(), t0: 1, t1: 301, slug: 'x', profile: 'conservative', eng: 'strict', side: 'up',
      entry: 0.6, stake: 5, shares: 8, btcOpen: 1, btcEntry: 1, btcClose: null, feed: 'x',
      status: 'settled', hedge: null, pnl: -20, result: 'loss', settledBy: 'test' });   // > $10 cap on $100 bank
    save();
    const now = Date.now(), nowS = Math.floor(now / 1000);
    BTC.mkt = { t0: nowS - 210, t1: nowS + 90, ev: true, evClosed: false, slug: 'btc-updown-5m-test3',
      tokUp: '111111', tokDown: '222222', upBid: 0.64, upAsk: 0.66, gAt: now,
      bookUp: { bid: 0.64, ask: 0.66, topAskUsd: 132, mirrorTopUsd: 54, at: now },
      bookDown: { bid: 0.34, ask: 0.36, topAskUsd: 54, mirrorTopUsd: 132, at: now } };
    BTC.feed = { src: 'Coinbase', open: 100000, last: 100130, at: now, t0: BTC.mkt.t0 };
    const ev = btcEvaluate(now, 'strict');
    const riskFail = ev.checks.find(c => /Risk caps/.test(c.k));
    return { all: ev.all, enter: ev.enter, riskOk: riskFail.ok };
  });
  ok(r7.enter === false && r7.riskOk === false, 'daily loss cap blocks entries');

  // --- 8. persistence across reload ---
  const nBefore = await page.evaluate(() => STATE.btc.engines.strict.trades.length);
  await page.reload();
  await page.waitForTimeout(1200);
  const after = await page.evaluate(() => ({ n: STATE.btc.engines.strict.trades.length, on: STATE.btc.on }));
  ok(after.n === nBefore, 'ledger persists across reload', after.n + '/' + nBefore);
  ok(after.on === true, 'watcher state persists & resumes');
  await page.waitForTimeout(5500);
  const led = await page.locator('#btcLedger').innerText();
  ok(/WIN/.test(led) && /STOP/.test(led) && /LOSS/.test(led), 'ledger renders results');
  await page.screenshot({ path: __dirname + '/btc5m-tab.png', fullPage: false });

  // stop watcher to leave a clean screenshot state; check no page errors
  ok(errors.length === 0, 'no JS page errors', errors.slice(0, 3).join(' | '));
  await browser.close();
  console.log(FAIL ? ('\n' + FAIL + ' FAILURES') : '\nALL PASS');
  process.exit(FAIL ? 1 : 0);
})().catch(e => { console.error('HARNESS ERROR', e); process.exit(2); });
