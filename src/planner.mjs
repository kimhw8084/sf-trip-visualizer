import { STORAGE_KEY, MODES, COLORS, uid, clone, minutes, clock, timeLabel, durationLabel, localDate, coordinates, estimateLeg, legKey, travelEndpoints, scheduleDay, makeStop, makeTrip, seedTrip, validateStore, navigationUrl, reorder, optimizeStops } from './planner-core.mjs';
import { GoogleConnection } from './planner-google.mjs';
import { PlannerMap } from './planner-map.mjs';

const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const safeUrl = value => { try { const u = new URL(value); return u.protocol === 'https:' ? u.href : '#'; } catch { return '#'; } };
const photoUrl = value => /^assets\/photos\/(thumb|medium)\/[a-z0-9_]+\.webp$/.test(value || '') ? value : '';
const dateLabel = (value, options = {}) => new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC', ...options }).format(new Date(`${value}T12:00:00Z`));
const google = new GoogleConnection();
const map = new PlannerMap((stopId, dayId) => { selectedDayId = dayId; view = 'day'; render(); showDetails(stopId); }, message => { $('mapError').textContent = message; $('mapError').hidden = false; });
let store, data, selectedDayId, view = 'day', history = [], results = new Map(), routingVersion = 0, routingTimer, routingStatus = '', toastTimer, recoverStorage = false, dialogVersion = 0;
const activeTrip = () => store.trips.find(t => t.id === store.activeTripId) || store.trips[0];
const activeDay = () => activeTrip().days.find(d => d.id === selectedDayId) || activeTrip().days[0];
const hydratedDay = day => ({ ...day, stops: day.stops.map(s => google.hydrate(s)) });
const plan = day => scheduleDay(hydratedDay(day), results, { remaining: !!day.replanRemaining });
const stopById = id => activeTrip().days.flatMap(d => d.stops).find(s => s.id === id);
const option = (value, label, selected) => `<option value="${esc(value)}" ${selected === value ? 'selected' : ''}>${esc(label)}</option>`;
const modeOptions = selected => Object.entries(MODES).map(([key, name]) => option(key, name, selected)).join('');

function toast(message) { clearTimeout(toastTimer); $('toast').textContent = message; $('toast').hidden = false; toastTimer = setTimeout(() => { $('toast').hidden = true; }, 5000); }
function save() {
  try {
    if (recoverStorage) throw new Error('Existing backup needs recovery');
    store.selectedDayId = selectedDayId; localStorage.setItem(STORAGE_KEY, JSON.stringify(store));
    $('saveStatus').textContent = 'Saved on this device'; $('saveStatus').title = 'Use Export backup to transfer your plan to another device.';
    return true;
  } catch { $('saveStatus').textContent = 'Not saved · export a backup'; toast('Changes are in memory only. Open trip tools and export a backup.'); return false; }
}
function mutate(fn, message, route = true) {
  history.push(clone(store)); if (history.length > 30) history.shift();
  fn(); if (route) { results.clear(); routingVersion++; }
  save(); render(); if (route) queueRoutes(); if (message) toast(message);
}
function undo() { if (!history.length) return; store = history.pop(); selectedDayId = activeTrip().days.some(d => d.id === selectedDayId) ? selectedDayId : activeTrip().days[0].id; results.clear(); routingVersion++; save(); render(true); queueRoutes(); toast('Last change undone.'); }
function selectDay(id) { selectedDayId = id; results.clear(); routingVersion++; $('planScroll').scrollTop = 0; save(); render(true); queueRoutes(); }
function setView(next) { view = next; render(true); }
function mobile(next) { document.body.dataset.mobile = next === 'map' ? 'map' : 'plan'; document.querySelectorAll('[data-mobile]').forEach(b => b.classList.toggle('active', b.dataset.mobile === next)); if (next === 'go') setView('go'); if (next === 'plan' && view === 'go') setView('day'); map.resize(); }

function render(fit = false) {
  const trip = activeTrip(), day = activeDay(), p = plan(day), index = trip.days.indexOf(day), today = localDate(new Date(), trip.timezone);
  $('tripSelect').innerHTML = store.trips.map(t => option(t.id, t.name, trip.id)).join('');
  $('tripTitle').textContent = trip.name;
  $('tripSubtitle').textContent = `${dateLabel(trip.days[0].date)} – ${dateLabel(trip.days.at(-1).date, { year: 'numeric' })} · ${trip.days.length} days · ${trip.destination || 'Your next adventure'}`;
  $('undo').disabled = !history.length;
  document.querySelectorAll('[data-view]').forEach(b => { b.classList.toggle('active', b.dataset.view === view); b.setAttribute('aria-pressed', String(b.dataset.view === view)); });
  $('dayStrip').hidden = view === 'overview';
  $('dayStrip').innerHTML = trip.days.map(d => `<button class="day-chip ${d.id === day.id ? 'active' : ''} ${d.date === today ? 'today' : ''}" data-day="${esc(d.id)}" aria-label="${esc(dateLabel(d.date, { weekday: 'long' }))}${d.date === today ? ', today' : ''}" aria-pressed="${d.id === day.id}"><span>${esc(dateLabel(d.date, { weekday: 'short', month: undefined, day: undefined }))}</span><b>${Number(d.date.slice(-2))}</b></button>`).join('');
  for (const key of ['day', 'overview', 'go']) $(`${key}View`).hidden = view !== key;
  $('dayHeading').innerHTML = `<div class="day-title-row"><div><p class="eyebrow">DAY ${index + 1} <span> / </span> ${esc(dateLabel(day.date, { weekday: 'long' }).toUpperCase())}${today === day.date ? ' · TODAY' : ''}</p><h2>${esc(day.title)}</h2></div><button id="editDay" aria-label="Edit day settings">⚙</button></div>${day.note ? `<p class="day-subtitle">${esc(day.note)}</p>` : ''}`;
  $('dayMetrics').innerHTML = `<div class="metric"><strong>${p.rows.filter(r => r.stop.kind === 'place').length}</strong><small>places to be</small></div><div class="metric"><strong>${p.unknown ? '≥ ' : p.estimated ? '~ ' : ''}${durationLabel(p.travel)}</strong><small>travel ${p.unknown ? '· incomplete' : 'planned'}</small></div><div class="metric"><strong>${timeLabel(p.finish)}</strong><small>estimated finish</small></div>`;
  $('dayControls').innerHTML = `<button id="optimize">↝ Less backtracking</button><button id="delayDay">＋15m delay</button><select id="allModes" class="mode-control" aria-label="Set travel mode for this day"><option value="">Travel mode</option>${modeOptions('')}</select>`;
  $('routeNotice').classList.toggle('live', google.ready);
  $('routeNotice').textContent = routingStatus || (google.ready ? 'Google connected · routes refresh when you edit.' : 'Planning estimates · connect Google for road routes and travel times.');
  const extra = p.unknown ? [{ message: `${p.unknown} travel leg${p.unknown > 1 ? 's need' : ' needs'} a location or travel allowance. Finish time excludes unknown travel.` }] : [];
  const warnings = [...extra, ...p.warnings];
  $('dayWarnings').innerHTML = warnings.length ? `<details class="warning"><summary>${warnings.length} timing check${warnings.length > 1 ? 's' : ''} to review</summary>${warnings.map(w => `<p>${esc(w.message)}</p>`).join('')}</details>` : '';
  $('timeline').innerHTML = day.stops.length ? day.stops.map((stop, i) => stopCard(stop, i, p.rows.find(r => r.stop.id === stop.id))).join('') : '<div class="empty-state"><h3>A day full of possibilities.</h3><p>Add your starting point, a few places you love,<br>and some room to wander.</p></div>';
  $('dayEnd').innerHTML = `${p.rows.length ? `◉ Wrap up around <strong>${timeLabel(p.finish)}</strong> · ${durationLabel(p.buffers)} of travel buffer` : ''}<br><span class="muted">${esc(trip.timezone)} · changes save on this device</span>`;
  if (view === 'overview') renderOverview();
  if (view === 'go') renderGo();
  $('connectionStatus').textContent = google.ready ? 'Google connected · saved locally' : 'Local planning · estimates';
  $('mapContext').textContent = view === 'overview' ? `${trip.days.length} days · the whole journey` : `Day ${index + 1} · ${dateLabel(day.date)} · ${p.rows.filter(r => coordinates(r.stop)).length} mapped stops`;
  $('mapLegend').innerHTML = '<span class="legend-line"></span>' + (google.ready ? 'Solid = Google route · dashed = estimate' : 'Dashed = estimated connection, not a road route');
  $('mapProvider').textContent = map.mode === 'google' ? 'Google Maps ▾' : map.mode === 'world' ? 'World map · online ▾' : 'Local SF map ▾';
  document.querySelector('.map-caption').hidden = view === 'overview' || p.rows.filter(r => coordinates(r.stop)).length > 8;
  map.draw((view === 'overview' ? trip.days : [day]).map(d => ({ dayId: d.id, index: trip.days.indexOf(d), plan: plan(d) })), fit);
}

function stopCard(stop, i, row) {
  const leg = row?.leg, photo = photoUrl(stop.photo), start = row?.start;
  const blockInfo = stop.kind === 'travel' ? `<div class="travel-link">${row?.blockRoute ? `${esc(row.blockRoute.label)} · ${durationLabel(row.blockRoute.minutes)}` : travelEndpoints(stop) ? 'Original allowance · connect Google to refresh' : 'Original allowance · edit endpoints for Google routing'}${(row?.blockRoute?.warnings || []).map(w => `<span class="warning">${esc(w)}</span>`).join('')}</div>` : '';
  const travel = leg && leg.source !== 'same' ? `<div class="travel-link"><select aria-label="Travel mode to ${esc(stop.name)}" data-mode-stop="${esc(stop.id)}">${modeOptions(stop.mode)}</select><strong class="${leg.source === 'google' ? '' : 'estimated'}">${leg.source === 'unknown' ? 'Time unknown' : `${leg.source === 'estimate' ? '~ ' : ''}${durationLabel(leg.minutes)}`}</strong>${leg.km != null ? `<span>${leg.km.toFixed(1)} km${leg.source === 'estimate' ? ' straight-line' : ''}</span>` : ''}${stop.buffer ? `<span>+ ${stop.buffer}m buffer</span>` : ''}<a href="${esc(navigationUrl(row.stop))}" target="_blank" rel="noopener noreferrer" aria-label="Navigate to ${esc(stop.name)}">Directions ↗</a><span title="${esc(leg.label)}">${leg.source === 'google' ? esc(leg.label) : leg.source === 'manual' ? 'Your allowance' : 'Estimate'}</span>${(leg.warnings || []).map(w => `<span class="warning">${esc(w)}</span>`).join('')}</div>` : '';
  return `${travel}${blockInfo}<article class="stop ${stop.done ? 'done' : ''} ${stop.skipped ? 'skipped' : ''}" data-stop="${esc(stop.id)}"><span class="stop-number">${stop.done ? '✓' : i + 1}</span><div class="stop-time"><span>${stop.skipped ? 'Skipped for now' : !row ? 'Completed' : `${timeLabel(start)} – ${timeLabel(row.end)}`}</span><span class="fixed-badge">${stop.fixedAt ? `◷ Fixed ${esc(stop.fixedAt)}` : 'Flexible'}${row?.late ? ` · ${row.late}m late` : ''}</span></div><div class="stop-card"><div class="stop-main">${photo ? `<img class="stop-photo" src="${esc(photo)}" alt="" loading="lazy">` : `<span class="stop-icon" aria-hidden="true">${stop.kind === 'travel' ? '↗' : stop.kind === 'break' ? '◌' : '⌖'}</span>`}<div class="stop-copy"><button class="stop-name" data-action="details" data-id="${esc(stop.id)}">${esc(stop.name)}</button><div class="stop-type">${stop.protected ? 'Protected recovery · ' : ''}${stop.kind === 'travel' ? 'Original travel allowance' : stop.kind === 'break' ? 'Break / schedule block' : `${stop.duration} min visit`}${!coordinates(google.hydrate(stop)) && stop.kind === 'place' ? ' · location needed' : ''}</div>${stop.note ? `<p class="stop-note">${esc(stop.note)}</p>` : ''}</div></div><div class="stop-actions"><button data-action="done" data-id="${esc(stop.id)}" aria-label="${stop.done ? 'Mark not done' : 'Mark done'}: ${esc(stop.name)}">${stop.done ? '✓ Done' : '○ Done'}</button><button data-action="up" data-id="${esc(stop.id)}" aria-label="Move ${esc(stop.name)} up" ${i === 0 ? 'disabled' : ''}>↑</button><button data-action="down" data-id="${esc(stop.id)}" aria-label="Move ${esc(stop.name)} down" ${i === activeDay().stops.length - 1 ? 'disabled' : ''}>↓</button><button data-action="skip" data-id="${esc(stop.id)}">${stop.skipped ? 'Restore' : 'Skip'}</button><button class="edit-stop" data-action="edit" data-id="${esc(stop.id)}">Edit ↗</button></div></div></article>`;
}

function renderOverview() {
  $('overviewView').innerHTML = `<h2 class="overview-intro">The shape of your trip.</h2><p class="muted">Every day on one map. Select a day to make it yours.</p>${activeTrip().days.map((day, index) => { const p = plan(day); return `<button class="overview-card" data-open-day="${esc(day.id)}" style="--day-color:${COLORS[index % COLORS.length]}"><span class="overview-date"><span>DAY ${index + 1} · ${esc(dateLabel(day.date, { weekday: 'short' }))}</span><span>${p.warnings.length ? '◷ Timing checks' : `${p.rows.length} stops & blocks`}</span></span><h3>${esc(day.title)}</h3><span class="overview-dots">${p.rows.map(() => '<i></i>').join('')}</span><small>${esc(day.stops.filter(s => !s.skipped && s.kind === 'place').map(s => s.name).slice(0, 3).join(' → ') || day.stops[0]?.name || 'A blank canvas for your day')}</small><br><small>${day.start} — ${timeLabel(p.finish)} · ${p.unknown ? 'Travel incomplete' : `~${durationLabel(p.travel)} between stops`}</small></button>`; }).join('')}<button id="appendDay" class="add-stop">＋ Add another day</button>`;
}
function renderGo() {
  const day = activeDay(), remaining = day.stops.filter(s => !s.done && !s.skipped), next = remaining[0], now = new Intl.DateTimeFormat('en-GB', { timeZone: activeTrip().timezone, hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(new Date());
  $('goView').innerHTML = `<div class="go-hero"><p class="eyebrow">${localDate(new Date(), activeTrip().timezone) === day.date ? `IT’S ${esc(now)} · YOUR NEXT MOMENT` : `${esc(dateLabel(day.date))} · YOUR NEXT MOMENT`}</p><h2>${esc(next?.name || 'You made a day of it.')}</h2><p>${esc(next?.note || 'Enjoy a little space in your day.')}</p>${next?.kind === 'place' ? `<a href="${esc(navigationUrl(google.hydrate(next)))}" target="_blank" rel="noopener noreferrer">Navigate from my location ↗</a>` : ''}</div><div class="go-actions">${next ? `<button class="primary" data-action="done" data-id="${esc(next.id)}">✓ Mark done</button><button data-action="skip" data-id="${esc(next.id)}">Skip this stop</button>` : ''}<button id="startNow">Replan from now</button></div><p class="muted">${remaining.length} remaining · ${day.stops.filter(s => s.done).length} done. Fixed appointments stay fixed; late arrivals are flagged.</p>${remaining.map(s => `<div class="go-list"><span>${esc(s.name)}<br><small>${s.duration} min · ${s.fixedAt ? `fixed ${s.fixedAt}` : 'flexible'}</small></span><button data-action="edit" data-id="${esc(s.id)}">Edit</button></div>`).join('')}`;
}

function queueRoutes() {
  clearTimeout(routingTimer);
  if (!google.ready) return;
  const version = ++routingVersion;
  routingStatus = 'Updating Google routes…'; $('routeNotice').textContent = routingStatus;
  routingTimer = setTimeout(() => refreshRoutes(version), 450);
}
async function refreshRoutes(version) {
  const trip = activeTrip(), day = clone(activeDay()), gen = google.generation; let failures = 0, count = 0, previous = null, cursor = minutes(day.start);
  for (let stop of day.stops) {
    if (version !== routingVersion || !google.ready || gen !== google.generation) return;
    if (stop.skipped || (day.replanRemaining && stop.done)) continue;
    try { stop = await google.resolve(stop); } catch { failures++; }
    let leg = previous ? estimateLeg(previous, stop) : null;
    if (leg && leg.source !== 'same' && stop.travelMinutes == null) {
      try {
        const routed = await google.route(previous, stop, day.date, cursor, trip.timezone);
        if (version !== routingVersion || !google.ready || gen !== google.generation) return;
        if (routed) { results.set(legKey(previous, stop), routed); leg = routed; count++; }
      } catch { failures++; }
    }
    const arrival = cursor + (leg?.minutes || 0) + (leg && leg.source !== 'same' ? stop.buffer : 0);
    const start = Math.max(arrival, stop.fixedAt ? minutes(stop.fixedAt) : 0), endpoints = travelEndpoints(stop);
    let stay = stop.duration;
    if (endpoints) {
      try {
        const routed = await google.route(endpoints.from, endpoints.to, day.date, start, trip.timezone);
        if (version !== routingVersion || !google.ready || gen !== google.generation) return;
        if (routed) { results.set(`block:${stop.id}`, routed); stay = routed.minutes; count++; }
      } catch { failures++; }
    }
    cursor = start + stay;
    previous = stop.kind === 'break' ? (stop.movesLocation ? null : previous) : stop;
  }
  if (version !== routingVersion || !google.ready || gen !== google.generation) return;
  routingStatus = failures ? `${count} Google legs updated · ${failures} unavailable. Remaining times are estimates or unknown.` : count ? `${count} Google legs updated at ${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}.` : 'Google connected · add two located stops for live routing.';
  render();
}

function openDialog(title, body, eyebrow = 'MAKE IT YOURS') {
  dialogVersion++; $('dialogTitle').textContent = title; $('dialogEyebrow').textContent = eyebrow; $('dialogBody').innerHTML = body;
  if (!$('editor').open) $('editor').showModal();
  $('editor').scrollTop = 0;
  return dialogVersion;
}
function closeDialog() { dialogVersion++; $('editor').close(); }

function showAdd() {
  openDialog('Find your next stop.', `<p class="muted">Search the researched SF collection, or connect Google for places anywhere.</p><form id="searchForm" class="search-box" style="margin-top:15px"><input id="placeSearch" type="search" placeholder="A place, neighborhood, or coffee…" aria-label="Search places" autocomplete="off"><button type="submit">Search</button></form><div id="searchStatus" class="inline-status" role="status"></div><div id="searchResults" class="search-results"></div><div class="choice-row"><button id="manualPlace">＋ Custom place</button><button id="addBreak">◌ Break / meal</button></div>${google.ready ? '<p class="google-attribution">Search by Google Maps</p>' : '<button id="connectSearch" class="quiet">Connect Google to search worldwide ↗</button>'}`);
  let candidates = [], searchSequence = 0;
  const showLocal = query => {
    candidates = data.markers.filter(p => `${p.name} ${p.cluster}`.toLowerCase().includes(query.toLowerCase())).slice(0, 10).map(p => ({ name: p.name, placeKey: p.place_key, lat: p.lat, lng: p.lon, photo: p.photo_thumb, note: p.description_en || '', source: 'researched' }));
    paintResults();
  };
  const paintResults = () => { $('searchResults').innerHTML = candidates.map((p, i) => `<button class="search-result" data-result="${i}">${photoUrl(p.photo) ? `<img src="${esc(p.photo)}" alt="">` : '<span>⌖</span>'}<span>${esc(p.name)}<small>${esc(p.displayAddress || (p.source === 'google' ? 'Google Maps' : 'Researched SF collection'))}</small></span><span>＋</span></button>`).join('') || '<p class="muted">No places found. Try a different name or add a custom place.</p>'; };
  showLocal(''); $('placeSearch').focus();
  $('placeSearch').oninput = e => { searchSequence++; showLocal(e.target.value.trim()); $('searchStatus').textContent = google.ready ? 'Press Search to include Google Maps.' : ''; };
  $('searchForm').onsubmit = async e => {
    e.preventDefault(); const query = $('placeSearch').value.trim(); if (!query) return;
    showLocal(query); if (!google.ready) { $('searchStatus').textContent = 'Showing your local collection. Connect Google for more places.'; return; }
    const version = dialogVersion, sequence = ++searchSequence; $('searchStatus').textContent = 'Searching Google Maps…';
    try { const places = await google.search(`${query} ${activeTrip().destination || ''}`); if (version !== dialogVersion || sequence !== searchSequence) return;
      candidates = [...candidates, ...places.map(p => ({ name: p.displayName, placeId: p.id, displayAddress: p.formattedAddress, source: 'google' }))]; paintResults(); $('searchStatus').textContent = `${places.length} Google results. Choose the exact location.`;
    } catch (error) { if (version === dialogVersion && sequence === searchSequence) $('searchStatus').textContent = error.message; }
  };
  $('searchResults').onclick = e => { const b = e.target.closest('[data-result]'); if (!b) return; const { displayAddress, ...p } = candidates[Number(b.dataset.result)]; showStopEditor(makeStop(p), true); };
  $('manualPlace').onclick = () => showStopEditor(makeStop({ name: '' }), true);
  $('addBreak').onclick = () => showStopEditor(makeStop({ name: 'Rest & recharge', kind: 'break', duration: 30, buffer: 0 }), true);
  if ($('connectSearch')) $('connectSearch').onclick = showSettings;
}

function showStopEditor(stop, isNew = false) {
  const day = activeTrip().days.find(d => d.stops.some(s => s.id === stop.id)) || activeDay();
  openDialog(isNew ? 'Make room for this.' : 'A little change of plans.', `<form id="stopForm"><label>Stop name<input name="name" value="${esc(stop.name)}" required maxlength="500" placeholder="Where would you like to go?"></label><div class="form-grid"><label>Type<select name="kind">${option('place', 'Place', stop.kind)}${option('break', 'Break / meal / note', stop.kind)}${option('travel', 'Manual travel block', stop.kind)}</select></label><label>Day<select name="day">${activeTrip().days.map(d => option(d.id, dateLabel(d.date), day.id)).join('')}</select><small class="muted">Moved stops go to the end of that day.</small></label><label>Time here (minutes)<input name="duration" type="number" min="0" max="1440" step="1" value="${stop.duration}" required></label><label>Getting here<select name="mode">${modeOptions(stop.mode)}</select></label><label>Fixed start (optional)<input name="fixedAt" type="time" value="${esc(stop.fixedAt)}"></label><label>Arrival / parking buffer (min)<input name="buffer" type="number" min="0" max="240" step="1" value="${stop.buffer}" required></label><label class="full">Address (for Google routing)<input name="address" value="${esc(stop.address || '')}" maxlength="1000" placeholder="Full address, city, country"></label><label>Latitude (optional)<input name="lat" type="number" min="-90" max="90" step="any" value="${stop.lat ?? ''}" placeholder="37.7955"></label><label>Longitude (optional)<input name="lng" type="number" min="-180" max="180" step="any" value="${stop.lng ?? ''}" placeholder="-122.3934"></label><label class="full">Travel time override (minutes, optional)<input name="travelMinutes" type="number" min="0" max="1440" step="1" value="${stop.travelMinutes ?? ''}" placeholder="Leave blank for automatic estimates"></label><label class="full">Notes, booking details, things to remember<textarea name="note" maxlength="10000">${esc(stop.note)}</textarea></label></div><label class="check-label"><input name="protected" type="checkbox" ${stop.protected ? 'checked' : ''}>Protect this stop when reducing backtracking</label>${stop.kind === 'break' ? `<label class="check-label"><input name="movesLocation" type="checkbox" ${stop.movesLocation ? 'checked' : ''}>This block changes location (break route continuity)</label>` : ''}${stop.placeId ? '<p class="muted">Linked to a Google place. Editing the address or coordinates clears the link.</p>' : ''}${stop.originalTime ? `<p class="muted">Original schedule: ${esc(stop.originalTime)}. Imported time ranges are editable planning allowances; check the field guide for exact instructions.</p>` : ''}<p id="formError" class="error-text" role="alert"></p><div class="form-actions">${!isNew ? '<button id="removeStop" class="danger" type="button">Remove</button>' : ''}<button class="primary" type="submit">${isNew ? 'Add to my day' : 'Save changes'}</button></div></form>`);
  const form = $('stopForm');
  if (stop.kind === 'travel') {
    const endpoints = document.createElement('div'); endpoints.className = 'form-grid';
    endpoints.innerHTML = `<label class="full">Start address ${stop.fromLabel ? `· ${esc(stop.fromLabel)}` : ''}<input name="fromAddress" value="${esc(stop.fromAddress || '')}" placeholder="${stop.fromLat != null ? 'Known public location; leave blank to keep it' : 'Enter the exact origin to enable Google routing'}" maxlength="1000"></label><label class="full">Destination address ${stop.toLabel ? `· ${esc(stop.toLabel)}` : ''}<input name="toAddress" value="${esc(stop.toAddress || '')}" placeholder="${stop.toLat != null ? 'Known public location; leave blank to keep it' : 'Enter the exact destination'}" maxlength="1000"></label><p class="muted full">When both endpoints are known and Google is connected, this travel block updates automatically. Otherwise its original travel allowance is kept.</p>`;
    form.querySelector('.form-actions').before(endpoints);
  }
  form.onsubmit = e => {
    e.preventDefault(); const f = new FormData(form), lat = f.get('lat'), lng = f.get('lng');
    if (!!lat !== !!lng) { $('formError').textContent = 'Enter both latitude and longitude, or leave both blank.'; return; }
    const changed = { ...stop, name: f.get('name').trim(), kind: f.get('kind'), duration: +f.get('duration'), mode: f.get('mode'), fixedAt: f.get('fixedAt'), buffer: +f.get('buffer'), address: f.get('address').trim(), note: f.get('note'), protected: f.has('protected'), travelMinutes: f.get('travelMinutes') === '' ? null : +f.get('travelMinutes') };
    if (!changed.name) { $('formError').textContent = 'Give this stop a name.'; return; }
    if (form.elements.movesLocation) changed.movesLocation = f.has('movesLocation');
    if (lat !== '') { changed.lat = +lat; changed.lng = +lng; } else { delete changed.lat; delete changed.lng; }
    if (changed.address !== (stop.address || '') || changed.lat !== stop.lat || changed.lng !== stop.lng) { delete changed.placeId; delete changed.placeKey; }
    if (stop.kind === 'travel') for (const prefix of ['from', 'to']) {
      changed[`${prefix}Address`] = f.get(`${prefix}Address`).trim();
      if (changed[`${prefix}Address`]) { delete changed[`${prefix}Lat`]; delete changed[`${prefix}Lng`]; }
    }
    const target = activeTrip().days.find(d => d.id === f.get('day'));
    mutate(() => { if (isNew) target.stops.push(changed); else if (target.id !== day.id) { day.stops = day.stops.filter(s => s.id !== stop.id); target.stops.push(changed); } else day.stops[day.stops.findIndex(s => s.id === stop.id)] = changed; selectedDayId = target.id; }, isNew ? 'Added. Your day has been recalculated.' : 'Saved. Your day has been recalculated.');
    closeDialog(); map.fit();
  };
  if ($('removeStop')) $('removeStop').onclick = () => { mutate(() => { day.stops = day.stops.filter(s => s.id !== stop.id); }, 'Stop removed. Undo is available.'); closeDialog(); };
}

function showDayEditor() {
  const day = activeDay();
  openDialog('Set the pace.', `<form id="dayForm"><label>Day title<input name="title" value="${esc(day.title)}" maxlength="200" required></label><div class="form-grid"><label>Start at<input name="start" type="time" value="${day.start}" required></label><label>Finish by<input name="end" type="time" value="${day.end}" required></label><label class="full">A reminder for the day<textarea name="note" maxlength="10000">${esc(day.note)}</textarea></label></div><p class="muted">Fixed times stay in place. If a change makes one impossible, the plan flags it.</p><div class="form-actions"><button class="primary">Save day</button></div></form>`);
  $('dayForm').onsubmit = e => { e.preventDefault(); const f = new FormData(e.target); if (minutes(f.get('end')) <= minutes(f.get('start'))) { toast('Finish time must be after the start time.'); return; } mutate(() => Object.assign(day, { title: f.get('title').trim(), start: f.get('start'), end: f.get('end'), note: f.get('note') }), 'Day updated.'); closeDialog(); };
}

function showNewTrip() {
  const today = localDate();
  openDialog('Where to next?', `<form id="tripForm"><label>Trip name<input name="name" placeholder="A long weekend in Kyoto" required maxlength="200"></label><div class="form-grid"><label class="full">Destination<input name="destination" placeholder="City, region, country" required maxlength="200"></label><label>First day<input name="startDate" type="date" value="${today}" required></label><label>Number of days<input name="count" type="number" value="4" min="1" max="60" required></label><label class="full">Destination time zone<input name="timezone" list="timezones" value="America/Los_Angeles" required><datalist id="timezones">${['America/Los_Angeles', 'America/New_York', 'America/Chicago', 'Europe/London', 'Europe/Paris', 'Asia/Seoul', 'Asia/Tokyo', 'Asia/Singapore', 'Australia/Sydney', 'UTC'].map(z => `<option value="${z}">`).join('')}</datalist></label></div><p class="muted">Your existing trips stay here. For places beyond California, select the online world map or connect Google.</p><p id="newTripError" class="error-text" role="alert"></p><div class="form-actions"><button class="primary">Create trip</button></div></form>`);
  $('tripForm').onsubmit = e => { e.preventDefault(); const f = new FormData(e.target); try {
    new Intl.DateTimeFormat('en', { timeZone: f.get('timezone') }).format();
    if (!f.get('name').trim() || !f.get('destination').trim()) throw new Error('Name and destination are required.');
    if (store.trips.length >= 50) throw new Error('This device has 50 trips. Export a backup before adding more.');
    const trip = makeTrip({ name: f.get('name').trim(), destination: f.get('destination').trim(), startDate: f.get('startDate'), count: +f.get('count'), timezone: f.get('timezone') });
    mutate(() => { store.trips.push(trip); store.activeTripId = trip.id; selectedDayId = trip.days[0].id; view = 'day'; }, 'Your new trip is ready.'); closeDialog(); if (!google.ready) map.setWorld();
  } catch (error) { $('newTripError').textContent = `Check your trip details and use a valid time zone, such as Asia/Tokyo. ${error.message}`; } };
}

function showSettings() {
  openDialog('A little more connected.', `<p class="detail-note">Connect Google for worldwide place search, road routes, traffic predictions, opening hours, and available reviews. When connected, place searches and route endpoints (including any custom addresses) are sent to Google. Notes and booking details stay in your plan on this device.</p><div class="connection-card"><h3>Google Maps ${google.ready ? '· connected' : ''}</h3><p class="muted">This uses your Google Cloud project and its API billing. A browser key is visible to the browser: restrict it to your website and the required APIs.</p><ol><li>Enable Maps JavaScript API, Places API (New), and Routes API.</li><li>Add this website to the key’s website restrictions.</li><li>Connect below. The key stays in this tab’s session storage and is never included in a trip backup.</li></ol><a class="muted" href="https://developers.google.com/maps/documentation/javascript/get-api-key" target="_blank" rel="noopener noreferrer">Google setup instructions ↗</a></div><form id="googleForm"><label>Restricted browser API key<input id="googleKey" type="password" autocomplete="off" placeholder="AIza…" required></label><p id="googleStatus" class="inline-status" role="status"></p><div class="form-actions">${google.ready ? '<button id="disconnectGoogle" type="button">Disconnect</button>' : ''}<button class="primary" id="connectGoogle">Connect Google</button></div></form><p class="muted" style="margin-top:18px">Google returns a selection of reviews, not every Google Maps review. This does not synchronize your personal saved Google Maps lists or accounts. Reviews and route results are loaded fresh and kept out of your backup.</p>`);
  $('googleForm').onsubmit = async e => {
    e.preventDefault(); const version = dialogVersion, key = $('googleKey').value.trim(); $('connectGoogle').disabled = true; $('googleStatus').textContent = 'Connecting to Google…';
    try { await google.connect(key); await map.setGoogle(); try { sessionStorage.setItem('fieldtrip.googleKey', key); } catch {} if (version === dialogVersion) closeDialog(); routingStatus = ''; render(); queueRoutes(); toast('Google libraries connected. Place and route requests will verify API access.'); }
    catch (error) { if (version === dialogVersion) { $('googleStatus').textContent = error.message; $('connectGoogle').disabled = false; } }
  };
  if ($('disconnectGoogle')) $('disconnectGoogle').onclick = () => { google.disconnect(); try { sessionStorage.removeItem('fieldtrip.googleKey'); } catch {} routingVersion++; results.clear(); routingStatus = ''; map.setLocal(); closeDialog(); render(); toast('Google disconnected. Local planning is available.'); };
}

function showDetails(id) {
  const stop = stopById(id); if (!stop) return;
  map.focus(google.hydrate(stop));
  const photo = photoUrl(stop.photo);
  openDialog(stop.name, `${photo ? `<img class="details-photo" src="${esc(photo.replace('/thumb/', '/medium/'))}" alt="${esc(stop.name)}">` : ''}<p class="detail-note">${esc(stop.note || 'Add a note, set your pace, and make this stop your own.')}</p>${stop.originalTime ? `<p class="muted">Original plan: ${esc(stop.originalTime)}</p>` : ''}<div class="details-links"><a href="${esc(navigationUrl(google.hydrate(stop)))}" target="_blank" rel="noopener noreferrer">Directions ↗</a><a href="https://www.google.com/maps/search/?${esc(new URLSearchParams({ api: '1', query: stop.address || stop.name, ...(stop.placeId ? { query_place_id: stop.placeId } : {}) }).toString())}" target="_blank" rel="noopener noreferrer">Google Maps & reviews ↗</a></div><div class="choice-row"><button id="detailEdit">Edit this stop</button><button id="detailLive">${google.ready ? 'Load Google details' : 'Connect Google'}</button></div><div id="liveDetails"></div>`);
  $('detailEdit').onclick = () => showStopEditor(stop);
  $('detailLive').onclick = () => google.ready ? loadDetails(stop) : showSettings();
}
async function loadDetails(stop) {
  const version = dialogVersion; $('liveDetails').innerHTML = '<p class="inline-status">Fetching current Google details…</p>';
  try {
    const result = await google.details(stop); if (version !== dialogVersion) return;
    if (result.candidates) {
      $('liveDetails').innerHTML = `<p class="inline-status">Choose the exact Google place to link. Check its address before confirming.</p>${result.candidates.map((p, i) => `<button class="search-result" data-link-place="${i}"><span>${esc(p.displayName)}<small>${esc(p.formattedAddress)}</small></span>Link</button>`).join('') || '<p class="muted">No matching place. Try editing the name or address.</p>'}<p class="google-attribution">Google Maps</p>`;
      $('liveDetails').onclick = e => { const b = e.target.closest('[data-link-place]'); if (!b) return; const p = result.candidates[Number(b.dataset.linkPlace)]; if (p.location) google.locations.set(p.id, { lat: p.location.lat(), lng: p.location.lng() }); mutate(() => { stop.placeId = p.id; }, 'Linked to the selected Google place.'); loadDetails(stop); };
      return;
    }
    const p = result.place;
    $('liveDetails').innerHTML = `<div class="connection-card"><p class="google-attribution">Google Maps · fetched ${esc(new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }))}</p><h3>${esc(p.displayName)}</h3><p class="muted">${esc(p.formattedAddress)}</p><p class="inline-status">${p.rating ? `★ ${esc(p.rating)} · ${esc(p.userRatingCount || 0)} ratings` : 'Rating unavailable'}${p.businessStatus ? ` · ${esc(p.businessStatus.replaceAll('_', ' ').toLowerCase())}` : ''}</p><p class="muted">${(p.regularOpeningHours?.weekdayDescriptions || ['Opening hours unavailable.']).map(esc).join('<br>')}</p><p class="muted">Regular hours do not guarantee access on your travel date.</p>${p.websiteURI ? `<div class="details-links"><a href="${esc(safeUrl(p.websiteURI))}" target="_blank" rel="noopener noreferrer">Official website ↗</a></div>` : ''}${(p.reviews || []).map(r => `<article class="review"><a href="${esc(safeUrl(r.authorAttribution?.uri))}" target="_blank" rel="noopener noreferrer">${esc(r.authorAttribution?.displayName || 'Google reviewer')}</a> <small>★ ${esc(r.rating)} · ${esc(r.relativePublishTimeDescription || '')}</small><p>${esc(r.text || '')}</p>${r.googleMapsURI ? `<a href="${esc(safeUrl(r.googleMapsURI))}" target="_blank" rel="noopener noreferrer">View review ↗</a>` : ''}</article>`).join('') || '<p class="muted">No review text returned by Google.</p>'}${(p.attributions || []).map(a => `<a href="${esc(safeUrl(a.providerURI))}" target="_blank" rel="noopener noreferrer">${esc(a.provider || '')}</a>`).join('')}<p class="muted">Google supplies a limited selection of reviews. <a href="${esc(safeUrl(p.googleMapsURI))}" target="_blank" rel="noopener noreferrer">Read more on Google Maps ↗</a></p></div>`;
  } catch (error) { if (version === dialogVersion) $('liveDetails').innerHTML = `<p class="error-text">${esc(error.message)}</p>`; }
}

function showTools() {
  openDialog('Everything in its place.', `<div class="tools-list"><button id="toolUndo" ${history.length ? '' : 'disabled'}>↶ Undo the last change</button><button id="toolConnection">⌖ Google Maps connection</button><button id="exportBackup">↓ Export all trips as a backup</button><label class="search-result" for="importBackup">↑ Import trips from a backup<input id="importBackup" type="file" accept="application/json,.json" class="sr-only"></label><button id="duplicateTrip">＋ Duplicate this trip to try another plan</button><button id="toolNewTrip">＋ Create a new trip</button><button id="toolEditDay">◷ Day settings</button><button id="printTrip">Print this trip / save as PDF</button></div><p class="muted" style="margin-top:18px">Saved in this browser on this device. Export and import to move plans to your phone. Backups include your notes and custom addresses; Google keys and fetched reviews are excluded. There is no automatic cross-device sync.</p>${recoverStorage ? '<p class="warning">A saved plan could not be read. Export the recovery file before resetting storage.</p><button id="exportRecovery">Export original recovery file</button><button id="resetStorage">Start a fresh plan on this device</button>' : ''}`);
  $('toolUndo').onclick = () => { undo(); closeDialog(); }; $('toolConnection').onclick = showSettings; $('toolNewTrip').onclick = showNewTrip; $('toolEditDay').onclick = showDayEditor;
  $('exportBackup').onclick = () => download(JSON.stringify(store, null, 2), `fieldtrip-backup-${localDate()}.json`);
  $('importBackup').onchange = async e => {
    const file = e.target.files[0]; if (!file) return;
    try { if (file.size > 5 * 1024 * 1024) throw new Error('Choose a backup smaller than 5 MB.'); const imported = validateStore(JSON.parse(await file.text()));
      if (store.trips.length + imported.trips.length > 50) throw new Error('Import would exceed the 50-trip limit.');
      openDialog('Bring these trips along?', `<p class="detail-note">Import ${imported.trips.length} trip${imported.trips.length > 1 ? 's' : ''}: ${imported.trips.map(t => esc(t.name)).join(', ')}. Your existing trips stay here. Matching trips will be added as copies.</p><div class="form-actions"><button id="confirmImport" class="primary">Import trips</button></div>`);
      $('confirmImport').onclick = () => { mutate(() => { imported.trips.forEach(t => { t.id = uid(); store.trips.push(t); }); store.activeTripId = imported.trips[0].id; selectedDayId = activeTrip().days[0].id; view = 'day'; }, 'Trips imported. Existing trips kept.'); closeDialog(); };
    } catch (error) { toast(error.message || 'Could not read that backup. Existing plans were kept.'); }
  };
  $('duplicateTrip').onclick = () => { if (store.trips.length >= 50) return toast('Trip limit reached.'); const t = clone(activeTrip()); t.id = uid(); t.name += ' · alternate'; mutate(() => { store.trips.push(t); store.activeTripId = t.id; selectedDayId = t.days[0].id; }, 'Alternate plan created. Your original is safe.'); closeDialog(); };
  $('printTrip').onclick = () => { closeDialog(); printTrip(); };
  if ($('exportRecovery')) $('exportRecovery').onclick = () => download(localStorage.getItem(STORAGE_KEY) || '', 'fieldtrip-recovery.json');
  if ($('resetStorage')) $('resetStorage').onclick = () => { recoverStorage = false; save(); closeDialog(); toast('Fresh plan saved.'); };
}
function download(text, name) { const blob = new Blob([text], { type: 'application/json' }), url = URL.createObjectURL(blob), a = document.createElement('a'); a.href = url; a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); }
function printTrip() {
  const w = window.open('', '_blank'); if (!w) return toast('Allow the print window, then try again.');
  w.document.write(`<!doctype html><html><head><title>${esc(activeTrip().name)}</title><style>body{font:14px system-ui;max-width:850px;margin:40px auto;color:#173e36}section{break-inside:avoid}h1{font-size:32px}h2{margin-top:32px}li{margin:12px 0;line-height:1.5}small{color:#657268}a{color:inherit}@media print{button{display:none}}</style></head><body><button onclick="window.print()">Print / save as PDF</button><h1>${esc(activeTrip().name)}</h1><p>${esc(activeTrip().timezone)} · Planning estimates; check live directions before leaving.</p>${activeTrip().days.map(d => `<section><h2>${esc(dateLabel(d.date))} · ${esc(d.title)}</h2><p>${esc(d.note)}</p><ol>${plan(d).rows.map(r => `<li><strong>${timeLabel(r.start)} – ${timeLabel(r.end)} · ${esc(r.stop.name)}</strong>${r.late ? ` · ${r.late} min late` : ''}<br><small>${esc(r.stop.note)}${r.leg ? ` · Travel: ${r.leg.source === 'unknown' ? 'unknown' : `${r.leg.minutes} min (${r.leg.label})`}` : ''}</small></li>`).join('')}</ol></section>`).join('')}</body></html>`); w.document.close();
}

function showOptimize() {
  const day = activeDay(), next = optimizeStops(hydratedDay(day).stops), different = next.some((s, i) => s.id !== day.stops[i].id);
  if (!different) return toast('No shorter order found among flexible stops. Fixed times, breaks, recovery, and endpoints stay in place.');
  const original = plan(day), proposed = scheduleDay({ ...day, stops: next });
  openDialog('A little less backtracking.', `<p class="detail-note">A suggested order based on straight-line distance. Fixed appointments, recovery blocks, and the first and last stops stay in place. This does not account for road access, traffic, or opening hours.</p><p class="muted">Travel estimate: ${durationLabel(original.travel)} → ${durationLabel(proposed.travel)}. Review the order before applying.</p><ol>${next.filter(s => !s.skipped).map(s => `<li style="margin:10px 0;font-size:12px">${esc(s.name)}${s.fixedAt ? ` · fixed ${s.fixedAt}` : ''}</li>`).join('')}</ol><div class="form-actions"><button id="applyOrder" class="primary">Use this order</button></div>`);
  $('applyOrder').onclick = () => { const ids = next.map(s => s.id); mutate(() => { day.stops.sort((a, b) => ids.indexOf(a.id) - ids.indexOf(b.id)); }, 'New order applied. Undo is available.'); closeDialog(); map.fit(); };
}
function startNow() {
  const day = activeDay(), trip = activeTrip();
  if (day.date !== localDate(new Date(), trip.timezone)) return toast('Select today’s date to replan from now.');
  const time = new Intl.DateTimeFormat('en-GB', { timeZone: trip.timezone, hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(new Date());
  openDialog('Start from this moment.', `<p class="detail-note">Start unfinished stops at ${esc(time)} in ${esc(trip.timezone)}. Completed stops remain visible in your itinerary. Their time is excluded from the remaining schedule. Fixed appointments remain fixed and conflicts are flagged.</p><div class="form-actions"><button class="primary" id="confirmNow">Replan remaining day</button></div>`);
  $('confirmNow').onclick = () => { mutate(() => { day.start = time; day.replanRemaining = true; }, 'Remaining day starts now.'); closeDialog(); };
}

document.addEventListener('click', e => {
  const b = e.target.closest('button'); if (!b || !store) return;
  if (b.dataset.view) return setView(b.dataset.view);
  if (b.dataset.mobile) return mobile(b.dataset.mobile);
  if (b.dataset.day) return selectDay(b.dataset.day);
  if (b.dataset.openDay) { view = 'day'; return selectDay(b.dataset.openDay); }
  const s = b.dataset.id && stopById(b.dataset.id);
  if (s) {
    const day = activeTrip().days.find(d => d.stops.some(x => x.id === s.id));
    if (b.dataset.action === 'details') return showDetails(s.id);
    if (b.dataset.action === 'edit') return showStopEditor(s);
    if (b.dataset.action === 'done') return mutate(() => { s.done = !s.done; }, s.done ? 'Marked not done.' : 'A moment well spent.', day.replanRemaining || false);
    if (b.dataset.action === 'skip') return mutate(() => { s.skipped = !s.skipped; if (!s.skipped) day.stops.forEach(other => { if ((s.swapFor && other.placeKey === s.swapFor) || (s.placeKey && other.swapFor === s.placeKey)) other.skipped = true; }); }, 'Day recalculated.');
    if (['up', 'down'].includes(b.dataset.action)) { mutate(() => { day.stops = reorder(day.stops, s.id, b.dataset.action === 'up' ? -1 : 1); }); return; }
  }
  if (b.id === 'editDay') showDayEditor();
  if (b.id === 'optimize') showOptimize();
  if (b.id === 'delayDay') { const day = activeDay(); if (minutes(day.start) > 1424) return toast('The delay would move into tomorrow. Edit the day instead.'); mutate(() => { day.start = clock(minutes(day.start) + 15); }, 'Start delayed by 15 minutes. Fixed times are checked.'); }
  if (b.id === 'startNow') startNow();
  if (b.id === 'appendDay') { const trip = activeTrip(); if (trip.days.length >= 90) return toast('This trip already has 90 days.'); const date = new Date(Date.parse(`${trip.days.at(-1).date}T12:00:00Z`) + 86400000).toISOString().slice(0, 10); mutate(() => { const d = { id: uid(), date, title: 'Room for one more adventure', start: '09:00', end: '20:00', note: '', stops: [] }; trip.days.push(d); selectedDayId = d.id; view = 'day'; }, 'Another day added.'); }
});
document.addEventListener('change', e => {
  if (e.target.dataset.modeStop) { const s = stopById(e.target.dataset.modeStop); mutate(() => { s.mode = e.target.value; s.travelMinutes = null; }); }
  if (e.target.id === 'allModes' && e.target.value) { const mode = e.target.value; mutate(() => { activeDay().stops.filter(s => s.kind === 'place').forEach(s => { s.mode = mode; s.travelMinutes = null; }); }, `Travel to places set to ${MODES[mode].toLowerCase()}.`); }
});
$('closeDialog').onclick = closeDialog; $('editor').addEventListener('cancel', () => { dialogVersion++; });
$('addStop').onclick = showAdd; $('newTrip').onclick = showNewTrip; $('undo').onclick = undo; $('settings').onclick = showSettings; $('more').onclick = showTools;
$('tripSelect').onchange = e => { store.activeTripId = e.target.value; history = []; selectedDayId = activeTrip().days.find(d => d.date === localDate(new Date(), activeTrip().timezone))?.id || activeTrip().days[0].id; results.clear(); routingVersion++; save(); render(true); queueRoutes(); };
$('fitRoute').onclick = () => map.fit();
$('locate').onclick = () => { if (!navigator.geolocation) return toast('Location is unavailable in this browser.'); navigator.geolocation.getCurrentPosition(position => { map.location(position.coords.latitude, position.coords.longitude); toast('Your location is shown for this session.'); }, () => toast('Location is unavailable. Check browser location permissions.'), { timeout: 10000, maximumAge: 30000 }); };
$('mapProvider').onclick = () => { openDialog('See it your way.', `<div class="tools-list"><button id="localMap">Local SF, Monterey & Yosemite map</button><button id="worldMap">World map · needs internet</button><button id="googleMapChoice">${google.ready ? 'Google Maps · connected' : 'Connect Google Maps'}</button></div><p class="muted" style="margin-top:15px">The local map covers this California trip. Google routes are displayed on Google Maps. Online world tiles are provided by OpenStreetMap.</p>`); $('localMap').onclick = () => { if (google.ready) { toast('Disconnect Google in Connections to return to the local map.'); return; } map.setLocal(); closeDialog(); render(); }; $('worldMap').onclick = () => { if (google.ready) { toast('Disconnect Google in Connections to use the world map.'); return; } map.setWorld(); closeDialog(); render(); }; $('googleMapChoice').onclick = () => google.ready ? (map.setGoogle(), closeDialog(), render()) : showSettings(); };
window.addEventListener('fieldtrip-google-error', () => { google.disconnect(); routingVersion++; results.clear(); routingStatus = 'Google authentication failed. Local estimates are shown.'; map.setLocal(); render(); toast('Google rejected the connection. Check API access, billing and website restrictions.'); });
window.addEventListener('online', () => { toast('Back online.'); queueRoutes(); });
window.addEventListener('offline', () => { routingVersion++; routingStatus = 'Offline · saved plan available. Google results may be stale.'; render(); });
document.addEventListener('visibilitychange', () => { if (!document.hidden && store) { render(); if (google.ready) queueRoutes(); } });

async function init() {
  try {
    const response = await fetch('data/phase7_app_data.json'); if (!response.ok) throw new Error('Trip data could not load.'); data = await response.json();
    let saved; try { saved = localStorage.getItem(STORAGE_KEY); if (saved) store = validateStore(JSON.parse(saved)); } catch { recoverStorage = Boolean(saved); }
    if (!store) { const trip = seedTrip(data); store = { version: 1, activeTripId: trip.id, trips: [trip] }; }
    const trip = activeTrip(); selectedDayId = trip.days.find(d => d.id === store.selectedDayId)?.id || trip.days.find(d => d.date === localDate(new Date(), trip.timezone))?.id || trip.days[0].id;
    render(); map.init(); if (!recoverStorage) save(); else toast('A saved plan needs recovery. Open trip tools to export the original file.');
    let key; try { key = sessionStorage.getItem('fieldtrip.googleKey'); } catch {}
    if (key) { try { await google.connect(key); await map.setGoogle(); render(); queueRoutes(); } catch { toast('Google could not reconnect. Your saved plan is available.'); } }
    if ('serviceWorker' in navigator) navigator.serviceWorker.register('planner-sw.js').catch(() => {});
  } catch (error) { $('tripTitle').textContent = 'Let’s get your trip back.'; $('tripSubtitle').textContent = error.message; $('timeline').innerHTML = '<p class="warning">Open the app through the local server or its website, then reload. Your saved plans have not been changed.</p>'; }
}
init();
