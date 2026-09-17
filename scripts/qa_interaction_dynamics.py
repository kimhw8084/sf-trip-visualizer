"""Real-browser checks for Smart-map persistence, date fitting, routes, and tooltips."""

import json
from pathlib import Path

from playwright.sync_api import sync_playwright
from qa_config import MODULAR_URL


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "QA/map_first"
URL = MODULAR_URL
report = {"status": "FAIL", "date_route_fits": [], "zoom_states": [], "errors": [], "screenshots": []}


def capture(page, name):
    path = OUT / f"{name}.png"
    page.screenshot(path=str(path), full_page=True)
    report["screenshots"].append(str(path.relative_to(ROOT)))


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.on("pageerror", lambda error: report["errors"].append(str(error)))
    page.goto(URL, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_function("window.__tripApp?.map()?.isStyleLoaded()", timeout=30000)
    page.wait_for_function("!document.getElementById('loadingScreen')", timeout=10000)

    report["provider_inventory"] = page.evaluate(
        """()=>({active:window.__tripApp.state.provider,data:Object.keys(window.__tripApp.DATA.providers),desktop:[...document.querySelectorAll('[data-provider]')].map(x=>x.dataset.provider),mobile:[...document.querySelectorAll('#mobileProvider option')].map(x=>x.value)})"""
    )

    report["date_route_fits"] = page.evaluate(
        """async()=>{const a=window.__tripApp,rows=[];for(const route of Object.keys(a.DATA.routes))for(const date of a.DATA.dates.map(x=>x.key)){a.state.routes=new Set([route]);a.state.date=date;a.state.region='overall';a.state.selected=null;a.renderTimeline();a.renderDetail(null);await a.drawMap(false);const m=a.map(),canvas=m.getCanvas(),visible=a.DATA.markers.filter(a.markerVisible),points=visible.map(x=>m.project([x.lon,x.lat])),routePoints=a.visibleRouteFeatures().filter(f=>f.properties.kind!=='transfer').flatMap(f=>f.geometry.coordinates).map(c=>m.project(c)),regions=new Set(visible.map(x=>a.DATA.place_region[x.place_key])),inFrame=p=>p.x>=-1&&p.y>=-1&&p.x<=canvas.clientWidth+1&&p.y<=canvas.clientHeight+1,inside=points.every(inFrame),routeInside=routePoints.every(inFrame),focusedEnough=visible.length<=1||regions.size!==1||m.getZoom()>=8.5;rows.push({route,date,markers:visible.length,regions:[...regions],zoom:Number(m.getZoom().toFixed(2)),inside,routeInside,focusedEnough,provider:a.state.provider,routeFeatures:a.visibleRouteFeatures().length})}return rows}"""
    )

    page.evaluate(
        """async()=>{const a=window.__tripApp;a.state.routes=new Set(Object.keys(a.DATA.routes));a.state.date='10/8';a.state.region='overall';a.state.selected=null;a.renderTimeline();a.renderDetail(null);await a.drawMap(false)}"""
    )
    report["thursday_fit"] = page.evaluate(
        """()=>{const a=window.__tripApp,m=a.map(),visible=a.DATA.markers.filter(a.markerVisible);return {provider:a.state.provider,zoom:Number(m.getZoom().toFixed(2)),markers:visible.map(x=>x.place_key),legs:[...new Set(a.visibleRouteFeatures().map(x=>x.properties.leg_id))],schedule:[...document.querySelectorAll('.map-slot')].map(x=>x.innerText),legend:[...document.querySelectorAll('.map-route-row')].map(x=>x.innerText)}}"""
    )
    capture(page, "dynamics_1440_thursday_fit")

    report["route_layer_bounds"] = page.evaluate(
        """()=>{const m=window.__tripApp.map();return m.getStyle().layers.filter(x=>x.id.startsWith('trip-')&&!x.id.endsWith('-hit')&&!x.id.endsWith('-casing')).map(x=>({id:x.id,minzoom:x.minzoom??0,maxzoom:x.maxzoom??24,color:m.getPaintProperty(x.id,'line-color')}))}"""
    )
    for zoom in (3, 5, 8, 10, 12, 15, 18):
        page.evaluate("""z=>{const a=window.__tripApp,f=a.visibleRouteFeatures().find(x=>x.properties.leg_id==='UX_1008_OUT'),c=f.geometry.coordinates[Math.floor(f.geometry.coordinates.length*.5)];a.map().jumpTo({center:c,zoom:z})}""", zoom)
        page.wait_for_timeout(180)
        report["zoom_states"].append(page.evaluate(
            """()=>{const a=window.__tripApp,m=a.map(),layers=['trip-local-A1','trip-conditional-A1','trip-recovery-A1'];return {zoom:Number(m.getZoom().toFixed(2)),provider:a.state.provider,features:a.visibleRouteFeatures().length,rendered:m.queryRenderedFeatures({layers}).length,canvas:document.querySelectorAll('.maplibregl-canvas').length}}"""
        ))

    box = page.locator("#map").bounding_box()
    page.mouse.move(box["x"] + box["width"] * 0.55, box["y"] + box["height"] * 0.48)
    page.mouse.down()
    page.mouse.move(box["x"] + box["width"] * 0.66, box["y"] + box["height"] * 0.58, steps=8)
    page.mouse.up()
    page.mouse.wheel(0, -620)
    page.wait_for_timeout(500)
    report["after_real_pan_zoom"] = page.evaluate(
        """()=>({provider:window.__tripApp.state.provider,zoom:Number(window.__tripApp.map().getZoom().toFixed(2)),features:window.__tripApp.visibleRouteFeatures().length,canvas:document.querySelectorAll('.maplibregl-canvas').length})"""
    )

    page.evaluate("()=>window.__tripApp.fitVisibleMap(window.__tripApp.map())")
    page.wait_for_timeout(250)
    point = page.evaluate(
        """()=>{const f=window.__tripApp.visibleRouteFeatures().find(x=>x.properties.leg_id==='UX_1008_OUT'),c=f.geometry.coordinates[Math.floor(f.geometry.coordinates.length*.5)],p=window.__tripApp.map().project(c),r=document.getElementById('map').getBoundingClientRect();return {x:r.left+p.x,y:r.top+p.y}}"""
    )
    page.mouse.move(point["x"], point["y"])
    page.wait_for_timeout(350)
    report["route_tooltip"] = page.evaluate(
        """()=>({visible:document.getElementById('routeTip').classList.contains('show'),text:document.getElementById('routeTip').innerText})"""
    )
    capture(page, "dynamics_1440_thursday_route_tooltip")

    page.evaluate(
        """async()=>{const a=window.__tripApp;a.state.date='10/4';a.state.region='overall';a.state.selected=null;a.hidePreview();document.getElementById('routeTip').classList.remove('show');a.renderTimeline();a.renderDetail(null);await a.drawMap(false)}"""
    )
    page.wait_for_function("window.__tripApp.map().areTilesLoaded()", timeout=15000)
    page.wait_for_timeout(150)
    capture(page, "dynamics_1440_sunday_connected")

    page.set_viewport_size({"width": 390, "height": 844})
    page.evaluate(
        """async()=>{const a=window.__tripApp;a.state.date='10/8';a.state.region='overall';await a.drawMap(false)}"""
    )
    page.wait_for_function("window.__tripApp.map().areTilesLoaded()", timeout=15000)
    page.wait_for_timeout(350)
    report["mobile_thursday"] = page.evaluate(
        """()=>({provider:window.__tripApp.state.provider,zoom:Number(window.__tripApp.map().getZoom().toFixed(2)),overflow:document.documentElement.scrollWidth-innerWidth,markers:[...document.querySelectorAll('.photo-marker')].map(x=>x.dataset.placeKey),schedule:document.querySelectorAll('.map-slot').length,legend:document.querySelectorAll('.map-route-row').length})"""
    )
    capture(page, "dynamics_390_thursday_fit")
    browser.close()


fits_pass = all(row["inside"] and row["routeInside"] and row["focusedEnough"] and row["provider"] == "vector" for row in report["date_route_fits"])
layers_pass = bool(report["route_layer_bounds"]) and all(row["minzoom"] == 0 and row["maxzoom"] >= 18 for row in report["route_layer_bounds"])
zoom_pass = all(row["provider"] == "vector" and row["features"] > 0 and row["rendered"] > 0 and row["canvas"] == 1 for row in report["zoom_states"])
report["status"] = "PASS" if (
    not report["errors"]
    and report["provider_inventory"] == {"active": "vector", "data": ["vector", "satellite"], "desktop": ["vector", "satellite"], "mobile": ["vector", "satellite"]}
    and fits_pass and layers_pass and zoom_pass
    and report["thursday_fit"]["markers"] == ["cooks", "washburn", "glacier"]
    and set(report["thursday_fit"]["legs"]) == {"UX_1008_OUT", "C_1008_01", "UX_1008_RETURN"}
    and report["after_real_pan_zoom"]["provider"] == "vector"
    and report["after_real_pan_zoom"]["canvas"] == 1
    and report["route_tooltip"]["visible"]
    and report["mobile_thursday"]["provider"] == "vector"
    and report["mobile_thursday"]["overflow"] == 0
) else "FAIL"
(OUT / "interaction_dynamics.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"status": report["status"], "fit_failures": [row for row in report["date_route_fits"] if not row["inside"] or not row["routeInside"] or not row["focusedEnough"] or row["provider"] != "vector"], "thursday": report["thursday_fit"], "zoom_states": report["zoom_states"], "tooltip": report["route_tooltip"], "errors": report["errors"]}, ensure_ascii=False, indent=2))
raise SystemExit(0 if report["status"] == "PASS" else 1)
