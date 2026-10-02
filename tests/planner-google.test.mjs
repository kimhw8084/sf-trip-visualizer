import test from 'node:test';
import assert from 'node:assert/strict';
import { GoogleConnection } from '../src/planner-google.mjs';

const requests = [];
class Place {
  constructor({ id }) { this.id = id; }
  async fetchFields(request) { requests.push({ details: request }); this.location = { lat: () => 37.8, lng: () => -122.4 }; this.reviews = []; }
  static async searchByText(request) { requests.push({ search: request }); return { places: [new Place({ id: 'selected-place' })] }; }
}
globalThis.window = globalThis;
globalThis.google = { maps: { importLibrary: async () => ({ Place, Route: { computeRoutes: async request => { requests.push(request); if (request.destination === 'NO_ROUTE') return { routes: [] }; return { routes: [{ durationMillis: 420000, distanceMeters: 1800, path: [{ lat: () => 37.8, lng: () => -122.4 }], warnings: ['Route warning'] }] }; } } }) } };
test('uses current Google Routes fields and a timezone-correct traffic departure', async () => {
  const g = new GoogleConnection(), from = { id: 'a', address: 'Start' }, to = { id: 'b', address: 'End', mode: 'drive' };
  const r = await g.route(from, to, '2030-10-02', 540, 'America/Los_Angeles');
  assert.equal(r.minutes, 7); assert.equal(r.km, 1.8); assert.deepEqual(r.warnings, ['Route warning']);
  const req = requests.at(-1); assert.equal(req.routingPreference, 'TRAFFIC_AWARE'); assert.equal(req.departureTime.toISOString(), '2030-10-02T16:00:00.000Z'); assert.deepEqual(req.fields, ['path', 'durationMillis', 'distanceMeters', 'warnings']);
  const n = requests.length; await g.route(from, to, '2030-10-02', 540, 'America/Los_Angeles'); assert.equal(requests.length, n);
  await g.route(from, { ...to, mode: 'walk' }, '2030-10-02', 540, 'America/Los_Angeles'); assert.equal(requests.at(-1).travelMode, 'WALKING'); assert.equal(requests.at(-1).routingPreference, undefined);
});
test('past driving times do not silently use current traffic', async () => {
  const g = new GoogleConnection(); const r = await g.route({ id: 'a', address: 'Start' }, { id: 'b', address: 'End', mode: 'drive' }, '2020-01-01', 540, 'UTC');
  assert.equal(requests.at(-1).routingPreference, 'TRAFFIC_UNAWARE'); assert.equal(requests.at(-1).departureTime, undefined); assert.match(r.label, /not included/);
});
test('missing and unavailable routes never become fictitious live routes', async () => {
  const g = new GoogleConnection(); assert.equal(await g.route({ id: 'a' }, { id: 'b', address: 'End', mode: 'walk' }, '2030-01-01', 540, 'UTC'), null);
  await assert.rejects(() => g.route({ id: 'a', address: 'Start' }, { id: 'b', address: 'NO_ROUTE', mode: 'walk' }, '2030-01-01', 540, 'UTC'), /No Google route/);
});
test('place coordinates stay ephemeral and unresolved matches need user selection', async () => {
  const g = new GoogleConnection(), stop = { id: 's', name: 'Coffee', placeId: 'known-id' };
  const resolved = await g.resolve(stop); assert.equal(resolved.lat, 37.8); assert.equal(stop.lat, undefined);
  const result = await g.details({ name: 'Coffee', lat: 37.8, lng: -122.4 }); assert.equal(result.candidates[0].id, 'selected-place');
  assert.equal((await g.details(stop)).place.id, 'known-id'); g.disconnect(); assert.equal(g.hydrate(stop).lat, undefined);
});
