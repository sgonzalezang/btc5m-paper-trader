// Full-lifecycle e2e: watcher discovers market, auto-enters in the entry
// window, interval rolls, trade settles from the resolved market. Real time,
// no manual driving. Runtime: up to ~7 minutes depending on clock position.
const { chromium } = require('playwright-core');
const IVL = 300, TOK_UP = '111111', TOK_DN = '222222';
const nowSec = () => Math.floor(Date.now() / 1000);
let FAIL = 0;
const ok = (c, n, x) => { console.log((c ? 'PASS' : 'FAIL') + '  ' + n + (x ? '  [' + x + ']' : '')); if (!c) FAIL++; };

function gammaEvent(ts) {
  const done = nowSec() > ts + IVL + 5;
  return [{
    slug: 'btc-updown-5m-' + ts, title: 'Bitcoin Up or Down', closed: done,
    endDate: new Date((ts + IVL) * 1000).toISOString(),
    markets: [{
      question: 'Bitcoin Up or Down?', closed: done,
      umaResolutionStatus: done ? 'resolved' : 'initialized',
      endDate: new Date((ts + IVL) * 1000).toISOString(),
      clobTokenIds: JSON.stringify([TOK_UP, TOK_DN]),
      outcomes: JSON.stringify(['Up', 'Down']),
      outcomePrices: done ? JSON.stringify(['1', '0']) : JSON.stringify(['0.65', '0.35']),
      bestBid: done ? null : '0.64', bestAsk: done ? null : '0.66'
    }]
  }];
}
function candles(t0) {
  const rows = [];
  for (let t = t0 - 120; t <= nowSec() - (nowSec() % 60); t += 60) {
    const isT0 = t === t0;
    rows.unshift([t, 99900, 100300, isT0 ? 100000 : 99990, t >= t0 ? 100140 : 99998, 12.3]);
  }
  return rows;
}

(async () => {
  const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' });
  const page = await browser.newPage({ viewport: { width: 1280, height: 1600 } });
  const errors = [];
  page.on('pageerror', e => errors.push('' + e));

  await page.route('**/*', route => {
    const url = route.request().url();
    if (url.startsWith('file://')) return route.continue();
    let body = null;
    const m = url.match(/gamma-api\.polymarket\.com\/events\?slug=btc-updown-5m-(\d+)/);
    if (m) body = gammaEvent(parseInt(m[1], 10));
    else if (/gamma-api\.polymarket\.com\/(events\?series_slug|public-search)/.test(url)) body = [];
    else if (/clob\.polymarket\.com\/book/.test(url))
      body = url.indexOf(TOK_UP) >= 0
        ? { bids: [{ price: '0.64', size: '150' }], asks: [{ price: '0.66', size: '200' }] }
        : { bids: [{ price: '0.34', size: '150' }], asks: [{ price: '0.36', size: '200' }] };
    else if (/api\.exchange\.coinbase\.com\/products\/BTC-USD\/candles/.test(url))
      body = candles(Math.floor(nowSec() / IVL) * IVL);
    else if (/espn|fifa|binance|kraken/.test(url)) body = [];
    if (body !== null) return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
    return route.fulfill({ status: 404, body: '' });
  });

  await page.goto('file://' + require('path').resolve(__dirname, '..', 'index.html'));
  await page.waitForTimeout(800);
  await page.evaluate(() => localStorage.clear());
  await page.reload(); await page.waitForTimeout(800);
  await page.click('#btcStart');
  console.log('watcher started; interval position now =', nowSec() % IVL, 's; waiting for entry window (150-240s)…');

  // wait until an entry happens (must occur in the first window we cross)
  let entered = false;
  for (let i = 0; i < 400; i++) {                 // up to ~400s
    await page.waitForTimeout(1000);
    const n = await page.evaluate(() => STATE.btc.engines.strict.trades.length);
    if (n > 0) { entered = true; break; }
  }
  ok(entered, 'watcher auto-entered a paper trade during the entry window');
  const tr1 = await page.evaluate(() => STATE.btc.engines.strict.trades[0]);
  ok(tr1.side === 'up' && Math.abs(tr1.entry - 0.67) < 1e-9, 'entered UP at 66¢ ask + 1¢ slippage', JSON.stringify({ side: tr1.side, entry: tr1.entry }));
  const posInIvl = IVL - (tr1.t1 - Math.floor(tr1.at / 1000));
  ok(tr1.t1 - Math.floor(tr1.at / 1000) >= 60 && tr1.t1 - Math.floor(tr1.at / 1000) <= 150, 'entry fell inside the 60-150s-left window', (tr1.t1 - Math.floor(tr1.at / 1000)) + 's left');

  // wait for the interval to close and the trade to settle from the resolved mock
  let settled = null;
  for (let i = 0; i < 240; i++) {
    await page.waitForTimeout(1000);
    settled = await page.evaluate(() => { const t = STATE.btc.engines.strict.trades[0]; return t.status === 'settled' ? t : null; });
    if (settled) break;
  }
  ok(!!settled, 'trade settled after interval close');
  ok(settled && settled.result === 'win' && settled.settledBy === 'polymarket', 'settled WIN via polymarket resolution', settled && JSON.stringify({ r: settled.result, by: settled.settledBy, pnl: settled.pnl }));
  ok(settled && Math.abs(settled.pnl - (settled.shares - settled.stake)) < 0.02, 'P&L = shares − stake', settled && ('' + settled.pnl));
  const oneOnly = await page.evaluate(() => STATE.btc.engines.strict.trades.length);
  ok(oneOnly === 1 || oneOnly === 2, 'no runaway re-entries (1 per interval)', '' + oneOnly);

  const log = await page.locator('#btcLogBox').innerText();
  ok(/\[STRICT\] ENTER BTC UP/.test(log), 'log shows STRICT ENTER line');
  ok(/WIN ✓/.test(log), 'log shows WIN settle line');
  await page.screenshot({ path: __dirname + '/btc5m-e2e.png', fullPage: false });
  ok(errors.length === 0, 'no JS page errors', errors.slice(0, 3).join(' | '));
  await browser.close();
  console.log(FAIL ? '\n' + FAIL + ' FAILURES' : '\nALL PASS');
  process.exit(FAIL ? 1 : 0);
})().catch(e => { console.error('HARNESS ERROR', e); process.exit(2); });
