import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from validate_trip_data import active_route_contract_failures  # noqa: E402


class ActiveRouteContractTests(unittest.TestCase):
    def test_one_route_is_valid(self):
        self.assertEqual(active_route_contract_failures({"A"}, {"A"}, {"A"}, {"A"}), [])

    def test_future_multi_route_trip_is_valid_when_configured(self):
        configured = {"north", "south"}
        self.assertEqual(active_route_contract_failures(configured, configured, configured, configured), [])

    def test_stale_multi_route_data_fails_the_single_route_candidate(self):
        failures = active_route_contract_failures({"A", "B"}, {"A", "B"}, {"A"}, {"A", "B"})
        self.assertTrue(any("exactly match" in failure for failure in failures))
        self.assertTrue(any("escape" in failure for failure in failures))

    def test_stale_route_reference_fails_even_without_a_stale_route_card(self):
        failures = active_route_contract_failures({"A"}, {"A"}, {"A"}, {"A", "E"})
        self.assertTrue(any("escape" in failure for failure in failures))


if __name__ == "__main__":
    unittest.main()
