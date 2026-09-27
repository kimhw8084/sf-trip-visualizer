import hashlib
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import pipeline  # noqa: E402
import prepare_public_site  # noqa: E402
import security_privacy  # noqa: E402


class PublicQualificationProjectionTests(unittest.TestCase):
    def qualification_report(self, revision):
        return {
            "schema_version": 1,
            "project": "sf-trip-visualizer",
            "status": "PASS",
            "candidate_head": revision,
            "external_verify_required": ["native_safari", "real_iphone_ipad", "independent_review"],
            "build": {
                "manifest_sha256": "a" * 64,
                "modular_index_sha256": "b" * 64,
                "standalone_sha256": "c" * 64,
            },
            "tests": [
                {
                    "name": "phone_field_surface",
                    "command": "python3 scripts/qa_phone_field_surface.py",
                    "evidence": "QA/CHG-232/phone_field_surface.json",
                    "status": "PASS",
                    "returncode": 0,
                    "timeout_seconds": 300,
                    "stdout_tail": "artifact path /home/runner/work/repo/.build/portability-fixture/output",
                    "stderr_tail": "diagnostic /Users/runner/Library/Caches/fixture",
                },
                {
                    "name": "gate5_field_quality",
                    "command": "python3 scripts/qa_gate5_field_quality.py",
                    "evidence": "QA/CHG-232/gate5/candidate.json",
                    "status": "PASS",
                    "returncode": 0,
                    "timeout_seconds": 900,
                    "execution_status": "PASS",
                    "acceptance_status": "VERIFY_REQUIRED",
                    "status_reason": "External review and native device evidence remain outstanding.",
                    "stdout_tail": "gate 5 diagnostic output",
                    "stderr_tail": "",
                },
            ],
        }

    def test_projection_retains_release_truth_and_removes_diagnostic_tails(self):
        revision = pipeline.current_revision()
        original = self.qualification_report(revision)
        with tempfile.TemporaryDirectory(prefix="qualification-projection-") as directory:
            internal_path = Path(directory) / "qualification.json"
            public_path = Path(directory) / ".release-qualification.json"
            internal_path.write_text(json.dumps(original, ensure_ascii=False, indent=2) + "\n")
            original_bytes = internal_path.read_bytes()

            projection = prepare_public_site.public_qualification_projection(json.loads(original_bytes))
            public_path.write_text(json.dumps(projection, ensure_ascii=False, indent=2) + "\n")

            self.assertEqual(internal_path.read_bytes(), original_bytes)
            expected = json.loads(original_bytes)
            for test in expected["tests"]:
                test.pop("stdout_tail", None)
                test.pop("stderr_tail", None)
            self.assertEqual(projection, expected)
            self.assertEqual(projection["candidate_head"], original["candidate_head"])
            self.assertEqual(projection["status"], original["status"])
            self.assertEqual(
                [test["status"] for test in projection["tests"]],
                [test["status"] for test in original["tests"]],
            )
            self.assertEqual(projection["tests"][1]["execution_status"], "PASS")
            self.assertEqual(projection["tests"][1]["acceptance_status"], "VERIFY_REQUIRED")
            self.assertEqual(projection["external_verify_required"], original["external_verify_required"])
            self.assertEqual(projection["build"], original["build"])
            self.assertTrue(all("stdout_tail" not in test and "stderr_tail" not in test for test in projection["tests"]))
            self.assertIsNone(re.search(r"/(?:Users|home)/[A-Za-z0-9._-]+/", public_path.read_text()))

            scan = security_privacy.check_artifact_paths([public_path], ROOT)
            self.assertEqual(scan["status"], "PASS", scan["findings"])
            self.assertEqual(scan["findings"], [])

    def test_verify_public_passes_with_original_qualification_attestation(self):
        revision = pipeline.current_revision()
        original = self.qualification_report(revision)
        original["build"]["standalone_sha256"] = hashlib.sha256(b"standalone fixture\n").hexdigest()
        with tempfile.TemporaryDirectory(prefix="verify-public-projection-") as directory:
            root = Path(directory)
            qualification_path = root / "qualification.json"
            qualification_path.write_text(json.dumps(original, ensure_ascii=False, indent=2) + "\n")
            original_qualification_sha = hashlib.sha256(qualification_path.read_bytes()).hexdigest()

            build = root / "build"
            modular = build / "modular"
            standalone = build / "standalone"
            modular.mkdir(parents=True)
            standalone.mkdir()
            (modular / "index.html").write_text("<!doctype html><title>Fixture</title>\n")
            standalone_path = standalone / "SF_Smart_Minority_Map_First_Standalone.html"
            standalone_path.write_text("standalone fixture\n")
            build_manifest_path = build / "build_manifest.json"
            build_manifest_path.write_text(
                json.dumps(
                    {
                        "modular": {"sha256": pipeline.digest(modular / "index.html")},
                        "standalone": {"path": "standalone/SF_Smart_Minority_Map_First_Standalone.html"},
                    }
                )
            )

            public = root / "public"
            public.mkdir()
            (public / "index.html").write_text("<!doctype html><title>Fixture</title>\n")
            projection = prepare_public_site.public_qualification_projection(original)
            (public / ".release-qualification.json").write_text(
                json.dumps(projection, ensure_ascii=False, indent=2) + "\n"
            )
            (public / ".nojekyll").touch()
            artifact_sha, file_count, byte_count = pipeline.tree_digest(public, {".release-provenance.json"})
            active_trip = pipeline.load_package(pipeline.DEFAULT_PACKAGE)
            provenance = {
                "trip_identity": active_trip["trip_identity"],
                "display_title": active_trip["display_title"],
                "slug": active_trip["slug"],
                "currency": active_trip["currency"],
                "tested_sha": revision,
                "qualification_sha256": original_qualification_sha,
                "build_manifest_sha256": pipeline.digest(build_manifest_path),
                "modular_index_sha256": pipeline.digest(modular / "index.html"),
                "artifact_sha256_excluding_provenance": artifact_sha,
                "artifact_file_count_excluding_provenance": file_count,
                "artifact_bytes_excluding_provenance": byte_count,
            }
            (public / ".release-provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")

            release_evidence = root / "release-evidence"
            release_evidence.mkdir()

            def scan_public_artifacts(expected_revision, roots):
                self.assertEqual(expected_revision, revision)
                scan = security_privacy.check_artifact_paths(roots, ROOT)
                return {"status": scan["status"], "secret_scan": {"generated_artifacts": scan}}

            with (
                patch.object(pipeline, "PUBLIC", public),
                patch.object(pipeline, "BUILD", build),
                patch.object(pipeline, "QUALIFICATION", qualification_path),
                patch.object(pipeline, "RELEASE_EVIDENCE", release_evidence),
                patch.object(pipeline, "require_qualified", return_value=revision),
                patch.object(pipeline, "audit_tree", return_value={"status": "PASS"}),
                patch.object(pipeline, "run_security_gate", side_effect=scan_public_artifacts),
                patch.object(pipeline, "delivery_report", return_value={"status": "PASS"}),
            ):
                report = pipeline.verify_public(revision)

            self.assertEqual(report["status"], "PASS")
            self.assertTrue(report["checks"]["qualification_sha256"])
            self.assertTrue(report["checks"]["security_privacy"])
            self.assertEqual(report["security_privacy"]["secret_scan"]["generated_artifacts"]["findings"], [])
            self.assertEqual(
                hashlib.sha256(qualification_path.read_bytes()).hexdigest(),
                original_qualification_sha,
            )
            self.assertEqual(json.loads(qualification_path.read_text()), original)


if __name__ == "__main__":
    unittest.main()
