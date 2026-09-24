import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import qa_route_key_camera  # noqa: E402


EXPECTED_TASK = {"routes": ["A"], "primary_route": "A", "date": "10/8", "region": "yosemite", "selected": None}
EXPECTED_COUNTS = {"visible_markers": 3, "route_features": 2}


def good_context(style_loaded=True):
    return {
        "map_present": True,
        "provider": "vector",
        "app_ready": True,
        "map_visual_ready": True,
        "canvas_count": 1,
        "style_loaded": style_loaded,
        "map_moving": False,
        "visible_markers": 3,
        "route_features": 2,
        "spatial": {
            "useful": True,
            "visible_markers": 3,
            "markers_in_viewport": 3,
            "route_features": 2,
            "route_features_in_viewport": 2,
            "route_points_in_viewport": 18,
        },
        "map_obstacles": 1,
    }


class FakePage:
    def __init__(self, context=None, *, recover=True, task=None, comparison_chrome_count=0):
        self.context = context or good_context()
        self.recover = recover
        self.task = dict(task or EXPECTED_TASK)
        self.comparison_chrome_count = comparison_chrome_count
        self.wait_calls = []

    def evaluate(self, script):
        if "const s=window.__tripApp.state.task" in script:
            return self.task
        if "const a=window.__tripApp" in script:
            return copy.deepcopy(self.context)
        raise AssertionError(f"unexpected evaluate script: {script}")

    def locator(self, _selector):
        return self

    def count(self):
        return self.comparison_chrome_count

    def wait_for_function(self, expression, *, timeout):
        self.wait_calls.append((expression, timeout))
        if self.recover:
            self.context["style_loaded"] = True
            self.context["map_moving"] = False
            return
        raise TimeoutError("bounded readiness window expired")


class RouteKeyCameraOracleTests(unittest.TestCase):
    def test_transient_false_style_recovers_within_bounded_window(self):
        page = FakePage(good_context(style_loaded=False))
        result = qa_route_key_camera.acceptance_snapshot(page, EXPECTED_TASK, EXPECTED_COUNTS)
        self.assertTrue(result["valid"], result["failures"])
        self.assertTrue(result["style_readiness"]["transient_recovery"])
        self.assertFalse(result["style_readiness"]["initial_style_loaded"])
        self.assertEqual(page.wait_calls[0][1], qa_route_key_camera.STYLE_READY_TIMEOUT_MS)
        self.assertIn("!m.isMoving()", page.wait_calls[0][0])

    def test_permanently_never_ready_map_fails_closed(self):
        page = FakePage(good_context(style_loaded=False), recover=False)
        result = qa_route_key_camera.acceptance_snapshot(page, EXPECTED_TASK, EXPECTED_COUNTS)
        self.assertFalse(result["valid"])
        self.assertFalse(result["style_loaded"])
        self.assertTrue(any("did not become ready" in failure for failure in result["failures"]))
        self.assertTrue(any("timed out" in failure for failure in result["failures"]))

    def test_missing_expected_markers_or_route_features_fail(self):
        for field, spatial_field in (("visible_markers", "markers_in_viewport"), ("route_features", "route_features_in_viewport")):
            with self.subTest(field=field):
                context = good_context(style_loaded=False)
                context[field] -= 1
                context["spatial"][field] -= 1
                context["spatial"][spatial_field] -= 1
                page = FakePage(context)
                result = qa_route_key_camera.acceptance_snapshot(page, EXPECTED_TASK, EXPECTED_COUNTS)
                self.assertFalse(result["valid"])
                self.assertTrue(any("count changed" in failure for failure in result["failures"]))
                self.assertEqual(page.wait_calls, [])

    def test_route_date_or_region_task_mutation_fails(self):
        mutated_task = {**EXPECTED_TASK, "date": "10/9"}
        page = FakePage(task=mutated_task)
        result = qa_route_key_camera.acceptance_snapshot(page, EXPECTED_TASK, EXPECTED_COUNTS)
        self.assertFalse(result["valid"])
        self.assertIn("route/date/region task state changed", result["initial_failures"])
        self.assertEqual(page.wait_calls, [])

    def test_route_comparison_chrome_leak_fails(self):
        page = FakePage(comparison_chrome_count=1)
        result = qa_route_key_camera.acceptance_snapshot(page, EXPECTED_TASK, EXPECTED_COUNTS)
        self.assertFalse(result["valid"])
        self.assertIn("route-comparison chrome leaked", result["initial_failures"])


if __name__ == "__main__":
    unittest.main()
