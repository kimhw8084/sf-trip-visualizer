#!/usr/bin/env python3
"""Aggregate current Golden UI evidence for the canonical Gate 5 component.

The individual R5 suites remain the authoritative producers for their domains.
This runner binds their fresh outputs to the exact candidate, records a small
current-lineage performance sample, and returns VERIFY_REQUIRED only for
explicit external evidence boundaries.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "manifests" / "gate5_field_quality_contract.json"
EVIDENCE_ROOT = ROOT / "QA" / "CHG-204" / "gate5"
DEFAULT_OUTPUT = EVIDENCE_ROOT / "candidate.json"
BASELINE_OUTPUT = EVIDENCE_ROOT / "baseline.json"
PAIRED_OUTPUT = EVIDENCE_ROOT / "paired_comparison.json"
SUMMARY_OUTPUT = EVIDENCE_ROOT / "performance_summary.log"
FINDING_MATRIX = EVIDENCE_ROOT / "finding_matrix.json"
REVIEW_INDEX = EVIDENCE_ROOT / "review_pack_index.json"
UI_ROOT = ROOT / "QA" / "CHG-204"
CURRENT_EVIDENCE = {
    "decision_workbench": UI_ROOT / "decision_workbench" / "task_oracles.json",
    "accessibility_reflow": UI_ROOT / "accessibility.json",
    "sheet_geometry": UI_ROOT / "sheet_geometry.json",
    "route_key_camera": UI_ROOT / "route_key_camera.json",
    "map_geometry": UI_ROOT / "map_geometry.json",
    "cross_browser": UI_ROOT / "browser_summary.json",
    "visual_evidence": UI_ROOT / "visual" / "visual_index.json",
    "place_list_membership": UI_ROOT / "place_list_roles.json",
    "provider_recovery": ROOT / "QA" / "CHG-204" / "release" / "gate4_runtime.json",
}
SOURCE_EXCLUDED_PREFIXES = ("QA/", ".build/", ".release/", ".public-site/")
REQUIRED_PAIRED_BASELINE_REVISION = "7d5d8727b1772642e87311d91d087e211656f6e4"
REQUIRED_PAIRED_BASELINE_TREE = "ede888516de0dc9c8554036435ae9f8034aaea4f"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def revision() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def tree() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT, text=True).strip()


def source_paths() -> list[str]:
    paths = subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=all"], cwd=ROOT, text=True).splitlines()
    result = []
    for row in paths:
        path = row[3:].strip().strip('"') if len(row) >= 4 else ""
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        if path and not path.startswith(SOURCE_EXCLUDED_PREFIXES):
            result.append(path)
    return result


def source_binding(expected_revision: str | None) -> dict:
    actual = revision()
    actual_tree = tree()
    dirty = source_paths()
    if expected_revision and expected_revision != actual:
        return {"binding": "mismatch", "status": "FAIL", "claimed_revision": expected_revision, "checked_out_revision": actual, "checked_out_tree": actual_tree, "source_worktree_dirty": bool(dirty), "reason": "checked-out revision does not match the claimed candidate"}
    if dirty:
        return {"binding": "source_fingerprint", "status": "FAIL", "claimed_revision": expected_revision, "checked_out_revision": actual, "checked_out_tree": actual_tree, "source_worktree_dirty": True, "dirty_paths": dirty, "reason": "source files changed after checkout"}
    return {"binding": "exact_commit", "status": "PASS", "claimed_revision": expected_revision, "checked_out_revision": actual, "checked_out_tree": actual_tree, "source_worktree_dirty": False, "reason": "clean checkout is bound to the exact checked-out revision"}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def quantiles(values: list[float]) -> dict:
    ordered = sorted(float(value) for value in values)
    return {
        "count": len(ordered),
        "min_ms": round(ordered[0], 3) if ordered else None,
        "median_ms": round(statistics.median(ordered), 3) if ordered else None,
        "max_ms": round(ordered[-1], 3) if ordered else None,
        "mean_ms": round(statistics.mean(ordered), 3) if ordered else None,
        "stdev_ms": round(statistics.stdev(ordered), 3) if len(ordered) > 1 else 0.0,
    }


def evidence_row(name: str, path: Path, expected_revision: str, expected_tree: str, started_ns: int) -> tuple[dict, list[str]]:
    row = {"name": name, "path": str(path.relative_to(ROOT)), "status": "FAIL"}
    failures: list[str] = []
    if not path.is_file():
        failures.append(f"{name}: missing evidence output")
        row["execution_status"] = "MISSING"
        return row, failures
    row["sha256"] = digest(path)
    row["mtime_ns"] = path.stat().st_mtime_ns
    if started_ns and path.stat().st_mtime_ns <= started_ns:
        failures.append(f"{name}: stale evidence output")
        row["execution_status"] = "STALE"
    try:
        payload = json.loads(path.read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        failures.append(f"{name}: malformed JSON ({error})")
        row["execution_status"] = "MALFORMED"
        return row, failures
    if not isinstance(payload, dict):
        failures.append(f"{name}: evidence must be a JSON object")
        row["execution_status"] = "MALFORMED"
        return row, failures
    row["reported_status"] = payload.get("status")
    row["candidate"] = payload.get("candidate", payload.get("candidate_head"))
    row["candidate_tree"] = payload.get("candidate_tree")
    row["candidate_binding"] = payload.get("candidate_binding")
    if payload.get("status") != "PASS":
        failures.append(f"{name}: status is {payload.get('status')!r}")
    if payload.get("candidate") != expected_revision and payload.get("candidate_head") != expected_revision:
        failures.append(f"{name}: wrong candidate binding")
    if payload.get("candidate_tree") != expected_tree:
        failures.append(f"{name}: wrong candidate tree binding")
    if payload.get("candidate_binding") != "exact-clean-checkout" and name != "provider_recovery":
        failures.append(f"{name}: non-exact or non-clean source binding")
    if payload.get("failures"):
        failures.append(f"{name}: contradictory failures are present")
    if payload.get("errors"):
        failures.append(f"{name}: errors are present")
    row["status"] = "PASS" if not failures else "FAIL"
    return row, failures


def provider_row(path: Path, expected_revision: str, started_ns: int) -> tuple[dict, list[str]]:
    row = {"name": "provider_recovery", "path": str(path.relative_to(ROOT)), "status": "FAIL"}
    failures: list[str] = []
    if not path.is_file():
        return {**row, "execution_status": "MISSING"}, ["provider_recovery: missing evidence output"]
    row["sha256"] = digest(path)
    row["mtime_ns"] = path.stat().st_mtime_ns
    if started_ns and path.stat().st_mtime_ns <= started_ns:
        failures.append("provider_recovery: stale evidence output")
    try:
        payload = json.loads(path.read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        return {**row, "execution_status": "MALFORMED"}, [f"provider_recovery: malformed JSON ({error})"]
    if not isinstance(payload, dict):
        return {**row, "execution_status": "MALFORMED"}, ["provider_recovery: evidence must be a JSON object"]
    external = payload.get("external_provider") or {}
    deterministic = payload.get("deterministic_provider") or {}
    row.update({"reported_status": payload.get("status"), "candidate_head": payload.get("candidate_head"), "deterministic_provider": deterministic, "external_provider": external})
    if payload.get("candidate_head") != expected_revision:
        failures.append("provider_recovery: wrong candidate binding")
    if payload.get("status") != "PASS":
        failures.append(f"provider_recovery: status is {payload.get('status')!r}")
    if deterministic.get("status") != "PASS":
        failures.append(f"provider_recovery: deterministic Satellite recovery is {deterministic.get('status')!r}")
    if payload.get("failures") or payload.get("errors"):
        failures.append("provider_recovery: errors or contradictory failures are present")
    row["status"] = "PASS" if not failures else "FAIL"
    return row, failures


def measure_performance_page(browser, url: str, label: str, sample: int, order: int) -> dict:
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()
    try:
        started = time.perf_counter()
        page.goto(url, wait_until="domcontentloaded", timeout=90000)
        dom_content_ms = (time.perf_counter() - started) * 1000
        page.wait_for_function("window.__tripApp?.map()?.isStyleLoaded()", timeout=30000)
        smart_style_ms = (time.perf_counter() - started) * 1000
        page.wait_for_function("window.__tripApp?.state?.runtime?.mapVisualReady === true", timeout=30000)
        ready_ms = (time.perf_counter() - started) * 1000
        return {"label": label, "sample": sample, "order": order, "dom_content_ms": round(dom_content_ms, 3), "smart_style_ready_ms": round(smart_style_ms, 3), "first_actionable_state_ms": round(ready_ms, 3), "markers": page.locator(".photo-marker").count(), "map_layers": page.evaluate("window.__tripApp?.map()?.getStyle?.()?.layers?.length || 0")}
    finally:
        context.close()


def current_performance(url: str, samples: int) -> dict:
    rows = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        browser_version = browser.version
        for sample in range(1, samples + 1):
            rows.append(measure_performance_page(browser, url, "candidate", sample, 0))
        browser.close()
    return {"status": "MEASURED", "comparison_status": "VERIFY_REQUIRED", "environment": {"platform": platform.platform(), "python": sys.version.split()[0], "browser": "Chromium", "browser_version": browser_version, "viewport": "1440x900", "headless": True, "url": url, "sample_count": samples}, "samples": rows, "metrics": {key: quantiles([row[key] for row in rows]) for key in ("dom_content_ms", "smart_style_ready_ms", "first_actionable_state_ms")}}


def paired_performance(candidate_url: str, baseline_url: str, samples: int, baseline_revision: str, baseline_tree: str) -> dict:
    rows = {"baseline": [], "candidate": []}
    ordering = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        browser_version = browser.version
        for sample in range(1, samples + 1):
            variant_order = (("baseline", baseline_url), ("candidate", candidate_url)) if sample % 2 else (("candidate", candidate_url), ("baseline", baseline_url))
            for order, (label, url) in enumerate(variant_order):
                ordering.append({"sample": sample, "label": label, "order": order})
                rows[label].append(measure_performance_page(browser, url, label, sample, order))
        browser.close()
    metric_names = ("dom_content_ms", "smart_style_ready_ms", "first_actionable_state_ms")
    deltas = [{"sample": index, "deltas": {key: round(rows["candidate"][index - 1][key] - rows["baseline"][index - 1][key], 3) for key in metric_names}} for index in range(1, samples + 1)]
    comparison = {}
    for key in metric_names:
        values = [row["deltas"][key] for row in deltas]
        comparison[key] = {"mean_ms": round(statistics.mean(values), 3), "median_ms": round(statistics.median(values), 3), "stdev_ms": round(statistics.stdev(values), 3) if len(values) > 1 else 0.0, "slower_count": sum(value > 0 for value in values), "material_slower_200ms_count": sum(value > 200 for value in values)}
    material = any(row["mean_ms"] > 250 or row["material_slower_200ms_count"] >= max(6, (samples + 1) // 2) for row in comparison.values())
    noisy_direction = any(row["slower_count"] >= max(5, (samples + 1) // 2 + 1) for row in comparison.values())
    comparison_status = "FIX_REQUIRED" if material else "VERIFY_REQUIRED" if noisy_direction else "PASS"
    environment = {"platform": platform.platform(), "python": sys.version.split()[0], "browser": "Chromium", "browser_version": browser_version, "viewport": "1440x900", "headless": True, "sample_count_per_variant": samples, "ordering": ordering, "candidate_url": candidate_url, "baseline_url": baseline_url, "baseline_revision": baseline_revision, "baseline_tree": baseline_tree}
    return {"status": "PAIRED", "comparison_status": comparison_status, "environment": environment, "baseline": {"revision": baseline_revision, "tree": baseline_tree, "samples": rows["baseline"], "metrics": {key: quantiles([row[key] for row in rows["baseline"]]) for key in metric_names}}, "candidate": {"samples": rows["candidate"], "metrics": {key: quantiles([row[key] for row in rows["candidate"]]) for key in metric_names}}, "comparison": comparison, "deltas": deltas}


def write_auxiliary(report: dict, performance: dict) -> None:
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
    paired = performance.get("status") == "PAIRED"
    BASELINE_OUTPUT.write_text(json.dumps({"schema_version": 1, "status": "PASS" if paired else "VERIFY_REQUIRED", "candidate_revision": report["candidate_head"], "baseline": performance.get("baseline"), "reason": None if paired else "No exact same-environment paired current-main baseline was claimed; historical R5 evidence is excluded."}, ensure_ascii=False, indent=2) + "\n")
    PAIRED_OUTPUT.write_text(json.dumps({"schema_version": 1, "status": performance.get("comparison_status", "VERIFY_REQUIRED"), "candidate_revision": report["candidate_head"], "performance": performance}, ensure_ascii=False, indent=2) + "\n")
    FINDING_MATRIX.write_text(json.dumps({"schema_version": 1, "candidate_revision": report["candidate_head"], "suites": report["evidence"], "external_boundaries": report["verify_required"], "status": report["status"]}, ensure_ascii=False, indent=2) + "\n")
    screenshot_paths = [str(path.relative_to(ROOT)) for path in sorted(UI_ROOT.rglob("*.png"))]
    REVIEW_INDEX.write_text(json.dumps({"schema_version": 1, "candidate_revision": report["candidate_head"], "source": "CHG-204 current single-route qualification", "screenshots": screenshot_paths}, ensure_ascii=False, indent=2) + "\n")
    lines = ["gate5_performance_summary schema=1", f"candidate_revision={report['candidate_head']}", f"candidate_tree={report['candidate_tree']}", f"environment={json.dumps(performance.get('environment', {}), sort_keys=True)}"]
    for metric, values in performance.get("metrics", {}).items():
        lines.append(f"metric={metric} distribution={json.dumps(values, sort_keys=True)}")
    for metric, values in performance.get("comparison", {}).items():
        lines.append(f"comparison={metric} result={json.dumps(values, sort_keys=True)}")
    lines.append(f"status={performance.get('comparison_status', 'VERIFY_REQUIRED')}")
    SUMMARY_OUTPUT.write_text("\n".join(lines) + "\n")


def process_exit_code(status: str) -> int:
    return 0 if status in {"PASS", "VERIFY_REQUIRED"} else 1


def performance_terminal_status(performance: dict | None) -> str:
    """Preserve performance evidence status; rc0 never promotes it."""
    if not isinstance(performance, dict):
        return "FAIL"
    status = performance.get("comparison_status")
    return status if status in {"PASS", "VERIFY_REQUIRED"} else "FAIL"


def run(expected_revision: str | None, output: Path) -> dict:
    started_ns = int(os.environ.get("TRIP_GATE5_EVIDENCE_STARTED_NS", "0"))
    binding = source_binding(expected_revision)
    candidate = revision()
    candidate_tree = tree()
    report = {"schema_version": 1, "gate": "production_readiness_gate_5", "status": "FAIL", "candidate_head": candidate, "candidate_tree": candidate_tree, "source_binding": binding, "contract": str(CONTRACT_PATH.relative_to(ROOT)), "captured_at": now(), "evidence_started_ns": started_ns, "evidence": [], "performance": {}, "verify_required": [], "failures": []}
    if binding["status"] != "PASS":
        report["failures"].append(binding["reason"])
    else:
        for name, path in CURRENT_EVIDENCE.items():
            if name == "provider_recovery":
                row, failures = provider_row(path, expected_revision or candidate, started_ns)
            else:
                row, failures = evidence_row(name, path, expected_revision or candidate, candidate_tree, started_ns)
            report["evidence"].append(row)
            report["failures"].extend(failures)
        url = os.environ.get("TRIP_QA_URL", "http://127.0.0.1:8768/index.html")
        samples = max(8, int(os.environ.get("TRIP_GATE5_PERFORMANCE_SAMPLES", "8")))
        try:
            baseline_url = os.environ.get("TRIP_GATE5_BASELINE_URL") or os.environ.get("TRIP_BASELINE_URL", "")
            baseline_revision = os.environ.get("TRIP_GATE5_BASELINE_REVISION") or os.environ.get("TRIP_BASELINE_REVISION", "")
            baseline_tree = os.environ.get("TRIP_GATE5_BASELINE_TREE") or os.environ.get("TRIP_BASELINE_TREE", "")
            if baseline_url:
                if baseline_revision != REQUIRED_PAIRED_BASELINE_REVISION or baseline_tree != REQUIRED_PAIRED_BASELINE_TREE:
                    report["failures"].append("paired performance baseline identity is not the requested clean authoritative main")
                else:
                    report["performance"] = paired_performance(url, baseline_url, samples, baseline_revision, baseline_tree)
                    if report["performance"].get("comparison_status") == "FIX_REQUIRED":
                        report["failures"].append("matched exact-main-versus-candidate performance comparison classified a material regression")
                    elif report["performance"].get("comparison_status") == "VERIFY_REQUIRED":
                        report["verify_required"].append("matched exact-main-versus-candidate performance remained directionally noisy after balanced repeated sampling")
            else:
                report["performance"] = current_performance(url, samples)
                report["verify_required"].append("current-lineage performance was measured, but no exact same-environment paired current-main baseline was available")
        except Exception as error:
            report["failures"].append(f"current-lineage performance measurement failed: {type(error).__name__}: {error}")
        if report["performance"] and performance_terminal_status(report["performance"]) == "FAIL":
            report["failures"].append("performance evidence has no accepted PASS or VERIFY_REQUIRED terminal comparison status")
        report["verify_required"] = [
            "native Safari remote automation is unavailable; Playwright WebKit is not a native Safari substitute",
            "no verifiably real iPhone or iPad is available in this execution environment",
            "independent candidate-bound multimodal visual/usability review is not supplied",
            *(["current-lineage performance was measured, but no exact same-environment paired current-main baseline was available"] if not report["performance"].get("status") == "PAIRED" else []),
            *(["matched exact-main-versus-candidate performance remained directionally noisy after balanced repeated sampling"] if report["performance"].get("comparison_status") == "VERIFY_REQUIRED" else []),
        ]
        external = next((row.get("external_provider") for row in report["evidence"] if row["name"] == "provider_recovery"), {})
        report["supplemental_external_provider"] = external
    if not report["failures"]:
        report["status"] = "VERIFY_REQUIRED" if report["verify_required"] else "PASS"
    report["completed_at"] = now()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    write_auxiliary(report, report["performance"])
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-revision")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    report = run(args.expected_revision, Path(args.output).resolve())
    print(json.dumps({"status": report["status"], "candidate_head": report["candidate_head"], "failures": report["failures"], "verify_required": report["verify_required"]}, ensure_ascii=False))
    return process_exit_code(report["status"])


if __name__ == "__main__":
    raise SystemExit(main())
