"""Cache build-time public OSM car/foot reference geometry; never route at runtime."""

from __future__ import annotations

import json
import math
import subprocess
import time
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data/phase7_app_data.json"
CACHE_PATH = ROOT / "data/route_geometry_cache.json"
HISTORICAL_REVISION = "db86b0f22c13b96a86d74a710abbb13dc354ff4b"
data = json.loads(DATA_PATH.read_text())
cache = json.loads(CACHE_PATH.read_text()) if CACHE_PATH.exists() else {}
marker_by_key = {marker["place_key"]: marker for marker in data.get("markers", [])}
public_endpoint_keys = set(marker_by_key) | set(data.get("endpoint_anchors", {}))
valid_ids = {leg["leg_id"] for leg in data.get("legs", [])}
cache = {key: value for key, value in cache.items() if key in valid_ids}


def distance_km(a: list[float], b: list[float]) -> float:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    delta_lat, delta_lon = lat2 - lat1, lon2 - lon1
    arc = 2 * math.asin(math.sqrt(math.sin(delta_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2))
    return 6371 * arc


def plausible(leg: dict, entry: dict) -> bool:
    coordinates = entry.get("coordinates", [])
    if len(coordinates) <= 2:
        return False
    start_gap = distance_km([coordinates[0][1], coordinates[0][0]], leg["from_latlon"])
    end_gap = distance_km([coordinates[-1][1], coordinates[-1][0]], leg["to_latlon"])
    straight = distance_km(leg["from_latlon"], leg["to_latlon"])
    maximum = max(2.5 if leg["mode"] == "walk" else 4.0, straight * (5 if leg["mode"] == "walk" else 4.5))
    endpoint_snap_limit = 0.2 if leg["mode"] == "walk" else 0.65
    return (
        entry.get("mode") == leg["mode"]
        and start_gap <= endpoint_snap_limit
        and end_gap <= endpoint_snap_limit
        and isinstance(entry.get("distance_km"), (int, float))
        and straight * 0.9 <= entry["distance_km"] <= maximum
        and isinstance(entry.get("duration_min_reference"), (int, float))
    )


def historical_cache() -> dict:
    try:
        raw = subprocess.check_output(["git", "show", f"{HISTORICAL_REVISION}:data/route_geometry_cache.json"], cwd=ROOT)
        return json.loads(raw)
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        return {}


old_entries = historical_cache().values()
old_by_signature = {}
for item in old_entries:
    signature = item.get("endpoint_signature")
    if item.get("status") == "routed_osm" and isinstance(signature, list):
        old_by_signature.setdefault(json.dumps(signature, separators=(",", ":")), []).append(item)


for leg in data.get("legs", []):
    leg_id, mode = leg["leg_id"], leg["mode"]
    signature = [leg["from_latlon"], leg["to_latlon"], mode]
    current = cache.get(leg_id)
    network_attempted = False

    if mode == "ferry":
        entry = {
            "status": "conceptual_ferry",
            "coordinates": [[leg["from_latlon"][1], leg["from_latlon"][0]], [leg["to_latlon"][1], leg["to_latlon"][0]]],
            "mode": mode,
            "endpoint_signature": signature,
            "source": "Conceptual ferry relation between public Pier 33 and Alcatraz endpoints",
            "endpoint_note": "Direct public-endpoint relationship only; no vessel track is claimed.",
        }
    elif mode in {"drive", "walk"}:
        if leg.get("from") not in public_endpoint_keys or leg.get("to") not in public_endpoint_keys:
            raise SystemExit(f"Refusing to route {leg_id}: physical route endpoints must be explicitly public map endpoints.")
        if current and current.get("endpoint_signature") == signature and current.get("status") == "routed_osm" and plausible(leg, current):
            entry = current
        else:
            old = next((item for item in old_by_signature.get(json.dumps(signature, separators=(",", ":")), []) if plausible(leg, item)), None)
            if old:
                entry = {
                    "status": "routed_osm",
                    "coordinates": old["coordinates"],
                    "distance_km": old["distance_km"],
                    "duration_min_reference": old["duration_min_reference"],
                    "mode": mode,
                    "endpoint_signature": signature,
                    "source": f"OpenStreetMap {('car' if mode == 'drive' else 'foot')} reference geometry; exact endpoint/mode cache reuse",
                    "source_revision": HISTORICAL_REVISION,
                    "endpoint_note": "Historical network geometry reused only for the exact public endpoint signature and mode; not live closure or traffic advice.",
                }
            else:
                network_attempted = True
                profile = "car" if mode == "drive" else "foot"
                a, b = leg["from_latlon"], leg["to_latlon"]
                coordinates = f"{a[1]},{a[0]};{b[1]},{b[0]}"
                request_url = f"https://routing.openstreetmap.de/routed-{profile}/route/v1/driving/{quote(coordinates, safe=',;.-')}?overview=full&geometries=geojson&steps=false"
                try:
                    request = Request(request_url, headers={"User-Agent": "SmartMinorityFamilyTrip/1.0 (personal offline geometry cache)"})
                    with urlopen(request, timeout=30) as response:
                        payload = json.load(response)
                    route = payload["routes"][0]
                    candidate = {
                        "status": "routed_osm",
                        "coordinates": route["geometry"]["coordinates"],
                        "distance_km": round(route["distance"] / 1000, 2),
                        "duration_min_reference": round(route["duration"] / 60, 1),
                        "mode": mode,
                        "endpoint_signature": signature,
                        "source": f"OpenStreetMap routed-{profile} reference geometry",
                        "source_url": f"https://routing.openstreetmap.de/routed-{profile}",
                        "endpoint_note": "OSM network-following reference, not live closure or traffic advice.",
                    }
                    if not plausible(leg, candidate):
                        raise ValueError("route failed endpoint, point-count, or distance plausibility checks")
                    entry = candidate
                except Exception as error:  # Network failures produce no drawable geometry.
                    entry = {
                        "status": "intentionally_omitted",
                        "coordinates": [],
                        "mode": mode,
                        "endpoint_signature": signature,
                        "source": f"OpenStreetMap routed-{profile} build-time routing attempt",
                        "source_url": f"https://routing.openstreetmap.de/routed-{profile}",
                        "omission_reason": "route_unavailable_or_implausible",
                        "failure_class": type(error).__name__,
                    }
    else:
        raise SystemExit(f"Refusing unsupported route mode for {leg_id}.")

    cache[leg_id] = entry
    leg["geometry_kind"] = entry["status"]
    leg["geometry_source"] = entry["source"]
    leg["render_style"] = {
        "routed_osm": "cached_osm_reference_line",
        "conceptual_ferry": "conceptual_ferry_dots",
        "intentionally_omitted": "omitted",
    }[entry["status"]]
    if entry["status"] == "intentionally_omitted":
        leg["source_limitation"] = "No truthful network-following geometry was available; line intentionally omitted."
    elif entry["status"] == "routed_osm":
        leg["source_limitation"] = "Cached OSM network reference; not live traffic or current closure advice."
    else:
        leg["source_limitation"] = "Conceptual ferry relation only; not a surveyed vessel track."
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n")
    print(leg_id, entry["status"], len(entry.get("coordinates", [])), flush=True)
    if network_attempted:
        time.sleep(0.6)

DATA_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
