"""Record exact local map binaries and the cached routing provenance."""

import hashlib
import json
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


vector = ROOT / "assets/vector/sf_trip.pmtiles"
map_assets = [vector, ROOT / "assets/vector/yosemite_hillshade_source.png", ROOT / "assets/vector/yosemite_hillshade_shadow.webp", *sorted((ROOT / "assets/vector/fonts").rglob("*.pbf")), *sorted((ROOT / "assets/vector/sprites").glob("*"))]
basemap = {
    "version": "map-first-1.0", "generated": str(date.today()),
    "default": "vector", "fallback": None,
    "vector_source": {
        "label": "Local Protomaps vector basemap from OpenStreetMap data",
        "source_build": "https://build.protomaps.com/20260912.pmtiles",
        "extraction_bbox_lonlat": [-123.05, 36.15, -119.20, 38.35],
        "max_source_zoom": 14, "render_engine": "MapLibre GL JS (direct)",
        "online_api_key_required": False,
        "license_attribution": "© OpenStreetMap contributors · Protomaps",
        "standalone_loading": "Embedded PMTiles FileSource and bundled glyph/sprite protocols",
        "modular_loading": "Local HTTP Range requests; use scripts/serve_map.py",
    },
    "yosemite_relief": {
        "source": "https://basemap.nationalmap.gov/arcgis/rest/services/USGSShadedReliefOnly/MapServer",
        "provider": "USGS The National Map 3DEP shaded relief",
        "bbox_lonlat": [-119.99, 37.38, -119.35, 37.95],
        "source_path": "assets/vector/yosemite_hillshade_source.png",
        "render_derivative_path": "assets/vector/yosemite_hillshade_shadow.webp",
        "role": "transparent terrain shadows beneath locally rendered vector roads and labels",
    },
    "assets": [{"path": str(path.relative_to(ROOT)), "bytes": path.stat().st_size, "sha256": digest(path)} for path in map_assets],
    "provider_failure_domains": {
        "vector": "local PMTiles, fonts, sprites",
        "satellite": "Esri World Imagery live tiles, local vector labels",
    },
    "user_selectable_providers": ["vector", "satellite"],
    "internal_emergency_fallback": None,
    "retired_user_choices": ["light", "osm"],
    "policy_notes": ["Public OpenStreetMap tile.openstreetmap.org is never used for offline bulk downloads.", "Google tiles are not copied or embedded."],
}
(ROOT / "manifests/map_first_basemap_manifest.json").write_text(json.dumps(basemap, ensure_ascii=False, indent=2) + "\n")
(ROOT / "manifests/basemap_provider_manifest.json").write_text(json.dumps({
    "vector": {
        "label": "Smart map",
        "kind": "local Protomaps vector extract with bundled labels and Yosemite relief",
        "network_required": False,
        "attribution": "© OpenStreetMap contributors · Protomaps; Yosemite relief: USGS The National Map 3DEP",
        "fallback": "none; Smart map remains the selected renderer and exposes a load error instead of silently changing map type",
    },
    "satellite": {
        "label": "Satellite + labels",
        "kind": "Esri World Imagery with bundled local vector labels",
        "network_required": True,
        "health_probe": "service tile plus selected viewport tile; viewport monitored after switch",
        "failure_behavior": "automatic return to Smart map",
        "attribution": "Tiles © Esri and contributors; labels © OpenStreetMap contributors · Protomaps",
    },
    "user_selectable_provider_count": 2,
    "removed_user_choices": ["USGS topo", "Live OSM"],
}, ensure_ascii=False, indent=2) + "\n")

manifest_path = ROOT / "data/route_geometry_manifest.json"
manifest = json.loads(manifest_path.read_text())
cache = json.loads((ROOT / "data/route_geometry_cache.json").read_text())
app_data = json.loads((ROOT / "data/phase7_app_data.json").read_text())
legs = app_data.get("legs", [])
exact_count = sum(entry.get("status") == "routed_osm" and entry.get("mode") in {"drive", "walk"} for entry in cache.values())
conceptual_ferry_count = sum(entry.get("status") == "conceptual_ferry" for entry in cache.values())
conceptual_relationship_count = sum(entry.get("status") in {"conceptual_ferry", "conceptual_transfer", "conceptual_connector"} for entry in cache.values())
unavailable_count = sum(entry.get("status") == "intentionally_omitted" for entry in cache.values())
semantic_public_count = sum(leg.get("mode") in {"drive", "walk"} for leg in legs)
point_count = sum(len(entry.get("coordinates", [])) for entry in cache.values())
omissions = app_data.get("route_graph_omissions", [])
manifest.update({
    "version": "2.0-map-first", "generated": str(date.today()),
    "routing_service_status": "OSM_REFERENCE_GEOMETRY_WITH_EXPLICIT_OMISSIONS",
    "acceptance_strategy": f"{exact_count}/{semantic_public_count} semantic public car/walk legs have cached network-following OSM geometry; {conceptual_ferry_count} ferry relationships remain endpoint-only; {len(omissions) + unavailable_count} connections are intentionally omitted. App runtime performs no routing requests.",
    "exact_routed_legs": exact_count,
    "semantic_public_route_legs": semantic_public_count,
    "routed_public_legs": exact_count,
    "conceptual_legs": conceptual_relationship_count,
    "conceptual_ferry_legs": conceptual_ferry_count,
    "conceptual_relationship_legs": conceptual_relationship_count,
    "unavailable_physical_legs": unavailable_count,
    "intentionally_omitted_connections": len(omissions),
    "total_geometry_point_count": point_count,
    "renderable_conceptual_legs": conceptual_ferry_count,
    "counts": {
        "semantic_public_route_legs": semantic_public_count,
        "routed_public_legs": exact_count,
        "conceptual_legs": conceptual_relationship_count,
        "conceptual_ferry_legs": conceptual_ferry_count,
        "intentionally_omitted_legs": len(omissions) + unavailable_count,
        "unavailable_physical_legs": unavailable_count,
        "total_geometry_points": point_count,
    },
    "display_policy": "Physical public car/walk lines render only from routed_osm geometry with matching endpoint signature and mode. Unavailable lines and semantic break connections are intentionally omitted. Ferry relationships remain conceptual endpoint links. App runtime performs no routing requests.",
    "geometry_cache_path": "data/route_geometry_cache.json",
    "geometry_cache_sha256": digest(ROOT / "data/route_geometry_cache.json"),
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
    leg["geometry_source"] = entry["source"]
    leg["geometry_point_count"] = len(entry.get("coordinates", []))
    leg["point_count"] = len(entry.get("coordinates", []))
    leg["status"] = entry["status"]
    leg["mode"] = entry.get("mode")
    leg["endpoint_signature"] = entry.get("endpoint_signature")
    leg["distance_km"] = entry.get("distance_km")
    leg["reference_duration_min"] = entry.get("duration_min_reference")
    leg["source"] = entry.get("source")
    leg["render_style"] = source_leg.get("render_style")
    leg["source_limitation"] = {
        "routed_osm": "Cached OSM network reference; not live closure or traffic advice",
        "conceptual_ferry": "Conceptual public ferry relationship, not a surveyed vessel track",
        "intentionally_omitted": "No truthful network-following geometry was available; the map line is omitted",
    }.get(entry["status"], "Geometry status requires review")
    manifest["legs"].append(leg)
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
print(f"Basemap assets: {len(map_assets)}; route geometry: {exact_count}/{semantic_public_count} routed public legs, {conceptual_ferry_count} conceptual ferry, {len(omissions) + unavailable_count} omitted connections, {point_count} points")
