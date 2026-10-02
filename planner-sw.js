// Cache only this planner's shell, canonical data, and local photos.
// Do not cache Google responses, online world tiles, or the large PMTiles archive.
const CACHE = 'fieldtrip-shell-v1';
const SHELL = ['planner.html', 'src/planner.css', 'src/planner.mjs', 'src/planner-core.mjs', 'src/planner-google.mjs', 'src/planner-map.mjs', 'data/phase7_app_data.json', 'vendor/maplibre-gl.js', 'vendor/maplibre-gl.css', 'vendor/trip-vector.js'];
self.addEventListener('install', event => { event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(SHELL)).then(() => self.skipWaiting())); });
self.addEventListener('activate', event => { event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k.startsWith('fieldtrip-shell-') && k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim())); });
self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET') return;
  const url = new URL(event.request.url), base = new URL(self.registration.scope);
  if (url.origin !== base.origin || !url.pathname.startsWith(base.pathname) || url.search) return;
  const path = url.pathname.slice(base.pathname.length);
  if (!SHELL.includes(path) && !/^assets\/photos\/(thumb|medium)\/[a-z0-9_]+\.webp$/.test(path)) return;
  event.respondWith(fetch(event.request).then(response => { if (response.ok) { const copy = response.clone(); event.waitUntil(caches.open(CACHE).then(cache => cache.put(event.request, copy))); } return response; }).catch(async () => (await caches.match(event.request)) || Response.error()));
});
