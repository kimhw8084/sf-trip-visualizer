import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import qa_route_key_camera as camera  # noqa: E402


TASK = {"routes": ["A"], "primary_route": "A", "date": "10/8", "region": "yosemite", "selected": None}


def sample(
    *,
    style_loaded=True,
    map_moving=False,
    task=None,
    markers=3,
    route_features=2,
    markers_in_viewport=3,
    route_features_in_viewport=2,
    useful=True,
    comparison_chrome=0,
    panel_visible=False,
    focus_id="",
):
    return {
        "task_state": TASK.copy() if task is None else task,
        "context": {
            "canvas_count": 1,
            "style_loaded": style_loaded,
            "map_moving": map_moving,
            "visible_markers": markers,
            "route_features": route_features,
            "spatial": {
                "useful": useful,
                "width": 414,
                "height": 473,
                "markers_in_viewport": markers_in_viewport,
                "route_features_in_viewport": route_features_in_viewport,
                "route_points_in_viewport": 82,
            },
        },
        "comparison_chrome_count": comparison_chrome,
        "panel_visible": panel_visible,
        "focus_id": focus_id,
    }


class RouteKeyCameraReadinessTests(unittest.TestCase):
    def test_transient_not_ready_sample_recovers_with_expected_state_intact(self):
        recovered = sample(style_loaded=True)
        result = camera.assess_sample(sample(style_loaded=False), TASK, lambda: recovered)
        self.assertTrue(result["passed"])
        self.assertTrue(result["readiness_waited"])
        self.assertTrue(result["transient_recovery"])
        self.assertEqual(result["recovered_sample"], recovered)

    def test_persistent_never_ready_map_fails_closed_at_bound(self):
        def never_ready():
            raise TimeoutError("test readiness bound elapsed")

        result = camera.assess_sample(sample(style_loaded=False), TASK, never_ready)
        self.assertFalse(result["passed"])
        self.assertTrue(result["readiness_waited"])
        self.assertFalse(result["transient_recovery"])
        self.assertIn("did not return within 5000 ms", result["failures"][0])

    def test_missing_markers_or_routes_fail_before_waiting(self):
        for missing in (sample(markers=0, markers_in_viewport=0), sample(route_features=0, route_features_in_viewport=0)):
            with self.subTest(context=missing["context"]):
                result = camera.assess_sample(missing, TASK, self.fail)
                self.assertFalse(result["passed"])
                self.assertFalse(result["readiness_waited"])

    def test_changed_route_date_or_region_fails_before_waiting(self):
        changed_states = (
            {**TASK, "routes": ["A", "B"]},
            {**TASK, "date": "10/7"},
            {**TASK, "region": "sf"},
        )
        for changed in changed_states:
            with self.subTest(task=changed):
                result = camera.assess_sample(sample(task=changed), TASK, self.fail)
                self.assertFalse(result["passed"])
                self.assertIn("route/date/region task state changed", result["failures"])

    def test_comparison_chrome_leak_fails_closed(self):
        result = camera.assess_sample(sample(comparison_chrome=1), TASK, self.fail)
        self.assertFalse(result["passed"])
        self.assertIn("comparison chrome leaked into the single-route surface", result["failures"])

    def test_panel_close_and_focus_return_are_required(self):
        opened = camera.assess_sample(sample(panel_visible=True), TASK, self.fail, panel_visible=True)
        closed = camera.assess_sample(
            sample(focus_id="mapOptionsToggle"),
            TASK,
            self.fail,
            panel_visible=False,
            expected_focus_id="mapOptionsToggle",
        )
        bad_close = camera.assess_sample(
            sample(panel_visible=True, focus_id="otherControl"),
            TASK,
            self.fail,
            panel_visible=False,
            expected_focus_id="mapOptionsToggle",
        )
        self.assertTrue(opened["passed"])
        self.assertTrue(closed["passed"])
        self.assertFalse(bad_close["passed"])
        self.assertIn("map-options panel visibility changed", bad_close["failures"])
        self.assertIn("focus did not return to the map-options control", bad_close["failures"])


if __name__ == "__main__":
    unittest.main()
