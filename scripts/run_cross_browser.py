"""Chromium, Firefox, and WebKit coverage for the Decide/Day/Place contract."""

import json
import os
from pathlib import Path

from playwright.sync_api import sync_playwright

from qa_config import MODULAR_URL


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "QA" / "map_first"
SHOT = OUT / "screenshots"
SHOT.mkdir(parents=True, exist_ok=True)
cases = [(browser, width, height) for browser in ("chromium", "firefox", "webkit") for width, height in ((1280, 800), (390, 844))]
rows = []


with sync_playwright() as playwright:
    for browser_name, width, height in cases:
        row = {"browser": browser_name, "viewport": f"{width}x{height}", "status": "FAIL", "errors": [], "checks": {}}
        try:
            browser = getattr(playwright, browser_name).launch(headless=True, timeout=60000)
            page = browser.new_page(viewport={"width": width, "height": height}, has_touch=width < 500, is_mobile=width < 500)
            page.on("pageerror", lambda error, row=row: row["errors"].append(str(error)))
            page.goto(MODULAR_URL, wait_until="domcontentloaded", timeout=90000)
            page.wait_for_function("window.__tripApp?.map()?.isStyleLoaded()", timeout=45000)
            page.wait_for_function("document.querySelectorAll('.photo-marker').length===window.__tripApp.DATA.markers.length", timeout=30000)
            row["checks"].update({
                "markers": page.locator(".photo-marker").count() == page.evaluate("window.__tripApp.DATA.markers.length"),
                "canvas": page.locator(".maplibregl-canvas").count() == 1,
                "overflow": page.evaluate("document.documentElement.scrollWidth<=innerWidth"),
                "decide": page.locator("#recommendation").is_visible() and page.locator("#routeCards .route-card").count() == 4,
                "legacy_absent": page.locator("#dateRibbon,#mapSchedule,#mapFocus,#routeTip,#mobileDate,#mobileProvider,#previewCard,#detailsPane").count() == 0,
            })
            page.locator('[data-mode="day"]').click()
            page.locator("#dateSelect").select_option("10/8")
            row["checks"]["day"] = page.locator("#dayPlan .day-item, #dayPlan .plan-card").count() > 0 and page.locator("#dateSelect").input_value() == "10/8"
            page.locator(".photo-marker").first.click()
            page.locator("#peek [data-peek-open]").evaluate("element=>element.click()")
            page.wait_for_function("window.__tripApp.state.presentation.mode==='place'")
            row["checks"]["place"] = page.locator("#placeInspector .photo-slot img").count() == 3
            shot = SHOT / f"{browser_name}_{width}x{height}_place.png"
            page.screenshot(path=str(shot), full_page=True)
            row["screenshot"] = str(shot.relative_to(ROOT))
            row["status"] = "PASS" if not row["errors"] and all(row["checks"].values()) else "FAIL"
            browser.close()
        except Exception as error:
            row["error"] = f"{type(error).__name__}: {error}"
            row["status"] = "UNVERIFIED"
        rows.append(row)

report = {"schema_version": 2, "candidate": os.environ.get("TRIP_CANDIDATE_SHA", "WORKTREE"), "browser_families": ["Chromium", "Firefox", "WebKit"], "cases": rows, "status": "PASS" if rows and all(row["status"] == "PASS" for row in rows) else "FAIL", "native_safari_boundary": "Playwright WebKit is not native Safari; native Safari and physical-device evidence remain external."}
(OUT / "cross_browser.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"status": report["status"], "cases": [{"browser": row["browser"], "viewport": row["viewport"], "status": row["status"]} for row in rows]}, ensure_ascii=False, indent=2))
raise SystemExit(0 if report["status"] == "PASS" else 1)
