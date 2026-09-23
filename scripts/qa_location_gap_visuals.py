"""Focused browser QA for the eight audited location additions and branches."""

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

from qa_config import MODULAR_URL


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "QA" / "CHG-188" / "location_gap"
OUT.mkdir(parents=True, exist_ok=True)
GAPS = ["pier39", "tunnel_tops", "bixby", "ghirardelli", "cable_car", "carmel", "el_capitan", "monterey_wharf"]
report = {"status": "FAIL", "checks": {}, "screenshots": [], "errors": []}
OUT.mkdir(parents=True, exist_ok=True)


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
    report["checks"]["data"] = page.evaluate(
        """keys=>{const a=window.__tripApp;return {places:a.DATA.markers.length,timeline:a.DATA.timeline.length,legs:a.DATA.legs.length,missing:keys.filter(k=>!a.DATA.markers.some(m=>m.place_key===k)),photoStatus:keys.map(k=>a.DATA.markers.find(m=>m.place_key===k)?.photo_status),choiceGroups:[...new Set(a.DATA.timeline.map(t=>t.mutually_exclusive_group).filter(Boolean))]}}""",
        GAPS,
    )
    page.wait_for_function("window.__tripApp?.state?.task?.routes", timeout=15000)
    page.evaluate("""async()=>{const a=window.__tripApp;a.state.routes=new Set(Object.keys(a.DATA.routes));a.state.primaryRoute=Object.keys(a.DATA.routes)[0];a.state.date='10/5';a.state.region='sf';a.state.selected=null;a.setMode('day');await a.drawMap(false)}""")
    report["checks"]["sf_branches"] = page.evaluate("()=>{const a=window.__tripApp,keys=new Set(a.DATA.markers.filter(a.markerVisible).map(x=>x.place_key)),kinds=new Set(a.visibleRouteFeatures().map(x=>x.properties.kind));return {pier39:keys.has('pier39'),kinds:[...kinds]}}")
    capture(page, "gap_1440_sf_decision_surface")
    page.locator(".photo-marker[data-place-key='pier39']").click()
    page.wait_for_selector("#peek.show")
    page.locator("#peek [data-peek-open]").evaluate("element=>element.click()")
    page.wait_for_function("document.querySelectorAll('#placeInspector .photo-slot img').length===3")
    report["checks"]["pier_inspector"] = page.evaluate("()=>({photos:document.querySelectorAll('#placeInspector .photo-slot img').length,why:!!document.querySelector('#placeInspector .place-glance'),rules:document.querySelectorAll('#placeInspector .decision-rule').length})")
    capture(page, "gap_1440_pier39_inspector")
    page.locator("#langToggle").click()
    page.wait_for_function("document.documentElement.lang==='en'")
    report["checks"]["english_inspector"] = page.evaluate("()=>({hangul:document.querySelector('#placeInspector').innerText.split('\\n').filter(x=>/[가-힣]/.test(x))})")
    page.locator("[data-place-back]").click()
    page.locator("#langToggle").click()
    page.evaluate("""async()=>{const a=window.__tripApp,route=Object.keys(a.DATA.routes)[0];a.state.primaryRoute=route;a.state.routes=new Set([route]);a.state.date='10/6';a.state.region='monterey';a.state.selected=null;a.setMode('day');await a.drawMap(false)}""")
    report["checks"]["monterey_branches"] = page.evaluate("()=>{const a=window.__tripApp,keys=new Set(a.DATA.markers.filter(a.markerVisible).map(x=>x.place_key)),route=Object.keys(a.DATA.routes)[0];return {bixby_visible:keys.has('bixby'),bixby_role:a.DATA.route_roles.bixby[route],features:a.visibleRouteFeatures().length,wharf:keys.has('monterey_wharf')}}")
    page.set_viewport_size({"width": 390, "height": 844})
    page.wait_for_timeout(250)
    report["checks"]["mobile"] = page.evaluate("()=>({overflow:document.documentElement.scrollWidth-innerWidth,canvas:document.querySelectorAll('.maplibregl-canvas').length})")
    browser.close()

data = report["checks"]["data"]
report["status"] = "PASS" if not report["errors"] and data["places"] == 36 and data["timeline"] == 51 and data["legs"] == 37 and not data["missing"] and report["checks"]["sf_branches"]["pier39"] and report["checks"]["pier_inspector"]["photos"] == 3 and not report["checks"]["english_inspector"]["hangul"] and not report["checks"]["monterey_branches"]["bixby_visible"] and report["checks"]["monterey_branches"]["bixby_role"] == "Skip" and report["checks"]["monterey_branches"]["wharf"] and report["checks"]["mobile"]["overflow"] == 0 else "FAIL"
(OUT / "location_gap_visuals.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"status": report["status"], "checks": report["checks"], "errors": report["errors"]}, ensure_ascii=False, indent=2))
raise SystemExit(0 if report["status"] == "PASS" else 1)
