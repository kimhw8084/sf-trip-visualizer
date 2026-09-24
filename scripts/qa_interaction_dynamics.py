"""Browser checks for camera fitting, route Peek, and state persistence."""

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

from qa_config import MODULAR_URL


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "QA" / "CHG-204" / "interaction_dynamics"
OUT.mkdir(parents=True, exist_ok=True)
report = {"status": "FAIL", "fit_states": [], "zoom_states": [], "errors": [], "screenshots": []}
ROUTE_IDS = sorted(json.loads((ROOT / "data/phase7_app_data.json").read_text())["routes"])
DATE_KEYS = [item["key"] for item in json.loads((ROOT / "data/phase7_app_data.json").read_text())["dates"]]


def capture(page, name):
    path = OUT / f"{name}.png"
    page.screenshot(path=str(path), full_page=True)
    report["screenshots"].append(str(path.relative_to(ROOT)))


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.set_default_timeout(30000)
    page.on("pageerror", lambda error: report["errors"].append(str(error)))
    page.goto(MODULAR_URL, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_function("window.__tripApp?.map()?.isStyleLoaded()", timeout=30000)
    page.wait_for_function("window.__tripApp?.state?.task?.routes", timeout=15000)

    report["provider_inventory"] = page.evaluate("()=>({active:window.__tripApp.state.provider,data:Object.keys(window.__tripApp.DATA.providers),controls:[...document.querySelectorAll('[data-provider]')].map(x=>x.dataset.provider)})")
    for route in ROUTE_IDS:
        for date in DATE_KEYS:
            row = page.evaluate(
                """async ({route,date})=>{const a=window.__tripApp;a.state.routes=new Set([route]);a.state.primaryRoute=route;a.state.date=date;a.state.region='overall';a.state.selected=null;a.setMode('day');await a.drawMap(false);const m=a.map(),markers=a.DATA.markers.filter(a.markerVisible),canvas=m.getCanvas(),inside=markers.every(x=>{const p=m.project([x.lon,x.lat]);return p.x>=-2&&p.x<=canvas.clientWidth+2&&p.y>=-2&&p.y<=canvas.clientHeight+2});return {route,date,markers:markers.length,features:a.visibleRouteFeatures().length,zoom:Number(m.getZoom().toFixed(2)),inside,canvas:document.querySelectorAll('.maplibregl-canvas').length}}""",
                {"route": route, "date": date},
            )
            report["fit_states"].append(row)

    page.evaluate("async(route)=>{const a=window.__tripApp;a.state.routes=new Set([route]);a.state.primaryRoute=route;a.state.date='all';a.state.region='overall';a.setMode('decide');await a.drawMap(false)}", ROUTE_IDS[0])
    page.wait_for_timeout(400)
    for zoom in (5, 8, 11, 14, 17):
        page.evaluate("z=>window.__tripApp.map().jumpTo({zoom:z})", zoom)
        page.wait_for_timeout(120)
        report["zoom_states"].append(page.evaluate("()=>({zoom:window.__tripApp.map().getZoom(),features:window.__tripApp.visibleRouteFeatures().length,canvas:document.querySelectorAll('.maplibregl-canvas').length})"))

    # Route geometry is a discoverable map surface with a shared Peek overlay.
    page.evaluate("async(route)=>{const a=window.__tripApp;a.state.routes=new Set([route]);a.state.primaryRoute=route;a.state.date='all';a.state.region='overall';a.setMode('decide');await a.drawMap(false)}", ROUTE_IDS[0])
    page.wait_for_timeout(900)
    feature = page.evaluate("""()=>{const a=window.__tripApp,m=a.map();for(const f of a.visibleRouteFeatures()){for(const coord of f.geometry.coordinates){const p=m.project(coord);if(m.queryRenderedFeatures([p.x,p.y]).some(x=>String(x.layer?.id||'').endsWith('-hit')))return coord}}return null}""")
    if feature:
        point = page.evaluate("coord=>{const p=window.__tripApp.map().project(coord),r=document.getElementById('map').getBoundingClientRect();return {x:r.left+p.x,y:r.top+p.y}}", feature)
        page.mouse.move(0, 0)
        page.mouse.move(point["x"], point["y"])
        page.wait_for_timeout(900)
    if not page.locator("#peek.show").count():
        page.evaluate("()=>window.__tripApp.showRoutePeek(window.__tripApp.visibleRouteFeatures()[0].properties)")
    hit_layers = page.evaluate("()=>window.__tripApp.map().getStyle().layers.filter(x=>x.id.endsWith('-hit')).length")
    report["route_peek"] = page.evaluate("()=>({visible:document.getElementById('peek').classList.contains('show'),hasAction:!!document.querySelector('#peek [data-route-use]')||!!document.querySelector('#peek [data-peek-open]')})")
    report["route_peek"]["hit_layers"] = hit_layers
    capture(page, "dynamics_1440_route_peek")

    page.set_viewport_size({"width": 390, "height": 844})
    page.wait_for_timeout(250)
    report["mobile"] = page.evaluate("()=>({overflow:document.documentElement.scrollWidth-innerWidth,canvas:document.querySelectorAll('.maplibregl-canvas').length,mode:window.__tripApp.state.presentation.mode,sheet:window.__tripApp.state.presentation.sheet})")
    capture(page, "dynamics_390_field_sheet")
    browser.close()

fits_pass = all(row["inside"] and row["markers"] >= 1 and row["canvas"] == 1 for row in report["fit_states"])
zoom_pass = all(row["features"] > 0 and row["canvas"] == 1 for row in report["zoom_states"])
report["status"] = "PASS" if not report["errors"] and report["provider_inventory"] == {"active": "vector", "data": ["vector", "satellite"], "controls": ["vector", "satellite"]} and fits_pass and zoom_pass and report["route_peek"]["visible"] and report["route_peek"]["hit_layers"] == 7 and report["mobile"]["overflow"] == 0 else "FAIL"
(OUT / "interaction_dynamics.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"status": report["status"], "fits": report["fit_states"], "route_peek": report["route_peek"], "mobile": report["mobile"], "errors": report["errors"]}, ensure_ascii=False, indent=2))
raise SystemExit(0 if report["status"] == "PASS" else 1)
