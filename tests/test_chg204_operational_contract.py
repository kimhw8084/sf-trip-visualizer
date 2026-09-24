import json
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import security_privacy  # noqa: E402
from travel_contract import validate_travel_contract  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]


def read_json(relative):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


class CHG204OperationalContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = read_json("data/phase7_app_data.json")
        cls.manifest = read_json("manifests/canonical_pipeline.json")
        cls.freshness = read_json("manifests/trip_freshness.json")

    def test_runtime_is_one_final_route_with_all_eleven_days(self):
        self.assertEqual(set(self.data["routes"]), {"A"})
        self.assertEqual(self.manifest["invariants"]["active_route_ids"], ["A"])
        self.assertEqual(len(self.data["dates"]), 11)
        self.assertEqual(set(self.data["operating_days"]), {item["key"] for item in self.data["dates"]})
        self.assertEqual(set(self.data["operating_days"]), {item["date_key"] for item in self.data["timeline"]})
        removed = {"bay_lights", "exploratorium", "musee", "academy", "coit", "bixby", "mariposa"}
        self.assertFalse(removed & {item["place_key"] for item in self.data["markers"]})
        twins = [row for marker in self.data["markers"] if marker["place_key"] == "twin_peaks" for row in marker["occurrences"]]
        self.assertEqual(len(twins), 1)
        self.assertEqual(twins[0]["date_key"], "10/4")
        self.assertTrue(twins[0].get("condition"))
        cards = [item for item in self.data["timeline"] if item["date_key"] == "10/4"]
        twin_card = next(index for index, item in enumerate(cards) if item.get("swap_for") == "palace")
        palace_card = next(index for index, item in enumerate(cards) if "palace" in item.get("spatial_keys", []))
        crissy_card = next(index for index, item in enumerate(cards) if "crissy" in item.get("spatial_keys", []))
        self.assertEqual((palace_card + 1, crissy_card - 1), (twin_card, twin_card))
        oct11 = next(item for item in self.data["timeline"] if item["id"] == "chg204_1011_baker")
        self.assertIn("fog or wind", oct11["reason_en"].lower())
        self.assertIn("fallback", oct11["reason_en"].lower())
        self.assertIn("19:30", self.data["operating_days"]["10/11"]["invalidator_en"])

    def test_recovery_and_navigation_are_explicit(self):
        days = self.data["operating_days"]
        self.assertIn("13:30–15:30", days["10/3"]["nap_en"])
        self.assertIn("13:00–15:00", days["10/8"]["nap_en"])
        self.assertIn("13:00–15:00", days["10/10"]["nap_en"])
        self.assertIn("13:30–15:00", days["10/9"]["nap_en"])
        self.assertIn("recovery only", days["10/9"]["recovery_en"].lower())
        self.assertTrue(any("19:30" in str(value) for value in days["10/11"].values()))
        material_departures = [item for item in self.data["timeline"] if item.get("travel_navigation_cue")]
        self.assertGreaterEqual(len(material_departures), 8)
        for day in days.values():
            self.assertTrue(day["recovery_en"] and day["recovery_ko"])

    def test_travel_range_coverage_is_complete_and_fails_a_missing_binding(self):
        report = validate_travel_contract(self.data)
        self.assertEqual(report["status"], "PASS", report["failures"])
        self.assertEqual(report["counts"]["material_timeline_movements"], report["counts"]["linked_timeline_movements"])
        self.assertEqual(report["counts"]["material_route_connectors"], report["counts"]["linked_route_connectors"])
        ranges = {item["id"]: item for item in self.data["travel_ranges"]}
        self.assertEqual(len(ranges), len(self.data["travel_ranges"]))
        self.assertTrue(all(item["baseline_reference"]["status"] == "UNAVAILABLE_NO_INDEPENDENT_SOURCE" for item in ranges.values()))
        self.assertTrue(all(item["baseline_reference"]["minutes_min"] is None and item["baseline_reference"]["minutes_max"] is None for item in ranges.values()))
        self.assertTrue(all("static planning" in item["basis"].lower() for item in ranges.values()))
        self.assertTrue(all("Check live navigation before leaving" in item["live_navigation_cue"] for item in ranges.values()))
        self.assertFalse(any("NOT_RESEARCHED" in json.dumps(item) for item in ranges.values()))

        fixture = json.loads(json.dumps(self.data))
        required_row = next(item for item in fixture["timeline"] if item["id"] == "chg204_104_ggb_lodging")
        required_row.pop("travel_range_id")
        mutated = validate_travel_contract(fixture)
        self.assertEqual(mutated["status"], "FAIL")
        self.assertTrue(any("chg204_104_ggb_lodging has no travel_range_id" in failure for failure in mutated["failures"]))

        conflated = json.loads(json.dumps(self.data))
        conflated["travel_ranges"][0]["baseline_reference"]["departure"] = "08:00"
        self.assertEqual(validate_travel_contract(conflated)["status"], "FAIL")

        address_fixture = json.loads(json.dumps(self.data))
        address_fixture["travel_ranges"][0]["to_identity"] = " ".join(("123", "Example", "Street"))
        address_report = validate_travel_contract(address_fixture)
        self.assertEqual(address_report["status"], "FAIL")
        self.assertTrue(any("street-address-shaped endpoint" in failure for failure in address_report["failures"]))

        coordinate_fixture = json.loads(json.dumps(self.data))
        coordinate_fixture["travel_ranges"][0]["private_endpoint_metadata"] = {"coordinates": ["redacted-test-value"]}
        coordinate_report = validate_travel_contract(coordinate_fixture)
        self.assertEqual(coordinate_report["status"], "FAIL")
        self.assertTrue(any("contains a coordinate" in failure for failure in coordinate_report["failures"]))

    def test_october_6_place_rows_and_october_4_return_are_explicit(self):
        oct6 = [item for item in self.data["timeline"] if item["date_key"] == "10/6"]
        ids = [item["id"] for item in oct6]
        sequence = [
            "chg204_106_aquarium",
            "chg204_106_aquarium_stagecoach",
            "chg204_106_checkin_reset",
            "chg204_106_stagecoach_wharf",
            "chg204_106_wharf",
            "chg204_106_wharf_stagecoach",
        ]
        self.assertEqual([ids.index(item) for item in sequence], sorted(ids.index(item) for item in sequence))
        by_id = {item["id"]: item for item in oct6}
        self.assertEqual(by_id["chg204_106_checkin_reset"]["kind"], "logistics")
        self.assertNotIn("Old Fisherman", by_id["chg204_106_checkin_reset"]["title_en"])
        self.assertEqual(by_id["chg204_106_wharf"]["kind"], "place")
        self.assertEqual(by_id["chg204_106_wharf"]["title_en"], "Old Fisherman's Wharf")
        self.assertEqual(by_id["chg204_106_wharf_stagecoach"]["travel_range_id"], "travel_106_wharf_stagecoach")

        oct4_return = next(item for item in self.data["timeline"] if item["id"] == "chg204_104_ggb_lodging")
        self.assertEqual(oct4_return["kind"], "travel")
        self.assertEqual(oct4_return["title_en"], "Golden Gate Bridge south-side overlook → Mill Valley lodging")
        self.assertTrue(oct4_return["travel_range_id"])

    def test_daily_return_semantics_have_timeline_movement_bindings(self):
        timeline = {item["id"]: item for item in self.data["timeline"]}
        for date_key, operation in self.data["operating_days"].items():
            contract = operation["travel_contract"]
            self.assertIn(contract["start_movement_id"], timeline, date_key)
            for movement_id in contract["nap_return_movement_ids"]:
                self.assertEqual(timeline[movement_id]["travel_role"], "protected_nap_return", date_key)
            end_id = contract["end_movement_id"]
            recovery = operation["recovery_en"].lower()
            return_is_stated = any(term in recovery for term in ("back by", "lodging by", "lodging ~", "return", "back ~"))
            if return_is_stated:
                self.assertTrue(end_id, date_key)
            if end_id:
                self.assertEqual(timeline[end_id]["kind"], "travel", date_key)
                self.assertTrue(timeline[end_id].get("travel_range_id"), date_key)

    def test_cost_scenarios_reproduce_lower_bounds_without_duplicate_lines(self):
        model = self.data["cost_cockpit"]
        expected = {
            "us_resident_annual_pass": 65280,
            "us_resident_a_la_carte": 66780,
            "nonresident_annual_pass": 82280,
            "nonresident_a_la_carte": 106780,
        }
        scenarios = {item["id"]: item for item in model["scenarios"]}
        self.assertEqual(set(scenarios), set(expected))
        for scenario_id, amount in expected.items():
            scenario = scenarios[scenario_id]
            line_ids = [line["id"] for line in scenario["lines"]]
            self.assertEqual(len(line_ids), len(set(line_ids)), scenario_id)
            self.assertEqual(sum(line["amount_cents"] for line in scenario["lines"]), amount, scenario_id)
            self.assertEqual(scenario["lower_bound_cents"], amount, scenario_id)
            self.assertEqual(sum(line["id"] == "ggb_tolls" for line in scenario["lines"]), 1)
            self.assertEqual(sum(line["id"] == "alcatraz" for line in scenario["lines"]), 1)
        self.assertEqual(set(model["analysis_scenario"]["excluded"]), {"food", "gas", "lodging", "base rental rate"})
        self.assertIn("Never inferred", model["analysis_scenario"]["residency"])

    def test_starting_and_variable_fees_stay_unfrozen(self):
        model = self.data["cost_cockpit"]
        starts = [line for scenario in model["scenarios"] for line in scenario["lines"] if line["fee_semantic"] == "starting"]
        variables = model["variable_checkout_required"] + model["optional_convenience"]
        self.assertTrue(starts)
        self.assertTrue(all(line["category"] == "starting" for line in starts))
        self.assertTrue(variables)
        self.assertTrue(all(item["fee_semantic"] in {"starting", "variable", "estimated", "conditional"} for item in variables))
        self.assertTrue(any(item["fee_semantic"] == "starting" for item in variables))
        self.assertTrue(any(item["fee_semantic"] == "variable" for item in variables))
        for item in self.data["readiness_items"]:
            if item["fee_semantic"] in {"variable", "estimated"}:
                self.assertIsNone(item.get("fee_amount_cents"), item["id"])

    def test_readiness_records_are_source_linked_bilingual_and_actionable(self):
        allowed_severity = {"required", "strongly_recommended", "optional", "recheck_only"}
        allowed_fee = {"fixed", "starting", "estimated", "variable", "conditional", "included", "free"}
        freshness_ids = {record["fact_id"] for record in self.freshness["records"]}
        self.assertGreaterEqual(len(freshness_ids), 15)
        for item in self.data["readiness_items"]:
            with self.subTest(item=item["id"]):
                self.assertTrue(item["source"])
                self.assertTrue(all(url.startswith("https://") for url in item["source"]))
                self.assertEqual(item["researched_on"], "2026-09-24")
                self.assertTrue(item["confidence"])
                self.assertTrue(item["recheck_timing"])
                self.assertIn(item["prerequisite_severity"], allowed_severity)
                self.assertIn(item["fee_semantic"], allowed_fee)
                self.assertTrue(item["parking_guidance_en"] and item["parking_guidance_ko"])
                self.assertTrue(item["baby_mobility_en"] and item["baby_mobility_ko"])
                self.assertTrue(item.get("place_key") or item.get("leg_id") or item.get("logistics_key"))
                self.assertEqual(item["status_scope"], "local_user_only")
                self.assertTrue(set(item["freshness_fact_ids"]) <= freshness_ids)
        for record in self.freshness["records"]:
            self.assertEqual(record["observed_on"], "2026-09-24")
            self.assertEqual(record["status"], "RECHECK_REQUIRED")
            self.assertTrue(record["source"]["primary_or_official"])
            linked_ids = {item["id"] for item in self.data["readiness_items"] if record["fact_id"] in item["freshness_fact_ids"]}
            self.assertTrue(linked_ids)
            self.assertTrue({f"readiness_items.{item_id}" for item_id in linked_ids} <= set(record["product_claim_refs"]))

    def test_user_readiness_state_is_identity_scoped_and_local(self):
        script = r"""
          const fs=require('fs'),vm=require('vm'),assert=require('assert');
          const values=new Map();
          const sandbox={localStorage:{getItem:k=>values.get(k)||null,setItem:(k,v)=>values.set(k,v)},window:null};
          sandbox.window=sandbox;
          vm.runInNewContext(fs.readFileSync('src/atlas_state.js','utf8'),sandbox);
          const data={trip_identity:'trip-one',routes:{A:{recommended:true}},dates:[{key:'10/5'}],region_cfg:{overall:{}},providers:{vector:{identity:'smart-local-vector'}},cost_cockpit:{scenarios:[{id:'annual'}]}};
          const first=sandbox.TRIP_ATLAS_STATE.create(data);
          first.state.user.readiness.alcatraz='user_marked_booked';first.state.user.costScenario='annual';first.persist();
          const restored=sandbox.TRIP_ATLAS_STATE.create(data);
          assert.equal(restored.state.user.readiness.alcatraz,'user_marked_booked');
          assert.equal(restored.state.user.costScenario,'annual');
          const other=sandbox.TRIP_ATLAS_STATE.create({...data,trip_identity:'trip-two'});
          assert.deepEqual({...other.state.user.readiness},{});
          assert.equal(other.state.user.costScenario,null);
        """
        result = subprocess.run(["node", "-e", script], cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_address_scan_redacts_matches_and_allows_the_public_rental_center(self):
        terms = ("123", "Example", "Lane")
        report = security_privacy.scan_text("lodging " + " ".join(terms), "fixture.txt")
        self.assertEqual([item["classification"] for item in report], ["possible_residential_street_address"])
        self.assertNotIn(" ".join(terms), json.dumps(report))
        public = "SFO Hertz Rental Car Center, " + " ".join(("780", "N.", "McDonnell", "Rd."))
        self.assertEqual(security_privacy.scan_text(public, "fixture.txt"), [])
        self.assertEqual(security_privacy.check_active_trip_location_privacy(ROOT)["status"], "PASS")
        fixture = json.loads(json.dumps(self.data))
        fixture["trip"]["lodging_coordinates"] = "<redacted-test-field>"
        fixture["legs"][0]["from"] = "family residence"
        privacy = security_privacy.active_trip_location_privacy_report(fixture)
        self.assertEqual(privacy["status"], "FAIL")
        self.assertEqual(len(privacy["failures"]), 2)


if __name__ == "__main__":
    unittest.main()
