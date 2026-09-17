"""Deterministic pre-trip freshness refresh for the static trip client.

The command accepts reviewed observations rather than scraping. That keeps the
repository local-first and makes an unavailable external source fail closed.
After a refresh it runs the canonical fast pipeline, which rebuilds generated
artifacts without hand-editing the embedded runtime output.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "manifests" / "trip_freshness.json"
ALLOWED_STATUS = {"VERIFIED", "STALE", "UNVERIFIED", "RECHECK_REQUIRED", "NOT_APPLICABLE"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text())


def validate_observations(manifest: dict, observations: list[dict]) -> None:
    records = {record["fact_id"]: record for record in manifest["records"]}
    seen: set[str] = set()
    for observation in observations:
        fact_id = observation.get("fact_id")
        if fact_id not in records:
            raise ValueError(f"Unknown freshness fact_id: {fact_id}")
        if fact_id in seen:
            raise ValueError(f"Duplicate observation: {fact_id}")
        seen.add(fact_id)
        status = observation.get("status")
        if status not in ALLOWED_STATUS:
            raise ValueError(f"Invalid status for {fact_id}: {status}")
        observed_on = observation.get("observed_on")
        if observed_on is not None and not DATE_RE.fullmatch(str(observed_on)):
            raise ValueError(f"Invalid observed_on for {fact_id}: {observed_on}")
        if status == "VERIFIED" and observed_on is None:
            raise ValueError(f"VERIFIED observation requires observed_on: {fact_id}")
        source_url = observation.get("source_url")
        allowed_sources = records[fact_id].get("source", {}).get("source_urls", [])
        if not source_url or source_url not in allowed_sources or urlparse(source_url).scheme not in {"http", "https"}:
            raise ValueError(f"Observation source_url must be one of the fact's declared sources: {fact_id}")
        if not observation.get("certainty"):
            raise ValueError(f"Observation certainty is required: {fact_id}")


def apply_observations(manifest: dict, observations: list[dict], *, offline: bool = False) -> dict:
    """Return a deterministic manifest copy; never performs I/O."""

    result = copy.deepcopy(manifest)
    if offline:
        for record in result["records"]:
            record["observed_on"] = None
            record["status"] = "RECHECK_REQUIRED"
            record["certainty"] = "NOT_CURRENTLY_VERIFIED"
            record.pop("last_observation", None)
        return result
    validate_observations(result, observations)
    by_id = {observation["fact_id"]: observation for observation in observations}
    for record in result["records"]:
        observation = by_id.get(record["fact_id"])
        if not observation:
            continue
        record["observed_on"] = observation.get("observed_on")
        record["status"] = observation["status"]
        record["certainty"] = observation["certainty"]
        record["last_observation"] = {
            "source_url": observation["source_url"],
            "note": observation.get("note", ""),
        }
    return result


def write_manifest(manifest: dict) -> bool:
    payload = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    if MANIFEST_PATH.read_text() == payload:
        return False
    MANIFEST_PATH.write_text(payload)
    return True


def run_fast() -> dict:
    process = subprocess.run([sys.executable, str(ROOT / "scripts" / "pipeline.py"), "fast"], cwd=ROOT, text=True, capture_output=True)
    return {"status": "PASS" if process.returncode == 0 else "FAIL", "returncode": process.returncode, "stdout_tail": process.stdout[-3000:], "stderr_tail": process.stderr[-3000:]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate")
    refresh = subparsers.add_parser("refresh")
    refresh.add_argument("--offline", action="store_true", help="record an explicit fail-closed recheck state without network access")
    refresh.add_argument("--observations", type=Path, help="reviewed JSON list or {observations: [...]} payload")
    args = parser.parse_args()
    manifest = load_manifest()
    if args.command == "validate":
        from validate_trip_data import validate_trip_data

        report = validate_trip_data()
        print(json.dumps({"status": report["status"], "freshness_records": report["counts"]["freshness_records"], "failures": report["failures"][:20]}, ensure_ascii=False, indent=2))
        return 0 if report["status"] == "PASS" else 1

    if not args.offline and not args.observations:
        parser.error("refresh requires --offline or --observations <file>")
    observations: list[dict] = []
    if args.observations:
        payload = json.loads(args.observations.read_text())
        observations = payload.get("observations", []) if isinstance(payload, dict) else payload
        if not isinstance(observations, list):
            raise SystemExit("Observation file must be a JSON list or an object with an observations list.")
    updated = apply_observations(manifest, observations, offline=args.offline)
    changed = write_manifest(updated)
    fast = run_fast()
    print(json.dumps({"status": fast["status"], "mode": "offline" if args.offline else "observations", "manifest_changed": changed, "pipeline": fast}, ensure_ascii=False, indent=2))
    return 0 if fast["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
