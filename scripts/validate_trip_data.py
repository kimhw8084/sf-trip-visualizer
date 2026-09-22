"""Fail-closed Gate 3 validation for canonical trip truth and freshness.

This validator is intentionally independent of the browser renderer.  It checks
the authored runtime dataset, its reference evidence, derived route geometry,
photo identities, bilingual critical fields, and the freshness authority without
rewriting any input.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "manifests" / "canonical_pipeline.json"
DATA = ROOT / "data" / "phase7_app_data.json"
FRESHNESS = ROOT / "manifests" / "trip_freshness.json"
TRANSLATIONS = ROOT / "data" / "translations.json"
GEOMETRY = ROOT / "data" / "route_geometry_cache.json"
GEOMETRY_MANIFEST = ROOT / "data" / "route_geometry_manifest.json"
ROLE_MATRIX = ROOT / "data" / "route_role_matrix.json"
ASSETS = ROOT / "manifests" / "asset_manifest.json"
REFERENCE_FILES = {
    "routes": ROOT / "data" / "routes.json",
    "itineraries": ROOT / "data" / "itineraries.json",
    "canonical_places": ROOT / "data" / "canonical_places.json",
    "coordinate_audit": ROOT / "data" / "coordinate_audit.json",
    "location_coverage": ROOT / "data" / "location_coverage_audit.json",
    "source_manifest": ROOT / "manifests" / "source_manifest.json",
}

KO = re.compile(r"[가-힣]")
DATE = re.compile(r"^(\d{1,2}/\d{1,2})")
BRANCH_KINDS = {"main", "conditional", "swap", "bonus", "recovery", "choice"}
GEOMETRY_STATUSES = {"routed_osm", "conceptual_ferry", "conceptual_transfer"}
REGIONS = {"sf", "monterey", "yosemite"}


def load(path: Path) -> Any:
    return json.loads(path.read_text())


def close(a: float, b: float, tolerance: float = 0.00002) -> bool:
    return abs(float(a) - float(b)) <= tolerance


def coordinate_equal(actual: list[float], expected: list[float], tolerance: float = 0.00002) -> bool:
    return len(actual) == 2 and len(expected) == 2 and close(actual[0], expected[0], tolerance) and close(actual[1], expected[1], tolerance)


def has_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def date_key(value: Any) -> str | None:
    match = DATE.match(str(value or ""))
    return match.group(1) if match else None


def validate_trip_data() -> dict[str, Any]:
    manifest = load(MANIFEST)
    data = load(DATA)
    translations = load(TRANSLATIONS)
    geometry = load(GEOMETRY)
    geometry_manifest = load(GEOMETRY_MANIFEST)
    assets = load(ASSETS)
    freshness = load(FRESHNESS)
    role_doc = load(ROLE_MATRIX)
    route_role_matrix = role_doc.get("places", {})
    canonical_route_ids = role_doc.get("route_ids", [])
    references = {name: load(path) for name, path in REFERENCE_FILES.items()}
    failures: list[str] = []
    checks: dict[str, bool] = {}

    def check(name: str, passed: bool, detail: str | None = None) -> None:
        checks[name] = passed
        if not passed:
            failures.append(f"{name}{': ' + detail if detail else ''}")

    truth = manifest.get("truth_authority", {})
    check("truth_authority_source", truth.get("authored_source") == "data/phase7_app_data.json")
    check("truth_authority_validator", truth.get("validator") == "scripts/validate_trip_data.py")
    check("reference_files_are_not_runtime_authority", all(path != truth.get("authored_source") for path in manifest.get("reference_evidence_inputs", [])))
    required = set(truth.get("required_top_level_fields", []))
    check("canonical_truth_fields", required.issubset(data))

    routes = data.get("routes", {})
    route_ids = set(routes)
    dates = data.get("dates", [])
    date_ids = [item.get("key") for item in dates]
    date_set = set(date_ids)
    markers = data.get("markers", [])
    marker_keys = [marker.get("place_key") for marker in markers]
    marker_set = set(marker_keys)
    place_region = data.get("place_region", {})
    endpoint_anchors = data.get("endpoint_anchors", {})

    check("physical_place_keys_unique", len(marker_keys) == len(marker_set) and all(has_text(key) for key in marker_keys))
    expected = manifest.get("invariants", {})
    check("place_count", len(markers) == expected.get("places") == len(route_role_matrix) == 39)
    check("timeline_count", len(data.get("timeline", [])) == expected.get("timeline_cards"))
    check("leg_count", len(data.get("legs", [])) == expected.get("route_legs"))
    check("route_count", sorted(route_ids) == sorted(canonical_route_ids) == ["A", "B", "C", "D", "E"])
    recommended_routes = [route for route, meta in routes.items() if meta.get("recommended") is True]
    check("recommended_route_is_explicit", recommended_routes == ["A"])
    check("date_count", len(dates) == expected.get("dates") and len(date_set) == len(dates))
    check("region_count", set(place_region.values()) == REGIONS and set(data.get("region_cfg", {})) == REGIONS | {"overall"})
    check("provider_keys", sorted(data.get("providers", {})) == ["satellite", "vector"])
    check("provider_configuration", all(has_text(data["providers"].get(key, {}).get("label")) for key in ("vector", "satellite")))
    check("region_labels_bilingual", all(has_text(meta.get("label")) and has_text(meta.get("label_ko")) for meta in data.get("region_cfg", {}).values()))

    for marker in markers:
        key = marker.get("place_key")
        path = f"markers[{key}]"
        routes_for_marker = marker.get("routes", [])
        check(f"{path}.routes_valid", bool(routes_for_marker) and set(routes_for_marker) <= route_ids and marker.get("route_count") == len(routes_for_marker))
        roles = route_role_matrix.get(key, {})
        check(f"{path}.role_matrix", set(roles) == set(canonical_route_ids) and all(roles[route] in {"Core", "Strong", "Conditional", "Skip"} for route in canonical_route_ids))
        check(f"{path}.routes_derived_from_roles", set(routes_for_marker) == {route for route in canonical_route_ids if roles.get(route) != "Skip"})
        check(f"{path}.region_resolves", key in place_region and place_region[key] in REGIONS)
        check(f"{path}.coordinate", isinstance(marker.get("lat"), (int, float)) and isinstance(marker.get("lon"), (int, float)))
        occurrences = marker.get("occurrences", [])
        occurrence_ids = [(item.get("route"), item.get("date"), item.get("seq"), item.get("time"), item.get("title")) for item in occurrences]
        check(f"{path}.occurrences_unique", len(occurrence_ids) == len(set(occurrence_ids)))
        for index, occurrence in enumerate(occurrences):
            route = occurrence.get("route")
            day = date_key(occurrence.get("date"))
            check(f"{path}.occurrence[{index}].route", route in route_ids and route in routes_for_marker)
            check(f"{path}.occurrence[{index}].date", day in date_set)
            check(f"{path}.occurrence[{index}].critical_fields", all(has_text(occurrence.get(field)) for field in ("title", "reason", "advantage", "status")))
            role = roles.get(route)
            check(f"{path}.occurrence[{index}].role_agrees", role in {"Core", "Strong", "Conditional"})
            if role == "Conditional":
                check(f"{path}.occurrence[{index}].conditional_rule", has_text(occurrence.get("condition")) and has_text(occurrence.get("recovery_rule")))
            if role == "Core":
                check(f"{path}.occurrence[{index}].core_fallback", has_text(occurrence.get("fallback_rule")))

    check("place_region_is_exact", set(place_region) == marker_set)

    timeline_ids = [item.get("id") for item in data.get("timeline", [])]
    check("timeline_ids_unique", len(timeline_ids) == len(set(timeline_ids)))
    for item in data.get("timeline", []):
        prefix = f"timeline[{item.get('id')}]"
        item_routes = set(item.get("routes", []))
        item_regions = set(item.get("regions", []))
        check(f"{prefix}.date", item.get("date_key") in date_set and date_key(item.get("date")) == item.get("date_key"))
        check(f"{prefix}.routes", bool(item_routes) and item_routes <= route_ids)
        check(f"{prefix}.regions", item_regions <= REGIONS)
        check(f"{prefix}.critical_fields", all(has_text(item.get(field)) for field in ("title", "reason", "advantage")))
        for key in item.get("spatial_keys", []):
            check(f"{prefix}.spatial_key_resolves.{key}", key in marker_set)
            if key not in marker_set:
                continue
            marker = next(marker for marker in markers if marker["place_key"] == key)
            occurrences = marker.get("occurrences", [])
            available_routes = {occurrence.get("route") for occurrence in occurrences if date_key(occurrence.get("date")) == item.get("date_key")}
            check(f"{prefix}.route_date_membership.{key}", item_routes <= available_routes)
            check(f"{prefix}.region_membership.{key}", place_region.get(key) in item_regions)

    def resolve_endpoint(endpoint: str) -> tuple[dict[str, Any] | None, str]:
        if endpoint in marker_set:
            marker = next(marker for marker in markers if marker["place_key"] == endpoint)
            return {"lat": marker["lat"], "lon": marker["lon"], "region": place_region[endpoint], "kind": "place"}, endpoint
        anchor = endpoint_anchors.get(endpoint)
        if anchor:
            return {**anchor, "kind": "anchor"}, endpoint
        return None, endpoint

    legs = data.get("legs", [])
    leg_ids = [leg.get("leg_id") for leg in legs]
    check("leg_ids_unique", len(leg_ids) == len(set(leg_ids)))
    for leg in legs:
        prefix = f"leg[{leg.get('leg_id')}]"
        from_ref, from_name = resolve_endpoint(leg.get("from"))
        to_ref, to_name = resolve_endpoint(leg.get("to"))
        check(f"{prefix}.from_resolves", from_ref is not None, from_name)
        check(f"{prefix}.to_resolves", to_ref is not None, to_name)
        leg_routes = set(leg.get("routes", []))
        branch = leg.get("branch_kind", "main")
        check(f"{prefix}.date", leg.get("date") in date_set)
        check(f"{prefix}.routes", bool(leg_routes) and leg_routes <= route_ids)
        check(f"{prefix}.branch_kind", branch in BRANCH_KINDS)
        check(f"{prefix}.typed_fields", all(has_text(leg.get(field)) for field in ("mode", "label", "note", "render_style", "geometry_source")))
        if from_ref and to_ref:
            check(f"{prefix}.from_coordinate", coordinate_equal(leg.get("from_latlon", []), [from_ref["lat"], from_ref["lon"]], 0.00005))
            check(f"{prefix}.to_coordinate", coordinate_equal(leg.get("to_latlon", []), [to_ref["lat"], to_ref["lon"]], 0.00005))
            crosses_region = from_ref.get("region") != to_ref.get("region")
            check(f"{prefix}.transfer_rendering", (not crosses_region) or leg.get("render_style") == "transfer_dots")
            check(f"{prefix}.transfer_semantics", (leg.get("render_style") != "transfer_dots") or leg.get("geometry_kind") == "conceptual_transfer")
        cross_date_relationship = leg.get("relationship_scope") == "cross_date_scenario"
        if leg.get("from") in marker_set and leg.get("to") in marker_set:
            for route in leg_routes:
                from_dates = {date_key(item.get("date")) for item in next(marker for marker in markers if marker["place_key"] == leg["from"])["occurrences"] if item.get("route") == route}
                to_dates = {date_key(item.get("date")) for item in next(marker for marker in markers if marker["place_key"] == leg["to"])["occurrences"] if item.get("route") == route}
                if cross_date_relationship:
                    check(f"{prefix}.cross_date_endpoints.{route}", leg.get("from_date_key") in from_dates and leg.get("to_date_key") in to_dates)
                else:
                    check(f"{prefix}.endpoint_route_date.{route}", leg.get("date") in from_dates and leg.get("date") in to_dates)
        if leg.get("mode") == "ferry":
            check(f"{prefix}.ferry_is_conceptual", leg.get("geometry_kind") in {"conceptual", "conceptual_ferry", "osm_reference_pending"} and leg.get("render_style") in {"conceptual_dots", "conceptual_ferry_dots"} and not re.search(r"track|항적", str(leg.get("note", "")), re.IGNORECASE) is None)
        if branch != "main":
            check(f"{prefix}.branch_explanation", has_text(leg.get("label")) and has_text(leg.get("note")))

    check("anchor_registry_is_explicit", set(endpoint_anchors) == {"Pier 33 Alcatraz Landing", "sf_center", "monterey_center", "yosemite_valley"})
    check("anchor_registry_provenance", all(has_text(anchor.get("coordinate_provenance")) and anchor.get("role") in {"ferry_embarkation", "transfer_anchor"} for anchor in endpoint_anchors.values()))

    coordinate_audit = references["coordinate_audit"]
    coordinate_keys = [row.get("place_key") for row in coordinate_audit]
    check("coordinate_audit_unique", len(coordinate_keys) == len(set(coordinate_keys)))
    check("coordinate_audit_covers_places", set(coordinate_keys) == marker_set)
    for row in coordinate_audit:
        key = row.get("place_key")
        marker = next((marker for marker in markers if marker.get("place_key") == key), None)
        check(f"coordinate[{key}].role", has_text(row.get("coordinate_type")))
        check(f"coordinate[{key}].provenance", has_text(row.get("verification_source")) and has_text(row.get("verification_source_url")))
        check(f"coordinate[{key}].verified", isinstance(row.get("verified_lat"), (int, float)) and isinstance(row.get("verified_lon"), (int, float)))
        if marker:
            check(f"coordinate[{key}].runtime_reconciles", close(marker["lat"], row["verified_lat"], 0.00005) and close(marker["lon"], row["verified_lon"], 0.00005))
    canonical_places = references["canonical_places"]
    canonical_place_keys = [row.get("place_key") for row in canonical_places]
    check("canonical_places_unique", len(canonical_place_keys) == len(set(canonical_place_keys)))
    check("canonical_places_covers_places", set(canonical_place_keys) == marker_set)
    location_result = references["location_coverage"].get("result", {})
    check("location_audit_count", location_result.get("total_places", location_result.get("final_map_places")) == len(markers))

    source_manifest = references["source_manifest"]
    check("source_manifest_classifies_snapshots", source_manifest.get("reference_role") == "locked_reference_evidence" or source_manifest.get("evidence_role") == "reference_only")
    policy = source_manifest.get("authority_policy", "")
    check("source_manifest_does_not_override_runtime", "never override" in policy or "never overrides" in policy)
    route_snapshot = references["routes"].get("routes", {})
    itinerary_snapshot = references["itineraries"].get("plans", {})
    check("route_snapshot_reconciles", set(route_snapshot) == route_ids)
    check("itinerary_snapshot_reconciles", set(itinerary_snapshot) == route_ids)

    asset_items = assets.get("assets", [])
    asset_ids = [(asset.get("place_key"), asset.get("role")) for asset in asset_items]
    expected_roles = set(expected.get("photo_roles", []))
    check("photo_identity_unique", len(asset_ids) == len(set(asset_ids)))
    check("photo_identity_covers_places", {key for key, _ in asset_ids} == marker_set)
    check("photo_roles_complete", len(asset_items) == expected.get("photos") and {role for _, role in asset_ids} == expected_roles)
    for asset in asset_items:
        check(f"photo[{asset.get('place_key')}/{asset.get('role')}].paths", all(has_text(asset.get(field)) and (ROOT / asset[field]).is_file() for field in ("local_thumb_path", "local_medium_path")))

    def bilingual(value: Any, path: str, *, require_reverse: bool = False) -> None:
        if not has_text(value) or value.startswith("http"):
            return
        if KO.search(value):
            check(f"bilingual.ko_to_en.{path}", has_text(translations.get("ko_to_en", {}).get(value)))
        elif require_reverse and re.search(r"[A-Za-z]{3}", value) and len(value) > 8:
            check(f"bilingual.en_to_ko.{path}", has_text(translations.get("en_to_ko", {}).get(value)))

    for route, meta in routes.items():
        for field in ("title", "subtitle", "core_reason", "lodging"):
            bilingual(meta.get(field), f"route.{route}.{field}")
        for locale in ("ko", "en"):
            narrative = meta.get("explanation", {}).get(locale, {})
            check(f"bilingual.route.{route}.{locale}", all(has_text(narrative.get(field)) for field in ("best_for", "tradeoff", "decision_rule", "regret_guard")))
    for marker in markers:
        key = marker["place_key"]
        for field in ("title", "summary", "why", "role", "cluster"):
            bilingual(marker.get(field), f"marker.{key}.{field}")
        place_pair = translations.get("places", {}).get(key, [])
        check(f"bilingual.place_name.{key}", isinstance(place_pair, list) and len(place_pair) == 2 and all(has_text(value) for value in place_pair))
        for occurrence in marker.get("occurrences", []):
            for field in ("title", "reason", "advantage", "kind", "status", "stop_reason", "stop_advantage"):
                bilingual(occurrence.get(field), f"occurrence.{key}.{occurrence.get('route')}.{field}")
        for rule in marker.get("decision_rules", []):
            bilingual(rule.get("text"), f"decision_rule.{key}.{rule.get('key')}")
    for item in data.get("timeline", []):
        for field in ("title", "reason", "advantage", "kind"):
            bilingual(item.get(field), f"timeline.{item.get('id')}.{field}")
    for leg in legs:
        for field in ("label", "note"):
            bilingual(leg.get(field), f"leg.{leg.get('leg_id')}.{field}")
    check("translations_have_no_known_missing_korean", translations.get("untranslated_korean_data_values") == [])

    geometry_ids = set(geometry)
    check("geometry_covers_legs", geometry_ids == set(leg_ids))
    check("geometry_manifest_covers_legs", {item.get("leg_id") for item in geometry_manifest.get("legs", [])} == set(leg_ids))
    for leg in legs:
        entry = geometry.get(leg["leg_id"], {})
        prefix = f"geometry[{leg['leg_id']}]"
        status = entry.get("status")
        check(f"{prefix}.status", status in GEOMETRY_STATUSES)
        check(f"{prefix}.provenance", has_text(entry.get("source")) and isinstance(entry.get("endpoint_signature"), list))
        check(f"{prefix}.coordinates", isinstance(entry.get("coordinates"), list) and len(entry.get("coordinates", [])) >= 2)
        if leg.get("mode") == "ferry":
            check(f"{prefix}.ferry_status", status == "conceptual_ferry")
        if leg.get("render_style") == "transfer_dots":
            check(f"{prefix}.transfer_status", status == "conceptual_transfer")
            check(f"{prefix}.transfer_source_limit", "not a verified road track" in str(geometry_manifest.get("legs", [])[leg_ids.index(leg["leg_id"])].get("source_limitation", "")))
        if status == "routed_osm":
            check(f"{prefix}.road_reference_limit", "verify live closures" in str(entry.get("endpoint_note", "")) or "not live" in str(geometry_manifest.get("legs", [])[leg_ids.index(leg["leg_id"])].get("source_limitation", "")))

    records = freshness.get("records", [])
    fact_ids = [record.get("fact_id") for record in records]
    check("freshness_project", freshness.get("project") == "sf-trip-visualizer")
    check("freshness_ids_unique", len(fact_ids) == len(set(fact_ids)) and all(has_text(value) for value in fact_ids))
    check("freshness_default_fail_closed", freshness.get("default_status") == "RECHECK_REQUIRED" and freshness.get("default_certainty") == "NOT_CURRENTLY_VERIFIED")
    allowed_status = {"VERIFIED", "STALE", "UNVERIFIED", "RECHECK_REQUIRED", "NOT_APPLICABLE"}
    for record in records:
        prefix = f"freshness[{record.get('fact_id')}]"
        source = record.get("source", {})
        recheck = record.get("recheck", {})
        check(f"{prefix}.scope", isinstance(record.get("scope"), dict) and bool(record.get("scope")))
        check(f"{prefix}.source", bool(source.get("source_urls")) and all(urlparse(url).scheme in {"http", "https"} for url in source.get("source_urls", [])))
        check(f"{prefix}.metadata", record.get("status") in allowed_status and has_text(record.get("certainty")) and has_text(recheck.get("trigger")) and has_text(recheck.get("window")))
        observed = record.get("observed_on")
        observed_valid = observed is None or bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(observed)))
        check(f"{prefix}.observed_on", observed_valid)
        if record.get("status") == "VERIFIED":
            check(f"{prefix}.verified_requires_observation", observed is not None)
        if observed is None:
            check(f"{prefix}.null_date_is_fail_closed", record.get("status") in {"UNVERIFIED", "RECHECK_REQUIRED", "STALE"})
        check(f"{prefix}.claim_coverage", bool(record.get("product_claim_refs")))

    report = {
        "status": "PASS" if not failures else "FAIL",
        "checks": checks,
        "failure_count": len(failures),
        "failures": failures,
        "counts": {
            "places": len(markers),
            "timeline_cards": len(data.get("timeline", [])),
            "legs": len(legs),
            "routes": len(routes),
            "dates": len(dates),
            "freshness_records": len(records),
            "geometry_entries": len(geometry),
        },
        "roles": {row["place_key"]: row["coordinate_type"] for row in coordinate_audit},
        "geometry_statuses": {status: sum(entry.get("status") == status for entry in geometry.values()) for status in sorted(GEOMETRY_STATUSES)},
        "freshness_statuses": {status: sum(record.get("status") == status for record in records) for status in sorted(allowed_status)},
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()
    report = validate_trip_data()
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "failure_count": report["failure_count"], "counts": report["counts"], "failures": report["failures"][:20]}, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
