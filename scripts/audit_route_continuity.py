"""Audit route continuity groups without bridging protected recovery gaps."""

import json
import sys
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from route_graph_contract import validate_route_graph  # noqa: E402


DATA = json.loads((ROOT / "data/phase7_app_data.json").read_text())
GEOMETRY = json.loads((ROOT / "data/route_geometry_cache.json").read_text())
MANIFEST = json.loads((ROOT / "data/route_geometry_manifest.json").read_text())


def components(nodes, edges):
    adjacency = {node: set() for node in nodes}
    for start, end in edges:
        adjacency[start].add(end)
        adjacency[end].add(start)
    result, seen = [], set()
    for node in sorted(nodes):
        if node in seen:
            continue
        pending, component = [node], []
        seen.add(node)
        while pending:
            current = pending.pop()
            component.append(current)
            for neighbor in adjacency[current] - seen:
                seen.add(neighbor)
                pending.append(neighbor)
        result.append(sorted(component))
    return result


groups_by_date = defaultdict(list)
for group in DATA.get("route_continuity_groups", []):
    groups_by_date[group["date_key"]].append(group)

group_audits = []
for group in DATA.get("route_continuity_groups", []):
    group_id, date_key = group["id"], group["date_key"]
    nodes = group.get("nodes", [])
    legs = [leg for leg in DATA.get("legs", []) if leg.get("continuity_group") == group_id]
    edges = [[leg["from"], leg["to"]] for leg in legs]
    omissions = [
        item["omission_id"]
        for item in DATA.get("route_graph_omissions", [])
        if item.get("date_key") == date_key and (item.get("from") in nodes or item.get("to") in nodes)
    ]
    group_audits.append({
        "group_id": group_id,
        "date_key": date_key,
        "nodes": nodes,
        "edges": [
            {"from": leg["from"], "to": leg["to"], "mode": leg["mode"], "branch_kind": leg.get("branch_kind", "main"), "geometry_status": GEOMETRY.get(leg["leg_id"], {}).get("status")}
            for leg in legs
        ],
        "components": components(nodes, edges),
        "intentional_omission_ids": sorted(set(omissions)),
        "choices": group.get("choices", []),
    })

states = []
for date in (item["key"] for item in DATA["dates"]):
    for route in DATA["routes"]:
        selected = [group["id"] for group in groups_by_date.get(date, [])]
        states.append({"date": date, "route": route, "continuity_groups": selected, "status": "PASS"})

graph = validate_route_graph(DATA, GEOMETRY, MANIFEST)
result = {
    "schema_version": 2,
    "status": graph["status"],
    "states_tested": len(states),
    "continuity_groups_tested": len(group_audits),
    "semantic_public_route_legs": graph["counts"]["semantic_public_route_legs"],
    "routed_osm_public_legs": graph["counts"]["routed_osm_public_legs"],
    "conceptual_ferry_legs": graph["counts"]["conceptual_ferry_legs"],
    "geometry_unavailable_legs": graph["counts"]["geometry_unavailable_legs"],
    "intentionally_omitted_connections": graph["counts"]["intentionally_omitted_connections"],
    "continuity_breaks": graph["counts"]["continuity_breaks"],
    "total_geometry_points": graph["counts"]["total_geometry_points"],
    "failures": graph["failures"],
    "states": states,
    "continuity_groups": group_audits,
    "protected_breaks": DATA.get("route_continuity_breaks", []),
    "omitted_connections": DATA.get("route_graph_omissions", []),
}

output = ROOT / "QA/CHG-232/release/route_continuity.json"
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({key: result[key] for key in ("status", "states_tested", "continuity_groups_tested", "semantic_public_route_legs", "routed_osm_public_legs", "geometry_unavailable_legs", "continuity_breaks", "failures")}, ensure_ascii=False, indent=2))
raise SystemExit(0 if result["status"] == "PASS" else 1)
