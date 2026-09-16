"""Capture focused route and mobile screenshots for human visual inspection."""

import json
from pathlib import Path

from playwright.sync_api import sync_playwright
from qa_config import MODULAR_URL


ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / "QA/map_first/screenshots"
SHOTS.mkdir(parents=True, exist_ok=True)
ROWS = []

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    for width, height in ((1440, 900), (390, 844)):
        page = browser.new_page(viewport={"width": width, "height": height}, has_touch=width == 390, is_mobile=width == 390)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(MODULAR_URL, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_function("window.__tripApp && document.querySelectorAll('.photo-marker').length===window.__tripApp.DATA.markers.length")
        page.wait_for_function("!document.getElementById('loadingScreen')", timeout=10000)
        for route in ("A1", "A2", "B1", "B2"):
            page.evaluate("""async route=>{const a=window.__tripApp;a.state.routes=new Set([route]);a.state.region='sf';a.state.date='all';a.renderTimeline();await a.drawMap(false)}""", route)
            page.wait_for_function("window.__tripApp.map().getSource('trip-routes')")
            page.wait_for_timeout(250)
            shot = SHOTS / f"visual_{width}_{route}_sf.png"
            page.screenshot(path=str(shot))
            colors = page.evaluate("""()=>{const m=window.__tripApp.map();return [...new Set(m.getSource('trip-routes')._data.features.map(f=>f.properties.color))]}""")
            ROWS.append({"width": width, "route": route, "region": "sf", "colors": colors, "markers": page.locator(".photo-marker").count(), "screenshot": str(shot.relative_to(ROOT)), "errors": list(errors)})
        if width == 390:
            page.locator(".route-guide summary").click()
            shot = SHOTS / "visual_390_route_guide.png"
            page.screenshot(path=str(shot))
            ROWS.append({"width": width, "view": "expanded_route_guide", "screenshot": str(shot.relative_to(ROOT)), "errors": list(errors)})
        page.close()
    browser.close()

report = {"status": "PASS" if len(ROWS) == 9 and all(not row["errors"] for row in ROWS) else "FAIL", "rows": ROWS}
(ROOT / "QA/map_first/visual_spots.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(json.dumps(report, ensure_ascii=False, indent=2))
