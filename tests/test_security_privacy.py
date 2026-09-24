import json
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import security_privacy  # noqa: E402


class SecurityPrivacyContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads((ROOT / "manifests/security_privacy_contract.json").read_text())

    def test_clean_repository_security_gate_passes(self):
        report = security_privacy.run_gate(ROOT, security_privacy.git_revision(ROOT))
        self.assertEqual(report["status"], "PASS", report["failures"])
        self.assertTrue(report["exact_candidate_bound"])
        self.assertEqual(report["secret_scan"]["production_inputs"]["findings"], [])

    def test_synthetic_secret_fails_without_value_disclosure(self):
        secret = "ghp_1234567890abcdefghijklmnopqrstu"
        private_key = "-----BEGIN PRIVATE KEY-----"
        report = security_privacy.scan_text(f"token={secret}\n{private_key}\n", "fixture.txt")
        serialized = json.dumps(report)
        self.assertEqual(len(report), 2)
        self.assertNotIn(secret, serialized)
        self.assertNotIn(private_key, serialized)
        self.assertEqual({item["classification"] for item in report}, {"github_token", "private_key"})

    def test_embedded_runtime_json_keeps_address_context_field_scoped(self):
        compact = (
            '<script>window.TRIP_DATA={'
            '"coordinate_provenance":"141 Main Avenue from a public map source",'
            '"recovery_note":"Protected lodging rest follows"'
            '};</script>'
        )
        self.assertEqual(security_privacy.scan_text(compact, "candidate.html"), [])

    def test_embedded_runtime_json_still_detects_residential_address_leaks(self):
        sample_street = " ".join(("123", "Example", "Road"))
        private_data = f'<script>window.TRIP_DATA={{"lodging":{{"street_address":"{sample_street}"}}}};</script>'
        private_report = security_privacy.scan_text(private_data, "candidate.html")
        self.assertEqual([item["classification"] for item in private_report], ["possible_residential_street_address"])
        visible_address = f'<p>{sample_street}.</p><script>window.TRIP_DATA={{}};</script>'
        visible_report = security_privacy.scan_text(visible_address, "candidate.html")
        self.assertEqual([item["classification"] for item in visible_report], ["possible_residential_street_address"])

    def test_vendor_inventory_passes_and_drift_fails(self):
        report = security_privacy.check_vendor_inventory(ROOT, self.contract)
        self.assertEqual(report["status"], "PASS", report["failures"])
        original = security_privacy.sha256

        def drifted(path):
            if path.name == "maplibre-gl.js":
                return "0" * 64
            return original(path)

        with patch.object(security_privacy, "sha256", side_effect=drifted):
            drift = security_privacy.check_vendor_inventory(ROOT, self.contract)
        self.assertEqual(drift["status"], "FAIL")
        self.assertTrue(any("maplibre-gl.js" in failure for failure in drift["failures"]))

    def test_stock_vulnerable_maplibre_state_fails_closed(self):
        contract = json.loads(json.dumps(self.contract))
        entry = next(item for item in contract["dependency_inventory"] if item["id"] == "maplibre-gl-js")
        entry["version"] = "4.7.1"
        entry.pop("local_backport", None)
        failed = security_privacy.check_maplibre_dependency(ROOT, contract)
        self.assertEqual(failed["status"], "FAIL")
        self.assertTrue(any("neither exact upstream 6.4.1+ nor an explicit provenance-bound local backport" in item for item in failed["failures"]))

    def test_maplibre_backport_hash_and_fix_markers_are_mechanical(self):
        contract = json.loads(json.dumps(self.contract))
        entry = next(item for item in contract["dependency_inventory"] if item["id"] == "maplibre-gl-js")
        entry["artifact_hashes"]["vendor/maplibre-gl.js"] = "0" * 64
        failed = security_privacy.check_maplibre_dependency(ROOT, contract)
        self.assertEqual(failed["status"], "FAIL")
        self.assertTrue(any("JavaScript hash" in item for item in failed["failures"]))

    def test_required_dependency_is_hash_pinned(self):
        report = security_privacy.check_requirements(ROOT, self.contract)
        self.assertEqual(report["status"], "PASS", report["failures"])
        with tempfile.TemporaryDirectory(prefix="g7-requirements-") as directory:
            root = Path(directory)
            (root / "requirements-qa.txt").write_text("requests==2.32.4\n")
            failed = security_privacy.check_requirements(root, self.contract)
        self.assertEqual(failed["status"], "FAIL")
        self.assertTrue(any("lacks hash" in failure or "no artifact hash" in failure for failure in failed["failures"]))

    def test_platform_coverage_requires_linux_playwright_hash(self):
        requirements = (ROOT / "requirements-qa.txt").read_text()
        linux_hash = "ba33bae6a13b3d9d354c751cb618af357d20fe1d57767cbcce52079bbef17ad3"
        mac_only = requirements.replace(f"    --hash=sha256:{linux_hash}\n", "")
        with tempfile.TemporaryDirectory(prefix="g7-platform-missing-") as directory:
            root = Path(directory)
            (root / "requirements-qa.txt").write_text(mac_only)
            failed = security_privacy.check_requirements(root, self.contract)
        self.assertEqual(failed["artifact_coverage"]["status"], "FAIL")
        self.assertTrue(any("playwright" in failure and "linux-x86_64-cp311" in failure for failure in failed["artifact_coverage"]["failures"]))

    def test_repaired_artifact_matrix_covers_supported_platforms(self):
        with tempfile.TemporaryDirectory(prefix="g7-platform-repaired-") as directory:
            root = Path(directory)
            (root / "requirements-qa.txt").write_text((ROOT / "requirements-qa.txt").read_text())
            passed = security_privacy.check_requirements(root, self.contract)
        coverage = passed["artifact_coverage"]
        self.assertEqual(coverage["status"], "PASS", coverage["failures"])
        self.assertEqual({platform["id"] for platform in coverage["supported_platforms"]}, {"macos-arm64-cp311", "linux-x86_64-cp311"})

    def test_wrong_linux_artifact_hash_fails_coverage(self):
        requirements = (ROOT / "requirements-qa.txt").read_text()
        linux_hash = "ba33bae6a13b3d9d354c751cb618af357d20fe1d57767cbcce52079bbef17ad3"
        wrong_hash = "0" * 64
        wrong_linux = requirements.replace(linux_hash, wrong_hash)
        with tempfile.TemporaryDirectory(prefix="g7-platform-wrong-hash-") as directory:
            root = Path(directory)
            (root / "requirements-qa.txt").write_text(wrong_linux)
            failed = security_privacy.check_requirements(root, self.contract)
        self.assertEqual(failed["artifact_coverage"]["status"], "FAIL")
        self.assertTrue(any("unapproved artifact hash" in failure for failure in failed["artifact_coverage"]["failures"]))

    def test_unapproved_platform_artifact_hash_fails_closed(self):
        requirements = (ROOT / "requirements-qa.txt").read_text()
        linux_hash = "ba33bae6a13b3d9d354c751cb618af357d20fe1d57767cbcce52079bbef17ad3"
        unknown_hash = "1" * 64
        extra_hash = f"    --hash=sha256:{unknown_hash}\n"
        unapproved = requirements.replace(f"    --hash=sha256:{linux_hash}\n", f"    --hash=sha256:{linux_hash} \\\n{extra_hash}")
        with tempfile.TemporaryDirectory(prefix="g7-platform-unapproved-") as directory:
            root = Path(directory)
            (root / "requirements-qa.txt").write_text(unapproved)
            failed = security_privacy.check_requirements(root, self.contract)
        self.assertEqual(failed["artifact_coverage"]["status"], "FAIL")
        self.assertTrue(any(unknown_hash in failure and "unapproved artifact hash" in failure for failure in failed["artifact_coverage"]["failures"]))

    def test_unknown_platform_artifact_is_rejected(self):
        contract = json.loads(json.dumps(self.contract))
        inventory = next(entry for entry in contract["dependency_inventory"] if entry["id"] == "python-qa-closure")
        inventory["artifact_coverage"]["approved_artifacts"].append(
            {
                "package": "playwright",
                "version": "1.62.0",
                "filename": "playwright-1.62.0-py3-none-unknown_platform.whl",
                "sha256": "db755ab27db21a04186f1fe8169888e42356086e439b1059b923ef417f0b6034",
                "platforms": ["unknown-linux-x86_64-cp311"],
            }
        )
        with tempfile.TemporaryDirectory(prefix="g7-platform-unknown-") as directory:
            root = Path(directory)
            (root / "requirements-qa.txt").write_text((ROOT / "requirements-qa.txt").read_text())
            failed = security_privacy.check_requirements(root, contract)
        self.assertEqual(failed["artifact_coverage"]["status"], "FAIL")
        self.assertTrue(any("unknown platform unknown-linux-x86_64-cp311" in failure for failure in failed["artifact_coverage"]["failures"]))

    def test_advisory_validation_rejects_known_affected_transitive_pin(self):
        requirements = (ROOT / "requirements-qa.txt").read_text()
        old_state = requirements.replace("urllib3==2.8.0 \\", "urllib3==2.0.7 \\").replace(
            "sha256:0cf3cae568d36aa9576b28dfb35f11328f1cb974ca7647d9475ebb86c75ac6e3",
            "sha256:fdb6d215c776278489906c2f8916e6e7d4f5a9b602ccbcfdf7f016fc8da0596e",
        )
        with tempfile.TemporaryDirectory(prefix="g7-advisory-fixture-") as directory:
            root = Path(directory)
            (root / "requirements-qa.txt").write_text(old_state)
            failed = security_privacy.check_requirements(root, self.contract)
        self.assertEqual(failed["status"], "FAIL")
        self.assertEqual(failed["advisory_review"]["status"], "FAIL")
        self.assertTrue(any("urllib3==2.0.7" in failure and "GHSA-2xpw-w6gg-jr37" in failure for failure in failed["failures"]))
        self.assertTrue(any(row["status"] == "FIX_REQUIRED" for row in failed["advisory_review"]["constraints"]))

    def test_workflows_are_sha_pinned_and_least_privilege(self):
        report = security_privacy.check_workflows(ROOT, self.contract)
        self.assertEqual(report["status"], "PASS", report["failures"])
        with tempfile.TemporaryDirectory(prefix="g7-workflows-") as directory:
            root = Path(directory)
            (root / ".github/workflows").mkdir(parents=True)
            for name in ("candidate-qualification.yml", "deploy-pages.yml"):
                shutil.copy(ROOT / ".github/workflows" / name, root / ".github/workflows" / name)
            candidate = root / ".github/workflows/candidate-qualification.yml"
            candidate.write_text(candidate.read_text().replace("actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1", "actions/checkout@v7"))
            failed = security_privacy.check_workflows(root, self.contract)
        self.assertEqual(failed["status"], "FAIL")
        self.assertTrue(any("not pinned" in failure for failure in failed["failures"]))

    def test_origins_storage_and_static_controls_pass(self):
        self.assertEqual(security_privacy.check_origins(ROOT)["status"], "PASS")
        self.assertEqual(security_privacy.check_local_storage(ROOT, self.contract)["status"], "PASS")
        self.assertEqual(security_privacy.check_static_controls(ROOT)["status"], "PASS")

    def test_private_only_artifact_path_fails(self):
        with tempfile.TemporaryDirectory(prefix="g7-artifact-") as directory:
            root = Path(directory)
            private = root / "public" / "private" / "original.jpg"
            private.parent.mkdir(parents=True)
            private.write_bytes(b"fixture")
            report = security_privacy.check_artifact_paths([root / "public"], root)
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any(item["classification"] == "private_or_credential_artifact" for item in report["findings"]))

    def test_candidate_binding_rejects_wrong_revision(self):
        passed = security_privacy.check_candidate_binding(ROOT, security_privacy.git_revision(ROOT), self.contract)
        failed = security_privacy.check_candidate_binding(ROOT, "0" * 40, self.contract)
        self.assertEqual(passed["status"], "PASS")
        self.assertEqual(failed["status"], "FAIL")
        self.assertFalse(failed["exact_candidate_bound"])

    def test_browser_rendering_escapes_adversarial_data_and_bounds_navigation(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as error:  # pragma: no cover - CI installs the pinned QA closure
            self.skipTest(str(error))

        with tempfile.TemporaryDirectory(prefix="g7-browser-build-") as directory:
            output = Path(directory)
            build = subprocess.run(
                [sys.executable, str(ROOT / "scripts/build_map_first.py"), "--output-dir", str(output)],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            port = 18765
            server = subprocess.Popen(
                [sys.executable, str(ROOT / "scripts/serve_map.py"), "--port", str(port), "--directory", str(output / "modular")],
                cwd=ROOT,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:
                for _ in range(80):
                    try:
                        with urlopen(f"http://127.0.0.1:{port}/", timeout=0.5):
                            break
                    except Exception:
                        time.sleep(0.1)
                else:
                    self.fail("test server did not start")
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(headless=True)
                    page = browser.new_page()
                    page.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
                    page.wait_for_function("window.__tripSecurity && window.__tripApp && window.__tripApp.map()", timeout=30000)
                    page.evaluate("window.__g7Probe = 0")
                    payload = '<img src=x onerror="window.__g7Probe=1"><svg/onload=window.__g7Probe=2>\"\' javascript:alert(1) &lt;encoded&gt;'
                    result = page.evaluate("value => window.__tripSecurity.renderFixture(value)", payload)
                    self.assertEqual(result["unsafe_nodes"], 0)
                    self.assertIsNone(result["href"])
                    self.assertEqual(page.evaluate("window.__g7Probe"), 0)
                    self.assertEqual(page.locator("#detailsPane script, #detailsPane [onerror], #detailsPane [onload]").count(), 0)
                    self.assertTrue("&lt;img" in result["html"] or "&amp;lt;img" in result["html"])
                    keys = page.evaluate("Object.keys(localStorage)")
                    self.assertTrue(set(keys).issubset(set(page.evaluate("window.__tripSecurity.allowedStorageKeys"))))
                    self.assertEqual(page.evaluate("window.__tripSecurity.safeExternalUrl('javascript:alert(1)')"), "")
                    self.assertEqual(page.evaluate("window.__tripSecurity.safeExternalUrl('https://evil.example/maps/search/?api=1&query=SF')"), "")
                    browser.close()
            finally:
                server.terminate()
                server.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
