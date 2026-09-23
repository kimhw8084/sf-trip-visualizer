"""Touch/keyboard map-control and one-route camera-context oracle."""

from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

from qa_config import MODULAR_URL
from qa_evidence import bind_report, candidate_identity


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "QA" / "CHG-188" / "route_key_camera.json"
SCREENSHOTS = ROOT / "QA" / "CHG-188" / "screenshots"
VIEWPORTS = ((360, 800), (375, 812), (390, 844), (414, 896))
PATHS = ("pointer", "keyboard", "touch")
ROUTES = sorted(json.loads((ROOT / "data/phase7_app_data.json").read_text())["routes"])


def task_state(page) -> dict:
    return page.evaluate("""() => {const s=window.__tripApp.state.task;return {routes:[...s.routes].sort(),primary_route:s.primaryRoute,date:s.date,region:s.region,selected:s.selected}}""")


def map_context(page) -> dict:
    return page.evaluate("""() => {const a=window.__tripApp,m=a.map(),g=a.mapGeometrySnapshot();return {canvas_count:document.querySelectorAll('.maplibregl-canvas').length,style_loaded:m.isStyleLoaded(),visible_markers:a.DATA.markers.filter(x=>a.markerVisible(x,{map:true})).length,route_features:a.visibleRouteFeatures().length,spatial:a.mapSpatialSnapshot(),map_obstacles:g.obstacles.length}}""")


def control_path(page, path: str) -> dict:
    button = page.locator("#mapOptionsToggle")
    if path == "keyboard":
        button.focus()
        page.keyboard.press("Enter")
    elif path == "touch":
        button.tap()
    else:
        button.click()
    page.wait_for_function("document.querySelector('#mapOptionsPanel')?.hidden === false")
    page.wait_for_function("window.__tripApp?.map()?.isStyleLoaded() && !window.__tripApp.map().isMoving()", timeout=5000)
    page.wait_for_timeout(160)
    opened = map_context(page)
    open_state = task_state(page)
    if path == "keyboard":
        page.keyboard.press("Escape")
    else:
        page.keyboard.press("Escape")
    page.wait_for_function("document.querySelector('#mapOptionsPanel')?.hidden === true")
    page.wait_for_function("document.activeElement?.id === 'mapOptionsToggle'")
    page.wait_for_function("window.__tripApp?.map()?.isStyleLoaded() && !window.__tripApp.map().isMoving()", timeout=5000)
    page.wait_for_timeout(160)
    closed = map_context(page)
    return {"path": path, "opened": opened, "closed": closed, "task_preserved": task_state(page) == open_state, "focus_returned": page.evaluate("document.activeElement?.id === 'mapOptionsToggle'"), "panel_closed": page.locator("#mapOptionsPanel").is_hidden()}


def context_passes(context: dict) -> bool:
    return context["canvas_count"] == 1 and context["style_loaded"] and context["visible_markers"] > 0 and context["route_features"] > 0 and context["spatial"].get("useful") is True


def main() -> int:
    identity = candidate_identity()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    report = bind_report({"schema_version": 2, "change": "CHG-188 single-route map controls and camera context", "status": "FAIL", "route_ids": ROUTES, "viewports": {}, "failures": [], "errors": [], "screenshots": [], "negative_control": {"route_comparison_ui_absent": True}}, identity)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        for width, height in VIEWPORTS:
            key = f"{width}x{height}"
            context = browser.new_context(viewport={"width": width, "height": height}, has_touch=True, is_mobile=True)
            page = context.new_page()
            page_errors = []
            page.on("pageerror", lambda error: page_errors.append(str(error)))
            try:
                page.goto(MODULAR_URL, wait_until="domcontentloaded", timeout=90000)
                page.wait_for_function("window.__tripApp?.state?.runtime?.mapVisualReady === true", timeout=30000)
                page.locator("#mapOptionsToggle").click()
                page.locator("#regionControls [data-region='yosemite']").click()
                page.locator('[data-mode="day"]').click()
                page.locator("#dateSelect").select_option("10/8")
                page.evaluate("window.__tripApp.fitVisibleMap()")
                page.wait_for_timeout(180)
                baseline_task = task_state(page)
                baseline_context = map_context(page)
                chrome = page.locator("#routeLegendToggle,#routeLegendPanel,[data-compare-route],#comparePanel,.route-compare,.route-membership,.membership-cell").count()
                paths = {path: control_path(page, path) for path in PATHS}
                page.locator("#fitMap").click()
                page.wait_for_timeout(100)
                fit_context = map_context(page)
                screenshots = []
                if width in (390, 414):
                    target = SCREENSHOTS / f"map_controls_{key}_single_route.png"
                    target.parent.mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=str(target), full_page=True)
                    screenshots.append(str(target.relative_to(ROOT)))
                    report["screenshots"].append({"path": screenshots[-1], "candidate": identity["sha"], "candidate_tree": identity["tree"], "browser": "chromium", "viewport": key, "state": "single-route Yosemite map controls"})
                row = {"baseline_task": baseline_task, "task_after_controls": task_state(page), "baseline_context": baseline_context, "fit_context": fit_context, "comparison_chrome_count": chrome, "paths": paths, "screenshots": screenshots, "page_errors": page_errors}
                row["pass"] = baseline_task["routes"] == ROUTES and baseline_task["date"] == "10/8" and baseline_task["region"] == "yosemite" and row["task_after_controls"] == baseline_task and chrome == 0 and context_passes(baseline_context) and context_passes(fit_context) and all(control["task_preserved"] and control["focus_returned"] and control["panel_closed"] and context_passes(control["opened"]) and context_passes(control["closed"]) for control in paths.values()) and not page_errors
                if not row["pass"]:
                    report["failures"].append(f"{key}: map controls changed task state, lost map context, or exposed route comparison chrome")
                report["viewports"][key] = row
            except Exception as error:
                report["errors"].append(f"{key}: {type(error).__name__}: {error}")
            page.close()
            context.close()
        browser.close()
    report["negative_control"]["route_comparison_ui_absent"] = all(row.get("comparison_chrome_count") == 0 for row in report["viewports"].values()) and len(report["viewports"]) == len(VIEWPORTS)
    report["status"] = "PASS" if not report["failures"] and not report["errors"] and len(report["viewports"]) == len(VIEWPORTS) else "FAIL"
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "viewports": len(report["viewports"]), "failures": report["failures"], "errors": report["errors"]}, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
