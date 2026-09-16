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


class CrossBrowserRunnerTests(unittest.TestCase):
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
