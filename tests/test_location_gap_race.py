import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class LocationGapRaceContractTests(unittest.TestCase):
    def test_marker_callbacks_are_keyed_and_bound_to_their_map(self):
        source = (ROOT / "src/app_phase7.js").read_text()
        self.assertIn("photoMarkers=new Map()", source)
        self.assertIn("photoMarkers.get(place.place_key)", source)
        self.assertIn("map!==photoMap", source)
        self.assertIn("__tripPhotoCleanup", source)
        self.assertNotIn("const m=visible[i]", source)

    def test_browser_regression_exercises_state_transitions_and_preservation(self):
        source = (ROOT / "scripts/qa_location_gap_race.py").read_text()
        for expected in ("routeSets", "dates", "regions", "map.jumpTo", "map.fire('moveend')", "map.fire('zoomend')", "checks[\"selected\"] == \"pier39\"", "detailsActive", "detailPhotos"):
            self.assertIn(expected, source)


if __name__ == "__main__":
    unittest.main()
