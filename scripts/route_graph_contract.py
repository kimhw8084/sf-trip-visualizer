"""Semantic and geometry contract for public field-atlas route lines."""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any


PUBLIC_MODES = {"drive", "walk"}
BREAK_KINDS = {"protected_nap_return", "lodging_checkin_reset"}


def _distance_km(a: list[float], b: list[float]) -> float:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    delta_lat, delta_lon = lat2 - lat1, lon2 - lon1
    arc = 2 * math.asin(math.sqrt(math.sin(delta_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2))
    return 6371 * arc


def validate_route_graph(data: dict[str, Any], geometry: dict[str, Any], manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    failures: list[str] = []

    def check(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    markers = {item.get("place_key"): item for item in data.get("markers", [])}
    anchors = data.get("endpoint_anchors", {})
    non_photo = {item.get("key") for item in data.get("non_photo_itinerary_identities", [])}
    dates = {item.get("key") for item in data.get("dates", [])}
    groups = data.get("route_continuity_groups", [])
    group_ids = [group.get("id") for group in groups]
    group_by_id = {group.get("id"): group for group in groups if group.get("id")}

    check(data.get("route_graph_schema_version") == 1, "route graph does not declare semantic schema version 1")
    check(len(group_ids) == len(set(group_ids)) and all(group_ids), "route continuity group IDs are missing or duplicated")
    for group in groups:
        group_id, date_key = group.get("id"), group.get("date_key")
        nodes = group.get("nodes", [])
        check(date_key in dates, f"continuity group {group_id} uses an unknown date")
        check(isinstance(nodes, list) and bool(nodes) and len(nodes) == len(set(nodes)), f"continuity group {group_id} has missing or duplicated nodes")
        for node in nodes:
            check(node in markers or node in anchors or node in non_photo, f"continuity group {group_id} references an unknown public itinerary identity")
        for choice in group.get("choices", []):
            check(choice.get("default") != choice.get("alternative"), f"choice {choice.get('id')} repeats its default and alternate")
            check(choice.get("default") in nodes and choice.get("alternative") in nodes and choice.get("rejoins_at") in nodes, f"choice {choice.get('id')} has an endpoint outside {group_id}")

    timeline = {item.get("id"): item for item in data.get("timeline", [])}
    breaks = data.get("route_continuity_breaks", [])
    break_ids = [item.get("id") for item in breaks]
    check(len(break_ids) == len(set(break_ids)) and all(break_ids), "route continuity break IDs are missing or duplicated")
    for barrier in breaks:
        prefix = f"continuity break {barrier.get('id')}"
        before, after = group_by_id.get(barrier.get("from_group")), group_by_id.get(barrier.get("to_group"))
        row = timeline.get(barrier.get("barrier_timeline_id"))
        check(barrier.get("kind") in BREAK_KINDS, f"{prefix} has an untyped recovery/check-in barrier")
        check(before is not None and after is not None, f"{prefix} references an unknown continuity group")
        if before and after:
            check(before.get("date_key") == after.get("date_key") == barrier.get("date_key"), f"{prefix} crosses dates or has stale date ownership")
            check(before.get("id") != after.get("id"), f"{prefix} does not split route continuity")
            overlap = set(before.get("nodes", [])) & set(after.get("nodes", []))
            check(not overlap, f"{prefix} reuses a route node across a protected continuity break")
        check(row is not None and row.get("date_key") == barrier.get("date_key"), f"{prefix} lacks its timeline-owned barrier")
        if barrier.get("kind") == "protected_nap_return":
            check(row is not None and row.get("kind") == "travel" and row.get("travel_role") == "protected_nap_return", f"{prefix} is not a protected_nap_return timeline movement")
        if barrier.get("kind") == "lodging_checkin_reset":
            check(row is not None and row.get("kind") == "logistics" and any(term in str(row.get("id", "")).lower() for term in ("checkin", "reset")), f"{prefix} is not a lodging check-in/reset timeline event")

    legs = data.get("legs", [])
    leg_ids = [leg.get("leg_id") for leg in legs]
    check(len(leg_ids) == len(set(leg_ids)) and all(leg_ids), "semantic route leg IDs are missing or duplicated")
    check(set(geometry) == set(leg_ids), "route geometry cache does not exactly cover semantic route legs")
    active_edges: set[tuple[str, str, str]] = set()
    outgoing: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)

    for leg in legs:
        leg_id, date_key = leg.get("leg_id"), leg.get("date")
        start, end = leg.get("from"), leg.get("to")
        mode, branch = leg.get("mode"), leg.get("branch_kind", "main")
        group = group_by_id.get(leg.get("continuity_group"))
        entry = geometry.get(leg_id, {})
        prefix = f"route leg {leg_id}"
        check(date_key in dates, f"{prefix} uses an unknown date")
        check(mode in PUBLIC_MODES | {"ferry"}, f"{prefix} has an unsupported movement mode")
        check(start in markers or start in anchors, f"{prefix} has no public start endpoint")
        check(end in markers or end in anchors, f"{prefix} has no public end endpoint")
        check(group is not None and group.get("date_key") == date_key, f"{prefix} has no same-date continuity group")
        if group:
            check(start in group.get("nodes", []) and end in group.get("nodes", []), f"{prefix} crosses a protected recovery/check-in break or leaves its continuity group")
        if mode in PUBLIC_MODES:
            check(start in markers or start in anchors, f"{prefix} physical route start must be an explicit public map endpoint")
            check(end in markers or end in anchors, f"{prefix} physical route end must be an explicit public map endpoint")
        if start in markers and end in markers:
            for route in leg.get("routes", []):
                start_dates = {str(item.get("date_key") or item.get("date", "")).split(" ", 1)[0] for item in markers[start].get("occurrences", []) if item.get("route") == route}
                end_dates = {str(item.get("date_key") or item.get("date", "")).split(" ", 1)[0] for item in markers[end].get("occurrences", []) if item.get("route") == route}
                check(date_key in start_dates and date_key in end_dates, f"{prefix} endpoints do not occur on the same route/date")

        signature = [leg.get("from_latlon"), leg.get("to_latlon"), mode]
        check(entry.get("mode") == mode, f"geometry {leg_id} mode disagrees with its semantic edge")
        check(entry.get("endpoint_signature") == signature, f"geometry {leg_id} endpoint signature disagrees with its semantic edge")
        coords = entry.get("coordinates")
        status = entry.get("status")
        check(leg.get("geometry_kind") == status, f"semantic leg {leg_id} geometry status is stale")
        if mode in PUBLIC_MODES:
            if status == "routed_osm":
                check(isinstance(coords, list) and len(coords) > 2, f"normal public {mode} leg {leg_id} must have routed_osm geometry with more than two points")
                check(leg.get("render_style") == "cached_osm_reference_line", f"routed public leg {leg_id} uses a non-reference render style")
                check(bool(entry.get("source")) and entry.get("distance_km") is not None and entry.get("duration_min_reference") is not None, f"routed public leg {leg_id} lacks source, distance, or reference duration")
                if isinstance(coords, list) and len(coords) > 2 and isinstance(leg.get("from_latlon"), list) and isinstance(leg.get("to_latlon"), list):
                    start_gap = _distance_km([coords[0][1], coords[0][0]], leg["from_latlon"])
                    end_gap = _distance_km([coords[-1][1], coords[-1][0]], leg["to_latlon"])
                    endpoint_snap_limit = 0.2 if mode == "walk" else 0.65
                    check(start_gap <= endpoint_snap_limit and end_gap <= endpoint_snap_limit, f"routed public leg {leg_id} geometry endpoints are too far from the public places")
                straight = _distance_km(leg.get("from_latlon", []), leg.get("to_latlon", []))
                distance = entry.get("distance_km")
                max_distance = max(2.5 if mode == "walk" else 4.0, straight * (5 if mode == "walk" else 4.5))
                check(isinstance(distance, (int, float)) and distance >= straight * 0.9 and distance <= max_distance, f"routed public leg {leg_id} has implausible route distance")
            elif status == "intentionally_omitted":
                check(not coords, f"omitted public leg {leg_id} still carries drawable geometry")
                check(leg.get("render_style") == "omitted", f"omitted public leg {leg_id} is not marked non-renderable")
            else:
                check(False, f"normal public road/walk leg {leg_id} is not routed_osm or intentionally omitted")
            if status == "conceptual_fallback" and isinstance(coords, list) and len(coords) == 2:
                check(False, f"normal public {mode} leg {leg_id} has a two-point straight fallback")
        elif mode == "ferry":
            check(status == "conceptual_ferry", f"ferry relation {leg_id} must remain explicitly conceptual")
            check(isinstance(coords, list) and len(coords) == 2, f"conceptual ferry relation {leg_id} must retain endpoint-only geometry")
            check(leg.get("render_style") == "conceptual_ferry_dots", f"ferry relation {leg_id} must use the conceptual ferry style")

        check(branch in {"main", "swap"}, f"{prefix} has an unsupported branch type")
        if group:
            outgoing[(group["id"], start)].append(leg)
            active_edges.add((date_key, start, end))

    for group in groups:
        for choice in group.get("choices", []):
            default, alternate, rejoin = choice.get("default"), choice.get("alternative"), choice.get("rejoins_at")
            default_edges = [leg for leg in legs if leg.get("continuity_group") == group.get("id") and leg.get("from") == default and leg.get("to") == rejoin and leg.get("branch_kind") == "main"]
            check(len(default_edges) == 1, f"choice {choice.get('id')} default must join the shared path at its declared rejoin")
            outgoing_alternate = [leg for leg in legs if leg.get("continuity_group") == group.get("id") and leg.get("from") == alternate]
            check(len(outgoing_alternate) == 1 and outgoing_alternate[0].get("to") == rejoin and outgoing_alternate[0].get("branch_kind") == "swap" and outgoing_alternate[0].get("choice_id") == choice.get("id"), f"choice {choice.get('id')} alternate must join its shared path as one typed swap")
            for leg in legs:
                if leg.get("continuity_group") != group.get("id"):
                    continue
                if leg.get("from") == alternate or leg.get("to") == alternate:
                    allowed = leg.get("from") == alternate and leg.get("to") == rejoin and leg.get("branch_kind") == "swap" and leg.get("choice_id") == choice.get("id")
                    check(allowed, f"choice {choice.get('id')} is joined sequentially to the default path")
            adjacency: dict[str, set[str]] = defaultdict(set)
            for leg in legs:
                if leg.get("continuity_group") == group.get("id") and leg.get("branch_kind") != "swap":
                    adjacency[leg.get("from")].add(leg.get("to"))
            pending, seen = [default], {default}
            while pending:
                current = pending.pop()
                for neighbor in adjacency[current] - seen:
                    seen.add(neighbor)
                    pending.append(neighbor)
            check(alternate not in seen, f"choice {choice.get('id')} has a sequential path from its default into the alternate")

    omissions = data.get("route_graph_omissions", [])
    omission_ids = [item.get("omission_id") for item in omissions]
    check(len(omission_ids) == len(set(omission_ids)) and all(omission_ids), "route omission IDs are missing or duplicated")
    for omission in omissions:
        prefix = f"omitted route connection {omission.get('omission_id')}"
        check(omission.get("date_key") in dates and bool(omission.get("reason")), f"{prefix} lacks date or reason")
        if omission.get("from") and omission.get("to"):
            check((omission.get("date_key"), omission["from"], omission["to"]) not in active_edges, f"{prefix} is also present as an active route edge")

    archive = data.get("route_graph_legacy_range_archive", [])
    archived_ranges = [item.get("travel_range_id") for item in archive]
    check(len(archived_ranges) == len(set(archived_ranges)) and all(archived_ranges), "legacy travel-range archive contains duplicate or empty identities")

    if manifest is not None:
        manifest_legs = {item.get("leg_id"): item for item in manifest.get("legs", [])}
        check(set(manifest_legs) == set(leg_ids), "route manifest per-leg audit does not match semantic route legs")
        for leg_id, entry in geometry.items():
            row = manifest_legs.get(leg_id, {})
            check(row.get("status") == entry.get("status") and row.get("point_count") == len(entry.get("coordinates", [])), f"route manifest per-leg geometry is stale for {leg_id}")
            check(row.get("mode") == entry.get("mode") and row.get("endpoint_signature") == entry.get("endpoint_signature"), f"route manifest per-leg endpoint/mode audit is stale for {leg_id}")
        counts = manifest.get("counts", {})
        routed = sum(entry.get("status") == "routed_osm" and entry.get("mode") in PUBLIC_MODES for entry in geometry.values())
        conceptual = sum(entry.get("status") == "conceptual_ferry" for entry in geometry.values())
        unavailable = sum(entry.get("status") == "intentionally_omitted" for entry in geometry.values())
        check(counts.get("routed_public_legs") == routed, "route manifest routed public count is inaccurate")
        check(counts.get("conceptual_legs") == conceptual, "route manifest conceptual count is inaccurate")
        check(counts.get("intentionally_omitted_legs") == unavailable + len(omissions), "route manifest omitted count is inaccurate")

    return {
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "counts": {
            "semantic_public_route_legs": sum(leg.get("mode") in PUBLIC_MODES for leg in legs),
            "routed_osm_public_legs": sum(geometry.get(leg.get("leg_id"), {}).get("status") == "routed_osm" for leg in legs),
            "conceptual_ferry_legs": sum(leg.get("mode") == "ferry" for leg in legs),
            "geometry_unavailable_legs": sum(geometry.get(leg.get("leg_id"), {}).get("status") == "intentionally_omitted" for leg in legs),
            "intentionally_omitted_connections": len(omissions),
            "total_geometry_points": sum(len(entry.get("coordinates", [])) for entry in geometry.values()),
            "continuity_breaks": len(breaks),
        },
    }
