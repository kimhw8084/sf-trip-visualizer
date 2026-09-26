"""Capture the exact-bound R5 visual matrix for independent pixel review."""

from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

from qa_config import MODULAR_URL
from qa_evidence import ROOT, bind_report, candidate_identity


OUT = ROOT / "QA" / "CHG-232" / "visual"
SHOTS = OUT / "screenshots"


def capture(page, rows, name: str, viewport: tuple[int, int], mode: str, state: str, purpose: str, profile: str, profile_detail: str = "") -> None:
    path = SHOTS / f"{name}.png"
    page.screenshot(path=str(path), full_page=True)
    rows.append({"file": str(path.relative_to(ROOT)), "viewport": f"{viewport[0]}x{viewport[1]}", "browser": "chromium", "language": page.evaluate("document.documentElement.lang"), "theme": page.evaluate("document.documentElement.dataset.theme"), "mode": mode, "state": state, "task_purpose": purpose, "profile": profile, "profile_detail": profile_detail})


def wait_ready(page) -> None:
    page.wait_for_function("window.__tripApp?.map()?.isStyleLoaded()", timeout=30000)
    page.wait_for_function("document.querySelectorAll('.photo-marker').length > 0", timeout=15000)
    page.wait_for_timeout(180)


def new_page(browser, viewport: tuple[int, int]):
    context = browser.new_context(viewport={"width": viewport[0], "height": viewport[1]}, has_touch=viewport[0] < 500, is_mobile=viewport[0] < 500)
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(MODULAR_URL, wait_until="domcontentloaded", timeout=90000)
    wait_ready(page)
    return context, page, errors


def settle_map(page) -> None:
    page.evaluate("window.__tripApp.whenIdle()")
    page.wait_for_function("window.__tripApp?.map()?.areTilesLoaded?.() === true && !window.__tripApp.map().isMoving()", timeout=10000)
    page.evaluate("new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")


def select_region(page, region: str) -> None:
    if page.locator("#mapOptionsPanel").is_hidden():
        page.locator("#mapOptionsToggle").click()
        page.wait_for_function("document.querySelector('#mapOptionsPanel')?.hidden === false")
    page.locator(f"#regionControls [data-region='{region}']").click()
    settle_map(page)


def empty_state_metrics(page) -> dict:
    return page.evaluate("""() => {
      const a=window.__tripApp,m=a.map(),task=a.state.task,center=m.getCenter(),region=a.DATA.region_cfg[task.region];
      return {
        task:{region:task.region,date:task.date},
        visible_markers:a.DATA.markers.filter(marker=>a.markerVisible(marker,{map:true})).length,
        route_features:a.visibleRouteFeatures().length,
        camera:{center:[center.lng,center.lat],zoom:m.getZoom()},
        expected_region_camera:{center:[region.center.lon,region.center.lat],zoom:region.zoom},
        expected_region_label:region.label||task.region,
        selected_region_control_label:document.querySelector(`#regionControls [data-region="${task.region}"]`)?.textContent?.trim()||'',
        map_summary:document.querySelector('#mapCurrentSummary')?.textContent?.trim()||'',
        day_empty_text:document.querySelector('#dayPlan .empty-state')?.innerText?.trim()||'',
        canvas_count:document.querySelectorAll('.maplibregl-canvas').length
      };
    }""")


def capture_empty_state_holdouts(browser, rows: list[dict], errors: list[str]) -> None:
    combinations = [
        ((1440, 900), "ko", "dark", "region then date"),
        ((1440, 900), "en", "light", "date then region"),
        ((1440, 900), "en", "dark", "date then region"),
        ((390, 844), "ko", "light", "date then region"),
        ((390, 844), "ko", "dark", "region then date"),
        ((390, 844), "en", "light", "region then date"),
        ((390, 844), "en", "dark", "date then region"),
    ]
    for viewport, language, theme, ordering in combinations:
        context, page, page_errors = new_page(browser, viewport)
        if language == "en":
            page.locator("#langToggle").click()
            settle_map(page)
        if theme == "dark":
            page.locator("#themeToggle").click()
            page.wait_for_function("window.__tripApp?.state?.runtime?.mapVisualReady === true")
            settle_map(page)
        select_region(page, "yosemite")
        page.locator("#modeNav [data-mode='day']").click()
        page.locator("#dateSelect").select_option("10/9")
        settle_map(page)
        if ordering == "region then date":
            select_region(page, "sf")
            page.locator("#dateSelect").select_option("10/6")
            settle_map(page)
        else:
            page.locator("#dateSelect").select_option("10/6")
            settle_map(page)
            select_region(page, "sf")
        metrics = empty_state_metrics(page)
        name = f"empty_state_sf_10-6_{viewport[0]}x{viewport[1]}_{language}_{theme}_{ordering.replace(' ', '_')}"
        capture(page, rows, name, viewport, "day", "SF + Marin 10/6 no-results", "selected-region camera fallback with zero matching spatial data", "empty-state holdout", ordering)
        rows[-1]["empty_state_metrics"] = metrics
        expected = metrics["expected_region_camera"]
        actual = metrics["camera"]
        center_matches = all(abs(float(left) - float(right)) <= 1e-5 for left, right in zip(actual["center"], expected["center"]))
        if metrics["task"] != {"region": "sf", "date": "10/6"} or metrics["visible_markers"] != 0 or metrics["route_features"] != 0 or not center_matches or abs(actual["zoom"] - expected["zoom"]) > 0.01 or not metrics["day_empty_text"] or metrics["expected_region_label"] not in metrics["map_summary"] or metrics["selected_region_control_label"] != metrics["expected_region_label"] or metrics["canvas_count"] != 1:
            errors.append(f"{viewport[0]}x{viewport[1]} {language}/{theme} {ordering}: empty-state visual holdout does not match selected SF fallback and empty task state")
        errors.extend(f"{viewport[0]}x{viewport[1]} {language}/{theme}: {error}" for error in page_errors)
        page.close(); context.close()


def main() -> int:
    identity = candidate_identity()
    OUT.mkdir(parents=True, exist_ok=True)
    SHOTS.mkdir(parents=True, exist_ok=True)
    rows = []
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)

        context, page, page_errors = new_page(browser, (1440, 900))
        capture(page, rows, "canonical_decide_default_1440x900", (1440, 900), "decide", "recommended_default", "canonical-anchor", "canonical desktop default")
        page.locator("#mapOptionsToggle").click()
        capture(page, rows, "compact_map_options_open_1440x900", (1440, 900), "decide", "Map options open", "compact provider/region disclosure and focus return target", "canonical-anchor", "compact map options")
        page.locator("#providerControls [data-provider='vector']").click()
        page.locator("#mapOptionsToggle").click()
        page.locator("#regionControls [data-region='yosemite']").click()
        page.wait_for_timeout(300)
        capture(page, rows, "compact_map_region_yosemite_1440x900", (1440, 900), "decide", "Yosemite selected", "semantic region change through compact map options", "canonical-anchor", "region change")
        capture(page, rows, "single_route_plan_1440x900", (1440, 900), "decide", "Route A — Temporal Arbitrage Master", "single configured plan and its decision rules", "canonical-anchor", "single route Decide")
        page.locator("#modeNav [data-mode='day']").click()
        page.locator("#dateSelect").select_option("10/8")
        settle_map(page)
        capture(page, rows, "canonical_day_dense_recovery_1440x900", (1440, 900), "day", "10/8", "dense Day with recovery and typed decisions", "canonical-anchor", "canonical dense day")
        page.locator("#dateSelect").select_option("10/9")
        settle_map(page)
        capture(page, rows, "canonical_day_sparse_1440x900", (1440, 900), "day", "10/9", "sparse/recovery Day state", "canonical-anchor", "canonical sparse day")
        page.locator("#mapOptionsToggle").click()
        page.locator("#regionControls [data-region='sf']").click()
        page.locator("#dateSelect").select_option("10/6")
        settle_map(page)
        capture(page, rows, "canonical_no_results_1440x900", (1440, 900), "day", "SF + 10/6 no-results", "no-results handling", "canonical-anchor", "R17 region then date ordering; Yosemite 10/9 predecessor context")
        page.locator("#mapOptionsToggle").click()
        page.locator("#regionControls [data-region='yosemite']").click()
        page.locator("#dateSelect").select_option("10/7")
        page.locator(".photo-marker[data-place-key='cooks']").click()
        capture(page, rows, "canonical_peek_cooks_1440x900", (1440, 900), "day", "Yosemite 10/7 Cook's Meadow Peek", "Peek context and real marker target", "canonical-anchor", "marker peek")
        page.locator("#peek [data-peek-open]").click()
        page.wait_for_function("window.__tripApp.state.presentation.mode==='place'")
        capture(page, rows, "canonical_place_inspector_1440x900", (1440, 900), "place", "Cook's Meadow Inspector", "Peek → Inspector → return context", "canonical-anchor", "place inspector")
        page.locator("[data-place-back]").click()
        page.locator("#langToggle").click()
        page.locator("#themeToggle").click()
        capture(page, rows, "canonical_en_dark_1440x900", (1440, 900), "day", "English + dark", "KO/EN and semantic dark tokens", "canonical-anchor", "i18n theme")
        page.locator("#workbench [data-sheet='compact']").click()
        capture(page, rows, "canonical_workbench_compact_1440x900", (1440, 900), "day", "desktop compact", "collapsed workbench and persistent map", "canonical-anchor", "desktop compact")
        page.locator("#workbenchToggle").click()
        capture(page, rows, "canonical_workbench_expanded_1440x900", (1440, 900), "day", "desktop expanded", "expanded workbench", "canonical-anchor", "desktop expanded")
        page.locator("#workbench [data-sheet='full']").click()
        capture(page, rows, "canonical_workbench_full_1440x900", (1440, 900), "day", "desktop full", "full workbench composition", "canonical-anchor", "desktop full")
        errors.extend(page_errors)
        page.close(); context.close()

        for viewport, profile in (((1366, 768), "stress desktop"), ((1920, 1080), "stress desktop large"), ((390, 844), "stress mobile portrait"), ((360, 800), "stress mobile narrow"), ((844, 390), "stress mobile landscape"), ((1600, 900), "fresh holdout desktop"), ((375, 812), "fresh holdout mobile"), ((1536, 864), "additional desktop holdout"), ((414, 896), "additional mobile holdout")):
            context, page, page_errors = new_page(browser, viewport)
            capture(page, rows, f"stress_decide_{viewport[0]}x{viewport[1]}", viewport, "decide", "recommended_default", "responsive route recommendation", "holdout" if "holdout" in profile else "stress", profile)
            if viewport[0] < 500:
                page.locator("#workbench [data-sheet='compact']").click()
                capture(page, rows, f"mobile_compact_{viewport[0]}x{viewport[1]}", viewport, "decide", "mobile compact", "mobile compact task sheet", "stress", "mobile compact")
                page.locator("#mapOptionsToggle").click()
                capture(page, rows, f"mobile_compact_map_options_{viewport[0]}x{viewport[1]}", viewport, "decide", "mobile compact map options", "compact provider/region disclosure", "stress", "mobile compact map options")
                page.keyboard.press("Escape")
                page.locator("#workbench [data-sheet='expanded']").click()
                capture(page, rows, f"mobile_expanded_{viewport[0]}x{viewport[1]}", viewport, "decide", "mobile expanded", "mobile expanded task sheet", "stress", "mobile expanded")
                page.locator("#workbench [data-sheet='full']").click()
                capture(page, rows, f"mobile_full_{viewport[0]}x{viewport[1]}", viewport, "decide", "mobile full", "mobile full task sheet", "stress", "mobile full")
            errors.extend(page_errors)
            page.close(); context.close()

        context, page, page_errors = new_page(browser, (390, 844))
        page.locator("#mapOptionsToggle").click()
        page.locator("#regionControls [data-region='yosemite']").click()
        page.locator("#modeNav [data-mode='day']").click()
        page.locator("#dateSelect").select_option("10/7")
        marker = page.locator(".photo-marker[data-place-key='cooks']")
        page.wait_for_function("document.querySelector('.photo-marker[data-place-key=\"cooks\"]')?.getBoundingClientRect().width > 0")
        marker.focus()
        page.wait_for_selector("#peek.show")
        capture(page, rows, "mobile_keyboard_peek_390x844", (390, 844), "day", "keyboard Cook's Meadow Peek", "keyboard-only marker discovery", "stress", "keyboard path")
        page.evaluate("window.__tripApp.hidePreview({returnFocus:false})")
        marker.tap()
        page.wait_for_selector("#peek.show")
        capture(page, rows, "mobile_touch_peek_390x844", (390, 844), "day", "touch Cook's Meadow Peek", "touch marker discovery", "stress", "touch path")
        errors.extend(page_errors)
        page.close(); context.close()

        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()
        page_errors = []
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        page.goto(MODULAR_URL, wait_until="domcontentloaded", timeout=90000)
        page.screenshot(path=str(SHOTS / "startup_immediate_1440x900.png"), full_page=True)
        rows.append({"file": str((SHOTS / "startup_immediate_1440x900.png").relative_to(ROOT)), "viewport": "1440x900", "browser": "chromium", "language": page.evaluate("document.documentElement.lang"), "theme": page.evaluate("document.documentElement.dataset.theme"), "mode": "initialization", "state": "immediate after DOM navigation", "task_purpose": "immediate/non-artificial loading observation", "profile": "stress"})
        page.close(); context.close()

        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()
        failure_errors = []
        page.on("pageerror", lambda error: failure_errors.append(str(error)))
        page.route("**/assets/vector/**", lambda route: route.abort())
        page.goto(MODULAR_URL, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_selector("#mapError:not([hidden])", timeout=30000)
        capture(page, rows, "smart_failure_1440x900", (1440, 900), "decide", "Smart local asset failure", "fail-closed Smart map recovery surface", "stress", "Smart failure")
        errors.extend(failure_errors)
        page.close(); context.close()

        context, page, failure_errors = new_page(browser, (1440, 900))
        page.route("https://server.arcgisonline.com/**", lambda route: route.abort())
        page.evaluate("window.__tripApp.chooseProvider('satellite')")
        page.wait_for_selector("#mapError:not([hidden])", timeout=10000)
        capture(page, rows, "satellite_failure_recovery_1440x900", (1440, 900), "decide", "Satellite failure → Smart recovery", "provider failure and recovery", "stress", "Satellite recovery")
        errors.extend(failure_errors)
        page.close(); context.close()
        capture_empty_state_holdouts(browser, rows, errors)
        browser.close()

    for row in rows:
        row["candidate"] = identity["sha"]
        row["candidate_tree"] = identity["tree"]
    report = {"schema_version": 3, "status": "PASS" if rows and not errors else "FAIL", "base": "7d5d8727b1772642e87311d91d087e211656f6e4", "rows": rows, "errors": errors, "canonical_anchors": ["1440x900 desktop", "390x844 mobile"], "stress_profiles": ["1366x768", "1920x1080", "360x800", "844x390", "200% reflow via accessibility oracle"], "fresh_holdouts": {"profiles": ["1600x900 desktop", "375x812 mobile"], "frozen_after": identity["sha"], "tuning_status": "captured after source freeze; no new failure class recorded by script"}, "notes": ["Candidate-bound screenshots for the single-route redesign; native Safari, physical devices and independent human/field evidence remain separate."]}
    bind_report(report, identity)
    OUT.joinpath("visual_index.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "screenshots": len(rows), "errors": errors}, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
