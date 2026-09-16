"""Firefox and WebKit real-browser smoke/visual checks."""

import json
from pathlib import Path

from playwright.sync_api import sync_playwright
from qa_cleanup import bounded_cleanup
from qa_config import MODULAR_URL

ROOT = Path(__file__).resolve().parents[1]
URL = MODULAR_URL
OUTPUT = ROOT / "QA/map_first/cross_browser.json"
shots = ROOT / "QA/map_first/screenshots"
shots.mkdir(parents=True, exist_ok=True)
rows = []
evidence = {
    "schema_version": 1,
    "status": "RUNNING",
    "expected_rows": 4,
    "rows": rows,
    "cleanup_warnings": [],
    "errors": [],
}


def persist() -> None:
    evidence["rows"] = rows
    OUTPUT.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")


persist()
playwright = sync_playwright().start()
try:
    for name in ("firefox", "webkit"):
        browser = None
        try:
            browser = getattr(playwright, name).launch(headless=True, timeout=90000)
            for width, height in ((1280, 800), (390, 844)):
                context = None
                try:
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
                    # Assertions are durable before any browser/context teardown.
                    persist()
                except Exception as error:
                    evidence["errors"].append({"browser": name, "width": width, "error": str(error)})
                    persist()
                finally:
                    if context is not None:
                        warning = bounded_cleanup(context.close, f"{name} {width}px context")
                        if warning:
                            evidence["cleanup_warnings"].append(warning)
                            persist()
        except Exception as error:
            evidence["errors"].append({"browser": name, "error": str(error)})
            persist()
        finally:
            if browser is not None:
                warning = bounded_cleanup(browser.close, f"{name} browser")
                if warning:
                    evidence["cleanup_warnings"].append(warning)
                    persist()
finally:
    warning = bounded_cleanup(playwright.stop, "Playwright driver")
    if warning:
        evidence["cleanup_warnings"].append(warning)
    evidence["status"] = "PASS" if len(rows) == evidence["expected_rows"] and all(row.get("status") == "PASS" for row in rows) and not evidence["errors"] else "FAIL"
    persist()

print(json.dumps(evidence, ensure_ascii=False, indent=2))
