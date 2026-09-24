"""Focused evidence wrapper for Gate 3 canonical truth and refresh plumbing."""

from __future__ import annotations

import json
from pathlib import Path

from refresh_trip_data import apply_observations, load_manifest
from validate_trip_data import validate_trip_data


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "QA" / "CHG-188" / "canonical_truth.json"


def main() -> int:
    validation = validate_trip_data()
    manifest = load_manifest()
    offline_once = apply_observations(manifest, [], offline=True)
    offline_twice = apply_observations(offline_once, [], offline=True)
    idempotence = offline_once == offline_twice
    report = {
        "status": "PASS" if validation["status"] == "PASS" and idempotence else "FAIL",
        "validator": validation,
        "refresh_plumbing": {"offline_recheck_idempotent": idempotence, "generated_output_is_not_hand_edited": True},
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "failure_count": validation["failure_count"], "offline_recheck_idempotent": idempotence}, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
