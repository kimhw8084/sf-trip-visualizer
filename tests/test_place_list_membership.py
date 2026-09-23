import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from qa_place_list_membership import collect_rows_from_fixture, validate_place_rows  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]


class ActivePlaceRoleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        document = json.loads((ROOT / "data/route_role_matrix.json").read_text())
        cls.roles = document["places"]
        cls.route_ids = document["route_ids"]

    def test_complete_fixture_matches_single_route_roles(self):
        report = validate_place_rows(collect_rows_from_fixture(self.roles, self.route_ids), self.roles, self.route_ids, len(self.roles))
        self.assertEqual(report["status"], "PASS", report["failures"])
        self.assertEqual(report["places"], 36)
        self.assertEqual(self.route_ids, ["A"])

    def test_rendered_role_mutation_is_rejected(self):
        rows = copy.deepcopy(collect_rows_from_fixture(self.roles, self.route_ids))
        rows[0]["role"] = "Skip" if rows[0]["role"] != "Skip" else "Core"
        report = validate_place_rows(rows, self.roles, self.route_ids, len(self.roles))
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any("canonical role" in failure for failure in report["failures"]))

    def test_route_membership_cells_are_rejected(self):
        rows = collect_rows_from_fixture(self.roles, self.route_ids)
        rows[0]["route_cells"] = [{"route": "B", "role": "Core"}]
        report = validate_place_rows(rows, self.roles, self.route_ids, len(self.roles))
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any("comparison membership cells" in failure for failure in report["failures"]))

    def test_skip_is_visible_text_not_color_only(self):
        rows = collect_rows_from_fixture(self.roles, self.route_ids)
        skips = [row for row in rows if row["role"] == "Skip"]
        self.assertEqual({row["place_key"] for row in skips}, {"bixby", "coit"})
        self.assertTrue(all(row["label"] == "Skip" for row in skips))


if __name__ == "__main__":
    unittest.main()
