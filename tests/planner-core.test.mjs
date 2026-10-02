import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { makeStop, makeTrip, seedTrip, scheduleDay, estimateLeg, distanceKm, legKey, reorder, optimizeStops, validateStore, zonedDate, localDate, navigationUrl, clone } from '../src/planner-core.mjs';

const stop = values => makeStop({ duration: 30, buffer: 0, ...values });
const day = stops => ({ start: '09:00', end: '20:00', stops });
test('editing duration, order and walking mode immediately propagates arrival times', () => {
  const a = stop({ lat: 37.8, lng: -122.4 }), b = stop({ lat: 37.81, lng: -122.42 }), c = stop({ lat: 37.82, lng: -122.41 });
  const d = day([a, b, c]), before = scheduleDay(d);
  b.duration += 20; assert.equal(scheduleDay(d).rows[2].start, before.rows[2].start + 20);
  b.mode = 'walk'; assert.ok(scheduleDay(d).rows[1].start > before.rows[1].start);
  d.stops = reorder(d.stops, c.id, -1); assert.equal(scheduleDay(d).rows[1].stop.id, c.id);
});
test('fixed appointments wait when early and report late conflicts without moving the fixed input', () => {
  const d = day([stop({ duration: 30 }), stop({ kind: 'break', fixedAt: '10:00' })]);
  let p = scheduleDay(d); assert.equal(p.rows[1].wait, 30); assert.equal(p.rows[1].start, 600);
  d.stops[0].duration = 90; p = scheduleDay(d); assert.equal(p.rows[1].late, 30); assert.equal(d.stops[1].fixedAt, '10:00'); assert.ok(p.warnings.length);
});
test('missing locations produce unknown travel, not a fabricated zero-minute route', () => {
  const p = scheduleDay(day([stop({ name: 'Hotel' }), stop({ lat: 37.8, lng: -122.4 })]));
  assert.equal(p.unknown, 1); assert.equal(p.rows[1].leg.source, 'unknown');
});
test('same-place activities do not add travel buffers; breaks preserve location only when stationary', () => {
  const a = stop({ lat: 1, lng: 1 }), b = stop({ lat: 1, lng: 1, buffer: 10 });
  assert.equal(scheduleDay(day([a, b])).buffers, 0);
  const rest = stop({ kind: 'break' }), c = stop({ lat: 1.01, lng: 1.01 });
  assert.ok(scheduleDay(day([a, rest, c])).rows[2].leg);
  rest.movesLocation = true; assert.equal(scheduleDay(day([a, rest, c])).rows[2].leg, null);
});
test('manual transfer blocks do not double-count automatic travel', () => {
  const d = day([stop({ lat: 1, lng: 1 }), stop({ kind: 'travel', duration: 45 }), stop({ lat: 2, lng: 2 })]);
  assert.equal(scheduleDay(d).travel, 45); assert.equal(scheduleDay(d).total, 105);
});
test('provider results override estimates; stale mode/coordinate results cannot match new legs', () => {
  const a = stop({ lat: 37.8, lng: -122.4 }), b = stop({ lat: 37.81, lng: -122.42 });
  const routes = new Map([[legKey(a, b), { minutes: 18, source: 'google', km: 4 }]]);
  assert.equal(scheduleDay(day([a, b]), routes).travel, 18);
  b.mode = 'walk'; assert.equal(scheduleDay(day([a, b]), routes).rows[1].leg.source, 'estimate');
});
test('a routed travel block replaces its manual allowance exactly once', () => {
  const transfer = stop({ kind: 'travel', duration: 60, fromAddress: 'Start', toAddress: 'End' });
  const d = day([transfer, stop({ kind: 'break', duration: 20 })]);
  const p = scheduleDay(d, new Map([[`block:${transfer.id}`, { minutes: 25, source: 'google' }]]));
  assert.equal(p.travel, 25); assert.equal(p.total, 45); assert.equal(p.rows[1].start, 565);
});
test('remaining mode excludes completed and skipped stops but retains upcoming fixed appointments', () => {
  const d = { ...day([stop({ done: true }), stop({ skipped: true }), stop({ kind: 'break', fixedAt: '10:00' })]), start: '11:00' };
  const p = scheduleDay(d, new Map(), { remaining: true }); assert.equal(p.rows.length, 1); assert.equal(p.rows[0].late, 60);
});
test('manual travel allowances remain explicit and finish after midnight is not silently wrapped', () => {
  const d = { ...day([stop({ duration: 60 }), stop({ travelMinutes: 45 })]), start: '23:00', end: '23:59' };
  const p = scheduleDay(d); assert.equal(p.rows[1].leg.source, 'manual'); assert.equal(p.finish, 1515); assert.equal(p.overtime, 76);
});
test('route suggestion respects fixed, protected and endpoint anchors and cannot increase geometric length', () => {
  const stops = [0, 3, 1, 2, 4].map(lng => stop({ lat: 10, lng }));
  const length = arr => arr.slice(1).reduce((s, p, i) => s + distanceKm(arr[i], p), 0);
  const next = optimizeStops(stops); assert.ok(length(next) < length(stops)); assert.equal(next[0], stops[0]); assert.equal(next.at(-1), stops.at(-1));
  stops[2].fixedAt = '10:00'; stops[1].protected = true; const anchored = optimizeStops(stops); assert.equal(anchored[1], stops[1]); assert.equal(anchored[2], stops[2]);
});
test('canonical import preserves every original card, place coordinate and source time', () => {
  const data = JSON.parse(readFileSync(new URL('../data/phase7_app_data.json', import.meta.url))), trip = seedTrip(data);
  const stops = trip.days.flatMap(d => d.stops); assert.equal(stops.length, data.timeline.length); assert.equal(trip.days[0].date, '2026-10-02');
  for (const t of data.timeline) assert.equal(stops.find(s => s.id === t.id).originalTime, t.time);
  assert.equal(stops.find(s => s.placeKey === 'twin_peaks').skipped, true);
  assert.equal(stops.find(s => s.name === 'Palace of Fine Arts').fixedAt, '15:50');
  const arrival = scheduleDay(trip.days[0]);
  assert.equal(arrival.finish, 19 * 60 + 50);
  assert.equal(arrival.warnings.length, 0);
  validateStore({ version: 1, activeTripId: trip.id, trips: [trip] });
});
test('backup validation rejects malformed dates, duplicate IDs, unknown modes and unsafe coordinates', () => {
  const trip = makeTrip({ name: 'Test', startDate: '2026-10-02', count: 2 }); trip.days[0].stops.push(stop({ name: 'Test' }));
  const value = { version: 1, activeTripId: trip.id, trips: [trip] }; assert.equal(validateStore(clone(value)).trips.length, 1);
  for (const mutation of [v => { v.trips[0].days[0].date = '2026-02-30'; }, v => { v.trips[0].days[1].id = v.trips[0].days[0].id; }, v => { v.trips[0].days[0].stops[0].mode = 'flying'; }, v => { Object.assign(v.trips[0].days[0].stops[0], { lat: 100, lng: 1 }); }]) { const bad = clone(value); mutation(bad); assert.throws(() => validateStore(bad)); }
});
test('route departure uses destination timezone across daylight-saving changes', () => {
  assert.equal(zonedDate('2026-10-02', 9 * 60, 'America/Los_Angeles').toISOString(), '2026-10-02T16:00:00.000Z');
  assert.equal(zonedDate('2026-12-02', 9 * 60, 'America/Los_Angeles').toISOString(), '2026-12-02T17:00:00.000Z');
  assert.equal(zonedDate('2026-10-02', 9 * 60, 'Asia/Tokyo').toISOString(), '2026-10-02T00:00:00.000Z');
  assert.equal(localDate(new Date('2026-10-02T02:00:00Z')), '2026-10-01');
});
test('navigation URLs preserve explicit places and never interpolate arbitrary schemes', () => {
  const url = new URL(navigationUrl(stop({ name: 'Coffee & tea', placeId: 'abc', mode: 'walk' })));
  assert.equal(url.origin, 'https://www.google.com'); assert.equal(url.searchParams.get('destination_place_id'), 'abc'); assert.equal(url.searchParams.get('travelmode'), 'walking');
});
