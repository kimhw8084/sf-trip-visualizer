import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import pipeline  # noqa: E402
import qa_gate5_field_quality  # noqa: E402


def report(status="PASS", candidate_head="candidate", binding="exact_commit", failures=None, boundaries=None):
    return {
        "candidate_head": candidate_head,
        "candidate_tree": "tree",
        "source_binding": {
            "binding": binding,
            "status": "PASS" if binding == "exact_commit" else "FAIL",
            "claimed_revision": candidate_head,
            "checked_out_revision": candidate_head,
            "source_worktree_dirty": False,
        },
        "status": status,
        "failures": [] if failures is None else failures,
        "verify_required": boundaries if boundaries is not None else (["native Safari and physical-device evidence"] if status == "VERIFY_REQUIRED" else []),
    }


class Gate5QualificationTests(unittest.TestCase):
    def validate(self, payload=None, returncode=0, expected="candidate", started=0):
        with tempfile.TemporaryDirectory(prefix="gate5-status-") as directory:
            path = Path(directory) / "candidate.json"
            if payload is not None:
                if isinstance(payload, str):
                    path.write_text(payload)
                else:
                    path.write_text(json.dumps(payload))
            return pipeline.validate_gate5_execution(path, returncode, expected, started)

    def test_completed_pass_is_accepted(self):
        result = self.validate(report("PASS"))
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(result["process_completed"])

    def test_completed_verify_required_is_accepted_as_external_boundary(self):
        result = self.validate(report("VERIFY_REQUIRED"))
        decision = pipeline.qualification_decision([
            {"name": "canonical_truth", "status": "PASS"},
            {"name": "gate5_field_quality", "status": result["status"], "returncode": 0, "process_completed": result["process_completed"]},
        ])
        self.assertEqual(decision["status"], "PASS")
        self.assertEqual(decision["external_verify_required"], ["gate5_field_quality"])

    def test_timeout_is_execution_failure_even_if_old_status_would_be_verify_required(self):
        result = self.validate(report("VERIFY_REQUIRED"), returncode=124)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["execution_status"], "UNVERIFIED")
        decision = pipeline.qualification_decision([
            {"name": "gate5_field_quality", "status": result["status"], "returncode": 124, "process_completed": result["process_completed"]},
        ])
        self.assertEqual(decision["status"], "FAIL")
        self.assertEqual(decision["external_verify_required"], [])

    def test_nonzero_missing_stale_wrong_head_binding_malformed_unverified_and_contradictory_fail_closed(self):
        cases = [
            (report("PASS"), 7, "FAILED"),
            (None, 0, "MISSING"),
            (report("PASS"), 0, "STALE"),
            (report("PASS", candidate_head="other"), 0, "MISMATCH"),
            (report("PASS", binding="source_fingerprint"), 0, "MISMATCH"),
            ("not-json", 0, "MALFORMED"),
            (report("UNVERIFIED"), 0, "UNVERIFIED"),
            (report("PASS", failures=["contradictory failure"]), 0, "FAILED"),
            (report("VERIFY_REQUIRED", boundaries=[]), 0, "MALFORMED"),
        ]
        for payload, returncode, execution_status in cases:
            with self.subTest(execution_status=execution_status):
                if execution_status == "STALE":
                    with tempfile.TemporaryDirectory(prefix="gate5-stale-") as directory:
                        path = Path(directory) / "candidate.json"
                        path.write_text(json.dumps(payload))
                        os.utime(path, (1, 1))
                        result = pipeline.validate_gate5_execution(path, returncode, "candidate", 2_000_000_000)
                elif payload == "not-json":
                    result = self.validate(payload, returncode)
                else:
                    result = self.validate(payload, returncode)
                self.assertEqual(result["status"], "FAIL")
                self.assertEqual(result["execution_status"], execution_status)

    def test_stale_expected_output_is_removed_before_gate5_invocation(self):
        with tempfile.TemporaryDirectory(prefix="gate5-freshness-") as directory:
            path = Path(directory) / "candidate.json"
            path.write_text(json.dumps(report("PASS")))
            started = pipeline.prepare_gate5_output(path)
            self.assertFalse(path.exists())
            self.assertGreater(started, 0)

    def test_gate5_component_is_singular_and_has_dedicated_timeout(self):
        self.assertEqual(sum(name == "gate5_field_quality" for name, _script, _output in pipeline.COMPONENTS), 1)
        self.assertEqual(pipeline.GATE5_TIMEOUT_SECONDS, 900)
        self.assertNotEqual(pipeline.GATE5_TIMEOUT_SECONDS, pipeline.COMPONENT_TIMEOUT_SECONDS)

    def test_release_mode_cannot_assemble_after_gate5_execution_failure(self):
        failed = {"status": "FAIL", "candidate_head": "candidate", "errors": ["Gate 5 timed out"]}
        with patch.object(pipeline, "run_qualification", return_value=failed), patch.object(pipeline, "assemble_public") as assemble:
            with patch.object(sys, "argv", ["pipeline.py", "release", "--revision", "candidate"]):
                result = pipeline.main()
        self.assertEqual(result, 1)
        assemble.assert_not_called()

    def test_gate5_verify_required_process_exit_is_zero_but_unverified_is_not(self):
        self.assertEqual(qa_gate5_field_quality.process_exit_code("VERIFY_REQUIRED"), 0)
        self.assertEqual(qa_gate5_field_quality.process_exit_code("PASS"), 0)
        self.assertEqual(qa_gate5_field_quality.process_exit_code("UNVERIFIED"), 1)
        self.assertEqual(qa_gate5_field_quality.process_exit_code("FAIL"), 1)


if __name__ == "__main__":
    unittest.main()
