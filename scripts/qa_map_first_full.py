"""Map-first acceptance: filters, visual states, bilingual/theme, providers, touch."""

import itertools
import json
from pathlib import Path

from playwright.sync_api import sync_playwright
from qa_cleanup import bounded_cleanup
from qa_config import MODULAR_URL


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "QA/map_first"
OUT.mkdir(parents=True, exist_ok=True)
URL = MODULAR_URL
ROUTES = ("A1", "A2", "B1", "B2")
DATES = ("all", "10/3", "10/4", "10/5", "10/6", "10/7", "10/8", "10/9", "10/10", "10/11")
REGIONS = ("overall", "sf", "monterey", "yosemite")
report = {"checks": {}, "screenshots": [], "errors": [], "console_errors": [], "failed_requests": [], "cleanup_warnings": []}


def capture(page, name):
    if page.evaluate("!!window.__tripApp && window.__tripApp.state.provider==='vector'"):
        page.wait_for_function("window.__tripApp.map().areTilesLoaded()", timeout=15000)
    page.wait_for_timeout(150)
    path = OUT / f"{name}.png"
    page.screenshot(path=str(path), full_page=True)
    report["screenshots"].append(str(path.relative_to(ROOT)))


def read(page, expression, argument=None):
    return page.evaluate(expression, argument)


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True, timeout=90000)
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.set_default_timeout(240000)
    page.on("pageerror", lambda error: report["errors"].append(str(error)))
    page.on("console", lambda message: report["console_errors"].append(message.text[:500]) if message.type == "error" else None)
    page.on("requestfailed", lambda request: report["failed_requests"].append({"url": request.url, "failure": request.failure}))
    page.goto(URL, wait_until="domcontentloaded", timeout=90000)
    loading_path = OUT / "loading_1440.png"
    page.screenshot(path=str(loading_path), full_page=True)
    report["screenshots"].append(str(loading_path.relative_to(ROOT)))
    page.wait_for_function("window.__tripApp?.map()?.isStyleLoaded()", timeout=30000)
    page.wait_for_timeout(900)
    report["checks"]["loading_completed"] = read(page, "()=>!document.getElementById('loadingScreen')")
    capture(page, "default_1440_ko_light")
    report["checks"]["initial"] = read(page, """()=>{const a=window.__tripApp,m=a.map();return {provider:a.state.provider,health:a.state.providerHealth.vector,features:a.visibleRouteFeatures().length,clusters:document.querySelectorAll('.photo-cluster').length,dayChips:document.querySelectorAll('.day-chip').length,dayCards:document.querySelectorAll('.map-slot').length,legLabels:document.querySelectorAll('.route-leg-label').length,routeLayers:['A1','A2','B1','B2'].map(r=>!!m.getLayer('trip-transfer-'+r)),canvas:document.querySelectorAll('.maplibregl-canvas').length}}""")
    report["checks"]["gap_audit"] = read(page, """()=>{const a=window.__tripApp,keys=['pier39','tunnel_tops','bixby','ghirardelli','cable_car','carmel','el_capitan','monterey_wharf'];return {places:a.DATA.markers.length,photos:a.DATA.markers.length*3,audited:keys.filter(k=>a.DATA.markers.some(m=>m.place_key===k)),auditedMarkers:document.querySelectorAll('.photo-marker.audited').length,routeKinds:[...new Set(a.visibleRouteFeatures().map(x=>x.properties.kind))].sort(),routeLayerColors:['transfer','local','conditional','option','bonus','recovery','choice'].every(kind=>['A1','A2','B1','B2'].every(r=>a.map().getPaintProperty(`trip-${kind}-${r}`,'line-color')===a.DATA.routes[r].color))}}""")
    page.locator(".photo-cluster").first.hover()
    report["checks"]["cluster_hover"] = read(page, """()=>({preview:document.getElementById('previewCard').classList.contains('show'),routeTip:document.getElementById('routeTip').classList.contains('show'),photo:document.querySelector('#previewCard img')?.naturalWidth||0})""")
    capture(page, "cluster_hover_1440")
    page.locator(".photo-cluster").first.click()
    page.wait_for_timeout(900)
    report["checks"]["cluster_zoom"] = read(page, """()=>{const a=window.__tripApp,m=a.map();return {zoom:m.getZoom(),localRouteLayer:!!m.getLayer('trip-local-A1'),renderedRoutes:m.queryRenderedFeatures({layers:['trip-local-A1']}).length,localRouteLayout:m.getLayoutProperty('trip-local-A1','visibility')||'visible',visibleMarkers:[...document.querySelectorAll('.photo-marker')].filter(x=>x.style.display!=='none').length}}""")
    capture(page, "cluster_zoom_1440")
    page.locator("#panelToggle").click()
    report["checks"]["map_only"] = read(page, """()=>({panelHidden:document.getElementById('app').classList.contains('panel-hidden'),dayChips:document.querySelectorAll('.day-chip').length,dayCards:document.querySelectorAll('.map-slot').length,mapWidth:document.getElementById('map').getBoundingClientRect().width})""")
    capture(page, "map_only_1440")
    page.locator('.day-chip[data-day="10/3"]').click()
    page.wait_for_function("window.__tripApp.state.date==='10/3'")
    page.locator('[data-region="sf"]').click()
    page.wait_for_function("window.__tripApp.state.region==='sf'")
    for route in ("A2", "B1", "B2"):
        page.locator(f'[data-route="{route}"]').click()
    page.wait_for_function("window.__tripApp.state.routes.size===1")
    read(page, """()=>window.__tripApp.map().jumpTo({center:[-122.395,37.797],zoom:12.2})""")
    page.wait_for_timeout(900)
    report["checks"]["a1_oct3_sf_zoom12"] = read(page, """()=>{const a=window.__tripApp,m=a.map();return {date:a.state.date,region:a.state.region,routes:[...a.state.routes],zoom:m.getZoom(),routeLayer:!!m.getLayer('trip-local-A1'),renderedRoutes:m.queryRenderedFeatures({layers:['trip-local-A1']}).length,labels:[...document.querySelectorAll('.marker-callout')].filter(x=>x.style.display==='block').length,scheduleCards:document.querySelectorAll('.map-slot').length}}""")
    capture(page, "a1_oct3_sf_map_only")
    page.locator(".photo-marker[data-place-key='ferry']").hover()
    report["checks"]["stop_hover"] = read(page, """()=>({preview:document.getElementById('previewCard').classList.contains('show'),photo:document.querySelector('#previewCard img')?.naturalWidth||0,text:document.getElementById('previewCard').innerText.slice(0,350)})""")
    capture(page, "stop_hover_1440")
    page.locator(".photo-marker[data-place-key='ferry']").click()
    page.wait_for_function("[...document.querySelectorAll('#detailsPane .photo-grid img')].length===3&&[...document.querySelectorAll('#detailsPane .photo-grid img')].every(x=>x.complete&&x.naturalWidth>0)", timeout=15000)
    report["checks"]["place_detail"] = read(page, """()=>({focus:document.getElementById('mapFocus').classList.contains('show'),title:document.querySelector('#detailsPane h2')?.innerText,subtitle:document.querySelector('#detailsPane .place-korean')?.innerText,photos:document.querySelectorAll('#detailsPane .photo-grid img').length,decoded:[...document.querySelectorAll('#detailsPane .photo-grid img')].every(x=>x.complete&&x.naturalWidth>0),timingCards:document.querySelectorAll('#detailsPane .fact .timeline-card').length})""")
    capture(page, "ferry_detail_map_only")
    page.locator("#langToggle").click()
    page.wait_for_function("window.__tripApp.state.lang==='en'")
    report["checks"]["english"] = read(page, """()=>({lang:document.documentElement.lang,title:document.querySelector('#detailsPane h2')?.innerText,subtitleCount:document.querySelectorAll('#detailsPane .place-korean').length,controls:[...document.querySelectorAll('[data-i18n]')].slice(0,12).map(x=>x.innerText),reason:document.querySelector('#detailsPane .detail-glance')?.innerText.slice(0,250)})""")
    capture(page, "english_light_1440")
    page.locator("#themeToggle").click()
    page.wait_for_function("window.__tripApp.state.theme==='dark'&&document.documentElement.dataset.theme==='dark'&&window.__tripApp.map().isStyleLoaded()")
    page.wait_for_timeout(650)
    report["checks"]["dark"] = read(page, """()=>({theme:document.documentElement.dataset.theme,mapBackground:window.__tripApp.map().getPaintProperty('background','background-color'),canvas:document.querySelectorAll('.maplibregl-canvas').length})""")
    capture(page, "english_dark_1440")
    page.locator("#panelToggle").click()
    capture(page, "english_dark_sidebar_1440")
    # Every nonempty route selection × all dates × four regions, on the actual map engine.
    matrix = read(page, """async ({routes,dates,regions})=>{const a=window.__tripApp,rows=[];for(let mask=1;mask<16;mask++){a.state.routes=new Set(routes.filter((_,i)=>mask&(1<<i)));for(const date of dates)for(const region of regions){a.state.date=date;a.state.region=region;a.state.selected=null;a.renderDetail(null);a.renderTimeline();await a.drawMap(false);const map=a.map(),expected=a.DATA.markers.filter(a.markerVisible).length,expectedTimeline=a.DATA.timeline.filter(a.timelineVisible).length,markers=[...document.querySelectorAll('.photo-marker')],features=a.visibleRouteFeatures();const fail=[];if(markers.length!==expected)fail.push('markers');if(new Set(markers.map(x=>x.dataset.placeKey)).size!==markers.length)fail.push('duplicate_stop');if(document.querySelectorAll('[data-timeline]').length!==expectedTimeline)fail.push('timeline');if(document.querySelectorAll('.maplibregl-canvas').length!==1)fail.push('canvas');if(!map.getLayer('trip-local-A1'))fail.push('route_layer');if(date!=='all'&&features.some(f=>f.properties.date!==date))fail.push('cross_day');if(document.querySelectorAll('.day-chip').length!==10)fail.push('date_ribbon');rows.push({routes:[...a.state.routes].join(','),date,region,markers:markers.length,timeline:expectedTimeline,features:features.length,fail})}}return rows}""", {"routes": ROUTES, "dates": DATES, "regions": REGIONS})
    report["checks"]["matrix"] = {"states": len(matrix), "failed": [row for row in matrix if row["fail"]], "min_markers": min(row["markers"] for row in matrix), "max_markers": max(row["markers"] for row in matrix)}
    (OUT / "filter_matrix.json").write_text(json.dumps(matrix, ensure_ascii=False, indent=2) + "\n")
    edge = read(page, """async()=>{const a=window.__tripApp;a.state.routes=new Set(['A1']);a.state.date='10/9';a.state.region='yosemite';a.state.selected=null;a.renderDetail(null);a.renderTimeline();await a.drawMap(false);return {markers:document.querySelectorAll('.photo-marker').length,legs:a.visibleRouteFeatures().length,cards:document.querySelectorAll('.map-slot').length}}""")
    report["checks"]["a1_oct9_yosemite"] = edge
    capture(page, "a1_oct9_yosemite")
    widths = {}
    for width in (1440, 1280, 1024, 768, 430, 390):
        page.set_viewport_size({"width": width, "height": 900 if width >= 768 else 844})
        page.wait_for_timeout(300)
        widths[str(width)] = read(page, """()=>({overflow:document.documentElement.scrollWidth-document.documentElement.clientWidth,mapWidth:document.getElementById('map').getBoundingClientRect().width,sidebarVisible:getComputedStyle(document.querySelector('.sidebar')).display!=='none',dateChips:document.querySelectorAll('.day-chip').length})""")
        capture(page, f"responsive_{width}")
    report["checks"]["widths"] = widths
    # Restore the broad view, then exercise the two supported user-facing providers.
    page.set_viewport_size({"width": 1440, "height": 900})
    read(page, """async()=>{const a=window.__tripApp;a.state.routes=new Set(['A1','A2','B1','B2']);a.state.date='all';a.state.region='overall';a.renderTimeline();await a.drawMap(false)}""")
    providers = {}
    for provider in ("satellite", "vector"):
        read(page, f"async()=>await window.__tripApp.chooseProvider('{provider}')")
        page.wait_for_function("window.__tripApp.map().isStyleLoaded()", timeout=15000)
        page.wait_for_timeout(900)
        providers[provider] = read(page, """()=>({active:window.__tripApp.state.provider,health:window.__tripApp.state.providerHealth[window.__tripApp.state.provider],canvas:document.querySelectorAll('.maplibregl-canvas').length,tilesLoaded:window.__tripApp.map().areTilesLoaded()})""")
        capture(page, f"provider_{provider}")
    report["checks"]["providers"] = providers
    report["checks"]["visible_provider_controls"] = read(page, """()=>({desktop:[...document.querySelectorAll('[data-provider]')].map(x=>x.dataset.provider),mobile:[...document.querySelectorAll('#mobileProvider option')].map(x=>x.value),data:Object.keys(window.__tripApp.DATA.providers)})""")
    report["checks"]["console_errors_before_injected_failure"] = report["console_errors"][:]
    report["checks"]["failed_requests_before_injected_failure"] = report["failed_requests"][:]
    page.route("https://**/*", lambda route: route.abort())
    read(page, """async()=>await window.__tripApp.chooseProvider('satellite')""")
    report["checks"]["satellite_initial_failure_fallback"] = read(page, """()=>({active:window.__tripApp.state.provider,satelliteHealth:window.__tripApp.state.providerHealth.satellite,note:document.getElementById('fallbackNote').innerText,canvas:document.querySelectorAll('.maplibregl-canvas').length})""")
    capture(page, "satellite_failure_fallback")
    page.unroute("https://**/*")
    read(page, """async()=>await window.__tripApp.chooseProvider('satellite')""")
    page.wait_for_function("window.__tripApp.state.provider==='satellite'&&window.__tripApp.map().isStyleLoaded()")
    page.route("https://server.arcgisonline.com/**", lambda route: route.abort())
    read(page, """()=>window.__tripApp.map().jumpTo({center:[-122.42,37.78],zoom:12})""")
    page.wait_for_function("window.__tripApp.state.provider==='vector'", timeout=15000)
    report["checks"]["post_success_pan_failure_fallback"] = read(page, """()=>({active:window.__tripApp.state.provider,satelliteHealth:window.__tripApp.state.providerHealth.satellite,canvas:document.querySelectorAll('.maplibregl-canvas').length})""")
    capture(page, "satellite_pan_failure_fallback")
    page.unroute("https://server.arcgisonline.com/**")
    report["checks"]["expected_injected_failure_console"] = report["console_errors"][len(report["checks"]["console_errors_before_injected_failure"]):]
    warning = bounded_cleanup(browser.close, "map-first full Chromium browser")
    if warning:
        report["cleanup_warnings"].append(warning)

    # Chromium touch interaction remains owned here. Firefox/WebKit coverage is
    # decisively owned by the isolated run_cross_browser.py suite.
    touch_browser = playwright.chromium.launch(headless=True, timeout=90000)
    context = touch_browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    touch_page = context.new_page()
    touch_page.set_default_timeout(60000)
    local_errors = []
    touch_page.on("pageerror", lambda error: local_errors.append(str(error)))
    touch_page.goto(URL, wait_until="domcontentloaded", timeout=90000)
    touch_page.wait_for_function("window.__tripApp?.map()?.isStyleLoaded()", timeout=30000)
    touch_page.wait_for_timeout(800)
    touch_page.locator(".photo-cluster").first.click()
    touch_page.wait_for_timeout(700)
    cluster_preview = read(touch_page, """()=>document.getElementById('previewCard').classList.contains('show')""")
    read(touch_page, """()=>window.__tripApp.hidePreview()""")
    clickable = read(touch_page, """()=>[...document.querySelectorAll('.photo-marker')].find(el=>{if(el.style.display==='none')return false;const r=el.getBoundingClientRect(),x=r.left+r.width/2,y=r.top+r.height/2,target=document.elementFromPoint(x,y);return target===el||el.contains(target)})?.dataset.placeKey||null""")
    if not clickable:
        raise AssertionError("No unobscured touch marker after cluster zoom")
    touch_page.locator(f'.photo-marker[data-place-key="{clickable}"]').click()
    touch_page.wait_for_timeout(400)
    touch_preview = read(touch_page, """()=>({visible:document.getElementById('previewCard').classList.contains('show'),photo:document.querySelector('#previewCard .preview-media')?.naturalWidth||0,details:document.querySelectorAll('#detailsPane .photo-grid img').length})""")
    capture(touch_page, "touch_390_preview")
    touch_page.locator("#previewCard .preview-action").click()
    touch_page.wait_for_function("[...document.querySelectorAll('#detailsPane .photo-grid img')].length===3&&[...document.querySelectorAll('#detailsPane .photo-grid img')].every(x=>x.complete&&x.naturalWidth>0)", timeout=15000)
    report["checks"]["touch_390"] = read(touch_page, """()=>({preview:document.getElementById('previewCard').classList.contains('show'),details:document.querySelectorAll('#detailsPane .photo-grid img').length,decoded:[...document.querySelectorAll('#detailsPane .photo-grid img')].every(x=>x.complete&&x.naturalWidth>0),overflow:document.documentElement.scrollWidth-document.documentElement.clientWidth})""")
    report["checks"]["touch_390"]["cluster_preview"] = cluster_preview
    report["checks"]["touch_390"]["marker_preview"] = touch_preview
    capture(touch_page, "touch_390_detail")
    report["errors"].extend(local_errors)
    warning = bounded_cleanup(touch_browser.close, "map-first full Chromium 390px browser")
    if warning:
        report["cleanup_warnings"].append(warning)

checks = report["checks"]
report["status"] = "PASS" if (
    not report["errors"]
    and not checks["console_errors_before_injected_failure"]
    and not checks["matrix"]["failed"]
    and checks["place_detail"]["photos"] == 3
    and checks["place_detail"]["decoded"]
    and checks["dark"]["theme"] == "dark"
    and checks["touch_390"]["decoded"]
    and checks["touch_390"]["marker_preview"]["visible"]
    and checks["touch_390"]["marker_preview"]["photo"] > 0
    and all(check["overflow"] == 0 for check in checks["widths"].values())
    and checks["visible_provider_controls"]["desktop"] == ["vector", "satellite"]
    and checks["visible_provider_controls"]["mobile"] == ["vector", "satellite"]
    and sorted(checks["visible_provider_controls"]["data"]) == ["satellite", "vector"]
    and checks["satellite_initial_failure_fallback"]["active"] == "vector"
    and checks["satellite_initial_failure_fallback"]["satelliteHealth"] == "failed"
    and checks["satellite_initial_failure_fallback"]["canvas"] == 1
    and checks["post_success_pan_failure_fallback"]["active"] == "vector"
    and all(check["active"] == name and check["canvas"] == 1 for name, check in checks["providers"].items())
    and checks["loading_completed"]
    and checks["gap_audit"]["places"] == 36
    and checks["gap_audit"]["photos"] == 108
    and len(checks["gap_audit"]["audited"]) == 8
    and checks["gap_audit"]["routeLayerColors"]
) else "FAIL"
(OUT / "full_acceptance.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"status": report["status"], "initial": report["checks"]["initial"], "matrix_states": report["checks"]["matrix"]["states"], "matrix_failures": len(report["checks"]["matrix"]["failed"]), "providers": report["checks"].get("providers"), "errors": report["errors"], "console_errors": report["console_errors"][:5]}, ensure_ascii=False, indent=2))
