// Pure scheduling and persistence rules. Provider results stay in memory, never in exports.
export const STORAGE_KEY = 'fieldtrip.plans.v1';
export const MODES = { walk: 'Walk', drive: 'Drive', transit: 'Transit', bike: 'Bike' };
export const COLORS = ['#146b5b', '#cf663f', '#5269ac', '#9b6092', '#a07921', '#33899b'];
export const uid = () => globalThis.crypto?.randomUUID?.() || `p${Date.now()}${Math.random().toString(36).slice(2)}`;
export const clone = value => JSON.parse(JSON.stringify(value));
export const minutes = value => { const m = /^(\d{1,2}):(\d{2})$/.exec(value || ''); return m ? +m[1] * 60 + +m[2] : 0; };
export const clock = value => `${String(Math.floor(Math.max(0, value) / 60) % 24).padStart(2, '0')}:${String(Math.round(Math.max(0, value)) % 60).padStart(2, '0')}`;
export const timeLabel = value => `${clock(value)}${value >= 1440 ? ` +${Math.floor(value / 1440)}d` : ''}`;
export const durationLabel = value => value >= 60 ? `${Math.floor(value / 60)}h${value % 60 ? ` ${Math.round(value % 60)}m` : ''}` : `${Math.round(value)} min`;
export function localDate(date = new Date(), zone = 'America/Los_Angeles') {
  const p = Object.fromEntries(new Intl.DateTimeFormat('en-US', { timeZone: zone, year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(date).map(x => [x.type, x.value]));
  return `${p.year}-${p.month}-${p.day}`;
}
export function zonedDate(date, minute, zone) {
  const target = Date.parse(`${date}T00:00:00Z`) + minute * 60000;
  let guess = target;
  for (let i = 0; i < 3; i++) {
    const parts = Object.fromEntries(new Intl.DateTimeFormat('en-US', { timeZone: zone, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' }).formatToParts(new Date(guess)).map(p => [p.type, p.value]));
    const represented = Date.parse(`${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}:${parts.second}Z`);
    guess += target - represented;
  }
  return new Date(guess);
}
export function coordinates(stop) {
  return Number.isFinite(stop?.lat) && Number.isFinite(stop?.lng) && Math.abs(stop.lat) <= 90 && Math.abs(stop.lng) <= 180 ? [stop.lng, stop.lat] : null;
}
export function distanceKm(a, b) {
  if (!coordinates(a) || !coordinates(b)) return null;
  const rad = Math.PI / 180, dLat = (b.lat - a.lat) * rad, dLon = (b.lng - a.lng) * rad;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(dLon / 2) ** 2;
  return 6371 * 2 * Math.asin(Math.sqrt(Math.min(1, h)));
}
export function estimateLeg(from, to) {
  if (!from || from.kind === 'travel' || to.kind === 'travel' || to.kind === 'break') return null;
  if (to.travelMinutes != null) return { minutes: to.travelMinutes, km: null, source: 'manual', label: 'Your travel allowance', path: coordinates(from) && coordinates(to) ? [coordinates(from), coordinates(to)] : [] };
  const km = distanceKm(from, to);
  if (km == null) return { minutes: 0, km: null, source: 'unknown', label: 'Travel time unknown · add locations', path: [] };
  if (km < .015) return { minutes: 0, km: 0, source: 'same', label: 'Same location', path: [] };
  const mode = to.mode || 'drive';
  // Deliberately rough; no claim of road distance, safe access, closures or traffic.
  const speed = { walk: 4, drive: 30, bike: 13, transit: 18 }[mode];
  return { minutes: Math.max(1, Math.ceil(km * 1.35 / speed * 60)), km, source: 'estimate', label: 'Rough estimate · straight-line distance × 1.35', path: [coordinates(from), coordinates(to)] };
}
export function legKey(from, to) { return JSON.stringify([from?.id, from?.lat, from?.lng, from?.placeId, from?.address, to.id, to.lat, to.lng, to.placeId, to.address, to.mode]); }
export function travelEndpoints(stop) {
  if (stop.kind !== 'travel') return null;
  const from = { id: `${stop.id}-from`, name: stop.fromLabel || 'Start', address: stop.fromAddress || '', lat: stop.fromLat, lng: stop.fromLng };
  const to = { id: `${stop.id}-to`, name: stop.toLabel || 'Destination', address: stop.toAddress || '', lat: stop.toLat, lng: stop.toLng, mode: stop.mode };
  return (coordinates(from) || from.address) && (coordinates(to) || to.address) ? { from, to } : null;
}
export function scheduleDay(day, results = new Map(), options = {}) {
  let cursor = options.fromNow ?? minutes(day.start), previous = null, travel = 0, visits = 0, buffers = 0, unknown = 0, estimated = 0;
  const rows = [], warnings = [];
  for (const stop of day.stops) {
    if (stop.skipped || (options.remaining && stop.done)) continue;
    const leg = previous ? results.get(legKey(previous, stop)) || estimateLeg(previous, stop) : null;
    if (leg?.source === 'unknown') unknown++;
    if (leg?.source === 'estimate') estimated++;
    const allowance = leg && leg.source !== 'same' ? (stop.buffer || 0) : 0;
    const arrival = cursor + (leg?.minutes || 0) + allowance;
    const fixed = stop.fixedAt ? minutes(stop.fixedAt) : null;
    const start = fixed == null ? arrival : Math.max(arrival, fixed);
    const late = fixed == null ? 0 : Math.max(0, arrival - fixed);
    if (late) warnings.push({ id: stop.id, message: `${stop.name}: ${durationLabel(late)} after its fixed time.` });
    if (leg?.source === 'estimate' && stop.mode === 'walk' && leg.km > 5) warnings.push({ id: stop.id, message: `${stop.name}: long walk estimate. Check access and terrain.` });
    const endpoints = travelEndpoints(stop);
    const blockRoute = stop.kind === 'travel' ? results.get(`block:${stop.id}`) || (endpoints && coordinates(endpoints.from) && coordinates(endpoints.to) ? { source: 'manual', minutes: stop.duration, km: null, label: 'Original allowance · schematic connection', path: [coordinates(endpoints.from), coordinates(endpoints.to)] } : null) : null;
    const stay = blockRoute?.minutes ?? stop.duration;
    rows.push({ stop, index: day.stops.indexOf(stop), leg, blockRoute, start, end: start + stay, late, wait: Math.max(0, (fixed ?? arrival) - arrival), departure: cursor, buffer: allowance });
    travel += (leg?.minutes || 0) + (stop.kind === 'travel' ? stay : 0); visits += stop.kind === 'travel' ? 0 : stay; buffers += allowance; cursor = start + stay;
    // Unlocated activities break spatial continuity; do not invent a route across them.
    previous = stop.kind === 'break' ? (stop.movesLocation ? null : previous) : stop;
  }
  const overtime = Math.max(0, cursor - minutes(day.end));
  if (overtime) warnings.push({ message: `Day ends ${durationLabel(overtime)} after your ${day.end} target.` });
  return { rows, finish: cursor, travel, visits, buffers, unknown, estimated, overtime, warnings, total: cursor - (options.fromNow ?? minutes(day.start)) };
}
export function makeStop(values = {}) {
  return { id: uid(), name: 'New stop', kind: 'place', duration: 45, mode: 'drive', buffer: 5, fixedAt: '', note: '', done: false, skipped: false, ...values };
}
export function makeTrip({ name, destination, startDate, count, timezone = 'America/Los_Angeles' }) {
  return { id: uid(), name, destination, timezone, createdAt: new Date().toISOString(), days: Array.from({ length: count }, (_, i) => ({ id: uid(), date: new Date(Date.parse(`${startDate}T12:00:00Z`) + i * 86400000).toISOString().slice(0, 10), title: `Day ${i + 1}`, start: '09:00', end: '20:00', note: '', stops: [] })) };
}
export function seedTrip(data) {
  const trip = makeTrip({ name: 'San Francisco & beyond', destination: 'San Francisco · Monterey · Yosemite', startDate: '2026-10-02', count: data.dates.length });
  trip.id = 'sf-family-october-2026'; trip.sourceIdentity = data.trip_identity;
  const markers = new Map(data.markers.map(p => [p.place_key, p]));
  trip.days.forEach((day, i) => {
    const dateKey = data.dates[i].key, items = data.timeline.filter(x => x.date_key === dateKey);
    const op = data.operating_days?.[dateKey];
    day.title = i === 0 ? 'Arrival & a soft landing' : i < 4 ? 'San Francisco & Marin' : i === 4 ? 'Down the coast' : i < 8 ? 'Into Yosemite' : 'The Bay, at your pace';
    day.note = [op?.prepare_en, op?.recovery_en].filter(Boolean).join(' · ');
    day.stops = items.map((item, itemIndex) => {
      const place = markers.get(item.spatial_keys?.[0]);
      const afterArrow = (item.time || '').split('→')[1]?.trim();
      const scheduleText = item.kind !== 'travel' && /^~?\d{1,2}:/.test(afterArrow || '') ? afterArrow : item.time || '';
      const times = [...scheduleText.matchAll(/(\d{1,2}):(\d{2})/g)].map(m => `${m[1].padStart(2, '0')}:${m[2]}`);
      let start = times[0] || '', elapsed = times.length > 1 ? minutes(times[times.length - 1]) - minutes(start) : 30;
      // Use the late edge of a stated departure window, not its earliest edge plus
      // the entire arrival range. Preserve the original text for inspection.
      if (item.kind === 'travel' && afterArrow) {
        const departures = [...item.time.split('→')[0].matchAll(/(\d{1,2}):(\d{2})/g)];
        const departure = departures.at(-1);
        if (departure) { start = `${departure[1].padStart(2, '0')}:${departure[2]}`; elapsed = minutes(times.at(-1)) - minutes(start); }
      }
      // Arrival/checkout summary cards can describe the same interval as the next
      // transport block. Keep the context without counting that interval twice.
      const nextItem = items[itemIndex + 1], nextTime = nextItem?.time?.match(/(\d{1,2}):(\d{2})/);
      if (item.kind === 'logistics' && nextItem?.kind === 'travel' && nextTime && minutes(`${nextTime[1]}:${nextTime[2]}`) === minutes(start)) elapsed = 0;
      if (item.kind === 'logistics' && /recovery only/i.test(item.title_en || '')) { start = times.at(-1) || start; elapsed = 0; }
      const range = data.travel_ranges?.find(r => r.id === item.travel_range_id);
      const endpoint = (identity, prefix) => { const p = data.markers.find(m => m.name === identity || m.place_key === identity); return p ? { [`${prefix}Lat`]: p.lat, [`${prefix}Lng`]: p.lon, [`${prefix}Label`]: identity } : { [`${prefix}Label`]: identity || '' }; };
      return makeStop({ id: item.id, name: item.title_en || item.title, kind: item.kind === 'travel' ? 'travel' : place ? 'place' : 'break', movesLocation: !place, ...(place ? { lat: place.lat, lng: place.lon, placeKey: place.place_key, photo: place.photo_thumb } : {}), ...(range ? { ...endpoint(range.from_identity, 'from'), ...endpoint(range.to_identity, 'to') } : {}), duration: Math.max(0, Math.min(720, elapsed >= 0 ? elapsed : 30)), fixedAt: start, mode: item.travel_mode === 'walk' ? 'walk' : 'drive', buffer: 0, note: item.reason_en || '', originalTime: item.time, originalKind: item.kind, protected: item.schedule_tier === 'recovery', source: 'researched', skipped: ['swap', 'bonus'].includes(item.schedule_tier), swapFor: item.swap_for || '' });
    });
    day.start = day.stops.find(s => s.fixedAt)?.fixedAt || '09:00';
    day.end = '20:00';
  });
  return trip;
}
export function validateStore(value) {
  const fail = () => { throw new Error('This is not a valid Fieldtrip backup. Your existing plans were kept.'); };
  if (value?.version !== 1 || !Array.isArray(value.trips) || !value.trips.length || value.trips.length > 50) fail();
  const tripIds = new Set();
  for (const trip of value.trips) {
    if (!trip || typeof trip.id !== 'string' || tripIds.has(trip.id) || typeof trip.name !== 'string' || !trip.name.trim() || trip.name.length > 200 || typeof trip.timezone !== 'string' || !Array.isArray(trip.days) || !trip.days.length || trip.days.length > 90) fail();
    tripIds.add(trip.id);
    try { new Intl.DateTimeFormat('en', { timeZone: trip.timezone }).format(); } catch { fail(); }
    const ids = new Set(), dates = new Set();
    for (const day of trip.days) {
      if (!day || typeof day.id !== 'string' || ids.has(day.id) || typeof day.title !== 'string' || (day.note != null && typeof day.note !== 'string') || !validDate(day.date) || dates.has(day.date) || !validClock(day.start) || !validClock(day.end) || !Array.isArray(day.stops) || day.stops.length > 150) fail();
      ids.add(day.id); dates.add(day.date);
      for (const s of day.stops) {
        if (!s || typeof s.id !== 'string' || ids.has(s.id) || typeof s.name !== 'string' || !s.name.trim() || s.name.length > 500 || !['place', 'break', 'travel'].includes(s.kind) || !Object.hasOwn(MODES, s.mode) || !Number.isFinite(s.duration) || s.duration < 0 || s.duration > 1440 || !Number.isFinite(s.buffer) || s.buffer < 0 || s.buffer > 240 || (s.fixedAt && !validClock(s.fixedAt)) || (s.travelMinutes != null && (!Number.isFinite(s.travelMinutes) || s.travelMinutes < 0 || s.travelMinutes > 1440)) || ((s.lat != null || s.lng != null) && !coordinates(s))) fail();
        if (['note', 'address', 'placeId', 'placeKey', 'originalTime', 'photo', 'fromAddress', 'toAddress', 'fromLabel', 'toLabel'].some(k => s[k] != null && (typeof s[k] !== 'string' || s[k].length > 10000))) fail();
        for (const prefix of ['from', 'to']) if ((s[`${prefix}Lat`] != null || s[`${prefix}Lng`] != null) && !coordinates({ lat: s[`${prefix}Lat`], lng: s[`${prefix}Lng`] })) fail();
        ids.add(s.id);
      }
    }
  }
  if (!tripIds.has(value.activeTripId)) value.activeTripId = value.trips[0].id;
  return value;
}
export function validClock(value) { return typeof value === 'string' && /^([01]\d|2[0-3]):[0-5]\d$/.test(value); }
export function validDate(value) { return typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(Date.parse(value)) && new Date(`${value}T12:00:00Z`).toISOString().slice(0, 10) === value; }
export function navigationUrl(stop, from) {
  const url = new URL('https://www.google.com/maps/dir/');
  url.searchParams.set('api', '1');
  url.searchParams.set('destination', coordinates(stop) ? `${stop.lat},${stop.lng}` : stop.address || stop.name);
  if (stop.placeId) url.searchParams.set('destination_place_id', stop.placeId);
  if (from && coordinates(from)) url.searchParams.set('origin', `${from.lat},${from.lng}`);
  url.searchParams.set('travelmode', { walk: 'walking', drive: 'driving', bike: 'bicycling', transit: 'transit' }[stop.mode] || 'driving');
  return url.href;
}
export function reorder(stops, id, delta) {
  const index = stops.findIndex(s => s.id === id), target = index + delta;
  if (index < 0 || target < 0 || target >= stops.length) return stops;
  const result = [...stops]; [result[index], result[target]] = [result[target], result[index]]; return result;
}
// Optimize flexible, unfinished blocks only. Fixed appointments, breaks and first/last stops are anchors.
export function optimizeStops(stops) {
  const next = [...stops]; let start = 1;
  const anchored = s => s.fixedAt || s.done || s.skipped || s.protected || s.kind !== 'place' || !coordinates(s);
  while (start < next.length - 1) {
    if (anchored(next[start])) { start++; continue; }
    let end = start; while (end < next.length - 1 && !anchored(next[end])) end++;
    if (coordinates(next[start - 1]) && coordinates(next[end])) {
      const length = part => part.slice(1).reduce((sum, s, i) => sum + (distanceKm(part[i], s) ?? 1e8), 0);
      let segment = next.slice(start - 1, end + 1), improved = true;
      while (improved) { improved = false; for (let i = 1; i < segment.length - 2; i++) for (let j = i + 1; j < segment.length - 1; j++) {
        const candidate = [...segment.slice(0, i), ...segment.slice(i, j + 1).reverse(), ...segment.slice(j + 1)];
        if (length(candidate) < length(segment) - .001) { segment = candidate; improved = true; }
      } }
      next.splice(start, end - start, ...segment.slice(1, -1));
    }
    start = end + 1;
  }
  return next;
}
