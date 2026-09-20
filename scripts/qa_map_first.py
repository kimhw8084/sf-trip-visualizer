"""Fast smoke for the maintained Decide → Day → Place modular artifact."""

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

from qa_config import MODULAR_URL


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "QA" / "map_first"
OUT.mkdir(parents=True, exist_ok=True)
report = {"status": "FAIL", "errors": [], "failed_requests": []}


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.on("pageerror", lambda error: report["errors"].append(str(error)))
    page.on("requestfailed", lambda request: report["failed_requests"].append(request.url))
    page.goto(MODULAR_URL, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_function("window.__tripApp?.map()?.isStyleLoaded()", timeout=30000)
    page.wait_for_function("document.querySelectorAll('.photo-marker').length===window.__tripApp.DATA.markers.length", timeout=15000)
    report["state"] = page.evaluate("()=>({app:!!window.__tripApp,provider:window.__tripApp.state.provider,health:window.__tripApp.state.providerHealth,theme:document.documentElement.dataset.theme,lang:document.documentElement.lang,canvas:document.querySelectorAll('.maplibregl-canvas').length,markers:document.querySelectorAll('.photo-marker').length,places:window.__tripApp.DATA.markers.length,features:window.__tripApp.visibleRouteFeatures().length,recommendation:document.querySelector('#recommendation')?.innerText.slice(0,180),date_controls:document.querySelectorAll('#dateSelect').length,legacy:document.querySelectorAll('#dateRibbon,#mapSchedule,#mapFocus,#routeTip,#mobileDate,#mobileProvider,#previewCard,#detailsPane').length})")
    page.screenshot(path=str(OUT / "smoke_1440.png"), full_page=True)
    browser.close()

state = report["state"]
report["status"] = "PASS" if not report["errors"] and not report["failed_requests"] and state["app"] and state["provider"] == "vector" and state["health"]["vector"] == "ready" and state["canvas"] == 1 and state["markers"] == state["places"] == 36 and state["features"] > 0 and state["date_controls"] == 1 and state["legacy"] == 0 and "A1" in state["recommendation"] else "FAIL"
(OUT / "smoke.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(json.dumps(report, ensure_ascii=False, indent=2))
raise SystemExit(0 if report["status"] == "PASS" else 1)
