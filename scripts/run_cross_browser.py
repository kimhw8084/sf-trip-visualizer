"""Firefox and WebKit real-browser smoke/visual checks."""

import json
from pathlib import Path
from playwright.sync_api import sync_playwright
from qa_config import MODULAR_URL

ROOT = Path(__file__).resolve().parents[1]
URL = MODULAR_URL
shots = ROOT / "QA/map_first/screenshots"
shots.mkdir(parents=True, exist_ok=True)
rows = []
with sync_playwright() as playwright:
    for name in ("firefox", "webkit"):
        browser = getattr(playwright, name).launch(headless=True)
        for width, height in ((1280, 800), (390, 844)):
            context = browser.new_context(viewport={"width": width, "height": height}, has_touch=width == 390, is_mobile=width == 390)
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(URL, wait_until="domcontentloaded", timeout=90000)
            page.wait_for_function("window.__tripApp?.map()?.isStyleLoaded()", timeout=30000)
            page.wait_for_function("document.querySelectorAll('.photo-marker').length===window.__tripApp.DATA.markers.length", timeout=15000)
            row = {
                "browser": name, "width": width,
                "marker_objects": page.locator(".photo-marker").count(),
                "canvas": page.locator(".maplibregl-canvas").count(),
                "horizontal_overflow": page.evaluate("document.documentElement.scrollWidth>innerWidth"),
                "broken_marker_images": page.locator(".photo-marker img").evaluate_all("es=>es.filter(e=>!e.complete||e.naturalWidth===0).length"),
            }
            page.locator("[data-timeline]").first.click()
            page.locator("[data-tab=details]").click()
            page.wait_for_function("[...document.querySelectorAll('#detailsPane .photo-slot img')].length===3&&[...document.querySelectorAll('#detailsPane .photo-slot img')].every(e=>e.complete&&e.naturalWidth>0)", timeout=8000)
            row["detail_photos"] = page.locator("#detailsPane .photo-slot img").count()
            row["page_errors"] = errors
            expected_places = page.evaluate("window.__tripApp.DATA.markers.length")
            row["expected_places"] = expected_places
            row["status"] = "PASS" if row["marker_objects"] == expected_places and row["canvas"] == 1 and not row["horizontal_overflow"] and row["broken_marker_images"] == 0 and row["detail_photos"] == 3 and not errors else "FAIL"
            image = shots / f"{name}_{width}_detail.png"
            page.screenshot(path=str(image))
            row["screenshot"] = str(image.relative_to(ROOT))
            rows.append(row)
            context.close()
        browser.close()
(ROOT / "QA/map_first/cross_browser.json").write_text(json.dumps(rows, indent=2) + "\n")
print(json.dumps(rows, indent=2))
