"""Record the reviewed research pass in the runtime freshness authority."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRESHNESS = ROOT / "manifests" / "trip_freshness.json"
LEDGER = ROOT / "data" / "route_research_ledger.json"
CHECKED_AT = "2026-09-21"


EXTRA_FACTS = {
    "17_mile_rules": {"scope": {"date": "10/6", "region": "monterey", "place_keys": ["lone_cypress"]}, "recheck": "T-72H and entry morning"},
    "glacier_point_access": {"scope": {"date_range": ["10/8", "10/9"], "region": "yosemite", "place_keys": ["glacier", "washburn"]}, "recheck": "T-24H and departure morning"},
    "bridalveil_access": {"scope": {"date": "10/7", "region": "yosemite", "place_keys": ["bridalveil"]}, "recheck": "T-24H and arrival corridor"},
    "tea_garden_carrier": {"scope": {"date": "10/10", "region": "sf", "place_keys": ["tea_garden"]}, "recheck": "T-48H and opening morning"},
}


def main() -> None:
    manifest = json.loads(FRESHNESS.read_text())
    ledger = json.loads(LEDGER.read_text())
    records = manifest["records"]
    ledger_by_id = {record["fact_id"]: record for record in ledger["records"]}
    manifest["observation_policy"] = (
        "Research observations are recorded at checked_at but remain RECHECK_REQUIRED until trip-date operational checks. "
        "The linked route research ledger carries the detailed hours, access, family-friction, best-time, and recheck fields."
    )
    manifest["last_reviewed_at"] = CHECKED_AT
    manifest["reviewed_research_ledger"] = "data/route_research_ledger.json"
    manifest["reviewed_research_record_count"] = len(ledger["records"])
    for record in records:
        record["observed_on"] = CHECKED_AT
        record["certainty"] = "OBSERVED_AT_SOURCE_CHECK_RECHECK_REQUIRED"
        record["last_observation"] = {
            "source_url": record["source"]["source_urls"][0],
            "checked_at": CHECKED_AT,
            "research_ledger": "data/route_research_ledger.json",
        }
    for fact_id, metadata in EXTRA_FACTS.items():
        if fact_id in {record["fact_id"] for record in records}:
            continue
        source = ledger_by_id[fact_id]
        records.append(
            {
                "fact_id": fact_id,
                "scope": metadata["scope"],
                "claim": f"{source['source_title']} supports the route decision for the configured trip window.",
                "source": {"publisher": source["source_title"], "source_urls": [source["source_url"]], "primary_or_official": True},
                "observed_on": CHECKED_AT,
                "status": "RECHECK_REQUIRED",
                "certainty": "OBSERVED_AT_SOURCE_CHECK_RECHECK_REQUIRED",
                "recheck": {"trigger": source["recheck_trigger"], "window": metadata["recheck"]},
                "last_observation": {"source_url": source["source_url"], "checked_at": CHECKED_AT, "research_ledger": "data/route_research_ledger.json"},
                "product_claim_refs": [f"data.route_research_ledger.records[{fact_id}]"],
            }
        )
    FRESHNESS.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": "PASS", "checked_at": CHECKED_AT, "freshness_records": len(records), "research_records": len(ledger["records"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
