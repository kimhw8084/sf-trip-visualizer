"""Fast smoke for the maintained Decide → Day → Place modular artifact."""

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

from qa_config import MODULAR_URL
from qa_evidence import bind_report, candidate_identity


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "QA" / "CHG-204" / "map_first_smoke"
OUT.mkdir(parents=True, exist_ok=True)
identity = candidate_identity()
SOURCE_DATA = json.loads((ROOT / "data/phase7_app_data.json").read_text())
expected_routes = sorted(SOURCE_DATA["routes"])
expected_places = len(SOURCE_DATA["markers"])
expected_route_markers = sum(bool(set(marker.get("routes", [])) & set(expected_routes)) for marker in SOURCE_DATA["markers"])
report = bind_report({"status": "FAIL", "errors": [], "failed_requests": []}, identity)


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.on("pageerror", lambda error: report["errors"].append(str(error)))
    page.on("requestfailed", lambda request: report["failed_requests"].append(request.url))
    page.goto(MODULAR_URL, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_function("window.__tripApp?.map()?.isStyleLoaded()", timeout=30000)
    page.wait_for_function("document.querySelectorAll('.photo-marker').length===window.__tripApp.DATA.markers.filter(window.__tripApp.markerVisible).length", timeout=15000)
    report["state"] = page.evaluate("()=>({app:!!window.__tripApp,routes:Object.keys(window.__tripApp.DATA.routes),provider:window.__tripApp.state.provider,health:window.__tripApp.state.providerHealth,theme:document.documentElement.dataset.theme,lang:document.documentElement.lang,canvas:document.querySelectorAll('.maplibregl-canvas').length,markers:document.querySelectorAll('.photo-marker').length,places:window.__tripApp.DATA.markers.length,features:window.__tripApp.visibleRouteFeatures().length,recommendation:document.querySelector('#recommendation')?.innerText.slice(0,180),date_controls:document.querySelectorAll('#dateSelect').length,legacy:document.querySelectorAll('#dateRibbon,#mapSchedule,#mapFocus,#routeTip,#mobileDate,#mobileProvider,#previewCard,#detailsPane').length})")
    page.screenshot(path=str(OUT / "smoke_1440.png"), full_page=True)
    browser.close()

state = report["state"]
report["expected_counts"] = {"active_route_markers": expected_route_markers, "catalog_places": expected_places}
report["status"] = "PASS" if not report["errors"] and not report["failed_requests"] and state["app"] and state["routes"] == expected_routes and state["provider"] == "vector" and state["health"]["vector"] == "ready" and state["canvas"] == 1 and state["markers"] == expected_route_markers and state["places"] == expected_places and state["features"] > 0 and state["date_controls"] == 1 and state["legacy"] == 0 and expected_routes[0] in state["recommendation"] else "FAIL"
(OUT / "smoke.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(json.dumps(report, ensure_ascii=False, indent=2))
raise SystemExit(0 if report["status"] == "PASS" else 1)
