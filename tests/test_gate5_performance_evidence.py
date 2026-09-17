import copy
import unittest
from unittest.mock import patch


import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import pipeline  # noqa: E402
import qa_gate5_field_quality as gate5  # noqa: E402


def signature(os_name="Linux", machine="x86_64"):
    value = gate5.performance_environment_signature(
        "chromium", "151.0.7922.34", {"width": 1440, "height": 900}, False, False, "candidate", 3
    )
    value["os"]["system"] = os_name
    value["architecture"]["machine"] = machine
    return value


def stats(values):
    return gate5.quantiles(values)


def samples(values, environment=None):
    return {
        "environment_signature": environment or signature(),
        "cold_milestones": {"first_actionable_state": stats(values)},
        "warm_milestones": {"first_actionable_state": stats(values)},
        "interactions": {"route": stats(values)},
    }


class Gate5PerformanceEvidenceTests(unittest.TestCase):
    def test_same_environment_non_regression_passes(self):
        baseline = samples([100, 110, 120])
        candidate = samples([100, 105, 115])
        result = gate5.compare_performance(candidate, baseline)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["failures"], [])

    def test_same_environment_material_regression_fails_with_adequate_variance(self):
        baseline = samples([100, 110, 120])
        candidate = samples([160, 165, 170])
        result = gate5.compare_performance(candidate, baseline)
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(result["failures"])

    def test_low_variance_ambiguous_regression_requires_verification(self):
        baseline = samples([100, 100.1, 100.2])
        candidate = samples([101, 101, 101])
        result = gate5.compare_performance(candidate, baseline)
        self.assertEqual(result["status"], "VERIFY_REQUIRED")
        self.assertEqual(result["failures"], [])
        self.assertTrue(result["verify_reasons"])

    def test_cross_os_architecture_never_becomes_hard_failure(self):
        baseline = samples([100, 110, 120], signature("Darwin", "arm64"))
        candidate = samples([500, 500, 500], signature("Linux", "x86_64"))
        result = gate5.compare_performance(candidate, baseline)
        self.assertEqual(result["status"], "VERIFY_REQUIRED")
        self.assertEqual(result["failures"], [])
        self.assertTrue(any(item["field"] == "environment.os.system" for item in result["mismatch"]))
        self.assertTrue(any(item["field"] == "environment.architecture.machine" for item in result["mismatch"]))
        self.assertEqual(result["candidate_environment_signature"], candidate["environment_signature"])
        self.assertEqual(result["baseline_environment_signature"], baseline["environment_signature"])

    def test_missing_baseline_requires_verification(self):
        result = gate5.compare_performance(samples([100, 100, 100]), None)
        self.assertEqual(result["status"], "VERIFY_REQUIRED")
        self.assertIn("no regression guard", result["reason"])

    def test_missing_signature_requires_verification(self):
        baseline = samples([100, 100, 100])
        candidate = copy.deepcopy(baseline)
        del candidate["environment_signature"]
        result = gate5.compare_performance(candidate, baseline)
        self.assertEqual(result["status"], "VERIFY_REQUIRED")
        self.assertEqual(result["failures"], [])

    def test_revision_fingerprint_mismatch_is_fail_closed(self):
        fingerprint = {"sha256": "source-hash", "file_count": 1, "tracked_head": "actual"}
        with patch.object(gate5, "revision", return_value="actual"), patch.object(
            gate5, "candidate_fingerprint", return_value=fingerprint
        ), patch.object(gate5, "status_paths", return_value=[]):
            result = gate5.source_binding("claimed")
        self.assertEqual(result["binding"], "mismatch")
        self.assertEqual(result["status"], "VERIFY_REQUIRED")
        self.assertEqual(result["source_fingerprint"], fingerprint)

    def test_dirty_matching_revision_is_fingerprint_bound_not_exact_commit(self):
        fingerprint = {"sha256": "source-hash", "file_count": 1, "tracked_head": "actual"}
        with patch.object(gate5, "revision", return_value="actual"), patch.object(
            gate5, "candidate_fingerprint", return_value=fingerprint
        ), patch.object(gate5, "status_paths", return_value=["src/app_phase7.js"]):
            result = gate5.source_binding("actual")
        self.assertEqual(result["binding"], "source_fingerprint")
        self.assertEqual(result["status"], "VERIFY_REQUIRED")
        self.assertNotEqual(result["binding"], "exact_commit")

    def test_pipeline_preserves_verify_required_as_non_pass_status(self):
        with self.subTest("explicit status"):
            path = ROOT / "tests" / "_gate5_verify_required_test.json"
            try:
                path.write_text('{"status":"VERIFY_REQUIRED"}\n')
                self.assertEqual(pipeline.evidence_status(path, 0), "VERIFY_REQUIRED")
            finally:
                path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
