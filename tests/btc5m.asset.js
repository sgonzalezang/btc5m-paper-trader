// Asset-switch harness: verify ETH + DOGE discovery, feeds, %-move guard.
const { chromium } = require('playwright-core');
const IVL = 300;
const nowSec = () => Math.floor(Date.now() / 1000);
let FAIL = 0;
const ok = (c, n, x) => { console.log((c ? 'PASS' : 'FAIL') + '  ' + n + (x ? '  [' + x + ']' : '')); if (!c) FAIL++; };

const SPOT = { 'ETH-USD': 2500, 'DOGE-USD': 0.12 };            // open prices
const MOVE = { 'ETH-USD': 3.0, 'DOGE-USD': 0.000144 };         // ≥0.10% moves (0.12% of open)

(async () => {
  const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' });
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors = [];
  page.on('pageerror', e => errors.push('' + e));

  await page.route('**/*', route => {
    const url = route.request().url();
    if (url.startsWith('file://')) return route.continue();
    let body = null;
    const m = url.match(/gamma-api\.polymarket\.com\/events\?slug=((eth|doge)-updown-5m)-(\d+)/);
    if (m) {
      const ts = parseInt(m[3], 10);
      body = [{ slug: m[1] + '-' + ts, title: 'Up or Down', closed: false,
        endDate: new Date((ts + IVL) * 1000).toISOString(),
        markets: [{ question: 'Up or Down?', closed: false, umaResolutionStatus: 'initialized',
          endDate: new Date((ts + IVL) * 1000).toISOString(),
          clobTokenIds: JSON.stringify(['333', '444']), outcomes: JSON.stringify(['Up', 'Down']),
          outcomePrices: JSON.stringify(['0.60', '0.40']), bestBid: '0.58', bestAsk: '0.62' }] }];
    } else if (/gamma-api\.polymarket\.com\/(events\?(slug|series_slug)|public-search)/.test(url)) body = [];
    else if (/clob\.polymarket\.com\/book/.test(url))
      body = { bids: [{ price: '0.58', size: '200' }], asks: [{ price: '0.62', size: '200' }] };
    else if (/api\.exchange\.coinbase\.com\/products\/(ETH-USD|DOGE-USD)\/candles/.test(url)) {
      const pair = url.match(/products\/([A-Z-]+)\/candles/)[1];
      const t0 = Math.floor(nowSec() / IVL) * IVL, open = SPOT[pair], rows = [];
      for (let t = t0 - 120; t <= nowSec() - (nowSec() % 60); t += 60)
        rows.unshift([t, open * 0.999, open * 1.002, t === t0 ? open : open * 0.9999, t >= t0 ? open + MOVE[pair] : open * 0.9999, 5]);
      body = rows;
    } else if (/binance|kraken|BTC-USD/.test(url)) body = [];
    if (body !== null) return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
    return route.fulfill({ status: 404, body: '' });
  });

  await page.goto('file://' + require('path').resolve(__dirname, '..', 'index.html'));
  await page.waitForTimeout(600);
  await page.evaluate(() => localStorage.clear());
  await page.reload(); await page.waitForTimeout(600);

  // ETH
  await page.selectOption('#btcAsset', 'ETH');
  await page.click('#btcStart');
  await page.waitForTimeout(6000);
  let live = await page.locator('#btcLive').innerText();
  ok(/eth-updown-5m-\d+/.test(live), 'ETH market discovered', live.match(/eth-updown-5m-\d+/)?.[0]);
  ok(/\$2,503/.test(live), 'ETH price from ETH-USD candles');
  ok(/\+\$3\.00/.test(live), 'ETH delta 2-decimal formatting');
  let mv = await page.evaluate(() => BTC.lastEval.checks.find(c => /Move ≥/.test(c.k)));
  ok(mv && mv.ok === true, 'ETH %-move guard passes ($3 ≥ 0.10% of $2500=$2.50)', JSON.stringify(mv && mv.v));

  // DOGE (sub-$1 formatting + % threshold scaling)
  await page.selectOption('#btcAsset', 'DOGE');
  await page.waitForTimeout(6000);
  live = await page.locator('#btcLive').innerText();
  ok(/doge-updown-5m-\d+/.test(live), 'DOGE market discovered after switch', live.match(/doge-updown-5m-\d+/)?.[0]);
  ok(/\$0\.12/.test(live), 'DOGE price sub-$1 formatting');
  mv = await page.evaluate(() => BTC.lastEval.checks.find(c => /Move ≥/.test(c.k)));
  ok(mv && mv.ok === true, 'DOGE %-move guard scales ($0.000144 ≥ 0.10% of $0.12=$0.00012)', JSON.stringify(mv && mv.v));
  const asset = await page.evaluate(() => STATE.btc.asset);
  ok(asset === 'DOGE', 'asset persisted in state');
  ok(errors.length === 0, 'no JS page errors', errors.slice(0, 3).join(' | '));
  await browser.close();
  console.log(FAIL ? '\n' + FAIL + ' FAILURES' : '\nALL PASS');
  process.exit(FAIL ? 1 : 0);
})().catch(e => { console.error('HARNESS ERROR', e); process.exit(2); });
