#!/usr/bin/env python3
"""Build both checked-in packages through the canonical engine and prove isolation."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path

from build_map_first import ENGINE_FILES, build
from trip_package import DEFAULT_PACKAGE, load_package, validate_portable_data


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PACKAGE = "packages/portability-fixture/trip.json"
REUSABLE_FILES = (
    *ENGINE_FILES,
    "src/map_shell_template.html",
    "src/vector_entry.js",
    "vendor/maplibre-gl.css",
    "vendor/maplibre-gl.js",
    "vendor/trip-vector.js",
    "vendor/plotly.min.js",
)
OWNERSHIP_SCAN_FILES = (
    "scripts/build_map_first.py",
    "scripts/pipeline.py",
    "scripts/refresh_map_first_manifests.py",
    "scripts/trip_package.py",
    "scripts/qa_gate4_resilience.py",
    "scripts/security_privacy.py",
    "src/app_phase7.js",
    "src/atlas_messages.js",
    "src/atlas_state.js",
    "src/map_shell_template.html",
    "src/app_phase7.css",
    "src/map_first.css",
)
FORBIDDEN_RENDERER_LITERALS = (
    "data/phase7_app_data.json",
    "assets/vector/sf_trip.pmtiles",
    "yosemite_hillshade_shadow.webp",
    "SF_Smart_Minority_Map_First_Standalone.html",
    "currency: 'USD'",
    "server.arcgisonline.com",
    "www.google.com",
    "flysfo.com",
    "www.flysfo.com",
    "foodwise.org",
    "home.nps.gov",
    "www.nps.gov",
    "nps.gov",
    "gomuirwoods.com",
    "www.goldengate.org",
    "goldengate.org",
    "alcatrazcitycruises.com",
    "www.sfmta.com",
    "sfmta.com",
    "www.goldengatefortunecookies.com",
    "parks.ca.gov",
    "ci.carmel.ca.us",
    "www.pebblebeach.com",
    "www.montereybayaquarium.org",
    "gggp.org",
    "www.gggp.org",
    "museum.stanford.edu",
    "presidio.gov",
)


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def runtime_object(markup: str, name: str) -> dict:
    match = re.search(rf"window\.{re.escape(name)}=", markup)
    if not match:
        raise RuntimeError(f"Build artifact is missing window.{name}")
    value, _ = json.JSONDecoder().raw_decode(markup[match.end():])
    return value


def extract_payloads(markup: str) -> dict:
    return {name: runtime_object(markup, name) for name in ("TRIP_PACKAGE", "TRIP_DATA", "TRIP_ROUTE_GEOMETRY", "TRIP_I18N", "TRIP_FRESHNESS", "TRIP_RESEARCH_LEDGER")}


def assert_payload_identity(payloads: dict, package: dict, markup: str) -> None:
    descriptor = package
    runtime = payloads["TRIP_PACKAGE"]
    data = payloads["TRIP_DATA"]
    route_roles = json.loads((ROOT / descriptor["projections"]["route_roles"]).read_text())
    schedule = json.loads((ROOT / descriptor["projections"]["route_schedules"]).read_text())
    photos = json.loads((ROOT / descriptor["projections"]["photos_manifest"]).read_text())
    facts = {
        "trip_identity": (runtime.get("trip_identity"), descriptor["trip_identity"]),
        "display_title": (runtime.get("display_title"), descriptor["display_title"]),
        "subtitle": (runtime.get("subtitle"), descriptor["subtitle"]),
        "slug": (runtime.get("slug"), descriptor["slug"]),
        "currency": (runtime.get("currency"), descriptor["currency"]),
        "routes": (sorted(data.get("routes", {})), sorted(route_roles.get("route_ids", []))),
        "route_schedules": (sorted(data.get("route_day_models", {})), sorted(schedule.get("routes", {}))),
        "dates": (sorted(item["key"] for item in data.get("dates", [])), sorted(item["key"] for item in descriptor["data"].get("dates", []))),
        "regions": (sorted(key for key in data.get("region_cfg", {}) if key != "overall"), sorted(key for key in descriptor["data"].get("region_cfg", {}) if key != "overall")),
        "photo_root": (runtime["assets"]["photos"]["root"], descriptor["assets"]["photos"]["root"]),
        "vector_archive": (runtime["assets"]["map"]["vector_archive"], descriptor["assets"]["map"]["vector_archive"]),
        "provider_ids": (sorted(runtime["providers"]), sorted(descriptor["providers"])),
        "provider_configuration": (runtime["providers"], descriptor["providers"]),
        "source_policy": (runtime["source_policy"], descriptor["source_policy"]),
        "route_geometry": (payloads["TRIP_ROUTE_GEOMETRY"], json.loads((ROOT / descriptor["projections"]["route_geometry"]).read_text())),
        "translations": (payloads["TRIP_I18N"], json.loads((ROOT / descriptor["projections"]["translations"]).read_text())),
        "freshness": (payloads["TRIP_FRESHNESS"], json.loads((ROOT / descriptor["projections"]["freshness"]).read_text())),
        "research_ledger": (payloads["TRIP_RESEARCH_LEDGER"], json.loads((ROOT / descriptor["projections"]["research_ledger"]).read_text())),
        "photo_asset_count": (sum(len(roles) for roles in runtime["photo_assets"].values()), len(photos.get("assets", []))),
        "document_title": (re.search(r"<title>(.*?)</title>", markup, re.S).group(1) if re.search(r"<title>(.*?)</title>", markup, re.S) else None, descriptor["display_title"]),
    }
    failures = [name for name, (actual, expected) in facts.items() if actual != expected]
    if failures:
        raise RuntimeError("Package artifact identity mismatch: " + ", ".join(failures))


def ownership_scan() -> dict[str, str]:
    source = {relative: (ROOT / relative).read_text() for relative in OWNERSHIP_SCAN_FILES}
    failures = [f"{relative}:{literal}" for relative, content in source.items() for literal in FORBIDDEN_RENDERER_LITERALS if literal in content]
    if failures:
        raise RuntimeError("Instance-owned renderer/build literals returned: " + ", ".join(failures))
    return {relative: hashlib.sha256(content.encode()).hexdigest() for relative, content in source.items()}


def prove(evidence_path: Path | None = None, expected_revision: str | None = None) -> dict:
    candidate_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    candidate_tree = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT, text=True).strip()
    if expected_revision and candidate_head != expected_revision:
        raise RuntimeError(f"Portability proof candidate mismatch: expected {expected_revision}, found {candidate_head}")
    packages = {"sf": load_package(DEFAULT_PACKAGE), "fixture": load_package(FIXTURE_PACKAGE)}
    contracts = {name: validate_portable_data(package) for name, package in packages.items()}
    source_hashes_before = {relative: digest(ROOT / relative) for relative in REUSABLE_FILES}
    literal_scan = ownership_scan()
    with tempfile.TemporaryDirectory(prefix="trip-package-portability-") as temporary:
        output_roots = {name: Path(temporary) / name for name in packages}
        manifests = {
            "sf": build(output_roots["sf"], packages["sf"]["descriptor_path"]),
            "fixture": build(output_roots["fixture"], packages["fixture"]["descriptor_path"]),
        }
        outputs = {}
        renderer_build_hashes = {}
        for name, package in packages.items():
            dynamic_standalone = output_roots[name] / manifests[name]["standalone"]["path"]
            modular = output_roots[name] / "modular" / "index.html"
            if not dynamic_standalone.is_file() or not modular.is_file():
                raise RuntimeError(f"Package {name} did not emit modular and standalone artifacts")
            markup = modular.read_text()
            payloads = extract_payloads(markup)
            assert_payload_identity(payloads, package, markup)
            renderer_build_hashes[name] = {relative: digest(output_roots[name] / "modular" / relative) for relative in ENGINE_FILES}
            outputs[name] = {
                "trip_identity": package["trip_identity"],
                "display_title": package["display_title"],
                "slug": package["slug"],
                "currency": package["currency"],
                "routes": sorted(payloads["TRIP_DATA"]["routes"]),
                "dates": sorted(item["key"] for item in payloads["TRIP_DATA"]["dates"]),
                "regions": sorted(key for key in payloads["TRIP_DATA"]["region_cfg"] if key != "overall"),
                "photo_root": payloads["TRIP_PACKAGE"]["assets"]["photos"]["root"],
                "vector_archive": payloads["TRIP_PACKAGE"]["assets"]["map"]["vector_archive"],
                "vector_identity": payloads["TRIP_PACKAGE"]["assets"]["map"]["identity"],
                "vector_provider_id": package["vector_provider_id"],
                "vector_archive_sha256": digest(ROOT / package["assets"]["map"]["vector_archive"]),
                "official_hosts": sorted(payloads["TRIP_PACKAGE"]["source_policy"]["official_sources"]["hosts"]),
                "provider_ids": sorted(payloads["TRIP_PACKAGE"]["providers"]),
                "photo_count": len(payloads["TRIP_PACKAGE"]["photo_assets"]),
                "standalone": manifests[name]["standalone"]["path"],
                "standalone_sha256": manifests[name]["standalone"]["sha256"],
                "modular_sha256": manifests[name]["modular"]["sha256"],
            }
            outputs[name]["authored_runtime_payload"] = payloads
        renderer_equal = all(renderer_build_hashes["sf"][path] == renderer_build_hashes["fixture"][path] for path in ENGINE_FILES)
        source_hashes_after = {relative: digest(ROOT / relative) for relative in REUSABLE_FILES}
        if source_hashes_before != source_hashes_after or not renderer_equal:
            raise RuntimeError("Reusable renderer bytes changed during package builds or differ across package outputs")

    sf_payload, fixture_payload = outputs["sf"]["authored_runtime_payload"], outputs["fixture"]["authored_runtime_payload"]
    sf_package, fixture_package = packages["sf"], packages["fixture"]
    sf_data, fixture_data = sf_payload["TRIP_DATA"], fixture_payload["TRIP_DATA"]
    sf_text = json.dumps(sf_payload, ensure_ascii=False).lower()
    fixture_text = json.dumps(fixture_payload, ensure_ascii=False).lower()
    fixture_forbidden = [token for token in ("sf-family-2026-final", "sf / monterey / yosemite", "san francisco", "yosemite", "monterey") if token in fixture_text]
    sf_forbidden = [token for token in (fixture_package["trip_identity"], fixture_package["display_title"].lower(), "juniper.test", "2041-03-09", "2041-03-10", "cny") if token.lower() in sf_text]
    structured_crossings = {
        "route_ids": sorted(set(sf_data["routes"]) & set(fixture_data["routes"])),
        "date_keys": sorted({item["key"] for item in sf_data["dates"]} & {item["key"] for item in fixture_data["dates"]}),
        "region_keys": sorted((set(sf_data["region_cfg"]) - {"overall"}) & (set(fixture_data["region_cfg"]) - {"overall"})),
        "place_keys": sorted({item["place_key"] for item in sf_data["markers"]} & {item["place_key"] for item in fixture_data["markers"]}),
        "provider_ids": sorted(set(sf_package["providers"]) & set(fixture_package["providers"])),
        "official_hosts": sorted(set(sf_package["source_policy"]["official_sources"]["hosts"]) & set(fixture_package["source_policy"]["official_sources"]["hosts"])),
        "currencies_equal": sf_package["currency"] == fixture_package["currency"],
        "vector_asset_paths_equal": sf_package["assets"]["map"]["vector_archive"] == fixture_package["assets"]["map"]["vector_archive"],
        "vector_identities_equal": sf_package["assets"]["map"]["identity"] == fixture_package["assets"]["map"]["identity"],
        "vector_provider_ids_equal": sf_package["vector_provider_id"] == fixture_package["vector_provider_id"],
        "vector_asset_bytes_equal": outputs["sf"]["vector_archive_sha256"] == outputs["fixture"]["vector_archive_sha256"],
        "trip_identity_equal": sf_package["trip_identity"] == fixture_package["trip_identity"],
        "titles_equal": sf_package["display_title"] == fixture_package["display_title"],
    }
    leakage = {
        "sf_into_fixture": fixture_forbidden,
        "fixture_into_sf": sf_forbidden,
        "package_identity_overlap": structured_crossings,
    }
    if fixture_forbidden or sf_forbidden or any(value is True or value for value in structured_crossings.values()):
        raise RuntimeError("Cross-package runtime leakage detected: " + json.dumps(leakage, ensure_ascii=False))
    if not packages["fixture"].get("is_non_shipping_fixture") or not outputs["fixture"]["standalone"].startswith(f"standalone/{packages['fixture']['slug']}-"):
        raise RuntimeError("Portability fixture is not visibly flagged as non-shipping or its artifact name ignores the slug")

    report = {
        "schema_version": 1,
        "status": "PASS",
        "candidate_head": candidate_head,
        "candidate_tree": candidate_tree,
        "commands": [
            "python3 scripts/build_map_first.py --package packages/sf-family/trip.json --output-dir <temporary>/sf",
            "python3 scripts/build_map_first.py --package packages/portability-fixture/trip.json --output-dir <temporary>/fixture",
        ],
        "contracts": contracts,
        "outputs": {name: {key: value for key, value in record.items() if key != "authored_runtime_payload"} for name, record in outputs.items()},
        "renderer_source_sha256": source_hashes_before,
        "built_renderer_sha256": renderer_build_hashes,
        "renderer_bytes_identical": renderer_equal,
        "renderer_source_unchanged": source_hashes_before == source_hashes_after,
        "literal_ownership_scan": {"status": "PASS", "files": literal_scan, "forbidden_literals": list(FORBIDDEN_RENDERER_LITERALS)},
        "cross_package_leakage": leakage,
    }
    if evidence_path:
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--expected-revision")
    args = parser.parse_args()
    report = prove(args.evidence, args.expected_revision)
    print(json.dumps({"status": report["status"], "renderer_bytes_identical": report["renderer_bytes_identical"], "leakage": report["cross_package_leakage"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
