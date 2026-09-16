"""Real-browser QA for route explanations and the adaptive itinerary panel."""

import json
from pathlib import Path

from playwright.sync_api import sync_playwright
from qa_config import MODULAR_URL


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "QA" / "route_panel"
OUT.mkdir(parents=True, exist_ok=True)
URL = MODULAR_URL
ROUTES = ("A1", "A2", "B1", "B2")
report = {"status": "FAIL", "url": URL, "route_explanations": [], "route_repair": {}, "desktop": {}, "mobile": {}, "errors": []}


def snapshot(page, name):
    path = OUT / f"{name}.png"
    page.screenshot(path=str(path), full_page=True)
    return str(path.relative_to(ROOT))


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.on("pageerror", lambda error: report["errors"].append(str(error)))
    page.goto(URL, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_function("window.__tripApp?.map()?.isStyleLoaded()", timeout=30000)
    page.wait_for_function("!document.getElementById('loadingScreen')", timeout=10000)

    for route in ROUTES:
        button = page.locator(f'[data-route-info="{route}"]')
        button.click()
        state = page.evaluate(
            """route=>{const tip=document.getElementById('routeExplain');return {route,visible:tip.classList.contains('show'),expanded:document.querySelector(`[data-route-info="${route}"]`).getAttribute('aria-expanded'),text:tip.innerText,items:tip.querySelectorAll('.route-explain-item').length,scores:tip.querySelectorAll('.route-explain-score span').length}}""",
            route,
        )
        report["route_explanations"].append(state)
        if route == "A1":
            report["desktop"]["tooltip_screenshot"] = snapshot(page, "route_a1_explanation_1440_ko")
        page.locator("#routeExplain .route-explain-close").click()

    before = page.locator(".sidebar").bounding_box()["width"]
    page.locator("#panelLarger").click()
    page.wait_for_timeout(150)
    after_larger = page.locator(".sidebar").bounding_box()["width"]
    page.locator("#panelSmaller").click()
    page.wait_for_timeout(150)
    after_smaller = page.locator(".sidebar").bounding_box()["width"]
    splitter = page.locator("#panelResizer").bounding_box()
    page.mouse.move(splitter["x"] + splitter["width"] / 2, splitter["y"] + splitter["height"] / 2)
    page.mouse.down()
    page.mouse.move(splitter["x"] - 70, splitter["y"] + splitter["height"] / 2, steps=8)
    page.mouse.up()
    page.wait_for_timeout(150)
    after_drag = page.locator(".sidebar").bounding_box()["width"]
    page.locator("#panelClose").click()
    hidden = page.evaluate("document.getElementById('app').classList.contains('panel-hidden')")
    reopen_visible = page.locator("#panelReopen").is_visible()
    page.locator("#panelReopen").click()
    reopened = page.locator(".sidebar").is_visible()
    report["desktop"].update({"before": before, "after_larger": after_larger, "after_smaller": after_smaller, "after_drag": after_drag, "hidden": hidden, "reopen_visible": reopen_visible, "reopened": reopened, "resized_screenshot": snapshot(page, "panel_resized_1440")})

    page.evaluate("""async()=>{const a=window.__tripApp;a.state.routes=new Set(['B1']);a.state.date='10/7';a.state.region='yosemite';a.state.selected=null;a.renderTimeline();a.renderDetail(null);await a.drawMap(false)}""")
    page.wait_for_function("window.__tripApp.map().areTilesLoaded()", timeout=15000)
    page.locator("#panelToggle").click()
    report["route_repair"] = page.evaluate("""()=>{const a=window.__tripApp;return {markers:[...document.querySelectorAll('.photo-marker')].map(x=>x.dataset.placeKey),legs:[...new Set(a.visibleRouteFeatures().map(x=>x.properties.leg_id))],timeline:[...document.querySelectorAll('[data-timeline]')].map(x=>x.innerText),features:a.visibleRouteFeatures().length}}""")
    report["route_repair"]["screenshot"] = snapshot(page, "b1_oct7_arrival_overlooks_1440")
    page.locator("#panelReopen").click()

    page.locator("#langToggle").click()
    page.locator('[data-route-info="B1"]').click()
    report["desktop"]["english_tooltip"] = page.evaluate("document.getElementById('routeExplain').innerText")
    report["desktop"]["english_tooltip_screenshot"] = snapshot(page, "route_b1_explanation_1440_en")
    page.locator("#routeExplain .route-explain-close").click()

    for width in (430, 390):
        page.set_viewport_size({"width": width, "height": 844})
        page.wait_for_timeout(250)
        initial = page.locator(".sidebar").bounding_box()["height"]
        page.locator("#panelLarger").click()
        page.wait_for_timeout(150)
        larger = page.locator(".sidebar").bounding_box()["height"]
        page.locator("#panelSmaller").click()
        page.wait_for_timeout(150)
        smaller = page.locator(".sidebar").bounding_box()["height"]
        page.locator("#panelClose").click()
        map_hidden_panel_height = page.locator("#map").bounding_box()["height"]
        reopen = page.locator("#panelReopen").is_visible()
        page.locator("#panelReopen").click()
        overflow = page.evaluate("document.documentElement.scrollWidth-document.documentElement.clientWidth")
        screenshot = snapshot(page, f"panel_mobile_{width}")
        report["mobile"][str(width)] = {"initial": initial, "larger": larger, "smaller": smaller, "map_when_hidden": map_hidden_panel_height, "reopen_visible": reopen, "overflow": overflow, "screenshot": screenshot}

    browser.close()


routes_pass = len(report["route_explanations"]) == 4 and all(
    row["visible"] and row["expanded"] == "true" and row["items"] == 4 and row["scores"] == 7
    for row in report["route_explanations"]
)
desktop = report["desktop"]
desktop_pass = desktop["after_larger"] > desktop["before"] and abs(desktop["after_smaller"] - desktop["before"]) <= 2 and desktop["after_drag"] > desktop["after_smaller"] and desktop["hidden"] and desktop["reopen_visible"] and desktop["reopened"]
mobile_pass = all(row["larger"] > row["initial"] and abs(row["smaller"] - row["initial"]) <= 2 and row["reopen_visible"] and row["overflow"] == 0 for row in report["mobile"].values())
english_text = desktop["english_tooltip"].lower()
english_pass = all(label in english_text for label in ("best for", "trade-off", "choose / switch rule", "regret guard"))
repair = report["route_repair"]
repair_pass = {"cooks", "el_capitan", "tunnel_view", "valley_view"}.issubset(set(repair["markers"])) and {"GAP_1007_02", "GAP_1007_03"}.issubset(set(repair["legs"])) and repair["features"] > 0
report["status"] = "PASS" if not report["errors"] and routes_pass and desktop_pass and mobile_pass and english_pass and repair_pass else "FAIL"
(OUT / "route_explanations_panel.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(json.dumps(report, ensure_ascii=False, indent=2))
raise SystemExit(0 if report["status"] == "PASS" else 1)
