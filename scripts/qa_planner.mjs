// Run with PLAYWRIGHT_MODULE pointing to an installed playwright package if it is not local.
import { createRequire } from 'node:module';
import { mkdir, writeFile } from 'node:fs/promises';
import { sep } from 'node:path';
import assert from 'node:assert/strict';
import { makeTrip, makeStop } from '../src/planner-core.mjs';
const require = createRequire(import.meta.url);
const { chromium, webkit } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.PLANNER_URL || process.argv[2] || 'http://127.0.0.1:8767/planner.html';
const out = (process.env.PLANNER_QA_OUTPUT || new URL('../QA/planner/', import.meta.url).pathname).replace(/[\\/]$/, '') + sep;
await mkdir(out, { recursive: true });
const results = [];
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, serviceWorkers: 'block' });
const page = await context.newPage(), errors = [];
page.on('pageerror', error => errors.push(error.message));
const stored = () => page.evaluate(() => JSON.parse(localStorage.getItem('fieldtrip.plans.v1')));
try {
  await page.goto(base); await page.locator('.stop').first().waitFor();
  assert.equal(await page.locator('.day-chip').count(), 11); results.push('All 11 canonical days load');
  await page.locator('.day-chip').nth(2).click();
  await page.waitForFunction(() => document.querySelectorAll('.route-pin').length > 2);
  await page.waitForTimeout(1500);
  await page.screenshot({ path: `${out}desktop-day.png` });
  assert.equal(await page.locator('#mapError').isVisible(), false); results.push('California map and numbered route pins load');
  await page.getByRole('button', { name: 'Whole trip', exact: true }).click();
  assert.equal(await page.locator('.overview-card').count(), 11);
  await page.screenshot({ path: `${out}desktop-overview.png` }); results.push('Whole-trip overview and map display all days');
  await page.getByRole('button', { name: 'Create a new trip' }).click();
  await page.locator('[name=name]').fill('QA weekend'); await page.locator('[name=destination]').fill('San Francisco');
  await page.locator('[name=count]').fill('2'); await page.getByRole('button', { name: 'Create trip', exact: true }).click();
  assert.equal(await page.locator('.day-chip').count(), 2); results.push('Create a separate reusable trip');
  async function add(name, lat, lng) {
    await page.getByRole('button', { name: 'Add a place or a break' }).click(); await page.getByRole('button', { name: 'Custom place', exact: false }).click();
    await page.locator('[name=name]').fill(name); await page.locator('[name=lat]').fill(lat); await page.locator('[name=lng]').fill(lng);
    await page.getByRole('button', { name: 'Add to my day' }).click();
  }
  await add('Waterfront start', '37.79554', '-122.39343'); await add('Coffee & a view', '37.8067', '-122.4053'); await add('Park picnic', '37.808', '-122.417');
  assert.equal(await page.locator('.stop').count(), 3); assert.equal(await page.locator('.travel-link').count(), 2); results.push('Add custom places and instant route estimates');
  const before = await page.locator('.stop-time').last().textContent();
  await page.locator('.edit-stop').first().click(); await page.locator('[name=duration]').fill('90'); await page.getByRole('button', { name: 'Save changes', exact: true }).click();
  assert.notEqual(await page.locator('.stop-time').last().textContent(), before); results.push('Duration edits propagate to following stops');
  const travel = await page.locator('.travel-link strong').first().textContent(); await page.locator('[data-mode-stop]').first().selectOption('walk');
  assert.notEqual(await page.locator('.travel-link strong').first().textContent(), travel); results.push('Walking versus driving updates travel and schedule');
  await page.locator('[data-action=up]').last().click(); assert.match(await page.locator('.stop-name').nth(1).textContent(), /Park picnic/); results.push('Stop reordering');
  await page.locator('[data-action=skip]').nth(1).click(); assert.equal(await page.locator('.stop.skipped').count(), 1);
  await page.locator('#undo').click(); assert.equal(await page.locator('.stop.skipped').count(), 0); results.push('Skip and undo');
  await page.locator('.edit-stop').last().click(); await page.locator('[name=day]').selectOption({ index: 1 }); await page.getByRole('button', { name: 'Save changes', exact: true }).click();
  assert.equal(await page.locator('.stop').count(), 1); results.push('Move stop between days');
  await page.reload(); await page.locator('.stop').waitFor(); assert.equal(await page.locator('#tripTitle').textContent(), 'QA weekend'); assert.equal(await page.locator('.stop').count(), 1); results.push('Trip, selected day and changes persist across reload');
  await page.locator('#more').click(); const download = page.waitForEvent('download'); await page.locator('#exportBackup').click(); const file = await download; await file.saveAs(`${out}test-backup.json`);
  const backup = await stored(); assert.equal(backup.trips.length, 2); assert.ok(!JSON.stringify(backup).includes('AIza')); results.push('Export backup excludes Google credentials');
  await page.locator('#importBackup').setInputFiles({ name: 'bad.json', mimeType: 'application/json', buffer: Buffer.from('{"version":1,"trips":[]}') });
  assert.equal((await stored()).trips.length, 2); results.push('Invalid import keeps existing trips');
  await page.locator('#importBackup').setInputFiles(`${out}test-backup.json`); await page.locator('#confirmImport').click(); assert.equal((await stored()).trips.length, 4); results.push('Valid import adds copies without overwriting');
  await page.locator('#tripSelect').selectOption({ index: 0 });
  await page.locator('.day-chip').nth(2).click();
  await page.waitForTimeout(500);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: `${out}mobile-plan.png` });
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)); results.push('390px layout has no horizontal overflow');
  await page.locator('[data-mobile=map]').click();
  const pinsInsideMap = () => {
    const map = document.querySelector('#plannerMap').getBoundingClientRect(), pins = [...document.querySelectorAll('.route-pin')];
    return map.width > 0 && map.height > 0 && pins.length >= 6 && pins.every(pin => { const r = pin.getBoundingClientRect(); return r.left >= map.left && r.right <= map.right && r.top >= map.top && r.bottom <= map.bottom; });
  };
  await page.waitForFunction(pinsInsideMap);
  await page.waitForTimeout(500); await page.screenshot({ path: `${out}mobile-map.png` });
  results.push('Opening the mobile map fits every route pin after a desktop resize');
  await page.locator('[data-mobile=plan]').click(); await page.locator('.day-chip').nth(1).click();
  await page.locator('.day-chip').nth(2).click(); await page.locator('[data-mobile=map]').click();
  await page.waitForFunction(pinsInsideMap);
  results.push('Changing days while the mobile map is hidden fits the selected route on reopening');
  await page.locator('[data-mobile=go]').click(); assert.ok(await page.locator('#goView').isVisible()); await page.screenshot({ path: `${out}mobile-go.png` }); results.push('Mobile map and on-the-go navigation');
  await page.locator('button[data-mobile=plan]').click(); await page.locator('.day-chip').first().click(); await page.locator('[data-view=go]').click();
  await page.getByRole('button', { name: 'Mark done', exact: false }).first().click(); await page.locator('#startNow').click();
  if (await page.locator('#confirmNow').count()) { await page.locator('#confirmNow').click(); await page.locator('[data-view=day]').click(); assert.equal(await page.locator('.stop.done').count(), 1); results.push('Replan from now retains completed stops without counting their duration'); }
  assert.deepEqual(errors, []); results.push('No uncaught JavaScript errors');
  const broken = await browser.newContext({ serviceWorkers: 'block' });
  await broken.addInitScript(() => localStorage.setItem('fieldtrip.plans.v1', '{invalid-original-backup'));
  const brokenPage = await broken.newPage(); await brokenPage.goto(base); await brokenPage.locator('.stop').first().waitFor();
  assert.equal(await brokenPage.evaluate(() => localStorage.getItem('fieldtrip.plans.v1')), '{invalid-original-backup');
  await brokenPage.locator('#more').click(); assert.ok(await brokenPage.locator('#exportRecovery').isVisible()); await broken.close(); results.push('Corrupt storage is preserved for recovery, never silently overwritten');
  const offline = await browser.newContext(); const offlinePage = await offline.newPage();
  await offlinePage.goto(base); await offlinePage.locator('.stop').first().waitFor();
  await offlinePage.evaluate(async () => { await navigator.serviceWorker.ready; });
  await offlinePage.reload(); await offlinePage.locator('.stop').first().waitFor(); await offline.setOffline(true);
  await offlinePage.reload(); await offlinePage.locator('.stop').first().waitFor(); assert.equal(await offlinePage.locator('.day-chip').count(), 11);
  await offline.close(); results.push('Planner and saved itinerary reopen offline after an online visit');
  // Exercise the real connection UI against a simulated SDK, never a paid API.
  const connected = await browser.newContext({ serviceWorkers: 'block' });
  const fixtureTrip = makeTrip({ name: 'Provider test', destination: 'San Francisco', startDate: '2030-10-02', count: 1, timezone: 'America/Los_Angeles' });
  fixtureTrip.days[0].stops = [makeStop({ name: 'Public start', lat: 37.7955, lng: -122.3934 }), makeStop({ name: 'Public end', lat: 37.8067, lng: -122.4053, mode: 'drive' })];
  await connected.addInitScript(store => localStorage.setItem('fieldtrip.plans.v1', JSON.stringify(store)), { version: 1, activeTripId: fixtureTrip.id, trips: [fixtureTrip] });
  let sdkLoads = 0;
  await connected.route('https://maps.googleapis.com/maps/api/js?*', async route => {
    sdkLoads++;
    await route.fulfill({ contentType: 'application/javascript', body: `
      window.__routeCalls = [];
      class FakeMap { fitBounds() {} }
      class FakeOverlay { constructor(opts) { this.map = opts.map; } setMap(map) { this.map = map; } }
      class FakeBounds { extend() {} }
      class FakePlace { constructor({id}) { this.id = id; } }
      const Route = { computeRoutes: async request => {
        window.__routeCalls.push(request.travelMode);
        await new Promise(resolve => setTimeout(resolve, request.travelMode === 'DRIVING' ? 1000 : 50));
        if (request.travelMode === 'BICYCLING') throw new Error('Simulated provider unavailable');
        return {routes:[{durationMillis: request.travelMode === 'WALKING' ? 1380000 : 420000, distanceMeters: 1800, path: [{lat: 37.7955, lng: -122.3934}, {lat: 37.8067, lng: -122.4053}], warnings: []}]};
      }};
      window.google = {maps: {Map: FakeMap, Polyline: FakeOverlay, LatLngBounds: FakeBounds, marker: {AdvancedMarkerElement: FakeOverlay}, importLibrary: async () => ({Map: FakeMap, Place: FakePlace, Route})}};
      window.fieldtripGoogleReady();
    ` });
  });
  const cp = await connected.newPage(); await cp.goto(base); await cp.locator('.stop').first().waitFor();
  assert.equal(sdkLoads, 0); results.push('Google SDK remains unloaded before explicit connection');
  await cp.locator('#settings').click(); await cp.locator('#googleKey').fill('AIza' + 'testonly'.repeat(4)); await cp.locator('#connectGoogle').click();
  await cp.waitForFunction(() => window.__routeCalls?.includes('DRIVING'));
  await cp.locator('[data-mode-stop]').selectOption('walk');
  await cp.waitForFunction(() => document.querySelector('.travel-link strong')?.textContent === '23 min');
  await cp.waitForTimeout(1100);
  assert.equal(await cp.locator('.travel-link strong').textContent(), '23 min');
  results.push('Simulated Google route refresh rejects late results after mode edits');
  await cp.locator('[data-mode-stop]').selectOption('bike');
  await cp.waitForFunction(() => document.querySelector('#routeNotice').textContent.includes('unavailable'));
  assert.match(await cp.locator('.travel-link strong').textContent(), /~/);
  results.push('Simulated Google failure falls back to clearly labeled estimates');
  await cp.locator('#more').click(); const googleBackup = cp.waitForEvent('download'); await cp.locator('#exportBackup').click();
  const stream = await (await googleBackup).createReadStream(); let exported = ''; for await (const chunk of stream) exported += chunk;
  assert.equal(exported.includes('AIza'), false); assert.equal(exported.includes('durationMillis'), false);
  results.push('Connected trip backup excludes the session credential and provider responses');
  await cp.locator('#closeDialog').click(); await cp.locator('#settings').click(); await cp.locator('#disconnectGoogle').click();
  assert.equal(await cp.evaluate(() => sessionStorage.getItem('fieldtrip.googleKey')), null);
  assert.match(await cp.locator('#connectionStatus').textContent(), /Local planning/);
  await connected.close(); results.push('Disconnect clears the session key and returns to local planning');
} finally { await browser.close(); await writeFile(`${out}browser-results.json`, JSON.stringify({ results, errors }, null, 2)); }
// Safari engine smoke: separate storage and no existing user data.
const safari = await webkit.launch({ headless: true });
try {
  const p = await safari.newPage({ viewport: { width: 390, height: 844 }, serviceWorkers: 'block' });
  await p.goto(base); await p.locator('.stop').first().waitFor(); await p.locator('.day-chip').nth(1).click();
  assert.equal(await p.locator('.stop').count() > 0, true); await p.screenshot({ path: `${out}webkit-mobile.png` });
  results.push('WebKit mobile planner renders and changes days');
} finally { await safari.close(); }
await writeFile(`${out}browser-results.json`, JSON.stringify({ status: 'PASS', results, errors }, null, 2));
console.log(JSON.stringify({ status: 'PASS', checks: results.length, results, errors }, null, 2));
