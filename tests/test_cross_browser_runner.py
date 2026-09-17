import json
import os
import signal
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import pipeline  # noqa: E402
import run_cross_browser  # noqa: E402


class TimedOutProcess:
    pid = 99123
    returncode = -signal.SIGKILL

    def wait(self, timeout=None):
        raise subprocess.TimeoutExpired(cmd="cross-browser-worker", timeout=timeout)


class DiagnosticLocator:
    def __init__(self, count):
        self.count_value = count

    def count(self):
        return self.count_value


class DiagnosticPage:
    def __init__(self):
        self.events = {}

    def set_default_timeout(self, _timeout):
        return None

    def on(self, name, callback):
        self.events[name] = callback

    def goto(self, *_args, **_kwargs):
        raise TimeoutError("style readiness did not complete")

    def evaluate(self, script):
        if script == run_cross_browser.MAP_ERROR_HOOK:
            return True
        if "__crossBrowserMapErrors ||" in script:
            return [{"message": "WebGL context lost", "source_id": None, "source": None, "tile_url": None}]
        if "Boolean(window.__tripApp?.map?.())" in script:
            return True
        if "provider_health" in script:
            return {"provider": "vector", "provider_health": {"vector": "loading"}}
        if "isStyleLoaded" in script:
            return False
        if "current:" in script:
            return {"current": 0, "expected": 36}
        raise AssertionError(f"unexpected diagnostic expression: {script}")

    def locator(self, selector):
        return DiagnosticLocator(1 if selector == ".maplibregl-canvas" else 0)

    def screenshot(self, path, **_kwargs):
        Path(path).write_bytes(b"diagnostic screenshot")


class DiagnosticContext:
    def __init__(self, result_path):
        self.result_path = result_path
        self.page = DiagnosticPage()
        self.result_existed_before_cleanup = False

    def new_page(self):
        return self.page

    def close(self):
        self.result_existed_before_cleanup = self.result_path.is_file()


class DiagnosticBrowser:
    def __init__(self, result_path):
        self.context = DiagnosticContext(result_path)

    def new_context(self, **_kwargs):
        return self.context

    def close(self):
        return None


class DiagnosticBrowserType:
    def __init__(self, result_path):
        self.result_path = result_path
        self.options = None
        self.browser = None

    def launch(self, **options):
        self.options = options
        self.browser = DiagnosticBrowser(self.result_path)
        return self.browser


class DiagnosticPlaywright:
    def __init__(self, result_path):
        self.firefox = DiagnosticBrowserType(result_path)

    def stop(self):
        return None


class CompletedProcess:
    pid = 99124
    returncode = 0

    def wait(self, timeout=None):
        return self.returncode


class CrossBrowserRunnerTests(unittest.TestCase):
    def test_linux_firefox_hosted_launch_mode_selection(self):
        with patch.dict(
            os.environ,
            {run_cross_browser.FIREFOX_MODE_ENV: run_cross_browser.FIREFOX_HOSTED_LINUX_MODE},
            clear=False,
        ), patch.object(run_cross_browser.sys, "platform", "linux"):
            firefox = run_cross_browser.browser_launch_options("firefox")
            webkit = run_cross_browser.browser_launch_options("webkit")
            self.assertFalse(firefox["headless"])
            self.assertEqual(firefox["env"][run_cross_browser.SOFTWARE_GL_ENV], "1")
            self.assertTrue(webkit["headless"])
            self.assertEqual(run_cross_browser.launch_mode("firefox"), "hosted-linux-xvfb")

        with patch.dict(
            os.environ,
            {run_cross_browser.FIREFOX_MODE_ENV: run_cross_browser.FIREFOX_HOSTED_LINUX_MODE},
            clear=False,
        ), patch.object(run_cross_browser.sys, "platform", "darwin"):
            self.assertTrue(run_cross_browser.browser_launch_options("firefox")["headless"])

    def test_hosted_linux_environment_reaches_isolated_worker(self):
        case = ("firefox", 1280, 800)
        with tempfile.TemporaryDirectory(prefix="cross-browser-test-") as directory:
            result_path = Path(directory) / "result.json"
            run_cross_browser.durable_json(
                result_path,
                dict(run_cross_browser.base_row(case), status="PASS", completed=True),
            )
            process = CompletedProcess()
            with patch.dict(
                os.environ,
                {run_cross_browser.FIREFOX_MODE_ENV: run_cross_browser.FIREFOX_HOSTED_LINUX_MODE},
                clear=False,
            ), patch.object(run_cross_browser.sys, "platform", "linux"), patch.object(
                run_cross_browser.subprocess, "Popen", return_value=process
            ) as popen:
                run_cross_browser.run_isolated_case(
                    case, result_path, Path(directory) / "firefox_1280_detail.png"
                )
        environment = popen.call_args.kwargs["env"]
        self.assertEqual(environment[run_cross_browser.FIREFOX_MODE_ENV], "hosted-linux")
        self.assertEqual(environment[run_cross_browser.SOFTWARE_GL_ENV], "1")

    def test_failure_diagnostics_are_persisted_before_teardown(self):
        case = ("firefox", 1280, 800)
        with tempfile.TemporaryDirectory(prefix="cross-browser-test-") as directory:
            result_path = Path(directory) / "result.json"
            screenshot_path = Path(directory) / "firefox_1280_detail.png"
            playwright = DiagnosticPlaywright(result_path)
            with patch.object(run_cross_browser, "start_playwright", return_value=playwright):
                code = run_cross_browser.worker_case(case, result_path, screenshot_path)
            payload = json.loads(result_path.read_text())
            result_existed_before_cleanup = playwright.firefox.browser.context.result_existed_before_cleanup
            screenshot_exists = screenshot_path.is_file()
        self.assertEqual(code, 0)
        self.assertTrue(result_existed_before_cleanup)
        self.assertEqual(payload["status"], "UNVERIFIED")
        self.assertFalse(payload["completed"])
        self.assertTrue(screenshot_exists)
        diagnostics = payload["diagnostics"]
        self.assertEqual(diagnostics["browser"], "firefox")
        self.assertEqual(diagnostics["viewport"], {"width": 1280, "height": 800})
        self.assertTrue(diagnostics["map_object_present"])
        self.assertEqual(diagnostics["provider"], "vector")
        self.assertEqual(diagnostics["provider_health"]["vector"], "loading")
        self.assertFalse(diagnostics["is_style_loaded"])
        self.assertEqual(diagnostics["canvas_count"], 1)
        self.assertEqual(diagnostics["current_marker_count"], 0)
        self.assertEqual(diagnostics["expected_marker_count"], 36)
        self.assertTrue(diagnostics["map_error_events"])
        self.assertEqual(diagnostics["failure_screenshot"], str(screenshot_path))

    def test_completed_child_result_survives_teardown_failure(self):
        case = ("webkit", 390, 844)
        with tempfile.TemporaryDirectory(prefix="cross-browser-test-") as directory:
            result_path = Path(directory) / "result.json"
            row = run_cross_browser.base_row(case)
            row.update({"status": "PASS", "completed": True, "screenshot": "QA/map_first/screenshots/webkit_390_detail.png"})
            run_cross_browser.durable_json(result_path, row)
            process = TimedOutProcess()
            with patch.object(run_cross_browser.subprocess, "Popen", return_value=process), patch.object(
                run_cross_browser, "terminate_process_group", return_value=(True, [])
            ), patch.object(run_cross_browser, "CASE_TIMEOUT_SECONDS", 1):
                preserved, warnings, errors = run_cross_browser.run_isolated_case(
                    case, result_path, Path(directory) / "webkit_390_detail.png"
                )
        self.assertEqual(preserved["status"], "PASS")
        self.assertTrue(preserved["completed"])
        self.assertTrue(any("during teardown" in warning for warning in warnings))
        self.assertEqual(errors, [])

    def test_timeout_yields_terminal_non_pass_evidence(self):
        case = ("firefox", 1280, 800)
        with tempfile.TemporaryDirectory(prefix="cross-browser-test-") as directory:
            process = TimedOutProcess()
            with patch.object(run_cross_browser.subprocess, "Popen", return_value=process), patch.object(
                run_cross_browser, "terminate_process_group", return_value=(True, [])
            ), patch.object(run_cross_browser, "CASE_TIMEOUT_SECONDS", 1):
                row, _warnings, errors = run_cross_browser.run_isolated_case(
                    case, Path(directory) / "missing.json", Path(directory) / "firefox_1280_detail.png"
                )
        self.assertIn(row["status"], {"FAIL", "UNVERIFIED"})
        self.assertNotEqual(row["status"], "PASS")
        self.assertFalse(row["completed"])
        self.assertTrue(errors)

    def test_all_four_required_rows_are_needed_for_pass(self):
        self.assertEqual(
            run_cross_browser.REQUIRED_CASES,
            (("firefox", 1280, 800), ("firefox", 390, 844), ("webkit", 1280, 800), ("webkit", 390, 844)),
        )
        rows = {
            run_cross_browser.case_key(case): dict(run_cross_browser.base_row(case), status="PASS", completed=True)
            for case in run_cross_browser.REQUIRED_CASES
        }
        evidence = run_cross_browser.finalize_evidence(run_cross_browser.parent_evidence(), rows)
        self.assertEqual(evidence["status"], "PASS")
        self.assertEqual(len(evidence["rows"]), 4)
        self.assertEqual({run_cross_browser.case_key(case) for case in run_cross_browser.REQUIRED_CASES}, {
            run_cross_browser.case_key((row["browser"], row["width"], row["height"])) for row in evidence["rows"]
        })
        rows.pop(run_cross_browser.case_key(("webkit", 390, 844)))
        evidence = run_cross_browser.finalize_evidence(run_cross_browser.parent_evidence(), rows)
        self.assertEqual(evidence["status"], "FAIL")
        self.assertEqual(len(evidence["rows"]), 4)

        rows[run_cross_browser.case_key(("webkit", 390, 844))] = dict(
            run_cross_browser.base_row(("webkit", 390, 843)), status="PASS", completed=True
        )
        evidence = run_cross_browser.finalize_evidence(run_cross_browser.parent_evidence(), rows)
        self.assertEqual(evidence["status"], "FAIL")

    def test_diagnostic_evidence_cannot_promote_unverified_case_to_pass(self):
        rows = {
            run_cross_browser.case_key(case): dict(run_cross_browser.base_row(case), status="PASS", completed=True)
            for case in run_cross_browser.REQUIRED_CASES
        }
        failed_case = ("firefox", 390, 844)
        rows[run_cross_browser.case_key(failed_case)].update(
            {
                "status": "UNVERIFIED",
                "completed": False,
                "diagnostics": {"is_style_loaded": False, "current_marker_count": 0, "expected_marker_count": 36},
            }
        )
        evidence = run_cross_browser.finalize_evidence(run_cross_browser.parent_evidence(), rows)
        self.assertEqual(evidence["status"], "FAIL")
        self.assertEqual(evidence["rows"][1]["status"], "UNVERIFIED")

    def test_stale_running_output_is_not_accepted(self):
        with tempfile.TemporaryDirectory(prefix="cross-browser-test-") as directory:
            evidence_path = Path(directory) / "cross_browser.json"
            evidence_path.write_text(json.dumps({"status": "RUNNING"}) + "\n")
            self.assertEqual(pipeline.evidence_status(evidence_path, 0), "UNVERIFIED")

    def test_child_process_group_is_reaped_after_escalation(self):
        child = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(30)",
            ],
            start_new_session=True,
        )
        original_term = run_cross_browser.TERM_GRACE_SECONDS
        original_kill = run_cross_browser.KILL_GRACE_SECONDS
        run_cross_browser.TERM_GRACE_SECONDS = 0.05
        run_cross_browser.KILL_GRACE_SECONDS = 0.5
        try:
            reaped, warnings = run_cross_browser.terminate_process_group(child, "test worker")
        finally:
            run_cross_browser.TERM_GRACE_SECONDS = original_term
            run_cross_browser.KILL_GRACE_SECONDS = original_kill
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait(timeout=2)
        self.assertTrue(reaped, warnings)
        self.assertIsNotNone(child.poll())


if __name__ == "__main__":
    unittest.main()
