"""Fail-closed package schema and authored/projection consistency checks."""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from trip_package import (  # noqa: E402
    DEFAULT_PACKAGE,
    PackageError,
    ROOT,
    load_package,
    validate_policy,
    validate_portable_data,
)


FIXTURE = "packages/portability-fixture/trip.json"


class TripPackageTests(unittest.TestCase):
    def test_active_and_portability_packages_satisfy_shared_contract(self):
        for path in (DEFAULT_PACKAGE, FIXTURE):
            with self.subTest(package=path):
                package = load_package(path)
                self.assertEqual(validate_portable_data(package)["status"], "PASS")
        fixture = load_package(FIXTURE)
        self.assertEqual(fixture["vector_provider_id"], "juniper_local_map")
        self.assertNotEqual(fixture["vector_provider_id"], load_package(DEFAULT_PACKAGE)["vector_provider_id"])

    def test_unrecognized_currency_fails_before_build(self):
        descriptor = json.loads((ROOT / DEFAULT_PACKAGE).read_text())
        descriptor["currency"] = "XYZ"
        with tempfile.TemporaryDirectory(prefix="invalid-currency-", dir=ROOT / "packages") as temporary:
            path = Path(temporary) / "trip.json"
            path.write_text(json.dumps(descriptor))
            with self.assertRaisesRegex(PackageError, "Unrecognized trip currency"):
                load_package(path.relative_to(ROOT))

    def test_missing_geometry_package_policy_fails_schema_validation(self):
        descriptor = json.loads((ROOT / FIXTURE).read_text())
        descriptor.pop("geometry_metadata")
        with tempfile.TemporaryDirectory(prefix="missing-geometry-policy-", dir=ROOT / "packages") as temporary:
            path = Path(temporary) / "trip.json"
            path.write_text(json.dumps(descriptor))
            with self.assertRaisesRegex(PackageError, "geometry_metadata"):
                load_package(path.relative_to(ROOT))

    def test_unsafe_direction_destinations_fail_closed(self):
        package = load_package(FIXTURE)
        bad_policy = copy.deepcopy(package["source_policy"])
        bad_policy["external"]["directions"]["links"]["place"] = "https://attacker.invalid.test/place/?q={query}"
        with self.assertRaisesRegex(PackageError, "does not match its declared HTTPS host/path"):
            validate_policy(bad_policy, package["providers"])

    def test_provider_host_cannot_escape_declared_path_policy(self):
        package = load_package(FIXTURE)
        bad_policy = copy.deepcopy(package["source_policy"])
        bad_policy["external"]["beacon_tiles"]["path_prefix"] = "/other/"
        with self.assertRaisesRegex(PackageError, "unsafe raster URL configuration"):
            validate_policy(bad_policy, package["providers"])

    def test_stale_route_geometry_fails_before_artifact_emission(self):
        package = load_package(FIXTURE)
        package["data"]["legs"][0]["from"] = "unknown_place"
        with self.assertRaisesRegex(PackageError, "unknown endpoint"):
            validate_portable_data(package)

    def test_stale_package_map_and_provider_manifests_fail_before_artifact_emission(self):
        package = load_package(FIXTURE)
        package["assets"]["map"]["source_metadata"]["label"] = "A changed local map source"
        with self.assertRaisesRegex(PackageError, "map manifest is stale"):
            validate_portable_data(package)
        package = load_package(FIXTURE)
        package["providers"]["beacon_tiles"]["label_en"] = "A changed raster label"
        with self.assertRaisesRegex(PackageError, "provider manifest is stale"):
            validate_portable_data(package)

    def test_default_https_port_is_still_rejected_for_package_directions(self):
        package = load_package(FIXTURE)
        package["data"]["markers"][0]["maps_url"] = package["data"]["markers"][0]["maps_url"].replace("nav.juniper.example.test", "nav.juniper.example.test:443", 1)
        with self.assertRaisesRegex(PackageError, "directions URL violates package policy"):
            validate_portable_data(package)

    def test_provider_configuration_has_one_package_authority(self):
        package = load_package(FIXTURE)
        package["data"]["providers"] = {"raster": {"tile_template": "https://other.test/{z}/{x}/{y}"}}
        with self.assertRaisesRegex(PackageError, "belongs to the trip-package descriptor"):
            validate_portable_data(package)


if __name__ == "__main__":
    unittest.main()
