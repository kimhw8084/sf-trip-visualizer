"""Focused real-browser QA for the eight location-audit additions and their route branches."""

import json
from pathlib import Path

from playwright.sync_api import sync_playwright
from qa_config import MODULAR_URL
from qa_loading import wait_for_application_ready


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "QA/map_first"
URL = MODULAR_URL
GAPS = ["pier39", "tunnel_tops", "bixby", "ghirardelli", "cable_car", "carmel", "el_capitan", "monterey_wharf"]
report = {"checks": {}, "screenshots": [], "errors": []}


def capture(page, name):
    path = OUT / f"{name}.png"
    page.screenshot(path=str(path), full_page=True)
    report["screenshots"].append(str(path.relative_to(ROOT)))


def set_view(page, *, routes, date, region, panel_hidden=False):
    page.evaluate(
        """async cfg=>{const a=window.__tripApp;a.state.routes=new Set(cfg.routes);a.state.date=cfg.date;a.state.region=cfg.region;a.state.selected=null;a.renderDetail(null);a.renderTimeline();await a.drawMap(false);const app=document.getElementById('app');app.classList.toggle('panel-hidden',cfg.panelHidden);a.map().resize()}""",
        {"routes": routes, "date": date, "region": region, "panelHidden": panel_hidden},
    )
    page.wait_for_timeout(500)


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.on("pageerror", lambda error: report["errors"].append(str(error)))
    page.goto(URL, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_function("window.__tripApp?.map()?.isStyleLoaded()", timeout=30000)
    wait_for_application_ready(page, timeout=30000)

    report["checks"]["data"] = page.evaluate(
        """keys=>{const a=window.__tripApp;return {places:a.DATA.markers.length,timeline:a.DATA.timeline.length,legs:a.DATA.legs.length,missing:keys.filter(k=>!a.DATA.markers.some(m=>m.place_key===k)),photoStatus:keys.map(k=>a.DATA.markers.find(m=>m.place_key===k)?.photo_status),choiceGroups:[...new Set(a.DATA.timeline.map(t=>t.mutually_exclusive_group).filter(Boolean))]}}""",
        GAPS,
    )

    set_view(page, routes=["A1", "A2", "B1", "B2"], date="10/5", region="sf", panel_hidden=True)
    report["checks"]["sf_routes"] = page.evaluate(
        """()=>{const a=window.__tripApp,m=a.map(),features=a.visibleRouteFeatures();return {markers:[...document.querySelectorAll('.photo-marker')].map(x=>x.dataset.placeKey),features:features.length,kinds:[...new Set(features.map(f=>f.properties.kind))].sort(),colors:[...new Set(features.map(f=>f.properties.color))].sort(),schedule:[...document.querySelectorAll('.map-slot')].map(x=>x.innerText)}}"""
    )
    capture(page, "gap_1440_oct5_sf_all_routes_map_only")

    set_view(page, routes=["A1"], date="10/5", region="sf", panel_hidden=True)
    page.evaluate("()=>window.__tripApp.map().jumpTo({center:[-122.414,37.805],zoom:13.1})")
    page.wait_for_timeout(450)
    page.locator(".photo-marker[data-place-key='pier39']").hover()
    page.wait_for_timeout(250)
    report["checks"]["pier_hover"] = page.evaluate(
        """()=>({visible:document.getElementById('previewCard').classList.contains('show'),photo:document.querySelector('#previewCard .preview-media')?.naturalWidth||0,text:document.getElementById('previewCard').innerText})"""
    )
    capture(page, "gap_1440_pier39_hover")
    page.evaluate("()=>window.__tripApp.selectPlace('pier39',{focus:false,openDetails:true})")
    page.wait_for_function("[...document.querySelectorAll('#detailsPane .photo-slot img')].every(x=>x.complete&&x.naturalWidth>0)")
    report["checks"]["pier_detail_ko"] = page.evaluate(
        """()=>({title:document.querySelector('#detailsPane h2')?.innerText,subtitle:document.querySelector('#detailsPane .place-korean')?.innerText,photos:document.querySelectorAll('#detailsPane .photo-slot img').length,timing:document.querySelector('#detailsPane .detail-glance')?.innerText,rules:document.querySelectorAll('#detailsPane .decision').length,audit:document.querySelectorAll('#detailsPane .audit-note').length})"""
    )
    capture(page, "gap_1440_pier39_detail_ko")

    page.locator("#langToggle").click()
    page.wait_for_function("document.documentElement.lang==='en'")
    report["checks"]["pier_detail_en"] = page.evaluate(
        """()=>({hangul:document.getElementById('detailsPane').innerText.split('\\n').filter(x=>/[가-힣]/.test(x)),text:document.getElementById('detailsPane').innerText.slice(0,1000)})"""
    )
    capture(page, "gap_1440_pier39_detail_en")

    page.locator("#langToggle").click()
    set_view(page, routes=["A1", "A2", "B1", "B2"], date="10/6", region="monterey", panel_hidden=True)
    report["checks"]["monterey_routes"] = page.evaluate(
        """()=>{const a=window.__tripApp;return {markers:[...document.querySelectorAll('.photo-marker')].map(x=>x.dataset.placeKey),features:a.visibleRouteFeatures().map(x=>({kind:x.properties.kind,leg:x.properties.leg_id,color:x.properties.color})),choiceWarnings:document.querySelectorAll('.choice-warning').length}}"""
    )
    capture(page, "gap_1440_oct6_monterey_routes")

    set_view(page, routes=["A1"], date="10/7", region="yosemite", panel_hidden=True)
    capture(page, "gap_1440_oct7_el_capitan_route")

    for width in (430, 390):
        page.set_viewport_size({"width": width, "height": 844})
        set_view(page, routes=["A1"], date="10/5", region="sf", panel_hidden=True)
        page.evaluate("()=>window.__tripApp.map().jumpTo({center:[-122.414,37.805],zoom:13.1})")
        page.wait_for_timeout(450)
        page.locator(".photo-marker[data-place-key='pier39']").click()
        page.wait_for_timeout(250)
        preview_state = page.evaluate(
            """()=>({overflow:document.documentElement.scrollWidth-innerWidth,preview:document.getElementById('previewCard').classList.contains('show'),photo:document.querySelector('#previewCard .preview-media')?.naturalWidth||0,selected:window.__tripApp.state.selected,details:document.querySelectorAll('#detailsPane .photo-slot img').length,schedule:document.querySelectorAll('.map-slot').length,canvas:document.querySelectorAll('.maplibregl-canvas').length})"""
        )
        capture(page, f"gap_{width}_pier39_tap")
        page.locator("#previewCard .preview-action").click()
        page.wait_for_function("[...document.querySelectorAll('#detailsPane .photo-slot img')].length===3&&[...document.querySelectorAll('#detailsPane .photo-slot img')].every(x=>x.complete&&x.naturalWidth>0)", timeout=15000)
        report["checks"][f"mobile_{width}"] = page.evaluate(
            """preview=>({...preview,selected:window.__tripApp.state.selected,details:document.querySelectorAll('#detailsPane .photo-slot img').length,detailsVisible:document.getElementById('detailsPane').classList.contains('active')})""",
            preview_state,
        )
        page.evaluate("()=>window.__tripApp.hidePreview()")

    browser.close()


checks = report["checks"]
report["status"] = "PASS" if (
    not report["errors"]
    and checks["data"]["places"] == 36
    and checks["data"]["timeline"] == 79
    and checks["data"]["legs"] == 41
    and not checks["data"]["missing"]
    and {"sf_afternoon_icon", "monterey_scenic"}.issubset(set(checks["data"]["choiceGroups"]))
    and checks["pier_hover"]["visible"] and checks["pier_hover"]["photo"] > 0
    and checks["pier_detail_ko"]["photos"] == 3 and checks["pier_detail_ko"]["rules"] >= 1
    and not checks["pier_detail_en"]["hangul"]
    and "pier39" in checks["sf_routes"]["markers"]
    and "bixby" in checks["monterey_routes"]["markers"]
    and all(checks[f"mobile_{width}"]["overflow"] == 0 and checks[f"mobile_{width}"]["photo"] > 0 and checks[f"mobile_{width}"]["selected"] == "pier39" and checks[f"mobile_{width}"]["details"] == 3 for width in (430, 390))
) else "FAIL"
(OUT / "location_gap_visuals.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"status": report["status"], "data": checks["data"], "sf": checks["sf_routes"], "mobile": {w: checks[f"mobile_{w}"] for w in (430, 390)}, "errors": report["errors"]}, ensure_ascii=False, indent=2))
