"""Direct R5 compact-mobile route-key camera and visual-context oracle."""

from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

from qa_config import MODULAR_URL
from qa_evidence import bind_report, candidate_identity


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "QA" / "project_os_verify" / "ui_revamp_r5"
VIEWPORTS = ((360, 800), (375, 812), (390, 844), (414, 896))
PATHS = ("pointer", "keyboard", "touch")


def snapshot(page) -> dict:
    return page.evaluate(
        """() => {
          const state = window.__tripApp.state;
          return {
            task: {
              primary_route: state.task.primaryRoute,
              compare_routes: [...state.task.compareRoutes].sort(),
              routes: [...state.task.routes].sort(),
              date: state.task.date,
              region: state.task.region,
              selected: state.task.selected,
              selected_occurrence: state.task.selectedOccurrence,
            },
            presentation: {
              mode: state.presentation.mode,
              sheet: state.presentation.sheet,
              lang: state.presentation.lang,
              theme: state.presentation.theme,
              map_options_open: state.presentation.mapOptionsOpen,
              peek_open: Boolean(state.presentation.peek),
            },
          };
        }"""
    )


def camera(page) -> dict:
    return page.evaluate(
        """() => {
          const map = window.__tripApp.map();
          const center = map.getCenter();
          return {
            center: {lng: center.lng, lat: center.lat},
            zoom: map.getZoom(),
            bearing: map.getBearing(),
            pitch: map.getPitch(),
          };
        }"""
    )


def spatial_context(page) -> dict:
    return page.evaluate(
        """() => {
          const app = window.__tripApp;
          const map = app.map();
          const canvas = map.getCanvas();
          const width = canvas.clientWidth;
          const height = canvas.clientHeight;
          const markers = app.DATA.markers.filter(marker => app.markerVisible(marker, {map: true}));
          const routeCoordinates = app.visibleRouteFeatures()
            .filter(feature => feature.properties.kind !== 'transfer')
            .flatMap(feature => feature.geometry.coordinates);
          const markerCoordinates = markers.map(marker => [marker.lon, marker.lat]);
          const project = coordinate => map.project(coordinate);
          const points = [...markerCoordinates, ...routeCoordinates].map(project);
          const inFrame = point => point.x >= 0 && point.x <= width && point.y >= 0 && point.y <= height;
          const visiblePoints = points.filter(inFrame);
          const xs = visiblePoints.map(point => point.x);
          const ys = visiblePoints.map(point => point.y);
          const markerElements = [...document.querySelectorAll('.photo-marker, .photo-cluster, .route-leg-label')]
            .filter(element => {
              const style = getComputedStyle(element);
              const rect = element.getBoundingClientRect();
              return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
            });
          const markerHits = markerElements.map(element => {
            const rect = element.getBoundingClientRect();
            const target = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
            return {
              key: element.dataset.placeKey || element.className,
              hit: target?.closest?.('.photo-marker, .photo-cluster, .route-leg-label')?.className || target?.className || null,
              intercepted_by_route_panel: Boolean(target?.closest?.('#routeLegendPanel')),
            };
          });
          return {
            canvas_count: document.querySelectorAll('.maplibregl-canvas').length,
            style_loaded: map.isStyleLoaded(),
            canvas: {width, height},
            marker_count: markers.length,
            rendered_marker_count: markerElements.length,
            route_feature_count: app.visibleRouteFeatures().length,
            point_count: points.length,
            points_in_frame: visiblePoints.length,
            route_points_in_frame: routeCoordinates.map(project).filter(inFrame).length,
            marker_points_in_frame: markerCoordinates.map(project).filter(inFrame).length,
            occupied_width_ratio: width ? (Math.max(...xs, 0) - Math.min(...xs, width)) / width : 0,
            occupied_height_ratio: height ? (Math.max(...ys, 0) - Math.min(...ys, height)) / height : 0,
            marker_hits: markerHits,
          };
        }"""
    )


def camera_delta(before: dict, after: dict) -> dict:
    return {
        "center_lng": abs(after["center"]["lng"] - before["center"]["lng"]),
        "center_lat": abs(after["center"]["lat"] - before["center"]["lat"]),
        "zoom": abs(after["zoom"] - before["zoom"]),
        "bearing": abs(after["bearing"] - before["bearing"]),
        "pitch": abs(after["pitch"] - before["pitch"]),
    }


def camera_neutral(delta: dict) -> bool:
    return max(delta.values()) <= 0.002


def context_passes(context: dict) -> bool:
    if context["canvas_count"] != 1 or not context["style_loaded"]:
        return False
    if context["canvas"]["width"] <= 0 or context["canvas"]["height"] <= 0:
        return False
    if context["route_feature_count"] <= 0 or context["point_count"] <= 0:
        return False
    if context["points_in_frame"] < context["point_count"] * 0.9:
        return False
    if context["occupied_width_ratio"] < 0.18 or context["occupied_height_ratio"] < 0.08:
        return False
    return all(
        not row["intercepted_by_route_panel"]
        and any(token in str(row["hit"] or "") for token in ("photo-marker", "photo-cluster", "route-leg-label"))
        for row in context["marker_hits"]
    )


def activate(page, path: str) -> None:
    toggle = page.locator("#routeLegendToggle")
    if path == "pointer":
        toggle.click()
    elif path == "keyboard":
        toggle.focus()
        page.keyboard.press("Enter")
    else:
        toggle.tap()
    page.wait_for_function("document.querySelector('#routeLegendPanel')?.hidden === false")


def close_with_escape(page) -> None:
    page.keyboard.press("Escape")
    page.wait_for_function("document.querySelector('#routeLegendPanel')?.hidden === true")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    identity = candidate_identity()
    report = {
        "schema_version": 1,
        "change": "CHG-157 R5 compact-mobile route-key camera safety",
        "status": "FAIL",
        "camera_contract": "Compact-mobile route-key disclosure is camera-neutral within renderer noise; Fit-map remains an explicit action.",
        "viewports": {},
        "failures": [],
        "errors": [],
        "screenshots": [],
        "fresh_holdout": {"viewport": "414x896", "used_for_tuning": False},
        "notes": [
            "All disclosure paths use real Playwright pointer, keyboard, or touch input.",
            "Spatial context is measured from projected route and marker coordinates, not only DOM rectangle intersection.",
            "Native Safari, physical-device behavior, and independent pixel review remain external evidence boundaries.",
        ],
    }

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        for width, height in VIEWPORTS:
            viewport_key = f"{width}x{height}"
            viewport_report = {"paths": {}, "screenshots": []}
            context = browser.new_context(
                viewport={"width": width, "height": height},
                has_touch=True,
                is_mobile=True,
            )
            page = context.new_page()
            page_errors: list[str] = []
            page.on("pageerror", lambda error: page_errors.append(str(error)))
            try:
                page.goto(MODULAR_URL, wait_until="domcontentloaded", timeout=90000)
                page.wait_for_function("window.__tripApp?.state?.runtime?.mapVisualReady === true", timeout=30000)
                page.wait_for_selector("#routeLegendToggle", state="visible", timeout=15000)
                page.locator('[data-sheet="compact"]').click()
                page.wait_for_function("window.__tripApp.state.presentation.sheet === 'compact' && document.querySelector('#app[data-sheet=compact]')")
                page.wait_for_timeout(120)
                baseline_state = snapshot(page)
                baseline_camera = camera(page)
                baseline_context = spatial_context(page)
                pointer_done = False
                for path in PATHS:
                    if path != "pointer":
                        if page.locator("#routeLegendPanel").is_visible():
                            close_with_escape(page)
                        if page.evaluate("document.activeElement?.id") != "routeLegendToggle":
                            page.locator("#routeLegendToggle").focus()
                    activate(page, path)
                    page.wait_for_timeout(120)
                    open_state = snapshot(page)
                    open_camera = camera(page)
                    open_context = spatial_context(page)
                    panel_items = page.locator("#routeLegendPanel .route-legend-item").count()
                    route_labels = page.locator("#routeLegendPanel .route-legend-item strong").all_inner_texts()
                    open_focus = page.evaluate("document.activeElement?.id || document.activeElement?.className || null")
                    open_row = {
                        "path": path,
                        "focus_on_open": open_focus,
                        "aria_expanded": page.locator("#routeLegendToggle").get_attribute("aria-expanded"),
                        "panel_visible": page.locator("#routeLegendPanel").is_visible(),
                        "panel_items": panel_items,
                        "route_labels": route_labels,
                        "state_preserved_on_open": open_state == baseline_state,
                        "camera_before": baseline_camera,
                        "camera_open": open_camera,
                        "camera_delta_open": camera_delta(baseline_camera, open_camera),
                        "spatial_context_open": open_context,
                    }
                    open_row["open_pass"] = bool(
                        open_row["panel_visible"]
                        and open_row["aria_expanded"] == "true"
                        and panel_items == len(baseline_state["task"]["routes"])
                        and len(route_labels) == panel_items
                        and camera_neutral(open_row["camera_delta_open"])
                        and open_context == baseline_context
                        and context_passes(open_context)
                    )
                    close_with_escape(page)
                    closed_state = snapshot(page)
                    closed_camera = camera(page)
                    closed_context = spatial_context(page)
                    closed_focus = page.evaluate("document.activeElement?.id || document.activeElement?.className || null")
                    open_row.update(
                        {
                            "focus_after_escape": closed_focus,
                            "panel_hidden_after_escape": page.locator("#routeLegendPanel").is_hidden(),
                            "state_preserved_on_close": closed_state == baseline_state,
                            "camera_closed": closed_camera,
                            "camera_delta_close": camera_delta(baseline_camera, closed_camera),
                            "spatial_context_closed": closed_context,
                        }
                    )
                    open_row["close_pass"] = bool(
                        open_row["panel_hidden_after_escape"]
                        and closed_focus == "routeLegendToggle"
                        and open_row["state_preserved_on_close"]
                        and camera_neutral(open_row["camera_delta_close"])
                        and closed_context == baseline_context
                        and context_passes(closed_context)
                    )
                    viewport_report["paths"][path] = open_row
                    if not open_row["open_pass"]:
                        report["failures"].append(f"{viewport_key}:{path}: route-key open contract failed")
                    if not open_row["close_pass"]:
                        report["failures"].append(f"{viewport_key}:{path}: route-key Escape close contract failed")
                    if path == "pointer":
                        pointer_done = True
                        for state_name in ("open", "closed"):
                            filename = f"route_key_{state_name}_{viewport_key}.png"
                            path_out = OUT / filename
                            if state_name == "open":
                                activate(page, "pointer")
                                page.wait_for_timeout(80)
                            else:
                                close_with_escape(page)
                            page.screenshot(path=str(path_out), full_page=True)
                            screenshot = {
                                "path": str(path_out.relative_to(ROOT)),
                                "candidate": identity["sha"],
                                "candidate_tree": identity["tree"],
                                "browser": "chromium",
                                "viewport": viewport_key,
                                "state": state_name,
                                "route_key_path": "pointer",
                            }
                            viewport_report["screenshots"].append(screenshot)
                            report["screenshots"].append(screenshot)
                if not pointer_done:
                    report["failures"].append(f"{viewport_key}: pointer path did not run")
            except Exception as error:
                report["errors"].append(f"{viewport_key}: {type(error).__name__}: {error}")
            if page_errors:
                report["errors"].extend(f"{viewport_key}: pageerror: {error}" for error in page_errors)
            report["viewports"][viewport_key] = viewport_report
            page.close()
            context.close()
        browser.close()

    report["status"] = "PASS" if not report["failures"] and not report["errors"] and len(report["viewports"]) == len(VIEWPORTS) else "FAIL"
    bind_report(report, identity)
    (OUT / "route_key_camera.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "viewports": len(report["viewports"]), "failures": report["failures"], "errors": report["errors"]}, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
