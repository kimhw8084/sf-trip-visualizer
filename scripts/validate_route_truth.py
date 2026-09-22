#!/usr/bin/env python3
"""Fail-closed validation and deterministic projection for route truth.

The owner-approved 39x5 role matrix is the only role authority.  The day
model supplies dates and chronology; it may not contradict the matrix.
"""

from __future__ import annotations

import copy
import json
import re
from datetime import date
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ROLE_PATH = ROOT / "data" / "route_role_matrix.json"
SCHEDULE_PATH = ROOT / "data" / "route_schedules.json"
DATA_PATH = ROOT / "data" / "phase7_app_data.json"

ROUTES = ["A", "B", "C", "D", "E"]
ROLE_BUCKETS = {
    "hard_anchors": "Core",
    "strong": "Strong",
    "conditional": "Conditional",
}
ROLE_FIELDS = {role: field for field, role in ROLE_BUCKETS.items()}
ROLES = {"Core", "Strong", "Conditional", "Skip"}
KO_WEEKDAYS = ("월", "화", "수", "목", "금", "토", "일")
REGION_ALLOWANCE = {
    "10/3": {"sf"},
    "10/4": {"sf"},
    "10/5": {"sf"},
    "10/6": {"monterey"},
    "10/7": {"yosemite"},
    "10/8": {"yosemite"},
    # Yosemite morning followed by the SF arrival is explicitly legitimate.
    "10/9": {"yosemite", "sf"},
    "10/10": {"sf"},
    "10/11": {"sf"},
}
EXPECTED_LODGING = {
    "sf": ["10/2–10/6", "10/9–10/12"],
    "monterey": ["10/6–10/7"],
    "yosemite": ["10/7–10/9"],
}


def load(path: Path) -> Any:
    return json.loads(path.read_text())


def date_key(value: Any) -> str | None:
    text = str(value or "")
    return text.split(" ", 1)[0] if "/" in text else None


def date_labels(data: dict) -> dict[str, dict[str, str]]:
    return {
        item["key"]: {
            "ko": item.get("label", item["key"]),
            "en": item.get("label_en", item["key"]),
        }
        for item in data.get("dates", [])
    }


def display_date(data: dict, key: str) -> dict[str, str]:
    labels = date_labels(data)
    if key not in labels:
        raise ValueError(f"unknown canonical date key: {key}")
    return labels[key]


def actual_weekdays(key: str) -> tuple[str, str]:
    month, day = (int(part) for part in key.split("/"))
    observed = date(2026, month, day)
    return KO_WEEKDAYS[observed.weekday()], observed.strftime("%a")


def canonicalize_schedule(schedule: dict, roles: dict[str, dict[str, str]], place_region: dict[str, str] | None = None) -> dict:
    """Project existing day membership into the canonical role buckets.

    The existing day placement is retained.  A duplicate is kept once, in
    the matrix-defined bucket; Skip places are removed.  Monterey stops after
    the 10/6 departure are not eligible schedule rows.
    """

    projected = copy.deepcopy(schedule)
    place_region = place_region or {}
    for route in ROUTES:
        route_doc = projected.get("routes", {}).get(route, {})
        for day_key, day in route_doc.get("days", {}).items():
            buckets = {"Core": [], "Strong": [], "Conditional": []}
            seen: set[str] = set()
            for field, source_role in ROLE_BUCKETS.items():
                for place in day.get(field, []):
                    if place not in roles:
                        raise ValueError(f"schedule references unknown place {place!r} on route {route} {day_key}")
                    if place in seen:
                        continue
                    seen.add(place)
                    if place_region.get(place) == "monterey" and day_key != "10/6":
                        continue
                    role = roles[place].get(route)
                    if role == "Skip":
                        continue
                    if role not in buckets:
                        raise ValueError(f"invalid canonical role {role!r} for {place} / {route}")
                    buckets[role].append(place)
            for role, field in ROLE_FIELDS.items():
                day[field] = buckets[role]
    return projected


def _check(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def validate_route_truth(data: dict | None = None, roles_doc: dict | None = None, schedule: dict | None = None) -> dict:
    data = load(DATA_PATH) if data is None else data
    roles_doc = load(ROLE_PATH) if roles_doc is None else roles_doc
    schedule = load(SCHEDULE_PATH) if schedule is None else schedule
    failures: list[str] = []
    roles = roles_doc.get("places", {})
    route_ids = roles_doc.get("route_ids", [])
    labels = date_labels(data)
    date_keys = list(labels)
    place_region = data.get("place_region", {})
    markers = {marker.get("place_key"): marker for marker in data.get("markers", [])}

    _check(failures, route_ids == ROUTES, f"role matrix route_ids must be exactly {ROUTES}")
    _check(failures, len(roles) == 39, f"role matrix must contain 39 places, found {len(roles)}")
    _check(failures, set(roles) == set(markers), "role matrix and canonical marker place identities differ")
    _check(failures, set(place_region) == set(markers), "place-region authority does not cover exactly the 39 places")

    scheduled_rows = 0
    daily_regions: dict[str, dict[str, list[str]]] = {route: {} for route in ROUTES}
    for route in ROUTES:
        days = schedule.get("routes", {}).get(route, {}).get("days", {})
        _check(failures, route in schedule.get("routes", {}), f"missing schedule route {route}")
        seen_by_day: dict[str, set[str]] = {}
        for day_key, day in days.items():
            _check(failures, day_key in labels, f"{route} uses non-canonical date {day_key}")
            seen = seen_by_day.setdefault(day_key, set())
            regions: list[str] = []
            for field, expected_role in ROLE_BUCKETS.items():
                values = day.get(field, [])
                _check(failures, isinstance(values, list), f"{route} {day_key} {field} must be a list")
                for place in values:
                    scheduled_rows += 1
                    if place in seen:
                        failures.append(f"{route} {day_key} places {place} in multiple role buckets or repeats it")
                    seen.add(place)
                    if place not in roles:
                        failures.append(f"{route} {day_key} {field} references unknown place {place}")
                        continue
                    actual_role = roles[place].get(route)
                    if actual_role == "Skip":
                        failures.append(f"{route} {day_key} schedules Skip place {place}")
                    elif actual_role != expected_role:
                        failures.append(f"{route} {day_key} {place} is {expected_role}, canonical role is {actual_role}")
                    region = place_region.get(place)
                    if region and region not in regions:
                        regions.append(region)
                    allowed = REGION_ALLOWANCE.get(day_key, set())
                    if region and region not in allowed:
                        failures.append(f"{route} {day_key} places {place} in impossible region {region}; allowed {sorted(allowed)}")
                    if region == "monterey" and day_key != "10/6":
                        failures.append(f"{route} {day_key} schedules Monterey stop {place} after departure")
            daily_regions[route][day_key] = regions

        _check(failures, set(days) <= set(date_keys), f"{route} schedule dates are outside the canonical sightseeing window")
        ordered_regions: list[str] = []
        for day_key in date_keys:
            for region in daily_regions[route].get(day_key, []):
                if not ordered_regions or ordered_regions[-1] != region:
                    ordered_regions.append(region)
        _check(
            failures,
            ordered_regions == ["sf", "monterey", "yosemite", "sf"] or ordered_regions == ["sf", "monterey", "yosemite"],
            f"{route} region chronology is implausible: {ordered_regions}",
        )

        for day_key, day in days.items():
            if "bixby" not in day.get("hard_anchors", []) + day.get("strong", []) + day.get("conditional", []):
                continue
            _check(failures, day_key == "10/6", f"{route} Bixby must remain on the Monterey sightseeing day")
            text = " ".join(str(day.get(key, "")) for key in ("decisions", "recovery", "drop_first"))
            _check(failures, "drive-through" in text or "drive through" in text, f"{route} Bixby lacks drive-through-only language")
            unsafe = None
            for match in re.finditer(r"\b(parking|shoulder|u-?turn)\b", text.lower()):
                prefix = text.lower()[max(0, match.start() - 50):match.start()]
                if "no " not in prefix:
                    unsafe = match
                    break
            _check(failures, unsafe is None, f"{route} Bixby contains unsafe stop language")

    lodging = schedule.get("lodging")
    _check(failures, lodging == "SF 10/2–10/6 → Monterey exactly one night 10/6–10/7 → Yosemite exactly two nights 10/7–10/9 → SF 10/9–10/12", "lodging skeleton text drifted")
    _check(failures, data.get("trip", {}).get("lodging_nights") == EXPECTED_LODGING, "canonical lodging nights drifted")

    occurrence_count = 0
    occurrence_failures_before = len(failures)
    for marker in data.get("markers", []):
        place = marker.get("place_key")
        for index, occurrence in enumerate(marker.get("occurrences", [])):
            occurrence_count += 1
            route = occurrence.get("route")
            prefix = f"occurrence {place}[{index}]"
            key = occurrence.get("date_key") or date_key(occurrence.get("date"))
            _check(failures, route in ROUTES, f"{prefix} has invalid route {route}")
            _check(failures, key in labels, f"{prefix} has invalid date_key {key}")
            if key in labels:
                _check(failures, occurrence.get("date") == labels[key]["ko"], f"{prefix} has stale Korean weekday/date label")
                if "date_en" in occurrence:
                    _check(failures, occurrence.get("date_en") == labels[key]["en"], f"{prefix} has stale English weekday/date label")
                ko_weekday, en_weekday = actual_weekdays(key)
                _check(failures, labels[key]["ko"].endswith(ko_weekday), f"date authority Korean weekday is wrong for {key}")
                _check(failures, labels[key]["en"].endswith(en_weekday), f"date authority English weekday is wrong for {key}")
            if route in ROUTES and place in roles:
                _check(failures, roles[place].get(route) != "Skip", f"{prefix} schedules a Skip role")
                _check(failures, occurrence.get("role") == roles[place].get(route), f"{prefix} role disagrees with canonical matrix")
    if occurrence_failures_before == len(failures) and occurrence_count == 0:
        failures.append("canonical data contains no generated occurrence records")

    return {
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "counts": {
            "routes": len(schedule.get("routes", {})),
            "matrix_places": len(roles),
            "scheduled_rows": scheduled_rows,
            "occurrences": occurrence_count,
            "dates": len(labels),
        },
        "daily_regions": daily_regions,
        "lodging": EXPECTED_LODGING,
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()
    report = validate_route_truth()
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "counts": report["counts"], "failures": report["failures"][:20]}, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
