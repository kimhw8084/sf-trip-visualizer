import { coordinates, COLORS } from './planner-core.mjs';

export class PlannerMap {
  constructor(onSelect, onError) { this.onSelect = onSelect; this.onError = onError; this.markers = []; this.googleObjects = []; this.mode = 'local'; this.data = []; this.ready = false; }
  init() {
    try {
      const { Protocol } = window.TRIP_VECTOR;
      this.protocol = new Protocol(); maplibregl.addProtocol('pmtiles', this.protocol.tile);
      this.map = new maplibregl.Map({ container: 'plannerMap', style: this.localStyle(), center: [-122.42, 37.79], zoom: 11, attributionControl: true, dragRotate: false });
      this.map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-right');
      this.map.on('load', () => { this.ready = true; this.draw(this.data, true); });
      this.map.on('style.load', () => { this.ready = true; this.draw(this.data, true); });
      this.map.on('error', () => this.onError('Map tiles are unavailable. Your itinerary still works. Try the online world map in map options.'));
    } catch { this.onError('The map could not start on this device. Your itinerary and navigation links still work.'); }
  }
  localStyle() {
    const base = new URL('../assets/vector/', import.meta.url).href;
    const layers = window.TRIP_VECTOR.layers('basemap', window.TRIP_VECTOR.namedFlavor('light'), { lang: 'en' });
    for (const layer of layers) {
      if (layer.id === 'water') layer.paint['fill-color'] = '#bedbd9';
      if (layer.id === 'earth') layer.paint['fill-color'] = '#ebece3';
      if (layer.type === 'fill' && /park|forest|wood|grass|nature/.test(layer.id)) layer.paint['fill-color'] = '#c5d8be';
    }
    return { version: 8, glyphs: `${base}fonts/{fontstack}/{range}.pbf`, sprite: `${base}sprites/light`, sources: { basemap: { type: 'vector', url: `pmtiles://${base}sf_trip.pmtiles`, attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> · Protomaps' } }, layers };
  }
  setWorld() {
    this.mode = 'world'; this.showLocal(); this.ready = false;
    this.map?.setStyle({ version: 8, sources: { world: { type: 'raster', tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'], tileSize: 256, attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>' } }, layers: [{ id: 'world', type: 'raster', source: 'world' }] });
  }
  setLocal() { this.mode = 'local'; this.showLocal(); this.ready = false; this.map?.setStyle(this.localStyle()); }
  showLocal() {
    document.getElementById('googleMap').hidden = true; document.getElementById('plannerMap').hidden = false;
    this.googleObjects.forEach(x => x.setMap?.(null)); this.googleObjects = []; this.resize();
  }
  async setGoogle() {
    const { Map } = await google.maps.importLibrary('maps');
    this.mode = 'google'; document.getElementById('plannerMap').hidden = true; document.getElementById('googleMap').hidden = false;
    this.googleMap ||= new Map(document.getElementById('googleMap'), { center: { lat: 37.79, lng: -122.42 }, zoom: 11, mapId: 'DEMO_MAP_ID', mapTypeControl: false, streetViewControl: false, fullscreenControl: false });
    await google.maps.importLibrary('marker');
    this.draw(this.data, true);
  }
  draw(days, fit = false) {
    this.data = days;
    this.markers.forEach(m => m.remove()); this.markers = [];
    this.googleObjects.forEach(x => { if ('map' in x) x.map = null; else x.setMap?.(null); }); this.googleObjects = [];
    // Tile and route-source loading must not suppress edits after the style is ready.
    if (this.mode !== 'google' && !this.ready) return;
    const features = [], bounds = [];
    for (const entry of days) {
      const color = COLORS[entry.index % COLORS.length]; let number = 0;
      for (const row of entry.plan.rows) {
        const stop = row.stop, point = coordinates(stop); if (stop.skipped) continue;
        if (point) {
          number = row.index + 1; bounds.push(point);
          const el = document.createElement('button'); el.className = `route-pin${stop.done ? ' completed' : ''}`; el.style.setProperty('--pin-color', color); el.textContent = String(number); el.title = stop.name; el.setAttribute('aria-label', `${number}. ${stop.name}`); el.onclick = () => this.onSelect(stop.id, entry.dayId);
          if (this.mode === 'google') this.googleObjects.push(new google.maps.marker.AdvancedMarkerElement({ map: this.googleMap, position: { lat: point[1], lng: point[0] }, content: el, title: stop.name }));
          else this.markers.push(new maplibregl.Marker({ element: el }).setLngLat(point).addTo(this.map));
        }
        const route = row.blockRoute || row.leg;
        if (route?.path?.length > 1) {
          const live = route.source === 'google';
          // Google-derived routes are only displayed on a Google map.
          if (live && this.mode !== 'google') continue;
          const path = route.path; bounds.push(...path);
          if (this.mode === 'google') this.googleObjects.push(new google.maps.Polyline({ map: this.googleMap, path: path.map(p => ({ lng: p[0], lat: p[1] })), strokeColor: color, strokeWeight: 4, strokeOpacity: live ? .9 : 0, ...(live ? {} : { icons: [{ icon: { path: 'M 0,-1 0,1', strokeOpacity: .7, scale: 3 }, offset: '0', repeat: '14px' }] }) }));
          else features.push({ type: 'Feature', properties: { color }, geometry: { type: 'LineString', coordinates: path } });
        }
      }
    }
    if (this.mode !== 'google') {
      const source = this.map.getSource('plan-routes'), data = { type: 'FeatureCollection', features };
      if (source) source.setData(data);
      else { this.map.addSource('plan-routes', { type: 'geojson', data }); this.map.addLayer({ id: 'plan-routes', type: 'line', source: 'plan-routes', paint: { 'line-color': ['get', 'color'], 'line-width': 4, 'line-opacity': .8, 'line-dasharray': [2, 2] } }); }
    }
    this.bounds = bounds;
    if (fit) this.fit();
  }
  fit() {
    if (!this.bounds?.length) return;
    const container = document.getElementById(this.mode === 'google' ? 'googleMap' : 'plannerMap');
    if (!container.clientWidth || !container.clientHeight) { this.pendingFit = true; return; }
    this.pendingFit = false;
    if (this.mode === 'google') { const b = new google.maps.LatLngBounds(); this.bounds.forEach(p => b.extend({ lng: p[0], lat: p[1] })); this.googleMap.fitBounds(b, 80); }
    else if (this.map) { const b = new maplibregl.LngLatBounds(); this.bounds.forEach(p => b.extend(p)); this.map.fitBounds(b, { padding: { top: 100, left: 65, right: 65, bottom: 130 }, maxZoom: 14, duration: 400 }); }
  }
  focus(stop) { if (!coordinates(stop)) return; if (this.mode === 'google') { this.googleMap.panTo({ lat: stop.lat, lng: stop.lng }); this.googleMap.setZoom(14); } else this.map?.easeTo({ center: coordinates(stop), zoom: 14 }); }
  location(lat, lng) {
    this.userMarker?.remove?.(); this.userMarker?.setMap?.(null);
    if (this.mode === 'google') { this.userMarker = new google.maps.Marker({ map: this.googleMap, position: { lat, lng }, title: 'Your current location' }); this.googleMap.panTo({ lat, lng }); }
    else { this.userMarker = new maplibregl.Marker({ color: '#246ed2' }).setLngLat([lng, lat]).addTo(this.map); this.map?.easeTo({ center: [lng, lat], zoom: 14 }); }
  }
  resize(fit = false) { setTimeout(() => { this.map?.resize(); if (fit || this.pendingFit) this.fit(); }, 50); }
}
