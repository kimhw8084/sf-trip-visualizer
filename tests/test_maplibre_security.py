import unittest
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from qa_maplibre_security import static_contract_checks  # noqa: E402


class MapLibreSecurityTests(unittest.TestCase):
    def test_local_backport_artifact_and_regression_are_bound(self):
        result = static_contract_checks(ROOT)
        self.assertEqual(result["status"], "PASS", result)

    def test_maintained_renderer_keeps_fixed_attribution_only(self):
        source = (ROOT / "src/app_phase7.js").read_text()
        self.assertNotIn("customAttribution", source)
        self.assertIn("© OpenStreetMap contributors · Protomaps", source)
        self.assertIn("Tiles © Esri and contributors", source)


if __name__ == "__main__":
    unittest.main()
