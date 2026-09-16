"""Firefox and WebKit real-browser smoke/visual checks.

Each browser/viewport case runs in its own process group.  The parent owns the
case timeout and only trusts a worker result after the worker has durably
written its completed assertions and screenshot metadata.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

from qa_cleanup import bounded_cleanup
from qa_config import MODULAR_URL


ROOT = Path(__file__).resolve().parents[1]
URL = MODULAR_URL
OUTPUT = ROOT / "QA/map_first/cross_browser.json"
SHOTS = ROOT / "QA/map_first/screenshots"
CASE_TIMEOUT_SECONDS = int(os.environ.get("TRIP_CROSS_BROWSER_CASE_TIMEOUT_SECONDS", "60"))
TERM_GRACE_SECONDS = float(os.environ.get("TRIP_CROSS_BROWSER_TERM_GRACE_SECONDS", "2"))
KILL_GRACE_SECONDS = float(os.environ.get("TRIP_CROSS_BROWSER_KILL_GRACE_SECONDS", "2"))
TERMINAL_STATUSES = {"PASS", "FAIL", "UNVERIFIED"}
REQUIRED_CASES = (
    ("firefox", 1280, 800),
    ("firefox", 390, 844),
    ("webkit", 1280, 800),
    ("webkit", 390, 844),
)


def case_key(case: tuple[str, int, int]) -> tuple[str, int]:
    return case[0], case[1]


def durable_json(path: Path, payload: dict) -> None:
    """Atomically persist JSON so a parent never reads a partial worker row."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        if hasattr(os, "O_DIRECTORY"):
            directory = os.open(path.parent, os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def base_row(case: tuple[str, int, int]) -> dict:
    browser, width, height = case
    return {
        "browser": browser,
        "width": width,
        "height": height,
        "status": "UNVERIFIED",
        "completed": False,
        "cleanup_warnings": [],
    }


def timeout_row(case: tuple[str, int, int], reason: str) -> dict:
    row = base_row(case)
    row["error"] = reason
    return row


def load_worker_result(path: Path, case: tuple[str, int, int]) -> dict | None:
    """Return only a valid terminal row belonging to the requested case."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    browser, width, height = case
    if (
        payload.get("browser") != browser
        or payload.get("width") != width
        or payload.get("height") != height
        or payload.get("status") not in TERMINAL_STATUSES
    ):
        return None
    return payload


def terminate_process_group(process: subprocess.Popen, label: str) -> tuple[bool, list[str]]:
    """TERM then KILL one case group, and reap its worker within fixed bounds."""

    warnings = []
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    except OSError as error:
        warnings.append(f"{label} TERM failed: {error}")
    try:
        process.wait(timeout=TERM_GRACE_SECONDS)
        return True, warnings
    except subprocess.TimeoutExpired:
        pass

    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except OSError as error:
        warnings.append(f"{label} KILL failed: {error}")
    try:
        process.wait(timeout=KILL_GRACE_SECONDS)
        return True, warnings
    except subprocess.TimeoutExpired:
        warnings.append(f"{label} could not be reaped after TERM/KILL escalation")
        return False, warnings


def worker_case(case: tuple[str, int, int], result_path: Path, screenshot_path: Path) -> int:
    """Run one case and persist its result before attempting any teardown."""

    from playwright.sync_api import sync_playwright

    browser_name, width, height = case
    row = base_row(case)
    playwright = None
    browser = None
    context = None
    persisted = False

    try:
        playwright = sync_playwright().start()
        browser = getattr(playwright, browser_name).launch(headless=True, timeout=45000)
        context = browser.new_context(
            viewport={"width": width, "height": height},
            has_touch=width == 390,
            is_mobile=width == 390,
        )
        page = context.new_page()
        page.set_default_timeout(15000)
        page_errors = []
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        page.goto(URL, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_function("window.__tripApp?.map()?.isStyleLoaded()", timeout=30000)
        page.wait_for_function(
            "document.querySelectorAll('.photo-marker').length===window.__tripApp.DATA.markers.length",
            timeout=15000,
        )
        row.update(
            {
                "marker_objects": page.locator(".photo-marker").count(),
                "canvas": page.locator(".maplibregl-canvas").count(),
                "horizontal_overflow": page.evaluate("document.documentElement.scrollWidth>innerWidth"),
                "broken_marker_images": page.locator(".photo-marker img").evaluate_all(
                    "es=>es.filter(e=>!e.complete||e.naturalWidth===0).length"
                ),
                "page_errors": page_errors,
                "expected_places": page.evaluate("window.__tripApp.DATA.markers.length"),
            }
        )
        page.locator("[data-timeline]").first.click()
        page.locator("[data-tab=details]").click()
        page.wait_for_function(
            "[...document.querySelectorAll('#detailsPane .photo-slot img')].length===3&&"
            "[...document.querySelectorAll('#detailsPane .photo-slot img')].every(e=>e.complete&&e.naturalWidth>0)",
            timeout=8000,
        )
        row["detail_photos"] = page.locator("#detailsPane .photo-slot img").count()
        row["status"] = (
            "PASS"
            if row["marker_objects"] == row["expected_places"]
            and row["canvas"] == 1
            and not row["horizontal_overflow"]
            and row["broken_marker_images"] == 0
            and row["detail_photos"] == 3
            and not row["page_errors"]
            else "FAIL"
        )
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(screenshot_path))
        row["screenshot"] = str(screenshot_path.relative_to(ROOT))
        row["completed"] = True
    except Exception as error:
        row["status"] = "UNVERIFIED"
        row["error"] = f"{type(error).__name__}: {error}"
    finally:
        # This write is deliberately before browser/context/driver cleanup.  If
        # Playwright transport blocks during teardown, the parent can preserve
        # the completed row and terminate this entire process group.
        try:
            durable_json(result_path, row)
            persisted = True
        except Exception:
            persisted = False

        cleanup_warnings = []
        if context is not None:
            warning = bounded_cleanup(context.close, f"{browser_name} {width}px context")
            if warning:
                cleanup_warnings.append(warning)
        if browser is not None:
            warning = bounded_cleanup(browser.close, f"{browser_name} browser")
            if warning:
                cleanup_warnings.append(warning)
        if playwright is not None:
            warning = bounded_cleanup(playwright.stop, "Playwright driver")
            if warning:
                cleanup_warnings.append(warning)
        if persisted and cleanup_warnings:
            row["cleanup_warnings"] = cleanup_warnings
            try:
                durable_json(result_path, row)
            except Exception:
                pass

    return 0 if persisted else 1


def run_isolated_case(
    case: tuple[str, int, int],
    result_path: Path,
    screenshot_path: Path,
) -> tuple[dict, list[str], list[str]]:
    """Run one worker, preserving any durable result across teardown failure."""

    browser, width, _height = case
    label = f"{browser} {width}px"
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--worker",
        "--browser",
        browser,
        "--width",
        str(width),
        "--height",
        str(case[2]),
        "--result",
        str(result_path),
        "--screenshot",
        str(screenshot_path),
    ]
    try:
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            env=os.environ.copy(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as error:
        reason = f"{label} worker launch failed: {type(error).__name__}: {error}"
        return timeout_row(case, reason), [], [reason]

    cleanup_warnings = []
    errors = []
    timed_out = False
    try:
        returncode = process.wait(timeout=CASE_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        timed_out = True
        reaped, warnings = terminate_process_group(process, label)
        cleanup_warnings.extend(warnings)
        if not reaped:
            errors.append(f"{label} worker was not reaped after its hard timeout")
        returncode = process.returncode
    except Exception as error:
        reason = f"{label} worker wait failed: {type(error).__name__}: {error}"
        reaped, warnings = terminate_process_group(process, label)
        cleanup_warnings.extend(warnings)
        if not reaped:
            errors.append(f"{label} worker was not reaped after wait failure")
        row = load_worker_result(result_path, case)
        return row or timeout_row(case, reason), cleanup_warnings, [reason]

    row = load_worker_result(result_path, case)
    if timed_out:
        if row is not None and row.get("completed") is True:
            cleanup_warnings.append(f"{label} worker exceeded {CASE_TIMEOUT_SECONDS}s during teardown; durable result preserved")
            return row, cleanup_warnings, errors
        reason = f"{label} worker exceeded the {CASE_TIMEOUT_SECONDS}s hard timeout before durable completion"
        errors.append(reason)
        return timeout_row(case, reason), cleanup_warnings, errors

    if row is None:
        reason = f"{label} worker exited ({returncode}) without terminal durable evidence"
        errors.append(reason)
        return timeout_row(case, reason), cleanup_warnings, errors

    if row.get("completed") is True and returncode:
        cleanup_warnings.append(f"{label} worker exited {returncode} after durable evidence; result preserved")
    elif row.get("status") != "PASS" and returncode:
        errors.append(f"{label} worker exited {returncode}: {row.get('error', 'no durable PASS')}")
    return row, cleanup_warnings, errors


def parent_evidence() -> dict:
    return {
        "schema_version": 1,
        "status": "RUNNING",
        "expected_rows": len(REQUIRED_CASES),
        "rows": [],
        "cleanup_warnings": [],
        "errors": [],
    }


def ordered_rows(rows_by_case: dict[tuple[str, int], dict]) -> list[dict]:
    return [rows_by_case.get(case_key(case), timeout_row(case, "case did not run")) for case in REQUIRED_CASES]


def finalize_evidence(evidence: dict, rows_by_case: dict[tuple[str, int], dict]) -> dict:
    evidence["rows"] = ordered_rows(rows_by_case)
    required_keys = {case_key(case) for case in REQUIRED_CASES}
    actual_keys = {case_key((row.get("browser"), row.get("width"), row.get("height", -1))) for row in evidence["rows"]}
    evidence["status"] = (
        "PASS"
        if len(evidence["rows"]) == len(REQUIRED_CASES)
        and actual_keys == required_keys
        and all(row.get("status") == "PASS" and row.get("completed") is True for row in evidence["rows"])
        and not evidence["errors"]
        else "FAIL"
    )
    return evidence


def run_parent() -> dict:
    evidence = parent_evidence()
    rows_by_case = {}
    temporary_directory = None
    try:
        SHOTS.mkdir(parents=True, exist_ok=True)
        durable_json(OUTPUT, evidence)
        temporary_directory = tempfile.TemporaryDirectory(prefix="cross-browser-results-")
        result_root = Path(temporary_directory.name)
        for case in REQUIRED_CASES:
            key = case_key(case)
            result_path = result_root / f"{case[0]}_{case[1]}.json"
            screenshot_path = SHOTS / f"{case[0]}_{case[1]}_detail.png"
            row, cleanup_warnings, errors = run_isolated_case(case, result_path, screenshot_path)
            rows_by_case[key] = row
            evidence["cleanup_warnings"].extend(cleanup_warnings)
            evidence["errors"].extend({"browser": case[0], "width": case[1], "error": error} for error in errors)
            evidence["rows"] = ordered_rows(rows_by_case)
            durable_json(OUTPUT, evidence)
    except BaseException as error:
        evidence["errors"].append({"error": f"parent runner failed: {type(error).__name__}: {error}"})
    finally:
        if temporary_directory is not None:
            temporary_directory.cleanup()
        finalize_evidence(evidence, rows_by_case)
        durable_json(OUTPUT, evidence)
    return evidence


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--browser", choices=("firefox", "webkit"))
    parser.add_argument("--width", type=int)
    parser.add_argument("--height", type=int)
    parser.add_argument("--result", type=Path)
    parser.add_argument("--screenshot", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.worker:
        if not all((args.browser, args.width, args.height, args.result, args.screenshot)):
            raise SystemExit("worker requires browser, width, height, result, and screenshot")
        return worker_case((args.browser, args.width, args.height), args.result, args.screenshot)
    evidence = run_parent()
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
