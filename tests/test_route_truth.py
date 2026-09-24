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
        self.assertEqual(report["counts"]["routes"], 1)
        self.assertEqual(report["counts"]["dates"], 11)
        self.assertEqual(report["counts"]["occurrences"], 44)

    def test_production_drop_first_is_exhaustively_valid_across_all_eleven_trip_days(self):
        report = validate_route_truth(self.data, self.roles, self.schedule)
        self.assertEqual(report["status"], "PASS", report["failures"])
        self.assertEqual(report["counts"]["drop_first_days"], 11)
        self.assertEqual(report["counts"]["drop_first_references"], 12)

    def test_owner_must_upgrades_are_required_in_canonical_schedule(self):
        mutated = copy.deepcopy(self.schedule)
        mutated["routes"]["A"]["days"]["10/5"]["hard_anchors"].remove("pier39")
        report = validate_route_truth(self.data, self.roles, mutated)
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any("pier39 must remain scheduled as a hard anchor on 10/5" in failure for failure in report["failures"]))

    def test_yosemite_morning_to_san_francisco_recovery_is_required(self):
        mutated = copy.deepcopy(self.schedule)
        mutated["routes"]["A"]["days"]["10/9"]["recovery"] = ["Add an SF photo stop before hotel check-in."]
        report = validate_route_truth(self.data, self.roles, mutated)
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any("10/9 transfer must end in Foster City recovery only" in failure for failure in report["failures"]))

    def test_yosemite_to_san_francisco_transfer_must_follow_the_final_morning(self):
        mutated = copy.deepcopy(self.data)
        transfer = next(leg for leg in mutated["legs"] if leg["date"] == "10/9" and leg["from"] == "yosemite_valley")
        transfer["date"] = "10/10"
        report = validate_route_truth(mutated, self.roles, self.schedule)
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any("conceptual Yosemite → SF transfer after the 10/9 morning" in failure for failure in report["failures"]))

    def test_wrong_role_bucket_is_rejected(self):
        mutated = copy.deepcopy(self.schedule)
        mutated["routes"]["A"]["days"]["10/4"]["strong"].remove("palace")
        mutated["routes"]["A"]["days"]["10/4"]["conditional"].append("palace")
        report = validate_route_truth(self.data, self.roles, mutated)
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any("palace is Conditional, canonical role is Strong" in failure for failure in report["failures"]))

    def test_unknown_retired_place_and_post_departure_monterey_are_rejected(self):
        mutated = copy.deepcopy(self.schedule)
        mutated["routes"]["A"]["days"]["10/6"]["conditional"].append("removed_place")
        mutated["routes"]["A"]["days"]["10/11"]["conditional"].append("monterey_wharf")
        report = validate_route_truth(self.data, self.roles, mutated)
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any("references unknown place removed_place" in failure for failure in report["failures"]))
        self.assertTrue(any("Monterey stop monterey_wharf" in failure for failure in report["failures"]))

    def test_drop_first_unscheduled_place_is_rejected(self):
        mutated = copy.deepcopy(self.schedule)
        mutated["routes"]["A"]["days"]["10/3"]["drop_first"].append("lone_cypress")
        report = validate_route_truth(self.data, self.roles, mutated)
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any("A 10/3 drop_first lone_cypress is not scheduled" in failure for failure in report["failures"]))

    def test_drop_first_unknown_place_is_rejected(self):
        mutated = copy.deepcopy(self.schedule)
        mutated["routes"]["A"]["days"]["10/6"]["drop_first"].append("removed_place")
        report = validate_route_truth(self.data, self.roles, mutated)
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any("A 10/6 drop_first removed_place references a place outside the canonical place matrix" in failure for failure in report["failures"]))

    def test_drop_first_core_place_is_rejected(self):
        mutated = copy.deepcopy(self.schedule)
        mutated["routes"]["A"]["days"]["10/3"]["drop_first"].append("ferry")
        report = validate_route_truth(self.data, self.roles, mutated)
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any("A 10/3 drop_first ferry references a canonical Core place" in failure for failure in report["failures"]))

    def test_drop_first_duplicate_is_rejected(self):
        mutated = copy.deepcopy(self.schedule)
        mutated["routes"]["A"]["days"]["10/4"]["drop_first"].append("palace")
        report = validate_route_truth(self.data, self.roles, mutated)
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any("A 10/4 drop_first palace is duplicated" in failure for failure in report["failures"]))

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

    def test_stale_route_id_outside_canonical_set_is_rejected(self):
        mutated = copy.deepcopy(self.schedule)
        mutated["routes"]["B"] = copy.deepcopy(mutated["routes"]["A"])
        report = validate_route_truth(self.data, self.roles, mutated)
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any("schedule route IDs must exactly match" in failure for failure in report["failures"]))


if __name__ == "__main__":
    unittest.main()
