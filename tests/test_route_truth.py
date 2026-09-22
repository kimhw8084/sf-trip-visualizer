import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from validate_route_truth import validate_route_truth  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]


def load(relative: str):
    return json.loads((ROOT / relative).read_text())


class RouteTruthTests(unittest.TestCase):
    def setUp(self):
        self.data = load("data/phase7_app_data.json")
        self.roles = load("data/route_role_matrix.json")
        self.schedule = load("data/route_schedules.json")

    def test_canonical_route_and_calendar_truth_passes(self):
        report = validate_route_truth(self.data, self.roles, self.schedule)
        self.assertEqual(report["status"], "PASS", report["failures"])
        self.assertEqual(report["counts"]["matrix_places"], 39)
        self.assertEqual(report["counts"]["routes"], 5)
        self.assertEqual(report["counts"]["dates"], 9)
        self.assertEqual(report["counts"]["occurrences"], 176)

    def test_production_drop_first_is_exhaustively_valid_across_45_route_days(self):
        report = validate_route_truth(self.data, self.roles, self.schedule)
        self.assertEqual(report["status"], "PASS", report["failures"])
        self.assertEqual(report["counts"]["drop_first_days"], 45)
        self.assertEqual(report["counts"]["drop_first_references"], 78)

    def test_wrong_role_bucket_is_rejected(self):
        mutated = copy.deepcopy(self.schedule)
        mutated["routes"]["A"]["days"]["10/3"]["strong"].remove("bay_lights")
        mutated["routes"]["A"]["days"]["10/3"]["conditional"].append("bay_lights")
        report = validate_route_truth(self.data, self.roles, mutated)
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any("bay_lights is Conditional" in failure for failure in report["failures"]))

    def test_skip_schedule_and_post_departure_monterey_are_rejected(self):
        mutated = copy.deepcopy(self.schedule)
        mutated["routes"]["A"]["days"]["10/6"]["conditional"].append("bixby")
        mutated["routes"]["E"]["days"]["10/11"]["conditional"].append("monterey_wharf")
        report = validate_route_truth(self.data, self.roles, mutated)
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any("schedules Skip place bixby" in failure for failure in report["failures"]))
        self.assertTrue(any("Monterey stop monterey_wharf" in failure for failure in report["failures"]))

    def test_drop_first_unscheduled_place_is_rejected(self):
        mutated = copy.deepcopy(self.schedule)
        mutated["routes"]["A"]["days"]["10/3"]["drop_first"].append("lone_cypress")
        report = validate_route_truth(self.data, self.roles, mutated)
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any("A 10/3 drop_first lone_cypress is not scheduled" in failure for failure in report["failures"]))

    def test_drop_first_skip_place_is_rejected(self):
        mutated = copy.deepcopy(self.schedule)
        mutated["routes"]["A"]["days"]["10/6"]["drop_first"].append("bixby")
        report = validate_route_truth(self.data, self.roles, mutated)
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any("A 10/6 drop_first bixby references a canonical Skip place" in failure for failure in report["failures"]))

    def test_drop_first_core_place_is_rejected(self):
        mutated = copy.deepcopy(self.schedule)
        mutated["routes"]["A"]["days"]["10/3"]["drop_first"].append("ferry")
        report = validate_route_truth(self.data, self.roles, mutated)
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any("A 10/3 drop_first ferry references a canonical Core place" in failure for failure in report["failures"]))

    def test_drop_first_duplicate_is_rejected(self):
        mutated = copy.deepcopy(self.schedule)
        mutated["routes"]["A"]["days"]["10/3"]["drop_first"].append("bay_lights")
        report = validate_route_truth(self.data, self.roles, mutated)
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any("A 10/3 drop_first bay_lights is duplicated" in failure for failure in report["failures"]))

    def test_stale_weekday_label_is_rejected(self):
        mutated = copy.deepcopy(self.data)
        occurrence = mutated["markers"][0]["occurrences"][0]
        occurrence["date"] = "10/3 화"
        report = validate_route_truth(mutated, self.roles, self.schedule)
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any("stale Korean weekday/date label" in failure for failure in report["failures"]))

    def test_transition_days_are_allowed_without_region_simplification(self):
        report = validate_route_truth(self.data, self.roles, self.schedule)
        self.assertEqual(report["status"], "PASS")
        self.assertIn("yosemite", report["daily_regions"]["A"]["10/9"])
        self.assertIn("sf", report["daily_regions"]["A"]["10/9"])
        self.assertEqual(report["lodging"]["yosemite"], ["10/7–10/9"])


if __name__ == "__main__":
    unittest.main()
