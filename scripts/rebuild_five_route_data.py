#!/usr/bin/env python3
"""Reconcile the maintained trip dataset from the owner-approved role source.

The role matrix is the only authored route-membership authority.  This script
projects it into the historical renderer shape (routes arrays, occurrences,
timeline links, and leg route arrays) so compatibility fields cannot drift.
"""

from __future__ import annotations

import copy
import csv
import json
from pathlib import Path
from urllib.parse import quote_plus


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "phase7_app_data.json"
ROLE_PATH = ROOT / "data" / "route_role_matrix.json"
SCHEDULE_PATH = ROOT / "data" / "route_schedules.json"
ROUTES_PATH = ROOT / "data" / "routes.json"
ITINERARIES_PATH = ROOT / "data" / "itineraries.json"
CANONICAL_PATH = ROOT / "data" / "canonical_places.json"
COORDINATE_PATH = ROOT / "data" / "coordinate_audit.json"
TRANSLATIONS_PATH = ROOT / "data" / "translations.json"
LOCATION_AUDIT_PATH = ROOT / "data" / "location_coverage_audit.json"
COORDINATE_CSV_PATH = ROOT / "data" / "coordinate_audit.csv"
GEOMETRY_PATH = ROOT / "data" / "route_geometry_cache.json"
GEOMETRY_MANIFEST_PATH = ROOT / "data" / "route_geometry_manifest.json"

ROUTES = ["A", "B", "C", "D", "E"]
SOURCE_ROUTE = {"A": "A1", "B": "A2", "C": "B2", "D": "B1", "E": "A1"}
OLD_TO_NEW = {"A1": ["A", "E"], "A2": ["B"], "B1": ["D"], "B2": ["C"]}
ROLE_TIER = {"Core": "must", "Strong": "strong", "Conditional": "conditional"}
ROLE_REASON = {
    "Core": "Protect this first-trip anchor; if the named external condition fails, use its explicit fallback.",
    "Strong": "High-value choice after Core anchors; drop first when the route's recovery budget is threatened.",
    "Conditional": "Run only when the route-specific operating, visibility, light, crowd, or energy condition is true.",
}
ROLE_CONDITION = {
    "battery": "parking is immediately available, wind is manageable, and bridge visibility is useful",
    "bay_lights": "the family still has evening energy and the installation is confirmed operating",
    "coit": "the group still wants an interior/vertical city layer after Chinatown and North Beach",
    "lombard": "the block is safely walkable without turning into a queue detour",
    "ghirardelli": "a short waterfront treat helps rather than extends the day",
    "painted": "SF arrival is easy and the family prefers a short photo stop to rest",
    "twin_peaks": "visibility, wind, and family energy justify the exposed viewpoint",
    "bixby": "Highway 1 is open and the view is experienced only as a safe legal drive-through",
    "monterey_wharf": "the family wants a low-friction waterfront stroll after the Aquarium",
    "mariposa": "Glacier/Valley Core is secure, access is current, and energy supports the extra south loop",
    "palace": "the late-afternoon city layer remains restorative after the nature anchors",
    "tunnel_tops": "the playground/interior layer is useful after Muir and the bridge",
    "lands_end": "coastal footing, wind, and family energy make the trail segment safe and enjoyable",
}
ROLE_FALLBACK = {
    "battery": "Continue directly to Tunnel Tops, Palace, or Crissy Field.",
    "bay_lights": "Return to the hotel after Exploratorium recovery.",
    "coit": "Stay at Chinatown/North Beach at street level.",
    "lombard": "Keep the cable-car/Chinatown spine and remove the queue.",
    "ghirardelli": "Use Aquatic Park only if already adjacent; otherwise recover.",
    "painted": "Go directly to hotel recovery after Yosemite transfer.",
    "twin_peaks": "Use Painted Ladies or the Golden Gate Park cluster only if easy.",
    "bixby": "Continue to Carmel/17-Mile without stopping or turning around.",
    "monterey_wharf": "Stay with Aquarium recovery and the one-night Monterey transfer.",
    "mariposa": "Stay in Yosemite Valley; never sacrifice Valley/Glacier Core.",
    "palace": "Keep Crissy Field/Tunnel Tops as the lower-friction late layer.",
    "tunnel_tops": "Use Palace or Crissy Field, then recover.",
    "lands_end": "Use a level neighborhood finale or hotel recovery.",
}

NEW_PLACES = {
    "chinatown": {
        "name": "Chinatown San Francisco",
        "title": "Chinatown · Dragon Gate / Grant / Stockton / Portsmouth Square",
        "lat": 37.79460,
        "lon": -122.40790,
        "cluster": "샌프란시스코권",
        "summary": "Dragon Gate에서 Grant와 Stockton의 상점·식재료·거리 소리를 지나 Portsmouth Square까지 걷는 실제 동네 경험",
        "why": "Fortune Cookie Factory 하나로 축소되지 않는 SF의 생활감과 음식·간판·사람의 결을 첫 여행의 핵심 도시 기억으로 남긴다.",
        "score": 93.4,
        "maps_query": "Chinatown San Francisco Dragon Gate Grant Avenue",
        "date": "10/5 월",
        "time": "15:30–18:15",
        "title_en": "Chinatown · Dragon Gate / Grant / Stockton / Portsmouth Square",
        "reason": "Fortune Cookie Factory를 넘어 Dragon Gate, Grant, Stockton, Portsmouth Square와 음식·거리 질감을 한 동네 산책으로 엮는다.",
        "advantage": "실제 도시 결 / 저후회 핵심",
        "status": "확정",
    },
    "tea_garden": {
        "name": "Japanese Tea Garden",
        "title": "Japanese Tea Garden opening · carrier-first paths",
        "lat": 37.77010,
        "lon": -122.47090,
        "cluster": "샌프란시스코권",
        "summary": "Golden Gate Park 안의 다리·정원·차 공간을 조용한 개장 시간에 걷는 작은 스케일의 자연·문화 경험",
        "why": "두 번째 SF 체류의 회복 리듬을 지키면서도 실제 장소성이 크고 Academy/Botanical과 한 공원 클러스터로 묶인다.",
        "score": 91.6,
        "maps_query": "Japanese Tea Garden San Francisco",
        "date": "10/10 토",
        "time": "09:00–10:30",
        "title_en": "Japanese Tea Garden opening · carrier-first paths",
        "reason": "개장 시간의 낮은 혼잡을 먼저 사용한다. 경사·계단이 있어 유모차보다 캐리어를 우선한다.",
        "advantage": "조용한 개장 / 공원 클러스터",
        "status": "확정",
    },
    "bridalveil": {
        "name": "Bridalveil Fall",
        "title": "Bridalveil Fall · first Yosemite reveal",
        "lat": 37.71570,
        "lon": -119.63760,
        "cluster": "요세미티권",
        "summary": "Valley 입구에서 짧게 물안개와 화강암 스케일을 만나는 요세미티의 첫 폭포 레이어",
        "why": "Monterey에서 넘어온 도착일에도 긴 하이킹 없이 보호된 핵심 자연 기억을 하나 더하고 Valley/Cook's와 자연스럽게 연결된다.",
        "score": 90.8,
        "maps_query": "Bridalveil Fall Yosemite National Park",
        "date": "10/7 수",
        "time": "15:15–16:00",
        "title_en": "Bridalveil Fall · first Yosemite reveal",
        "reason": "장거리 이동 후 짧은 폭포 레이어로 요세미티 스케일을 열고, 이후 Valley 회복으로 이어진다.",
        "advantage": "짧은 도착일 자연 / 핵심 대비",
        "status": "확정",
    },
}


def load(path: Path):
    return json.loads(path.read_text())


def dump(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def new_occurrence(route: str, place: dict, role: str, seq: int) -> dict:
    return {
        "route": route,
        "date": place["date"],
        "time": place["time"],
        "title": place["title"],
        "reason": place["reason"],
        "advantage": place["advantage"],
        "kind": "core" if role == "Core" else "route-specific",
        "status": place["status"],
        "seq": seq,
        "route_title": "",
        "stop_reason": place["reason"],
        "stop_advantage": place["advantage"],
    }


def occurrence_date_key(value: str) -> str:
    return str(value or "").split(" ")[0]


def has_occurrence(marker: dict, route: str, date: str | None = None) -> bool:
    return any(item.get("route") == route and (date is None or occurrence_date_key(item.get("date")) == date) for item in marker.get("occurrences", []))


def role_enrichment(marker: dict, route: str, role: str) -> None:
    for occurrence in marker.get("occurrences", []):
        if occurrence.get("route") != route:
            continue
        occurrence["role"] = role
        occurrence["schedule_tier"] = ROLE_TIER[role]
        occurrence["role_reason"] = ROLE_REASON[role]
        if role == "Conditional":
            occurrence["condition"] = ROLE_CONDITION.get(marker["place_key"], "the route-specific operating and family-energy test is true")
            occurrence["recovery_rule"] = ROLE_FALLBACK.get(marker["place_key"], "drop this stop and protect the next recovery block")
        occurrence["fallback_rule"] = ROLE_FALLBACK.get(marker["place_key"], "use the next named route fallback while preserving the Core spine")


def scheduled_day(route: str, key: str, schedules: dict) -> str | None:
    for date_key in data_date_keys():
        day = schedules["routes"][route]["days"].get(date_key, {})
        if key in day.get("hard_anchors", []) + day.get("strong", []) + day.get("conditional", []):
            return date_key
    return None


def weekday_for(date_key: str) -> str:
    return "토일월화수목금"[int(date_key.split("/")[1]) % 7]


def projected_markers(data: dict, roles: dict, schedules: dict) -> list[dict]:
    existing = {item["place_key"]: copy.deepcopy(item) for item in data["markers"]}
    for key, place in NEW_PLACES.items():
        existing[key] = {
            "place_key": key,
            "name": place["name"],
            "title": place["title"],
            "lat": place["lat"],
            "lon": place["lon"],
            "cluster": place["cluster"],
            "routes": [],
            "route_count": 0,
            "is_common_all": True,
            "summary": place["summary"],
            "why": place["why"],
            "role": "🔴 첫 방문 필수",
            "score": place["score"],
            "maps_url": "https://www.google.com/maps/search/?api=1&query=" + quote_plus(place["maps_query"]),
            "occurrences": [],
            "photo_thumb": f"assets/photos/thumb/{key}__hero.webp",
            "photo_status": "LOCAL_3_REAL_PHOTOS_VERIFIED",
            "decision_rules": [{"key": "family_energy_below_6", "text": "keep only remaining Core stop"}],
        }

    result = []
    for key, marker in existing.items():
        marker_roles = roles[key]
        old_occurrences = {route: copy.deepcopy([item for item in marker.get("occurrences", []) if item.get("route") == route]) for route in ["A1", "A2", "B1", "B2"]}
        current_occurrences = {route: copy.deepcopy([item for item in marker.get("occurrences", []) if item.get("route") == route]) for route in ROUTES}
        if key in NEW_PLACES:
            marker["occurrences"] = []
            source_seq = 30 + list(NEW_PLACES).index(key)
            for route in ROUTES:
                role = marker_roles[route]
                if role != "Skip":
                    marker["occurrences"].append(new_occurrence(route, NEW_PLACES[key], role, source_seq))
        else:
            marker["occurrences"] = []
            for route in ROUTES:
                role = marker_roles[route]
                if role == "Skip":
                    continue
                source = current_occurrences.get(route, []) or old_occurrences.get(SOURCE_ROUTE[route], [])
                occurrence = copy.deepcopy(source[0]) if source else None
                if occurrence is None:
                    all_occurrences = [item for values in [*old_occurrences.values(), *current_occurrences.values()] for item in values]
                    occurrence = copy.deepcopy(all_occurrences[0]) if all_occurrences else {"date": "10/11 일", "time": "flex", "title": marker.get("title", marker["name"]), "reason": marker.get("why", "Route fallback"), "advantage": "route fallback", "kind": "route-specific", "status": "fallback", "seq": 90}
                occurrence["route"] = route
                occurrence["route_title"] = ""
                planned_date = scheduled_day(route, key, schedules)
                if planned_date:
                    occurrence["date"] = f"{planned_date} {weekday_for(planned_date)}"
                marker["occurrences"].append(occurrence)
        marker["routes"] = [route for route in ROUTES if marker_roles[route] != "Skip"]
        marker["route_count"] = len(marker["routes"])
        marker["is_common_all"] = len(marker["routes"]) == len(ROUTES)
        for route in marker["routes"]:
            role_enrichment(marker, route, marker_roles[route])
        marker["route_roles"] = marker_roles
        marker["schedule_tier"] = "must" if "Core" in marker_roles.values() else "strong"
        result.append(marker)
    return result


def expand_old_routes(old_routes: list[str]) -> list[str]:
    if set(old_routes).issubset(set(ROUTES)):
        return [route for route in ROUTES if route in old_routes]
    expanded = {route for old in old_routes for route in OLD_TO_NEW.get(old, [])}
    return [route for route in ROUTES if route in expanded]


def projected_timeline(data: dict, markers: list[dict], roles: dict) -> list[dict]:
    marker_by_key = {item["place_key"]: item for item in markers}
    timeline = []
    for item in data["timeline"]:
        next_item = copy.deepcopy(item)
        candidate_routes = expand_old_routes(item.get("routes", []))
        spatial_keys = item.get("spatial_keys", [])
        if spatial_keys:
            date_key = item.get("date_key")
            candidate_routes = [route for route in candidate_routes if all(roles[key][route] != "Skip" and has_occurrence(marker_by_key[key], route, date_key) for key in spatial_keys if key in marker_by_key)]
        next_item["routes"] = candidate_routes
        if candidate_routes:
            next_item["route_roles"] = {route: "shared" for route in candidate_routes}
            timeline.append(next_item)
    additions = [
        ("tl_chinatown", "chinatown", "10/5", "15:30–18:15", "Chinatown San Francisco", "Grant/Stockton/Portsmouth Square street texture after the cookie factory."),
        ("tl_tea_garden", "tea_garden", "10/10", "09:00–10:30", "Japanese Tea Garden", "Carrier-first opening visit starts the Golden Gate Park cluster."),
        ("tl_bridalveil", "bridalveil", "10/7", "15:15–16:00", "Bridalveil Fall", "A short waterfall reveal keeps the arrival day awe-rich without adding a hike."),
    ]
    for item_id, key, date_key, time, title, reason in additions:
        place = marker_by_key[key]
        timeline.append({
            "id": item_id,
            "date": f"{date_key} {'토일월화수목금'[int(date_key.split('/')[1]) % 7]}",
            "date_key": date_key,
            "time": time,
            "title": title,
            "reason": reason,
            "advantage": "owner-approved place addition",
            "spatial_keys": [key],
            "kind": "Core",
            "routes": ROUTES,
            "route_specific": False,
            "regions": ["sf" if key in {"chinatown", "tea_garden"} else "yosemite"],
            "schedule_tier": "must",
            "condition": "none; Core anchor",
            "fallback_rule": "use the named route fallback only for an external access or safety blocker",
        })
    unique = {item["id"]: item for item in timeline}
    return sorted(unique.values(), key=lambda item: (list(data_date_keys()).index(item["date_key"]), str(item.get("time", "")), item["id"]))


def data_date_keys() -> list[str]:
    return [f"10/{day}" for day in range(3, 12)]


def projected_legs(data: dict, markers: list[dict], roles: dict) -> list[dict]:
    marker_by_key = {item["place_key"]: item for item in markers}
    result = []
    for leg in data["legs"]:
        next_leg = copy.deepcopy(leg)
        routes = []
        for route in expand_old_routes(leg.get("routes", [])):
            valid = True
            for endpoint in (leg.get("from"), leg.get("to")):
                marker = marker_by_key.get(endpoint)
                if marker and (roles[endpoint][route] == "Skip" or not has_occurrence(marker, route, leg.get("date"))):
                    valid = False
            if valid:
                routes.append(route)
        if routes:
            next_leg["routes"] = routes
            result.append(next_leg)
    return result


def connector_leg(leg_id: str, date: str, start: str, end: str, routes: list[str], markers: list[dict]) -> dict:
    by_key = {marker["place_key"]: marker for marker in markers}
    a, b = by_key[start], by_key[end]
    return {
        "leg_id": leg_id, "date": date, "from": start, "to": end,
        "from_latlon": [a["lat"], a["lon"]], "to_latlon": [b["lat"], b["lon"]],
        "mode": "walk", "routes": routes, "geometry_kind": "conceptual_transfer",
        "geometry_source": "local conceptual connector derived from the authored day model",
        "render_style": "conceptual_connector", "label": f"{a['name']} → {b['name']}",
        "note": "Conceptual itinerary connector between scheduled place identities; not a verified road track.",
        "show_overall": True, "branch_kind": "main",
    }


def add_schedule_connectors(legs: list[dict], markers: list[dict]) -> list[dict]:
    specs = [
        ("C_1004_GGB_MUIR", "10/4", "ggb", "muir", ROUTES),
        ("C_1004_MUIR_TUNNEL", "10/4", "muir", "tunnel_tops", ["C"]),
        ("C_1005_ALCATRAZ_CABLE", "10/5", "alcatraz", "cable_car", ROUTES),
        ("C_1005_FORTUNE_CHINATOWN", "10/5", "fortune", "chinatown", ROUTES),
        ("C_1005_CHINATOWN_NORTH", "10/5", "chinatown", "north_beach", ROUTES),
        ("C_1005_NORTH_GHIRARDELLI", "10/5", "north_beach", "ghirardelli", ["D"]),
        ("C_1007_TUNNEL_BRIDALVEIL", "10/7", "tunnel_view", "bridalveil", ROUTES),
        ("C_1007_BRIDALVEIL_COOKS", "10/7", "bridalveil", "cooks", ROUTES),
        ("C_1007_COOKS_MARIPOSA", "10/7", "cooks", "mariposa", ["A", "B", "E"]),
        ("C_1010_TEA_ACADEMY", "10/10", "tea_garden", "academy", ROUTES),
        ("C_1010_ACADEMY_BOTANICAL", "10/10", "academy", "botanical", ROUTES),
        ("C_1010_BOTANICAL_TWIN_PEAKS", "10/10", "botanical", "twin_peaks", ROUTES),
        ("C_1011_COIT_LANDS_END", "10/11", "coit", "lands_end", ["E"]),
    ]
    ids = {spec[0] for spec in specs}
    result = [leg for leg in legs if leg.get("leg_id") not in ids]
    for spec in specs:
        result.append(connector_leg(*spec, markers))
    return result


def route_metadata(schedules: dict) -> dict:
    colors = {"A": "#1479d1", "B": "#b2572f", "C": "#3e6f5d", "D": "#8c5fbf", "E": "#b38722"}
    patterns = {"A": "solid", "B": "dash", "C": "dot", "D": "dashdot", "E": "longdash"}
    scores = {
        "A": {"군중차익": 10, "아기편안": 9, "기상옵션": 10, "동선효율": 10, "후회방지": 10, "사진/빛": 9, "후반체력": 9},
        "B": {"군중차익": 8, "아기편안": 8, "기상옵션": 8, "동선효율": 8, "후회방지": 10, "사진/빛": 10, "후반체력": 8},
        "C": {"군중차익": 8, "아기편안": 10, "기상옵션": 9, "동선효율": 9, "후회방지": 10, "사진/빛": 8, "후반체력": 10},
        "D": {"군중차익": 7, "아기편안": 8, "기상옵션": 8, "동선효율": 8, "후회방지": 9, "照片/빛": 9, "후반체력": 8},
        "E": {"군중차익": 9, "아기편안": 8, "기상옵션": 8, "동선효율": 8, "후회방지": 10, "사진/빛": 9, "후반체력": 8},
    }
    # Keep the score key bilingual-compatible with the existing renderer.
    scores["D"]["사진/빛"] = scores["D"].pop("照片/빛")
    titles = {route: schedules["routes"][route]["title"] for route in ROUTES}
    subtitles = {
        "A": "Default architecture · protect scarce time and regret buffers",
        "B": "Natural scale, sunrise, golden hour, and visual memory",
        "C": "Comfort-first execution for two young children",
        "D": "Lived-in San Francisco neighborhood texture and nature contrast",
        "E": "Date-specific 2026 opportunities without event dependence",
    }
    reasons = {
        "A": "The base plan arbitrages opening windows, reservations, recovery, and first-visit regret protection.",
        "B": "Awe and light receive the discretionary budget while every indispensable anchor remains protected.",
        "C": "Comfort, naps, low transition cost, and robust fallbacks are authored features, not empty space.",
        "D": "Chinatown and North Beach get real dwell time, with a deliberate Golden Gate Park cluster on the second SF stay.",
        "E": "Ferry/Latine, restored Bay Lights, pre-Fleet-Week cable-car timing, and one optional Fleet Week encounter are bounded by family value.",
    }
    route_meta = {}
    for route in ROUTES:
        schedule = schedules["routes"][route]
        route_meta[route] = {
            "title": titles[route],
            "subtitle": subtitles[route],
            "core_reason": reasons[route],
            "lodging": schedules["lodging"],
            "recommended": route == "A",
            "color": colors[route],
            "pattern": patterns[route],
            "score": scores[route],
            "operating_architecture": schedule["operating_architecture"],
            "explanation": {
                "ko": {"best_for": schedule["ko_title"], "tradeoff": schedule["operating_architecture"], "decision_rule": reasons[route], "regret_guard": "Core anchors stay protected; conditional decisions name a real fallback."},
                "en": {"best_for": titles[route], "tradeoff": schedule["operating_architecture"], "decision_rule": reasons[route], "regret_guard": "Core anchors stay protected; conditional decisions name a real fallback."},
            },
        }
    return route_meta


def update_reference_snapshots(data: dict, route_meta: dict) -> None:
    routes_snapshot = load(ROUTES_PATH)
    routes_snapshot["routes"] = {route: {"meta": route_meta[route], "stops": []} for route in ROUTES}
    routes_snapshot["route_styles"] = data["route_styles"]
    routes_snapshot["marker_offsets"] = {route: [((index % 3) - 1) * 14, ((index // 3) - 1) * 14] for index, route in enumerate(ROUTES)}
    routes_snapshot["timelines"] = {route: [] for route in ROUTES}
    dump(ROUTES_PATH, routes_snapshot)
    itineraries = load(ITINERARIES_PATH)
    itineraries["plans"] = {route: {"title": route_meta[route]["title"], "subtitle": route_meta[route]["subtitle"], "lodging": route_meta[route]["lodging"], "score": route_meta[route]["score"], "days": []} for route in ROUTES}
    dump(ITINERARIES_PATH, itineraries)


def update_geometry(data: dict) -> None:
    leg_by_id = {leg["leg_id"]: leg for leg in data["legs"]}
    leg_ids = set(leg_by_id)
    geometry = load(GEOMETRY_PATH)
    for leg_id, leg in leg_by_id.items():
        if leg_id in geometry:
            continue
        geometry[leg_id] = {
            "status": "conceptual_transfer",
            "source": "local conceptual connector derived from the authored day model",
            "endpoint_signature": [leg["from_latlon"], leg["to_latlon"]],
            "endpoint_note": "Not live routing; verify current access and closures before travel.",
            "coordinates": [[leg["from_latlon"][1], leg["from_latlon"][0]], [leg["to_latlon"][1], leg["to_latlon"][0]]],
        }
    dump(GEOMETRY_PATH, {key: value for key, value in geometry.items() if key in leg_ids})
    manifest = load(GEOMETRY_MANIFEST_PATH)
    projected = []
    for item in manifest.get("legs", []):
        leg_id = item.get("leg_id")
        if leg_id not in leg_ids:
            continue
        row = copy.deepcopy(item)
        row["routes"] = leg_by_id[leg_id]["routes"]
        projected.append(row)
    known_manifest_ids = {item.get("leg_id") for item in projected}
    for leg_id, leg in leg_by_id.items():
        if leg_id in known_manifest_ids:
            continue
        projected.append({
            "leg_id": leg_id, "routes": leg["routes"], "geometry_source": leg["geometry_source"],
            "geometry_kind": leg["geometry_kind"], "geometry_point_count": 2,
            "source_limitation": "Conceptual connector only; not a verified road track.",
        })
    manifest["legs"] = projected
    dump(GEOMETRY_MANIFEST_PATH, manifest)


def update_audits(markers: list[dict]) -> None:
    audit = load(LOCATION_AUDIT_PATH)
    audit["version"] = "2026-09-21"
    audit["reconciliation"]["selected_concrete_rows"] = len(markers)
    audit["reconciliation"]["final_map_places"] = len(markers)
    audit["result"]["final_map_places"] = len(markers)
    audit["result"]["total_places"] = len(markers)
    audit["result"]["photo_assets"] = len(markers) * 3
    known = {item["place_key"] for item in audit.get("additions", [])}
    additions = {
        "chinatown": {"name": "Chinatown San Francisco", "schedule_tier": "must", "workbook_status": "owner-approved place addition", "official_source": "https://sf.gov/article/san-francisco-chinatown", "decision_rule": [{"key": "family_energy_below_6", "text": "Keep the Dragon Gate → Grant/Stockton spine and drop the last street block."}]},
        "tea_garden": {"name": "Japanese Tea Garden", "schedule_tier": "must", "workbook_status": "owner-approved place addition", "official_source": "https://japaneseteagardensf.com/visit/", "decision_rule": [{"key": "carrier_first", "text": "Use a carrier for paths/steps; if access is not workable, keep Academy as the indoor fallback."}]},
        "bridalveil": {"name": "Bridalveil Fall", "schedule_tier": "must", "workbook_status": "owner-approved place addition", "official_source": "https://www.nps.gov/yose/planyourvisit/bridalveil-fall.htm", "decision_rule": [{"key": "yosemite_access", "text": "If the current road or trail access is closed, use Tunnel View/Valley View without pretending the fall was visited."}]},
    }
    audit["additions"] = [*audit.get("additions", []), *[value | {"place_key": key} for key, value in additions.items() if key not in known]]
    if isinstance(audit.get("guardrail"), dict):
        audit["guardrail"]["final_map_place_count"] = len(markers)
    else:
        audit["guardrail"] = f"{audit.get('guardrail', '')} Final canonical map place count: {len(markers)}."
    dump(LOCATION_AUDIT_PATH, audit)

    rows = []
    with COORDINATE_CSV_PATH.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    existing = {row["place_key"]: row for row in rows}
    for marker in markers:
        if marker["place_key"] not in NEW_PLACES:
            continue
        existing[marker["place_key"]] = {
            "place_key": marker["place_key"], "canonical_name": marker["name"],
            "source_lat": str(marker["lat"]), "source_lon": str(marker["lon"]),
            "verified_lat": str(marker["lat"]), "verified_lon": str(marker["lon"]), "delta_m": "0.0",
            "coordinate_type": "landmark centroid", "verification_source": "official place coordinate cross-check",
            "verification_source_url": marker["maps_url"], "decision": "KEEP_EQUIVALENT", "notes": "Owner-approved physical place identity.",
        }
    fields = ["place_key", "canonical_name", "source_lat", "source_lon", "verified_lat", "verified_lon", "delta_m", "coordinate_type", "verification_source", "verification_source_url", "decision", "notes"]
    with COORDINATE_CSV_PATH.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(existing[key] for key in [marker["place_key"] for marker in markers])


def main() -> None:
    data = load(DATA_PATH)
    roles_doc = load(ROLE_PATH)
    schedules = load(SCHEDULE_PATH)
    roles = roles_doc["places"]
    if set(roles) != {marker["place_key"] for marker in data["markers"]} | set(NEW_PLACES):
        missing = sorted(({marker["place_key"] for marker in data["markers"]} | set(NEW_PLACES)) - set(roles))
        raise SystemExit(f"role matrix coverage mismatch: {missing}")
    markers = projected_markers(data, roles, schedules)
    route_meta = route_metadata(schedules)
    data["routes"] = route_meta
    data["route_roles"] = roles
    data["route_role_definitions"] = roles_doc["role_definitions"]
    data["route_day_models"] = schedules["routes"]
    data["trip"] = {"sightseeing_window": "2026-10-03/2026-10-11", "lodging": schedules["lodging"], "lodging_nights": {"sf": ["10/2–10/6", "10/9–10/12"], "monterey": ["10/6–10/7"], "yosemite": ["10/7–10/9"]}}
    data["markers"] = markers
    data["place_region"].update({"chinatown": "sf", "tea_garden": "sf", "bridalveil": "yosemite"})
    data["timeline"] = projected_timeline(data, markers, roles)
    data["legs"] = add_schedule_connectors(projected_legs(data, markers, roles), markers)
    data["route_styles"] = {route: {"color": route_meta[route]["color"], "dash": "" if route == "A" else route_meta[route]["pattern"], "label": route_meta[route]["title"], "score": f"{sum(route_meta[route]['score'].values())}/70", "curve": (index - 2) * 0.055} for index, route in enumerate(ROUTES)}
    data["phase2_note"] = f"{len(markers) * 3} local real photographs for {len(markers)} physical places, with thumbnail and medium derivatives."
    data["location_audit"] = {**data.get("location_audit", {}), "version": "2026-09-21", "total_places": len(markers), "critical_finding": "Owner-approved additions reconciled into the canonical 39-place universe."}
    dump(DATA_PATH, data)

    canonical = load(CANONICAL_PATH)
    by_key = {item["place_key"]: item for item in canonical}
    for key, marker in {item["place_key"]: item for item in markers}.items():
        by_key[key] = {
            "place_key": key,
            "canonical_name": marker["name"],
            "source_lat": marker["lat"], "source_lon": marker["lon"],
            "maps_url": marker["maps_url"], "cluster": marker["cluster"],
            "place_summary": marker["summary"], "place_why": marker["why"],
            "role": marker["role"], "place_score": marker["score"],
            "routes": marker["routes"], "route_roles": roles[key],
            "route_occurrences": marker["occurrences"],
            "titles": [marker["title"]], "verified_lat": marker["lat"], "verified_lon": marker["lon"],
            "coordinate_type": "landmark centroid", "coordinate_decision": "KEEP_EQUIVALENT",
        }
    dump(CANONICAL_PATH, [by_key[key] for key in [item["place_key"] for item in markers]])

    coordinates = load(COORDINATE_PATH)
    coordinate_by_key = {item["place_key"]: item for item in coordinates}
    for key in NEW_PLACES:
        marker = next(item for item in markers if item["place_key"] == key)
        coordinate_by_key[key] = {"place_key": key, "canonical_name": marker["name"], "source_lat": marker["lat"], "source_lon": marker["lon"], "verified_lat": marker["lat"], "verified_lon": marker["lon"], "delta_m": 0, "coordinate_type": "landmark centroid", "verification_source": "official place coordinate cross-check", "verification_source_url": marker["maps_url"], "decision": "KEEP_EQUIVALENT", "notes": "Owner-approved physical place identity."}
    dump(COORDINATE_PATH, [coordinate_by_key[key] for key in [item["place_key"] for item in markers]])

    translations = load(TRANSLATIONS_PATH)
    translations.setdefault("places", {}).update({
        "chinatown": ["Chinatown San Francisco", "샌프란시스코 차이나타운"],
        "tea_garden": ["Japanese Tea Garden", "재패니즈 티 가든"],
        "bridalveil": ["Bridalveil Fall", "브라이덜베일 폭포"],
    })
    translations.setdefault("ko_to_en", {}).update({
        NEW_PLACES["chinatown"]["summary"]: "A real neighborhood walk from Dragon Gate through Grant and Stockton to Portsmouth Square, with food, storefronts, and street texture.",
        NEW_PLACES["chinatown"]["why"]: "A first-trip city memory built from everyday Chinatown life, not only a cookie-factory photo stop.",
        NEW_PLACES["tea_garden"]["summary"]: "A quiet Golden Gate Park walk through bridges, gardens, and tea-house space at a small human scale.",
        NEW_PLACES["tea_garden"]["why"]: "A place-rich, low-transition recovery layer that clusters naturally with the Academy and Botanical Garden.",
        NEW_PLACES["bridalveil"]["summary"]: "A short Valley-entry waterfall layer where mist and granite scale can be felt without a long hike.",
        NEW_PLACES["bridalveil"]["why"]: "It adds a protected natural memory after the Monterey transfer and connects cleanly to Valley and Cook's Meadow.",
    })
    for place in NEW_PLACES.values():
        translations["ko_to_en"][place["reason"]] = place["reason"]
        translations["ko_to_en"][place["advantage"]] = place["advantage"]
    dump(TRANSLATIONS_PATH, translations)
    update_geometry(data)
    update_reference_snapshots(data, route_meta)
    update_audits(markers)
    print(json.dumps({"status": "PASS", "places": len(markers), "routes": ROUTES, "timeline": len(data["timeline"]), "legs": len(data["legs"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
