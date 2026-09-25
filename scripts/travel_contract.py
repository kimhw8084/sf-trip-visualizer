"""Fail-closed validation for structured travel-time coverage."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any


SAFE_PRIVATE_LODGING_IDENTITIES = {
    "Mill Valley lodging",
    "Yosemite West lodging",
    "Foster City lodging",
}
NO_BASELINE = "UNAVAILABLE_NO_INDEPENDENT_SOURCE"


def validate_travel_contract(data: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []

    def check(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    def privacy_safe(value: Any, travel_id: str, path: str = "range") -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if re.fullmatch(r"(?:lat|lon|latitude|longitude|coordinates?|coordinate_pair)", str(key), re.IGNORECASE) and child not in (None, "", [], {}):
                    check(False, f"range {travel_id} contains a coordinate at {path}.{key}")
                privacy_safe(child, travel_id, f"{path}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                privacy_safe(child, travel_id, f"{path}[{index}]")
        elif isinstance(value, float):
            check(False, f"range {travel_id} contains an unapproved decimal value at {path}")
        elif isinstance(value, str):
            address = re.search(r"\b\d{1,6}\s+(?:[A-Za-z0-9.'’-]+\s+){0,4}(?:Street|St\.?|Avenue|Ave\.?|Road|Rd\.?|Lane|Ln\.?|Drive|Dr\.?|Court|Ct\.?|Way)\b", value, re.IGNORECASE)
            check(address is None, f"range {travel_id} contains a street-address-shaped endpoint at {path}")

    check(data.get("travel_contract_schema_version") == 2, "canonical data does not declare travel contract schema version 2")

    timeline = data.get("timeline", [])
    legs = data.get("legs", [])
    legacy_archive = data.get("route_graph_legacy_range_archive", [])
    ranges = data.get("travel_ranges", [])
    range_ids = [item.get("id") for item in ranges]
    duplicate_ranges = sorted(key for key, count in Counter(range_ids).items() if not key or count != 1)
    check(not duplicate_ranges, f"travel-range IDs are missing or duplicated: {duplicate_ranges}")
    by_id = {item.get("id"): item for item in ranges if item.get("id")}

    timeline_ids = [item.get("id") for item in timeline]
    leg_ids = [item.get("leg_id") for item in legs]
    check(len(timeline_ids) == len(set(timeline_ids)), "timeline IDs are not unique")
    check(len(leg_ids) == len(set(leg_ids)), "leg IDs are not unique")

    references: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for row in timeline:
        if row.get("kind") != "travel":
            continue
        travel_id = row.get("travel_range_id")
        check(bool(travel_id), f"timeline travel row {row.get('id')} has no travel_range_id")
        if travel_id:
            references.setdefault(travel_id, []).append(("timeline", row.get("id", "")))
            check(travel_id in by_id, f"timeline travel row {row.get('id')} references missing range {travel_id}")
    for leg in legs:
        travel_id = leg.get("travel_range_id")
        if travel_id:
            references.setdefault(travel_id, []).append(("leg", leg.get("leg_id", "")))
            check(travel_id in by_id, f"connector {leg.get('leg_id')} references missing range {travel_id}")
    for archived in legacy_archive:
        travel_id = archived.get("travel_range_id")
        check(bool(travel_id), f"legacy connector archive {archived.get('source_leg_id')} has no travel_range_id")
        if travel_id:
            references.setdefault(travel_id, []).append(("legacy_archive", archived.get("source_leg_id", "")))
            check(travel_id in by_id, f"legacy connector archive references missing range {travel_id}")

    for travel_id, travel_range in by_id.items():
        linked = references.get(travel_id, [])
        check(bool(linked), f"orphan travel range {travel_id}")
        check(sum(kind == "timeline" for kind, _ in linked) <= 1, f"range {travel_id} links multiple timeline movements")
        check(sum(kind == "leg" for kind, _ in linked) <= 1, f"range {travel_id} links multiple connectors")
        check(sum(kind == "legacy_archive" for kind, _ in linked) <= 1, f"range {travel_id} repeats in the legacy connector archive")
        check(not any(kind == "legacy_archive" for kind, _ in linked) or not any(kind in {"timeline", "leg"} for kind, _ in linked), f"range {travel_id} is both active and archived")
        if not linked:
            continue

        check(travel_range.get("travel_range_id") == travel_id, f"range {travel_id} does not repeat its stable identity")
        check(bool(re.fullmatch(r"travel_[a-z0-9_]+", str(travel_id))), f"range ID {travel_id} is not stable canonical syntax")
        required_text = ("date_key", "from_identity", "to_identity", "mode", "basis", "method", "confidence", "live_navigation_cue")
        for field in required_text:
            check(isinstance(travel_range.get(field), str) and bool(travel_range[field].strip()), f"range {travel_id} lacks {field}")
        check("check live navigation before leaving" in str(travel_range.get("live_navigation_cue", "")).lower(), f"range {travel_id} lacks the required recheck cue")

        window = travel_range.get("planned_schedule_window")
        check(isinstance(window, dict), f"range {travel_id} lacks a planned schedule window")
        if isinstance(window, dict):
            for endpoint in ("departure", "arrival"):
                item = window.get(endpoint)
                check(isinstance(item, dict) and bool(item.get("status")) and bool(item.get("detail")), f"range {travel_id} lacks truthful {endpoint} window semantics")
            check(bool(window.get("owner_approved_basis")), f"range {travel_id} does not identify its schedule-window basis")
            check("buffer_minutes" not in window and "schedule_buffer" not in window, f"range {travel_id} folds the schedule buffer into its window")

        duration = travel_range.get("planning_duration_range")
        check(isinstance(duration, dict), f"range {travel_id} lacks a planning-duration range status")
        if isinstance(duration, dict):
            status = duration.get("status")
            numeric = isinstance(duration.get("minutes_min"), int) and isinstance(duration.get("minutes_max"), int)
            if status == "SCHEDULE_DERIVED":
                check(numeric and duration["minutes_min"] <= duration["minutes_max"], f"range {travel_id} has an invalid schedule-derived duration")
                check(bool(duration.get("derivation")), f"range {travel_id} omits the schedule-only duration derivation")
            else:
                check(status == "NOT_ESTIMABLE_FROM_APPROVED_SCHEDULE", f"range {travel_id} has an unknown duration status")
                check(duration.get("minutes_min") is None and duration.get("minutes_max") is None, f"range {travel_id} assigns minutes despite an unavailable duration")
                check(bool(duration.get("reason")), f"range {travel_id} does not explain its unavailable schedule duration")

        baseline = travel_range.get("baseline_reference")
        check(isinstance(baseline, dict), f"range {travel_id} lacks a distinct baseline/reference object")
        if isinstance(baseline, dict):
            check(baseline.get("status") == NO_BASELINE, f"range {travel_id} presents an unsupported baseline status")
            check(baseline.get("minutes_min") is None and baseline.get("minutes_max") is None, f"range {travel_id} presents unsourced baseline minutes")
            check(baseline.get("provenance") is None, f"range {travel_id} claims unsupported baseline provenance")
            check(bool(baseline.get("reason")), f"range {travel_id} does not explain the missing independent baseline")
            check(not {"departure", "arrival", "buffer_minutes", "schedule_buffer"} & set(baseline), f"range {travel_id} conflates baseline with schedule-window/buffer fields")
        check("NOT_RESEARCHED" not in str(baseline), f"range {travel_id} retains ambiguous NOT_RESEARCHED vocabulary")

        buffer = travel_range.get("schedule_buffer")
        check(isinstance(buffer, dict) and bool(buffer.get("status")) and bool(buffer.get("detail")), f"range {travel_id} lacks a distinct schedule-buffer status")
        if isinstance(buffer, dict):
            check(buffer is not baseline and buffer is not duration, f"range {travel_id} conflates schedule buffer with duration/reference")
            check("minutes_min" in buffer and "minutes_max" in buffer and bool(buffer.get("detail")), f"range {travel_id} does not separately encode buffer values/status")
            check(not {"provenance", "departure", "arrival", "planning_duration_range"} & set(buffer), f"range {travel_id} conflates buffer with baseline or schedule window")

        private_endpoints = [value for value in (travel_range.get("from_identity"), travel_range.get("to_identity")) if "lodging" in str(value).lower()]
        privacy = travel_range.get("privacy_classification")
        if private_endpoints:
            check(all(value in SAFE_PRIVATE_LODGING_IDENTITIES for value in private_endpoints), f"range {travel_id} exposes a non-safe residential endpoint identity")
            check(privacy == "private_lodging_endpoint_redacted", f"range {travel_id} lacks private-lodging privacy classification")
        else:
            check(privacy == "public_place_endpoints", f"range {travel_id} lacks public endpoint privacy classification")
        lowered = str(travel_range).lower()
        check(not any(term in lowered for term in ("google maps", "google directions", "live router result")), f"range {travel_id} claims an unobserved live-routing source")
        privacy_safe(travel_range, travel_id)

    for day_key, operation in data.get("operating_days", {}).items():
        contract = operation.get("travel_contract")
        check(isinstance(contract, dict), f"operating day {day_key} lacks a timeline-backed travel contract")
        if not isinstance(contract, dict):
            continue
        field_roles = {
            "start_movement_id": {"day_start", "airport_departure", "airport_arrival_transfer", "lodging_arrival"},
            "nap_return_movement_ids": {"protected_nap_return"},
            "end_movement_id": {"final_lodging_return", "lodging_arrival", "airport_departure"},
        }
        required_fields = ("start_movement_id", "nap_return_movement_ids", "end_movement_id")
        check(all(field in contract for field in required_fields), f"operating day {day_key} travel contract is incomplete")
        ids = [value for value in (contract.get("start_movement_id"), *contract.get("nap_return_movement_ids", []), contract.get("end_movement_id")) if value]
        check(all(isinstance(value, str) and value for value in ids), f"operating day {day_key} has an empty required movement reference")
        check(len(ids) == len(set(ids)), f"operating day {day_key} repeats a movement in its travel contract")
        day_rows = {row.get("id"): row for row in timeline if row.get("date_key") == day_key and row.get("kind") == "travel"}
        for field, allowed_roles in field_roles.items():
            values = contract.get(field, []) if field == "nap_return_movement_ids" else [contract.get(field)]
            for movement_id in values:
                if not movement_id:
                    continue
                row = day_rows.get(movement_id)
                check(row is not None, f"operating day {day_key} {field} does not reference a travel timeline row")
                if row:
                    check(row.get("travel_role") in allowed_roles, f"operating day {day_key} {movement_id} has the wrong travel role")
                    check(bool(row.get("travel_range_id")), f"operating day {day_key} {movement_id} lacks a travel-range binding")
        recovery = str(operation.get("recovery_en", "")).lower()
        return_semantics = any(term in recovery for term in ("back by", "lodging by", "lodging ~", "return", "back ~"))
        check(not return_semantics or bool(contract.get("end_movement_id")), f"operating day {day_key} states a lodging return only in summary prose")

    return {
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "counts": {
            "material_timeline_movements": sum(row.get("kind") == "travel" for row in timeline),
            "material_route_connectors": sum(bool(leg.get("travel_range_id")) for leg in legs),
            "linked_legacy_connector_ranges": len(legacy_archive),
            "structured_travel_ranges": len(ranges),
            "linked_timeline_movements": sum(bool(row.get("travel_range_id")) for row in timeline if row.get("kind") == "travel"),
            "linked_route_connectors": sum(bool(leg.get("travel_range_id")) for leg in legs),
        },
    }
