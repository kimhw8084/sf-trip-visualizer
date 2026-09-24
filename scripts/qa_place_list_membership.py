"""Candidate-bound browser oracle for current place roles and the full Place list."""

from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

from qa_config import MODULAR_URL
from qa_evidence import ROOT, bind_report, candidate_identity


OUT = ROOT / "QA" / "CHG-204" / "place_list_roles.json"
SCREENSHOTS = ROOT / "QA" / "CHG-204" / "screenshots" / "place_list"
RETIRED_KEYS = {"bay_lights", "exploratorium", "musee", "academy", "coit", "bixby", "mariposa"}


def validate_place_rows(rows: list[dict], roles: dict[str, dict[str, str]], route_ids: list[str], expected_places: int | None = None) -> dict:
    """Check one visible role per place and reject route-matrix payloads."""
    failures: list[str] = []
    seen: set[str] = set()
    if len(route_ids) != 1:
        failures.append(f"configured single-route UI oracle received {len(route_ids)} route IDs")
    route = route_ids[0] if len(route_ids) == 1 else None
    for row in rows:
        place = row.get("place_key")
        if place in seen:
            failures.append(f"duplicate rendered place identity: {place}")
        seen.add(place)
        if place not in roles:
            failures.append(f"unknown rendered place identity: {place}")
            continue
        if row.get("route_id") not in (None, route):
            failures.append(f"{place} renders a role for stale route {row.get('route_id')}")
        if row.get("cells") or row.get("route_cells") or row.get("membership") or row.get("comparison_cells", 0):
            failures.append(f"{place} exposes route-comparison membership cells")
        role = row.get("role")
        if role != roles[place].get(route):
            failures.append(f"{place} renders {role!r}; canonical role is {roles[place].get(route)!r}")
        if role not in {"Core", "Strong", "Conditional", "Skip"}:
            failures.append(f"{place} has invalid visible role {role!r}")
        if not str(row.get("label", "")).strip():
            failures.append(f"{place} has no visible text role")
    if expected_places is not None and len(seen) != expected_places:
        failures.append(f"rendered place identity count is {len(seen)}, expected {expected_places}")
    if RETIRED_KEYS & seen:
        failures.append(f"retired attractions appear in the active Place list: {sorted(RETIRED_KEYS & seen)}")
    return {"status": "PASS" if not failures else "FAIL", "failures": failures, "places": len(seen), "rows": len(rows), "route_id": route}


def collect_rows(page, selector: str = ".place-list-item") -> list[dict]:
    return page.locator(selector).evaluate_all(
        """rows => rows.map(row => ({
          place_key: row.dataset.placeChoice,
          name: row.querySelector('.place-list-copy strong')?.textContent || '',
          role: row.querySelector('.place-role')?.dataset.role || '',
          label: row.querySelector('.place-role')?.textContent || '',
          comparison_cells: row.querySelectorAll('.membership-cell,[data-compare-route]').length
        }))"""
    )


def geometry_oracle(page) -> dict:
    return page.evaluate(
        """() => {
          const failures = [];
          if (document.documentElement.scrollWidth > innerWidth + 1) failures.push(`horizontal overflow ${document.documentElement.scrollWidth-innerWidth}px`);
          for (const row of document.querySelectorAll('.place-list-item')) {
            const rect=row.getBoundingClientRect(), name=row.querySelector('.place-list-copy strong'), role=row.querySelector('.place-role');
            if (rect.right > innerWidth+1 || rect.left < -1) failures.push(`row outside viewport: ${row.dataset.placeChoice}`);
            if (!name || !name.textContent.trim() || name.getBoundingClientRect().width < 1) failures.push(`place name is clipped or missing: ${row.dataset.placeChoice}`);
            if (!role || role.getBoundingClientRect().width < 24 || role.getBoundingClientRect().height < 18) failures.push(`role label is crushed or missing: ${row.dataset.placeChoice}`);
          }
          return {status:failures.length?'FAIL':'PASS',failures};
        }"""
    )


def collect_rows_from_fixture(roles: dict[str, dict[str, str]], route_ids: list[str]) -> list[dict]:
    route = route_ids[0]
    return [{"place_key": place, "role": row[route], "label": row[route]} for place, row in roles.items()]


def main() -> int:
    identity = candidate_identity()
    role_doc = json.loads((ROOT / "data/route_role_matrix.json").read_text())
    roles, route_ids = role_doc["places"], role_doc["route_ids"]
    expected_places = len(roles)
    report = {"schema_version": 2, "status": "FAIL", "candidate": identity["sha"], "candidate_tree": identity["tree"], "screenshots": [], "viewports": {}, "errors": [], "negative_control": {}, "checks": {}}
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
            page.wait_for_function("n => document.querySelectorAll('#placeView:not([hidden]) .place-list-item').length === n", arg=expected_places)
            if english_dark:
                page.locator("#langToggle").click()
                page.locator("#themeToggle").click()
                page.wait_for_function("document.documentElement.lang === 'en' && document.documentElement.dataset.theme === 'dark'")
            rows = collect_rows(page)
            row_oracle = validate_place_rows(rows, roles, route_ids, expected_places)
            layout = geometry_oracle(page)
            no_selection = page.evaluate("window.__tripApp.state.task.selected === null")
            no_matrix = page.locator(".route-membership,.membership-cell,.inspector-membership,[data-compare-route],#comparePanel").count() == 0
            scroll = page.locator(".workbench-scroll")
            if screenshot_prefix:
                top_path = SCREENSHOTS / f"{screenshot_prefix}_top.png"
                page.screenshot(path=str(top_path), full_page=False)
                report["screenshots"].append({"path": str(top_path.relative_to(ROOT)), "viewport": f"{viewport[0]}x{viewport[1]}", "language": page.evaluate("document.documentElement.lang"), "theme": page.evaluate("document.documentElement.dataset.theme"), "state": "top of complete active-place list"})
            scroll.evaluate("element => element.scrollTop = element.scrollHeight")
            page.wait_for_timeout(120)
            bottom = scroll.evaluate("element => element.scrollTop")
            last_key = rows[-1]["place_key"]
            page.locator("[data-place-choice]").last.click()
            page.wait_for_selector("#placeView:not([hidden]) .place-inspector .place-role")
            inspector_row = [{"place_key": last_key, **page.locator("#placeInspector .place-role").evaluate("node => ({role:node.dataset.role,label:node.textContent})")}]
            inspector_oracle = validate_place_rows(inspector_row, roles, route_ids, expected_places=1)
            no_matrix = no_matrix and page.locator(".route-membership,.membership-cell,.inspector-membership,[data-compare-route],#comparePanel").count() == 0
            page.locator("[data-place-back]").click()
            page.wait_for_timeout(100)
            restored_scroll = scroll.evaluate("element => element.scrollTop")
            restored_focus = page.evaluate("document.activeElement?.dataset?.placeChoice || null")
            restored = abs(restored_scroll - bottom) <= 3 and restored_focus == last_key
            if screenshot_prefix:
                bottom_path = SCREENSHOTS / f"{screenshot_prefix}_scrolled.png"
                page.screenshot(path=str(bottom_path), full_page=False)
                report["screenshots"].append({"path": str(bottom_path.relative_to(ROOT)), "viewport": f"{viewport[0]}x{viewport[1]}", "language": page.evaluate("document.documentElement.lang"), "theme": page.evaluate("document.documentElement.dataset.theme"), "state": "scrolled active list and restored focus"})
            page.evaluate("document.documentElement.style.fontSize = '200%'")
            page.wait_for_timeout(100)
            reflow = geometry_oracle(page)
            report["viewports"][name] = {"viewport": f"{viewport[0]}x{viewport[1]}", "no_selected_place": no_selection, "rows": row_oracle, "inspector": inspector_oracle, "layout": layout, "no_route_matrix": no_matrix, "restored_scroll": restored, "restored_focus": restored_focus, "200_percent_reflow": reflow, "page_errors": page_errors}
            context.close()

        run_viewport("desktop_ko_light", (1440, 900), screenshot_prefix="place_roles_1440x900_ko_light")
        run_viewport("mobile_en_dark", (390, 844), english_dark=True, screenshot_prefix="place_roles_390x844_en_dark")
        run_viewport("stress_375", (375, 812), screenshot_prefix="place_roles_375x812_stress")
        run_viewport("stress_360", (360, 800), screenshot_prefix="place_roles_360x800_stress")
        browser.close()

    fixture = collect_rows_from_fixture(roles, route_ids)
    fixture[0]["route_cells"] = [{"route": "B", "role": "Core"}]
    negative = validate_place_rows(fixture, roles, route_ids, expected_places)
    report["negative_control"] = {"status": negative["status"], "failures": negative["failures"][:4]}
    viewport_ok = all(row["no_selected_place"] and row["no_route_matrix"] and row["rows"]["status"] == "PASS" and row["inspector"]["status"] == "PASS" and row["layout"]["status"] == "PASS" and row["restored_scroll"] and row["200_percent_reflow"]["status"] == "PASS" and not row["page_errors"] for row in report["viewports"].values())
    report["checks"] = {"complete_active_place_list": viewport_ok, "comparison_matrix_absent": viewport_ok, "negative_route_cell_rejected": negative["status"] == "FAIL", "candidate_screenshots_present": len(report["screenshots"]) == 8}
    report["status"] = "PASS" if all(report["checks"].values()) else "FAIL"
    bind_report(report, identity)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "checks": report["checks"], "screenshots": len(report["screenshots"]), "errors": report["errors"]}, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
