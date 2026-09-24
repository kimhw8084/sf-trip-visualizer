"""R5 mobile sheet geometry, state, focus, and real-pointer regression oracle."""

from __future__ import annotations

import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from qa_config import MODULAR_URL
from qa_evidence import ROOT, bind_report, candidate_identity


OUT = ROOT / "QA" / "CHG-188" / "sheet_geometry.json"
VIEWPORTS = ((360, 800), (390, 844), (414, 896), (844, 390), (375, 812), (1600, 900))
MOBILE_PORTRAITS = {(360, 800), (390, 844), (414, 896), (375, 812)}


def wait_ready(page) -> None:
    page.goto(MODULAR_URL, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_function("window.__tripApp?.map()?.isStyleLoaded()", timeout=30000)
    page.wait_for_function("document.querySelectorAll('.photo-marker').length > 0", timeout=15000)
    page.evaluate("window.__tripApp.whenGeometryIdle()")


def snapshot(page) -> dict:
    return page.evaluate(
        """
        () => {
          const app = window.__tripApp;
          const geometry = app.mapGeometrySnapshot();
          const scroll = document.querySelector('#workbench .workbench-scroll');
          const active = document.activeElement;
          return {
            sheet: app.state.presentation.sheet,
            task: {
              primary_route: app.state.task.primaryRoute,
              date: app.state.task.date,
              region: app.state.task.region,
              selected: app.state.task.selected,
              mode: app.state.presentation.mode,
              provider: app.state.runtime.provider,
              lang: app.state.presentation.lang,
              theme: app.state.presentation.theme,
            },
            geometry: geometry.sheet_geometry,
            map: geometry.shell,
            useful_map_ratio: geometry.sheet_geometry?.useful_map_ratio ?? null,
            scroll_hidden: Boolean(scroll?.hidden),
            scroll_inert: Boolean(scroll?.inert),
            scroll_visible_focusables: scroll ? [...scroll.querySelectorAll('button,a,select,input,textarea,[tabindex]')].filter(element => element.getClientRects().length && getComputedStyle(element).visibility !== 'hidden').length : 0,
            active_element: active?.id || active?.dataset?.sheet || active?.tagName || null,
            horizontal_overflow: document.documentElement.scrollWidth > window.innerWidth,
          };
        }
        """
    )


def activate(page, sheet: str, method: str) -> dict:
    started = time.perf_counter()
    button = page.locator(f"#workbench [data-sheet='{sheet}']")
    if method == "keyboard":
        button.focus()
        page.keyboard.press("Enter")
    elif method == "touch":
        button.tap()
    else:
        button.click()
    page.wait_for_function("sheet => window.__tripApp.state.presentation.sheet === sheet", arg=sheet)
    page.evaluate("window.__tripApp.whenGeometryIdle()")
    page.wait_for_timeout(60)
    row = snapshot(page)
    row["transition_ms"] = round((time.perf_counter() - started) * 1000, 2)
    return row


def task_signature(row: dict) -> dict:
    return row["task"]


def prepare_context(page) -> dict:
    page.locator("#mapOptionsToggle").click()
    page.locator("#regionControls [data-region='yosemite']").click()
    page.locator("#modeNav [data-mode='day']").click()
    page.locator("#dateSelect").select_option("10/7")
    page.wait_for_function("document.querySelector('.photo-marker[data-place-key=\"cooks\"]')?.getBoundingClientRect().width > 0")
    page.locator(".photo-marker[data-place-key='cooks']").click()
    page.locator("#langToggle").click()
    page.locator("#themeToggle").click()
    page.evaluate("window.__tripApp.hidePreview({returnFocus:false})")
    page.evaluate("window.__tripApp.whenIdle()")
    return snapshot(page)


def transition_rows(page, method: str) -> tuple[list[dict], list[str]]:
    failures = []
    rows = []
    expected_task = task_signature(snapshot(page))
    for sheet in ("compact", "expanded", "full", "expanded", "compact"):
        row = activate(page, sheet, method)
        row["activation"] = method
        rows.append(row)
        if row["task"] != expected_task:
            failures.append(f"{method}:{sheet}: task state changed")
        if row["horizontal_overflow"]:
            failures.append(f"{method}:{sheet}: horizontal overflow")
        if sheet == "compact" and (
            not row["scroll_hidden"]
            or not row["scroll_inert"]
            or row["scroll_visible_focusables"]
            or row["geometry"]["workbench_height"] >= 220
        ):
            failures.append(f"{method}:{sheet}: compact content is not hidden/inert or sheet is oversized")
        if sheet != "compact" and (row["scroll_hidden"] or row["scroll_inert"]):
            failures.append(f"{method}:{sheet}: workbench content remained hidden/inert")
        if method in {"keyboard", "pointer", "touch"} and row["active_element"] not in {sheet, "workbenchToggle"}:
            failures.append(f"{method}:{sheet}: focus not on size control or predictable desktop toggle ({row['active_element']})")
    return rows, failures


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    identity = candidate_identity()
    report = {
        "schema_version": 1,
        "change": "CHG-188 single-route mobile compact-sheet geometry regression",
        "status": "FAIL",
        "viewports": {},
        "transition_rows": [],
        "failures": [],
        "orientation_rule": "The explicit sheet state is preserved across orientation changes. If compact becomes desktop-invalid at width >800px, the workbench adapts to the desktop collapsed presentation and the app-bar workbench toggle owns focus; returning to mobile restores the compact bottom sheet without resetting task state.",
        "notes": [
            "Geometry is read from rendered DOM rectangles after the coalesced MapLibre resize/refit settles.",
            "Cook's Meadow activation uses Playwright locator pointer input; no programmatic click is used.",
            "Independent Project OS pixel review, native Safari, physical-device behavior, and human field review remain external boundaries.",
        ],
    }
    errors = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        for viewport in VIEWPORTS:
            context = browser.new_context(
                viewport={"width": viewport[0], "height": viewport[1]},
                has_touch=viewport[0] < 500,
                is_mobile=viewport[0] < 500,
            )
            page = context.new_page()
            page_errors = []
            page.on("pageerror", lambda error: page_errors.append(str(error)))
            try:
                wait_ready(page)
                states = {}
                geometry_order = ("compact", "expanded", "full") if viewport in MOBILE_PORTRAITS else ("expanded", "full", "compact")
                for sheet in geometry_order:
                    states[sheet] = activate(page, sheet, "pointer")
                report["viewports"][f"{viewport[0]}x{viewport[1]}"] = states

                if viewport in MOBILE_PORTRAITS:
                    compact = states["compact"]["geometry"]
                    expanded = states["expanded"]["geometry"]
                    full = states["full"]["geometry"]
                    if compact["map_height"] <= expanded["map_height"] + 80:
                        report["failures"].append(f"{viewport[0]}x{viewport[1]}: compact map is not materially larger than expanded")
                    if compact["workbench_height"] >= 220 or compact["workbench_height"] >= expanded["workbench_height"] * 0.8:
                        report["failures"].append(f"{viewport[0]}x{viewport[1]}: compact workbench is not actual-controls height")
                    if full["workbench_height"] <= expanded["workbench_height"] * 1.5:
                        report["failures"].append(f"{viewport[0]}x{viewport[1]}: full sheet is not task-dominant")

                    activate(page, "expanded", "pointer")
                    prepared = prepare_context(page)
                    rows, failures = transition_rows(page, "keyboard")
                    report["transition_rows"].extend(rows)
                    report["failures"].extend(f"{viewport[0]}x{viewport[1]}: {failure}" for failure in failures)

                    activate(page, "expanded", "pointer")
                    rows, failures = transition_rows(page, "touch" if viewport[0] < 500 else "pointer")
                    report["transition_rows"].extend(rows)
                    report["failures"].extend(f"{viewport[0]}x{viewport[1]}: {failure}" for failure in failures)
                    if snapshot(page)["task"] != prepared["task"]:
                        report["failures"].append(f"{viewport[0]}x{viewport[1]}: task state failed transition preservation")

                    activate(page, "compact", "pointer")
                    page.locator("#mapOptionsToggle").click()
                    page.wait_for_timeout(40)
                    if page.locator("#mapOptionsPanel").is_hidden():
                        report["failures"].append(f"{viewport[0]}x{viewport[1]}: map options unreachable in compact")
                    page.keyboard.press("Escape")
                    cooks = page.locator(".photo-marker[data-place-key='cooks']")
                    cooks.click(timeout=5000)
                    if page.locator("#peek.show").count() != 1:
                        report["failures"].append(f"{viewport[0]}x{viewport[1]}: Cook's Meadow Peek did not open in compact")
                    page.keyboard.press("Escape")

                    page.set_viewport_size({"width": 844, "height": 390})
                    page.wait_for_timeout(120)
                    landscape = snapshot(page)
                    if landscape["task"] != prepared["task"]:
                        report["failures"].append(f"{viewport[0]}x{viewport[1]}: orientation changed task state")
                    if landscape["sheet"] != "compact":
                        report["failures"].append(f"{viewport[0]}x{viewport[1]}: orientation changed explicit sheet state")
                    page.set_viewport_size({"width": viewport[0], "height": viewport[1]})
                    page.wait_for_timeout(120)
                    restored = snapshot(page)
                    if restored["task"] != prepared["task"] or restored["sheet"] != "compact":
                        report["failures"].append(f"{viewport[0]}x{viewport[1]}: portrait recomposition failed to restore state")

                    page.evaluate("document.documentElement.style.fontSize='200%'")
                    page.wait_for_timeout(100)
                    if snapshot(page)["horizontal_overflow"]:
                        report["failures"].append(f"{viewport[0]}x{viewport[1]}: 200% compact reflow overflow")
            except Exception as error:
                errors.append(f"{viewport[0]}x{viewport[1]}: {type(error).__name__}: {error}")
            if page_errors:
                report.setdefault("page_errors", {})[f"{viewport[0]}x{viewport[1]}"] = list(page_errors)
            errors.extend(page_errors)
            page.close()
            context.close()
        browser.close()

    report["errors"] = errors
    report["status"] = "PASS" if not report["failures"] and not errors and report["viewports"] else "FAIL"
    bind_report(report, identity)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "viewports": len(report["viewports"]), "transitions": len(report["transition_rows"]), "failures": report["failures"], "errors": errors}, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
