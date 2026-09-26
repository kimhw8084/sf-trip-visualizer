"""Touch/keyboard map-control and one-route camera-context oracle."""

from __future__ import annotations

import json
import math
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from qa_config import MODULAR_URL
from qa_evidence import bind_report, candidate_identity


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "QA" / "CHG-232" / "route_key_camera.json"
SCREENSHOTS = ROOT / "QA" / "CHG-232" / "screenshots"
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


def settle_map(page) -> None:
    page.evaluate("window.__tripApp.whenIdle()")
    page.wait_for_function("window.__tripApp?.map()?.areTilesLoaded?.() === true && !window.__tripApp.map().isMoving()", timeout=10000)
    page.evaluate("new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")


def camera_snapshot(page) -> dict:
    return page.evaluate("""() => {
      const a=window.__tripApp,m=a.map(),task=a.state.task,center=m.getCenter(),region=a.DATA.region_cfg[task.region];
      const labels=m.queryRenderedFeatures().flatMap(feature=>Object.entries(feature.properties||{}).filter(([key,value])=>(key==='name'||key.startsWith('name:'))&&typeof value==='string').map(([,value])=>value));
      const empty=document.querySelector('#dayPlan .empty-state');
      return {
        task:{region:task.region,date:task.date},
        language:document.documentElement.lang,
        map_summary:document.querySelector('#mapCurrentSummary')?.textContent?.trim()||'',
        expected_region_label:task.region==='overall'?(document.documentElement.lang==='ko'?region.label_ko:region.label):(region[document.documentElement.lang==='ko'?'label':'label_en']||task.region),
        day_empty_text:empty?.innerText?.trim()||'',
        visible_markers:a.DATA.markers.filter(marker=>a.markerVisible(marker,{map:true})).length,
        photo_marker_elements:document.querySelectorAll('#map .photo-marker').length,
        route_features:a.visibleRouteFeatures().length,
        camera:{center:[center.lng,center.lat],zoom:m.getZoom()},
        expected_region_camera:{center:[region.center.lon,region.center.lat],zoom:region.zoom},
        rendered_yosemite_labels:[...new Set(labels.filter(value=>/^(Yosemite Valley|Yosemite Village|Curry Village|Upper Yosemite Fall|Lower Yosemite Fall)$/i.test(value)))],
        spatial:a.mapSpatialSnapshot(),
        canvas_count:document.querySelectorAll('.maplibregl-canvas').length,
        map_creations:a.state.runtime.mapCreations,
        map_removals:a.state.runtime.mapRemovals
      };
    }""")


def empty_camera_issues(snapshot: dict, region: str, *, require_day_empty: bool = False) -> list[str]:
    issues = []
    task = snapshot.get("task", {})
    if task.get("region") != region:
        issues.append(f"expected {region} region in empty state")
    if snapshot.get("visible_markers") != 0 or snapshot.get("photo_marker_elements") != 0:
        issues.append("empty state contains visible or rendered photo markers")
    if snapshot.get("route_features") != 0:
        issues.append("empty state contains visible route features")
    if snapshot.get("canvas_count") != 1:
        issues.append("empty state has a missing or duplicate map canvas")
    camera = snapshot.get("camera", {})
    expected = snapshot.get("expected_region_camera", {})
    center = camera.get("center", [])
    expected_center = expected.get("center", [])
    if len(center) != 2 or len(expected_center) != 2 or any(not math.isclose(float(actual), float(target), abs_tol=1e-5) for actual, target in zip(center, expected_center)):
        issues.append("empty state camera center does not match the selected region authority")
    if not math.isclose(float(camera.get("zoom", -1)), float(expected.get("zoom", -2)), abs_tol=0.01):
        issues.append("empty state camera zoom does not match the selected region authority")
    if snapshot.get("rendered_yosemite_labels"):
        issues.append("Yosemite labels remain in the rendered map context")
    summary = snapshot.get("map_summary", "")
    if "Smart" not in summary or snapshot.get("expected_region_label", "") not in summary:
        issues.append("Smart map summary does not identify the selected region")
    if require_day_empty:
        language = snapshot.get("language")
        expected_text = "현재 조건에 맞는 일정이 없습니다." if language == "ko" else "No plan items match these conditions."
        if snapshot.get("day_empty_text") != expected_text:
            issues.append("Day panel does not explicitly report that no plan items match")
    return issues


def nonempty_recovery_issues(snapshot: dict, *, require_route: bool) -> list[str]:
    issues = []
    if snapshot.get("task") != {"region": "yosemite", "date": "10/7"}:
        issues.append("Yosemite recovery task state is incorrect")
    if snapshot.get("visible_markers", 0) <= 0 or snapshot.get("photo_marker_elements") != snapshot.get("visible_markers"):
        issues.append("Yosemite recovery markers are missing or duplicated")
    if require_route and snapshot.get("route_features", 0) <= 0:
        issues.append("Yosemite recovery route geometry is missing")
    spatial = snapshot.get("spatial", {})
    if spatial.get("useful") is not True or spatial.get("markers_in_viewport") != snapshot.get("visible_markers"):
        issues.append("Yosemite recovery camera does not frame all visible markers")
    if require_route and (spatial.get("route_features_in_viewport") != snapshot.get("route_features") or spatial.get("route_points_in_viewport", 0) <= 0):
        issues.append("Yosemite recovery camera does not frame visible route geometry")
    if snapshot.get("canvas_count") != 1:
        issues.append("Yosemite recovery has a missing or duplicate map canvas")
    if snapshot.get("map_creations") != 1 or snapshot.get("map_removals") != 0:
        issues.append("Yosemite recovery has stale or duplicate map ownership")
    return issues


def select_region(page, region: str) -> None:
    if page.locator("#mapOptionsPanel").is_hidden():
        page.locator("#mapOptionsToggle").click()
        page.wait_for_function("document.querySelector('#mapOptionsPanel')?.hidden === false")
    page.locator(f"#regionControls [data-region='{region}']").click()
    settle_map(page)


def select_date(page, date: str) -> None:
    page.locator("#dateSelect").select_option(date)
    settle_map(page)


def empty_state_camera_regression(page) -> dict:
    page.locator("#modeNav [data-mode='day']").click()
    select_region(page, "yosemite")
    select_date(page, "10/9")
    sparse_control = camera_snapshot(page)
    sparse_issues = []
    if sparse_control["task"] != {"region": "yosemite", "date": "10/9"} or sparse_control["visible_markers"] <= 0 or not sparse_control["spatial"].get("useful"):
        sparse_issues.append("non-empty Yosemite 10/9 positive fit control is not useful")

    select_region(page, "sf")
    select_date(page, "10/6")
    region_then_date = camera_snapshot(page)
    region_then_date_issues = empty_camera_issues(region_then_date, "sf", require_day_empty=True)

    select_region(page, "yosemite")
    select_date(page, "10/9")
    select_date(page, "10/6")
    select_region(page, "sf")
    date_then_region = camera_snapshot(page)
    date_then_region_issues = empty_camera_issues(date_then_region, "sf", require_day_empty=True)

    select_region(page, "yosemite")
    select_date(page, "10/7")
    yosemite_recovery = camera_snapshot(page)
    recovery_issues = nonempty_recovery_issues(yosemite_recovery, require_route=True)

    select_region(page, "overall")
    select_date(page, "10/12")
    overall_empty = camera_snapshot(page)
    overall_issues = empty_camera_issues(overall_empty, "overall")

    return {
        "status": "PASS" if not (sparse_issues or region_then_date_issues or date_then_region_issues or recovery_issues or overall_issues) else "FAIL",
        "positive_nonempty_control": {"snapshot": sparse_control, "failures": sparse_issues},
        "region_then_date_empty": {"snapshot": region_then_date, "failures": region_then_date_issues},
        "date_then_region_empty": {"snapshot": date_then_region, "failures": date_then_region_issues},
        "yosemite_nonempty_recovery": {"snapshot": yosemite_recovery, "failures": recovery_issues},
        "overall_empty_fallback": {"snapshot": overall_empty, "failures": overall_issues},
        "failures": sparse_issues + region_then_date_issues + date_then_region_issues + recovery_issues + overall_issues,
    }


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
    report = bind_report({"schema_version": 2, "change": "CHG-232 single-route map controls and camera context", "status": "FAIL", "route_ids": ROUTES, "viewports": {}, "failures": [], "errors": [], "screenshots": [], "negative_control": {"route_comparison_ui_absent": True}}, identity)
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
                camera_regression = empty_state_camera_regression(page)
                all_acceptances = [baseline_acceptance, fit_context] + [sample for control in paths.values() for sample in (control["opened"], control["closed"])]
                comparison_chrome_count = baseline_acceptance["comparison_chrome_count"]
                row = {"baseline_task": baseline_task, "task_after_controls": task_after_controls, "baseline_context": baseline_acceptance, "fit_context": fit_context, "empty_state_camera_regression": camera_regression, "comparison_chrome_count": comparison_chrome_count, "comparison_chrome_counts": [sample["comparison_chrome_count"] for sample in all_acceptances], "expected_counts": expected_counts, "paths": paths, "screenshots": screenshots, "page_errors": page_errors}
                row["pass"] = task_matches_scenario and task_after_controls == baseline_task and all(sample["comparison_chrome_count"] == 0 and context_passes(sample) for sample in all_acceptances) and all(control["task_preserved"] and control["focus_returned"] and control["panel_closed"] for control in paths.values()) and camera_regression["status"] == "PASS" and not page_errors
                if not row["pass"]:
                    report["failures"].append(f"{key}: map controls or empty-state camera regression failed")
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
