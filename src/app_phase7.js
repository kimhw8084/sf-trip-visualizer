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
  let geometryFrame = 0;
  let geometryNeedsRefit = false;
  let geometryWaiters = [];
  let observedMapSize = null;
  let satelliteFallbackFlight = null;
  let smartCamera = null;

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
  const tx = (record, field) => record?.[`${field}_${state.presentation.lang}`] || tr(record?.[field] ?? '');
  const formatMoney = cents => new Intl.NumberFormat(state.presentation.lang === 'ko' ? 'ko-KR' : 'en-US', { style: 'currency', currency: 'USD' }).format((Number(cents) || 0) / 100);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
  const isMobile = () => window.matchMedia('(max-width:800px)').matches;
  const safeColor = value => /^#[0-9a-f]{6}$/i.test(String(value ?? '')) ? String(value) : '#72857b';
  const photoPath = (key, role, variant) => /^[a-z0-9]+(?:_[a-z0-9]+)*$/i.test(String(key ?? '')) && SAFE_PHOTO_ROLES.has(role) && SAFE_PHOTO_VARIANTS.has(variant) ? `assets/photos/${variant}/${key}__${role}.webp` : SAFE_PIXEL;
  const photoSrc = path => window.EMBEDDED_PHOTOS?.[path] || path;
  const placeName = key => I18N.places[key]?.[0] || markerByKey[key]?.name || key;
  const placeKo = key => I18N.places[key]?.[1] || '';
  const roleFor = (key, route) => DATA.route_roles?.[key]?.[route] || (markerByKey[key]?.routes?.includes(route) ? 'Strong' : 'Skip');
  const roleShort = role => ({ Core: 'C', Strong: 'S', Conditional: '△', Skip: '—' }[role] || '—');
  const roleLabel = role => m({ Core: 'roleCore', Strong: 'roleStrong', Conditional: 'roleConditional', Skip: 'roleSkip' }[role] || 'roleSkip');
  function placeRoleMarkup(key, route = state.task.primaryRoute) {
    const role = roleFor(key, route);
    return `<span class="place-role role-${role.toLowerCase()}" data-role="${esc(role)}">${esc(roleLabel(role))}</span>`;
  }
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
    if (map && state.presentation.mode === 'decide') return new Set(ROUTES);
    if (state.task.routes.size) return new Set(state.task.routes);
    return new Set([state.task.primaryRoute]);
  }
  function routeIntersects(routes, options) { return (routes || []).some(route => activeRoutes(options).has(route)); }
  const occurrenceDateKey = item => item?.date_key || String(item?.date || '').split(' ')[0];
  function dateMatchesOccurrence(item) { return state.task.date === 'all' || occurrenceDateKey(item) === state.task.date; }
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
    if (from && to && !leg.routes.some(route => routes.has(route) && from.occurrences.some(item => item.route === route && occurrenceDateKey(item) === leg.date) && to.occurrences.some(item => item.route === route && occurrenceDateKey(item) === leg.date))) return false;
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
  function safeOfficialSourceUrl(value) {
    try {
      const url = new URL(String(value ?? ''));
      const hosts = new Set(['flysfo.com', 'foodwise.org', 'home.nps.gov', 'www.nps.gov', 'nps.gov', 'gomuirwoods.com', 'www.goldengate.org', 'goldengate.org', 'alcatrazcitycruises.com', 'www.sfmta.com', 'sfmta.com', 'www.goldengatefortunecookies.com', 'parks.ca.gov', 'ci.carmel.ca.us', 'www.pebblebeach.com', 'www.montereybayaquarium.org', 'gggp.org', 'www.gggp.org', 'museum.stanford.edu', 'presidio.gov']);
      return url.protocol === 'https:' && !url.username && !url.password && !url.port && !url.hash && hosts.has(url.hostname) ? url.href : '';
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
  function clearMapFeedback() {
    const errorBox = document.getElementById('mapError'), retry = document.getElementById('smartRetry');
    if (errorBox) errorBox.hidden = true;
    if (retry) { retry.dataset.retryProvider = 'vector'; retry.textContent = m('retrySmart'); }
  }
  function showSatelliteFallbackFeedback() {
    const errorBox = document.getElementById('mapError'), retry = document.getElementById('smartRetry');
    if (!errorBox) return;
    errorBox.querySelector('.map-error-message').textContent = m('satelliteFallback');
    errorBox.hidden = false;
    if (retry) { retry.dataset.retryProvider = 'satellite'; retry.textContent = m('retrySatellite'); }
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
  function isSatelliteRasterError(event, map) {
    if (state.runtime.provider !== 'satellite' || renderedProvider !== 'satellite' || photoMap !== map || String(event?.sourceId || '') !== 'base') return false;
    const source = map?.getStyle?.()?.sources?.base;
    return source?.type === 'raster' && Array.isArray(source.tiles) && source.tiles.some(tile => tile === SATELLITE_TILE_TEMPLATE);
  }
  function embeddedBytes(encoded, label) {
    if (typeof encoded !== 'string' || encoded.length < 8) throw new Error(`Missing embedded asset ${label}`);
    const binary = atob(encoded.replace(/\s+/g, ''));
    const bytes = new Uint8Array(binary.length);
    for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
    if (!bytes.length) throw new Error(`Empty embedded asset ${label}`);
    return bytes;
  }
  async function setupVector() {
    markStartup('local_vector_setup_start');
    if (!window.TRIP_VECTOR) throw new Error('Local vector renderer missing');
    const { Protocol, PMTiles, FileSource } = window.TRIP_VECTOR;
    const protocol = new Protocol();
    let archive;
    if (window.EMBEDDED_VECTOR) {
      if (typeof window.EMBEDDED_VECTOR !== 'string' || window.EMBEDDED_VECTOR.length < 100000) throw new Error('Embedded PMTiles payload is missing or truncated');
      const bytes = embeddedBytes(window.EMBEDDED_VECTOR, 'sf_trip.pmtiles');
      if (bytes.byteLength < 127) throw new Error('Embedded PMTiles payload is too small');
      vectorUrl = 'sf_trip.pmtiles'; archive = new PMTiles(new FileSource(new File([bytes], 'sf_trip.pmtiles', { type: 'application/octet-stream' })));
    } else archive = new PMTiles(vectorUrl);
    const header = await archive.getHeader();
    markStartup('local_pmtiles_header_ready', { tile_type: header?.tileType, max_zoom: header?.maxZoom });
    if (!header || ![1, 6].includes(header.tileType) || header.maxZoom < 1 || header.minLon >= header.maxLon || header.minLat >= header.maxLat) throw new Error('Smart map PMTiles header is invalid');
    protocol.add(archive); maplibregl.addProtocol('pmtiles', protocol.tile);
    maplibregl.addProtocol('tripasset', async params => {
      const path = decodeURIComponent(params.url.replace('tripasset://', ''));
      if (!/^assets\/vector\/(?:fonts|sprites)\/[^?#]+$/.test(path) || path.includes('..')) throw new Error('Unsafe local map asset path');
      if (window.EMBEDDED_MAP_ASSETS) {
        const bytes = embeddedBytes(window.EMBEDDED_MAP_ASSETS[path], path);
        return { data: path.endsWith('.json') ? JSON.parse(new TextDecoder().decode(bytes)) : bytes.buffer };
      }
      const response = await fetch(path);
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
  async function returnToSmart(provider, reason, detail = {}) {
    if (provider === 'satellite' && satelliteFallbackFlight) return satelliteFallbackFlight;
    const fallback = (async () => {
      state.runtime.providerStats[provider].fallbacks++; if (reason === 'tile_error') state.runtime.providerStats[provider].tileErrors++;
      state.runtime.providerHealth[provider] = 'failed'; state.runtime.provider = 'vector';
      if (reason === 'tile_error') recordRuntimeEvent('tile_error', provider, detail);
      recordRuntimeEvent('fallback_to_smart', provider, { reason, ...detail });
      if (provider === 'satellite') showSatelliteFallbackFeedback();
      renderProviderState(); persist(); await drawMap(true); return false;
    })();
    if (provider !== 'satellite') return fallback;
    satelliteFallbackFlight = fallback.finally(() => { satelliteFallbackFlight = null; });
    return satelliteFallbackFlight;
  }
  async function chooseProvider(provider) {
    if (!['vector', 'satellite'].includes(provider)) return false;
    if (provider === 'vector') { rememberSmartCamera(); state.runtime.provider = 'vector'; clearMapFeedback(); renderProviderState(); persist(); return drawMap(true); }
    rememberSmartCamera();
    const ok = await testProvider(provider) && await testViewportProvider(provider);
    if (!ok) { await returnToSmart(provider, 'probe_failure'); return false; }
    clearMapFeedback(); state.runtime.provider = provider; state.runtime.providerSwitches++; recordRuntimeEvent('provider_switch', provider, { from: 'vector' }); renderProviderState(); persist(); return drawMap(true);
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
        const fromOccurrence = markerByKey[leg.from]?.occurrences.find(item => item.route === route && occurrenceDateKey(item) === leg.date);
        const toOccurrence = markerByKey[leg.to]?.occurrences.find(item => item.route === route && occurrenceDateKey(item) === leg.date);
        features.push({ type: 'Feature', geometry: { type: 'LineString', coordinates }, properties: { leg_id: leg.leg_id, label: leg.label, mode: leg.mode, note: leg.note, date: leg.date, route, color: safeColor(routeMeta[route].color), offset: (index - (active.length - 1) / 2) * (transfer ? 3.2 : 3), kind, branch, emphasis: route === state.task.primaryRoute ? 1 : .22, status: geometry?.status || 'conceptual_fallback', distance_km: geometry?.distance_km || 0, time: [fromOccurrence?.time, toOccurrence?.time].filter(Boolean).map(tr).join(' → ') } });
      });
    }
    return features;
  }
  function cameraTaskContext() {
    return { routes: [...state.task.routes].sort(), primary_route: state.task.primaryRoute, date: state.task.date, region: state.task.region };
  }
  function sameCameraTask(a, b) {
    return !!a && !!b && JSON.stringify(a) === JSON.stringify(b);
  }
  function cameraView(map = photoMap) {
    if (!map) return null;
    const center = map.getCenter?.();
    if (!center || !Number.isFinite(center.lng) || !Number.isFinite(center.lat)) return null;
    return { center: [center.lng, center.lat], zoom: map.getZoom(), bearing: map.getBearing(), pitch: map.getPitch() };
  }
  function mapSpatialSnapshot(map = photoMap) {
    if (!map) return { useful: false, reason: 'map-missing' };
    const canvas = map.getCanvas?.(), width = canvas?.clientWidth || canvas?.width || 0, height = canvas?.clientHeight || canvas?.height || 0;
    if (!width || !height) return { useful: false, reason: 'viewport-missing', width, height };
    const inside = point => point && point.x >= 0 && point.x <= width && point.y >= 0 && point.y <= height;
    const visibleMarkers = DATA.markers.filter(item => markerVisible(item, { map: true }));
    const markerPoints = visibleMarkers.map(item => { try { return map.project([item.lon, item.lat]); } catch { return null; } }).filter(Boolean);
    const routeFeatures = visibleRouteFeatures().filter(feature => feature.properties.kind !== 'transfer');
    const routePoints = routeFeatures.flatMap(feature => feature.geometry.coordinates).map(coordinate => { try { return map.project(coordinate); } catch { return null; } }).filter(Boolean);
    const markerPointsInViewport = markerPoints.filter(inside), routePointsInViewport = routePoints.filter(inside);
    const routeFeaturesInViewport = routeFeatures.filter(feature => feature.geometry.coordinates.some(coordinate => { try { return inside(map.project(coordinate)); } catch { return false; } }));
    const contentPoints = [...markerPointsInViewport, ...routePointsInViewport];
    const minX = contentPoints.length ? Math.min(...contentPoints.map(point => point.x)) : 0, maxX = contentPoints.length ? Math.max(...contentPoints.map(point => point.x)) : 0;
    const minY = contentPoints.length ? Math.min(...contentPoints.map(point => point.y)) : 0, maxY = contentPoints.length ? Math.max(...contentPoints.map(point => point.y)) : 0;
    const occupancy = width * height ? Math.max(0, (maxX - minX) * (maxY - minY)) / (width * height) : 0;
    return { useful: markerPointsInViewport.length > 0 && (routeFeaturesInViewport.length > 0 || markerPointsInViewport.length > 0), width, height, visible_markers: visibleMarkers.length, markers_in_viewport: markerPointsInViewport.length, route_features: routeFeatures.length, route_features_in_viewport: routeFeaturesInViewport.length, route_points_in_viewport: routePointsInViewport.length, content_occupancy_ratio: Number(occupancy.toFixed(4)) };
  }
  function rememberSmartCamera(map = photoMap) {
    if (!map || state.runtime.provider !== 'vector' || renderedProvider !== 'vector' || !state.runtime.mapVisualReady) return null;
    const view = cameraView(map), spatial = mapSpatialSnapshot(map);
    if (!view || !spatial.useful) return null;
    smartCamera = { ...view, task: cameraTaskContext(), spatial, owner: 'smart' };
    return smartCamera;
  }
  function validSmartCamera() {
    return smartCamera && sameCameraTask(smartCamera.task, cameraTaskContext()) && smartCamera.spatial?.useful ? smartCamera : null;
  }
  function viewForDraw(preserve, previous) {
    if (!preserve || !previous) return null;
    if (renderedProvider === state.runtime.provider) return cameraView(previous);
    return validSmartCamera() ? { center: validSmartCamera().center, zoom: validSmartCamera().zoom, bearing: validSmartCamera().bearing, pitch: validSmartCamera().pitch } : null;
  }
  function installRouteLayers(map) {
    markStartup('route_layer_install_start');
    const add = () => {
      if (map.getSource('trip-routes')) return;
      map.addSource('trip-routes', { type: 'geojson', data: { type: 'FeatureCollection', features: visibleRouteFeatures() } });
      const patterns = { transfer: [3, 2], conditional: [5, 2], option: [4, 2], bonus: [1, 2.4], recovery: [8, 3], choice: [2, 2] }, routePatterns = { solid: null, dash: [5, 2], dot: [1.2, 2.2], dashdot: [5, 1.4, 1.2, 1.4], longdash: [10, 3] };
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
    const action = ROUTES.length > 1 ? `<button class="peek-action" type="button" data-route-use>${m('chooseRoute')} ${esc(properties.route)} ↗</button>` : '';
    card.innerHTML = `<div class="peek-body"><div class="eyebrow">${esc(properties.route)} · ${esc(dateLabel(properties.date))}</div><h3 id="peekTitle" class="peek-title">${esc(tr(properties.label || ''))}</h3><p id="peekDescription" class="peek-why"><strong>${esc(tierLabel(properties.branch === 'main' ? 'main' : properties.branch))}</strong> · ${esc(modeLabel(properties.mode))}${properties.time ? ` · ${esc(properties.time)}` : ''}<br>${esc(tr(properties.note || ''))}</p><p class="peek-sub">${properties.status === 'routed_osm' ? m('recheck') : m('mapLegend')}</p>${action}</div>`;
    card.classList.add('show'); card.setAttribute('aria-hidden', 'false'); positionPeek(event, card); card.querySelector('[data-route-use]')?.addEventListener('click', () => choosePrimaryRoute(properties.route));
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
    const persistent = obstacles.filter(obstacle => !/map-options-panel/.test(obstacle.selector)).map(obstacle => ({ ...obstacle, shellWidth: shellRect.width }));
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
    return marker.occurrences.find(item => routes.has(item.route) && dateMatchesOccurrence(item)) || marker.occurrences.find(item => routes.has(item.route)) || null;
  }
  function groupOccurrences(marker) {
    const groups = {};
    marker.occurrences.filter(item => activeRoutes().has(item.route) && (state.task.date === 'all' || dateMatchesOccurrence(item))).forEach(item => {
      const signature = [occurrenceDateKey(item), item.time, item.title, item.reason, item.advantage, item.status].join('|');
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
    map.getContainer()?.querySelectorAll('.maplibregl-marker.photo-marker, .maplibregl-marker .photo-marker').forEach(element => {
      (element.classList.contains('maplibregl-marker') ? element : element.parentElement)?.remove();
    });
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
        previous.getSource('trip-routes')?.setData({ type: 'FeatureCollection', features: visibleRouteFeatures() }); installPhotoMarkers(previous); installLegLabels(previous); if (!preserve || mapGeometrySnapshot().markers.some(marker => marker.intersects_obstacle.length)) fitVisibleMap(previous); rememberSmartCamera(previous); return true;
      }
      const view = viewForDraw(preserve, previous);
      if (previous) { previous.__tripCleanup?.(); previous.remove(); state.runtime.mapRemovals += 1; }
      const region = DATA.region_cfg[state.task.region];
      let map;
      try {
        state.runtime.mapStatus = 'loading'; state.runtime.mapVisualReady = false;
        map = new maplibregl.Map({ container: 'map', style: providerStyle(state.runtime.provider), center: [region.center.lon, region.center.lat], zoom: region.zoom, attributionControl: false, dragRotate: false, pitchWithRotate: false, maxZoom: 18 });
        photoMap = map; renderedProvider = state.runtime.provider; renderedTheme = state.presentation.theme; state.runtime.mapCreations += 1; state.runtime.mapStatus = 'loading'; renderProviderState(); markStartup('map_created');
        map.on('load', () => { markStartup('map_style_ready'); installRouteLayers(map); installPhotoMarkers(map, { deferClusters: true }); installLegLabels(map); if (view) map.jumpTo(view); else fitVisibleMap(map); updatePhotoClusters(); state.runtime.mapStatus = 'ready'; state.runtime.mapVisualReady = true; if (state.runtime.provider === 'vector') rememberSmartCamera(map); renderProviderState(); renderShellStatus(); markStartup('map_visual_ready', { markers: photoMarkers.length, layers: map.getStyle()?.layers?.length || 0 }); });
        map.on('moveend', () => { if (state.runtime.provider === 'vector' && renderedProvider === 'vector') rememberSmartCamera(map); });
        map.on('click', () => hidePeek({ returnFocus: false }));
        map.on('error', event => { if (isSatelliteRasterError(event, map)) { void returnToSmart('satellite', 'tile_error', { source_id: event.sourceId, message: String(event?.error?.message || event?.message || event?.error || 'raster tile request failed') }); return; } if (localMapError(event)) showMapFailure(event.error || event.message, 'map_runtime'); });
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
    card.innerHTML = `<img class="peek-media" src="${photoSrc(photoPath(key, 'hero', 'medium'))}" alt="${esc(placeName(key))}"><div class="peek-body"><h3 id="peekTitle" class="peek-title">${esc(placeName(key))}</h3>${state.presentation.lang === 'ko' ? `<p class="peek-sub">${esc(placeKo(key))}</p>` : ''}<div class="peek-meta"><span class="tier-chip">${esc(tierLabel(tier))}</span>${groups.map(group => `<span>${esc(group.routes.join('/'))} · ${esc(dateLabel(group.date_key || group.date))} · ${esc(tr(group.time || '—'))}</span>`).join('')}</div><p id="peekDescription" class="peek-why"><strong>${m('whyNow')}</strong> ${esc(tr(occurrence?.reason || marker.why))}</p>${occurrence?.advantage ? `<p class="peek-sub">${m('advantage')}: ${esc(tr(occurrence.advantage))}</p>` : ''}<button class="peek-action" type="button" data-peek-open>${m('openPlace')} ↗</button></div>`;
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
    state.task.selected = key; state.task.selectedOccurrence = occurrenceDateKey(preferredOccurrence(markerByKey[key])) || null; if (focus) focusPlace(key); updateMarkerEmphasis(); renderDay(); renderPlace(); if (open) openPlace(key, invoker); persist();
  }
  function openPlace(key = state.task.selected, invoker) {
    if (!markerByKey[key]) return;
    state.presentation.previousMode = state.presentation.mode || 'day'; state.presentation.previousContext = { date: state.task.date, selected: state.task.selected, scrollTop: document.querySelector('.workbench-scroll')?.scrollTop || 0, focusPlace: invoker?.dataset?.placeChoice || null }; state.task.selected = key; state.presentation.mode = 'place'; hidePeek({ returnFocus: false }); renderAll(); document.querySelector('.workbench-scroll')?.scrollTo({ top: 0, behavior: 'smooth' }); persist();
  }
  function closePlace() {
    const previous = state.presentation.previousMode || 'day'; const context = state.presentation.previousContext; state.presentation.mode = previous; state.presentation.previousMode = null; state.presentation.previousContext = null; if (context?.date) state.task.date = context.date; if (context && Object.prototype.hasOwnProperty.call(context, 'selected')) { state.task.selected = context.selected; state.task.selectedOccurrence = context.selected ? state.task.selectedOccurrence : null; } renderAll(); requestAnimationFrame(() => { const scroll = document.querySelector('.workbench-scroll'); if (scroll && Number.isFinite(context?.scrollTop)) scroll.scrollTop = context.scrollTop; if (context?.focusPlace) [...document.querySelectorAll('[data-place-choice]')].find(button => button.dataset.placeChoice === context.focusPlace)?.focus({ preventScroll: true }); }); persist();
  }

  /* ----- Decide mode ----- */
  function routeProfile(route) {
    const meta = routeMeta[route], scores = Object.entries(meta.score || {});
    const selector = ROUTES.length > 1 ? `<div class="route-card-actions"><button type="button" class="route-use" data-route="${esc(route)}" aria-pressed="${route === state.task.primaryRoute}">${route === state.task.primaryRoute ? m('currentRoute') : m('chooseRoute')}</button></div>` : '';
    return `<article class="route-card ${route === state.task.primaryRoute ? 'primary' : ''}" style="--route-color:${safeColor(meta.color)}"><div class="route-card-head"><div class="route-card-title"><strong>${esc(tr(meta.title))}</strong><small>${esc(tr(meta.subtitle || ''))}</small></div><span class="route-code-pill" aria-label="${m('routeCode')}">${esc(route)}</span></div><p class="route-architecture">${esc(tr(meta.operating_architecture || ''))}</p><div class="score-line" aria-label="${m('routeScore')}">${scores.slice(0, 4).map(([key, value]) => `<span>${esc(state.presentation.lang === 'en' ? messages.scoreLabels[key] || key : key)} ${esc(value)}/10</span>`).join('')}</div>${selector}</article>`;
  }
  function renderDecide() {
    const meta = routeMeta[recommendedRoute], narrative = routeNarrative(recommendedRoute), recommendation = document.getElementById('recommendation');
    const selector = ROUTES.length > 1 ? `<button class="primary-action" type="button" data-route="${esc(recommendedRoute)}" data-recommendation-use>${state.task.primaryRoute === recommendedRoute ? m('currentRoute') : m('chooseRoute')}</button>` : '';
    recommendation.innerHTML = `<div class="route-code">${m('recommended')} · ${esc(recommendedRoute)}</div><h3>${esc(tr(meta.title))}</h3><p class="promise">${esc(tr(meta.subtitle || ''))}</p><div class="recommendation-grid"><div class="decision-cell"><strong>${m('bestFor')}</strong><span>${esc(narrative.best_for)}</span></div><div class="decision-cell"><strong>${m('tradeoff')}</strong><span>${esc(narrative.tradeoff)}</span></div><div class="decision-cell"><strong>${m('switchRule')}</strong><span>${esc(narrative.decision_rule)}</span></div><div class="decision-cell"><strong>${m('regretGuard')}</strong><span>${esc(narrative.regret_guard)}</span></div></div><div class="recommendation-footer"><span class="route-code">${m('routeCode')}: ${esc(recommendedRoute)} · ${esc(tr(meta.lodging || ''))}</span>${selector}</div>`;
    document.getElementById('routeCards').innerHTML = ROUTES.map(routeProfile).join('');
    document.querySelectorAll('[data-route]').forEach(button => { button.onclick = () => choosePrimaryRoute(button.dataset.route); });
  }
  function choosePrimaryRoute(route) {
    if (!ROUTES.includes(route)) return;
    state.task.primaryRoute = route;
    state.task.routes = new Set([route]);
    renderAll(); persist(); drawMap(true);
  }

  /* ----- Day mode ----- */
  function routeMini(routes, key) {
    return ROUTES.length > 1 ? routes.filter(route => activeRoutes().has(route)).map(route => `<span class="semantic-tag" style="border-color:${safeColor(routeMeta[route].color)};color:${safeColor(routeMeta[route].color)}">${esc(route)}${key ? ` · ${esc(roleShort(roleFor(key, route)))}` : ''}</span>`).join('') : '';
  }
  function dayIntensity(items) { const tiers = items.map(item => item.schedule_tier || 'main'); if (tiers.filter(tier => tier === 'recovery').length >= 2) return m('calm'); if (tiers.includes('must') && items.length >= 8) return m('full'); return m('steady'); }
  function renderDatePicker() {
    const select = document.getElementById('dateSelect'); select.innerHTML = `<option value="all">${m('allDates')}</option>${DATA.dates.map(date => `<option value="${esc(date.key)}">${esc(dateLabel(date.key))}</option>`).join('')}`; select.value = state.task.date;
  }
  function feeLabel(semantic) {
    return m(({ fixed: 'feeFixed', starting: 'feeStarting', estimated: 'feeEstimated', variable: 'feeVariable', conditional: 'feeConditional', included: 'feeIncluded', free: 'feeFree' })[semantic] || 'feeVariable');
  }
  function prerequisiteLabel(level) {
    return m(({ required: 'prereqRequired', strongly_recommended: 'prereqStrong', optional: 'prereqOptional', recheck_only: 'prereqRecheck' })[level] || 'prereqOptional');
  }
  function confidenceLabel(confidence) {
    return m(({ high_source_review: 'confidenceHigh', medium_source_review: 'confidenceMedium' })[confidence] || 'confidenceMedium');
  }
  function freshnessFacts(item) {
    const records = window.TRIP_FRESHNESS?.records || [], ids = new Set(item.freshness_fact_ids || []);
    return records.filter(record => ids.has(record.fact_id));
  }
  function freshnessLabel(status) {
    return m(({ VERIFIED: 'freshnessVerified', STALE: 'freshnessStale', UNVERIFIED: 'freshnessUnverified', RECHECK_REQUIRED: 'freshnessRecheck', NOT_APPLICABLE: 'freshnessNA' })[status] || 'freshnessUnverified');
  }
  function renderCostCockpit() {
    const content = document.getElementById('costCockpitContent'), dialog = document.getElementById('costCockpit');
    if (!content || !dialog) return;
    document.getElementById('costCockpitHeading').textContent = m('costHeading');
    document.getElementById('costCockpitIntro').textContent = m('costIntro');
    document.getElementById('costCockpitClose').textContent = m('costClose');
    const model = DATA.cost_cockpit || {}, scenarios = model.scenarios || [], selected = scenarios.find(item => item.id === state.user.costScenario), allRows = DATA.readiness_items || [];
    const rows = allRows.filter(item => state.task.date === 'all' || (item.applies_dates || []).includes(state.task.date));
    const excluded = state.presentation.lang === 'ko' ? (model.analysis_scenario?.excluded_ko || []) : (model.analysis_scenario?.excluded || []);
    const fmtLine = line => { const href = (line.source || []).map(safeOfficialSourceUrl).find(Boolean); return `<li class="cost-line"><span>${esc(tx(line, 'label'))}<small class="fee-chip">${esc(feeLabel(line.fee_semantic))}</small>${href ? `<a href="${esc(href)}" target="_blank" rel="noopener noreferrer" referrerpolicy="no-referrer">${esc(m('source'))} ↗</a>` : ''}</span><strong>${formatMoney(line.amount_cents)}</strong></li>`; };
    const otherLines = (items, detailField = null) => items.map(item => {
      const href = (item.source || []).map(safeOfficialSourceUrl).find(Boolean);
      return `<li class="cockpit-detail"><strong>${esc(tx(item, 'label'))}</strong><span class="fee-chip">${esc(feeLabel(item.fee_semantic))}</span>${detailField ? `<p>${esc(tx(item, detailField))}</p>` : ''}${href ? `<a href="${esc(href)}" target="_blank" rel="noopener noreferrer" referrerpolicy="no-referrer">${m('source')} ↗</a>` : ''}</li>`;
    }).join('');
    content.innerHTML = `<section class="cost-scenario"><label for="costScenarioSelect">${esc(m('chooseScenario'))}</label><select id="costScenarioSelect" class="day-picker"><option value="">${esc(m('chooseScenario'))}</option>${scenarios.map(item => `<option value="${esc(item.id)}" ${item.id === state.user.costScenario ? 'selected' : ''}>${esc(tx(item, 'label'))}</option>`).join('')}</select><p class="analysis-note">${esc(m('analysisOnly'))} · ${esc(tx(model.analysis_scenario || {}, 'label'))}</p>${selected ? `<h3>${esc(formatMoney(selected.lower_bound_cents))} <small>${esc(m('lowerBound'))}</small></h3><ul class="cost-lines">${selected.lines.map(fmtLine).join('')}</ul>` : `<p class="scenario-empty">${esc(m('chooseScenario'))}</p>`}</section><section class="cockpit-section"><h3>${esc(m('variableCosts'))}</h3><ul>${otherLines(model.variable_checkout_required || [])}</ul></section><section class="cockpit-section"><h3>${esc(m('optionalCosts'))}</h3><ul>${otherLines(model.optional_convenience || [], 'details')}</ul></section><section class="cockpit-section"><h3>${esc(m('excludedCosts'))}</h3><p>${esc(excluded.join(', '))}</p><p>${esc(tx(model, 'double_count_rule'))}</p></section><section class="cockpit-section readiness-section"><h3>${esc(m('readiness'))}</h3><p class="local-only">${esc(m('localOnly'))}</p>${rows.length ? rows.map(item => { const hrefs = (item.source || []).map(safeOfficialSourceUrl).filter(Boolean), facts = freshnessFacts(item), status = facts.length ? facts.map(fact => fact.status).sort((a, b) => ({ STALE: 0, UNVERIFIED: 1, RECHECK_REQUIRED: 2, VERIFIED: 3, NOT_APPLICABLE: 4 }[a] - ({ STALE: 0, UNVERIFIED: 1, RECHECK_REQUIRED: 2, VERIFIED: 3, NOT_APPLICABLE: 4 }[b])))[0] : 'UNVERIFIED', windows = facts.map(fact => fact.recheck?.window).filter(Boolean), value = state.user.readiness[item.id] || ''; return `<article class="readiness-card"><header><div><h4>${esc(tx(item, 'label'))}</h4><span class="fee-chip">${esc(feeLabel(item.fee_semantic))}</span> <span class="recheck-chip" data-freshness-status="${esc(status)}">${esc(freshnessLabel(status))}</span></div><label class="readiness-status" for="ready-${esc(item.id)}"><span>${esc(m('statusFor'))}: ${esc(tx(item, 'label'))}</span><select id="ready-${esc(item.id)}" data-readiness-status="${esc(item.id)}"><option value="">${esc(m('statusUnmarked'))}</option><option value="prepared" ${value === 'prepared' ? 'selected' : ''}>${esc(m('statusPrepared'))}</option><option value="user_marked_booked" ${value === 'user_marked_booked' ? 'selected' : ''}>${esc(m('statusBooked'))}</option><option value="user_marked_paid" ${value === 'user_marked_paid' ? 'selected' : ''}>${esc(m('statusPaid'))}</option></select></label></header><p><b>${esc(m('prerequisite'))}:</b> ${esc(prerequisiteLabel(item.prerequisite_severity))} · <b>${esc(m('confidence'))}:</b> ${esc(confidenceLabel(item.confidence))} · <b>${esc(m('researched'))}:</b> ${esc(item.researched_on)} · <b>${esc(m('recheckWhen'))}:</b> ${esc([tx(item, 'recheck_timing'), ...windows].filter(Boolean).join(' · '))}</p><p><b>${esc(m('parkingGuidance'))}:</b> ${esc(tx(item, 'parking_guidance'))}</p><p><b>${esc(m('babyGuidance'))}:</b> ${esc(tx(item, 'baby_mobility'))}</p>${hrefs.map(href => `<a href="${esc(href)}" target="_blank" rel="noopener noreferrer" referrerpolicy="no-referrer">${esc(m('source'))} ↗</a>`).join(' ')}</article>`; }).join('') : `<p class="empty-state">${esc(m('noActiveReadiness'))}</p>`}</section>`;
    const select = content.querySelector('#costScenarioSelect');
    select.onchange = () => { state.user.costScenario = scenarios.some(item => item.id === select.value) ? select.value : null; persist(); renderCostCockpit(); };
    content.querySelectorAll('[data-readiness-status]').forEach(input => { input.onchange = () => { if (input.value) state.user.readiness[input.dataset.readinessStatus] = input.value; else delete state.user.readiness[input.dataset.readinessStatus]; persist(); }; });
  }
  function renderDay() {
    renderDatePicker(); const items = DATA.timeline.filter(timelineVisible), header = document.getElementById('dayHeader'), plan = document.getElementById('dayPlan');
    const cockpitButton = `<button type="button" id="openCostCockpit" class="secondary-action cost-open" aria-haspopup="dialog" aria-controls="costCockpit" aria-expanded="${document.getElementById('costCockpit')?.open ? 'true' : 'false'}">${esc(m('costReadiness'))}</button>`;
    if (state.task.date === 'all') {
      header.innerHTML = `<h3>${m('chooseDay')}</h3><p>${DATA.dates.length} ${m('day').toLowerCase()} · ${esc(state.task.primaryRoute)} · ${esc(m('recheck'))}</p>${cockpitButton}`;
      plan.innerHTML = DATA.dates.map(date => { const dayRows = DATA.timeline.filter(item => item.date_key === date.key && routeIntersects(item.routes)); const mapped = dayRows.find(item => item.spatial_keys?.length); const op = DATA.operating_days?.[date.key]; return `<button type="button" class="day-item" data-day-choice="${esc(date.key)}" style="--tier-color:var(--accent)"><span class="day-time">${esc(dateLabel(date.key))}</span><span class="day-item-main"><span class="day-item-title">${esc(mapped ? placeName(mapped.spatial_keys[0]) : tx(dayRows[0], 'title'))}</span><span class="day-item-reason">${esc(tx(op, 'leave'))} · ${esc(tx(op, 'nap'))}</span><span class="day-item-tags"><span class="semantic-tag">${dayRows.length} ${esc(m('stop'))}</span><span class="semantic-tag">${esc(dayIntensity(dayRows))}</span></span></span></button>`; }).join('');
      plan.querySelectorAll('[data-day-choice]').forEach(button => { button.onclick = () => { state.task.date = button.dataset.dayChoice; renderAll(); persist(); drawMap(false); }; });
      document.getElementById('openCostCockpit').onclick = event => { const dialog = document.getElementById('costCockpit'); renderCostCockpit(); dialog.showModal(); event.currentTarget.setAttribute('aria-expanded', 'true'); document.getElementById('costCockpitClose').focus(); };
      return;
    }
    const dayMeta = DATA.dates.find(date => date.key === state.task.date), op = DATA.operating_days?.[state.task.date], regions = [...new Set(items.flatMap(item => item.regions || []))].map(region => DATA.region_cfg[region]?.[state.presentation.lang === 'ko' ? 'label_ko' : 'label'] || m(region)).join(' · '), recovery = items.filter(item => ['recovery', 'bonus'].includes(item.schedule_tier)).length, decisions = items.filter(item => ['swap', 'conditional', 'choice'].includes(item.schedule_tier)).length;
    header.innerHTML = `<h3>${esc(dateLabel(dayMeta?.key || state.task.date))}</h3><p>${esc(regions || m('overall'))} · ${esc(state.task.primaryRoute)}</p><div class="day-facts"><p><b>${esc(m('leaveBy'))}:</b> ${esc(tx(op, 'leave'))}</p><p><b>${esc(m('napWindow'))}:</b> ${esc(tx(op, 'nap'))}</p><p><b>${esc(m('recoveryPlan'))}:</b> ${esc(tx(op, 'recovery'))}</p><p><b>${esc(m('prepareBefore'))}:</b> ${esc(tx(op, 'prepare'))}</p><p><b>${esc(m('couldInvalidate'))}:</b> ${esc(tx(op, 'invalidator'))}</p></div><div class="day-metrics"><span class="day-metric">${m('intensity')}: ${esc(dayIntensity(items))}</span><span class="day-metric">${m('decisions')}: ${decisions}</span><span class="day-metric">${m('calm')}: ${recovery}</span></div>${cockpitButton}`;
    if (!items.length) { plan.innerHTML = `<div class="empty-state">${m('noSlots')}</div>`; return; }
    plan.innerHTML = `<p class="day-story">${esc(tx(items[0], 'reason'))}</p>${items.map(item => { const mapped = item.spatial_keys?.length, tier = item.schedule_tier || 'main', color = tier === 'must' ? '#a94335' : tier === 'swap' ? '#a76a42' : tier === 'recovery' ? '#72857b' : 'var(--accent)', identity = item.itinerary_identity, cue = item.travel_navigation_cue ? `<p class="travel-cue">${esc(m('liveNavCue'))}</p>` : '', cueInline = item.travel_navigation_cue ? `<span class="travel-cue">${esc(m('liveNavCue'))}</span>` : '', blocker = identity?.photo_blocker ? `<p class="photo-blocker"><b>${esc(m('photoBlocked'))}:</b> ${esc(tx(identity, 'photo_blocker'))}</p>` : '', title = tx(item, 'title'), reason = tx(item, 'reason'); return mapped ? `<button type="button" class="day-item ${item.spatial_keys.includes(state.task.selected) ? 'selected' : ''}" data-day-place="${esc(item.spatial_keys[0])}" style="--tier-color:${color}"><span class="day-time">${esc(tr(item.time || '—'))}</span><span class="day-item-main"><span class="day-item-title">${esc(title)}</span><span class="day-item-reason"><strong>${esc(m('whyNow'))}:</strong> ${esc(reason)}</span>${cueInline}<span class="day-item-tags"><span class="tier-chip">${esc(tierLabel(tier))}</span>${ROUTES.length > 1 ? (item.route_specific ? `<span class="semantic-tag">${m('specific')}</span>` : `<span class="semantic-tag">${m('shared')}</span>`) : ''}${routeMini(item.routes, item.spatial_keys[0])}</span></span></button>` : `<article class="plan-card" style="--tier-color:${color}"><strong>${esc(tr(item.time || '—'))} · ${esc(title)}</strong><p>${esc(reason)} · ${esc(m('unpinnedActivity'))}</p>${blocker}${cue}<div class="day-item-tags"><span class="tier-chip">${esc(tierLabel(tier))}</span>${routeMini(item.routes)}</div></article>`; }).join('')}`;
    plan.querySelectorAll('[data-day-place]').forEach(button => { button.onclick = () => { selectPlace(button.dataset.dayPlace, { focus: true, open: false, invoker: button }); showPeek(button.dataset.dayPlace, { invoker: button }); }; });
    document.getElementById('openCostCockpit').onclick = event => { const dialog = document.getElementById('costCockpit'); renderCostCockpit(); dialog.showModal(); event.currentTarget.setAttribute('aria-expanded', 'true'); document.getElementById('costCockpitClose').focus(); };
  }

  /* ----- Place mode: browser, Peek -> Inspector, and return ----- */
  function renderPlaceBrowser() {
    const regionMatches = marker => state.task.region === 'overall' || DATA.place_region[marker.place_key] === state.task.region;
    const visible = DATA.markers.filter(marker => regionMatches(marker) && (state.task.date === 'all' || markerVisible(marker)));
    const html = `<div class="place-browser"><p class="place-browser-intro">${m('placeListComplete')} ${visible.length}/${DATA.markers.length} ${m('stop')}</p><div class="place-list">${visible.map(marker => { const occurrence = preferredOccurrence(marker); return `<button type="button" class="place-list-item" data-place-choice="${esc(marker.place_key)}"><img src="${photoSrc(photoPath(marker.place_key, 'hero', 'thumb'))}" alt=""><span class="place-list-copy"><strong>${esc(placeName(marker.place_key))}</strong>${state.presentation.lang === 'ko' ? `<small>${esc(placeKo(marker.place_key))}</small>` : ''}<small>${esc(dateLabel(occurrence?.date_key || occurrence?.date || ''))} · ${esc(tr(occurrence?.time || '—'))}</small><em>${esc(tr(occurrence?.reason || marker.why))}</em>${placeRoleMarkup(marker.place_key)}</span></button>`; }).join('')}</div></div>`;
    const panel = document.getElementById('placeInspector'); panel.innerHTML = html;
    panel.querySelectorAll('[data-place-choice]').forEach(button => { button.onclick = () => openPlace(button.dataset.placeChoice, button); });
  }
  function renderPlaceInspector(marker) {
    const panel = document.getElementById('placeInspector'), occurrences = groupOccurrences(marker), now = preferredOccurrence(marker), tier = tierFor(marker), photos = [[m('hero'), 'hero'], [m('experiencePhoto'), 'experience'], [m('scale'), 'scale_context']], mapsHref = safeExternalUrl(marker.maps_url);
    panel.innerHTML = `<button type="button" class="secondary-action place-back" data-place-back>← ${m('closePlace')}</button><div class="place-title-row"><div><h3>${esc(placeName(marker.place_key))}</h3>${state.presentation.lang === 'ko' ? `<p>${esc(placeKo(marker.place_key))}</p>` : ''}</div><span class="place-score">${esc(marker.score)}/100</span></div><div class="place-meta"><span>${esc(tr(marker.cluster))}</span><span>${esc(tierLabel(tier))}</span></div><div class="place-role-line">${placeRoleMarkup(marker.place_key)}</div><div class="place-glance"><strong>${esc(tr(now?.status || tierLabel(tier)))} · ${esc(dateLabel(now?.date_key || now?.date || ''))} · ${esc(tr(now?.time || '—'))}</strong><div><b>${m('whyNow')}</b> ${esc(tr(now?.reason || marker.why))}</div>${now?.advantage ? `<em>${m('advantage')}: ${esc(tr(now.advantage))}</em>` : ''}</div><div class="photo-grid">${photos.map(([label, role]) => `<figure class="photo-slot"><img src="${photoSrc(photoPath(marker.place_key, role, 'medium'))}" alt="${esc(placeName(marker.place_key))} — ${esc(label)}" loading="lazy"><figcaption>${esc(label)}</figcaption></figure>`).join('')}</div><div class="place-fact"><strong>${m('placeWhy')}</strong>${esc(tr(marker.why))}</div><div class="place-fact"><strong>${m('experience')}</strong>${esc(tr(marker.summary))}</div><div class="place-fact"><strong>${m('exactTiming')}</strong>${occurrences.length ? occurrences.map(item => `<div class="occurrence"><b>${esc(tr(item.title))}</b><small>${esc(dateLabel(item.date_key || item.date))} · ${esc(tr(item.time || '—'))} · ${esc(tr(item.status || ''))}</small><small>${m('whyNow')}: ${esc(tr(item.reason || ''))}</small></div>`).join('') : `<span class="muted">${m('noSlots')}</span>`}</div>${marker.decision_rules?.length ? `<div class="place-fact"><strong>${m('switchRule')}</strong>${marker.decision_rules.map(rule => `<div class="decision-rule"><b>${esc(decisionLabel(rule.key))}</b>${esc(tr(rule.text))}</div>`).join('')}</div>` : ''}<div class="place-fact"><strong>${m('freshness')}</strong><span>${esc(m('recheck'))}</span></div><div class="place-fact directions"><span>${marker.lat.toFixed(5)}, ${marker.lon.toFixed(5)}</span>${mapsHref ? `<a href="${esc(mapsHref)}" target="_blank" rel="noopener noreferrer" referrerpolicy="no-referrer">${m('directions')} ↗</a>` : `<span>${m('unavailableDirections')}</span>`}</div>`;
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
  function renderShellStatus() {
    const status = document.getElementById('workbenchStatus'); if (!status) return; const mode = state.presentation.mode === 'decide' ? m('decide') : state.presentation.mode === 'day' ? m('day') : m('place'); const context = state.presentation.mode === 'day' && state.task.date !== 'all' ? dateLabel(state.task.date) : state.task.primaryRoute; status.textContent = `${mode} · ${context}`;
  }
  function applyTranslations() {
    document.documentElement.lang = state.presentation.lang; document.documentElement.dataset.theme = state.presentation.theme;
    document.querySelectorAll('[data-i18n]').forEach(element => { const key = element.dataset.i18n; element.textContent = m(key); });
    document.querySelector('.brand').textContent = m('brand'); document.querySelector('.sub').textContent = m('subtitle');
    const fieldSet = document.querySelector('.route-section .eyebrow'); if (fieldSet) fieldSet.textContent = m('fieldSet');
    const routeHeading = document.getElementById('routeSectionHeading'); if (routeHeading) routeHeading.textContent = m('routeStrategies');
    document.getElementById('langToggle').textContent = state.presentation.lang === 'ko' ? 'EN' : '한국어'; document.getElementById('themeToggle').textContent = state.presentation.theme === 'dark' ? `☀ ${m('light')}` : `☾ ${m('dark')}`;
    document.getElementById('workbenchToggle').textContent = state.presentation.sheet === 'compact' ? m('expand') : m('collapse');
    const smartRetry = document.getElementById('smartRetry'); if (smartRetry) smartRetry.textContent = m(smartRetry.dataset.retryProvider === 'satellite' ? 'retrySatellite' : 'retrySmart');
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
  function renderAll() { applyTranslations(); renderMapControls(); renderModes(); renderShellStatus(); renderDecide(); if (state.presentation.mode === 'day') renderDay(); if (state.presentation.mode === 'place') renderPlace(); if (document.getElementById('costCockpit')?.open) renderCostCockpit(); }
  function bindShell() {
    document.querySelectorAll('[data-mode]').forEach(button => { button.onclick = () => setMode(button.dataset.mode); });
    document.querySelectorAll('[data-sheet]').forEach(button => { if (button.classList.contains('icon-button')) button.onclick = () => setSheet(button.dataset.sheet); });
    document.getElementById('workbenchToggle').onclick = () => setSheet(state.presentation.sheet === 'compact' ? 'expanded' : 'compact');
    document.getElementById('costCockpitClose').onclick = () => document.getElementById('costCockpit').close();
    document.getElementById('costCockpit').addEventListener('close', () => requestAnimationFrame(() => { const button = document.getElementById('openCostCockpit'); if (button) { button.setAttribute('aria-expanded', 'false'); button.focus({ preventScroll: true }); } }));
    document.getElementById('mapOptionsToggle').onclick = () => setMapOptionsOpen(!state.presentation.mapOptionsOpen);
    document.getElementById('mapOptionsClose').onclick = () => setMapOptionsOpen(false);
    document.getElementById('langToggle').onclick = () => { state.presentation.lang = state.presentation.lang === 'ko' ? 'en' : 'ko'; hidePeek({ returnFocus: false }); renderAll(); persist(); drawMap(true); };
    document.getElementById('themeToggle').onclick = () => { state.presentation.theme = state.presentation.theme === 'dark' ? 'light' : 'dark'; renderAll(); persist(); drawMap(true); };
    document.getElementById('fitMap').onclick = () => fitVisibleMap();
    document.getElementById('mapErrorDismiss').onclick = () => { document.getElementById('mapError').hidden = true; };
    document.getElementById('smartRetry').onclick = async event => {
      const retry = event.currentTarget;
      if (retry.dataset.retryProvider === 'satellite') { retry.disabled = true; document.getElementById('mapError').hidden = true; await chooseProvider('satellite'); retry.disabled = false; return; }
      document.getElementById('mapError').hidden = true; state.runtime.provider = 'vector'; state.runtime.providerHealth.vector = 'loading'; state.runtime.localAssets.status = 'checking'; renderProviderState(); try { await setupVector(); await drawMap(true); } catch (error) { showMapFailure(error, 'retry'); }
    };
    document.getElementById('dateSelect').onchange = event => { state.task.date = event.target.value; if (state.task.selected && !markerVisible(markerByKey[state.task.selected])) state.task.selected = null; state.presentation.mode = 'day'; renderAll(); persist(); drawMap(false); };
    const handleEscape = event => { if (event.key !== 'Escape') return; if (document.getElementById('costCockpit')?.open) return; if (state.presentation.mapOptionsOpen) { setMapOptionsOpen(false); event.preventDefault(); return; } if (state.presentation.peek) { hidePeek(); event.preventDefault(); return; } if (state.presentation.mode === 'place') { closePlace(); event.preventDefault(); return; } if (state.presentation.sheet === 'full') { setSheet('expanded'); event.preventDefault(); } };
    document.onkeydown = handleEscape;
    document.body?.addEventListener('keydown', handleEscape);
    document.addEventListener('pointerdown', event => { if (state.presentation.mapOptionsOpen && !event.target.closest('#mapControlSurface')) setMapOptionsOpen(false); });
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
    return { provider: state.runtime.provider, provider_identity: state.runtime.providerIdentity, provider_health: { ...state.runtime.providerHealth }, app_ready: state.runtime.mapStatus === 'ready', map_visual_ready: state.runtime.mapVisualReady, planning_state: { routes: [...activeRoutes()], primary_route: state.task.primaryRoute, date: state.task.date, region: state.task.region, selected: state.task.selected, mode: state.presentation.mode, sheet: state.presentation.sheet, lang: state.presentation.lang, theme: state.presentation.theme }, provider_events: state.runtime.providerEvents.slice(), local_assets: { status: state.runtime.localAssets.status, failures: state.runtime.localAssets.failures.slice() }, startup: { marks: [...(window.__tripStartupMarks || [])] }, runtime: { ...state.runtime, events: state.runtime.events.slice() }, smart_camera: validSmartCamera(), map: { canvas_count: document.querySelectorAll('.maplibregl-canvas').length, photo_markers: document.querySelectorAll('.photo-marker').length, photo_marker_keys: [...document.querySelectorAll('.photo-marker')].map(element => element.dataset.placeKey), clusters: document.querySelectorAll('.photo-cluster').length, leg_markers: document.querySelectorAll('.route-leg-label').length, layers: photoMap?.getStyle?.()?.layers?.length || 0, camera: cameraView(), spatial: mapSpatialSnapshot() } };
  }
  function renderFixture(value) {
    const marker = DATA.markers[0], saved = marker ? JSON.parse(JSON.stringify(marker)) : null;
    if (!marker) return { html: '', href: null, unsafe_nodes: 0 };
    try { marker.why = value; marker.summary = value; marker.maps_url = value; marker.name = value; state.task.selected = marker.place_key; renderPlaceInspector(marker); const panel = document.getElementById('placeInspector'); return { html: panel.innerHTML, href: panel.querySelector('a')?.getAttribute('href') || null, unsafe_nodes: panel.querySelectorAll('script,[onerror],[onclick],[onload],[javascript]').length }; }
    finally { Object.assign(marker, saved); renderPlace(); }
  }
  function expose() {
    window.__tripApp = { state, DATA, drawMap, whenIdle: () => Promise.all([drawQueue, scheduleMapGeometryUpdate()]), whenGeometryIdle: () => scheduleMapGeometryUpdate(), map: () => photoMap, whenMapVisualReady: () => Promise.resolve(runtimeSnapshot().map), selectPlace, chooseProvider, testProvider, setMode, setSheet, setTab: tab => setMode(tab === 'timeline' ? 'day' : tab === 'details' ? 'place' : 'decide'), markerVisible, timelineVisible, legVisible, visibleRouteFeatures, renderTimeline: renderDay, renderDetail: key => { if (key) state.task.selected = key; renderPlace(); }, showPreview: showPeek, showRoutePeek: properties => showRoutePeek(properties), hidePreview: hidePeek, fitVisibleMap, mapGeometrySnapshot, mapSpatialSnapshot, runtimeSnapshot };
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
