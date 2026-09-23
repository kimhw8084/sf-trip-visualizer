import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from qa_place_list_membership import collect_rows_from_fixture, validate_membership_rows  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]


class PlaceListMembershipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.matrix = json.loads((ROOT / "data/route_role_matrix.json").read_text())["places"]

    def test_complete_fixture_matches_canonical_matrix(self):
        report = validate_membership_rows(collect_rows_from_fixture(self.matrix), self.matrix)
        self.assertEqual(report["status"], "PASS", report["failures"])
        self.assertEqual(report["places"], 39)

    def test_rendered_role_mutation_is_rejected(self):
        rows = copy.deepcopy(collect_rows_from_fixture(self.matrix))
        rows[0]["cells"][0]["role"] = "Skip"
        report = validate_membership_rows(rows, self.matrix)
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any("canonical role" in failure for failure in report["failures"]))

    def test_skip_has_non_color_symbol_and_text(self):
        rows = collect_rows_from_fixture(self.matrix)
        skip_cells = [cell for row in rows for cell in row["cells"] if cell["role"] == "Skip"]
        self.assertTrue(skip_cells)
        self.assertTrue(all(cell["symbol"] == "—" and cell["label"] for cell in skip_cells))


if __name__ == "__main__":
    unittest.main()
