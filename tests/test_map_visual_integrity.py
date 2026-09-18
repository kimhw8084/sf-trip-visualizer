import unittest
from pathlib import Path

import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from qa_map_visual_integrity import crop_map, image_from_path, integrity_result, make_corruption_fixture, measure  # noqa: E402


class MapVisualIntegrityTests(unittest.TestCase):
    def setUp(self):
        baseline = image_from_path(ROOT / "QA/gate5/screenshots/baseline/webkit_1440_overall.png")
        self.clean = crop_map(baseline, (0, 94, 1044, 806))

    def test_clean_gate4_webkit_baseline_passes(self):
        result = integrity_result(self.clean, self.clean)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["metric"]["components"], result["clean_reference_metric"]["components"])

    def test_known_r4_opaque_label_rectangle_class_fails(self):
        boxes = tuple((x, y, x + 24, y + 12) for x, y in ((120, 100), (260, 160), (410, 220), (560, 280), (710, 340), (180, 470), (420, 560), (760, 650)))
        affected = make_corruption_fixture(self.clean, boxes)
        result = integrity_result(affected, self.clean)
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("suspicious_rectangle_component_count", result["failures"])
        self.assertGreater(result["metric"]["total_area"], result["clean_reference_metric"]["total_area"])

    def test_same_host_control_detector_preserves_base_and_candidate_metrics(self):
        boxes = tuple((x, y, x + 24, y + 12) for x, y in ((120, 100), (260, 160), (410, 220), (560, 280), (710, 340), (180, 470), (420, 560), (760, 650)))
        affected = make_corruption_fixture(self.clean, boxes)
        result = integrity_result(affected, self.clean)
        self.assertEqual(result["clean_reference_metric"], measure(self.clean))
        self.assertEqual(result["metric"], measure(affected))


if __name__ == "__main__":
    unittest.main()
