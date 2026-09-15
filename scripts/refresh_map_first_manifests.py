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
exact_count = sum(entry["status"] == "routed_osm" for entry in cache.values())
conceptual_count = sum(entry["status"] != "routed_osm" for entry in cache.values())
manifest.update({
    "version": "2.0-map-first", "generated": str(date.today()),
    "routing_service_status": "OSM_REFERENCE_GEOMETRY_CACHED_LOCALLY",
    "acceptance_strategy": f"{exact_count} car/walk legs use cached OSM network geometry; {conceptual_count} ferry legs remain explicit conceptual water links. App runtime performs no routing requests.",
    "exact_routed_legs": exact_count,
    "conceptual_legs": conceptual_count,
    "renderable_conceptual_legs": conceptual_count,
    "display_policy": "Day and active-route membership gate every leg. Every route remains visible from zoom 0–24. Main lines are solid; swap, conditional, bonus, recovery-gap, and choice links retain route colors with distinct matching casing/dash patterns. Ferry links are explicitly conceptual.",
    "geometry_cache_path": "data/route_geometry_cache.json",
    "geometry_cache_sha256": digest(ROOT / "data/route_geometry_cache.json"),
})
manifest["legs"] = []
for source_leg in app_data["legs"]:
    leg = dict(source_leg)
    entry = cache[leg["leg_id"]]
    leg["geometry_kind"] = entry["status"]
    leg["geometry_source"] = entry["source"]
    leg["geometry_point_count"] = len(entry["coordinates"])
    leg["distance_km"] = entry.get("distance_km")
    leg["reference_duration_min"] = entry.get("duration_min_reference")
    leg["render_style"] = "conceptual_ferry_dots" if entry["status"] == "conceptual_ferry" else "cached_osm_reference_line"
    leg["source_limitation"] = "Reference OSM routing, not live closure/traffic advice" if entry["status"] == "routed_osm" else "Direct ferry relationship, not a surveyed boat track"
    manifest["legs"].append(leg)
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
print(f"Basemap assets: {len(map_assets)}; route geometry: {manifest['exact_routed_legs']} cached car/walk, {manifest['conceptual_legs']} conceptual ferry")
