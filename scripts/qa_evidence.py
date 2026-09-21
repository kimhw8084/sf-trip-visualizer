"""Fail-closed identity helpers for decisive browser evidence."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GENERATED_PREFIXES = (
    "QA/",
    ".build/",
    ".public-site/",
    ".release/",
    "release-path-checkout/",
)


def candidate_identity() -> dict[str, str]:
    expected = os.environ.get("TRIP_EXPECTED_REVISION") or os.environ.get("TRIP_CANDIDATE_SHA")
    actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    tree = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT, text=True).strip()
    if not expected:
        raise RuntimeError("Decisive evidence requires TRIP_EXPECTED_REVISION or TRIP_CANDIDATE_SHA.")
    if expected != actual:
        raise RuntimeError(f"Expected candidate {expected}, checked out {actual}.")
    dirty_paths = []
    for line in subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).splitlines():
        path = line[3:].strip().strip('"')
        if not path.startswith(GENERATED_PREFIXES):
            dirty_paths.append(path)
    if dirty_paths:
        raise RuntimeError("Decisive evidence requires a clean source worktree: " + ", ".join(dirty_paths))
    return {"sha": actual, "tree": tree}


def bind_report(report: dict, identity: dict[str, str]) -> dict:
    report["candidate"] = identity["sha"]
    report["candidate_tree"] = identity["tree"]
    report["candidate_binding"] = "exact-clean-checkout"
    return report
