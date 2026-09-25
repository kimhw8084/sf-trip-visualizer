"""Fail-closed route and compact Day contracts for CHG-232."""

import copy
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from day_presentation_contract import audit_day_surface  # noqa: E402
from route_graph_contract import validate_route_graph  # noqa: E402


class CHG232RegressionRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((ROOT / "data/phase7_app_data.json").read_text())
        self.geometry = json.loads((ROOT / "data/route_geometry_cache.json").read_text())

    def assert_route_failure(self, data, geometry, expected):
        report = validate_route_graph(data, geometry)
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(any(expected in failure for failure in report["failures"]), report["failures"])

    def test_current_semantic_graph_has_truthful_route_statuses(self):
        report = validate_route_graph(self.data, self.geometry)
        self.assertEqual(report["status"], "PASS", report["failures"])
        self.assertEqual(report["counts"]["semantic_public_route_legs"], 23)
        self.assertEqual(report["counts"]["conceptual_ferry_legs"], 1)

    def test_missing_required_geometry_fails_closed(self):
        data, geometry = copy.deepcopy(self.data), copy.deepcopy(self.geometry)
        geometry.pop(data["legs"][0]["leg_id"])
        self.assert_route_failure(data, geometry, "route geometry cache does not exactly cover semantic route legs")

    def test_two_point_public_road_fallback_fails(self):
        data, geometry = copy.deepcopy(self.data), copy.deepcopy(self.geometry)
        leg = next(item for item in data["legs"] if item["mode"] in {"drive", "walk"})
        geometry[leg["leg_id"]] = {
            "status": "conceptual_fallback",
            "coordinates": [[leg["from_latlon"][1], leg["from_latlon"][0]], [leg["to_latlon"][1], leg["to_latlon"][0]]],
            "mode": leg["mode"],
            "endpoint_signature": [leg["from_latlon"], leg["to_latlon"], leg["mode"]],
        }
        leg["geometry_kind"] = "conceptual_fallback"
        self.assert_route_failure(data, geometry, "two-point straight fallback")

    def test_edge_across_protected_lodging_nap_fails(self):
        data, geometry = copy.deepcopy(self.data), copy.deepcopy(self.geometry)
        source = next(item for item in data["legs"] if item["leg_id"] == "CHG232_104_01")
        target = next(item for item in data["legs"] if item["leg_id"] == "CHG232_104_02")
        leg = {
            **copy.deepcopy(source),
            "leg_id": "MUTANT_MUIR_TO_PALACE",
            "from": source["to"],
            "to": target["from"],
            "continuity_group": target["continuity_group"],
        }
        data["legs"].append(leg)
        geometry[leg["leg_id"]] = {
            "status": "intentionally_omitted",
            "coordinates": [],
            "mode": leg["mode"],
            "endpoint_signature": [leg["from_latlon"], leg["to_latlon"], leg["mode"]],
            "omission_reason": "mutation fixture",
        }
        leg["geometry_kind"] = "intentionally_omitted"
        leg["render_style"] = "omitted"
        self.assert_route_failure(data, geometry, "crosses a protected recovery/check-in break")

    def test_twin_peaks_cannot_be_joined_to_default_path(self):
        data, geometry = copy.deepcopy(self.data), copy.deepcopy(self.geometry)
        source = next(item for item in data["legs"] if item["leg_id"] == "CHG232_104_04")
        leg = {
            **copy.deepcopy(source),
            "leg_id": "MUTANT_GGB_TO_TWIN_PEAKS",
            "from": "ggb",
            "to": "twin_peaks",
            "branch_kind": "main",
        }
        data["legs"].append(leg)
        geometry[leg["leg_id"]] = {
            "status": "intentionally_omitted",
            "coordinates": [],
            "mode": leg["mode"],
            "endpoint_signature": [leg["from_latlon"], leg["to_latlon"], leg["mode"]],
            "omission_reason": "mutation fixture",
        }
        leg["geometry_kind"] = "intentionally_omitted"
        leg["render_style"] = "omitted"
        self.assert_route_failure(data, geometry, "sequential path from its default into the alternate")

    @staticmethod
    def day_snapshot():
        return {
            "travel_rows": [{
                "travel_id": "day-travel-1",
                "expanded": False,
                "region_hidden": True,
                "collapsed_text": "12:50 → 13:20 · Ferry Building → Mill Valley lodging · ~30–40 min",
                "button_id": "travel-toggle-1",
                "controls_id": "travel-region-1",
                "region_id": "travel-region-1",
                "labelled_by": "travel-toggle-1",
                "focus_preserved": True,
            }],
            "day_notes": {
                "expanded": False,
                "region_hidden": True,
                "button_id": "notes-toggle",
                "controls_id": "notes-region",
                "region_id": "notes-region",
                "labelled_by": "notes-toggle",
            },
        }

    def assert_day_failure(self, snapshot, expected):
        failures = audit_day_surface(snapshot)
        self.assertTrue(any(expected in failure for failure in failures), failures)

    def test_default_travel_details_must_be_collapsed(self):
        snapshot = self.day_snapshot()
        snapshot["travel_rows"][0].update(expanded=True, region_hidden=False)
        self.assert_day_failure(snapshot, "expanded by default")

    def test_provenance_must_stay_out_of_default_row(self):
        snapshot = self.day_snapshot()
        snapshot["travel_rows"][0]["collapsed_text"] += " · Provenance: schedule-derived"
        self.assert_day_failure(snapshot, "audit provenance appears")

    def test_travel_details_aria_and_focus_ownership_are_required(self):
        snapshot = self.day_snapshot()
        snapshot["travel_rows"][0]["controls_id"] = "unowned-region"
        snapshot["travel_rows"][0]["focus_preserved"] = False
        failures = audit_day_surface(snapshot)
        self.assertTrue(any("ARIA ownership is broken" in failure for failure in failures), failures)
        self.assertTrue(any("focus was lost" in failure for failure in failures), failures)


if __name__ == "__main__":
    unittest.main()
