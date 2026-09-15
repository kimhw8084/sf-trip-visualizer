"""Cache one-time OSM-based car/foot routes; never query routing at app runtime."""

import json
import math
import time
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
data = json.loads((ROOT / "data/phase7_app_data.json").read_text())
output = ROOT / "data/route_geometry_cache.json"
existing = json.loads(output.read_text()) if output.exists() else {}
valid_leg_ids = {leg["leg_id"] for leg in data["legs"]}
existing = {key: value for key, value in existing.items() if key in valid_leg_ids}


def km_between(a, b):
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    delta = lat2 - lat1
    c = 2 * math.asin(math.sqrt(math.sin(delta / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2))
    return 6371 * c


for leg in data["legs"]:
    key = leg["leg_id"]
    endpoint_signature = [leg["from_latlon"], leg["to_latlon"], leg["mode"]]
    if key in existing and existing[key].get("endpoint_signature") == endpoint_signature and existing[key].get("status") != "conceptual_fallback":
        continue
    if leg["mode"] == "ferry":
        existing[key] = {"status": "conceptual_ferry", "coordinates": [list(reversed(leg["from_latlon"])), list(reversed(leg["to_latlon"]))], "source": "authoritative dock/island endpoints", "mode": "ferry", "endpoint_signature": endpoint_signature}
        continue
    profile = "foot" if leg["mode"] == "walk" else "car"
    a, b = leg["from_latlon"], leg["to_latlon"]
    coords = f"{a[1]},{a[0]};{b[1]},{b[0]}"
    url = f"https://routing.openstreetmap.de/routed-{profile}/route/v1/driving/{quote(coords, safe=',;.-')}?overview=full&geometries=geojson&steps=false"
    try:
        request = Request(url, headers={"User-Agent": "SmartMinorityFamilyTrip/1.0 (personal offline geometry cache)"})
        with urlopen(request, timeout=30) as response:
            payload = json.load(response)
        route = payload["routes"][0]
        points = route["geometry"]["coordinates"]
        distance_km = route["distance"] / 1000
        straight_km = km_between(a, b)
        if len(points) < 2 or distance_km > leg.get("max_route_km", max(6, straight_km * 9)):
            raise ValueError(f"implausible route {distance_km:.1f} km vs {straight_km:.1f} km straight")
        existing[key] = {
            "status": "routed_osm", "coordinates": points, "distance_km": round(distance_km, 2),
            "duration_min_reference": round(route["duration"] / 60, 1), "mode": leg["mode"],
            "endpoint_signature": endpoint_signature,
            "source": url, "endpoint_note": "OSRM snapped itinerary coordinates to its current OSM network; verify live closures separately",
        }
    except Exception as exc:
        existing[key] = {"status": "conceptual_fallback", "coordinates": [list(reversed(a)), list(reversed(b))], "mode": leg["mode"], "source": url, "error": str(exc), "endpoint_signature": endpoint_signature}
    output.write_text(json.dumps(existing, ensure_ascii=False, indent=2) + "\n")
    print(key, existing[key]["status"], existing[key].get("distance_km", ""), flush=True)
    time.sleep(0.6)

output.write_text(json.dumps(existing, ensure_ascii=False, indent=2) + "\n")
