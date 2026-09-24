"""Rendered accessibility, focus, forced-colors, reduced-motion, and reflow checks."""

import json
import os
from pathlib import Path

from playwright.sync_api import sync_playwright

from qa_config import MODULAR_URL
from qa_evidence import bind_report, candidate_identity


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "QA" / "CHG-204" / "accessibility.json"
IDENTITY = candidate_identity()
report = {"schema_version": 1, "checks": {}, "errors": []}


def put(name, passed, detail=None):
    report["checks"][name] = {"status": "PASS" if passed else "FAIL", "detail": detail}


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.on("pageerror", lambda error: report["errors"].append(str(error)))
    page.goto(MODULAR_URL, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_function("window.__tripApp?.map()?.isStyleLoaded()", timeout=30000)
    source_data = json.loads((ROOT / "data" / "phase7_app_data.json").read_text())
    active_routes = set(source_data["routes"])
    expected_markers = sum(bool(set(marker.get("routes", [])) & active_routes) for marker in source_data["markers"])
    page.wait_for_function("expected=>document.querySelectorAll('.photo-marker').length===expected", arg=expected_markers, timeout=15000)
    put("focusable_controls_have_visible_focus", page.evaluate("""()=>{const controls=[...document.querySelectorAll('button,a,select')].filter(element=>element.getClientRects().length&&getComputedStyle(element).visibility!=='hidden');for(const element of controls.slice(0,18)){element.focus();const r=element.getBoundingClientRect(),s=getComputedStyle(element);if(r.width<1||r.height<1||s.visibility==='hidden')return false}return true}"""))
    page.locator("#mapOptionsToggle").click()
    page.locator("#regionControls [data-region='yosemite']").click()
    page.locator("#modeNav [data-mode='day']").click()
    page.locator("#dateSelect").select_option("10/7")
    page.locator(".photo-marker[data-place-key='cooks']").click()
    page.wait_for_selector("#peek.show")
    page.mouse.move(0, 0)
    page.keyboard.press("Escape")
    put("escape_closes_peek", page.locator("#peek.show").count() == 0)
    page.locator('#modeNav [data-mode="day"]').click()
    page.locator("#dateSelect").select_option("10/8")
    page.locator("#dayPlan .day-item").first.click()
    page.wait_for_selector("#peek.show")
    page.keyboard.press("Escape")
    put("escape_preserves_day_context", page.evaluate("window.__tripApp.state.presentation.mode==='day'&&window.__tripApp.state.date==='10/8'"))
    page.evaluate("document.documentElement.style.fontSize='200%'")
    page.wait_for_timeout(200)
    put("200_percent_reflow", page.evaluate("document.documentElement.scrollWidth<=innerWidth && document.querySelector('#workbench').getBoundingClientRect().height>0"))
    page.close()

    reduced = browser.new_context(viewport={"width": 390, "height": 844}, reduced_motion="reduce")
    reduced_page = reduced.new_page()
    reduced_page.goto(MODULAR_URL, wait_until="domcontentloaded", timeout=90000)
    reduced_page.wait_for_function("window.__tripApp?.map()?.isStyleLoaded()", timeout=30000)
    put("reduced_motion_media_applied", reduced_page.evaluate("matchMedia('(prefers-reduced-motion: reduce)').matches && getComputedStyle(document.body).scrollBehavior==='auto'"))
    reduced.close()

    forced = browser.new_context(viewport={"width": 390, "height": 844}, forced_colors="active")
    forced_page = forced.new_page()
    forced_page.goto(MODULAR_URL, wait_until="domcontentloaded", timeout=90000)
    forced_page.wait_for_function("window.__tripApp?.map()?.isStyleLoaded()", timeout=30000)
    put("forced_colors_surface_remains_operable", forced_page.evaluate("matchMedia('(forced-colors: active)').matches && document.querySelectorAll('#modeNav button').length===3 && document.querySelector('#map').getBoundingClientRect().height>0"))
    forced.close()
    browser.close()

bind_report(report, IDENTITY)
report["status"] = "PASS" if not report["errors"] and all(row["status"] == "PASS" for row in report["checks"].values()) else "FAIL"
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"status": report["status"], "checks": report["checks"], "errors": report["errors"]}, ensure_ascii=False, indent=2))
raise SystemExit(0 if report["status"] == "PASS" else 1)
