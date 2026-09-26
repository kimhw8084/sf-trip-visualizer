"""Machine task/state oracles for the CHG-157 Decide → Day → Place workbench."""

from __future__ import annotations

import json
import os
from pathlib import Path

from playwright.sync_api import sync_playwright

from qa_config import MODULAR_URL
from qa_evidence import bind_report, candidate_identity
from trip_package import DEFAULT_PACKAGE, load_package


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "QA" / "CHG-232" / "decision_workbench"
OUT.mkdir(parents=True, exist_ok=True)
IDENTITY = candidate_identity()
PACKAGE = load_package(DEFAULT_PACKAGE)
DATA = PACKAGE["data"]
ROUTE_IDS = sorted(DATA["routes"])
PRIMARY_ROUTE = ROUTE_IDS[0]
PROVIDERS = sorted(PACKAGE["providers"])
VECTOR_PROVIDER = next(key for key, value in PACKAGE["providers"].items() if value.get("kind") == "vector")
RASTER_PROVIDER = next(key for key, value in PACKAGE["providers"].items() if value.get("kind") == "raster")
RASTER_HOST = PACKAGE["source_policy"]["external"][RASTER_PROVIDER]["host"]
DAY_ROWS = {day["key"]: [item for item in DATA["timeline"] if item.get("date_key", item.get("date")) == day["key"]] for day in DATA["dates"]}
DENSE_DATE = next(key for key, rows in DAY_ROWS.items() if any(item.get("spatial_keys") for item in rows))
SPARSE_DATE = next(key for key, rows in DAY_ROWS.items() if rows and not any(item.get("spatial_keys") for item in rows))
REGION_WITH_PLACES = next(key for key in DATA["region_cfg"] if key != "overall" and any(DATA["place_region"].get(marker["place_key"]) == key for marker in DATA["markers"]))


def oracle(name: str, passed: bool, detail: object = None) -> dict:
    row = {"id": name, "status": "PASS" if passed else "FAIL"}
    if detail is not None:
        row["detail"] = detail
    return row


results: list[dict] = []
errors: list[str] = []
screenshots: list[dict] = []

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(MODULAR_URL, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_function("window.__tripApp?.map()?.isStyleLoaded()", timeout=30000)
    page.wait_for_function("window.__tripApp?.state?.runtime?.mapVisualReady === true", timeout=30000)

    def activate_visible_place_marker() -> str:
        marker = page.locator(".photo-marker:visible").first
        if marker.count() == 0:
            cluster = page.locator(".photo-cluster:visible").first
            if cluster.count() == 0:
                raise AssertionError("No visible place marker or cluster is available for pointer activation")
            cluster.click()
            page.wait_for_function("!!document.querySelector('.photo-marker:not([style*=\"display: none\"])')", timeout=15000)
            marker = page.locator(".photo-marker:visible").first
        key = marker.get_attribute("data-place-key")
        marker.click()
        return key

    def shot(name: str, viewport: tuple[int, int], mode: str, state: str) -> None:
        path = OUT / f"{name}.png"
        page.screenshot(path=str(path), full_page=True)
        screenshots.append({"path": str(path.relative_to(ROOT)), "candidate": IDENTITY["sha"], "candidate_tree": IDENTITY["tree"], "browser": "chromium", "viewport": f"{viewport[0]}x{viewport[1]}", "language": page.evaluate("document.documentElement.lang"), "theme": page.evaluate("document.documentElement.dataset.theme"), "mode": mode, "state": state, "purpose": name})

    results.append(oracle("decide_recommendation", page.locator("#recommendation").is_visible() and PRIMARY_ROUTE in page.locator("#recommendation").inner_text() and all(text in page.locator("#recommendation").inner_text() for text in ("감수할 것", "선택·전환 규칙", "후회 방지"))))
    results.append(oracle("single_authority_controls", page.locator("#dateSelect").count() == 1 and page.locator("#providerControls [data-provider]").count() == len(PROVIDERS) and page.locator("#regionControls [data-region]").count() == len(DATA["region_cfg"]) and page.locator("#peek").count() == 1))
    page.locator("#mapOptionsToggle").click()
    page.wait_for_function("document.querySelector('#mapOptionsPanel')?.hidden === false && document.activeElement?.id === 'mapOptionsClose'")
    options_open = page.locator("#mapOptionsPanel").is_visible() and page.evaluate("document.activeElement?.id === 'mapOptionsClose'")
    page.keyboard.press("Escape")
    page.wait_for_function("document.querySelector('#mapOptionsPanel')?.hidden === true && document.activeElement?.id === 'mapOptionsToggle'")
    options_closed = page.locator("#mapOptionsPanel").is_hidden() and page.evaluate("document.activeElement?.id === 'mapOptionsToggle'") and page.locator("#mapOptionsPanel button:visible").count() == 0
    results.append(oracle("compact_map_options_focus_contract", options_open and options_closed))
    page.locator("#mapOptionsToggle").click()
    page.locator(f"#providerControls [data-provider='{VECTOR_PROVIDER}']").click()
    page.wait_for_function("provider=>window.__tripApp.state.runtime.provider===provider", arg=VECTOR_PROVIDER)
    page.locator("#mapOptionsToggle").click()
    page.locator(f"#regionControls [data-region='{REGION_WITH_PLACES}']").click()
    page.wait_for_function("region=>window.__tripApp.state.task.region===region", arg=REGION_WITH_PLACES)
    page.locator("#mapOptionsToggle").click()
    page.locator("#regionControls [data-region='overall']").click()
    page.wait_for_function("window.__tripApp.state.task.region === 'overall'")
    results.append(oracle("compact_map_options_provider_region_selection", page.evaluate("provider=>window.__tripApp.state.runtime.provider===provider&&window.__tripApp.state.task.region==='overall'", VECTOR_PROVIDER)))
    results.append(oracle("legacy_surface_removed", page.locator("#dateRibbon,#mapSchedule,#mapFocus,#routeTip,#mobileDate,#mobileProvider").count() == 0))
    comparison_chrome = page.locator("[data-compare-route],#comparePanel,.route-compare,.route-membership,.membership-cell,.inspector-membership").count()
    results.append(oracle("route_cards_follow_package_routes", comparison_chrome == 0 and page.locator("#routeCards .route-card").count() == len(ROUTE_IDS)))
    shot("decide_default_desktop", (1440, 900), "decide", "recommended_default")

    results.append(oracle("route_code_matches_active_runtime", page.locator("#recommendation").inner_text().count(PRIMARY_ROUTE) >= 1 and page.locator("#routeCards .route-card").count() == len(ROUTE_IDS)))

    page.locator('#modeNav [data-mode="day"]').click()
    page.locator("#dateSelect").select_option(DENSE_DATE)
    day_text = page.locator("#dayPlan").inner_text()
    page.locator("#dateSelect").select_option(SPARSE_DATE)
    non_spatial_count = page.locator("#dayPlan .plan-card").count()
    page.locator("#dateSelect").select_option(DENSE_DATE)
    results.append(oracle("day_semantic_items", page.locator("#dayPlan .day-item").count() > 0 and non_spatial_count > 0 and page.locator("#dayPlan .tier-chip").count() > 0, {"sparse_date": SPARSE_DATE, "non_spatial_cards": non_spatial_count, "day_text_present": bool(day_text)}))
    results.append(oracle("day_single_date_authority", page.locator("#dateSelect").input_value() == DENSE_DATE and page.locator("#dayView").is_visible()))
    shot("day_selected_desktop", (1440, 900), "day", f"{DENSE_DATE}_dense_recovery")

    activate_visible_place_marker()
    page.wait_for_selector("#peek.show")
    peek_text = page.locator("#peek").inner_text()
    results.append(oracle("place_peek", page.locator("#peek.show").count() == 1 and page.locator("#peek img").count() == 1 and "왜 지금" in peek_text))
    page.locator("#peek [data-peek-open]").evaluate("element => element.click()")
    page.wait_for_function("window.__tripApp.state.presentation.mode==='place'")
    results.append(oracle("place_inspector", page.locator("#placeView:not([hidden])").count() == 1 and page.locator("#placeInspector .photo-slot img").count() == 3 and page.locator("#placeInspector .place-glance").count() == 1))
    page.locator("[data-place-back]").click()
    results.append(oracle("place_return_context", page.evaluate("window.__tripApp.state.presentation.mode") == "day" and page.input_value("#dateSelect") == DENSE_DATE))
    shot("place_inspector_desktop", (1440, 900), "place", "inspector_after_peek")

    page.locator("#dateSelect").select_option("all")
    page.locator("#mapOptionsToggle").click()
    page.locator("#regionControls [data-region='overall']").click()
    pointer_place = activate_visible_place_marker()
    results.append(oracle("place_marker_real_pointer_activation", page.locator("#peek.show").count() == 1 and page.evaluate("place=>window.__tripApp.state.task.selected===place", pointer_place), pointer_place))
    page.keyboard.press("Escape")
    page.locator("#dateSelect").select_option(DENSE_DATE)
    page.route(f"https://{RASTER_HOST}/**", lambda route: route.abort())
    page.evaluate("provider=>window.__tripApp.chooseProvider(provider)", RASTER_PROVIDER)
    page.wait_for_timeout(3500)
    results.append(oracle("raster_failure_recovery", page.evaluate("provider=>window.__tripApp.state.provider===provider", VECTOR_PROVIDER) and page.locator("#mapError:not([hidden])").count() == 1 and page.input_value("#dateSelect") == DENSE_DATE and page.evaluate("window.__tripApp.state.task.primaryRoute") == PRIMARY_ROUTE))

    page.set_viewport_size({"width": 390, "height": 844})
    page.wait_for_timeout(450)
    results.append(oracle("mobile_sheet_reflow", page.evaluate("document.documentElement.scrollWidth <= innerWidth") and page.locator("#workbench[data-sheet]").count() == 1 and page.locator("#dateSelect").count() == 1))
    page.locator('[data-sheet="compact"]').click()
    results.append(oracle("mobile_compact_non_drag", page.locator('#workbench[data-sheet="compact"]').count() == 1 and page.locator(".workbench-scroll").is_hidden()))
    page.locator('[data-sheet="expanded"]').click()
    results.append(oracle("mobile_expanded_non_drag", page.locator('#workbench[data-sheet="expanded"]').count() == 1 and not page.locator(".workbench-scroll").is_hidden()))
    activate_visible_place_marker()
    page.locator('#modeNav [data-mode="place"]').click()
    results.append(oracle("mobile_mode_identity", page.evaluate("window.__tripApp.state.presentation.mode") == "place"))
    shot("place_mobile_expanded", (390, 844), "place", "expanded_sheet")
    page.evaluate("document.documentElement.style.fontSize='200%'")
    page.wait_for_timeout(250)
    results.append(oracle("mobile_200_percent_reflow", page.evaluate("document.documentElement.scrollWidth <= innerWidth") and page.locator("#workbench").is_visible() and page.locator("[data-place-back]").is_visible()))
    browser.close()

report = {"schema_version": 2, "change": "CHG-232", "status": "PASS" if not errors and all(row["status"] == "PASS" for row in results) else "FAIL", "base": "7d5d8727b1772642e87311d91d087e211656f6e4", "results": results, "errors": errors, "screenshots": screenshots, "reserved_holdouts": ["1536x864 desktop", "414x896 mobile"], "notes": ["Candidate-bound Chromium evidence; native Safari, physical-device and independent-human evidence remain external."]}
bind_report(report, IDENTITY)
(OUT / "task_oracles.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"status": report["status"], "passed": sum(row["status"] == "PASS" for row in results), "total": len(results), "errors": errors}, ensure_ascii=False, indent=2))
raise SystemExit(0 if report["status"] == "PASS" else 1)
