/*
 * Calm field atlas runtime.
 * Ownership map: state/persistence -> atlas_state.js; messages -> atlas_messages.js;
 * map/provider/layers -> Map adapter below; Decide/Day/Place -> renderers below;
 * focus/Escape/sheet -> overlay and shell controller below.
 */
(() => {
  const DATA = window.TRIP_DATA || {};
  const ROUTES = Object.keys(DATA.routes || {});
  const GEOMETRY = window.TRIP_ROUTE_GEOMETRY || {};
  const I18N = window.TRIP_I18N || { ko_to_en: {}, en_to_ko: {}, places: {} };
  const FRESHNESS = window.TRIP_FRESHNESS || { default_status: 'RECHECK_REQUIRED' };
  const RUNTIME_CONTRACT = window.TRIP_RUNTIME_CONTRACT || {};
  const messages = window.TRIP_ATLAS_MESSAGES;
  const model = window.TRIP_ATLAS_STATE.create(DATA);
  const state = model.state;
  const routeMeta = DATA.routes;
  const markerByKey = Object.fromEntries((DATA.markers || []).map(item => [item.place_key, item]));
  const SAFE_PIXEL = 'data:image/gif;base64,R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs=';
  const SATELLITE_TILE_TEMPLATE = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';
  const SATELLITE_HEALTH_PROBE = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/12/1583/655';
  const SATELLITE_ATTRIBUTION = 'Tiles © Esri and contributors';
  const SAFE_PHOTO_ROLES = new Set(['hero', 'experience', 'scale_context']);
  const SAFE_PHOTO_VARIANTS = new Set(['thumb', 'medium']);
  let photoMap = null;
  let photoMarkers = [];
  let clusterMarkers = [];
  let legMarkers = [];
  let drawQueue = Promise.resolve();
  let vectorUrl = 'assets/vector/sf_trip.pmtiles';
  let renderedProvider = null;
  let renderedTheme = null;
  const MAP_SAFE_MARGIN = 16;
  let peekHideTimer = null;
  let suppressPeekFocusKey = null;
  let mapOptionsInvoker = null;
  let routeLegendInvoker = null;
  let geometryFrame = 0;
  let geometryNeedsRefit = false;
  let geometryWaiters = [];
  let observedMapSize = null;

  const markStartup = (name, detail = {}) => {
    if (typeof window.__tripStartupMark === 'function') return window.__tripStartupMark(name, detail);
    const started = window.__tripLoadStarted || performance.now();
    (window.__tripStartupMarks ||= []).push({ name, at_ms: Math.round((performance.now() - started) * 100) / 100, ...detail });
  };
  markStartup('authored_js_evaluated');

  const m = key => messages.messages[state.presentation.lang]?.[key] || messages.messages.en[key] || key;
  const tr = value => {
    const text = String(value ?? '');
    return state.presentation.lang === 'en' ? (I18N.ko_to_en[text] || text) : (I18N.en_to_ko[text] || text);
  };
  const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
  const isMobile = () => window.matchMedia('(max-width:800px)').matches;
  const safeColor = value => /^#[0-9a-f]{6}$/i.test(String(value ?? '')) ? String(value) : '#72857b';
  const photoPath = (key, role, variant) => /^[a-z0-9]+(?:_[a-z0-9]+)*$/i.test(String(key ?? '')) && SAFE_PHOTO_ROLES.has(role) && SAFE_PHOTO_VARIANTS.has(variant) ? `assets/photos/${variant}/${key}__${role}.webp` : SAFE_PIXEL;
  const photoSrc = path => window.EMBEDDED_PHOTOS?.[path] || path;
  const placeName = key => I18N.places[key]?.[0] || markerByKey[key]?.name || key;
  const placeKo = key => I18N.places[key]?.[1] || '';
  const dateLabel = value => {
    const key = String(value || '').match(/^\d+\/\d+/)?.[0];
    if (!key) return tr(value);
    const date = DATA.dates.find(item => item.key === key);
    return state.presentation.lang === 'en' ? (date?.label_en || key) : (date?.label || key);
  };
  const modeLabel = mode => messages.modeLabels[state.presentation.lang]?.[mode] || mode;
  const tierFor = item => item?.schedule_tier || (String(item?.role || '').includes('필수') ? 'must' : String(item?.role || '').includes('근처') ? 'bonus' : 'strong');
  const tierLabel = tier => m(tier || 'strong');
  const decisionLabel = key => messages.decisions[key]?.[state.presentation.lang] || key.replaceAll('_', ' ');
  const routeNarrative = route => routeMeta[route]?.explanation?.[state.presentation.lang] || { best_for: tr(routeMeta[route]?.subtitle), tradeoff: tr(routeMeta[route]?.core_reason), decision_rule: tr(routeMeta[route]?.core_reason), regret_guard: tr(routeMeta[route]?.core_reason) };
  const recommendedRoute = ROUTES.find(route => routeMeta[route]?.recommended) || ROUTES[0];

  /* ----- Task state projection and persistence ----- */
  function activeRoutes({ map = false } = {}) {
    if (state.task.routes.size === 1) return new Set(state.task.routes);
    if (map && state.presentation.mode === 'decide' && !state.task.compareRoutes.size) return new Set(ROUTES);
    if (state.task.compareRoutes.size && state.presentation.mode === 'decide') return new Set([state.task.primaryRoute, ...state.task.compareRoutes]);
    return new Set([state.task.primaryRoute]);
  }
  function routeIntersects(routes, options) { return (routes || []).some(route => activeRoutes(options).has(route)); }
  function dateMatchesOccurrence(item) { return state.task.date === 'all' || (item.date || '').startsWith(state.task.date + ' ') || item.date === state.task.date; }
  function markerVisible(marker, options = {}) {
    if (!routeIntersects(marker.routes, options)) return false;
    if (state.task.region !== 'overall' && DATA.place_region[marker.place_key] !== state.task.region) return false;
    if (state.task.date === 'all') return true;
    return marker.occurrences.some(item => activeRoutes(options).has(item.route) && dateMatchesOccurrence(item));
  }
  function timelineVisible(item) {
    if (!routeIntersects(item.routes)) return false;
    if (state.task.date !== 'all' && item.date_key !== state.task.date) return false;
    return state.task.region === 'overall' || item.regions.includes(state.task.region);
  }
  function legVisible(leg, options = {}) {
    if (!routeIntersects(leg.routes, options)) return false;
    if (state.task.date !== 'all' && leg.date !== state.task.date) return false;
    const from = markerByKey[leg.from], to = markerByKey[leg.to], routes = activeRoutes(options);
    if (from && to && !leg.routes.some(route => routes.has(route) && from.occurrences.some(item => item.route === route && item.date.startsWith(leg.date)) && to.occurrences.some(item => item.route === route && item.date.startsWith(leg.date)))) return false;
    if (state.task.region !== 'overall') {
      const fromRegion = DATA.place_region[leg.from], toRegion = DATA.place_region[leg.to];
      if (fromRegion !== state.task.region && toRegion !== state.task.region) return false;
      if (leg.render_style === 'transfer_dots') return false;
    }
    return true;
  }
  function persist() { model.persist(); }
  function recordRuntimeEvent(type, provider, detail = {}) {
    const event = { seq: ++state.runtime.sequence, type, provider, ...detail };
    state.runtime.providerEvents.push(event); state.runtime.events.push(event);
    if (state.runtime.providerEvents.length > 80) state.runtime.providerEvents.shift();
    if (state.runtime.events.length > 80) state.runtime.events.shift();
  }

  /* ----- Local asset and provider boundary ----- */
  function safeExternalUrl(value) {
    try {
      const url = new URL(String(value ?? ''), document.baseURI);
      if (url.protocol !== 'https:' || url.username || url.password || url.port || url.hash) return '';
      if (url.hostname === 'server.arcgisonline.com' && url.pathname.startsWith('/ArcGIS/rest/services/World_Imagery/MapServer/tile/')) return url.href;
      if (url.hostname === 'www.google.com' && url.pathname === '/maps/search/' && url.searchParams.get('api') === '1' && url.searchParams.get('query') && [...url.searchParams.keys()].every(key => key === 'api' || key === 'query')) return url.href;
      return '';
    } catch { return ''; }
  }
  function safeProviderConfig() {
    const config = DATA.providers?.satellite;
    return config?.tile_template === SATELLITE_TILE_TEMPLATE && config?.health_probe === SATELLITE_HEALTH_PROBE ? { tile_template: SATELLITE_TILE_TEMPLATE, health_probe: SATELLITE_HEALTH_PROBE } : null;
  }
  function safeProviderUrl(value) {
    const url = safeExternalUrl(value);
    return url && url.startsWith('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/') ? url : '';
  }
  function mapFailureText(error, phase = 'runtime') {
    const detail = String(error?.message || error || 'local asset failure');
    return state.presentation.lang === 'ko' ? `로컬 Smart 지도 오류 (${phase}): ${detail}` : `Local Smart map error (${phase}): ${detail}`;
  }
  function setStatus(text) {
    const startup = document.getElementById('startupStatus'); if (startup) startup.textContent = text;
  }
  function showMapFailure(error, phase = 'runtime') {
    const message = `${m('smartFailure')} ${mapFailureText(error, phase)}`;
    const errorBox = document.getElementById('mapError');
    if (errorBox) { errorBox.querySelector('.map-error-message').textContent = message; errorBox.hidden = false; }
    state.runtime.providerHealth.vector = 'failed'; state.runtime.localAssets.status = 'failed'; state.runtime.localAssets.failures.push(message);
    recordRuntimeEvent('smart_failure', 'vector', { phase, message });
    renderProviderState(); renderShellStatus(); setStatus(message); persist();
  }
  function localMapError(event) {
    const source = String(event?.sourceId || ''), message = String(event?.error?.message || event?.message || event?.error || '');
    return source === 'basemap' || source === 'hillshade' || /pmtiles|tripasset|glyph|sprite|font|local asset|range|byte serving/i.test(message);
  }
  async function setupVector() {
    markStartup('local_vector_setup_start');
    if (!window.TRIP_VECTOR) throw new Error('Local vector renderer missing');
    const { Protocol, PMTiles, FileSource } = window.TRIP_VECTOR;
    const protocol = new Protocol();
    let archive;
    if (window.EMBEDDED_VECTOR) {
      if (typeof window.EMBEDDED_VECTOR !== 'string' || window.EMBEDDED_VECTOR.length < 100000) throw new Error('Embedded PMTiles payload is missing or truncated');
      const response = await fetch(`data:application/octet-stream;base64,${window.EMBEDDED_VECTOR}`);
      const blob = await response.blob();
      if (blob.size < 127) throw new Error('Embedded PMTiles payload is too small');
      vectorUrl = 'sf_trip.pmtiles'; archive = new PMTiles(new FileSource(new File([blob], 'sf_trip.pmtiles')));
    } else archive = new PMTiles(vectorUrl);
    const header = await archive.getHeader();
    markStartup('local_pmtiles_header_ready', { tile_type: header?.tileType, max_zoom: header?.maxZoom });
    if (!header || ![1, 6].includes(header.tileType) || header.maxZoom < 1 || header.minLon >= header.maxLon || header.minLat >= header.maxLat) throw new Error('Smart map PMTiles header is invalid');
    protocol.add(archive); maplibregl.addProtocol('pmtiles', protocol.tile);
    maplibregl.addProtocol('tripasset', async params => {
      const path = decodeURIComponent(params.url.replace('tripasset://', ''));
      if (!/^assets\/vector\/(?:fonts|sprites)\/[^?#]+$/.test(path) || path.includes('..')) throw new Error('Unsafe local map asset path');
      const response = await fetch(window.EMBEDDED_MAP_ASSETS?.[path] ? `data:application/octet-stream;base64,${window.EMBEDDED_MAP_ASSETS[path]}` : path);
      if (!response.ok) throw new Error(`Missing map asset ${path}`);
      return { data: path.endsWith('.json') ? await response.json() : await response.arrayBuffer() };
    });
    state.runtime.localAssets.status = 'ready'; state.runtime.providerHealth.vector = 'ready'; recordRuntimeEvent('smart_ready', 'vector', { identity: state.runtime.providerIdentity });
    markStartup('local_vector_setup_ready');
  }
  function vectorStyle({ labelsOnly = false } = {}) {
    markStartup('local_map_asset_style_start', { labels_only: labelsOnly });
    const vector = window.TRIP_VECTOR, dark = state.presentation.theme === 'dark';
    const layers = vector.layers('basemap', vector.namedFlavor(dark ? 'dark' : 'light'), { lang: 'en', labelsOnly });
    for (const layer of layers) {
      if (layer.type === 'background') layer.paint['background-color'] = dark ? '#334553' : '#e9eee8';
      if (dark && !labelsOnly) {
        if (layer.id === 'earth') layer.paint['fill-color'] = '#334553';
        if (layer.id === 'water') layer.paint['fill-color'] = '#28566e';
        if (layer.id.startsWith('water_') && layer.type === 'line') layer.paint['line-color'] = '#3b7892';
        if (layer.id === 'buildings') layer.paint['fill-color'] = '#263745';
        if (layer.type === 'symbol' && layer.paint?.['text-color']) { layer.paint['text-color'] = layer.id.startsWith('places_') ? '#edf5fb' : '#d3e2ec'; layer.paint['text-halo-color'] = '#253949'; layer.paint['text-halo-width'] = 1.25; }
      }
      if (labelsOnly && layer.paint?.['text-color']) { layer.paint['text-color'] = '#fff'; layer.paint['text-halo-color'] = '#202a36'; layer.paint['text-halo-width'] = 2.2; }
    }
    const sources = { basemap: { type: 'vector', url: `pmtiles://${vectorUrl}`, attribution: '© OpenStreetMap contributors · Protomaps' } };
    if (!labelsOnly) {
      sources.hillshade = { type: 'image', url: window.EMBEDDED_HILLSHADE || 'assets/vector/yosemite_hillshade_shadow.webp', coordinates: [[-119.99, 37.95], [-119.35, 37.95], [-119.35, 37.38], [-119.99, 37.38]] };
      const index = layers.findIndex(layer => layer.id === 'roads_tunnels_other_casing');
      layers.splice(index < 0 ? layers.length : index, 0, { id: 'yosemite-relief', type: 'raster', source: 'hillshade', minzoom: 8, maxzoom: 18, paint: { 'raster-opacity': dark ? .58 : .72, 'raster-fade-duration': 0 } });
    }
    const style = { version: 8, glyphs: 'tripasset://assets/vector/fonts/{fontstack}/{range}.pbf', sprite: `tripasset://assets/vector/sprites/${dark ? 'dark' : 'light'}`, sources, layers };
    markStartup('local_map_asset_style_ready', { labels_only: labelsOnly, layers: layers.length, hillshade: !labelsOnly });
    return style;
  }
  function providerStyle(provider) {
    if (provider === 'vector') return vectorStyle();
    const config = safeProviderConfig();
    if (provider !== 'satellite' || !config) throw new Error('Satellite provider configuration is not approved');
    const style = { version: 8, sources: { base: { type: 'raster', tiles: [config.tile_template], tileSize: 256, attribution: SATELLITE_ATTRIBUTION } }, layers: [{ id: 'base', type: 'raster', source: 'base' }] };
    const labels = vectorStyle({ labelsOnly: true }); style.sources.basemap = labels.sources.basemap; style.glyphs = labels.glyphs; style.sprite = labels.sprite; style.layers.push(...labels.layers); return style;
  }
  function probeImage(value, timeout = 2600, tag = 'health') {
    return new Promise(resolve => {
      const url = safeProviderUrl(value); if (!url) return resolve(false);
      const image = new Image(); let done = false;
      const end = result => { if (done) return; done = true; clearTimeout(timer); image.onload = image.onerror = null; resolve(result); };
      const timer = setTimeout(() => end(false), timeout); image.onload = () => end(image.naturalWidth > 0); image.onerror = () => end(false); image.referrerPolicy = 'no-referrer'; image.src = `${url}${url.includes('?') ? '&' : '?'}${tag}=${++state.runtime.probeSequence}`;
    });
  }
  async function testProvider(provider) {
    if (provider === 'vector') return state.runtime.providerHealth.vector === 'ready' && state.runtime.localAssets.status === 'ready';
    const config = safeProviderConfig();
    if (provider !== 'satellite' || !config || DATA.providers?.satellite?.requires_api_key) { state.runtime.providerHealth[provider] = 'failed'; renderProviderState(); return false; }
    state.runtime.providerHealth[provider] = 'loading'; state.runtime.providerStats[provider].healthProbes++; renderProviderState();
    const ok = await probeImage(config.health_probe); state.runtime.providerHealth[provider] = ok ? 'ready' : 'failed'; recordRuntimeEvent(ok ? 'health_probe_passed' : 'health_probe_failed', provider); renderProviderState(); return ok;
  }
  function tileUrlAt(provider, lat, lon, zoom) {
    const config = provider === 'satellite' ? safeProviderConfig() : null; if (!config) return '';
    const n = 2 ** zoom, rad = lat * Math.PI / 180, x = Math.floor((lon + 180) / 360 * n), y = Math.floor((1 - Math.log(Math.tan(rad) + 1 / Math.cos(rad)) / Math.PI) / 2 * n);
    return safeProviderUrl(config.tile_template.replace('{z}', zoom).replace('{x}', x).replace('{y}', y));
  }
  async function testViewportProvider(provider) {
    const first = DATA.markers.find(item => markerVisible(item, { map: true })), center = first || DATA.region_cfg[state.task.region].center, zoom = state.task.region === 'overall' && state.task.date === 'all' ? 6 : 11;
    state.runtime.providerStats[provider].viewportProbes++; const ok = await probeImage(tileUrlAt(provider, center.lat, center.lon, zoom), 2800, 'viewport');
    if (!ok) state.runtime.providerHealth[provider] = 'failed'; renderProviderState(); return ok;
  }
  async function returnToSmart(provider, reason) {
    state.runtime.providerStats[provider].fallbacks++; state.runtime.providerHealth[provider] = 'failed'; state.runtime.provider = 'vector'; recordRuntimeEvent('fallback_to_smart', provider, { reason });
    const errorBox = document.getElementById('mapError'); if (errorBox && provider === 'satellite') { errorBox.querySelector('.map-error-message').textContent = m('satelliteFallback'); errorBox.hidden = false; }
    renderProviderState(); persist(); await drawMap(true); return false;
  }
  async function chooseProvider(provider) {
    if (!['vector', 'satellite'].includes(provider)) return false;
    if (provider === 'vector') { state.runtime.provider = 'vector'; document.getElementById('mapError').hidden = true; renderProviderState(); persist(); return drawMap(true); }
    const ok = await testProvider(provider) && await testViewportProvider(provider);
    if (!ok) { await returnToSmart(provider, 'probe_failure'); return false; }
    state.runtime.provider = provider; state.runtime.providerSwitches++; recordRuntimeEvent('provider_switch', provider, { from: 'vector' }); renderProviderState(); persist(); return drawMap(true);
  }
  function renderProviderState() {
    const provider = state.runtime.provider, health = state.runtime.providerHealth[provider] || 'untested', status = document.getElementById('providerStatus');
    const label = provider === 'vector' ? (health === 'ready' ? m('mapReady') : health === 'failed' ? m('mapUnavailable') : m('mapChecking')) : (health === 'ready' ? m('satelliteReady') : health === 'failed' ? m('satelliteUnavailable') : m('satelliteChecking'));
    const region = state.task.region === 'overall' ? m('overall') : DATA.region_cfg[state.task.region]?.[state.presentation.lang === 'ko' ? 'label' : 'label_en'] || state.task.region;
    const providerLabel = provider === 'vector' ? m('smartMap') : m('satellite');
    const summary = document.getElementById('mapCurrentSummary');
    if (summary) summary.textContent = `${providerLabel} · ${region}`;
    const optionsToggle = document.getElementById('mapOptionsToggle');
    if (optionsToggle) optionsToggle.setAttribute('aria-label', `${m('mapOptions')}: ${providerLabel} · ${region}`);
    if (status) { status.textContent = label; status.className = `map-status ${health === 'ready' ? 'ready' : health === 'failed' ? 'failed' : ''}`; }
    document.querySelectorAll('[data-provider]').forEach(button => { button.dataset.health = state.runtime.providerHealth[button.dataset.provider] || 'untested'; button.setAttribute('aria-pressed', String(button.dataset.provider === provider)); });
  }

  /* ----- Map adapter, route semantics, camera, and marker ownership ----- */
  function visibleRouteFeatures() {
    const routes = activeRoutes({ map: true }), features = [];
    for (const leg of DATA.legs || []) {
      if (!legVisible(leg, { map: true })) continue;
      const geometry = GEOMETRY[leg.leg_id], transfer = leg.render_style === 'transfer_dots', branch = leg.branch_kind || 'main';
      const kind = transfer ? 'transfer' : branch === 'swap' ? 'option' : ['bonus', 'conditional', 'recovery', 'choice'].includes(branch) ? branch : 'local';
      const coordinates = geometry?.coordinates || [[leg.from_latlon[1], leg.from_latlon[0]], [leg.to_latlon[1], leg.to_latlon[0]]];
      leg.routes.filter(route => routes.has(route)).forEach((route, index, active) => {
        const fromOccurrence = markerByKey[leg.from]?.occurrences.find(item => item.route === route && item.date.startsWith(leg.date));
        const toOccurrence = markerByKey[leg.to]?.occurrences.find(item => item.route === route && item.date.startsWith(leg.date));
        features.push({ type: 'Feature', geometry: { type: 'LineString', coordinates }, properties: { leg_id: leg.leg_id, label: leg.label, mode: leg.mode, note: leg.note, date: leg.date, route, color: safeColor(routeMeta[route].color), offset: (index - (active.length - 1) / 2) * (transfer ? 3.2 : 3), kind, branch, emphasis: route === state.task.primaryRoute ? 1 : .22, status: geometry?.status || 'conceptual_fallback', distance_km: geometry?.distance_km || 0, time: [fromOccurrence?.time, toOccurrence?.time].filter(Boolean).map(tr).join(' → ') } });
      });
    }
    return features;
  }
  function installRouteLayers(map) {
    markStartup('route_layer_install_start');
    const add = () => {
      if (map.getSource('trip-routes')) return;
      map.addSource('trip-routes', { type: 'geojson', data: { type: 'FeatureCollection', features: visibleRouteFeatures() } });
      const patterns = { transfer: [3, 2], conditional: [5, 2], option: [4, 2], bonus: [1, 2.4], recovery: [8, 3], choice: [2, 2] }, routePatterns = { solid: null, dash: [5, 2], dot: [1.2, 2.2], dashdot: [5, 1.4, 1.2, 1.4] };
      for (const kind of ['transfer', 'local', 'conditional', 'option', 'bonus', 'recovery', 'choice']) {
        const kindFilter = ['==', ['get', 'kind'], kind], transfer = kind === 'transfer', faint = kind === 'bonus';
        for (const route of ROUTES) {
          const filter = ['all', kindFilter, ['==', ['get', 'route'], route]], pattern = kind === 'local' ? routePatterns[routeMeta[route].pattern] : patterns[kind], color = safeColor(routeMeta[route].color);
          const casing = { 'line-color': state.presentation.theme === 'dark' ? '#14201b' : '#fffefa', 'line-width': transfer ? 6 : 5, 'line-opacity': ['case', ['==', ['get', 'emphasis'], 1], .9, .12], 'line-offset': ['get', 'offset'] };
          const paint = { 'line-color': color, 'line-width': transfer ? 4 : kind === 'local' ? 3.8 : 3.2, 'line-opacity': ['case', ['==', ['get', 'emphasis'], 1], faint ? .75 : 1, faint ? .12 : .2], 'line-offset': ['get', 'offset'] };
          if (pattern) { casing['line-dasharray'] = pattern; paint['line-dasharray'] = pattern; }
          map.addLayer({ id: `trip-${kind}-${route}-casing`, type: 'line', source: 'trip-routes', filter, layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: casing });
          map.addLayer({ id: `trip-${kind}-${route}`, type: 'line', source: 'trip-routes', filter, layout: { 'line-cap': 'round', 'line-join': 'round' }, paint });
        }
        const hitId = `trip-${kind}-hit`;
        map.addLayer({ id: hitId, type: 'line', source: 'trip-routes', filter: kindFilter, paint: { 'line-color': '#fff', 'line-width': 18, 'line-opacity': .001 } });
        map.on('mousemove', hitId, event => {
          const properties = event.features?.[0]?.properties;
          if (!properties || state.presentation.peek?.key) return;
          map.getCanvas().style.cursor = 'pointer'; showRoutePeek(properties, event.originalEvent);
        });
        map.on('mouseleave', hitId, () => { map.getCanvas().style.cursor = ''; if (state.presentation.peek?.route) scheduleHidePeek(); });
      }
      markStartup('route_layer_install_ready', { layers: map.getStyle()?.layers?.length || 0 });
    };
    if (map.isStyleLoaded()) add(); else map.once('load', add);
  }
  function showRoutePeek(properties, event) {
    const card = document.getElementById('peek');
    state.presentation.peek = { route: properties.route, invoker: document.activeElement };
    card.innerHTML = `<div class="peek-body"><div class="eyebrow">${esc(properties.route)} · ${esc(dateLabel(properties.date))}</div><h3 id="peekTitle" class="peek-title">${esc(tr(properties.label || ''))}</h3><p id="peekDescription" class="peek-why"><strong>${esc(tierLabel(properties.branch === 'main' ? 'main' : properties.branch))}</strong> · ${esc(modeLabel(properties.mode))}${properties.time ? ` · ${esc(properties.time)}` : ''}<br>${esc(tr(properties.note || ''))}</p><p class="peek-sub">${properties.status === 'routed_osm' ? m('recheck') : m('mapLegend')}</p><button class="peek-action" type="button" data-route-use>${m('chooseRoute')} ${esc(properties.route)} ↗</button></div>`;
    card.classList.add('show'); card.setAttribute('aria-hidden', 'false'); positionPeek(event, card); card.querySelector('[data-route-use]').onclick = () => choosePrimaryRoute(properties.route);
  }
  function mapObstacleRects() {
    const shell = document.querySelector('.map-shell');
    if (!shell) return [];
    const shellRect = shell.getBoundingClientRect();
    return [...document.querySelectorAll('.map-chrome, .maplibregl-ctrl, .workbench')].filter(element => {
      const style = getComputedStyle(element), rect = element.getBoundingClientRect();
      return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0 && rect.right > shellRect.left && rect.left < shellRect.right && rect.bottom > shellRect.top && rect.top < shellRect.bottom;
    }).map(element => {
      const rect = element.getBoundingClientRect();
      return { selector: element.className || element.tagName.toLowerCase(), left: rect.left - shellRect.left, top: rect.top - shellRect.top, right: rect.right - shellRect.left, bottom: rect.bottom - shellRect.top, width: rect.width, height: rect.height };
    });
  }
  function unionArea(rects) {
    const xs = [...new Set(rects.flatMap(rect => [Math.max(0, rect.left), Math.min(rect.right, rect.shellWidth || Infinity)]))].sort((a, b) => a - b);
    let area = 0;
    for (let index = 0; index < xs.length - 1; index += 1) {
      const left = xs[index], right = xs[index + 1];
      if (right <= left) continue;
      const intervals = rects.filter(rect => rect.left < right && rect.right > left).map(rect => [rect.top, rect.bottom]).sort((a, b) => a[0] - b[0]);
      let covered = 0, end = -Infinity;
      intervals.forEach(([top, bottom]) => { if (bottom > end) { covered += bottom - Math.max(top, end); end = bottom; } });
      area += (right - left) * covered;
    }
    return area;
  }
  function mapSafePadding(map = photoMap) {
    const shell = document.querySelector('.map-shell');
    if (!map || !shell) return isMobile() ? { top: 118, right: 30, bottom: 112, left: 30 } : { top: 170, right: 60, bottom: 100, left: 60 };
    const shellRect = shell.getBoundingClientRect(), padding = { top: MAP_SAFE_MARGIN, right: MAP_SAFE_MARGIN, bottom: MAP_SAFE_MARGIN, left: MAP_SAFE_MARGIN };
    for (const obstacle of mapObstacleRects()) {
      const touchesLeft = obstacle.left <= MAP_SAFE_MARGIN && obstacle.right > 0;
      const touchesRight = obstacle.right >= shellRect.width - MAP_SAFE_MARGIN && obstacle.left < shellRect.width;
      const touchesTop = obstacle.top <= MAP_SAFE_MARGIN && obstacle.bottom > 0;
      const touchesBottom = obstacle.bottom >= shellRect.height - MAP_SAFE_MARGIN && obstacle.top < shellRect.height;
      const mobileSideOverlay = isMobile() && (obstacle.selector.includes('map-top-left') || obstacle.selector.includes('map-bottom-left'));
      if (touchesLeft && !mobileSideOverlay) padding.left = Math.max(padding.left, obstacle.right + MAP_SAFE_MARGIN);
      if (touchesRight) padding.right = Math.max(padding.right, shellRect.width - obstacle.left + MAP_SAFE_MARGIN);
      if (touchesTop) padding.top = Math.max(padding.top, obstacle.bottom + MAP_SAFE_MARGIN);
      if (touchesBottom) padding.bottom = Math.max(padding.bottom, shellRect.height - obstacle.top + MAP_SAFE_MARGIN);
    }
    const horizontalBudget = Math.max(MAP_SAFE_MARGIN * 2, shellRect.width - MAP_SAFE_MARGIN * 2);
    const verticalBudget = Math.max(MAP_SAFE_MARGIN * 2, shellRect.height - MAP_SAFE_MARGIN * 2);
    if (padding.left + padding.right > horizontalBudget) {
      if (padding.left >= padding.right) {
        padding.left = Math.min(padding.left, horizontalBudget - MAP_SAFE_MARGIN);
        padding.right = Math.min(padding.right, horizontalBudget - padding.left);
      } else {
        padding.right = Math.min(padding.right, horizontalBudget - MAP_SAFE_MARGIN);
        padding.left = Math.min(padding.left, horizontalBudget - padding.right);
      }
    }
    if (padding.top + padding.bottom > verticalBudget) {
      if (padding.top >= padding.bottom) {
        padding.top = Math.min(padding.top, verticalBudget - MAP_SAFE_MARGIN);
        padding.bottom = Math.min(padding.bottom, verticalBudget - padding.top);
      } else {
        padding.bottom = Math.min(padding.bottom, verticalBudget - MAP_SAFE_MARGIN);
        padding.top = Math.min(padding.top, verticalBudget - padding.bottom);
      }
    }
    markStartup('map_safe_padding_computed', { padding: { ...padding } });
    return padding;
  }
  function mapGeometrySnapshot() {
    const shell = document.querySelector('.map-shell'), shellRect = shell?.getBoundingClientRect();
    if (!shell || !shellRect) return { obstacles: [], markers: [], safe_padding: null };
    const obstacles = mapObstacleRects();
    const intersects = (a, b) => a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
    const markers = [...document.querySelectorAll('.photo-marker, .photo-cluster, .route-leg-label')].filter(element => {
      const style = getComputedStyle(element), rect = element.getBoundingClientRect();
      return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
    }).map(element => {
      const rect = element.getBoundingClientRect(), effective = { left: rect.left - shellRect.left, top: rect.top - shellRect.top, right: rect.right - shellRect.left, bottom: rect.bottom - shellRect.top, width: rect.width, height: rect.height };
      const center = { x: (effective.left + effective.right) / 2, y: (effective.top + effective.bottom) / 2 };
      const hit = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
      return { key: element.dataset.placeKey || element.getAttribute('aria-label') || element.className, rect: effective, intersects_obstacle: obstacles.filter(obstacle => intersects(effective, obstacle)).map(obstacle => obstacle.selector), center_hit: hit?.closest?.('.photo-marker, .photo-cluster, .route-leg-label')?.className || hit?.className || null, center: center };
    });
    const persistent = obstacles.filter(obstacle => !/(map-options-panel|route-legend-panel)/.test(obstacle.selector)).map(obstacle => ({ ...obstacle, shellWidth: shellRect.width }));
    const shellArea = shellRect.width * shellRect.height, persistentArea = unionArea(persistent);
    const appbarRect = document.querySelector('.appbar')?.getBoundingClientRect();
    const workbenchRect = document.querySelector('.workbench')?.getBoundingClientRect();
    const usefulMapRatio = shellArea ? Math.max(0, shellArea - persistentArea) / shellArea : 0;
    return {
      shell: { width: shellRect.width, height: shellRect.height, area_px: shellArea },
      sheet_geometry: {
        viewport_height: window.innerHeight,
        appbar_height: appbarRect?.height || 0,
        map_height: shellRect.height,
        workbench_height: workbenchRect?.height || 0,
        useful_map_ratio: usefulMapRatio,
        sheet: state.presentation.sheet,
      },
      safe_padding: mapSafePadding(),
      obstacles,
      persistent_opaque_chrome: { area_px: persistentArea, ratio: shellArea ? persistentArea / shellArea : 0, rectangles: persistent },
      unobstructed_interior: { area_px: Math.max(0, shellArea - persistentArea), ratio: usefulMapRatio },
      markers,
    };
  }
  function fitVisibleMap(map = photoMap) {
    if (!map) return;
    markStartup('initial_fit_start');
    const visible = DATA.markers.filter(item => markerVisible(item, { map: true })), routePoints = visibleRouteFeatures().filter(feature => feature.properties.kind !== 'transfer').flatMap(feature => feature.geometry.coordinates), points = [...visible.map(item => [item.lon, item.lat]), ...routePoints];
    if (!points.length) return;
    if (points.length === 1) return map.jumpTo({ center: points[0], zoom: 13.1 });
    const bounds = [[Math.min(...points.map(point => point[0])), Math.min(...points.map(point => point[1]))], [Math.max(...points.map(point => point[0])), Math.max(...points.map(point => point[1]))]];
    map.fitBounds(bounds, { padding: mapSafePadding(map), maxZoom: state.task.date !== 'all' ? 12.8 : 7.8, duration: 0 });
    markStartup('initial_fit_complete');
  }
  function scheduleMapGeometryUpdate({ refit = false, reason = 'viewport' } = {}) {
    if (refit) geometryNeedsRefit = true;
    if (!photoMap) return Promise.resolve();
    const promise = new Promise(resolve => geometryWaiters.push(resolve));
    if (geometryFrame) return promise;
    geometryFrame = requestAnimationFrame(() => {
      geometryFrame = 0;
      const map = photoMap;
      const shouldRefit = geometryNeedsRefit;
      geometryNeedsRefit = false;
      if (map) {
        map.resize();
        if (shouldRefit && state.runtime.mapVisualReady) fitVisibleMap(map);
        if (state.presentation.mapOptionsOpen) positionMapOptions();
        if (state.presentation.routeLegendOpen) positionRouteLegend();
        markStartup('map_geometry_recomposed', { reason, refit: shouldRefit });
      }
      const waiters = geometryWaiters;
      geometryWaiters = [];
      waiters.forEach(resolve => resolve());
    });
    return promise;
  }
  function ringFor(marker) {
    const colors = marker.routes.filter(route => activeRoutes({ map: true }).has(route)).map(route => safeColor(routeMeta[route].color));
    if (colors.length === 1) return colors[0];
    return `conic-gradient(${colors.map((color, index) => `${color} ${index / colors.length * 100}% ${(index + 1) / colors.length * 100}%`).join(',')})`;
  }
  function preferredOccurrence(marker) {
    const routes = activeRoutes();
    return marker.occurrences.find(item => routes.has(item.route) && dateMatchesOccurrence(item)) || marker.occurrences.find(item => routes.has(item.route)) || marker.occurrences[0];
  }
  function groupOccurrences(marker) {
    const groups = {};
    marker.occurrences.filter(item => activeRoutes().has(item.route) && (state.task.date === 'all' || dateMatchesOccurrence(item))).forEach(item => {
      const signature = [item.date, item.time, item.title, item.reason, item.advantage, item.status].join('|');
      if (!groups[signature]) groups[signature] = { ...item, routes: [] };
      groups[signature].routes.push(item.route);
    });
    return Object.values(groups);
  }
  function updatePhotoClusters() {
    if (!photoMap) return;
    clusterMarkers.forEach(marker => marker.remove()); clusterMarkers = [];
    const visible = DATA.markers.filter(item => markerVisible(item, { map: true })), parent = Array.from({ length: visible.length }, (_, index) => index), root = index => { while (parent[index] !== index) index = parent[index]; return index; }, points = visible.map(item => photoMap.project([item.lon, item.lat])), threshold = photoMap.getZoom() < 7 ? 52 : 36;
    for (let i = 0; i < visible.length; i += 1) for (let j = i + 1; j < visible.length; j += 1) if (visible[i].place_key !== state.task.selected && visible[j].place_key !== state.task.selected && Math.hypot(points[i].x - points[j].x, points[i].y - points[j].y) < threshold) parent[root(j)] = root(i);
    const groups = {}; for (let i = 0; i < visible.length; i += 1) (groups[root(i)] ||= []).push(i);
    photoMarkers.forEach(marker => { marker.getElement().style.display = ''; });
    Object.values(groups).forEach(indexes => {
      if (indexes.length < 2) return;
      indexes.forEach(index => { photoMarkers[index].getElement().style.display = 'none'; });
      const members = indexes.map(index => visible[index]), center = [members.reduce((sum, item) => sum + item.lon, 0) / members.length, members.reduce((sum, item) => sum + item.lat, 0) / members.length], hero = members[0];
      const element = document.createElement('button'); element.type = 'button'; element.className = 'photo-cluster'; element.setAttribute('aria-label', `${members.length} ${m('stop')} · ${m('choosePlace')}`); element.innerHTML = `<img src="${photoSrc(photoPath(hero.place_key, 'hero', 'thumb'))}" alt=""><span class="cluster-count">${members.length}</span>`;
      const show = event => showClusterPeek(members, event, center);
      element.addEventListener('mouseenter', event => { if (!state.touch) show(event); }); element.addEventListener('focus', show); element.addEventListener('mouseleave', () => { if (!state.touch) scheduleHidePeek(); }); element.addEventListener('click', event => { event.stopPropagation(); show(event); photoMap.easeTo({ center, zoom: Math.max(photoMap.getZoom() + 2.2, 11), duration: 300 }); });
      clusterMarkers.push(new maplibregl.Marker({ element, anchor: 'center' }).setLngLat(center).addTo(photoMap));
    });
  }
  function bindLocalImageFailures(root) { root?.querySelectorAll('img').forEach(image => { if (!image.src.startsWith('data:')) image.addEventListener('error', () => showMapFailure(new Error(`Missing local photo ${image.getAttribute('src') || ''}`), 'photo_asset')); }); }
  function installPhotoMarkers(map, { deferClusters = false } = {}) {
    photoMap = map; photoMarkers = [];
    markStartup('photo_preparation_start');
    markStartup('marker_install_start', { count: DATA.markers.filter(item => markerVisible(item, { map: true })).length });
    DATA.markers.filter(item => markerVisible(item, { map: true })).forEach(marker => {
      const element = document.createElement('button'); element.type = 'button'; element.className = `photo-marker${state.task.selected === marker.place_key ? ' selected' : ''}${marker.source_class === 'official_gap_audit' ? ' audited' : ''}`; element.dataset.placeKey = marker.place_key; element.setAttribute('aria-label', `${m('choosePlace')}: ${placeName(marker.place_key)}`); element.title = placeName(marker.place_key); element.style.background = ringFor(marker);
      const occurrence = preferredOccurrence(marker), sequence = state.task.date === 'all' ? DATA.markers.indexOf(marker) + 1 : occurrence?.seq || DATA.markers.indexOf(marker) + 1;
      element.innerHTML = `<img src="${photoSrc(photoPath(marker.place_key, 'hero', 'thumb'))}" alt="" draggable="false"><span class="photo-seq">${sequence}</span>${marker.source_class === 'official_gap_audit' ? '<span class="audit-star" aria-hidden="true">★</span>' : ''}`;
      bindLocalImageFailures(element);
      element.addEventListener('mouseenter', event => { if (!state.touch) showPeek(marker.place_key, { event, focusAction: false }); });
      element.addEventListener('mouseleave', () => { if (!state.touch) scheduleHidePeek(); });
      element.addEventListener('focus', event => { if (suppressPeekFocusKey === marker.place_key) { suppressPeekFocusKey = null; return; } showPeek(marker.place_key, { event, focusAction: true }); });
      element.addEventListener('click', event => { event.stopPropagation(); selectPlace(marker.place_key, { focus: false, open: false, invoker: element }); showPeek(marker.place_key, { event, focusAction: false, invoker: element }); });
      photoMarkers.push(new maplibregl.Marker({ element, anchor: 'center' }).setLngLat([marker.lon, marker.lat]).addTo(map));
    });
    if (!map.__tripClusterHandlersInstalled) { map.on('zoomend', updatePhotoClusters); map.on('moveend', updatePhotoClusters); map.__tripClusterHandlersInstalled = true; }
    if (!deferClusters) updatePhotoClusters();
    markStartup('photo_preparation_ready', { markers: photoMarkers.length });
    markStartup('marker_install_ready', { markers: photoMarkers.length });
  }
  function installLegLabels(map) {
    legMarkers.forEach(marker => marker.remove()); legMarkers = [];
    DATA.legs.filter(leg => leg.render_style === 'transfer_dots' && legVisible(leg, { map: true })).forEach(leg => {
      const points = GEOMETRY[leg.leg_id]?.coordinates; if (!points?.length) return;
      const element = document.createElement('button'); element.type = 'button'; element.className = 'route-leg-label'; element.innerHTML = `<b>${esc(dateLabel(leg.date))} · ${esc(tr(leg.label))}</b><span>${leg.routes.filter(route => activeRoutes({ map: true }).has(route)).map(route => `<i style="background:${safeColor(routeMeta[route].color)}">${route}</i>`).join('')}</span>`; element.title = `${dateLabel(leg.date)} · ${tr(leg.label)}`;
      element.onclick = async event => { event.stopPropagation(); state.task.date = leg.date; state.presentation.mode = 'day'; renderAll(); persist(); await drawMap(false); };
      legMarkers.push(new maplibregl.Marker({ element, anchor: 'center' }).setLngLat(points[Math.floor(points.length / 2)]).addTo(map));
    });
  }
  function drawMap(preserve = true) {
    state.runtime.drawRequests += 1;
    markStartup('map_draw_requested', { request: state.runtime.drawRequests });
    const perform = async () => {
      const previous = photoMap, same = previous && renderedProvider === state.runtime.provider && renderedTheme === state.presentation.theme;
      clusterMarkers.forEach(marker => marker.remove()); clusterMarkers = []; photoMarkers.forEach(marker => marker.remove()); photoMarkers = []; legMarkers.forEach(marker => marker.remove()); legMarkers = [];
      if (same && state.runtime.localAssets.status === 'ready') {
        previous.getSource('trip-routes')?.setData({ type: 'FeatureCollection', features: visibleRouteFeatures() }); installPhotoMarkers(previous); installLegLabels(previous); renderMapLegend(); if (!preserve || mapGeometrySnapshot().markers.some(marker => marker.intersects_obstacle.length)) fitVisibleMap(previous); return true;
      }
      const view = preserve && previous ? { center: previous.getCenter(), zoom: previous.getZoom() } : null;
      if (previous) { previous.__tripCleanup?.(); previous.remove(); state.runtime.mapRemovals += 1; }
      const region = DATA.region_cfg[state.task.region];
      let map;
      try {
        map = new maplibregl.Map({ container: 'map', style: providerStyle(state.runtime.provider), center: [region.center.lon, region.center.lat], zoom: region.zoom, attributionControl: false, dragRotate: false, pitchWithRotate: false, maxZoom: 18 });
        photoMap = map; renderedProvider = state.runtime.provider; renderedTheme = state.presentation.theme; state.runtime.mapCreations += 1; state.runtime.mapStatus = 'loading'; renderProviderState(); markStartup('map_created');
        map.on('load', () => { markStartup('map_style_ready'); installRouteLayers(map); installPhotoMarkers(map, { deferClusters: true }); installLegLabels(map); if (view) map.jumpTo(view); else fitVisibleMap(map); updatePhotoClusters(); state.runtime.mapStatus = 'ready'; state.runtime.mapVisualReady = true; renderProviderState(); renderMapLegend(); renderShellStatus(); markStartup('map_visual_ready', { markers: photoMarkers.length, layers: map.getStyle()?.layers?.length || 0 }); });
        map.on('click', () => hidePeek({ returnFocus: false }));
        map.on('error', event => { if (localMapError(event)) showMapFailure(event.error || event.message, 'map_runtime'); });
        return true;
      } catch (error) { showMapFailure(error, 'map_create'); return false; }
    };
    drawQueue = drawQueue.then(perform, perform); return drawQueue;
  }

  /* ----- Peek and focus lifecycle ----- */
  function positionPeek(event, card) {
    if (isMobile()) return;
    const wrap = document.querySelector('.map-shell').getBoundingClientRect(); let left = (event?.clientX || wrap.left + wrap.width * .55) - wrap.left + 14, top = (event?.clientY || wrap.top + wrap.height * .44) - wrap.top + 14; const width = Math.min(318, wrap.width - 28), height = Math.min(420, wrap.height - 28);
    if (left + width > wrap.width) left = Math.max(8, left - width - 28); if (top + height > wrap.height) top = Math.max(8, top - height - 28); card.style.left = `${left}px`; card.style.top = `${top}px`; card.style.right = 'auto'; card.style.bottom = 'auto';
  }
  function showClusterPeek(members, event, center) {
    const card = document.getElementById('peek'), active = [...new Set(members.flatMap(item => item.routes.filter(route => activeRoutes({ map: true }).has(route))))];
    state.presentation.peek = { cluster: members.map(item => item.place_key), invoker: document.activeElement }; card.innerHTML = `<div class="peek-body"><div class="eyebrow">${esc(active.join(' · '))}</div><h3 id="peekTitle" class="peek-title">${members.length} ${m('stop')}</h3><p id="peekDescription" class="peek-why">${esc(members.slice(0, 4).map(item => placeName(item.place_key)).join(' · '))}</p><button class="peek-action" type="button" data-cluster-zoom>${m('choosePlace')} ↗</button></div>`; wirePeekHover(card); card.classList.add('show'); card.setAttribute('aria-hidden', 'false'); positionPeek(event, card); card.querySelector('[data-cluster-zoom]').onclick = () => { photoMap?.easeTo({ center, zoom: Math.max(photoMap.getZoom() + 2.2, 11), duration: 300 }); hidePeek(); };
  }
  function scheduleHidePeek() { clearTimeout(peekHideTimer); peekHideTimer = setTimeout(() => { const card = document.getElementById('peek'); if (!card?.matches(':hover')) hidePeek({ returnFocus: false }); }, 120); }
  function wirePeekHover(card) { card.onmouseenter = () => clearTimeout(peekHideTimer); card.onmouseleave = () => scheduleHidePeek(); }
  function showPeek(key, { event, focusAction = false, invoker } = {}) {
    const marker = markerByKey[key]; if (!marker) return;
    const card = document.getElementById('peek'), occurrence = preferredOccurrence(marker), groups = groupOccurrences(marker).slice(0, 3), tier = tierFor(marker); state.presentation.peek = { key, invoker: invoker || document.activeElement }; state.presentation.focusReturn = invoker || document.activeElement;
    card.innerHTML = `<img class="peek-media" src="${photoSrc(photoPath(key, 'hero', 'medium'))}" alt="${esc(placeName(key))}"><div class="peek-body"><h3 id="peekTitle" class="peek-title">${esc(placeName(key))}</h3>${state.presentation.lang === 'ko' ? `<p class="peek-sub">${esc(placeKo(key))}</p>` : ''}<div class="peek-meta"><span class="tier-chip">${esc(tierLabel(tier))}</span>${groups.map(group => `<span>${esc(group.routes.join('/'))} · ${esc(dateLabel(group.date))} · ${esc(tr(group.time || '—'))}</span>`).join('')}</div><p id="peekDescription" class="peek-why"><strong>${m('whyNow')}</strong> ${esc(tr(occurrence?.reason || marker.why))}</p>${occurrence?.advantage ? `<p class="peek-sub">${m('advantage')}: ${esc(tr(occurrence.advantage))}</p>` : ''}<button class="peek-action" type="button" data-peek-open>${m('openPlace')} ↗</button></div>`;
    bindLocalImageFailures(card); wirePeekHover(card); card.classList.add('show'); card.setAttribute('aria-hidden', 'false'); positionPeek(event, card);
    card.querySelector('[data-peek-open]').onclick = () => openPlace(key);
    if (focusAction) card.querySelector('[data-peek-open]').focus({ preventScroll: true });
  }
  function hidePeek({ returnFocus = true } = {}) {
    clearTimeout(peekHideTimer); const card = document.getElementById('peek'); if (!card) return; card.onmouseenter = null; card.onmouseleave = null; card.classList.remove('show'); card.setAttribute('aria-hidden', 'true'); card.innerHTML = '';
    const target = state.presentation.focusReturn, key = state.presentation.peek?.key; state.presentation.peek = null; state.presentation.focusReturn = null; if (returnFocus && target?.focus && document.contains(target)) { suppressPeekFocusKey = key || null; target.focus({ preventScroll: true }); }
  }
  function focusPlace(key) { const marker = markerByKey[key]; if (marker && photoMap) photoMap.easeTo({ center: [marker.lon, marker.lat], zoom: 13.3, duration: 300 }); }
  function updateMarkerEmphasis() { document.querySelectorAll('.photo-marker').forEach(element => element.classList.toggle('selected', element.dataset.placeKey === state.task.selected)); updatePhotoClusters(); }
  function selectPlace(key, { focus = true, open = false, invoker } = {}) {
    if (!markerByKey[key]) return;
    state.task.selected = key; state.task.selectedOccurrence = preferredOccurrence(markerByKey[key])?.date || null; if (focus) focusPlace(key); updateMarkerEmphasis(); renderDay(); renderPlace(); if (open) openPlace(key, invoker); persist();
  }
  function openPlace(key = state.task.selected, invoker) {
    if (!markerByKey[key]) return;
    state.presentation.previousMode = state.presentation.mode === 'place' ? 'day' : state.presentation.mode; state.presentation.previousContext = { date: state.task.date, selected: state.task.selected, scrollTop: document.querySelector('.workbench-scroll')?.scrollTop || 0 }; state.task.selected = key; state.presentation.mode = 'place'; hidePeek({ returnFocus: false }); renderAll(); document.querySelector('.workbench-scroll')?.scrollTo({ top: 0, behavior: 'smooth' }); persist();
  }
  function closePlace() {
    const previous = state.presentation.previousMode || 'day'; const context = state.presentation.previousContext; state.presentation.mode = previous; state.presentation.previousMode = null; state.presentation.previousContext = null; if (context?.date) state.task.date = context.date; renderAll(); requestAnimationFrame(() => { const scroll = document.querySelector('.workbench-scroll'); if (scroll && Number.isFinite(context?.scrollTop)) scroll.scrollTop = context.scrollTop; }); persist();
  }

  /* ----- Decide mode ----- */
  function routeProfile(route) {
    const meta = routeMeta[route], narrative = routeNarrative(route), scores = Object.entries(meta.score || {});
    return `<article class="route-card ${route === state.task.primaryRoute ? 'primary' : ''}" style="--route-color:${safeColor(meta.color)}"><div class="route-card-head"><div class="route-card-title"><strong>${esc(tr(meta.title))}</strong><small>${esc(tr(meta.subtitle || ''))}</small></div><span class="route-code-pill" aria-label="${m('routeCode')}">${esc(route)}</span></div><div class="score-line" aria-label="${m('routeScore')}">${scores.slice(0, 4).map(([key, value]) => `<span>${esc(state.presentation.lang === 'en' ? messages.scoreLabels[key] || key : key)} ${esc(value)}/10</span>`).join('')}</div><div class="route-card-actions"><button type="button" class="route-use" data-route="${esc(route)}" aria-pressed="${route === state.task.primaryRoute}">${route === state.task.primaryRoute ? m('currentRoute') : m('chooseRoute')}</button><button type="button" class="route-compare" data-compare-route="${esc(route)}" aria-pressed="${state.task.compareRoutes.has(route)}">${state.task.compareRoutes.has(route) ? m('compareRemove') : m('compareSelect')}</button></div></article>`;
  }
  function renderDecide() {
    const meta = routeMeta[recommendedRoute], narrative = routeNarrative(recommendedRoute), recommendation = document.getElementById('recommendation');
    recommendation.innerHTML = `<div class="route-code">${m('recommended')} · ${esc(recommendedRoute)}</div><h3>${esc(tr(meta.title))}</h3><p class="promise">${esc(tr(meta.subtitle || ''))}</p><div class="recommendation-grid"><div class="decision-cell"><strong>${m('bestFor')}</strong><span>${esc(narrative.best_for)}</span></div><div class="decision-cell"><strong>${m('tradeoff')}</strong><span>${esc(narrative.tradeoff)}</span></div><div class="decision-cell"><strong>${m('switchRule')}</strong><span>${esc(narrative.decision_rule)}</span></div><div class="decision-cell"><strong>${m('regretGuard')}</strong><span>${esc(narrative.regret_guard)}</span></div></div><div class="recommendation-footer"><span class="route-code">${m('routeCode')}: ${esc(recommendedRoute)} · ${esc(tr(meta.lodging || ''))}</span><button class="primary-action" type="button" data-route="${esc(recommendedRoute)}" data-recommendation-use>${state.task.primaryRoute === recommendedRoute ? m('currentRoute') : m('chooseRoute')}</button></div>`;
    document.getElementById('routeCards').innerHTML = ROUTES.map(routeProfile).join(''); document.getElementById('routeCount').textContent = `${ROUTES.length} ${m('route')}`; document.getElementById('compareCount').textContent = `${state.task.compareRoutes.size}/2`;
    recommendation.querySelector('[data-recommendation-use]').onclick = () => choosePrimaryRoute(recommendedRoute);
    document.querySelectorAll('[data-route]').forEach(button => { button.onclick = () => choosePrimaryRoute(button.dataset.route); });
    document.querySelectorAll('[data-compare-route]').forEach(button => { button.onclick = () => toggleCompare(button.dataset.compareRoute); });
    renderCompare();
  }
  function choosePrimaryRoute(route) { if (!ROUTES.includes(route)) return; state.task.primaryRoute = route; if (state.task.compareRoutes.has(route)) state.task.compareRoutes.delete(route); renderAll(); persist(); drawMap(true); }
  function toggleCompare(route) { if (state.task.compareRoutes.has(route)) state.task.compareRoutes.delete(route); else if (route !== state.task.primaryRoute && state.task.compareRoutes.size < 2) state.task.compareRoutes.add(route); renderDecide(); renderMapLegend(); persist(); drawMap(true); }
  function renderCompare() {
    const routes = [state.task.primaryRoute, ...state.task.compareRoutes].filter((route, index, all) => route && all.indexOf(route) === index).slice(0, 2), panel = document.getElementById('comparePanel');
    if (routes.length < 2) { panel.innerHTML = `<div class="compare-empty">${m('compareNeed')}<br>${m('compareHint')}</div>`; return; }
    const [first, second] = routes, a = routeMeta[first], b = routeMeta[second], an = routeNarrative(first), bn = routeNarrative(second), shared = DATA.legs.filter(leg => leg.routes.includes(first) && leg.routes.includes(second)).length, divergent = DATA.legs.filter(leg => leg.routes.includes(first) !== leg.routes.includes(second)).slice(0, 3).map(leg => tr(leg.label)).join(' · ');
    panel.innerHTML = `<div class="compare-head"><strong>${esc(first)} × ${esc(second)}</strong><span>${shared} ${m('sharedStructure').toLowerCase()} legs</span></div><div class="compare-grid"><article><strong>${esc(first)} · ${esc(tr(a.title))}</strong><p>${esc(an.best_for)}</p></article><article><strong>${esc(second)} · ${esc(tr(b.title))}</strong><p>${esc(bn.best_for)}</p></article></div><div class="compare-rows"><div class="compare-row"><b>${m('tradeoff')}</b><span>${esc(an.tradeoff)}<br><strong>${esc(second)}:</strong> ${esc(bn.tradeoff)}</span></div><div class="compare-row"><b>${m('switchRule')}</b><span>${esc(an.decision_rule)}<br><strong>${esc(second)}:</strong> ${esc(bn.decision_rule)}</span></div><div class="compare-row"><b>${m('divergentStructure')}</b><span>${esc(divergent || m('noSlots'))}</span></div></div>`;
  }

  /* ----- Day mode ----- */
  function routeMini(routes) { return routes.filter(route => activeRoutes().has(route)).map(route => `<span class="semantic-tag" style="border-color:${safeColor(routeMeta[route].color)};color:${safeColor(routeMeta[route].color)}">${esc(route)}</span>`).join(''); }
  function dayIntensity(items) { const tiers = items.map(item => item.schedule_tier || 'main'); if (tiers.filter(tier => tier === 'recovery').length >= 2) return m('calm'); if (tiers.includes('must') && items.length >= 8) return m('full'); return m('steady'); }
  function renderDatePicker() {
    const select = document.getElementById('dateSelect'); select.innerHTML = `<option value="all">${m('allDates')}</option>${DATA.dates.map(date => `<option value="${esc(date.key)}">${esc(dateLabel(date.key))}</option>`).join('')}`; select.value = state.task.date;
  }
  function renderDay() {
    renderDatePicker(); const items = DATA.timeline.filter(timelineVisible), header = document.getElementById('dayHeader'), plan = document.getElementById('dayPlan');
    if (state.task.date === 'all') { header.innerHTML = `<h3>${m('chooseDay')}</h3><p>${DATA.dates.length} ${m('day').toLowerCase()} · ${state.task.primaryRoute} · ${esc(m('recheck'))}</p>`; plan.innerHTML = DATA.dates.map(date => { const rows = DATA.timeline.filter(item => item.date_key === date.key && routeIntersects(item.routes)); const mapped = rows.find(item => item.spatial_keys?.length); return `<button type="button" class="day-item" data-day-choice="${esc(date.key)}" style="--tier-color:var(--accent)"><span class="day-time">${esc(dateLabel(date.key))}</span><span class="day-item-main"><span class="day-item-title">${esc(mapped ? placeName(mapped.spatial_keys[0]) : tr(rows[0]?.title || '—'))}</span><span class="day-item-reason">${rows.length} ${m('stop')} · ${esc(dayIntensity(rows))}</span><span class="day-item-tags"><span class="semantic-tag">${rows.length} items</span><span class="semantic-tag">${esc(DATA.region_cfg[rows[0]?.regions?.[0] || 'overall']?.label || m('overall'))}</span></span></span></button>`; }).join(''); plan.querySelectorAll('[data-day-choice]').forEach(button => { button.onclick = () => { state.task.date = button.dataset.dayChoice; renderAll(); persist(); drawMap(false); }; }); return; }
    const dayMeta = DATA.dates.find(date => date.key === state.task.date), regions = [...new Set(items.flatMap(item => item.regions || []))].map(region => DATA.region_cfg[region]?.[state.presentation.lang === 'ko' ? 'label' : 'label_en'] || m(region)).join(' · '), recovery = items.filter(item => ['recovery', 'bonus'].includes(item.schedule_tier)).length, decisions = items.filter(item => ['swap', 'conditional', 'choice'].includes(item.schedule_tier)).length;
    header.innerHTML = `<h3>${esc(dateLabel(dayMeta?.key || state.task.date))}</h3><p>${esc(regions || m('overall'))} · ${esc(state.task.primaryRoute)} · ${esc(m('recheck'))}</p><div class="day-metrics"><span class="day-metric">${m('intensity')}: ${esc(dayIntensity(items))}</span><span class="day-metric">${m('decisions')}: ${decisions}</span><span class="day-metric">${m('calm')}: ${recovery}</span></div>`;
    if (!items.length) { plan.innerHTML = `<div class="empty-state">${m('noSlots')}</div>`; return; }
    plan.innerHTML = `<p class="day-story">${esc(tr(items[0]?.reason || ''))}</p>${items.map(item => { const mapped = item.spatial_keys?.length, tier = item.schedule_tier || 'main', color = tier === 'must' ? '#a94335' : tier === 'swap' ? '#a76a42' : tier === 'recovery' ? '#72857b' : 'var(--accent)'; return mapped ? `<button type="button" class="day-item ${item.spatial_keys.includes(state.task.selected) ? 'selected' : ''}" data-day-place="${esc(item.spatial_keys[0])}" style="--tier-color:${color}"><span class="day-time">${esc(tr(item.time || '—'))}</span><span class="day-item-main"><span class="day-item-title">${esc(item.spatial_keys.length === 1 ? placeName(item.spatial_keys[0]) : tr(item.title))}</span><span class="day-item-reason"><strong>${esc(m('whyNow'))}:</strong> ${esc(tr(item.reason || ''))}</span><span class="day-item-tags"><span class="tier-chip">${esc(tierLabel(tier))}</span>${item.route_specific ? `<span class="semantic-tag">${m('specific')}</span>` : `<span class="semantic-tag">${m('shared')}</span>`}${routeMini(item.routes)}</span></span></button>` : `<article class="plan-card" style="--tier-color:${color}"><strong>${esc(tr(item.time || '—'))} · ${esc(tr(item.title))}</strong><p>${esc(tr(item.reason || item.advantage || ''))} · ${m('noMapped')}</p><div class="day-item-tags"><span class="tier-chip">${esc(tierLabel(tier))}</span>${routeMini(item.routes)}</div></article>`; }).join('')}`;
    plan.querySelectorAll('[data-day-place]').forEach(button => { button.onclick = () => { selectPlace(button.dataset.dayPlace, { focus: true, open: false, invoker: button }); showPeek(button.dataset.dayPlace, { invoker: button }); }; });
  }

  /* ----- Place mode: browser, Peek -> Inspector, and return ----- */
  function renderPlaceBrowser() {
    const visible = DATA.markers.filter(item => markerVisible(item)), html = `<div class="place-browser"><p class="place-browser-intro">${m('browseHint')} ${visible.length} ${m('stop')} · ${esc(state.task.primaryRoute)}</p>${visible.map(marker => { const occurrence = preferredOccurrence(marker); return `<button type="button" class="place-list-item" data-place-choice="${esc(marker.place_key)}"><img src="${photoSrc(photoPath(marker.place_key, 'hero', 'thumb'))}" alt=""><span><strong>${esc(placeName(marker.place_key))}</strong>${state.presentation.lang === 'ko' ? `<small>${esc(placeKo(marker.place_key))}</small>` : ''}<small>${esc(dateLabel(occurrence?.date || ''))} · ${esc(tr(occurrence?.time || '—'))}</small><em>${esc(tr(occurrence?.reason || marker.why))}</em></span></button>`; }).join('')}</div>`; const panel = document.getElementById('placeInspector'); panel.innerHTML = html; panel.querySelectorAll('[data-place-choice]').forEach(button => { button.onclick = () => openPlace(button.dataset.placeChoice, button); });
  }
  function renderPlaceInspector(marker) {
    const panel = document.getElementById('placeInspector'), occurrences = groupOccurrences(marker), now = preferredOccurrence(marker), tier = tierFor(marker), photos = [[m('hero'), 'hero'], [m('experiencePhoto'), 'experience'], [m('scale'), 'scale_context']], mapsHref = safeExternalUrl(marker.maps_url);
    panel.innerHTML = `<button type="button" class="secondary-action place-back" data-place-back>← ${m('closePlace')}</button><div class="place-title-row"><div><h3>${esc(placeName(marker.place_key))}</h3>${state.presentation.lang === 'ko' ? `<p>${esc(placeKo(marker.place_key))}</p>` : ''}</div><span class="place-score">${esc(marker.score)}/100</span></div><div class="place-meta"><span>${esc(tr(marker.cluster))}</span><span>${esc(tierLabel(tier))}</span><span>${marker.routes.filter(route => activeRoutes().has(route)).join(' · ')}</span></div><div class="place-glance"><strong>${esc(tr(now?.status || m('status')))} · ${esc(dateLabel(now?.date || ''))} · ${esc(tr(now?.time || '—'))}</strong><div><b>${m('whyNow')}</b> ${esc(tr(now?.reason || marker.why))}</div>${now?.advantage ? `<em>${m('advantage')}: ${esc(tr(now.advantage))}</em>` : ''}</div><div class="photo-grid">${photos.map(([label, role]) => `<figure class="photo-slot"><img src="${photoSrc(photoPath(marker.place_key, role, 'medium'))}" alt="${esc(placeName(marker.place_key))} — ${esc(label)}" loading="lazy"><figcaption>${esc(label)}</figcaption></figure>`).join('')}</div><div class="place-fact"><strong>${m('placeWhy')}</strong>${esc(tr(marker.why))}</div><div class="place-fact"><strong>${m('experience')}</strong>${esc(tr(marker.summary))}</div><div class="place-fact"><strong>${m('exactTiming')}</strong>${occurrences.length ? occurrences.map(item => `<div class="occurrence"><b>${esc(tr(item.title))}</b><small>${esc(item.routes.join(' · '))} · ${esc(dateLabel(item.date))} · ${esc(tr(item.time || '—'))} · ${esc(tr(item.status || ''))}</small><small>${m('whyNow')}: ${esc(tr(item.reason || ''))}</small></div>`).join('') : `<span class="muted">${m('noSlots')}</span>`}</div>${marker.decision_rules?.length ? `<div class="place-fact"><strong>${m('switchRule')}</strong>${marker.decision_rules.map(rule => `<div class="decision-rule"><b>${esc(decisionLabel(rule.key))}</b>${esc(tr(rule.text))}</div>`).join('')}</div>` : ''}<div class="place-fact"><strong>${m('freshness')}</strong><span>${esc(m('recheck'))}</span></div><div class="place-fact directions"><span>${marker.lat.toFixed(5)}, ${marker.lon.toFixed(5)}</span>${mapsHref ? `<a href="${esc(mapsHref)}" target="_blank" rel="noopener noreferrer" referrerpolicy="no-referrer">${m('directions')} ↗</a>` : `<span>${m('unavailableDirections')}</span>`}</div>`;
    bindLocalImageFailures(panel); panel.querySelector('[data-place-back]').onclick = closePlace;
  }
  function renderPlace() { const marker = markerByKey[state.task.selected]; if (state.presentation.mode === 'place' && marker) renderPlaceInspector(marker); else if (state.presentation.mode === 'place') renderPlaceBrowser(); }

  /* ----- Shell, i18n, transitions, focus, and responsive sheet ----- */
  function positionMapOptions() {
    const shell = document.querySelector('.map-shell'), surface = document.getElementById('mapControlSurface'), panel = document.getElementById('mapOptionsPanel');
    if (!shell || !surface || !panel || panel.hidden) return;
    const shellRect = shell.getBoundingClientRect();
    panel.classList.remove('open-up', 'align-right');
    const panelRect = panel.getBoundingClientRect(), surfaceRect = surface.getBoundingClientRect();
    if (panelRect.bottom > shellRect.bottom - 8) panel.classList.add('open-up');
    if (surfaceRect.left + panelRect.width > shellRect.right - 8) panel.classList.add('align-right');
  }
  function setMapOptionsOpen(open, { returnFocus = true, focus = true } = {}) {
    const toggle = document.getElementById('mapOptionsToggle'), panel = document.getElementById('mapOptionsPanel');
    if (!toggle || !panel) return;
    state.presentation.mapOptionsOpen = open;
    if (open) mapOptionsInvoker = toggle;
    panel.hidden = !open; toggle.setAttribute('aria-expanded', String(open));
    if (open) {
      requestAnimationFrame(() => { positionMapOptions(); fitVisibleMap(); if (focus) panel.querySelector('[data-provider], [data-region], #mapOptionsClose')?.focus({ preventScroll: true }); });
    } else {
      panel.classList.remove('open-up', 'align-right');
      const restore = returnFocus && mapOptionsInvoker?.focus && document.contains(mapOptionsInvoker) ? mapOptionsInvoker : null;
      requestAnimationFrame(() => { fitVisibleMap(); if (restore) requestAnimationFrame(() => restore.focus({ preventScroll: true })); });
      mapOptionsInvoker = null;
    }
  }
  function positionRouteLegend() {
    const shell = document.querySelector('.map-shell'), surface = document.getElementById('mapLegend'), panel = document.getElementById('routeLegendPanel');
    if (!shell || !surface || !panel || panel.hidden) return;
    const shellRect = shell.getBoundingClientRect(); panel.classList.remove('open-down');
    if (panel.getBoundingClientRect().top < shellRect.top + 8) panel.classList.add('open-down');
  }
  function setRouteLegendOpen(open, { returnFocus = true } = {}) {
    const toggle = document.getElementById('routeLegendToggle'), panel = document.getElementById('routeLegendPanel');
    if (!toggle || !panel) return;
    state.presentation.routeLegendOpen = open;
    if (open) routeLegendInvoker = toggle;
    panel.hidden = !open; toggle.setAttribute('aria-expanded', String(open));
    if (open) requestAnimationFrame(() => { positionRouteLegend(); fitVisibleMap(); });
    else { panel.classList.remove('open-down'); const restore = returnFocus && routeLegendInvoker?.focus && document.contains(routeLegendInvoker) ? routeLegendInvoker : null; requestAnimationFrame(() => { fitVisibleMap(); if (restore) requestAnimationFrame(() => restore.focus({ preventScroll: true })); }); routeLegendInvoker = null; }
  }
  function renderMapControls() {
    const provider = document.getElementById('providerControls'), region = document.getElementById('regionControls');
    provider.innerHTML = ['vector', 'satellite'].map(key => `<button type="button" class="segment" data-provider="${key}" aria-pressed="${state.runtime.provider === key}">${key === 'vector' ? m('smartMap') : m('satellite')}</button>`).join('');
    region.innerHTML = Object.keys(DATA.region_cfg).map(key => `<button type="button" class="segment" data-region="${esc(key)}" aria-pressed="${state.task.region === key}">${esc(key === 'overall' ? m('overall') : DATA.region_cfg[key][state.presentation.lang === 'ko' ? 'label' : 'label_en'] || key)}</button>`).join('');
    const panel = document.getElementById('mapOptionsPanel'), toggle = document.getElementById('mapOptionsToggle');
    if (panel && toggle) { panel.hidden = !state.presentation.mapOptionsOpen; toggle.setAttribute('aria-expanded', String(state.presentation.mapOptionsOpen)); }
    provider.querySelectorAll('[data-provider]').forEach(button => { button.onclick = async () => { setMapOptionsOpen(false); await chooseProvider(button.dataset.provider); }; });
    region.querySelectorAll('[data-region]').forEach(button => { button.onclick = () => { setMapOptionsOpen(false); state.task.region = button.dataset.region; if (state.task.selected && !markerVisible(markerByKey[state.task.selected])) state.task.selected = null; renderAll(); persist(); drawMap(false); }; });
    renderProviderState();
  }
  function renderMapLegend() {
    const current = state.task.primaryRoute, meta = routeMeta[current], currentLabel = document.getElementById('routeLegendCurrent'), panel = document.getElementById('routeLegendPanel'), toggle = document.getElementById('routeLegendToggle');
    if (!currentLabel || !panel || !toggle) return;
    currentLabel.textContent = `${m('current')}: ${current} · ${tr(meta.title)}`;
    panel.innerHTML = ROUTES.map(route => { const item = routeMeta[route], pattern = ['solid', 'dash', 'dot', 'dashdot'].includes(item.pattern) ? item.pattern : 'solid', narrative = routeNarrative(route); return `<div class="route-legend-item"><i class="route-legend-swatch ${pattern}" style="--route-color:${safeColor(item.color)}" aria-hidden="true"></i><span><strong>${esc(route)} · ${esc(tr(item.title))}</strong><small>${esc(tr(narrative.best_for || item.core_reason || ''))}</small></span></div>`; }).join('');
    panel.hidden = !state.presentation.routeLegendOpen; toggle.setAttribute('aria-expanded', String(state.presentation.routeLegendOpen));
  }
  function renderShellStatus() {
    const status = document.getElementById('workbenchStatus'); if (!status) return; const mode = state.presentation.mode === 'decide' ? m('decide') : state.presentation.mode === 'day' ? m('day') : m('place'); const context = state.presentation.mode === 'day' && state.task.date !== 'all' ? dateLabel(state.task.date) : state.task.primaryRoute; status.textContent = `${mode} · ${context}`;
  }
  function applyTranslations() {
    document.documentElement.lang = state.presentation.lang; document.documentElement.dataset.theme = state.presentation.theme;
    document.querySelectorAll('[data-i18n]').forEach(element => { const key = element.dataset.i18n; element.textContent = m(key); });
    document.querySelector('.brand').textContent = m('brand'); document.querySelector('.sub').textContent = m('subtitle');
    const fieldSet = document.querySelector('.route-section .eyebrow'); if (fieldSet) fieldSet.textContent = m('fieldSet');
    const routeHeading = document.getElementById('routeSectionHeading'); if (routeHeading) routeHeading.textContent = m('routeStrategies');
    const compareKicker = document.querySelector('.compare-section .eyebrow'); if (compareKicker) compareKicker.textContent = m('compareKicker');
    document.getElementById('langToggle').textContent = state.presentation.lang === 'ko' ? 'EN' : '한국어'; document.getElementById('themeToggle').textContent = state.presentation.theme === 'dark' ? `☀ ${m('light')}` : `☾ ${m('dark')}`;
    document.getElementById('workbenchToggle').textContent = state.presentation.sheet === 'compact' ? m('expand') : m('collapse');
    syncSheetPresentation();
    renderProviderState();
    document.querySelectorAll('[data-sheet]').forEach(button => { if (button.classList.contains('icon-button')) { button.setAttribute('aria-pressed', String(button.dataset.sheet === state.presentation.sheet)); button.title = m(button.dataset.sheet); button.setAttribute('aria-label', m(button.dataset.sheet)); } });
  }
  function setMode(mode) { if (!['decide', 'day', 'place'].includes(mode)) return; if (mode === 'place' && !state.task.selected) state.presentation.mode = 'place'; else state.presentation.mode = mode; renderAll(); persist(); }
  function syncSheetPresentation() {
    const app = document.getElementById('app'), workbench = document.getElementById('workbench'), scroll = workbench?.querySelector('.workbench-scroll');
    if (!app || !workbench) return;
    const compact = state.presentation.sheet === 'compact';
    app.dataset.sheet = state.presentation.sheet;
    workbench.dataset.sheet = state.presentation.sheet;
    app.classList.toggle('app-collapsed', compact && !isMobile());
    if (scroll) {
      scroll.hidden = compact;
      scroll.inert = compact;
      scroll.setAttribute('aria-hidden', String(compact));
    }
    if (compact && !isMobile() && workbench.contains(document.activeElement)) {
      requestAnimationFrame(() => document.getElementById('workbenchToggle')?.focus({ preventScroll: true }));
    }
  }
  function setSheet(sheet) {
    if (!['compact', 'expanded', 'full'].includes(sheet)) return;
    const previous = state.presentation.sheet;
    state.presentation.sheet = sheet;
    syncSheetPresentation();
    document.getElementById('workbenchToggle').setAttribute('aria-expanded', String(sheet !== 'compact'));
    applyTranslations();
    scheduleMapGeometryUpdate({ refit: previous !== sheet, reason: `sheet:${sheet}` });
    persist();
  }
  function renderModes() {
    const mode = state.presentation.mode, workbench = document.getElementById('workbench'); workbench.dataset.mode = mode; document.querySelectorAll('[data-mode]').forEach(button => { const active = button.dataset.mode === mode; button.classList.toggle('active', active); if (active) button.setAttribute('aria-current', 'page'); else button.removeAttribute('aria-current'); }); document.querySelectorAll('.mode-view').forEach(view => { const active = view.dataset.view === mode; view.hidden = !active; view.classList.toggle('active', active); });
  }
  function renderAll() { applyTranslations(); renderMapControls(); renderModes(); renderShellStatus(); renderDecide(); if (state.presentation.mode === 'day') renderDay(); if (state.presentation.mode === 'place') renderPlace(); renderMapLegend(); }
  function bindShell() {
    document.querySelectorAll('[data-mode]').forEach(button => { button.onclick = () => setMode(button.dataset.mode); });
    document.querySelectorAll('[data-sheet]').forEach(button => { if (button.classList.contains('icon-button')) button.onclick = () => setSheet(button.dataset.sheet); });
    document.getElementById('workbenchToggle').onclick = () => setSheet(state.presentation.sheet === 'compact' ? 'expanded' : 'compact');
    document.getElementById('mapOptionsToggle').onclick = () => setMapOptionsOpen(!state.presentation.mapOptionsOpen);
    document.getElementById('mapOptionsClose').onclick = () => setMapOptionsOpen(false);
    document.getElementById('routeLegendToggle').onclick = () => setRouteLegendOpen(!state.presentation.routeLegendOpen);
    document.getElementById('langToggle').onclick = () => { state.presentation.lang = state.presentation.lang === 'ko' ? 'en' : 'ko'; hidePeek({ returnFocus: false }); renderAll(); persist(); drawMap(true); };
    document.getElementById('themeToggle').onclick = () => { state.presentation.theme = state.presentation.theme === 'dark' ? 'light' : 'dark'; renderAll(); persist(); drawMap(true); };
    document.getElementById('fitMap').onclick = () => fitVisibleMap();
    document.getElementById('smartRetry').onclick = async () => { document.getElementById('mapError').hidden = true; state.runtime.provider = 'vector'; state.runtime.providerHealth.vector = 'loading'; state.runtime.localAssets.status = 'checking'; renderProviderState(); try { await setupVector(); await drawMap(true); } catch (error) { showMapFailure(error, 'retry'); } };
    document.getElementById('dateSelect').onchange = event => { state.task.date = event.target.value; if (state.task.selected && !markerVisible(markerByKey[state.task.selected])) state.task.selected = null; state.presentation.mode = 'day'; renderAll(); persist(); drawMap(false); };
    const handleEscape = event => { if (event.key !== 'Escape') return; if (state.presentation.mapOptionsOpen) { setMapOptionsOpen(false); event.preventDefault(); return; } if (state.presentation.routeLegendOpen) { setRouteLegendOpen(false); event.preventDefault(); return; } if (state.presentation.peek) { hidePeek(); event.preventDefault(); return; } if (state.presentation.mode === 'place') { closePlace(); event.preventDefault(); return; } if (state.presentation.sheet === 'full') { setSheet('expanded'); event.preventDefault(); } };
    document.onkeydown = handleEscape;
    document.body?.addEventListener('keydown', handleEscape);
    document.addEventListener('pointerdown', event => { if (state.presentation.mapOptionsOpen && !event.target.closest('#mapControlSurface')) setMapOptionsOpen(false); if (state.presentation.routeLegendOpen && !event.target.closest('#mapLegend')) setRouteLegendOpen(false); });
    const handleViewportChange = () => {
      syncSheetPresentation();
      renderModes();
      scheduleMapGeometryUpdate({ refit: true, reason: 'viewport' });
    };
    window.addEventListener('resize', handleViewportChange);
    const mapShell = document.querySelector('.map-shell');
    if (window.ResizeObserver && mapShell) {
      new ResizeObserver(entries => {
        const rect = entries[0]?.contentRect;
        const next = rect ? `${Math.round(rect.width)}x${Math.round(rect.height)}` : '';
        if (!next || next === observedMapSize) return;
        observedMapSize = next;
        scheduleMapGeometryUpdate({ refit: true, reason: 'map-shell-resize' });
      }).observe(mapShell);
    }
  }

  /* ----- QA instrumentation and compatibility surface ----- */
  function runtimeSnapshot() {
    return { provider: state.runtime.provider, provider_identity: state.runtime.providerIdentity, provider_health: { ...state.runtime.providerHealth }, app_ready: state.runtime.mapStatus === 'ready', map_visual_ready: state.runtime.mapVisualReady, planning_state: { routes: [...activeRoutes()], primary_route: state.task.primaryRoute, compare_routes: [...state.task.compareRoutes], date: state.task.date, region: state.task.region, selected: state.task.selected, mode: state.presentation.mode, sheet: state.presentation.sheet, lang: state.presentation.lang, theme: state.presentation.theme }, provider_events: state.runtime.providerEvents.slice(), local_assets: { status: state.runtime.localAssets.status, failures: state.runtime.localAssets.failures.slice() }, startup: { marks: [...(window.__tripStartupMarks || [])] }, runtime: { ...state.runtime, events: state.runtime.events.slice() }, map: { canvas_count: document.querySelectorAll('.maplibregl-canvas').length, photo_markers: document.querySelectorAll('.photo-marker').length, photo_marker_keys: [...document.querySelectorAll('.photo-marker')].map(element => element.dataset.placeKey), clusters: document.querySelectorAll('.photo-cluster').length, leg_markers: document.querySelectorAll('.route-leg-label').length, layers: photoMap?.getStyle?.()?.layers?.length || 0 } };
  }
  function renderFixture(value) {
    const marker = DATA.markers[0], saved = marker ? JSON.parse(JSON.stringify(marker)) : null;
    if (!marker) return { html: '', href: null, unsafe_nodes: 0 };
    try { marker.why = value; marker.summary = value; marker.maps_url = value; marker.name = value; state.task.selected = marker.place_key; renderPlaceInspector(marker); const panel = document.getElementById('placeInspector'); return { html: panel.innerHTML, href: panel.querySelector('a')?.getAttribute('href') || null, unsafe_nodes: panel.querySelectorAll('script,[onerror],[onclick],[onload],[javascript]').length }; }
    finally { Object.assign(marker, saved); renderPlace(); }
  }
  function expose() {
    window.__tripApp = { state, DATA, drawMap, whenIdle: () => Promise.all([drawQueue, scheduleMapGeometryUpdate()]), whenGeometryIdle: () => scheduleMapGeometryUpdate(), map: () => photoMap, whenMapVisualReady: () => Promise.resolve(runtimeSnapshot().map), selectPlace, chooseProvider, testProvider, setMode, setSheet, setTab: tab => setMode(tab === 'timeline' ? 'day' : tab === 'details' ? 'place' : 'decide'), markerVisible, timelineVisible, legVisible, visibleRouteFeatures, renderTimeline: renderDay, renderDetail: key => { if (key) state.task.selected = key; renderPlace(); }, showPreview: showPeek, showRoutePeek: properties => showRoutePeek(properties), hidePreview: hidePeek, fitVisibleMap, mapGeometrySnapshot, runtimeSnapshot };
    window.__tripSecurity = { escapeHtml: esc, safeExternalUrl, safePhotoPath: photoPath, renderFixture, allowedStorageKeys: ['trip_visualizer_runtime_v2', 'trip_visualizer_runtime_v1', 'trip_lang', 'trip_theme'] };
  }
  async function init() {
    markStartup('init_start'); state.touch = ('ontouchstart' in window) || navigator.maxTouchPoints > 0; expose(); renderAll(); bindShell(); markStartup('decision_shell_ready', { dom_nodes: document.body.querySelectorAll('*').length });
    setStatus(state.presentation.lang === 'ko' ? '로컬 Smart 지도와 결정 화면을 준비하는 중입니다.' : 'Preparing the local Smart map and decision views.');
    try { if (window.__tripRuntimeReady) await window.__tripRuntimeReady; await setupVector(); await drawMap(false); setStatus(m('mapReady')); markStartup('init_complete'); } catch (error) { showMapFailure(error, 'initialization'); }
  }
  const boot = () => init().catch(error => showMapFailure(error, 'initialization'));
  if (document.readyState === 'loading') window.addEventListener('DOMContentLoaded', boot, { once: true });
  else queueMicrotask(boot);
})();
