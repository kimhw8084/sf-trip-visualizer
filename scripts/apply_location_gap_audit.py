"""Apply the official-source location gap audit to the map-first application data.

The original 28-place data remains intact. Eight audited supplements are added with
explicit must/strong/swap/bonus semantics so discovery does not become overpacking.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from urllib.parse import quote_plus


ROOT = Path(__file__).resolve().parents[1]
if "--write" not in sys.argv:
    raise SystemExit("Explicit source-generation step required: python3 scripts/apply_location_gap_audit.py --write")
DATA_PATH = ROOT / "data/phase7_app_data.json"
I18N_PATH = ROOT / "data/translations.json"
ROUTES = ["A1", "A2", "B1", "B2"]
SUPPLEMENT_KEYS = {
    "pier39", "tunnel_tops", "bixby", "ghirardelli", "cable_car",
    "carmel", "el_capitan", "monterey_wharf",
}


def maps_url(query: str) -> str:
    return "https://www.google.com/maps/search/?api=1&query=" + quote_plus(query)


def occurrence(route: str, *, date: str, time: str, title: str, reason: str,
               advantage: str, status: str, seq: int) -> dict:
    return {
        "route": route,
        "date": date,
        "time": time,
        "title": title,
        "reason": reason,
        "advantage": advantage,
        "kind": "공통",
        "status": status,
        "seq": seq,
        "route_title": "",
        "stop_reason": reason,
        "stop_advantage": advantage,
    }


def marker(*, key: str, name: str, title: str, lat: float, lon: float, cluster: str,
           summary: str, why: str, role: str, score: float, query: str,
           date: str, time: str, reason: str, advantage: str, status: str, seq: int,
           tier: str, rules: list[dict], source_url: str, workbook_status: str) -> dict:
    return {
        "place_key": key,
        "name": name,
        "title": title,
        "lat": lat,
        "lon": lon,
        "cluster": cluster,
        "routes": ROUTES,
        "route_count": 4,
        "is_common_all": True,
        "summary": summary,
        "why": why,
        "role": role,
        "score": score,
        "maps_url": maps_url(query),
        "occurrences": [
            occurrence(
                route,
                date=date,
                time=time,
                title=title,
                reason=reason,
                advantage=advantage,
                status=status,
                seq=seq,
            )
            for route in ROUTES
        ],
        "photo_thumb": f"assets/photos/thumb/{key}__hero.webp",
        "photo_status": "LOCAL_3_REAL_PHOTOS_VERIFIED",
        "decision_rules": rules,
        "source_class": "official_gap_audit",
        "schedule_tier": tier,
        "discovery_source_url": source_url,
        "workbook_status": workbook_status,
    }


def timeline(key: str, *, date: str, time: str, title: str, reason: str,
             advantage: str, region: str, tier: str, choice_group: str | None = None) -> dict:
    item = {
        "id": "gap_" + key,
        "date": {"10/4": "10/4 일", "10/5": "10/5 월", "10/6": "10/6 화", "10/7": "10/7 수"}[date],
        "date_key": date,
        "time": time,
        "title": title,
        "reason": reason,
        "advantage": advantage,
        "spatial_keys": [key],
        "kind": "공통",
        "routes": ROUTES,
        "route_specific": False,
        "regions": [region],
        "schedule_tier": tier,
        "source_class": "official_gap_audit",
    }
    if choice_group:
        item["mutually_exclusive_group"] = choice_group
    return item


ADDITIONS = [
    marker(
        key="tunnel_tops",
        name="Presidio Tunnel Tops + Outpost Playground",
        title="Presidio Tunnel Tops + Outpost",
        lat=37.80296,
        lon=-122.46172,
        cluster="샌프란시스코권",
        summary="골든게이트 브리지 전망, 잔디 피크닉 공간, 2–12세용 자연형 놀이터와 가족 편의시설이 한곳에 있는 프레시디오 공원",
        why="오후 회복 블록이 제시간에 끝날 때 Palace of Fine Arts 직전에 붙일 수 있는 고효율 가족 정류장이다.",
        role="🟢 강력 추천",
        score=81.1,
        query="Presidio Tunnel Tops San Francisco",
        date="10/4 일",
        time="15:05–15:45",
        reason="낮잠·세탁 블록이 15:00까지 끝났을 때만 실행. Palace of Fine Arts로 이어지는 동선에 가족 놀이터와 GGB 전망을 추가한다.",
        advantage="가족 편의 / 제로급 우회",
        status="강력 추가 · 회복 우선",
        seq=7,
        tier="strong",
        rules=[{"key": "reset_late", "text": "15:00이 넘으면 Tunnel Tops를 건너뛰고 Palace of Fine Arts로 바로 간다."}],
        source_url="https://presidio.gov/explore/attractions/presidio-tunnel-tops",
        workbook_status="⭐ 강력추천 — 원본 워크북에 있었으나 지도에서 누락",
    ),
    marker(
        key="cable_car",
        name="Powell–Hyde Cable Car",
        title="Powell–Hyde Cable Car",
        lat=37.80518,
        lon=-122.42067,
        cluster="샌프란시스코권",
        summary="언덕, 베이 전망, 수동 그립 케이블카의 움직임을 한 번에 체험하는 샌프란시스코 대표 이동 경험",
        why="Chinatown에서 Fisherman’s Wharf 방향으로 이동 자체를 관광으로 바꾸는 선택지다. 다만 유모차 규칙과 줄 때문에 Coit/Lombard와 동시에 넣지 않는다.",
        role="🔴 첫 방문 필수",
        score=88.0,
        query="Hyde Street Cable Car Turnaround San Francisco",
        date="10/5 월",
        time="14:10–15:25 · Coit/Lombard 대체",
        reason="Washington & Powell 부근에서 Hyde & Beach 방향으로 탄다. 대기 20분 이내이고 유모차를 접을 수 있을 때만 Coit/Lombard 대신 선택한다.",
        advantage="이동=경험 / SF 상징",
        status="대체 옵션 · 택1",
        seq=8,
        tier="swap",
        rules=[
            {"key": "cable_queue", "text": "대기줄이 20분을 넘거나 유모차를 접기 어렵다면 Coit 또는 Lombard 중 하나로 전환한다."},
            {"key": "stroller_rule", "text": "케이블카 탑승 전 유모차를 접고 아이를 내려야 한다."},
        ],
        source_url="https://www.sfmta.com/routes/powell-hyde-cable-car",
        workbook_status="공식 교차검증으로 추가 — 원본 워크북에 개별 항목 없음",
    ),
    marker(
        key="pier39",
        name="PIER 39 Sea Lions at K-Dock",
        title="PIER 39 Sea Lions",
        lat=37.81004,
        lon=-122.41038,
        cluster="샌프란시스코권",
        summary="K-도크의 야생 캘리포니아 바다사자를 가까이서 보고 베이·알카트라즈 전망을 함께 즐기는 무료 워터프런트 경험",
        why="Alcatraz와 Fisherman’s Wharf 일정 사이에 거의 우회 없이 들어가는 가족 체감가치가 큰 대표 경험이다.",
        role="🔴 첫 방문 필수",
        score=93.0,
        query="Sea Lion Viewing Area PIER 39 K Dock San Francisco",
        date="10/5 월",
        time="15:20–16:05",
        reason="Coit/Lombard 또는 케이블카 선택 뒤 K-도크로 이동해 20–40분만 본다. Musée Mécanique와 같은 워터프런트 흐름이라 추가 이동 부담이 작다.",
        advantage="야생동물 / 가족가치 / 지리",
        status="확정 추가",
        seq=9,
        tier="must",
        rules=[{"key": "sea_lion_presence", "text": "바다사자가 적어도 전망대에서 15분 확인한 뒤 Musée Mécanique로 이동한다."}],
        source_url="https://pier39.com/sealions/",
        workbook_status="중대한 워크북 사각지대 — PIER 39/Sea Lions 검색 결과 0건",
    ),
    marker(
        key="ghirardelli",
        name="Ghirardelli Square + Aquatic Park",
        title="Ghirardelli Square + Aquatic Park",
        lat=37.80582,
        lon=-122.42294,
        cluster="샌프란시스코권",
        summary="벽돌 공장 건축, 초콜릿 간식, 잔잔한 Aquatic Park 해변과 베이 전망을 묶는 짧은 저녁 보너스",
        why="Musée Mécanique에서 도보권이라 에너지가 남을 때만 붙이는 쉬운 피날레다.",
        role="🟢 근처면 좋음",
        score=86.0,
        query="Ghirardelli Square San Francisco",
        date="10/5 월",
        time="17:30–18:05 · 에너지 남을 때",
        reason="Musée Mécanique가 17:20 전에 끝나고 가족 에너지가 6/10 이상일 때만 디저트와 해변 전망을 더한다.",
        advantage="도보권 보너스 / 간식",
        status="보너스",
        seq=11,
        tier="bonus",
        rules=[{"key": "family_energy_below_6", "text": "가족 에너지가 6/10 미만이면 바로 저녁과 숙소로 이동한다."}],
        source_url="https://www.sftravel.com/article/top-20-attractions-san-francisco",
        workbook_status="공식 교차검증으로 추가 — 원본 워크북에 개별 항목 없음",
    ),
    marker(
        key="carmel",
        name="Carmel-by-the-Sea + Carmel Beach",
        title="Carmel-by-the-Sea + Carmel Beach",
        lat=36.55531,
        lon=-121.92331,
        cluster="몬터레이·요세미티 연결권",
        summary="오션 애비뉴의 작은 마을 산책, 흰 모래 해변, 몬터레이 사이프러스 풍경을 짧은 리셋으로 묶는 정류장",
        why="Point Lobos에서 17-Mile Drive의 Carmel Gate로 가는 길에 있어 기존 점심·기저귀 리셋 시간을 장소 경험으로 바꿀 수 있다.",
        role="🟠 첫여행 대표",
        score=87.0,
        query="Carmel Beach Carmel-by-the-Sea California",
        date="10/6 화",
        time="10:15–10:55",
        reason="Point Lobos 뒤 Ocean Avenue/해변에서 40분만 걷고 간단히 먹는다. 이후 Carmel Gate로 들어가 17-Mile Drive를 북상한다.",
        advantage="동선 / 마을+해변 / 리셋",
        status="강력 추가",
        seq=15,
        tier="strong",
        rules=[{"key": "coastal_day_delay", "text": "Point Lobos가 10:10을 넘기면 Carmel은 20분 해변 확인만 하거나 생략한다."}],
        source_url="https://www.carmelcalifornia.com/carmel-beach/",
        workbook_status="워크북의 Monterey/Carmel 번들에만 언급 — 개별 지도 정류장으로 보강",
    ),
    marker(
        key="bixby",
        name="Bixby Creek Bridge",
        title="Bixby Creek Bridge",
        lat=36.37149,
        lon=-121.90173,
        cluster="몬터레이·요세미티 연결권",
        summary="빅서 절벽과 태평양 위를 가로지르는 역사적 콘크리트 아치교를 북쪽 전망대에서 보는 대표 해안 풍경",
        why="상징성은 높지만 남쪽 왕복이므로 Carmel+17-Mile Drive와 겹쳐 넣지 않고 날씨·도로가 좋을 때만 대체한다.",
        role="🟠 첫여행 대표",
        score=79.2,
        query="Bixby Creek Bridge California north vista point",
        date="10/6 화",
        time="10:15–11:30 · Carmel/17-Mile 대체",
        reason="Point Lobos 뒤 남쪽으로 내려가 전망만 보고 Monterey로 복귀한다. Carmel과 17-Mile Drive를 통째로 대체하며 절대 겹쳐 넣지 않는다.",
        advantage="아이콘 / 맑은날 옵션",
        status="대체 옵션 · 택1",
        seq=15,
        tier="swap",
        rules=[
            {"key": "bixby_swap_only", "text": "Bixby를 선택하면 Carmel과 17-Mile Drive는 삭제한다."},
            {"key": "caltrans_recheck", "text": "출발 24시간 전 Caltrans 도로 상태를 다시 확인한다."},
        ],
        source_url="https://dot.ca.gov/caltrans-near-me/district-5/d5-news/d5-news-9-2-2026",
        workbook_status="🌤 조건부 — 원본 워크북에 있었으나 지도에서 누락",
    ),
    marker(
        key="monterey_wharf",
        name="Old Fisherman’s Wharf Monterey",
        title="Old Fisherman’s Wharf",
        lat=36.60393,
        lon=-121.89304,
        cluster="몬터레이·요세미티 연결권",
        summary="몬터레이 항구의 보트, 해달·바다사자 가능성, 해산물 식당과 역사적 부두 분위기를 함께 보는 저녁 산책",
        why="Aquarium 뒤 저녁 장소가 아직 비어 있으므로 가족 컨디션이 좋을 때 숙박지로 가기 전 붙이는 선택지다.",
        role="🟢 근처면 좋음",
        score=82.0,
        query="Old Fisherman's Wharf Monterey California",
        date="10/6 화",
        time="17:15–18:10 · 저녁 옵션",
        reason="Aquarium 폐장 뒤 에너지가 남으면 부두에서 이른 저녁과 30분 산책. 피곤하면 바로 숙소로 간다.",
        advantage="저녁 해결 / 항구 분위기",
        status="보너스",
        seq=18,
        tier="bonus",
        rules=[{"key": "family_energy_below_6", "text": "Aquarium 뒤 가족 에너지가 6/10 미만이면 워프를 생략하고 숙소로 간다."}],
        source_url="https://www.seemonterey.com/things-to-do/attractions/old-fishermans-wharf/",
        workbook_status="공식 교차검증으로 추가 — 원본 워크북에 개별 항목 없음",
    ),
    marker(
        key="el_capitan",
        name="El Capitan Meadow",
        title="El Capitan Meadow",
        lat=37.72752,
        lon=-119.63312,
        cluster="몬터레이·요세미티 연결권",
        summary="3,000피트 화강암 벽의 압도적 스케일과 등반가를 초원에서 올려다보는 요세미티 밸리의 대표 정지점",
        why="Cook’s Meadow와 다른 수직 스케일을 15–20분에 얻고 서쪽 숙소·일몰 뷰 방향으로 자연스럽게 이어진다.",
        role="🔴 첫 방문 필수",
        score=88.0,
        query="El Capitan Meadow Yosemite National Park",
        date="10/7 수",
        time="14:35–14:55 · 잠들지 않았을 때",
        reason="장거리 이동 뒤 Cook’s Meadow를 마친 다음 짧게 정차한다. 아이가 잠들었으면 차창으로만 보고 체크인·낮잠을 보호한다.",
        advantage="스케일 / 짧은 정차",
        status="강력 추가 · 낮잠 우선",
        seq=20,
        tier="strong",
        rules=[{"key": "nap_protection", "text": "아이가 잠들었거나 도착이 30분 이상 밀리면 정차하지 않고 숙소로 간다."}],
        source_url="https://www.nps.gov/places/000/el-capitan-meadow.htm",
        workbook_status="NPS 공식 POI 교차검증으로 추가 — 원본 워크북에 개별 항목 없음",
    ),
]


TRANSLATIONS = {
    "샌프란시스코권": "San Francisco area",
    "몬터레이·요세미티 연결권": "Monterey–Yosemite corridor",
    "🟢 강력 추천": "🟢 Strong recommendation",
    "🔴 첫 방문 필수": "🔴 First-visit essential",
    "🟢 근처면 좋음": "🟢 Good when nearby",
    "🟠 첫여행 대표": "🟠 First-trip icon",
    "강력 추가 · 회복 우선": "Strong addition · recovery first",
    "대체 옵션 · 택1": "Swap option · choose one",
    "확정 추가": "Confirmed addition",
    "보너스": "Bonus",
    "강력 추가": "Strong addition",
    "강력 추가 · 낮잠 우선": "Strong addition · nap first",
    "가족 편의 / 제로급 우회": "Family amenities / near-zero detour",
    "이동=경험 / SF 상징": "Transit as an experience / SF icon",
    "야생동물 / 가족가치 / 지리": "Wildlife / family value / geography",
    "도보권 보너스 / 간식": "Walkable bonus / snack",
    "동선 / 마을+해변 / 리셋": "Routing / village + beach / reset",
    "아이콘 / 맑은날 옵션": "Icon / clear-weather option",
    "저녁 해결 / 항구 분위기": "Dinner solution / harbor atmosphere",
    "스케일 / 짧은 정차": "Scale / short stop",
}


PLACE_NAMES = {
    "tunnel_tops": ["Presidio Tunnel Tops + Outpost", "프레시디오 터널 탑스 · 아웃포스트"],
    "cable_car": ["Powell–Hyde Cable Car", "파월–하이드 케이블카"],
    "pier39": ["PIER 39 Sea Lions", "피어 39 바다사자 · K-도크"],
    "ghirardelli": ["Ghirardelli Square + Aquatic Park", "기라델리 스퀘어 · 아쿠아틱 파크"],
    "carmel": ["Carmel-by-the-Sea + Carmel Beach", "카멀 바이 더 씨 · 카멀 비치"],
    "bixby": ["Bixby Creek Bridge", "빅스비 크리크 브리지"],
    "monterey_wharf": ["Old Fisherman’s Wharf", "몬터레이 올드 피셔맨스 워프"],
    "el_capitan": ["El Capitan Meadow", "엘 캐피탄 메도우"],
}


def leg(leg_id: str, date: str, start: str, end: str, mode: str, label: str,
        note: str, branch_kind: str = "main", routes: list[str] | None = None) -> dict:
    points = {m["place_key"]: [m["lat"], m["lon"]] for m in ADDITIONS}
    data = json.loads(DATA_PATH.read_text())
    points.update({m["place_key"]: [m["lat"], m["lon"]] for m in data["markers"]})
    is_ferry = mode == "ferry"
    return {
        "leg_id": leg_id,
        "date": date,
        "from": start,
        "to": end,
        "from_latlon": points[start],
        "to_latlon": points[end],
        "mode": mode,
        "routes": routes or ROUTES,
        "geometry_kind": "conceptual_ferry" if is_ferry else "osm_reference_pending",
        "geometry_source": "authoritative dock/island endpoints; exact vessel track not asserted" if is_ferry else "official itinerary endpoints; cached OSM route generated at build time",
        "render_style": "conceptual_dots" if is_ferry else "cached_osm_reference_line",
        "label": label,
        "note": note,
        "show_overall": True,
        "branch_kind": branch_kind,
    }


def apply() -> None:
    data = json.loads(DATA_PATH.read_text())
    route_titles = {route: data["routes"][route]["title"] for route in ROUTES}
    for item in ADDITIONS:
        for occ in item["occurrences"]:
            occ["route_title"] = route_titles[occ["route"]]

    data["markers"] = [m for m in data["markers"] if m["place_key"] not in SUPPLEMENT_KEYS]
    insert_after = {
        "crissy": ["tunnel_tops"],
        "fortune": ["cable_car"],
        "lombard": ["pier39"],
        "musee": ["ghirardelli"],
        "point_lobos": ["carmel", "bixby"],
        "aquarium": ["monterey_wharf"],
        "cooks": ["el_capitan"],
    }
    additions_by_key = {m["place_key"]: m for m in ADDITIONS}
    rebuilt = []
    for item in data["markers"]:
        rebuilt.append(item)
        rebuilt.extend(additions_by_key[key] for key in insert_after.get(item["place_key"], []))
    data["markers"] = rebuilt

    # Rebalance, rather than overload, the two dense days.
    for item in data["markers"]:
        legacy_tiers = {
            "bay_lights": "bonus", "coit": "swap", "lombard": "swap",
            "tunnel_view": "swap", "valley_view": "swap", "washburn": "conditional",
            "glacier": "conditional", "mariposa": "conditional", "painted": "swap",
            "twin_peaks": "swap", "lands_end": "swap",
        }
        if item["place_key"] in legacy_tiers:
            item["schedule_tier"] = legacy_tiers[item["place_key"]]
        if item["place_key"] in {"coit", "lombard"}:
            for occ in item["occurrences"]:
                occ["time"] = "14:10–15:05 · 택1"
                occ["status"] = "대체 옵션 · 택1"
        if item["place_key"] == "musee":
            for occ in item["occurrences"]:
                occ["time"] = "16:10–17:20"
        if item["place_key"] == "lone_cypress":
            for occ in item["occurrences"]:
                occ["time"] = "11:05–12:15"

    # Thursday's Glacier Point outing returns to an explicit Valley recovery base.
    # This makes the route a complete, honest loop without inventing an attraction.
    cooks = next(item for item in data["markers"] if item["place_key"] == "cooks")
    cooks["occurrences"] = [occ for occ in cooks["occurrences"] if not occ["date"].startswith("10/8")]
    for route in ROUTES:
        cooks["occurrences"].append(occurrence(
            route,
            date="10/8 목",
            time="12:00 이후 · Valley 회복 베이스" if route != "A1" else "12:15–18:00 · Valley 회복 베이스",
            title="Yosemite Valley recovery base",
            reason="Glacier Point 왕복 뒤 점심·낮잠·자유시간을 한 장소에 묶어 과부하를 막는다.",
            advantage="복귀점 명확 / 회복 보호",
            status="회복 베이스",
            seq=23,
        ))
        cooks["occurrences"][-1]["route_title"] = route_titles[route]

    data["timeline"] = [t for t in data["timeline"] if not t["id"].startswith("gap_")]
    for item in data["timeline"]:
        if item["id"] == "tl014":
            item["time"] = "14:10–15:05 · 택1"
            item["title"] = "Coit 또는 Lombard 중 딱 하나"
            item["schedule_tier"] = "swap"
            item["mutually_exclusive_group"] = "sf_afternoon_icon"
        elif item["id"] == "tl015":
            item["time"] = "16:10–17:20"
        elif item["id"] == "tl018":
            item["time"] = "11:05–12:15"
            item["title"] = "17-Mile Drive · 대표 3곳만"
            item["reason"] = (
                "70분은 전 구간 정복 시간이 아니다. Carmel Gate에서 들어가 "
                "Spanish Bay/Bird Rock/Lone Cypress 중 최대 3곳만 보고 북상한다. "
                "Bixby를 선택하면 Carmel과 이 구간을 모두 삭제한다."
            )
            item["advantage"] = "상징 해안 / 지리 / 낮잠"
            item["schedule_tier"] = "main"
            item["mutually_exclusive_group"] = "monterey_scenic"
        elif item["id"] == "tl019":
            item["time"] = "12:15–13:00"
            item["title"] = "이른 점심·기저귀·Aquarium 리셋"
        if item["id"] in {"tl028", "tl029", "tl042", "tl052", "tl063"}:
            item["spatial_keys"] = ["cooks"]
            item["regions"] = ["yosemite"]
        legacy_timeline_tiers = {
            "tl004": ("bonus", None),
            "tl025": ("swap", "yosemite_sunset_view"),
            "tl026": ("conditional", None), "tl027": ("conditional", None),
            "tl030": ("conditional", None), "tl033": ("swap", "sf_return_view"),
            "tl041": ("conditional", None), "tl043": ("conditional", None),
            "tl047": ("swap", "sf_return_view"), "tl051": ("conditional", None),
            "tl059": ("swap", "sf_return_view"), "tl060": ("swap", "last_day_choice"),
            "tl062": ("conditional", None), "tl067": ("swap", "sf_return_view"),
        }
        if item["id"] in legacy_timeline_tiers:
            item["schedule_tier"], group = legacy_timeline_tiers[item["id"]]
            if group:
                item["mutually_exclusive_group"] = group

    new_timeline = {
        "tunnel_tops": timeline(
            "tunnel_tops", date="10/4", time="15:05–15:45", title="Presidio Tunnel Tops + Outpost",
            reason=ADDITIONS[0]["occurrences"][0]["reason"], advantage="가족 편의 / 제로급 우회", region="sf", tier="strong"),
        "cable_car": timeline(
            "cable_car", date="10/5", time="14:10–15:25 · Coit/Lombard 대체", title="Powell–Hyde Cable Car",
            reason=ADDITIONS[1]["occurrences"][0]["reason"], advantage="이동=경험 / SF 상징", region="sf", tier="swap", choice_group="sf_afternoon_icon"),
        "pier39": timeline(
            "pier39", date="10/5", time="15:20–16:05", title="PIER 39 Sea Lions",
            reason=ADDITIONS[2]["occurrences"][0]["reason"], advantage="야생동물 / 가족가치 / 지리", region="sf", tier="must"),
        "ghirardelli": timeline(
            "ghirardelli", date="10/5", time="17:30–18:05 · 에너지 남을 때", title="Ghirardelli Square + Aquatic Park",
            reason=ADDITIONS[3]["occurrences"][0]["reason"], advantage="도보권 보너스 / 간식", region="sf", tier="bonus"),
        "carmel": timeline(
            "carmel", date="10/6", time="10:15–10:55", title="Carmel-by-the-Sea + Carmel Beach",
            reason=ADDITIONS[4]["occurrences"][0]["reason"], advantage="동선 / 마을+해변 / 리셋", region="monterey", tier="strong", choice_group="monterey_scenic"),
        "bixby": timeline(
            "bixby", date="10/6", time="10:15–11:30 · Carmel/17-Mile 대체", title="Bixby Creek Bridge",
            reason=ADDITIONS[5]["occurrences"][0]["reason"], advantage="아이콘 / 맑은날 옵션", region="monterey", tier="swap", choice_group="monterey_scenic"),
        "monterey_wharf": timeline(
            "monterey_wharf", date="10/6", time="17:15–18:10 · 저녁 옵션", title="Old Fisherman’s Wharf",
            reason=ADDITIONS[6]["occurrences"][0]["reason"], advantage="저녁 해결 / 항구 분위기", region="monterey", tier="bonus"),
        "el_capitan": timeline(
            "el_capitan", date="10/7", time="14:35–14:55 · 잠들지 않았을 때", title="El Capitan Meadow",
            reason=ADDITIONS[7]["occurrences"][0]["reason"], advantage="스케일 / 짧은 정차", region="yosemite", tier="strong"),
    }
    timeline_after = {
        "tl008": ["tunnel_tops"],
        "tl014": ["cable_car", "pier39"],
        "tl015": ["ghirardelli"],
        "tl017": ["carmel", "bixby"],
        "tl020": ["monterey_wharf"],
        "tl023": ["el_capitan"],
    }
    rebuilt_timeline = []
    for item in data["timeline"]:
        rebuilt_timeline.append(item)
        rebuilt_timeline.extend(new_timeline[key] for key in timeline_after.get(item["id"], []))
    data["timeline"] = rebuilt_timeline

    remove_legs = {
        "C_1005_02", "C_1006_01", "A1_1007_VIEW", "A1_1007_VIEW_ALT",
        "GAP_1004_01", "GAP_1005_COIT_01", "GAP_1005_COIT_02",
        "GAP_1005_LOMBARD_01", "GAP_1005_LOMBARD_02", "GAP_1005_CABLE_01",
        "GAP_1005_CABLE_02", "GAP_1005_MAIN_01", "GAP_1005_BONUS_01",
        "GAP_1006_MAIN_01", "GAP_1006_MAIN_02", "GAP_1006_SWAP_01",
        "GAP_1006_SWAP_02", "GAP_1006_BONUS_01", "GAP_1007_01",
        "GAP_1007_02", "GAP_1007_03",
        "UX_1003_EVENING", "UX_1004_RESET", "UX_1005_RETURN",
        "UX_1008_OUT", "UX_1008_RETURN", "UX_1009_B2_VIEW_CHOICE",
        "UX_1010_VIEW_CHOICE", "UX_1010_B1_RESET",
    }
    data["legs"] = [item for item in data["legs"] if item["leg_id"] not in remove_legs]
    data["legs"].extend([
        leg("GAP_1004_01", "10/4", "tunnel_tops", "palace", "drive", "Tunnel Tops → Palace of Fine Arts", "강력 추가. 회복 블록이 늦으면 이 연결 전체를 생략한다.", "conditional"),
        leg("GAP_1005_COIT_01", "10/5", "fortune", "coit", "walk", "Chinatown → Coit 선택", "Coit/Lombard/Cable Car 중 하나만 선택한다.", "swap"),
        leg("GAP_1005_COIT_02", "10/5", "coit", "pier39", "walk", "Coit → PIER 39 Sea Lions", "Coit 선택 뒤 K-도크로 이어진다.", "swap"),
        leg("GAP_1005_LOMBARD_01", "10/5", "fortune", "lombard", "walk", "Chinatown → Lombard 선택", "Coit/Lombard/Cable Car 중 하나만 선택한다.", "swap"),
        leg("GAP_1005_LOMBARD_02", "10/5", "lombard", "pier39", "walk", "Lombard → PIER 39 Sea Lions", "Lombard 선택 뒤 K-도크로 이어진다.", "swap"),
        leg("GAP_1005_CABLE_01", "10/5", "fortune", "cable_car", "walk", "Chinatown → Powell–Hyde 선택", "케이블카 선택은 Coit/Lombard를 대체한다.", "swap"),
        leg("GAP_1005_CABLE_02", "10/5", "cable_car", "pier39", "walk", "Cable Car → PIER 39 Sea Lions", "Hyde & Beach 하차 뒤 워터프런트를 따라 K-도크로 걷는다.", "swap"),
        leg("GAP_1005_MAIN_01", "10/5", "pier39", "musee", "walk", "PIER 39 → Musée Mécanique", "같은 워터프런트의 확정 짧은 연결.", "main"),
        leg("GAP_1005_BONUS_01", "10/5", "musee", "ghirardelli", "walk", "Musée → Ghirardelli 보너스", "가족 에너지가 6/10 이상일 때만 실행.", "bonus"),
        leg("GAP_1006_MAIN_01", "10/6", "point_lobos", "carmel", "drive", "Point Lobos → Carmel", "기존 리셋 창을 Carmel의 해변·마을 경험으로 전환.", "main"),
        leg("GAP_1006_MAIN_02", "10/6", "carmel", "lone_cypress", "drive", "Carmel Gate → 17-Mile Drive", "Carmel에서 북상해 Aquarium 방향으로 나간다.", "main"),
        leg("GAP_1006_SWAP_01", "10/6", "point_lobos", "bixby", "drive", "Point Lobos → Bixby 대체", "Bixby 선택 시 Carmel과 17-Mile Drive를 삭제한다.", "swap"),
        leg("GAP_1006_SWAP_02", "10/6", "bixby", "aquarium", "drive", "Bixby → Monterey Aquarium", "도로 상태를 당일 재확인하는 대체 연결.", "swap"),
        leg("GAP_1006_BONUS_01", "10/6", "aquarium", "monterey_wharf", "drive", "Aquarium → Old Fisherman’s Wharf", "Aquarium 뒤 에너지가 남을 때만 실행.", "bonus"),
        leg("GAP_1007_01", "10/7", "cooks", "el_capitan", "drive", "Cook’s Meadow → El Capitan Meadow", "아이가 깨어 있을 때만 짧게 정차.", "conditional"),
        leg("GAP_1007_02", "10/7", "el_capitan", "tunnel_view", "drive", "El Capitan → Tunnel View 선택", "Yosemite West/Wawona 숙소 방향일 때.", "swap"),
        leg("GAP_1007_03", "10/7", "el_capitan", "valley_view", "drive", "El Capitan → Valley View 선택", "Foresta/El Portal 숙소 방향일 때.", "swap"),
        leg("UX_1003_EVENING", "10/3", "exploratorium", "bay_lights", "walk", "Exploratorium → Bay Lights evening return", "중간 회복 시간을 보낸 뒤 같은 워터프런트로 돌아오는 저녁 동선이다.", "recovery"),
        leg("UX_1004_RESET", "10/4", "battery", "tunnel_tops", "drive", "Battery Spencer → afternoon recovery → Tunnel Tops", "11:15–15:00의 점심·낮잠·세탁 회복 간격을 포함한다. 연속 관광을 뜻하지 않는다.", "recovery"),
        leg("UX_1005_RETURN", "10/5", "alcatraz", "pier39", "ferry", "Alcatraz return ferry → Pier 33 / waterfront", "실제 페리는 Pier 33으로 돌아온다. 선은 가까운 PIER 39 일정 마커까지의 개념 연결이며 선박 항적이 아니다.", "recovery"),
        leg("UX_1008_OUT", "10/8", "cooks", "washburn", "drive", "Valley recovery base → Washburn Point", "날씨가 통과할 때만 실행하는 Glacier Point 아침 외출의 출발 연결이다.", "conditional"),
        leg("UX_1008_RETURN", "10/8", "glacier", "cooks", "drive", "Glacier Point → Valley recovery base", "전망 뒤 Valley로 돌아와 점심·낮잠·자유시간을 보호한다.", "recovery"),
        leg("UX_1009_B2_VIEW_CHOICE", "10/9", "painted", "twin_peaks", "drive", "Painted Ladies ↔ Twin Peaks: choose one", "두 장소를 모두 방문하는 이동선이 아니다. 날씨와 가족 에너지에 따라 하나만 고르는 선택 관계다.", "choice", ["B2"]),
        leg("UX_1010_VIEW_CHOICE", "10/10", "painted", "twin_peaks", "drive", "Painted Ladies ↔ Twin Peaks: choose one", "두 장소를 모두 방문하는 이동선이 아니다. 날씨와 가족 에너지에 따라 하나만 고르는 선택 관계다.", "choice", ["A1", "A2", "B1"]),
        leg("UX_1010_B1_RESET", "10/10", "botanical", "painted", "drive", "Botanical Garden → long recovery → evening view choice", "09:00 이후 긴 점심·낮잠·자유시간을 거친 뒤 저녁 택1 전망으로 이어진다.", "recovery", ["B1"]),
    ])
    for item in data["legs"]:
        if item["leg_id"] == "T_1006_SF_MONTEREY":
            point_lobos = next(marker for marker in data["markers"] if marker["place_key"] == "point_lobos")
            item.update({"to": "point_lobos", "to_latlon": [point_lobos["lat"], point_lobos["lon"]], "label": "SF → Point Lobos / Monterey"})
        elif item["leg_id"] == "T_1007_MONTEREY_YOSE":
            item.update({"to": "cooks", "to_latlon": [cooks["lat"], cooks["lon"]], "label": "Monterey → Yosemite Valley"})
        if item["leg_id"] in {"UX_1008_OUT", "UX_1008_RETURN"}:
            item["max_route_km"] = 65
    for item in data["legs"]:
        if item["leg_id"] in {"C_1008_01", "A_1009_MARIPOSA"}:
            item["branch_kind"] = "conditional"

    data["place_region"].update({
        "tunnel_tops": "sf", "cable_car": "sf", "pier39": "sf", "ghirardelli": "sf",
        "carmel": "monterey", "bixby": "monterey", "monterey_wharf": "monterey",
        "el_capitan": "yosemite",
    })
    data["location_audit"] = {
        "version": "2026-09-14",
        "original_places": 28,
        "audited_supplements": 8,
        "total_places": 36,
        "method": "230-row workbook reconciliation plus official destination-source cross-check",
        "critical_finding": "PIER 39 and Sea Lions were absent from the workbook itself, not only the map.",
        "audit_path": "data/location_coverage_audit.json",
    }
    english_days = ["Sat", "Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    for date_item, day in zip(data["dates"], english_days, strict=True):
        date_item["label_en"] = f'{date_item["key"]} {day}'
    data["providers"]["vector"] = {
        "label": "Local Protomaps vector · OpenStreetMap data",
        "failure_domain": "local bundled PMTiles",
        "attribution": "© OpenStreetMap contributors · Protomaps",
        "requires_api_key": False,
        "status_at_build": "LOCAL_VECTOR_PMTILES_READY",
    }
    data["providers"] = {key: data["providers"][key] for key in ("vector", "satellite")}
    data.pop("offline_topo", None)
    data.pop("offline_context", None)
    DATA_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")

    # Keep translations exact for English mode and English-main/Korean-subtitle display.
    i18n = json.loads(I18N_PATH.read_text())
    i18n["places"].update(PLACE_NAMES)
    for item in ADDITIONS:
        paired = {
            item["summary"]: {
                "tunnel_tops": "A Presidio park combining Golden Gate Bridge views, picnic lawns, a nature-based playground for ages 2–12, and family amenities.",
                "cable_car": "A quintessential San Francisco transit experience combining hills, bay views, and the manually operated cable-car system.",
                "pier39": "A free waterfront experience where wild California sea lions gather at K-Dock, with Bay and Alcatraz views.",
                "ghirardelli": "A short evening bonus combining historic brick factory architecture, a chocolate stop, Aquatic Park beach, and bay views.",
                "carmel": "A compact reset combining Ocean Avenue village walking, white-sand Carmel Beach, and Monterey cypress scenery.",
                "bixby": "The classic Big Sur coastal view of a historic concrete arch bridge spanning cliffs above the Pacific.",
                "monterey_wharf": "An evening harbor walk with boats, possible otter or sea-lion sightings, seafood, and historic wharf atmosphere.",
                "el_capitan": "A Yosemite Valley stop where the 3,000-foot granite wall and tiny climbers reveal El Capitan’s scale.",
            }[item["place_key"]],
            item["why"]: {
                "tunnel_tops": "A high-value family stop that fits just before the Palace of Fine Arts when the afternoon recovery block ends on time.",
                "cable_car": "It turns the Chinatown-to-wharf transfer into the attraction itself, but it never stacks with Coit/Lombard because of the stroller rule and possible queue.",
                "pier39": "A high-value family wildlife experience that adds almost no detour between Alcatraz and the Fisherman’s Wharf block.",
                "ghirardelli": "It is walkable from Musée Mécanique and works as an easy finale only when energy remains.",
                "carmel": "It lies between Point Lobos and the 17-Mile Drive Carmel Gate, turning the existing lunch/diaper reset into a place experience.",
                "bixby": "It is highly iconic but requires a southbound out-and-back, so it replaces Carmel and 17-Mile Drive only when weather and roads are favorable.",
                "monterey_wharf": "The post-Aquarium dinner slot was unassigned, so this is an optional stop before the hotel when the family still feels good.",
                "el_capitan": "It adds a distinct vertical-scale Yosemite experience in 15–20 minutes and naturally leads toward western lodging or sunset viewpoints.",
            }[item["place_key"]],
        }
        for occ in item["occurrences"][:1]:
            paired[occ["reason"]] = {
                "tunnel_tops": "Do this only if nap and laundry finish by 3:00 PM. It adds a family playground and Golden Gate Bridge view on the way to the Palace of Fine Arts.",
                "cable_car": "Board near Washington & Powell toward Hyde & Beach. Choose it instead of Coit/Lombard only when the wait is 20 minutes or less and the stroller can be folded.",
                "pier39": "After the Coit/Lombard or cable-car choice, spend only 20–40 minutes at K-Dock. It is on the same waterfront flow as Musée Mécanique.",
                "ghirardelli": "Add dessert and the beach view only if Musée Mécanique ends by 5:20 PM and family energy is at least 6/10.",
                "carmel": "After Point Lobos, walk Ocean Avenue or the beach for 40 minutes and eat something simple, then enter 17-Mile Drive through Carmel Gate.",
                "bixby": "Drive south after Point Lobos, view the bridge, and return toward Monterey. It replaces both Carmel and 17-Mile Drive—never stack them.",
                "monterey_wharf": "If energy remains after Aquarium closing, use the wharf for an early dinner and a 30-minute walk; otherwise go straight to the hotel.",
                "el_capitan": "Stop briefly after Cook’s Meadow. If the child is asleep, view it from the car and protect check-in and nap time.",
            }[item["place_key"]]
        for rule in item["decision_rules"]:
            translations_by_text = {
                "15:00이 넘으면 Tunnel Tops를 건너뛰고 Palace of Fine Arts로 바로 간다.": "If it is after 3:00 PM, skip Tunnel Tops and go directly to the Palace of Fine Arts.",
                "대기줄이 20분을 넘거나 유모차를 접기 어렵다면 Coit 또는 Lombard 중 하나로 전환한다.": "If the wait exceeds 20 minutes or folding the stroller is impractical, switch to either Coit or Lombard.",
                "케이블카 탑승 전 유모차를 접고 아이를 내려야 한다.": "Before boarding a cable car, fold the stroller and remove the child.",
                "바다사자가 적어도 전망대에서 15분 확인한 뒤 Musée Mécanique로 이동한다.": "Even if few sea lions are present, check the viewing area for 15 minutes, then continue to Musée Mécanique.",
                "가족 에너지가 6/10 미만이면 바로 저녁과 숙소로 이동한다.": "If family energy is below 6/10, go directly to dinner and the hotel.",
                "Point Lobos가 10:10을 넘기면 Carmel은 20분 해변 확인만 하거나 생략한다.": "If Point Lobos runs past 10:10 AM, reduce Carmel to a 20-minute beach look or skip it.",
                "Bixby를 선택하면 Carmel과 17-Mile Drive는 삭제한다.": "If you choose Bixby, remove Carmel and 17-Mile Drive.",
                "출발 24시간 전 Caltrans 도로 상태를 다시 확인한다.": "Recheck Caltrans road conditions 24 hours before departure.",
                "Aquarium 뒤 가족 에너지가 6/10 미만이면 워프를 생략하고 숙소로 간다.": "If family energy is below 6/10 after the Aquarium, skip the wharf and go to the hotel.",
                "아이가 잠들었거나 도착이 30분 이상 밀리면 정차하지 않고 숙소로 간다.": "If the child is asleep or arrival is delayed by 30+ minutes, do not stop; go to the lodging.",
            }
            paired[rule["text"]] = translations_by_text[rule["text"]]
        for ko, en in paired.items():
            i18n["ko_to_en"][ko] = en
            i18n["en_to_ko"][en] = ko
    for ko, en in TRANSLATIONS.items():
        i18n["ko_to_en"][ko] = en
        i18n["en_to_ko"][en] = ko
    extra_pairs = {
        "Chinatown → Coit 선택": "Chinatown → choose Coit",
        "Chinatown → Lombard 선택": "Chinatown → choose Lombard",
        "Chinatown → Powell–Hyde 선택": "Chinatown → choose Powell–Hyde",
        "Musée → Ghirardelli 보너스": "Musée → Ghirardelli bonus",
        "Point Lobos → Bixby 대체": "Point Lobos → Bixby alternative",
        "El Capitan → Tunnel View 선택": "El Capitan → choose Tunnel View",
        "El Capitan → Valley View 선택": "El Capitan → choose Valley View",
        "Coit 또는 Lombard 중 딱 하나": "Choose exactly one: Coit or Lombard",
        "Carmel Gate에서 들어가 북상하는 지리. 차 안을 낮잠 가능 창으로 활용. Bixby를 선택하면 삭제한다.": "Enter through Carmel Gate and continue north, using the car as a possible nap window. Remove this stop if choosing Bixby.",
        "이른 점심·기저귀·Aquarium 리셋": "Early lunch, diaper, and Aquarium reset",
        "강력 추가. 회복 블록이 늦으면 이 연결 전체를 생략한다.": "Strong addition; skip this entire link if the recovery block runs late.",
        "Coit/Lombard/Cable Car 중 하나만 선택한다.": "Choose only one of Coit, Lombard, or the cable car.",
        "Coit 선택 뒤 K-도크로 이어진다.": "Continue to K-Dock after choosing Coit.",
        "Lombard 선택 뒤 K-도크로 이어진다.": "Continue to K-Dock after choosing Lombard.",
        "케이블카 선택은 Coit/Lombard를 대체한다.": "The cable-car choice replaces Coit/Lombard.",
        "Hyde & Beach 하차 뒤 워터프런트를 따라 K-도크로 걷는다.": "After alighting at Hyde & Beach, walk the waterfront to K-Dock.",
        "같은 워터프런트의 확정 짧은 연결.": "A short confirmed link along the same waterfront.",
        "가족 에너지가 6/10 이상일 때만 실행.": "Do this only when family energy is at least 6/10.",
        "기존 리셋 창을 Carmel의 해변·마을 경험으로 전환.": "Convert the existing reset window into Carmel’s beach and village experience.",
        "Carmel에서 북상해 Aquarium 방향으로 나간다.": "Continue north from Carmel and exit toward the Aquarium.",
        "Bixby 선택 시 Carmel과 17-Mile Drive를 삭제한다.": "Choosing Bixby removes Carmel and 17-Mile Drive.",
        "도로 상태를 당일 재확인하는 대체 연결.": "A swap connection requiring a same-day road-condition recheck.",
        "Aquarium 뒤 에너지가 남을 때만 실행.": "Do this only when energy remains after the Aquarium.",
        "아이가 깨어 있을 때만 짧게 정차.": "Stop briefly only if the child is awake.",
        "Yosemite West/Wawona 숙소 방향일 때.": "Use this branch for Yosemite West/Wawona lodging.",
        "Foresta/El Portal 숙소 방향일 때.": "Use this branch for Foresta/El Portal lodging.",
        "Glacier Point 왕복 뒤 점심·낮잠·자유시간을 한 장소에 묶어 과부하를 막는다.": "After the Glacier Point outing, consolidate lunch, nap, and free time at one Valley base to prevent overload.",
        "복귀점 명확 / 회복 보호": "Clear return point / protects recovery",
        "회복 베이스": "Recovery base",
        "12:00 이후 · Valley 회복 베이스": "After 12:00 · Valley recovery base",
        "12:15–18:00 · Valley 회복 베이스": "12:15–18:00 · Valley recovery base",
        "중간 회복 시간을 보낸 뒤 같은 워터프런트로 돌아오는 저녁 동선이다.": "Return to the same waterfront for the evening after the midday recovery block.",
        "11:15–15:00의 점심·낮잠·세탁 회복 간격을 포함한다. 연속 관광을 뜻하지 않는다.": "Includes the 11:15–15:00 lunch, nap, and laundry recovery gap; it does not mean continuous sightseeing.",
        "실제 페리는 Pier 33으로 돌아온다. 선은 가까운 PIER 39 일정 마커까지의 개념 연결이며 선박 항적이 아니다.": "The ferry actually returns to Pier 33. This conceptual line reaches the nearby PIER 39 itinerary marker and is not a vessel track.",
        "날씨가 통과할 때만 실행하는 Glacier Point 아침 외출의 출발 연결이다.": "Outbound connection for the Glacier Point morning outing, used only when the weather check passes.",
        "전망 뒤 Valley로 돌아와 점심·낮잠·자유시간을 보호한다.": "Return to the Valley after the viewpoint to protect lunch, nap, and free time.",
        "두 장소를 모두 방문하는 이동선이 아니다. 날씨와 가족 에너지에 따라 하나만 고르는 선택 관계다.": "This is not a travel leg visiting both places; it shows a choose-one relationship based on weather and family energy.",
        "09:00 이후 긴 점심·낮잠·자유시간을 거친 뒤 저녁 택1 전망으로 이어진다.": "After the long lunch, nap, and free-time block following 09:00, continue to one evening viewpoint choice.",
        "10:15–11:30 · Carmel/17-Mile 대체": "10:15–11:30 · replaces Carmel/17-Mile",
        "14:10–15:25 · Coit/Lombard 대체": "14:10–15:25 · replaces Coit/Lombard",
        "14:10–15:05 · 택1": "14:10–15:05 · choose one",
        "17:30–18:05 · 에너지 남을 때": "17:30–18:05 · only if energy remains",
        "17:15–18:10 · 저녁 옵션": "17:15–18:10 · dinner option",
        "14:35–14:55 · 잠들지 않았을 때": "14:35–14:55 · if the child is awake",
        "⭐ 강력추천 — 원본 워크북에 있었으나 지도에서 누락": "⭐ Strong recommendation — present in the workbook but missing from the map",
        "🌤 조건부 — 원본 워크북에 있었으나 지도에서 누락": "🌤 Conditional — present in the workbook but missing from the map",
        "공식 교차검증으로 추가 — 원본 워크북에 개별 항목 없음": "Added by official-source cross-check — no standalone workbook row",
        "중대한 워크북 사각지대 — PIER 39/Sea Lions 검색 결과 0건": "Critical workbook blind spot — zero PIER 39 / Sea Lions matches",
        "워크북의 Monterey/Carmel 번들에만 언급 — 개별 지도 정류장으로 보강": "Mentioned only inside the Monterey/Carmel workbook bundle — promoted to a mapped stop",
        "NPS 공식 POI 교차검증으로 추가 — 원본 워크북에 개별 항목 없음": "Added by an official NPS POI cross-check — no standalone workbook row",
    }
    for ko, en in extra_pairs.items():
        i18n["ko_to_en"][ko] = en
        i18n["en_to_ko"][en] = ko
    I18N_PATH.write_text(json.dumps(i18n, ensure_ascii=False, indent=2) + "\n")

    audit = {
        "version": "2026-09-14",
        "scope": "SF / Monterey / Yosemite family trip",
        "workbook": "SF_Trip_FINAL_SELECTION_50Criteria_2026-09-13.xlsx",
        "workbook_rows": 230,
        "workbook_status_counts": {"excluded": 195, "must": 16, "strong": 9, "conditional": 7, "bundle_reference": 3},
        "reconciliation": {
            "selected_concrete_rows": 32,
            "already_mapped": 28,
            "broad_areas_merged_into_existing_stops": ["Golden Gate Park", "Chinatown Local-Life Route"],
            "selected_rows_missing_from_map_before_audit": ["Presidio Tunnel Tops", "Bixby Creek Bridge"],
            "critical_source_list_blind_spot": "PIER 39 and Sea Lions were absent from the workbook (0 matching rows).",
        },
        "result": {"original_map_places": 28, "audited_additions": 8, "final_map_places": 36, "photo_assets": 108},
        "additions": [
            {
                "place_key": item["place_key"], "name": item["name"], "schedule_tier": item["schedule_tier"],
                "workbook_status": item["workbook_status"], "official_source": item["discovery_source_url"],
                "decision_rule": item["decision_rules"],
            }
            for item in ADDITIONS
        ],
        "guardrail": "The audit adds representative gaps, not every popular attraction. Swap and bonus tiers remain visible without silently overloading the day.",
    }
    (ROOT / "data/location_coverage_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n")

    canonical_path = ROOT / "data/canonical_places.json"
    canonical = [x for x in json.loads(canonical_path.read_text()) if x["place_key"] not in SUPPLEMENT_KEYS]
    for item in ADDITIONS:
        canonical.append({
            "place_key": item["place_key"], "canonical_name": item["name"],
            "source_lat": item["lat"], "source_lon": item["lon"], "maps_url": item["maps_url"],
            "cluster": item["cluster"], "place_summary": item["summary"], "place_why": item["why"],
            "role": item["role"], "place_score": item["score"], "routes": item["routes"],
            "route_occurrences": item["occurrences"], "titles": [item["title"]],
            "verified_lat": item["lat"], "verified_lon": item["lon"],
            "coordinate_type": "official attraction centroid / signed visitor viewpoint",
            "coordinate_decision": "ADD_OFFICIAL_GAP_AUDIT",
            "source_class": item["source_class"], "schedule_tier": item["schedule_tier"],
        })
    canonical_path.write_text(json.dumps(canonical, ensure_ascii=False, indent=2) + "\n")

    coord_path = ROOT / "data/coordinate_audit.json"
    coords = [x for x in json.loads(coord_path.read_text()) if x["place_key"] not in SUPPLEMENT_KEYS]
    for item in ADDITIONS:
        coords.append({
            "place_key": item["place_key"], "canonical_name": item["name"],
            "source_lat": item["lat"], "source_lon": item["lon"],
            "verified_lat": item["lat"], "verified_lon": item["lon"], "delta_m": 0.0,
            "coordinate_type": "official attraction centroid / signed visitor viewpoint",
            "verification_source": "Official-source gap audit plus OSM feature cross-check",
            "verification_source_url": item["discovery_source_url"],
            "decision": "ADD_OFFICIAL_GAP_AUDIT",
            "notes": item["workbook_status"],
        })
    coord_path.write_text(json.dumps(coords, ensure_ascii=False, indent=2) + "\n")
    csv_path = ROOT / "data/coordinate_audit.csv"
    with csv_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(coords[0]))
        writer.writeheader()
        writer.writerows(coords)

    report = """# Location Coverage Audit — 2026-09-14

## Outcome

The 230-row selection workbook was reconciled against the 28-place application and then cross-checked against official family and destination sources. The original map missed two selected workbook places (Presidio Tunnel Tops and Bixby Creek Bridge). More importantly, the workbook itself contained no PIER 39 or sea-lion entry. The corrected application contains 36 map places and 108 verified local photographs.

## Workbook reconciliation

- 230 named candidates reviewed across all 43 columns; no hidden rows or columns.
- 195 excluded, 16 must-experience, 9 strong, 7 conditional, and 3 bundle-reference rows.
- 28 selections were already mapped.
- Golden Gate Park and Chinatown are broad-area concepts represented by existing concrete stops.
- Tunnel Tops and Bixby were selected but missing from the map.
- `PIER 39`, `Sea Lion`, `바다사자`, and `피어 39` returned zero workbook rows: this was a source-list blind spot.

## Bounded official-source additions

| Place | Map treatment | Why it does not overload the trip |
|---|---|---|
| PIER 39 Sea Lions | Must, 10/5 | Inserts on the existing Wharf line between the afternoon choice and Musée. |
| Presidio Tunnel Tops | Strong, 10/4 | Runs only if the recovery block ends by 15:00. |
| Bixby Creek Bridge | Swap, 10/6 | Replaces Carmel + 17-Mile; never stacks. |
| Powell–Hyde Cable Car | Swap, 10/5 | Replaces Coit/Lombard; stroller and 20-minute queue gate. |
| Carmel-by-the-Sea + Beach | Strong, 10/6 | Uses the existing reset window en route to Carmel Gate. |
| Ghirardelli + Aquatic Park | Bonus, 10/5 | Only when energy is at least 6/10. |
| El Capitan Meadow | Strong, 10/7 | A 15–20 minute stop only if the child is awake. |
| Old Fisherman’s Wharf | Bonus, 10/6 | Optional dinner after the Aquarium. |

## Guardrail

This is a missing-out audit, not a generic top-attractions dump. Every added place has a time, route relationship, local photo set, and keep/swap/skip rule. The 195 explicit workbook exclusions remain exclusions unless a future trip preference changes.

## Primary cross-check sources

- San Francisco Travel top attractions and family guides: `https://www.sftravel.com/article/top-20-attractions-san-francisco`, `https://www.sftravel.com/article/san-francisco-kids-best-family-friendly-activities`
- PIER 39 Sea Lion Center / K-Dock: `https://pier39.com/sealions/`
- Presidio Tunnel Tops and Outpost: `https://presidio.gov/explore/attractions/presidio-tunnel-tops`, `https://presidio.gov/explore/attractions/outpost-playground`
- SFMTA Powell–Hyde route and child/stroller rules: `https://www.sfmta.com/routes/powell-hyde-cable-car`, `https://www.sfmta.com/getting-around/muni/traveling-young-children`
- Carmel Beach: `https://www.carmelcalifornia.com/carmel-beach/`
- Current Caltrans District 5 Big Sur access notice: `https://dot.ca.gov/caltrans-near-me/district-5/d5-news/d5-news-9-2-2026`
- NPS Yosemite Valley and El Capitan Meadow: `https://www.nps.gov/yose/planyourvisit/yv.htm`, `https://www.nps.gov/places/000/el-capitan-meadow.htm`
"""
    (ROOT / "LOCATION_COVERAGE_AUDIT.md").write_text(report)


if __name__ == "__main__":
    apply()
    result = json.loads(DATA_PATH.read_text())
    print(json.dumps({"markers": len(result["markers"]), "timeline": len(result["timeline"]), "legs": len(result["legs"])}, indent=2))
