"""Refresh package-owned map/provider manifests and cached geometry provenance."""

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path

from trip_package import DEFAULT_PACKAGE, load_package


ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--package", default=DEFAULT_PACKAGE, help="trip package descriptor (defaults to canonical active package)")
args = parser.parse_args()
package = load_package(args.package)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


map_config = package["assets"]["map"]
source_metadata = map_config["source_metadata"]
vector_provider_id = package["vector_provider_id"]
vector_provider = package["providers"][vector_provider_id]
map_paths = set()
for relative in map_config["local_resources"]:
    path = ROOT / relative
    map_paths.update(item for item in path.rglob("*") if item.is_file()) if path.is_dir() else map_paths.add(path)
relief = map_config.get("relief")
if relief and relief.get("source_path"):
    map_paths.add(ROOT / relief["source_path"])
map_assets = sorted(map_paths, key=lambda path: str(path.relative_to(ROOT)))
basemap = {
    "version": "map-first-1.0", "generated": str(date.today()),
    "trip_identity": package["trip_identity"], "display_title": package["display_title"],
    "default": vector_provider_id, "fallback": None,
    "vector_source": {
        "label": source_metadata["label"],
        "source_build": source_metadata["source_build"],
        "extraction_bbox_lonlat": source_metadata["extraction_bbox_lonlat"],
        "max_source_zoom": source_metadata["max_source_zoom"], "render_engine": source_metadata["render_engine"],
        "online_api_key_required": source_metadata["online_api_key_required"],
        "license_attribution": vector_provider["attribution"],
        "standalone_loading": "Embedded PMTiles FileSource and bundled glyph/sprite protocols",
        "modular_loading": "Local HTTP Range requests; use scripts/serve_map.py",
    },
    "assets": [{"path": str(path.relative_to(ROOT)), "bytes": path.stat().st_size, "sha256": digest(path)} for path in map_assets],
    "provider_failure_domains": {provider_id: provider.get("failure_domain", provider["identity"]) for provider_id, provider in package["providers"].items()},
    "user_selectable_providers": list(package["providers"]),
    "internal_emergency_fallback": None,
    "retired_user_choices": map_config.get("retired_provider_choices", []),
    "policy_notes": source_metadata["policy_notes"],
}
if relief:
    basemap["relief"] = {
        key: relief[key] for key in ("source", "provider", "bbox_lonlat", "source_path", "role") if key in relief
    } | {"render_derivative_path": relief["path"], "coordinates": relief["coordinates"]}
(ROOT / package["projections"]["map_manifest"]).write_text(json.dumps(basemap, ensure_ascii=False, indent=2) + "\n")
provider_manifest = {
    provider_id: {
        "label": provider["label_en"],
        "kind": provider["identity"],
        "network_required": not provider.get("local", False),
        "attribution": provider["attribution"],
        "failure_behavior": provider.get("failure_behavior", "Keep the selected local provider and expose a load error."),
        **({"health_probe": provider["health_probe"]} if provider.get("health_probe") else {}),
    }
    for provider_id, provider in package["providers"].items()
}
provider_manifest["user_selectable_provider_count"] = len(package["providers"])
provider_manifest["removed_user_choices"] = []
(ROOT / package["projections"]["provider_manifest"]).write_text(json.dumps(provider_manifest, ensure_ascii=False, indent=2) + "\n")

manifest_path = ROOT / package["projections"]["route_geometry_manifest"]
manifest = json.loads(manifest_path.read_text())
cache_path = ROOT / package["projections"]["route_geometry"]
cache = json.loads(cache_path.read_text())
app_data = package["data"]
geometry_metadata = package["geometry_metadata"]
legs = app_data.get("legs", [])
routed_count = sum(entry.get("status") in geometry_metadata["routed_statuses"] for entry in cache.values())
conceptual_count = sum(entry.get("status") in geometry_metadata["conceptual_statuses"] for entry in cache.values())
conceptual_ferry_count = sum(entry.get("status") == "conceptual_ferry" for entry in cache.values())
unavailable_count = sum(entry.get("status") in geometry_metadata["omitted_statuses"] for entry in cache.values())
semantic_public_count = sum(leg.get("mode") in {"drive", "walk"} for leg in legs)
point_count = sum(len(entry.get("coordinates", [])) for entry in cache.values())
omissions = app_data.get("route_graph_omissions", [])
manifest.update({
    "trip_identity": package["trip_identity"],
    "version": "2.0-map-first", "generated": str(date.today()),
    "routing_service_status": geometry_metadata["routing_service_status"],
    "acceptance_strategy": f"{routed_count}/{semantic_public_count} semantic public route legs have cached reference geometry; {conceptual_count} conceptual relationships remain endpoint-only; {len(omissions) + unavailable_count} connections are intentionally omitted. App runtime performs no routing requests.",
    "exact_routed_legs": routed_count,
    "semantic_public_route_legs": semantic_public_count,
    "routed_public_legs": routed_count,
    "conceptual_legs": conceptual_count,
    "conceptual_ferry_legs": conceptual_ferry_count,
    "conceptual_relationship_legs": conceptual_count,
    "unavailable_physical_legs": unavailable_count,
    "intentionally_omitted_connections": len(omissions),
    "total_geometry_point_count": point_count,
    "renderable_conceptual_legs": conceptual_ferry_count,
    "counts": {
        "semantic_public_route_legs": semantic_public_count,
        "routed_public_legs": routed_count,
        "conceptual_legs": conceptual_count,
        "conceptual_ferry_legs": conceptual_ferry_count,
        "intentionally_omitted_legs": len(omissions) + unavailable_count,
        "unavailable_physical_legs": unavailable_count,
        "total_geometry_points": point_count,
    },
    "display_policy": "Display only package-declared cached geometry. Omit unavailable lines and retain conceptual relationships as endpoint links. App runtime performs no routing requests.",
    "geometry_cache_path": package["projections"]["route_geometry"],
    "geometry_cache_sha256": digest(cache_path),
    "cross_day_suppressed_legs": [],
    "omitted_connections": [
        {"omission_id": item["omission_id"], "date_key": item["date_key"], "from": item.get("from"), "to": item.get("to"), "mode": item.get("mode"), "status": item["status"], "endpoint_signature": None, "point_count": 0, "reason": item["reason"]}
        for item in omissions
    ],
})
manifest["legs"] = []
for source_leg in legs:
    leg = dict(source_leg)
    entry = cache[leg["leg_id"]]
    leg["geometry_kind"] = entry["status"]
    leg["geometry_source"] = entry.get("source")
    leg["geometry_point_count"] = len(entry.get("coordinates", []))
    leg["point_count"] = len(entry.get("coordinates", []))
    leg["status"] = entry["status"]
    leg["mode"] = entry.get("mode")
    leg["endpoint_signature"] = entry.get("endpoint_signature")
    leg["distance_km"] = entry.get("distance_km")
    leg["reference_duration_min"] = entry.get("duration_min_reference")
    leg["source"] = entry.get("source")
    leg["render_style"] = source_leg.get("render_style")
    leg["source_limitation"] = geometry_metadata["status_limitations"].get(entry["status"], "Geometry status requires review")
    manifest["legs"].append(leg)
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
print(f"Package {package['trip_identity']}: {len(map_assets)} map assets; {routed_count}/{semantic_public_count} cached reference legs, {conceptual_count} conceptual, {len(omissions) + unavailable_count} omitted; {point_count} points")
