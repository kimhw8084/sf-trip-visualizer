"""Exact-candidate browser oracle for the complete scrolling Place list."""

from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

from qa_config import MODULAR_URL
from qa_evidence import ROOT, bind_report, candidate_identity


OUT = ROOT / "QA" / "project_os_verify" / "ui_revamp_r5" / "place_list_membership.json"
SCREENSHOTS = ROOT / "QA" / "project_os_verify" / "ui_revamp_r5"
ROLE_SYMBOLS = {"Core": "C", "Strong": "S", "Conditional": "△", "Skip": "—"}


def validate_membership_rows(rows: list[dict], matrix: dict[str, dict[str, str]], expected_places: int = 39) -> dict:
    """Validate rendered route cells; intentionally usable as a mutation oracle."""
    failures: list[str] = []
    seen_places: set[str] = set()
    for row in rows:
        place = row.get("place_key")
        if place in seen_places:
            failures.append(f"duplicate rendered place identity: {place}")
        seen_places.add(place)
        expected = matrix.get(place)
        if expected is None:
            failures.append(f"unknown rendered place identity: {place}")
            continue
        cells = row.get("cells", [])
        if len(cells) != 5:
            failures.append(f"{place} exposes {len(cells)} route cells instead of exactly five")
        routes = [cell.get("route") for cell in cells]
        if routes != ["A", "B", "C", "D", "E"]:
            failures.append(f"{place} route cells are not ordered A/B/C/D/E: {routes}")
        for cell in cells:
            route = cell.get("route")
            role = cell.get("role")
            if role != expected.get(route):
                failures.append(f"{place}/{route} renders {role!r}; canonical role is {expected.get(route)!r}")
            if cell.get("symbol") != ROLE_SYMBOLS.get(expected.get(route)):
                failures.append(f"{place}/{route} symbol does not represent {expected.get(route)}")
            if not str(cell.get("label", "")).strip():
                failures.append(f"{place}/{route} has no visible role text")
            if expected.get(route) == "Skip" and cell.get("symbol") == "":
                failures.append(f"{place}/{route} Skip is not distinguishable without color")
    if len(seen_places) != expected_places:
        failures.append(f"rendered place identity count is {len(seen_places)}, expected {expected_places}")
    return {"status": "PASS" if not failures else "FAIL", "failures": failures, "places": len(seen_places), "rows": len(rows)}


def collect_rows(page, selector: str = ".place-list-item") -> list[dict]:
    return page.locator(selector).evaluate_all(
        """rows => rows.map(row => ({
          place_key: row.dataset.placeChoice,
          name: row.querySelector('.place-list-copy strong')?.textContent || '',
          cells: [...row.querySelectorAll('.route-membership .membership-cell')].map(cell => ({
            route: cell.dataset.route,
            role: cell.dataset.role,
            symbol: cell.querySelector('i')?.textContent || '',
            label: cell.querySelector('small')?.textContent || ''
          }))
        }))"""
    )


def geometry_oracle(page) -> dict:
    return page.evaluate(
        """() => {
          const failures = [];
          if (document.documentElement.scrollWidth > innerWidth + 1) failures.push(`horizontal overflow ${document.documentElement.scrollWidth - innerWidth}px`);
          for (const row of document.querySelectorAll('.place-list-item')) {
            const rect = row.getBoundingClientRect();
            if (rect.right > innerWidth + 1 || rect.left < -1) failures.push(`row outside viewport: ${row.dataset.placeChoice}`);
            const name = row.querySelector('.place-list-copy strong');
            if (!name || !name.textContent.trim() || name.getBoundingClientRect().width < 1) failures.push(`place name is clipped or missing: ${row.dataset.placeChoice}`);
            const cells = [...row.querySelectorAll('.membership-cell')];
            for (let index = 1; index < cells.length; index += 1) {
              const previous = cells[index - 1].getBoundingClientRect();
              const current = cells[index].getBoundingClientRect();
              if (current.left < previous.right - 0.5 || current.width < 8 || current.height < 8) failures.push(`crushed/overlapping route cells: ${row.dataset.placeChoice}`);
            }
          }
          return {status: failures.length ? 'FAIL' : 'PASS', failures};
        }"""
    )


def main() -> int:
    identity = candidate_identity()
    matrix = json.loads((ROOT / "data/route_role_matrix.json").read_text())["places"]
    report = {"schema_version": 1, "status": "FAIL", "candidate": identity["sha"], "candidate_tree": identity["tree"], "screenshots": [], "viewports": {}, "errors": [], "negative_control": {}, "checks": {}}
    SCREENSHOTS.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)

        def run_viewport(name: str, viewport: tuple[int, int], *, english_dark: bool = False, screenshot_prefix: str | None = None) -> None:
            context = browser.new_context(viewport={"width": viewport[0], "height": viewport[1]})
            page = context.new_page()
            page_errors: list[str] = []
            page.on("pageerror", lambda error: page_errors.append(str(error)))
            page.goto(MODULAR_URL, wait_until="domcontentloaded", timeout=90000)
            page.locator("#modeNav [data-mode='place']").click()
            page.wait_for_function("document.querySelectorAll('#placeView:not([hidden]) .place-list-item').length === 39")
            if english_dark:
                page.locator("#langToggle").click()
                page.locator("#themeToggle").click()
                page.wait_for_function("document.documentElement.lang === 'en' && document.documentElement.dataset.theme === 'dark'")
            rows = collect_rows(page)
            row_oracle = validate_membership_rows(rows, matrix)
            layout = geometry_oracle(page)
            no_selection = page.evaluate("window.__tripApp.state.task.selected === null")
            scroll = page.locator(".workbench-scroll")
            top_before = scroll.evaluate("element => element.scrollTop")
            if screenshot_prefix:
                top_path = SCREENSHOTS / f"{screenshot_prefix}_top.png"
                page.screenshot(path=str(top_path), full_page=False)
                report["screenshots"].append({"path": str(top_path.relative_to(ROOT)), "viewport": f"{viewport[0]}x{viewport[1]}", "language": page.evaluate("document.documentElement.lang"), "theme": page.evaluate("document.documentElement.dataset.theme"), "state": "top of complete scrolling list"})
            scroll.evaluate("element => element.scrollTop = element.scrollHeight")
            page.wait_for_timeout(120)
            bottom_before = scroll.evaluate("element => element.scrollTop")
            last_key = rows[-1]["place_key"]
            page.locator("[data-place-choice]").last.click()
            page.wait_for_selector("#placeView:not([hidden]) .place-inspector .inspector-membership")
            inspector_cells = page.locator("#placeInspector .inspector-membership .membership-cell").evaluate_all(
                """cells => cells.map(cell => ({
                  route: cell.dataset.route,
                  role: cell.dataset.role,
                  symbol: cell.querySelector('i')?.textContent || '',
                  label: cell.querySelector('small')?.textContent || ''
                }))"""
            )
            inspector_row = [{"place_key": last_key, "cells": inspector_cells}]
            inspector_oracle = validate_membership_rows(inspector_row, matrix, expected_places=1)
            page.locator("[data-place-back]").click()
            page.wait_for_timeout(100)
            restored_scroll = scroll.evaluate("element => element.scrollTop")
            restored_focus = page.evaluate("document.activeElement?.dataset?.placeChoice || null")
            restored = abs(restored_scroll - bottom_before) <= 3 and restored_focus == last_key
            if screenshot_prefix:
                bottom_path = SCREENSHOTS / f"{screenshot_prefix}_scrolled.png"
                page.screenshot(path=str(bottom_path), full_page=False)
                report["screenshots"].append({"path": str(bottom_path.relative_to(ROOT)), "viewport": f"{viewport[0]}x{viewport[1]}", "language": page.evaluate("document.documentElement.lang"), "theme": page.evaluate("document.documentElement.dataset.theme"), "state": "scrolled list and restored focus"})
            page.evaluate("document.documentElement.style.fontSize = '200%'")
            page.wait_for_timeout(100)
            reflow = geometry_oracle(page)
            page_errors.extend([])
            report["viewports"][name] = {"viewport": f"{viewport[0]}x{viewport[1]}", "no_selected_place": no_selection, "rows": row_oracle, "inspector": inspector_oracle, "layout": layout, "restored_scroll": restored, "restored_scroll_top": restored_scroll, "restored_focus": restored_focus, "200_percent_reflow": reflow, "page_errors": page_errors}
            context.close()

        run_viewport("desktop_ko_light", (1440, 900), screenshot_prefix="place_list_membership_1440x900_ko_light")
        run_viewport("mobile_en_dark", (390, 844), english_dark=True, screenshot_prefix="place_list_membership_390x844_en_dark")
        run_viewport("stress_375", (375, 812), screenshot_prefix="place_list_membership_375x812_stress")
        run_viewport("stress_360", (360, 800), screenshot_prefix="place_list_membership_360x800_stress")
        browser.close()

    negative_rows = collect_rows_from_fixture(matrix)
    negative_rows[0]["cells"][0]["role"] = "Skip" if negative_rows[0]["cells"][0]["role"] != "Skip" else "Core"
    negative = validate_membership_rows(negative_rows, matrix)
    report["negative_control"] = {"status": negative["status"], "failures": negative["failures"][:4]}

    viewport_ok = all(
        row["no_selected_place"] and row["rows"]["status"] == "PASS" and row["inspector"]["status"] == "PASS" and row["layout"]["status"] == "PASS" and row["restored_scroll"] and row["200_percent_reflow"]["status"] == "PASS" and not row["page_errors"]
        for row in report["viewports"].values()
    )
    report["checks"] = {"complete_39_place_list": viewport_ok, "negative_control_rejected": negative["status"] == "FAIL", "screenshots_present": len(report["screenshots"]) == 8}
    report["status"] = "PASS" if all(report["checks"].values()) else "FAIL"
    bind_report(report, identity)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "checks": report["checks"], "screenshots": len(report["screenshots"]), "errors": report["errors"]}, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


def collect_rows_from_fixture(matrix: dict[str, dict[str, str]]) -> list[dict]:
    return [{"place_key": place, "cells": [{"route": route, "role": role, "symbol": ROLE_SYMBOLS[role], "label": role} for route, role in roles.items()]} for place, roles in matrix.items()]


if __name__ == "__main__":
    raise SystemExit(main())
