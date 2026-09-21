#!/usr/bin/env python3
"""Canonical source, build, QA, packaging, and release pipeline.

The pipeline is deliberately a small Python orchestrator around the existing
map-first and browser suites. It is the only supported release authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from validate_trip_data import validate_trip_data
from qa_gate4_resilience import delivery_report
from public_asset_rights import audit_tree, load_contract, load_json as load_rights_json, write_notices
from hosted_linux_pipeline import contract_failures

MANIFEST_PATH = ROOT / "manifests" / "canonical_pipeline.json"
BUILD = ROOT / ".build"
PUBLIC = ROOT / ".public-site"
RELEASE = ROOT / ".release"
FAST_EVIDENCE = ROOT / "QA" / "release" / "fast.json"
QUALIFICATION = ROOT / "QA" / "release" / "qualification.json"
GATE4_STATIC = ROOT / "QA" / "release" / "gate4_static.json"
GATE4_RUNTIME = ROOT / "QA" / "release" / "gate4_runtime.json"
GATE4_SUMMARY = ROOT / "QA" / "release" / "gate4.json"
SECURITY_EVIDENCE = ROOT / "QA" / "release" / "security_privacy.json"
COMPONENT_TIMEOUT_SECONDS = int(os.environ.get("TRIP_QUALIFICATION_TIMEOUT_SECONDS", "300"))

COMPONENTS = (
    ("canonical_truth", "scripts/qa_canonical_truth.py", "QA/map_first/canonical_truth.json"),
    ("photo_integrity", "scripts/check_photo_integrity.py", "QA/photo_integrity.json"),
    ("maplibre_security", "scripts/qa_maplibre_security.py", "QA/release/maplibre_security.json"),
    ("map_first_smoke", "scripts/qa_map_first.py", "QA/map_first/smoke.json"),
    ("decision_workbench", "scripts/qa_decision_workbench.py", "QA/project_os_verify/ui_revamp_r4/task_oracles.json"),
    ("accessibility_reflow", "scripts/qa_accessibility_reflow.py", "QA/project_os_verify/ui_revamp_r4/accessibility.json"),
    ("map_geometry", "scripts/qa_map_geometry.py", "QA/project_os_verify/ui_revamp_r4/map_geometry.json"),
    ("sheet_geometry", "scripts/qa_sheet_geometry.py", "QA/project_os_verify/ui_revamp_r4/sheet_geometry.json"),
    ("map_first_full", "scripts/qa_map_first_full.py", "QA/map_first/full_acceptance.json"),
    ("map_first_p0", "scripts/qa_map_first_p0.py", "QA/map_first/p0_independent.json"),
    ("standalone", "scripts/qa_standalone_map_first.py", "QA/map_first/standalone.json"),
    ("location_gap", "scripts/qa_location_gap_visuals.py", "QA/map_first/location_gap_visuals.json"),
    ("interaction_dynamics", "scripts/qa_interaction_dynamics.py", "QA/map_first/interaction_dynamics.json"),
    ("route_continuity", "scripts/audit_route_continuity.py", "QA/map_first/route_continuity.json"),
    ("route_panel", "scripts/qa_route_explanations_panel.py", "QA/route_panel/route_explanations_panel.json"),
    ("exhaustive_states", "scripts/run_exhaustive_states.py", "QA/map_first/exhaustive_states.json"),
    ("cross_browser", "scripts/run_cross_browser.py", "QA/project_os_verify/ui_revamp_r4/browser_summary.json"),
    ("visual_spots", "scripts/run_visual_spots.py", "QA/project_os_verify/ui_revamp_r4/visual_index.json"),
    ("gate4_runtime", "scripts/qa_gate4_resilience.py", "QA/release/gate4_runtime.json"),
)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def tree_hashes(root: Path, exclude: set[str] | None = None) -> dict[str, str]:
    exclude = exclude or set()
    return {
        str(path.relative_to(root)): digest(path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and str(path.relative_to(root)) not in exclude
    }


def tree_digest(root: Path, exclude: set[str] | None = None) -> tuple[str, int, int]:
    files = tree_hashes(root, exclude)
    hasher = hashlib.sha256()
    for relative, file_hash in files.items():
        hasher.update(relative.encode())
        hasher.update(b"\0")
        hasher.update(bytes.fromhex(file_hash))
        hasher.update(b"\n")
    return hasher.hexdigest(), len(files), sum((root / relative).stat().st_size for relative in files)


def current_revision() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def working_tree_clean() -> bool:
    return not subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()


def pipeline_manifest() -> dict:
    return load_json(MANIFEST_PATH)


def authored_snapshot(manifest: dict) -> dict[str, str]:
    missing = [path for path in manifest["authored_inputs"] if not (ROOT / path).is_file()]
    if missing:
        raise RuntimeError(f"Missing canonical authored input(s): {', '.join(missing)}")
    return {path: digest(ROOT / path) for path in manifest["authored_inputs"]}


def validate_product() -> dict:
    manifest = pipeline_manifest()
    expected = manifest["invariants"]
    data = load_json(ROOT / manifest["authority"]["canonical_data"])
    asset_manifest = load_json(ROOT / "manifests" / "asset_manifest.json")
    routes = data["routes"]
    providers = sorted(data["providers"])
    regions = sorted(key for key in data["region_cfg"] if key != "overall")
    vector_path = ROOT / "assets" / "vector" / "sf_trip.pmtiles"
    vector_header = vector_path.read_bytes()[:64]
    marker_keys = [marker["place_key"] for marker in data["markers"]]
    if len(marker_keys) != len(set(marker_keys)):
        raise RuntimeError("Canonical data contains duplicate physical place keys.")
    truth_report = validate_trip_data()
    if truth_report["status"] != "PASS":
        raise RuntimeError("Canonical truth validation failed: " + "; ".join(truth_report["failures"][:12]))
    checks = {
        "places": len(marker_keys) == expected["places"],
        "photos": len(asset_manifest["assets"]) == expected["photos"] and asset_manifest["required_assets"] == expected["photos"],
        "timeline_cards": len(data["timeline"]) == expected["timeline_cards"],
        "route_legs": len(data["legs"]) == expected["route_legs"],
        "route_strategies": len(routes) == expected["route_strategies"] and sorted(routes) == ["A1", "A2", "B1", "B2"],
        "dates": len(data["dates"]) == expected["dates"],
        "regions": len(regions) == expected["regions"] and regions == ["monterey", "sf", "yosemite"],
        "providers": set(providers) == set(expected["providers"]),
        "place_region": set(data["place_region"]) == set(marker_keys),
        "photo_roles": {asset["role"] for asset in asset_manifest["assets"]} == set(expected["photo_roles"]),
        "photo_status": asset_manifest["status"] == "COMPLETE_108_LOCAL_REAL_PHOTOS",
        "semantic_links": all(leg.get("label") and leg.get("note") for leg in data["legs"] if leg.get("branch_kind") in {"recovery", "choice"}),
    }
    missing_assets = []
    for asset in asset_manifest["assets"]:
        for field in ("local_thumb_path", "local_medium_path"):
            if not (ROOT / asset[field]).is_file():
                missing_assets.append(asset[field])
    checks["photo_files"] = not missing_assets
    checks["vector_bundle"] = vector_path.stat().st_size > 1_000_000 and not vector_header.startswith(b"version https://git-lfs.github.com/spec/v1")
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise RuntimeError(f"Canonical source/schema checks failed: {', '.join(failed)}")
    return {"checks": checks, "truth_validation": {"status": truth_report["status"], "counts": truth_report["counts"]}, "counts": {"places": len(marker_keys), "photos": len(asset_manifest["assets"]), "timeline_cards": len(data["timeline"]), "route_legs": len(data["legs"])}, "providers": providers}


def validate_authority_boundaries() -> None:
    manifest = pipeline_manifest()
    workflow = (ROOT / ".github" / "workflows" / "deploy-pages.yml").read_text()
    hosted_runner = (ROOT / "scripts" / "hosted_linux_pipeline.py").read_text()
    if "python3 scripts/hosted_linux_pipeline.py release" not in workflow:
        raise RuntimeError("Pages workflow does not use the hosted canonical release runner.")
    if "scripts/pipeline.py" not in hosted_runner or "release" not in hosted_runner:
        raise RuntimeError("Hosted release runner does not delegate to the canonical pipeline.")
    forbidden_workflow_refs = ("prepare_public_site.py", "build_final.py", "package_final.py", "run_acceptance.py", "run_live_providers.py")
    if any(reference in workflow for reference in forbidden_workflow_refs):
        raise RuntimeError("Pages workflow references a legacy/direct release entry point.")
    build_source = (ROOT / "scripts" / "build_map_first.py").read_text()
    public_source = (ROOT / "scripts" / "prepare_public_site.py").read_text()
    if "(ROOT / \"index.html\").write_text" in build_source or "ROOT / \"index_map_first.html\"" in build_source:
        raise RuntimeError("Canonical build still writes a generated root HTML artifact.")
    if "ROOT / \"index.html\"" in public_source:
        raise RuntimeError("Public assembly still reads a generated root HTML artifact.")
    for relative in manifest["historical_or_legacy"]:
        path = ROOT / relative
        if path.suffix == ".py" and path.is_file() and "DEPRECATED LEGACY ENTRY POINT" not in path.read_text():
            raise RuntimeError(f"Legacy script is not mechanically deprecated: {relative}")


def run_process(command: list[str], env: dict[str, str] | None = None) -> tuple[int, str, str]:
    process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
    try:
        stdout, stderr = process.communicate(timeout=COMPONENT_TIMEOUT_SECONDS)
        return process.returncode, stdout[-5000:], stderr[-5000:]
    except subprocess.TimeoutExpired as error:
        os.killpg(process.pid, signal.SIGKILL)
        stdout, stderr = process.communicate()
        stdout = stdout or error.stdout or ""
        stderr = stderr or error.stderr or ""
        return 124, stdout[-5000:], f"TIMEOUT after {COMPONENT_TIMEOUT_SECONDS}s\n{stderr[-4800:]}"


def run_build(output: Path) -> None:
    code, stdout, stderr = run_process([sys.executable, str(ROOT / "scripts" / "build_map_first.py"), "--output-dir", str(output)])
    if code:
        raise RuntimeError(f"Canonical build failed ({code}).\n{stdout}\n{stderr}")


def run_public_rights_audit() -> dict:
    contract = load_contract()
    photo_manifest = load_rights_json(ROOT / "manifests" / "asset_manifest.json")
    with tempfile.TemporaryDirectory(prefix="public-candidate-", dir=ROOT) as temporary:
        candidate = Path(temporary) / "public"
        shutil.copytree(BUILD / "modular", candidate)
        (candidate / ".release-qualification.json").write_text(json.dumps({"status": "CANDIDATE", "candidate_head": current_revision()}))
        (candidate / ".nojekyll").touch()
        write_notices(candidate, contract, photo_manifest, "pages")
        result = audit_tree(candidate, contract=contract, manifest=photo_manifest, mode="pages", require_provenance=False)
    result["candidate_head"] = current_revision()
    result["build_manifest_sha256"] = digest(BUILD / "build_manifest.json")
    report_path = ROOT / "QA" / "release" / "public_asset_rights.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    if result["status"] != "PASS":
        raise RuntimeError("Public asset rights audit failed: " + "; ".join(result["failures"][:12]))
    return result


def run_gate4_static() -> dict:
    code, stdout, stderr = run_process([sys.executable, str(ROOT / "scripts" / "qa_gate4_resilience.py"), "--mode", "static", "--output", str(GATE4_STATIC)])
    status = evidence_status(GATE4_STATIC, code)
    report = load_json(GATE4_STATIC) if GATE4_STATIC.is_file() else {"status": status, "failures": [stderr or stdout]}
    report["returncode"] = code
    if code or status != "PASS":
        raise RuntimeError(f"Gate 4 static validation failed ({status}). {report.get('failures', [])}")
    return report


def run_security_gate(expected_revision: str | None = None, extra_roots: list[Path] | None = None) -> dict:
    revision = expected_revision or current_revision()
    command = [sys.executable, str(ROOT / "scripts" / "security_privacy.py"), "--revision", revision]
    for path in extra_roots or []:
        command.extend(["--scan-root", str(path)])
    code, stdout, stderr = run_process(command)
    report = load_json(SECURITY_EVIDENCE) if SECURITY_EVIDENCE.is_file() else {"status": "UNVERIFIED", "failures": [stderr or stdout]}
    report["returncode"] = code
    if code or report.get("status") != "PASS":
        raise RuntimeError(f"Gate 7 security/privacy validation failed ({report.get('status')}). {report.get('failures', [])[:12]}")
    return report


def write_gate4_summary(package: dict | None = None) -> dict:
    static = load_json(GATE4_STATIC) if GATE4_STATIC.is_file() else {"status": "VERIFY_REQUIRED", "failures": ["fast static evidence has not run"]}
    runtime = load_json(GATE4_RUNTIME) if GATE4_RUNTIME.is_file() else {"status": "VERIFY_REQUIRED", "failures": ["full browser evidence has not run"]}
    if PUBLIC.is_dir() and (PUBLIC / "index.html").is_file():
        delivery = delivery_report(PUBLIC)
    else:
        delivery = {"status": "VERIFY_REQUIRED", "reason": "public staging is assembled only after PASS qualification", "forms": []}
    package_evidence = package
    if package_evidence is None and GATE4_SUMMARY.is_file():
        previous = load_json(GATE4_SUMMARY).get("package", {})
        archive = RELEASE / "package.zip"
        manifest = RELEASE / "package" / "PACKAGE_MANIFEST.json"
        if (
            previous.get("status") == "PASS"
            and previous.get("revision") == current_revision()
            and archive.is_file()
            and manifest.is_file()
            and previous.get("package_sha256") == digest(archive)
            and previous.get("manifest_sha256") == digest(manifest)
            and all(previous.get("checks", {}).values())
        ):
            package_evidence = previous
    report = {
        "schema_version": 1,
        "project": "sf-trip-visualizer",
        "gate": "production_readiness_gate_4",
        "status": "PASS" if static.get("status") == "PASS" and runtime.get("status") == "PASS" else "INCOMPLETE",
        "candidate_head": current_revision(),
        "test_modes": ["static", "browser", "delivery_parity"],
        "static": {"status": static.get("status"), "evidence": "QA/release/gate4_static.json"},
        "runtime": {"status": runtime.get("status"), "evidence": "QA/release/gate4_runtime.json", "external_provider": runtime.get("external_provider")},
        "delivery": delivery,
        "package": package_evidence or {"status": "VERIFY_REQUIRED", "reason": "package is assembled after qualification"},
        "limitations": ["This is Gate 4 evidence only; it is not a production-readiness or production-release claim."],
    }
    GATE4_SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    GATE4_SUMMARY.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report


def run_fast(expected_revision: str | None = None, require_clean: bool = False) -> dict:
    evidence = {
        "schema_version": 1,
        "status": "FAIL",
        "candidate_head": current_revision(),
        "working_tree_clean": working_tree_clean(),
        "errors": [],
    }
    try:
        if expected_revision and evidence["candidate_head"] != expected_revision:
            raise RuntimeError(f"Expected revision {expected_revision}, found {evidence['candidate_head']}.")
        if require_clean and not evidence["working_tree_clean"]:
            raise RuntimeError("Release qualification requires a clean checkout.")
        validate_authority_boundaries()
        evidence["source"] = validate_product()
        manifest = pipeline_manifest()
        before = authored_snapshot(manifest)
        run_build(BUILD)
        after = authored_snapshot(manifest)
        if before != after:
            changed = [path for path in before if before[path] != after[path]]
            raise RuntimeError(f"Canonical build mutated authored input(s): {', '.join(changed)}")
        build_manifest = load_json(BUILD / "build_manifest.json")
        first_hashes = tree_hashes(BUILD, {"build_manifest.json"})
        with tempfile.TemporaryDirectory(prefix="pipeline-repro-", dir=ROOT) as temporary:
            repeat = Path(temporary) / "build"
            run_build(repeat)
            repeat_hashes = tree_hashes(repeat, {"build_manifest.json"})
        if first_hashes != repeat_hashes:
            differences = sorted(set(first_hashes) ^ set(repeat_hashes) | {key for key in first_hashes.keys() & repeat_hashes.keys() if first_hashes[key] != repeat_hashes[key]})
            raise RuntimeError(f"Canonical build is not reproducible; differing output(s): {', '.join(differences[:10])}")
        public_rights = run_public_rights_audit()
        gate4_static = run_gate4_static()
        security = run_security_gate(expected_revision or evidence["candidate_head"])
        evidence["authored_inputs_unchanged"] = True
        evidence["reproducible"] = True
        evidence["build"] = {
            "root": ".build",
            "manifest_sha256": digest(BUILD / "build_manifest.json"),
            "modular_index_sha256": digest(BUILD / "modular" / "index.html"),
            "standalone_sha256": digest(BUILD / "standalone" / "SF_Smart_Minority_Map_First_Standalone.html"),
            "file_count": len(build_manifest["files"]),
        }
        evidence["gate4_static"] = {"status": gate4_static["status"], "evidence": "QA/release/gate4_static.json"}
        evidence["public_asset_rights"] = {"status": public_rights["status"], "evidence": "QA/release/public_asset_rights.json", "candidate_file_count": public_rights["file_count"], "approved_file_counts_by_class": public_rights["approved_file_counts_by_class"]}
        evidence["security_privacy"] = {"status": security["status"], "evidence": "QA/release/security_privacy.json", "verify_required": security.get("verify_required", [])}
        evidence["status"] = "PASS"
    except (Exception, SystemExit) as error:
        evidence["errors"].append(str(error))
    FAST_EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    FAST_EVIDENCE.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")
    return evidence


def wait_for_server(url: str, process: subprocess.Popen) -> None:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Canonical QA server exited before becoming ready.")
        try:
            with urlopen(url, timeout=1):
                return
        except Exception:
            time.sleep(0.2)
    raise RuntimeError(f"Canonical QA server did not become ready at {url}.")


def free_local_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def evidence_status(path: Path, returncode: int) -> str:
    if returncode == 124:
        return "UNVERIFIED"
    if returncode:
        return "FAIL" if path.is_file() else "UNVERIFIED"
    if not path.is_file():
        return "UNVERIFIED"
    payload = json.loads(path.read_text())
    if isinstance(payload, dict):
        status = payload.get("status")
        if status in {"PASS", "FAIL", "UNVERIFIED"}:
            return status
        # Some maintained evidence schemas are terminal by successful exit
        # and intentionally omit a status field. A stale in-progress record is
        # never terminal and must remain fail-closed.
        return "UNVERIFIED" if status == "RUNNING" else ("PASS" if returncode == 0 else "UNVERIFIED")
    if isinstance(payload, list):
        if path.name == "smoke.json":
            return "PASS" if all(not row.get("errors") and not row.get("failed_requests") for row in payload) else "FAIL"
        return "PASS" if all(row.get("status") == "PASS" for row in payload) else "FAIL"
    return "FAIL"


def run_qualification(expected_revision: str | None = None, require_clean: bool = False) -> dict:
    report = {
        "schema_version": 1,
        "status": "FAIL",
        "project": "sf-trip-visualizer",
        "candidate_head": current_revision(),
        "working_tree_clean": working_tree_clean(),
        "canonical": {"manifest": "manifests/canonical_pipeline.json", "build": "scripts/build_map_first.py", "data": "data/phase7_app_data.json"},
        "component_timeout_seconds": COMPONENT_TIMEOUT_SECONDS,
        "tests": [],
        "errors": [],
        "historical_evidence_excluded": ["QA/final_acceptance.json", "QA/final_cross_browser.json", "QA/final_live_providers.json", "P0_PROOF_REPORT.md"],
    }
    server = None
    try:
        if require_clean:
            failures = contract_failures()
            if failures:
                raise RuntimeError(
                    "Hosted Linux release qualification contract is not satisfied: "
                    + "; ".join(failures)
                )
        fast = run_fast(expected_revision, require_clean)
        report["fast"] = fast
        if fast["status"] != "PASS":
            raise RuntimeError("Fast validation did not pass; decisive browser qualification was not authorized.")
        report["tests"].append({"name": "public_asset_rights", "command": "candidate-tree audit via scripts/public_asset_rights.py", "evidence": "QA/release/public_asset_rights.json", "status": fast.get("public_asset_rights", {}).get("status", "UNVERIFIED"), "returncode": 0, "timeout_seconds": COMPONENT_TIMEOUT_SECONDS})
        before = authored_snapshot(pipeline_manifest())
        port = free_local_port()
        qa_url = f"http://127.0.0.1:{port}/index.html"
        server = subprocess.Popen([sys.executable, str(ROOT / "scripts" / "serve_map.py"), "--port", str(port), "--directory", str(BUILD / "modular")], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        wait_for_server(qa_url, server)
        env = os.environ.copy()
        env["TRIP_QA_URL"] = qa_url
        env["TRIP_STANDALONE_PATH"] = str(BUILD / "standalone" / "SF_Smart_Minority_Map_First_Standalone.html")
        env["TRIP_EXPECTED_REVISION"] = report["candidate_head"]
        env["TRIP_CANDIDATE_SHA"] = report["candidate_head"]
        for name, script, output in COMPONENTS:
            print(json.dumps({"qualification": "running", "test": name, "candidate_head": report["candidate_head"]}), flush=True)
            output_path = ROOT / output
            command = [sys.executable, str(ROOT / script)]
            if name == "photo_integrity":
                command.append("--runtime-only")
            if name == "maplibre_security":
                command.extend(["--revision", report["candidate_head"], "--output", str(output_path)])
            if name == "gate4_runtime":
                command.extend(["--mode", "browser", "--output", str(output_path)])
            code, stdout, stderr = run_process(command, env)
            status = evidence_status(output_path, code)
            command_text = f"python3 {script}" + (" --runtime-only" if name == "photo_integrity" else "") + (f" --mode browser --output {output}" if name == "gate4_runtime" else "")
            if name == "maplibre_security":
                command_text += f' --revision {report["candidate_head"]} --output {output}'
            test_report = {"name": name, "command": command_text, "evidence": output, "status": status, "returncode": code, "timeout_seconds": COMPONENT_TIMEOUT_SECONDS, "stdout_tail": stdout, "stderr_tail": stderr}
            if code == 124:
                test_report["status_reason"] = f"Component exceeded the {COMPONENT_TIMEOUT_SECONDS}s bound; gate remains unverified and release is fail-closed."
            report["tests"].append(test_report)
        after = authored_snapshot(pipeline_manifest())
        if before != after:
            changed = [path for path in before if before[path] != after[path]]
            raise RuntimeError(f"Qualification mutated authored input(s): {', '.join(changed)}")
        report["authored_inputs_unchanged"] = True
        report["build"] = fast["build"]
        write_gate4_summary()
        if not report["tests"] or not all(test["status"] == "PASS" for test in report["tests"]):
            raise RuntimeError("One or more decisive qualification gates failed or were unverified.")
        report["status"] = "PASS"
    except (Exception, SystemExit) as error:
        report["errors"].append(str(error))
    finally:
        if server is not None:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
        QUALIFICATION.parent.mkdir(parents=True, exist_ok=True)
        QUALIFICATION.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report


def assemble_public(revision: str) -> None:
    code, stdout, stderr = run_process([sys.executable, str(ROOT / "scripts" / "prepare_public_site.py"), "--output-dir", str(PUBLIC), "--revision", revision])
    if code:
        raise RuntimeError(f"Public assembly failed ({code}).\n{stdout}\n{stderr}")


def verify_public(revision: str) -> dict:
    require_qualified(revision)
    provenance_path = PUBLIC / ".release-provenance.json"
    if not provenance_path.is_file():
        raise RuntimeError("Public artifact provenance is missing.")
    provenance = load_json(provenance_path)
    qualification_hash = digest(QUALIFICATION)
    artifact_hash, file_count, byte_count = tree_digest(PUBLIC, {".release-provenance.json"})
    checks = {
        "tested_sha": provenance.get("tested_sha") == revision == current_revision(),
        "qualification_sha256": provenance.get("qualification_sha256") == qualification_hash,
        "build_manifest_sha256": provenance.get("build_manifest_sha256") == digest(BUILD / "build_manifest.json"),
        "modular_index_sha256": provenance.get("modular_index_sha256") == digest(BUILD / "modular" / "index.html"),
        "standalone_sha256": load_json(QUALIFICATION).get("build", {}).get("standalone_sha256") == digest(BUILD / "standalone" / "SF_Smart_Minority_Map_First_Standalone.html"),
        "artifact_sha256": provenance.get("artifact_sha256_excluding_provenance") == artifact_hash,
        "artifact_file_count": provenance.get("artifact_file_count_excluding_provenance") == file_count,
        "artifact_bytes": provenance.get("artifact_bytes_excluding_provenance") == byte_count,
    }
    rights = audit_tree(PUBLIC, mode="pages", require_provenance=True)
    (ROOT / "QA" / "release" / "public_asset_rights.json").write_text(json.dumps(rights, ensure_ascii=False, indent=2) + "\n")
    checks["public_asset_rights"] = rights["status"] == "PASS"
    security = run_security_gate(revision, [PUBLIC])
    checks["security_privacy"] = security["status"] == "PASS"
    if not all(checks.values()):
        raise RuntimeError(f"Public provenance verification failed: {', '.join(name for name, passed in checks.items() if not passed)}")
    parity = delivery_report(PUBLIC)
    if parity["status"] != "PASS":
        raise RuntimeError(f"Public delivery parity failed: {', '.join(parity.get('failures', []))}")
    return {"status": "PASS", "revision": revision, "checks": checks, "artifact_sha256": artifact_hash, "files": file_count, "parity": parity, "public_asset_rights": rights, "security_privacy": security}


def verify_package(revision: str) -> dict:
    package_dir = RELEASE / "package"
    archive = RELEASE / "package.zip"
    manifest_path = package_dir / "PACKAGE_MANIFEST.json"
    if not package_dir.is_dir() or not archive.is_file() or not manifest_path.is_file():
        raise RuntimeError("Package output or PACKAGE_MANIFEST.json is missing.")
    manifest = load_json(manifest_path)
    files = tree_hashes(package_dir, {"PACKAGE_MANIFEST.json"})
    checks = {
        "tested_sha": manifest.get("tested_sha") == revision == current_revision(),
        "qualification_sha256": manifest.get("qualification_sha256") == digest(QUALIFICATION),
        "file_hashes": manifest.get("files") == files,
        "file_count": manifest.get("file_count_excluding_manifest") == len(files),
    }
    with zipfile.ZipFile(archive) as zip_file:
        infos = {info.filename: info for info in zip_file.infolist()}
        expected_names = {str(Path(package_dir.name) / relative) for relative in [*files, "PACKAGE_MANIFEST.json"]}
        checks["zip_members"] = set(infos) == expected_names
        checks["zip_timestamps_deterministic"] = all(info.date_time == (1980, 1, 1, 0, 0, 0) for info in infos.values())
        checks["zip_content_hashes"] = all(digest_bytes(zip_file.read(name)) == (digest(package_dir / name.split("/", 1)[1]) if "/" in name else "") for name in infos)
    if not all(checks.values()):
        raise RuntimeError(f"Package integrity verification failed: {', '.join(name for name, passed in checks.items() if not passed)}")
    original_zip_hash = digest(archive)
    with tempfile.TemporaryDirectory(prefix="package-repro-", dir=ROOT) as temporary:
        repeat_dir = Path(temporary) / "package"
        repeat_archive = Path(temporary) / "package.zip"
        code, stdout, stderr = run_process([sys.executable, str(ROOT / "scripts" / "package_map_first.py"), "--destination", str(repeat_dir), "--archive", str(repeat_archive), "--revision", revision])
        if code:
            raise RuntimeError(f"Repeat package failed ({code}).\n{stdout}\n{stderr}")
        repeat_zip_hash = digest(repeat_archive)
    checks["repeat_zip_sha256"] = original_zip_hash == repeat_zip_hash
    if not checks["repeat_zip_sha256"]:
        raise RuntimeError("Repeated packaging of the exact qualified revision changed the ZIP hash.")
    security = run_security_gate(revision, [package_dir])
    checks["security_privacy"] = security["status"] == "PASS"
    result = {"status": "PASS", "revision": revision, "package_sha256": original_zip_hash, "manifest_sha256": digest(manifest_path), "files": len(files), "checks": checks, "security_privacy": security}
    return result


def require_qualified(revision: str | None) -> str:
    if not QUALIFICATION.is_file():
        raise RuntimeError("Run `python3 scripts/pipeline.py qualify` before packaging or public assembly.")
    report = load_json(QUALIFICATION)
    head = current_revision()
    qualified_revision = report.get("candidate_head")
    if report.get("status") != "PASS" or qualified_revision != head or revision and revision != head:
        raise RuntimeError("No PASS full qualification exists for the current exact checkout.")
    return head


def command_fast(args: argparse.Namespace) -> int:
    evidence = run_fast(args.revision)
    print(json.dumps({"status": evidence["status"], "candidate_head": evidence["candidate_head"], "errors": evidence["errors"]}, ensure_ascii=False))
    return 0 if evidence["status"] == "PASS" else 1


def command_qualify(args: argparse.Namespace) -> int:
    report = run_qualification(args.revision)
    print(json.dumps({"status": report["status"], "candidate_head": report["candidate_head"], "tests": {test["name"]: test["status"] for test in report["tests"]}, "errors": report["errors"]}, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("fast", "qualify"):
        subparser = subparsers.add_parser(name)
        subparser.add_argument("--revision")
    subparsers.add_parser("package").add_argument("--revision")
    subparsers.add_parser("assemble-public", help="assemble Pages after a matching PASS qualification").add_argument("--revision", required=True)
    subparsers.add_parser("verify-public", help="verify Pages staging provenance").add_argument("--revision", required=True)
    release = subparsers.add_parser("release", help="qualify and assemble the exact checkout for Pages")
    release.add_argument("--revision", required=True)
    serve = subparsers.add_parser("serve", help="serve the generated modular build for local QA")
    serve.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    if args.command == "fast":
        return command_fast(args)
    if args.command == "qualify":
        return command_qualify(args)
    if args.command == "assemble-public":
        revision = require_qualified(args.revision)
        assemble_public(revision)
        public_report = verify_public(revision)
        write_gate4_summary()
        print(json.dumps(public_report, ensure_ascii=False))
        return 0
    if args.command == "verify-public":
        public_report = verify_public(args.revision)
        write_gate4_summary()
        print(json.dumps(public_report, ensure_ascii=False))
        return 0
    if args.command == "package":
        revision = require_qualified(args.revision)
        if not (PUBLIC / "index.html").is_file():
            assemble_public(revision)
        verify_public(revision)
        code, stdout, stderr = run_process([sys.executable, str(ROOT / "scripts" / "package_map_first.py"), "--revision", revision])
        if code:
            print(stdout, end="")
            print(stderr, end="", file=sys.stderr)
            return code
        package_report = verify_package(revision)
        write_gate4_summary(package_report)
        print(stdout, end="")
        print(json.dumps(package_report, ensure_ascii=False))
        return 0
    if args.command == "release":
        report = run_qualification(args.revision, require_clean=True)
        if report["status"] != "PASS":
            print(json.dumps({"status": report["status"], "candidate_head": report["candidate_head"], "errors": report["errors"]}, ensure_ascii=False))
            return 1
        assemble_public(args.revision)
        public_report = verify_public(args.revision)
        write_gate4_summary()
        print(json.dumps({"status": "PASS", "candidate_head": args.revision, "public": public_report}, ensure_ascii=False))
        return 0
    if args.command == "serve":
        if not (BUILD / "modular" / "index.html").is_file():
            raise SystemExit("No .build/modular/index.html; run the fast or qualify command first.")
        return subprocess.call([sys.executable, str(ROOT / "scripts" / "serve_map.py"), "--port", str(args.port), "--directory", str(BUILD / "modular")], cwd=ROOT)
    raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
