"""Rendered marker hit-region and map-chrome safe-area oracle."""

from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

from qa_config import MODULAR_URL
from qa_evidence import ROOT, bind_report, candidate_identity


OUT = ROOT / "QA" / "CHG-232" / "map_geometry.json"


def wait_ready(page) -> None:
    page.goto(MODULAR_URL, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_function("window.__tripApp?.map()?.isStyleLoaded()", timeout=30000)
    page.wait_for_function("document.querySelectorAll('.photo-marker').length > 0", timeout=15000)
    settle_geometry(page)


def settle_geometry(page) -> None:
    page.evaluate("window.__tripApp.whenIdle()")
    page.wait_for_function("window.__tripApp?.map()?.loaded() && !window.__tripApp.map().isMoving()", timeout=10000)
    page.evaluate("new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")


def geometry(page, viewport: tuple[int, int], state: str) -> dict:
    return {
        "viewport": f"{viewport[0]}x{viewport[1]}",
        "state": state,
        "snapshot": page.evaluate("window.__tripApp.mapGeometrySnapshot()"),
    }


def check_row(row: dict) -> list[str]:
    snapshot = row["snapshot"]
    failures = []
    for marker in snapshot.get("markers", []):
        if marker.get("key", "").startswith("Cook") or marker.get("key") == "cooks":
            row["cooks"] = marker
        if marker.get("intersects_obstacle"):
            failures.append(f"{row['state']}:{marker['key']} intersects {marker['intersects_obstacle']}")
        if marker.get("center_hit") and not any(token in marker["center_hit"] for token in ("photo-marker", "photo-cluster", "route-leg-label")):
            failures.append(f"{row['state']}:{marker['key']} center hit {marker['center_hit']}")
    return failures


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    report = {"schema_version": 2, "status": "FAIL", "states": [], "failures": [], "notes": ["Rendered Chromium hit testing; native Safari, physical-device and human field evidence remain separate."]}
    try:
        identity = candidate_identity()
        bind_report(report, identity)
    except Exception as error:
        report["errors"] = [f"candidate binding: {type(error).__name__}: {error}"]
        OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps({"status": report["status"], "errors": report["errors"]}, ensure_ascii=False))
        return 1

    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        for viewport in ((1440, 900), (390, 844)):
            context = browser.new_context(viewport={"width": viewport[0], "height": viewport[1]}, has_touch=viewport[0] < 500, is_mobile=viewport[0] < 500)
            page = context.new_page()
            page_errors = []
            page.on("pageerror", lambda error: page_errors.append(str(error)))
            wait_ready(page)
            report["states"].append(geometry(page, viewport, "overall-default-unselected"))
            page.locator("#mapOptionsToggle").click()
            settle_geometry(page)
            report["states"].append(geometry(page, viewport, "map-options-open"))
            page.keyboard.press("Escape")
            settle_geometry(page)
            report["states"].append(geometry(page, viewport, "map-options-closed-after-escape"))
            route_chrome = page.locator("#routeLegendToggle,#routeLegendPanel,[data-compare-route],#comparePanel,.route-membership,.membership-cell").count()
            if route_chrome:
                errors.append(f"{viewport[0]}x{viewport[1]} leaked route comparison/key chrome: {route_chrome}")
            page.locator("#mapOptionsToggle").click()
            page.locator("#regionControls [data-region='yosemite']").click()
            page.locator("#modeNav [data-mode='day']").click()
            page.locator("#dateSelect").select_option("10/8")
            settle_geometry(page)
            report["states"].append(geometry(page, viewport, "yosemite-10/8-clustered-unselected"))
            page.locator("#dateSelect").select_option("10/7")
            settle_geometry(page)
            report["states"].append(geometry(page, viewport, "yosemite-10/7-unclustered-unselected"))
            cooks = page.locator(".photo-marker[data-place-key='cooks']")
            try:
                cooks.click(timeout=5000)
                report["states"][-1]["real_pointer_activation"] = "PASS"
                page.evaluate("window.__tripApp.hidePreview({returnFocus:false})")
                page.wait_for_function("!document.querySelector('#peek.show')")
                settle_geometry(page)
                report["states"].append(geometry(page, viewport, "yosemite-10/7-selected-cooks"))
            except Exception as error:
                report["states"][-1]["real_pointer_activation"] = "FAIL"
                errors.append(f"{viewport[0]}x{viewport[1]} cooks pointer activation: {type(error).__name__}: {error}")
            if viewport[0] < 500:
                page.locator("#workbench [data-sheet='compact']").click()
                settle_geometry(page)
                report["states"].append(geometry(page, viewport, "mobile-compact-sheet"))
                page.locator("#workbench [data-sheet='expanded']").click()
                settle_geometry(page)
                report["states"].append(geometry(page, viewport, "mobile-expanded-sheet"))
            errors.extend(page_errors)
            page.close()
            context.close()
        browser.close()

    for row in report["states"]:
        report["failures"].extend(check_row(row))
    report["failures"].extend(errors)
    r2_reference = {
        "desktop_1440x900": {
            "safe_padding": {"top": 162.0, "right": 157.64, "bottom": 77.0, "left": 314.94},
            "persistent_opaque_area_px": 69085.0,
            "shell_area_px": 678886.0,
            "unobstructed_ratio": 0.8982,
        },
        "mobile_390x844": {
            "safe_padding": {"top": 146.0, "right": 113.0, "bottom": 71.0, "left": 16.0},
            "persistent_opaque_area_px": 42116.0,
            "shell_area_px": 173192.0,
            "unobstructed_ratio": 0.7569,
        },
    }
    report["r2_reference"] = r2_reference
    report["useful_map_area_comparison"] = {}
    for viewport_key, label in (("1440x900", "desktop_1440x900"), ("390x844", "mobile_390x844")):
        default = next((row["snapshot"] for row in report["states"] if row["viewport"] == viewport_key and row["state"] == "overall-default-unselected"), None)
        if default:
            shell = default.get("shell", {})
            persistent = default.get("persistent_opaque_chrome", {})
            interior = default.get("unobstructed_interior", {})
            r2 = r2_reference[label]
            r3_area = persistent.get("area_px", 0)
            r3_shell = shell.get("area_px", 0)
            report["useful_map_area_comparison"][label] = {
                "r2": r2,
                "r3": {
                    "safe_padding": default.get("safe_padding", {}),
                    "persistent_opaque_area_px": r3_area,
                    "shell_area_px": r3_shell,
                    "unobstructed_ratio": interior.get("ratio"),
                },
                "persistent_area_reduction_ratio": round(1 - (r3_area / r2["persistent_opaque_area_px"]), 4) if r2["persistent_opaque_area_px"] else None,
                "unobstructed_ratio_gain": round((interior.get("ratio", 0) or 0) - r2["unobstructed_ratio"], 4),
            }
    report["status"] = "PASS" if not report["failures"] and report["states"] else "FAIL"
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "states": len(report["states"]), "failures": report["failures"]}, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
