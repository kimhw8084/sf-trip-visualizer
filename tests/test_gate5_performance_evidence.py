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
        "chromium", "151.0.7922.34", {"width": 1440, "height": 900}, False, False, "candidate", 8
    )
    value["os"]["system"] = os_name
    value["architecture"]["machine"] = machine
    return value


def stats(values):
    return gate5.quantiles(values)


def source_binding(revision):
    return {
        "binding": "exact_commit",
        "status": "PASS",
        "claimed_revision": revision,
        "checked_out_revision": revision,
        "source_worktree_dirty": False,
        "source_fingerprint": {"sha256": revision, "file_count": 1, "tracked_head": revision},
    }


def samples(values, environment=None, revision="candidate"):
    return {
        "environment_signature": environment or signature(),
        "source_binding": source_binding(revision),
        "cold_milestones": {"first_actionable_state": stats(values)},
        "warm_milestones": {"first_actionable_state": stats(values)},
        "interactions": {"route": stats(values)},
    }


def paired_measurements(baseline_values, candidate_values):
    rows = []
    for index, (baseline, candidate) in enumerate(zip(baseline_values, candidate_values)):
        block = index // 4 + 1
        first_candidate = (index % 2) == 0
        candidate_metrics = {
            "cold_milestones": {"first_actionable_state": candidate},
            "warm_milestones": {"first_actionable_state": candidate},
            "interactions": {"route": candidate},
        }
        baseline_metrics = {
            "cold_milestones": {"first_actionable_state": baseline},
            "warm_milestones": {"first_actionable_state": baseline},
            "interactions": {"route": baseline},
        }
        rows.append(
            {
                "block": block,
                "pair": index + 1,
                "pair_in_block": index % 4 + 1,
                "order": ["candidate", "baseline"] if first_candidate else ["baseline", "candidate"],
                "candidate": candidate_metrics,
                "baseline": baseline_metrics,
            }
        )
    return rows


class Gate5PerformanceEvidenceTests(unittest.TestCase):
    def test_same_environment_non_regression_passes(self):
        baseline_values = [100, 110, 120, 105, 115, 125, 108, 118]
        candidate_values = [95, 105, 115, 100, 110, 120, 103, 113]
        baseline = samples(baseline_values, revision="base")
        candidate = samples(candidate_values)
        result = gate5.compare_performance(candidate, baseline, paired_measurements(baseline_values, candidate_values))
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["failures"], [])

    def test_all_paired_candidate_values_slower_despite_high_baseline_variance_fails(self):
        baseline_values = [100, 1000, 110, 900, 120, 800, 130, 700]
        candidate_values = [value + 60 for value in baseline_values]
        baseline = samples(baseline_values, revision="base")
        candidate = samples(candidate_values)
        result = gate5.compare_performance(candidate, baseline, paired_measurements(baseline_values, candidate_values))
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(result["failures"])
        interaction = next(item for item in result["comparisons"] if item["metric"] == "interactions.route")
        self.assertEqual(interaction["pair_evidence"]["positive_pairs"], 8)
        self.assertLess(interaction["pair_evidence"]["materiality_guard_ms"], 60)

    def test_materiality_below_observed_noise_requires_verification(self):
        baseline_values = [100, 120, 140, 160, 105, 125, 145, 165]
        candidate_values = [102, 123, 137, 163, 107, 128, 142, 168]
        result = gate5.compare_performance(
            samples(candidate_values),
            samples(baseline_values, revision="base"),
            paired_measurements(baseline_values, candidate_values),
        )
        self.assertEqual(result["status"], "VERIFY_REQUIRED")
        self.assertEqual(result["failures"], [])
        self.assertTrue(result["verify_reasons"])

    def test_paired_direction_inconsistent_across_blocks_requires_verification(self):
        baseline_values = [100, 110, 120, 130, 200, 210, 220, 230]
        candidate_values = [150, 160, 170, 180, 140, 150, 160, 170]
        result = gate5.compare_performance(
            samples(candidate_values),
            samples(baseline_values, revision="base"),
            paired_measurements(baseline_values, candidate_values),
        )
        self.assertEqual(result["status"], "VERIFY_REQUIRED")
        self.assertEqual(result["failures"], [])
        row = next(item for item in result["comparisons"] if item["metric"] == "interactions.route")
        self.assertFalse(row["pair_evidence"]["direction_consistent_across_blocks"])

    def test_same_source_repeated_batches_with_conflicting_classification_require_verification(self):
        baseline_values = [100, 110, 120, 130, 200, 210, 220, 230]
        candidate_values = [150, 160, 170, 180, 140, 150, 160, 170]
        candidate = samples(candidate_values, revision="same-source")
        baseline = samples(baseline_values, revision="same-source")
        result = gate5.compare_performance(candidate, baseline, paired_measurements(baseline_values, candidate_values))
        self.assertEqual(result["status"], "VERIFY_REQUIRED")
        self.assertEqual(result["failures"], [])

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
        result = gate5.compare_performance(samples([100] * 8), None)
        self.assertEqual(result["status"], "VERIFY_REQUIRED")
        self.assertIn("no regression guard", result["reason"])

    def test_missing_signature_requires_verification(self):
        baseline = samples([100] * 8, revision="base")
        candidate = copy.deepcopy(baseline)
        del candidate["environment_signature"]
        result = gate5.compare_performance(candidate, baseline)
        self.assertEqual(result["status"], "VERIFY_REQUIRED")
        self.assertEqual(result["failures"], [])

    def test_missing_source_binding_requires_verification(self):
        baseline = samples([100] * 8, revision="base")
        candidate = copy.deepcopy(baseline)
        del candidate["source_binding"]
        result = gate5.compare_performance(candidate, baseline)
        self.assertEqual(result["status"], "VERIFY_REQUIRED")
        self.assertEqual(result["failures"], [])

    def test_order_sensitive_regression_requires_verification_with_pair_evidence(self):
        baseline_values = [100, 110, 120, 130, 140, 150, 160, 170]
        candidate_values = [160, 105, 170, 115, 200, 145, 210, 155]
        baseline = samples(baseline_values, revision="base")
        candidate = samples(candidate_values)
        paired = paired_measurements(baseline_values, candidate_values)
        result = gate5.compare_performance(candidate, baseline, paired)
        self.assertEqual(result["status"], "VERIFY_REQUIRED")
        self.assertEqual(result["failures"], [])
        row = next(item for item in result["comparisons"] if item["metric"] == "cold_milestones.first_actionable_state")
        self.assertFalse(row["pair_evidence"]["decisive_regression"])
        self.assertLess(row["pair_evidence"]["positive_pairs"], row["pair_evidence"]["pair_count"])

    def test_source_binding_revision_mismatch_is_verify_required(self):
        baseline = samples([100] * 8, revision="base")
        candidate = samples([100] * 8)
        candidate["source_binding"]["checked_out_revision"] = "different"
        result = gate5.compare_performance(candidate, baseline)
        self.assertEqual(result["status"], "VERIFY_REQUIRED")
        self.assertEqual(result["failures"], [])

    def test_distribution_only_evidence_is_never_a_hard_pass(self):
        result = gate5.compare_performance(samples([500] * 8), samples([100] * 8, revision="base"))
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
