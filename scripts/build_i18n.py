"""Freeze locally generated translations with editorial corrections and place subtitles."""

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ko_to_en = json.loads((ROOT / ".tools/i18n_ko_to_en.json").read_text())
en_to_ko = json.loads((ROOT / ".tools/i18n_en_to_ko.json").read_text())
extra = ROOT / ".tools/i18n_missing_en.json"
if extra.exists():
    ko_to_en.update(json.loads(extra.read_text()))
ko_to_en.update({
    "2박 Yosemite — Fleet Week 역이용형": "2 nights in Yosemite — make Fleet Week work for us",
    "3박 Yosemite — 옵션가치 극대화형": "3 nights in Yosemite — maximum flexibility",
    "3박 Yosemite — 감동 스펙트럼 최대형": "3 nights in Yosemite — widest range of highlights",
    "2박 Yosemite — Yosemite 아침 보호 + SF 회복형": "2 nights in Yosemite — protect the final morning, recover in SF",
    "🔴 첫 방문 필수": "First-visit essential",
    "🟠 첫여행 대표": "Signature first-trip stop",
    "🟡 그룹 중 선택": "Choose one from this group",
    "🟢 근처면 좋음": "Optional if nearby",
    "공통": "Shared",
    "전용": "Route-specific",
    "확정": "Planned",
    "조건부": "Conditional",
    "샌프란시스코권": "San Francisco area",
    "몬터레이권": "Monterey area",
    "요세미티권": "Yosemite area",
})
place_names = {
    "ferry": ["Ferry Building + Farmers Market", "페리 빌딩 · 파머스 마켓"],
    "exploratorium": ["Exploratorium", "익스플로라토리움"],
    "bay_lights": ["The Bay Lights", "베이 브리지 야간 조명"],
    "ggb": ["Golden Gate Bridge", "금문교 · 남쪽 전망대"],
    "muir": ["Muir Woods", "뮤어 우즈 국립기념물"],
    "battery": ["Battery Spencer", "배터리 스펜서 전망대"],
    "palace": ["Palace of Fine Arts", "팰리스 오브 파인 아츠"],
    "crissy": ["Crissy Field", "크리시 필드 이스트 비치"],
    "alcatraz": ["Alcatraz Island", "알카트라즈 섬"],
    "north_beach": ["North Beach", "노스 비치"],
    "fortune": ["Golden Gate Fortune Cookie Factory", "골든 게이트 포춘 쿠키 공장"],
    "coit": ["Coit Tower", "코이트 타워"],
    "lombard": ["Lombard Street", "롬바드 스트리트"],
    "musee": ["Musée Mécanique", "뮤제 메카니크"],
    "point_lobos": ["Point Lobos", "포인트 로보스 자연보호구역"],
    "lone_cypress": ["The Lone Cypress", "론 사이프러스 · 17마일 드라이브"],
    "aquarium": ["Monterey Bay Aquarium", "몬터레이 베이 아쿠아리움"],
    "cooks": ["Cook’s Meadow Loop", "쿡스 메도우 루프"],
    "tunnel_view": ["Tunnel View", "터널 뷰"],
    "valley_view": ["Valley View", "밸리 뷰"],
    "washburn": ["Washburn Point", "워시번 포인트"],
    "glacier": ["Glacier Point", "글레이셔 포인트"],
    "mariposa": ["Mariposa Grove", "마리포사 그로브"],
    "painted": ["Painted Ladies", "페인티드 레이디스 · 알라모 스퀘어"],
    "twin_peaks": ["Twin Peaks", "트윈 픽스"],
    "botanical": ["San Francisco Botanical Garden", "샌프란시스코 식물원"],
    "academy": ["California Academy of Sciences", "캘리포니아 과학 아카데미"],
    "lands_end": ["Lands End", "랜즈 엔드 해안 트레일"],
}
data = json.loads((ROOT / "data/phase7_app_data.json").read_text())
values = set()


def walk(obj):
    if isinstance(obj, dict):
        for value in obj.values():
            walk(value)
    elif isinstance(obj, list):
        for value in obj:
            walk(value)
    elif isinstance(obj, str) and re.search(r"[가-힣]", obj):
        values.add(obj)


walk(data)
missing = sorted(values - ko_to_en.keys())
if missing:
    print(f"WARNING: {len(missing)} non-prose Korean strings remain; first ten: {missing[:10]}")
output = {"ko_to_en": ko_to_en, "en_to_ko": en_to_ko, "places": place_names, "untranslated_korean_data_values": missing}
(ROOT / "data/translations.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
print(f"Saved {len(ko_to_en)} Korean→English, {len(en_to_ko)} English→Korean, {len(place_names)} bilingual place names")
