"""Audit every route/date marker graph and the semantics of non-literal links."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = json.loads((ROOT / "data/phase7_app_data.json").read_text())


def components(nodes, edges):
    adjacency = {node: set() for node in nodes}
    for start, end in edges:
        adjacency[start].add(end)
        adjacency[end].add(start)
    result = []
    seen = set()
    for node in sorted(nodes):
        if node in seen:
            continue
        pending = [node]
        seen.add(node)
        component = []
        while pending:
            current = pending.pop()
            component.append(current)
            for neighbor in adjacency[current]:
                if neighbor not in seen:
                    seen.add(neighbor)
                    pending.append(neighbor)
        result.append(sorted(component))
    return result


states = []
failures = []
for date in (item["key"] for item in DATA["dates"]):
    for route in DATA["routes"]:
        nodes = {
            marker["place_key"]
            for marker in DATA["markers"]
            if any(occ["route"] == route and occ["date"].startswith(date) for occ in marker["occurrences"])
        }
        edges = [
            [leg["from"], leg["to"]]
            for leg in DATA["legs"]
            if leg["date"] == date and route in leg["routes"] and leg["from"] in nodes and leg["to"] in nodes
        ]
        groups = components(nodes, edges)
        passed = len(nodes) < 2 or len(groups) == 1
        row = {"date": date, "route": route, "markers": len(nodes), "edges": len(edges), "components": groups, "status": "PASS" if passed else "FAIL"}
        states.append(row)
        if not passed:
            failures.append(row)

semantic_links = [leg for leg in DATA["legs"] if leg.get("branch_kind") in {"recovery", "choice"}]
semantic_pass = all(leg.get("label") and leg.get("note") for leg in semantic_links)
result = {
    "status": "PASS" if not failures and semantic_pass else "FAIL",
    "states_tested": len(states),
    "connected_multi_marker_states": sum(row["status"] == "PASS" and row["markers"] >= 2 for row in states),
    "failures": failures,
    "semantic_links": [{key: leg[key] for key in ("leg_id", "date", "from", "to", "routes", "branch_kind", "label", "note")} for leg in semantic_links],
    "states": states,
}
output = ROOT / "QA/CHG-188/release/route_continuity.json"
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({key: result[key] for key in ("status", "states_tested", "connected_multi_marker_states", "failures")}, ensure_ascii=False, indent=2))
raise SystemExit(0 if result["status"] == "PASS" else 1)
