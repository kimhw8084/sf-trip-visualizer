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
from hosted_linux_pipeline import (
    FIREFOX_HOSTED_LINUX_MODE,
    FIREFOX_MODE_ENV,
    SOFTWARE_GL_ENV,
)
from qa_evidence import candidate_identity


ROOT = Path(__file__).resolve().parents[1]
URL = MODULAR_URL
OUTPUT = ROOT / "QA/project_os_verify/ui_revamp_r3/browser_summary.json"
SHOTS = ROOT / "QA/project_os_verify/ui_revamp_r3/screenshots"
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


def case_key(case: tuple[str, int, int]) -> tuple[str, int, int]:
    return case


def firefox_hosted_linux_enabled() -> bool:
    """Return whether hosted Linux Firefox should run headful under Xvfb."""

    return sys.platform.startswith("linux") and os.environ.get(FIREFOX_MODE_ENV) == FIREFOX_HOSTED_LINUX_MODE


def worker_environment() -> dict[str, str]:
    """Preserve the parent environment and request software GL for hosted Firefox."""

    environment = os.environ.copy()
    if firefox_hosted_linux_enabled():
        environment[SOFTWARE_GL_ENV] = "1"
    return environment


def browser_launch_options(browser_name: str) -> dict:
    """Select only the hosted-Linux Firefox launch mode; keep other cases headless."""

    hosted_firefox = browser_name == "firefox" and firefox_hosted_linux_enabled()
    options = {"headless": not hosted_firefox, "timeout": 45000}
    if hosted_firefox:
        options["env"] = worker_environment()
    return options


def launch_mode(browser_name: str) -> str:
    if browser_name == "firefox" and firefox_hosted_linux_enabled():
        return "hosted-linux-xvfb"
    return "headless"


def recorded_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


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
        "launch_mode": launch_mode(browser),
        "status": "UNVERIFIED",
        "completed": False,
        "cleanup_warnings": [],
        "page_errors": [],
        "console_errors": [],
        "failed_requests": [],
        "map_error_events": [],
        "candidate": os.environ.get("TRIP_CANDIDATE_SHA"),
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


MAP_ERROR_HOOK = """() => {
    const app = window.__tripApp;
    const map = app && typeof app.map === 'function' ? app.map() : null;
    if (!map || typeof map.on !== 'function') return false;
    if (!window.__crossBrowserMapErrors) {
        window.__crossBrowserMapErrors = [];
        map.on('error', event => {
            const error = event && event.error;
            window.__crossBrowserMapErrors.push({
                message: error?.message || event?.message || String(error || event || 'Map error'),
                source_id: event?.sourceId ?? null,
                source: event?.source ? String(event.source) : null,
                tile_url: event?.tile?.url ?? null,
            });
        });
    }
    return true;
}"""


def attach_map_error_listener(page) -> bool:
    """Attach a best-effort MapLibre error listener without masking the real check."""

    try:
        return bool(page.evaluate(MAP_ERROR_HOOK))
    except Exception:
        return False


def read_map_error_events(page) -> list:
    try:
        events = page.evaluate("window.__crossBrowserMapErrors || []")
    except Exception:
        return []
    return events if isinstance(events, list) else []


def collect_failure_diagnostics(
    page,
    case: tuple[str, int, int],
    page_errors: list[str],
    console_errors: list[dict],
    failed_requests: list[dict],
    map_listener_attached: bool,
) -> dict:
    """Collect browser/app state while the page is still alive after a failure."""

    browser, width, height = case
    diagnostics = {
        "browser": browser,
        "viewport": {"width": width, "height": height},
        "launch_mode": launch_mode(browser),
        "environment": {
            "platform": sys.platform,
            "display": os.environ.get("DISPLAY"),
            SOFTWARE_GL_ENV: os.environ.get(SOFTWARE_GL_ENV),
        },
        "map_object_present": None,
        "provider": None,
        "provider_health": None,
        "is_style_loaded": None,
        "canvas_count": None,
        "current_marker_count": None,
        "expected_marker_count": None,
        "page_errors": list(page_errors),
        "console_errors": list(console_errors),
        "failed_requests": list(failed_requests),
        "map_error_listener_attached": map_listener_attached,
        "map_error_events": read_map_error_events(page) if page is not None else [],
    }
    if page is None:
        return diagnostics

    map_listener_attached = attach_map_error_listener(page) or map_listener_attached
    diagnostics["map_error_listener_attached"] = map_listener_attached
    diagnostics["map_error_events"] = read_map_error_events(page)
    try:
        diagnostics["map_object_present"] = bool(
            page.evaluate("Boolean(window.__tripApp?.map?.())")
        )
    except Exception:
        pass
    try:
        provider_state = page.evaluate(
            """() => {
                const state = window.__tripApp?.state;
                return {provider: state?.provider ?? null, provider_health: state?.providerHealth ?? null};
            }"""
        )
        if isinstance(provider_state, dict):
            diagnostics["provider"] = provider_state.get("provider")
            diagnostics["provider_health"] = provider_state.get("provider_health")
    except Exception:
        pass
    try:
        diagnostics["is_style_loaded"] = page.evaluate(
            """() => {
                const map = window.__tripApp?.map?.();
                return map && typeof map.isStyleLoaded === 'function' ? map.isStyleLoaded() : null;
            }"""
        )
    except Exception:
        pass
    try:
        diagnostics["canvas_count"] = page.locator(".maplibregl-canvas").count()
    except Exception:
        pass
    try:
        marker_counts = page.evaluate(
            """() => ({
                current: document.querySelectorAll('.photo-marker').length,
                expected: window.__tripApp?.DATA?.markers?.length ?? null,
            })"""
        )
        if isinstance(marker_counts, dict):
            diagnostics["current_marker_count"] = marker_counts.get("current")
            diagnostics["expected_marker_count"] = marker_counts.get("expected")
    except Exception:
        pass
    return diagnostics


def capture_failure_evidence(
    row: dict,
    page,
    case: tuple[str, int, int],
    screenshot_path: Path,
    page_errors: list[str],
    console_errors: list[dict],
    failed_requests: list[dict],
    map_listener_attached: bool,
    error: Exception,
) -> None:
    """Record diagnostics and a screenshot without ever making a failed case pass."""

    diagnostics = collect_failure_diagnostics(
        page,
        case,
        page_errors,
        console_errors,
        failed_requests,
        map_listener_attached,
    )
    row["diagnostics"] = diagnostics
    row["page_errors"] = diagnostics["page_errors"]
    row["console_errors"] = diagnostics["console_errors"]
    row["failed_requests"] = diagnostics["failed_requests"]
    row["map_error_events"] = diagnostics["map_error_events"]
    row["error"] = f"{type(error).__name__}: {error}"
    row["status"] = "UNVERIFIED"
    row["completed"] = False
    if page is not None:
        try:
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(screenshot_path), timeout=5000)
            relative = recorded_path(screenshot_path)
            diagnostics["failure_screenshot"] = relative
            row["failure_screenshot"] = relative
        except Exception as screenshot_error:
            diagnostics["failure_screenshot_error"] = f"{type(screenshot_error).__name__}: {screenshot_error}"


def start_playwright():
    from playwright.sync_api import sync_playwright

    return sync_playwright().start()


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

    browser_name, width, height = case
    row = base_row(case)
    playwright = None
    browser = None
    context = None
    page = None
    page_errors = []
    console_errors = []
    failed_requests = []
    map_listener_attached = False
    persisted = False

    try:
        playwright = start_playwright()
        browser = getattr(playwright, browser_name).launch(**browser_launch_options(browser_name))
        context = browser.new_context(
            viewport={"width": width, "height": height},
            has_touch=width == 390,
            is_mobile=width == 390,
        )
        page = context.new_page()
        page.set_default_timeout(15000)
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        page.on(
            "console",
            lambda message: console_errors.append({"type": message.type, "text": message.text})
            if message.type == "error"
            else None,
        )
        page.on(
            "requestfailed",
            lambda request: failed_requests.append(
                {
                    "url": request.url,
                    "method": request.method,
                    "failure": request.failure,
                }
            ),
        )
        page.goto(URL, wait_until="domcontentloaded", timeout=45000)
        map_listener_attached = attach_map_error_listener(page)
        if not map_listener_attached:
            try:
                page.wait_for_function(MAP_ERROR_HOOK, timeout=5000)
                map_listener_attached = True
            except Exception:
                pass
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
                "expected_places": page.evaluate("window.__tripApp.DATA.markers.length"),
            }
        )
        page.locator("#modeNav [data-mode='day']").click()
        page.locator("#dateSelect").select_option("10/8")
        page.wait_for_function("document.querySelectorAll('#dayPlan .day-item, #dayPlan .plan-card').length > 0", timeout=8000)
        row["day_items"] = page.locator("#dayPlan .day-item, #dayPlan .plan-card").count()
        page.locator("#mapOptionsToggle").click()
        row["map_options_open"] = page.locator("#mapOptionsPanel").is_visible() and page.evaluate("document.activeElement?.id === 'mapOptionsClose'")
        row["map_options_open_geometry"] = page.evaluate("window.__tripApp.mapGeometrySnapshot()")
        page.keyboard.press("Escape")
        row["map_options_close_focus_return"] = page.locator("#mapOptionsPanel").is_hidden() and page.evaluate("document.activeElement?.id === 'mapOptionsToggle' and document.querySelectorAll('#mapOptionsPanel button:visible').length === 0")
        page.locator("#routeLegendToggle").click()
        row["route_key_open"] = page.locator("#routeLegendPanel").is_visible()
        row["route_key_open_geometry"] = page.evaluate("window.__tripApp.mapGeometrySnapshot()")
        page.keyboard.press("Escape")
        row["route_key_close_focus_return"] = page.locator("#routeLegendPanel").is_hidden() and page.evaluate("document.activeElement?.id === 'routeLegendToggle'")
        page.locator("#mapOptionsToggle").click()
        page.locator("#regionControls [data-region='yosemite']").click()
        page.locator("#dateSelect").select_option("10/7")
        page.wait_for_function("document.querySelector('.photo-marker[data-place-key=\"cooks\"]')?.getBoundingClientRect().width > 0", timeout=8000)
        # This is deliberately a real Playwright pointer activation. It is the
        # regression guard for the marker previously covered by map chrome.
        page.locator(".photo-marker[data-place-key='cooks']").click()
        page.wait_for_selector("#peek.show")
        row["marker_activation"] = "cooks"
        page.locator("#peek [data-peek-open]").click()
        page.wait_for_function("window.__tripApp.state.presentation.mode==='place'", timeout=8000)
        page.wait_for_function("document.querySelectorAll('#placeInspector .photo-slot img').length===3", timeout=8000)
        row["inspector_photos"] = page.locator("#placeInspector .photo-slot img").count()
        row["geometry"] = page.evaluate("window.__tripApp.mapGeometrySnapshot()")
        row["page_errors"] = list(page_errors)
        row["console_errors"] = list(console_errors)
        row["failed_requests"] = list(failed_requests)
        row["map_error_events"] = read_map_error_events(page)
        row["status"] = (
            "PASS"
            if row["marker_objects"] == row["expected_places"]
            and row["canvas"] == 1
            and not row["horizontal_overflow"]
            and row["broken_marker_images"] == 0
            and row["inspector_photos"] == 3
            and row["map_options_open"]
            and row["map_options_close_focus_return"]
            and row["route_key_open"]
            and row["route_key_close_focus_return"]
            and row["marker_activation"] == "cooks"
            and not any(marker.get("intersects_obstacle") for marker in row["geometry"].get("markers", []))
            and not row["page_errors"]
            else "FAIL"
        )
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(screenshot_path))
        row["map_error_listener_attached"] = map_listener_attached
        row["screenshot"] = recorded_path(screenshot_path)
        row["completed"] = True
    except Exception as error:
        capture_failure_evidence(
            row,
            page,
            case,
            screenshot_path,
            page_errors,
            console_errors,
            failed_requests,
            map_listener_attached,
            error,
        )
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
            env=worker_environment(),
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


def ordered_rows(rows_by_case: dict[tuple[str, int, int], dict]) -> list[dict]:
    return [rows_by_case.get(case_key(case), timeout_row(case, "case did not run")) for case in REQUIRED_CASES]


def finalize_evidence(evidence: dict, rows_by_case: dict[tuple[str, int, int], dict]) -> dict:
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
        identity = candidate_identity()
        evidence["candidate"] = identity["sha"]
        evidence["candidate_tree"] = identity["tree"]
        evidence["candidate_binding"] = "exact-clean-checkout"
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
