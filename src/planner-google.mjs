import { coordinates, legKey, zonedDate } from './planner-core.mjs';

const timeout = (promise, ms = 18000) => {
  let timer;
  return Promise.race([promise, new Promise((_, reject) => { timer = setTimeout(() => reject(new Error('Google request timed out. Your plan is still saved.')), ms); })]).finally(() => clearTimeout(timer));
};
export class GoogleConnection {
  constructor() { this.ready = false; this.locations = new Map(); this.cache = new Map(); this.loading = null; this.generation = 0; }
  async connect(key) {
    if (!/^AIza[\w-]{20,}$/.test(key)) throw new Error('Enter a valid browser API key from Google Cloud.');
    if (this.key && this.key !== key) throw new Error('To change API keys, disconnect, reload this tab, then connect the new key.');
    this.key = key;
    if (!window.google?.maps?.importLibrary) {
      if (!this.loading) this.loading = new Promise((resolve, reject) => {
        const script = document.createElement('script');
        window.fieldtripGoogleReady = resolve;
        window.gm_authFailure = () => { this.ready = false; reject(new Error('Google rejected this key. Check billing, enabled APIs, and website restrictions.')); window.dispatchEvent(new Event('fieldtrip-google-error')); };
        script.src = `https://maps.googleapis.com/maps/api/js?${new URLSearchParams({ key, v: 'weekly', loading: 'async', callback: 'fieldtripGoogleReady' })}`;
        script.onerror = () => { this.loading = null; script.remove(); reject(new Error('Google Maps could not load. Check your connection.')); };
        document.head.append(script);
      });
      await timeout(this.loading);
    }
    await timeout(Promise.all(['maps', 'places', 'routes', 'marker'].map(name => google.maps.importLibrary(name))));
    this.ready = true; this.generation++;
  }
  disconnect() { this.ready = false; this.generation++; this.locations.clear(); this.cache.clear(); }
  hydrate(stop) { return stop.placeId && this.locations.has(stop.placeId) ? { ...stop, ...this.locations.get(stop.placeId) } : stop; }
  async resolve(stop) {
    if (!stop.placeId || this.locations.has(stop.placeId)) return this.hydrate(stop);
    const { Place } = await google.maps.importLibrary('places');
    const place = new Place({ id: stop.placeId });
    await timeout(place.fetchFields({ fields: ['location'] }));
    if (place.location) this.locations.set(stop.placeId, { lat: place.location.lat(), lng: place.location.lng() });
    return this.hydrate(stop);
  }
  async search(query) {
    if (!this.ready) throw new Error('Connect Google Maps to search worldwide.');
    const { Place } = await google.maps.importLibrary('places');
    const { places } = await timeout(Place.searchByText({ textQuery: query, fields: ['id', 'displayName', 'formattedAddress', 'location'], maxResultCount: 8 }));
    for (const p of places || []) if (p.location) this.locations.set(p.id, { lat: p.location.lat(), lng: p.location.lng() });
    return places || [];
  }
  async details(stop) {
    const { Place } = await google.maps.importLibrary('places');
    let id = stop.placeId;
    if (!id) {
      const { places } = await timeout(Place.searchByText({ textQuery: `${stop.name} ${stop.address || ''}`, ...(coordinates(stop) ? { locationBias: { center: { lat: stop.lat, lng: stop.lng }, radius: 1000 } } : {}), fields: ['id', 'displayName', 'formattedAddress', 'location'], maxResultCount: 5 }));
      return { candidates: places || [] };
    }
    const place = new Place({ id });
    await timeout(place.fetchFields({ fields: ['displayName', 'formattedAddress', 'rating', 'userRatingCount', 'regularOpeningHours', 'reviews', 'googleMapsURI', 'websiteURI', 'attributions', 'businessStatus'] }));
    return { place };
  }
  async route(from, to, date, departure, zone) {
    const { Route } = await google.maps.importLibrary('routes');
    const { Place } = await google.maps.importLibrary('places');
    const endpoint = s => s.placeId ? new Place({ id: s.placeId }) : coordinates(s) ? { lat: s.lat, lng: s.lng } : s.address;
    if (!endpoint(from) || !endpoint(to)) return null;
    const mode = { walk: 'WALKING', drive: 'DRIVING', bike: 'BICYCLING', transit: 'TRANSIT' }[to.mode];
    const when = zonedDate(date, departure, zone), now = new Date(), future = when > now;
    // The editor stores whole minutes. A departure in this minute means now;
    // let Google use server time so network latency cannot make it a past request.
    const trafficAware = future || (now - when >= 0 && now - when < 60000);
    const key = `${legKey(from, to)}:${date}:${Math.round(departure / 5)}`;
    const cached = this.cache.get(key);
    if (cached && Date.now() - cached.fetchedAt < 300000) return cached;
    const request = { origin: endpoint(from), destination: endpoint(to), travelMode: mode, fields: ['path', 'durationMillis', 'distanceMeters', 'warnings'] };
    if (mode === 'DRIVING') { request.routingPreference = trafficAware ? 'TRAFFIC_AWARE' : 'TRAFFIC_UNAWARE'; if (future) request.departureTime = when; }
    if (mode === 'TRANSIT') request.departureTime = when;
    const { routes } = await timeout(Route.computeRoutes(request));
    const route = routes?.[0];
    if (!route || !Number.isFinite(route.durationMillis)) throw new Error('No Google route is available for this leg.');
    const result = { source: 'google', label: mode === 'DRIVING' ? (trafficAware ? 'Google · traffic prediction' : 'Google · traffic not included for past time') : `Google · ${to.mode}`, minutes: Math.ceil(route.durationMillis / 60000), km: route.distanceMeters / 1000, path: (route.path || []).map(p => [p.lng, p.lat]), warnings: route.warnings || [], fetchedAt: Date.now() };
    this.cache.set(key, result); return result;
  }
}
