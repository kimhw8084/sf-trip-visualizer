import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import hosted_linux_pipeline  # noqa: E402
import pipeline  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "manifests" / "canonical_pipeline.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class CanonicalPipelineTests(unittest.TestCase):
    def test_manifest_names_one_current_authority(self):
        manifest = json.loads(MANIFEST.read_text())
        self.assertEqual(manifest["authority"]["canonical_pipeline"], "scripts/pipeline.py")
        self.assertEqual(manifest["authority"]["canonical_build"], "scripts/build_map_first.py")
        self.assertEqual(manifest["authority"]["canonical_data"], "data/phase7_app_data.json")
        self.assertIn("index.html", manifest["historical_or_legacy"])
        self.assertIn("QA/final_acceptance.json", manifest["historical_or_legacy"])

    def test_current_product_counts_and_provider_contract(self):
        manifest = json.loads(MANIFEST.read_text())
        data = json.loads((ROOT / manifest["authority"]["canonical_data"]).read_text())
        photos = json.loads((ROOT / "manifests/asset_manifest.json").read_text())
        expected = manifest["invariants"]
        self.assertEqual(len(data["markers"]), expected["places"])
        self.assertEqual(len(photos["assets"]), expected["photos"])
        self.assertEqual(len(data["timeline"]), expected["timeline_cards"])
        self.assertEqual(len(data["legs"]), expected["route_legs"])
        self.assertEqual(set(data["providers"]), set(expected["providers"]))
        self.assertEqual(len(data["dates"]), expected["dates"])
        self.assertEqual(set(data["place_region"]), {marker["place_key"] for marker in data["markers"]})

    def test_build_does_not_mutate_authored_data(self):
        authored = ROOT / "data/phase7_app_data.json"
        before = sha256(authored)
        with tempfile.TemporaryDirectory(prefix="canonical-build-test-") as output:
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts/build_map_first.py"), "--output-dir", output],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(Path(output, "modular/index.html").is_file())
            self.assertTrue(Path(output, "standalone/SF_Smart_Minority_Map_First_Standalone.html").is_file())
        self.assertEqual(before, sha256(authored))

    def test_pages_workflow_cannot_bypass_release_gate(self):
        workflow = (ROOT / ".github/workflows/deploy-pages.yml").read_text()
        self.assertIn("branches: [main]", workflow)
        self.assertNotIn('"codex/**"', workflow)
        self.assertIn("ref: ${{ github.sha }}", workflow)
        self.assertIn("python3 scripts/hosted_linux_pipeline.py release --revision \"$GITHUB_SHA\"", workflow)
        self.assertIn("python3 scripts/pipeline.py verify-public", workflow)
        for forbidden in ("prepare_public_site.py", "build_final.py", "package_final.py", "run_acceptance.py", "run_live_providers.py"):
            self.assertNotIn(forbidden, workflow)
        for relative in ("scripts/build_final.py", "scripts/package_final.py", "scripts/run_acceptance.py", "scripts/run_live_providers.py", "scripts/expand_photo_manifest.py"):
            self.assertIn("DEPRECATED LEGACY ENTRY POINT", (ROOT / relative).read_text())

    def test_candidate_and_pages_share_fail_closed_hosted_linux_contract(self):
        candidate = (ROOT / ".github/workflows/candidate-qualification.yml").read_text()
        pages = (ROOT / ".github/workflows/deploy-pages.yml").read_text()
        runner = (ROOT / "scripts/hosted_linux_pipeline.py").read_text()
        self.assertIn("python3 scripts/hosted_linux_pipeline.py qualify --revision \"$GITHUB_SHA\"", candidate)
        self.assertIn("python3 scripts/hosted_linux_pipeline.py release --revision \"$GITHUB_SHA\"", pages)
        self.assertIn('"xvfb-run"', runner)
        self.assertIn("TRIP_CROSS_BROWSER_FIREFOX_MODE", runner)
        self.assertIn("LIBGL_ALWAYS_SOFTWARE", runner)
        self.assertIn("scripts/pipeline.py", runner)
        self.assertEqual(
            hosted_linux_pipeline.pipeline_command("qualify", "candidate")[0:2],
            hosted_linux_pipeline.pipeline_command("release", "candidate")[0:2],
        )
        self.assertEqual(
            hosted_linux_pipeline.contract_failures(
                {
                    "TRIP_CROSS_BROWSER_FIREFOX_MODE": "hosted-linux",
                    "LIBGL_ALWAYS_SOFTWARE": "1",
                    "DISPLAY": ":99",
                },
                platform="linux",
            ),
            [],
        )
        self.assertTrue(
            hosted_linux_pipeline.contract_failures(
                {"TRIP_CROSS_BROWSER_FIREFOX_MODE": "hosted-linux"},
                platform="linux",
            )
        )

    def test_release_qualification_fails_closed_without_hosted_linux_contract(self):
        with patch.dict(hosted_linux_pipeline.os.environ, {}, clear=True), patch.object(hosted_linux_pipeline.sys, "platform", "linux"):
            report = pipeline.run_qualification("candidate", require_clean=True)
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any("Hosted Linux release qualification contract" in error for error in report["errors"]))

    def test_candidate_workflow_is_exact_sha_non_deploying_and_evidence_backed(self):
        workflow = (ROOT / ".github/workflows/candidate-qualification.yml").read_text()
        self.assertIn('      - "codex/**"', workflow)
        self.assertIn("contents: read", workflow)
        self.assertNotIn("pages: write", workflow)
        self.assertNotIn("id-token: write", workflow)
        self.assertNotIn("deploy-pages", workflow)
        self.assertIn("ref: ${{ github.sha }}", workflow)
        self.assertIn("fetch-depth: 0", workflow)
        self.assertIn("lfs: true", workflow)
        self.assertIn('python-version: "3.11"', workflow)
        self.assertIn("pip install --require-hashes -r requirements-qa.txt", workflow)
        self.assertIn("playwright install --with-deps chromium firefox webkit", workflow)
        self.assertIn('python3 scripts/hosted_linux_pipeline.py qualify --revision "$GITHUB_SHA"', workflow)
        self.assertIn("python3 -m unittest discover -s tests -p 'test_*.py'", workflow)
        self.assertIn("if: always()", workflow)
        self.assertIn("actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02", workflow)
        self.assertNotIn("pip install --upgrade", workflow)
        self.assertIn("candidate-qualification-${{ github.sha }}", workflow)
        self.assertIn("QA/release/*.json", workflow)
        self.assertIn("QA/map_first/**/*.json", workflow)
        self.assertIn("QA/map_first/screenshots/**", workflow)

    def test_public_assembly_is_exact_sha_gated(self):
        public = (ROOT / "scripts/prepare_public_site.py").read_text()
        self.assertIn("qualification.get(\"status\") != \"PASS\"", public)
        self.assertIn("head != args.revision", public)
        self.assertIn(".release-provenance.json", public)
        self.assertIn("build manifest changed after qualification", public)
        source_generation = (ROOT / "scripts/apply_location_gap_audit.py").read_text()
        self.assertIn("Explicit source-generation step required", source_generation)

    def test_smart_map_asset_is_materialized_not_an_lfs_pointer(self):
        vector = ROOT / "assets/vector/sf_trip.pmtiles"
        self.assertGreater(vector.stat().st_size, 1_000_000)
        self.assertFalse(vector.read_bytes().startswith(b"version https://git-lfs.github.com/spec/v1"))


if __name__ == "__main__":
    unittest.main()
