"""Capture the candidate's canonical visual states for independent review."""

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

from qa_config import MODULAR_URL


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "QA" / "map_first" / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)
rows = []


def capture(page, name, width, height, mode, state):
    path = OUT / f"{name}.png"
    page.screenshot(path=str(path), full_page=True)
    rows.append({"screenshot": str(path.relative_to(ROOT)), "viewport": f"{width}x{height}", "mode": mode, "state": state, "language": page.evaluate("document.documentElement.lang"), "theme": page.evaluate("document.documentElement.dataset.theme"), "candidate": __import__("os").environ.get("TRIP_CANDIDATE_SHA", "WORKTREE")})


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    for width, height in ((1440, 900), (1366, 768), (390, 844), (360, 800)):
        page = browser.new_page(viewport={"width": width, "height": height}, has_touch=width < 500, is_mobile=width < 500)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(MODULAR_URL, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_function("window.__tripApp?.map()?.isStyleLoaded()", timeout=30000)
        page.wait_for_function("document.querySelectorAll('.photo-marker').length>0", timeout=15000)
        capture(page, f"decide_{width}x{height}", width, height, "decide", "recommended_default")
        page.locator('[data-compare-route="A2"]').click()
        capture(page, f"compare_{width}x{height}", width, height, "decide", "A1_A2")
        page.locator('[data-mode="day"]').click()
        page.locator("#dateSelect").select_option("10/8")
        capture(page, f"day_1008_{width}x{height}", width, height, "day", "10/8")
        page.locator(".photo-marker").first.click()
        page.locator("#peek [data-peek-open]").evaluate("element=>element.click()")
        page.wait_for_function("window.__tripApp.state.presentation.mode==='place'")
        capture(page, f"place_{width}x{height}", width, height, "place", "inspector")
        if width == 1440:
            page.locator("#langToggle").click()
            page.locator("#themeToggle").click()
            capture(page, "decide_1440x900_en_dark", width, height, "place", "ko_en_dark_transition")
        rows[-1]["errors"] = errors
        page.close()
    browser.close()

report = {"status": "PASS" if len(rows) == 17 and all(not row.get("errors", []) for row in rows) else "FAIL", "rows": rows, "reserved_holdouts": ["1366x768 desktop", "360x800 mobile"]}
(ROOT / "QA/map_first/visual_spots.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"status": report["status"], "screenshots": len(rows)}, ensure_ascii=False, indent=2))
raise SystemExit(0 if report["status"] == "PASS" else 1)
