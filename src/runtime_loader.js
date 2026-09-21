/* Load the task shell before map libraries; dynamic scripts do not block HTML parsing. */
(() => {
  const load = src => new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = src;
    script.onload = resolve;
    script.onerror = () => reject(new Error(`Runtime script failed: ${src}`));
    document.head.appendChild(script);
  });
  const ui = ['src/atlas_messages.js', 'src/atlas_state.js', 'src/app_phase7.js'];
  const map = ['vendor/maplibre-gl.js', 'vendor/trip-vector.js'];
  window.__tripRuntimeReady = load(ui[0]).then(() => load(ui[1])).then(() => load(ui[2])).then(() => Promise.all(map.map(load))).then(() => {
    window.__tripStartupMark?.('map_runtime_scripts_ready');
  });
  window.__tripRuntimeReady.then(() => load('vendor/plotly.min.js')).catch(() => {});
})();
