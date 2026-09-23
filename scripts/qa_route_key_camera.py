"""Touch/keyboard map-control and one-route camera-context oracle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Callable

from playwright.sync_api import sync_playwright

from qa_config import MODULAR_URL
from qa_evidence import bind_report, candidate_identity


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "QA" / "CHG-188" / "route_key_camera.json"
SCREENSHOTS = ROOT / "QA" / "CHG-188" / "screenshots"
VIEWPORTS = ((360, 800), (375, 812), (390, 844), (414, 896))
PATHS = ("pointer", "keyboard", "touch")
READINESS_TIMEOUT_MS = 5000
EXPECTED_MARKER_COUNT = 3
EXPECTED_ROUTE_FEATURE_COUNT = 2
ROUTES = sorted(json.loads((ROOT / "data/phase7_app_data.json").read_text())["routes"])


def task_state(page) -> dict:
    return page.evaluate("""() => {const s=window.__tripApp.state.task;return {routes:[...s.routes].sort(),primary_route:s.primaryRoute,date:s.date,region:s.region,selected:s.selected}}""")


def map_context(page) -> dict:
    return page.evaluate("""() => {const a=window.__tripApp,m=a.map(),g=a.mapGeometrySnapshot();return {canvas_count:document.querySelectorAll('.maplibregl-canvas').length,style_loaded:m.isStyleLoaded(),map_moving:m.isMoving(),visible_markers:a.DATA.markers.filter(x=>a.markerVisible(x,{map:true})).length,route_features:a.visibleRouteFeatures().length,spatial:a.mapSpatialSnapshot(),map_obstacles:g.obstacles.length}}""")


def capture_sample(page) -> dict:
    return {
        "task_state": task_state(page),
        "context": map_context(page),
        "comparison_chrome_count": page.locator(
            "#routeLegendToggle,#routeLegendPanel,[data-compare-route],#comparePanel,"
            ".route-compare,.route-membership,.membership-cell"
        ).count(),
        "panel_visible": page.locator("#mapOptionsPanel").is_visible(),
        "focus_id": page.evaluate("document.activeElement?.id || null"),
    }


def style_ready(context: dict) -> bool:
    return context.get("style_loaded") is True and context.get("map_moving") is False


def sample_invariant_failures(
    sample: dict,
    expected_task: dict,
    *,
    panel_visible: bool | None = None,
    expected_focus_id: str | None = None,
    expected_markers: int = EXPECTED_MARKER_COUNT,
    expected_route_features: int = EXPECTED_ROUTE_FEATURE_COUNT,
) -> list[str]:
    failures: list[str] = []
    context = sample.get("context", {})
    spatial = context.get("spatial", {})
    if sample.get("task_state") != expected_task:
        failures.append("route/date/region task state changed")
    if context.get("canvas_count") != 1:
        failures.append("map canvas count is not exactly one")
    if context.get("visible_markers") != expected_markers:
        failures.append("expected visible marker count is absent")
    if context.get("route_features") != expected_route_features:
        failures.append("expected route-feature count is absent")
    if spatial.get("useful") is not True:
        failures.append("map spatial usefulness is false")
    if spatial.get("width", 0) <= 0 or spatial.get("height", 0) <= 0:
        failures.append("map viewport has no usable dimensions")
    if spatial.get("markers_in_viewport") != expected_markers:
        failures.append("expected markers are not all in the viewport")
    if spatial.get("route_features_in_viewport") != expected_route_features:
        failures.append("expected route features are not all in the viewport")
    if spatial.get("route_points_in_viewport", 0) <= 0:
        failures.append("route geography is absent from the viewport")
    if sample.get("comparison_chrome_count") != 0:
        failures.append("comparison chrome leaked into the single-route surface")
    if panel_visible is not None and sample.get("panel_visible") is not panel_visible:
        failures.append("map-options panel visibility changed")
    if expected_focus_id is not None and sample.get("focus_id") != expected_focus_id:
        failures.append("focus did not return to the map-options control")
    return failures


def assess_sample(
    initial_sample: dict,
    expected_task: dict,
    wait_until_ready: Callable[[], dict],
    *,
    panel_visible: bool | None = None,
    expected_focus_id: str | None = None,
    expected_markers: int = EXPECTED_MARKER_COUNT,
    expected_route_features: int = EXPECTED_ROUTE_FEATURE_COUNT,
) -> dict:
    """Validate context before bounded style recovery, then validate it again."""
    result = {
        "initial_sample": initial_sample,
        "recovered_sample": None,
        "transient_recovery": False,
        "readiness_waited": False,
        "passed": False,
        "failures": [],
    }
    invariant_args = {
        "panel_visible": panel_visible,
        "expected_focus_id": expected_focus_id,
        "expected_markers": expected_markers,
        "expected_route_features": expected_route_features,
    }
    failures = sample_invariant_failures(initial_sample, expected_task, **invariant_args)
    if failures:
        result["failures"] = failures
        return result
    if style_ready(initial_sample["context"]):
        result["passed"] = True
        result["final_sample"] = initial_sample
        return result

    result["readiness_waited"] = True
    try:
        recovered_sample = wait_until_ready()
    except Exception as error:
        result["failures"] = [f"style/provider readiness did not return within {READINESS_TIMEOUT_MS} ms: {error}"]
        return result

    result["recovered_sample"] = recovered_sample
    failures = sample_invariant_failures(recovered_sample, expected_task, **invariant_args)
    if failures:
        result["failures"] = failures
        return result
    if not style_ready(recovered_sample.get("context", {})):
        result["failures"] = [f"style/provider readiness did not return within {READINESS_TIMEOUT_MS} ms"]
        return result
    result["transient_recovery"] = True
    result["passed"] = True
    result["final_sample"] = recovered_sample
    return result


def acceptance_sample(
    page,
    expected_task: dict,
    *,
    panel_visible: bool | None = None,
    expected_focus_id: str | None = None,
) -> dict:
    initial_sample = capture_sample(page)

    def wait_until_ready() -> dict:
        page.wait_for_function(
            "window.__tripApp?.map()?.isStyleLoaded() && !window.__tripApp.map().isMoving()",
            timeout=READINESS_TIMEOUT_MS,
        )
        return capture_sample(page)

    return assess_sample(
        initial_sample,
        expected_task,
        wait_until_ready,
        panel_visible=panel_visible,
        expected_focus_id=expected_focus_id,
    )


def install_style_control(page, control: str) -> None:
    if control == "none":
        return
    page.evaluate(
        """control => {
          const map = window.__tripApp.map();
          const original = map.isStyleLoaded.bind(map);
          let falseReads = control === 'transient' ? 1 : Number.POSITIVE_INFINITY;
          map.isStyleLoaded = () => {
            if (falseReads > 0) {
              falseReads -= 1;
              return false;
            }
            return original();
          };
        }""",
        control,
    )


def control_path(page, path: str, expected_task: dict) -> dict:
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
    opened = acceptance_sample(page, expected_task, panel_visible=True)
    page.keyboard.press("Escape")
    page.wait_for_function("document.querySelector('#mapOptionsPanel')?.hidden === true")
    page.wait_for_function("document.activeElement?.id === 'mapOptionsToggle'")
    page.wait_for_timeout(160)
    closed = acceptance_sample(
        page,
        expected_task,
        panel_visible=False,
        expected_focus_id="mapOptionsToggle",
    )
    return {
        "path": path,
        "opened": opened,
        "closed": closed,
        "task_preserved": task_state(page) == expected_task,
        "focus_returned": page.evaluate("document.activeElement?.id === 'mapOptionsToggle'"),
        "panel_closed": page.locator("#mapOptionsPanel").is_hidden(),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--viewport", choices=[f"{w}x{h}" for w, h in VIEWPORTS])
    parser.add_argument("--readiness-control", choices=("none", "transient", "never-ready"), default="none")
    parser.add_argument("--output", type=Path, default=OUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    viewports = VIEWPORTS if args.viewport is None else (tuple(map(int, args.viewport.split("x"))),)
    identity = candidate_identity()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report = bind_report(
        {
            "schema_version": 3,
            "change": "CHG-188 single-route map controls and camera context",
            "status": "FAIL",
            "route_ids": ROUTES,
            "readiness_control": args.readiness_control,
            "viewports": {},
            "failures": [],
            "errors": [],
            "screenshots": [],
            "negative_control": {"route_comparison_ui_absent": True},
        },
        identity,
    )
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        for width, height in viewports:
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
                install_style_control(page, args.readiness_control)
                baseline = acceptance_sample(page, baseline_task, panel_visible=False)
                if not baseline["passed"]:
                    row = {
                        "baseline_task": baseline_task,
                        "baseline_sample": baseline,
                        "comparison_chrome_count": baseline["initial_sample"].get("comparison_chrome_count"),
                        "page_errors": page_errors,
                        "pass": False,
                    }
                    report["viewports"][key] = row
                    report["failures"].append(f"{key}: baseline map context or bounded style readiness failed")
                    continue

                paths = {path: control_path(page, path, baseline_task) for path in PATHS}
                page.locator("#fitMap").click()
                page.wait_for_timeout(100)
                fit = acceptance_sample(page, baseline_task, panel_visible=False)
                screenshots = []
                if width in (390, 414):
                    target = SCREENSHOTS / f"map_controls_{key}_single_route.png"
                    target.parent.mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=str(target), full_page=True)
                    screenshots.append(str(target.relative_to(ROOT)))
                    report["screenshots"].append({"path": screenshots[-1], "candidate": identity["sha"], "candidate_tree": identity["tree"], "browser": "chromium", "viewport": key, "state": "single-route Yosemite map controls"})
                row = {
                    "baseline_task": baseline_task,
                    "task_after_controls": task_state(page),
                    "baseline_sample": baseline,
                    "fit_sample": fit,
                    "comparison_chrome_count": baseline["initial_sample"]["comparison_chrome_count"],
                    "paths": paths,
                    "screenshots": screenshots,
                    "page_errors": page_errors,
                }
                row["pass"] = (
                    baseline_task["routes"] == ROUTES
                    and baseline_task["primary_route"] == "A"
                    and baseline_task["date"] == "10/8"
                    and baseline_task["region"] == "yosemite"
                    and row["task_after_controls"] == baseline_task
                    and baseline["passed"]
                    and fit["passed"]
                    and all(
                        control["task_preserved"]
                        and control["focus_returned"]
                        and control["panel_closed"]
                        and control["opened"]["passed"]
                        and control["closed"]["passed"]
                        for control in paths.values()
                    )
                    and not page_errors
                )
                if not row["pass"]:
                    report["failures"].append(f"{key}: map controls changed task state, lost map context, or exposed route comparison chrome")
                report["viewports"][key] = row
            except Exception as error:
                report["errors"].append(f"{key}: {type(error).__name__}: {error}")
            finally:
                page.close()
                context.close()
        browser.close()
    report["negative_control"]["route_comparison_ui_absent"] = all(row.get("comparison_chrome_count") == 0 for row in report["viewports"].values()) and len(report["viewports"]) == len(viewports)
    report["status"] = "PASS" if not report["failures"] and not report["errors"] and len(report["viewports"]) == len(viewports) else "FAIL"
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "viewports": len(report["viewports"]), "failures": report["failures"], "errors": report["errors"], "output": str(args.output)}, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
