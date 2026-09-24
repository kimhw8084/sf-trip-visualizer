"""Touch/keyboard map-control and one-route camera-context oracle."""

from __future__ import annotations

import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from qa_config import MODULAR_URL
from qa_evidence import bind_report, candidate_identity


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "QA" / "CHG-204" / "route_key_camera.json"
SCREENSHOTS = ROOT / "QA" / "CHG-204" / "screenshots"
VIEWPORTS = ((360, 800), (375, 812), (390, 844), (414, 896))
PATHS = ("pointer", "keyboard", "touch")
ROUTES = sorted(json.loads((ROOT / "data/phase7_app_data.json").read_text())["routes"])
STYLE_READY_TIMEOUT_MS = 5000


def task_state(page) -> dict:
    return page.evaluate("""() => {const s=window.__tripApp.state.task;return {routes:[...s.routes].sort(),primary_route:s.primaryRoute,date:s.date,region:s.region,selected:s.selected}}""")


def map_context(page) -> dict:
    return page.evaluate("""() => {
      const a=window.__tripApp,m=a?.map?.(),r=a?.state?.runtime;
      const canvas_count=document.querySelectorAll('.maplibregl-canvas').length;
      if(!a||!m)return {map_present:false,provider:r?.provider??null,app_ready:r?.mapStatus==='ready',map_visual_ready:r?.mapVisualReady===true,canvas_count,style_loaded:false,map_moving:null,visible_markers:0,route_features:0,spatial:null,map_obstacles:null};
      const g=a.mapGeometrySnapshot();
      return {map_present:true,provider:r?.provider??null,app_ready:r?.mapStatus==='ready',map_visual_ready:r?.mapVisualReady===true,canvas_count,style_loaded:m.isStyleLoaded(),map_moving:m.isMoving(),visible_markers:a.DATA.markers.filter(x=>a.markerVisible(x,{map:true})).length,route_features:a.visibleRouteFeatures().length,spatial:a.mapSpatialSnapshot(),map_obstacles:g.obstacles.length};
    }""")


def context_issues(context: dict, expected_counts: dict | None = None) -> list[str]:
    issues = []
    if context.get("map_present") is not True:
        issues.append("map/provider state is missing")
    if not context.get("provider") or context.get("app_ready") is not True or context.get("map_visual_ready") is not True:
        issues.append("map/provider is not operational")
    if context.get("canvas_count") != 1:
        issues.append("map canvas is missing or duplicated")
    visible_markers = context.get("visible_markers", 0)
    route_features = context.get("route_features", 0)
    if visible_markers <= 0:
        issues.append("expected visible markers are missing")
    if route_features <= 0:
        issues.append("expected route features are missing")
    if expected_counts:
        if visible_markers != expected_counts["visible_markers"]:
            issues.append("expected visible marker count changed")
        if route_features != expected_counts["route_features"]:
            issues.append("expected route feature count changed")
    spatial = context.get("spatial")
    if not isinstance(spatial, dict) or spatial.get("useful") is not True:
        issues.append("map spatial context is unusable")
    else:
        if spatial.get("visible_markers") != visible_markers or spatial.get("markers_in_viewport") != visible_markers:
            issues.append("expected markers are not all in the viewport")
        if spatial.get("route_features") != route_features or spatial.get("route_features_in_viewport") != route_features:
            issues.append("expected route features are not all in the viewport")
        if spatial.get("route_points_in_viewport", 0) <= 0:
            issues.append("route geometry is outside the viewport")
    return issues


def acceptance_snapshot(page, expected_task: dict, expected_counts: dict | None = None) -> dict:
    task = task_state(page)
    initial_context = map_context(page)
    initial_chrome = page.locator("#routeLegendToggle,#routeLegendPanel,[data-compare-route],#comparePanel,.route-compare,.route-membership,.membership-cell").count()
    initial_issues = context_issues(initial_context, expected_counts)
    if task != expected_task:
        initial_issues.append("route/date/region task state changed")
    if initial_chrome:
        initial_issues.append("route-comparison chrome leaked")

    initial_ready = initial_context.get("style_loaded") is True and initial_context.get("map_moving") is False
    final_context = initial_context
    final_task = task
    final_chrome = initial_chrome
    wait_ms = 0
    wait_error = None
    if not initial_issues and not initial_ready:
        started = time.monotonic()
        try:
            page.wait_for_function(
                """() => {const m=window.__tripApp?.map?.();return !!m&&m.isStyleLoaded()&&!m.isMoving()}""",
                timeout=STYLE_READY_TIMEOUT_MS,
            )
        except Exception as error:
            wait_error = f"{type(error).__name__}: {error}"
        wait_ms = round((time.monotonic() - started) * 1000)
        final_context = map_context(page)
        final_task = task_state(page)
        final_chrome = page.locator("#routeLegendToggle,#routeLegendPanel,[data-compare-route],#comparePanel,.route-compare,.route-membership,.membership-cell").count()

    failures = context_issues(final_context, expected_counts)
    if final_task != expected_task:
        failures.append("route/date/region task state changed")
    if final_chrome:
        failures.append("route-comparison chrome leaked")
    if final_context.get("style_loaded") is not True or final_context.get("map_moving") is not False:
        failures.append("map style did not become ready and stationary within the bounded window")
    if wait_error:
        failures.append("map style readiness wait timed out or errored")
    return {
        **final_context,
        "task": final_task,
        "comparison_chrome_count": final_chrome,
        "style_readiness": {
            "initial_style_loaded": initial_context.get("style_loaded") is True,
            "initial_map_moving": initial_context.get("map_moving"),
            "transient_recovery": initial_context.get("style_loaded") is False and not wait_error and final_context.get("style_loaded") is True and final_context.get("map_moving") is False,
            "readiness_recovered": not initial_ready and not wait_error and final_context.get("style_loaded") is True and final_context.get("map_moving") is False,
            "wait_ms": wait_ms,
            "timeout_ms": STYLE_READY_TIMEOUT_MS,
            "wait_error": wait_error,
        },
        "initial_failures": initial_issues,
        "failures": list(dict.fromkeys(failures)),
        "valid": not initial_issues and not failures,
    }


def control_path(page, path: str, expected_task: dict, expected_counts: dict) -> dict:
    button = page.locator("#mapOptionsToggle")
    if path == "keyboard":
        button.focus()
        page.keyboard.press("Enter")
    elif path == "touch":
        button.tap()
    else:
        button.click()
    page.wait_for_function("document.querySelector('#mapOptionsPanel')?.hidden === false")
    page.wait_for_timeout(160)
    opened = acceptance_snapshot(page, expected_task, expected_counts)
    if path == "keyboard":
        page.keyboard.press("Escape")
    else:
        page.keyboard.press("Escape")
    page.wait_for_function("document.querySelector('#mapOptionsPanel')?.hidden === true")
    page.wait_for_function("document.activeElement?.id === 'mapOptionsToggle'")
    page.wait_for_timeout(160)
    closed = acceptance_snapshot(page, expected_task, expected_counts)
    return {"path": path, "opened": opened, "closed": closed, "task_preserved": opened["task"] == expected_task and closed["task"] == expected_task, "focus_returned": page.evaluate("document.activeElement?.id === 'mapOptionsToggle'"), "panel_closed": page.locator("#mapOptionsPanel").is_hidden()}


def context_passes(context: dict) -> bool:
    return context.get("valid") is True


def main() -> int:
    identity = candidate_identity()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    report = bind_report({"schema_version": 2, "change": "CHG-204 single-route map controls and camera context", "status": "FAIL", "route_ids": ROUTES, "viewports": {}, "failures": [], "errors": [], "screenshots": [], "negative_control": {"route_comparison_ui_absent": True}}, identity)
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
                baseline_acceptance = acceptance_snapshot(page, baseline_task)
                expected_counts = {"visible_markers": baseline_acceptance["visible_markers"], "route_features": baseline_acceptance["route_features"]}
                task_matches_scenario = baseline_task["routes"] == ROUTES == ["A"] and baseline_task["primary_route"] == "A" and baseline_task["date"] == "10/8" and baseline_task["region"] == "yosemite"
                paths = {path: control_path(page, path, baseline_task, expected_counts) for path in PATHS}
                page.locator("#fitMap").click()
                page.wait_for_timeout(100)
                fit_context = acceptance_snapshot(page, baseline_task, expected_counts)
                screenshots = []
                if width in (390, 414):
                    target = SCREENSHOTS / f"map_controls_{key}_single_route.png"
                    target.parent.mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=str(target), full_page=True)
                    screenshots.append(str(target.relative_to(ROOT)))
                    report["screenshots"].append({"path": screenshots[-1], "candidate": identity["sha"], "candidate_tree": identity["tree"], "browser": "chromium", "viewport": key, "state": "single-route Yosemite map controls"})
                task_after_controls = task_state(page)
                all_acceptances = [baseline_acceptance, fit_context] + [sample for control in paths.values() for sample in (control["opened"], control["closed"])]
                comparison_chrome_count = baseline_acceptance["comparison_chrome_count"]
                row = {"baseline_task": baseline_task, "task_after_controls": task_after_controls, "baseline_context": baseline_acceptance, "fit_context": fit_context, "comparison_chrome_count": comparison_chrome_count, "comparison_chrome_counts": [sample["comparison_chrome_count"] for sample in all_acceptances], "expected_counts": expected_counts, "paths": paths, "screenshots": screenshots, "page_errors": page_errors}
                row["pass"] = task_matches_scenario and task_after_controls == baseline_task and all(sample["comparison_chrome_count"] == 0 and context_passes(sample) for sample in all_acceptances) and all(control["task_preserved"] and control["focus_returned"] and control["panel_closed"] for control in paths.values()) and not page_errors
                if not row["pass"]:
                    report["failures"].append(f"{key}: map controls changed task state, lost map context, or exposed route comparison chrome")
                report["viewports"][key] = row
            except Exception as error:
                report["errors"].append(f"{key}: {type(error).__name__}: {error}")
            page.close()
            context.close()
        browser.close()
    report["negative_control"]["route_comparison_ui_absent"] = all(all(count == 0 for count in row.get("comparison_chrome_counts", [])) for row in report["viewports"].values()) and len(report["viewports"]) == len(VIEWPORTS)
    report["status"] = "PASS" if not report["failures"] and not report["errors"] and len(report["viewports"]) == len(VIEWPORTS) else "FAIL"
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "viewports": len(report["viewports"]), "failures": report["failures"], "errors": report["errors"]}, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
