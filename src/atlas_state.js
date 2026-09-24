/* Task, presentation, runtime, and persistence ownership for the atlas shell. */
(() => {
  const STORAGE_KEY = 'trip_visualizer_runtime_v2';
  const legacyKey = 'trip_visualizer_runtime_v1';
  const read = (key, fallback) => { try { return localStorage.getItem(key) || fallback; } catch { return fallback; } };
  const readJson = key => { try { return JSON.parse(localStorage.getItem(key) || 'null') || {}; } catch { return {}; } };

  function create(data) {
    const saved = readJson(STORAGE_KEY);
    const legacy = readJson(legacyKey);
    const restored = Object.keys(saved).length ? saved : legacy;
    const tripIdentity = String(data.trip_identity || 'unbound-trip');
    const sameTrip = restored.tripIdentity === tripIdentity;
    const checklistValues = ['prepared', 'user_marked_booked', 'user_marked_paid'];
    const savedChecklist = sameTrip && restored.readiness && typeof restored.readiness === 'object' ? restored.readiness : {};
    const readiness = Object.fromEntries(Object.entries(savedChecklist).filter(([, value]) => checklistValues.includes(value)));
    const scenarioIds = new Set((data.cost_cockpit?.scenarios || []).map(item => item.id));
    const routeKeys = Object.keys(data.routes || {});
    const dates = new Set(['all', ...(data.dates || []).map(item => item.key)]);
    const regions = new Set(Object.keys(data.region_cfg || {}));
    const savedRoutes = Array.isArray(restored.routes) ? restored.routes.filter(route => routeKeys.includes(route)) : [];
    const recommended = routeKeys.find(route => data.routes[route]?.recommended) || routeKeys[0];
    const state = {
      task: {
        primaryRoute: routeKeys.includes(restored.primaryRoute) ? restored.primaryRoute : (savedRoutes[0] || recommended),
        routes: new Set(savedRoutes.length ? savedRoutes : routeKeys),
        date: dates.has(restored.date) ? restored.date : 'all',
        region: regions.has(restored.region) ? restored.region : 'overall',
        selected: typeof restored.selected === 'string' ? restored.selected : null,
        selectedOccurrence: restored.selectedOccurrence || null,
      },
      presentation: {
        mode: ['decide', 'day', 'place'].includes(restored.mode) ? restored.mode : 'decide',
        sheet: ['compact', 'expanded', 'full'].includes(restored.sheet) ? restored.sheet : 'expanded',
        lang: ['ko', 'en'].includes(restored.lang) ? restored.lang : read('trip_lang', 'ko'),
        theme: ['light', 'dark'].includes(restored.theme) ? restored.theme : read('trip_theme', 'light'),
        peek: null,
        previousMode: null,
        previousContext: null,
        focusReturn: null,
        mapOptionsOpen: false,
      },
      runtime: {
        provider: 'vector', providerIdentity: data.providers?.vector?.identity || 'smart-local-vector',
        providerHealth: { vector: 'loading', satellite: 'untested' },
        providerEvents: [], localAssets: { status: 'checking', failures: [] },
        mapStatus: 'loading', mapVisualReady: false,
        sequence: 0, probeSequence: 0, mapCreations: 0, mapRemovals: 0,
        drawRequests: 0, providerSwitches: 0, events: [],
        providerStats: { vector: { healthProbes: 0, viewportProbes: 0, tileErrors: 0, fallbacks: 0 }, satellite: { healthProbes: 0, viewportProbes: 0, tileErrors: 0, fallbacks: 0 } },
      },
      user: {
        tripIdentity,
        readiness,
        costScenario: sameTrip && scenarioIds.has(restored.costScenario) ? restored.costScenario : null,
      },
    };

    /* Compatibility aliases are read-through only; ownership remains nested. */
    Object.defineProperties(state, {
      routes: { get: () => state.task.routes, set: value => { const next = value instanceof Set ? value : new Set(value || []); state.task.routes = next; if (next.size === 1) state.task.primaryRoute = [...next][0]; } },
      date: { get: () => state.task.date, set: value => { state.task.date = value; } },
      region: { get: () => state.task.region, set: value => { state.task.region = value; } },
      selected: { get: () => state.task.selected, set: value => { state.task.selected = value; } },
      provider: { get: () => state.runtime.provider, set: value => { state.runtime.provider = value; } },
      providerHealth: { get: () => state.runtime.providerHealth },
      lang: { get: () => state.presentation.lang, set: value => { state.presentation.lang = value; } },
      theme: { get: () => state.presentation.theme, set: value => { state.presentation.theme = value; } },
      tab: { get: () => state.presentation.mode === 'day' ? 'timeline' : state.presentation.mode === 'place' ? 'details' : 'decide' },
      panelHidden: { get: () => state.presentation.sheet === 'compact' },
    });
    return { state, storageKey: STORAGE_KEY, persist() {
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify({ version: 3, tripIdentity: state.user.tripIdentity, primaryRoute: state.task.primaryRoute, routes: [...state.task.routes].sort(), date: state.task.date, region: state.task.region, selected: state.task.selected, selectedOccurrence: state.task.selectedOccurrence, mode: state.presentation.mode, sheet: state.presentation.sheet, lang: state.presentation.lang, theme: state.presentation.theme, readiness: { ...state.user.readiness }, costScenario: state.user.costScenario }));
      } catch { /* local-first persistence is best effort */ }
    } };
  }
  window.TRIP_ATLAS_STATE = { create, storageKey: STORAGE_KEY };
})();
