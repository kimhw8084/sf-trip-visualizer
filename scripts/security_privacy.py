#!/usr/bin/env python3
"""Canonical Gate-7 security, privacy, dependency, and trust validator.

This is intentionally stdlib-only so the gate can run before QA dependency
installation.  It emits redacted findings only; secret values never enter the
machine-readable evidence or process output.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "manifests" / "security_privacy_contract.json"
EVIDENCE_PATH = ROOT / "QA" / "release" / "security_privacy.json"
REQUIREMENTS_PATH = ROOT / "requirements-qa.txt"
WORKFLOWS = {
    "candidate": ROOT / ".github" / "workflows" / "candidate-qualification.yml",
    "pages": ROOT / ".github" / "workflows" / "deploy-pages.yml",
}
TEXT_SUFFIXES = {".css", ".html", ".js", ".json", ".md", ".py", ".txt", ".yml", ".yaml", ".toml", ".xml"}
ALLOWED_STORAGE_KEYS = {
    "trip_visualizer_runtime_v1",
    "trip_lang",
    "trip_theme",
    "trip_panel_width",
    "trip_mobile_panel_height",
}
SECRET_PATTERNS = (
    ("private_key", re.compile(r"-----BEGIN(?: [A-Z0-9]+)* PRIVATE KEY-----")),
    ("github_token", re.compile(r"\b(?:gh[pousr]|github_pat)_[A-Za-z0-9_]{20,}\b")),
    ("openai_token", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("bearer_token", re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{20,}")),
    (
        "credential_assignment",
        re.compile(
            r"\b(?:api[_-]?key|access[_-]?token|client[_-]?secret|password|passwd|private[_-]?key)\b"
            r"\s*[:=]\s*[\"']?([A-Za-z0-9/+_=-]{20,})"
        ),
    ),
    ("absolute_user_path", re.compile(r"(?:file://)?/(?:Users|home)/[A-Za-z0-9._-]+/")),
    ("windows_user_path", re.compile(r"\b[A-Za-z]:\\Users\\[A-Za-z0-9._-]+\\")),
)
FORBIDDEN_ARTIFACT_COMPONENTS = {
    ".aws",
    ".ssh",
    "browser-profile",
    "credentials",
    "private",
    "scratch",
    "secrets",
    "tmp",
}
FORBIDDEN_ARTIFACT_SUFFIXES = {".key", ".pem", ".p12", ".pfx", ".sqlite", ".sqlite3"}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def git_revision(root: Path = ROOT) -> str | None:
    try:
        return subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def scan_text(text: str, relative_path: str) -> list[dict]:
    """Return classification-only findings; never return a matched value."""
    findings: list[dict] = []
    for line_number, line in enumerate(text.splitlines(), 1):
        for classification, pattern in SECRET_PATTERNS:
            if pattern.search(line):
                findings.append(
                    {
                        "path": relative_path,
                        "line": line_number,
                        "classification": classification,
                        "redacted_match": f"<redacted:{classification}>",
                    }
                )
    return findings


def read_text_if_safe(path: Path) -> str | None:
    if path.suffix.lower() not in TEXT_SUFFIXES:
        return None
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if b"\0" in data[:4096]:
        return None
    return data.decode("utf-8", errors="replace")


def scan_paths(paths: list[Path], root: Path = ROOT) -> dict:
    findings: list[dict] = []
    scanned: list[str] = []
    seen: set[Path] = set()
    for path in paths:
        candidates = sorted(path.rglob("*") if path.is_dir() else [path]) if path.exists() else []
        for candidate in candidates:
            if not candidate.is_file() or candidate in seen:
                continue
            seen.add(candidate)
            text = read_text_if_safe(candidate)
            relative = str(candidate.relative_to(root)) if candidate.is_relative_to(root) else str(candidate)
            scanned.append(relative)
            if {part.lower() for part in candidate.parts} & FORBIDDEN_ARTIFACT_COMPONENTS or candidate.suffix.lower() in FORBIDDEN_ARTIFACT_SUFFIXES:
                findings.append({"path": relative, "classification": "private_or_credential_input", "redacted_match": "<redacted:path-classification>"})
            if text is None:
                continue
            findings.extend(scan_text(text, relative))
    return {"status": "PASS" if not findings else "FAIL", "scanned_files": len(scanned), "findings": findings}


def production_paths(root: Path, contract: dict) -> list[Path]:
    paths: list[Path] = []
    canonical_manifest_path = root / "manifests" / "canonical_pipeline.json"
    if canonical_manifest_path.is_file():
        canonical_manifest = load_json(canonical_manifest_path)
        paths.extend(root / relative for relative in canonical_manifest.get("authored_inputs", []) if (root / relative).exists())
    for relative in contract.get("authority", {}).values():
        if isinstance(relative, str) and (root / relative).is_file():
            paths.append(root / relative)
    paths.extend(
        [
            root / "requirements-qa.txt",
            root / "src" / "vector_entry.js",
            root / "src" / "app_phase7.css",
            root / "src" / "map_first.css",
            root / "assets",
            root / "manifests" / "asset_manifest.json",
            root / "manifests" / "source_manifest.json",
            root / "manifests" / "map_first_basemap_manifest.json",
        ]
    )
    paths.extend(sorted((root / ".github" / "workflows").glob("*.yml")))
    paths.extend(sorted((root / "vendor").glob("*")))
    return paths


def artifact_paths(root: Path, extra_roots: list[Path]) -> list[Path]:
    paths = [root / ".build", root / ".public-site", root / ".release" / "package"]
    paths.extend(extra_roots)
    return [path for path in paths if path.exists()]


def check_artifact_paths(paths: list[Path], root: Path = ROOT) -> dict:
    failures: list[dict] = []
    inspected: list[str] = []
    for base in paths:
        for path in sorted(base.rglob("*")) if base.is_dir() else [base]:
            if not path.is_file():
                continue
            relative = str(path.relative_to(root)) if path.is_relative_to(root) else str(path)
            inspected.append(relative)
            components = {part.lower() for part in path.parts}
            if components & FORBIDDEN_ARTIFACT_COMPONENTS or path.suffix.lower() in FORBIDDEN_ARTIFACT_SUFFIXES:
                failures.append({"path": relative, "classification": "private_or_credential_artifact", "redacted_match": "<redacted:path-classification>"})
            text = read_text_if_safe(path)
            if text is not None:
                failures.extend(scan_text(text, relative))
    return {"status": "PASS" if not failures else "FAIL", "inspected_files": len(inspected), "findings": failures}


def check_vendor_inventory(root: Path = ROOT, contract: dict | None = None) -> dict:
    contract = contract or load_json(root / "manifests" / "security_privacy_contract.json")
    entries = [entry for entry in contract.get("dependency_inventory", []) if entry.get("artifact_hashes")]
    expected_paths: set[str] = set()
    results: list[dict] = []
    failures: list[str] = []
    for entry in entries:
        for relative, expected in entry["artifact_hashes"].items():
            expected_paths.add(relative)
            path = root / relative
            actual = sha256(path) if path.is_file() else None
            passed = actual == expected
            results.append({"id": entry["id"], "path": relative, "expected_sha256": expected, "actual_sha256": actual, "status": "PASS" if passed else "FAIL"})
            if not passed:
                failures.append(f"{relative}: expected {expected}, found {actual or 'missing'}")
    for relative in sorted(str(path.relative_to(root)) for path in (root / "vendor").glob("*") if path.is_file()):
        if relative not in expected_paths:
            failures.append(f"{relative}: shipped vendor file has no inventory entry")
    return {"status": "PASS" if not failures else "FAIL", "files": results, "failures": failures}


def _requirement_name(line: str) -> str | None:
    match = re.match(r"\s*([A-Za-z0-9_.-]+)==([^\s\\]+)", line)
    return match.group(1).lower().replace("-", "_") if match else None


def check_requirements(root: Path = ROOT, contract: dict | None = None) -> dict:
    path = root / "requirements-qa.txt"
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    packages: dict[str, dict] = {}
    current: str | None = None
    failures: list[str] = []
    for number, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        name = _requirement_name(line)
        if name:
            current = name
            packages.setdefault(name, {"line": number, "hashes": []})
            if "\\" not in line:
                failures.append(f"line {number}: exact requirement lacks hash continuation")
            continue
        if stripped.startswith("--hash=sha256:") and current:
            digest = stripped.split(":", 1)[1].rstrip(" \\")
            if re.fullmatch(r"[0-9a-f]{64}", digest):
                packages[current]["hashes"].append(digest)
            else:
                failures.append(f"line {number}: malformed sha256 hash")
            continue
        failures.append(f"line {number}: unrecognized or unpinned requirement syntax")
    expected = contract or load_json(root / "manifests" / "security_privacy_contract.json")
    inventory = next((entry for entry in expected.get("dependency_inventory", []) if entry.get("id") == "python-qa-closure"), {})
    expected_names = {item.split("==", 1)[0].lower().replace("-", "_") for item in inventory.get("packages", [])}
    if set(packages) != expected_names:
        failures.append(f"resolved package set differs: expected {sorted(expected_names)}, found {sorted(packages)}")
    for name, record in packages.items():
        if not record["hashes"]:
            failures.append(f"{name}: no artifact hash")
    return {"status": "PASS" if not failures else "FAIL", "packages": packages, "failures": failures}


def check_workflows(root: Path = ROOT, contract: dict | None = None) -> dict:
    contract = contract or load_json(root / "manifests" / "security_privacy_contract.json")
    expected = {entry["id"]: entry for entry in contract.get("dependency_inventory", []) if entry.get("id", "").startswith("actions-")}
    failures: list[str] = []
    workflow_results: dict[str, dict] = {}
    for kind, original_path in WORKFLOWS.items():
        path = root / original_path.relative_to(ROOT)
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
        if not text:
            failures.append(f"{kind}: workflow missing")
            continue
        if "pull_request_target" in text or "contents: write" in text or "secrets." in text:
            failures.append(f"{kind}: forbidden trust or secret pattern")
        uses = re.findall(r"^\s*uses:\s*([^\s#]+)", text, flags=re.MULTILINE)
        action_results = []
        for use in uses:
            if "@" not in use or use.startswith("./"):
                continue
            action, ref = use.rsplit("@", 1)
            action_id = "actions-" + action.split("/", 1)[1] if action.startswith("actions/") else action
            expected_pin = expected.get(action_id, {}).get("pin")
            passed = bool(re.fullmatch(r"[0-9a-f]{40}", ref)) and (expected_pin is None or ref == expected_pin)
            action_results.append({"action": action, "ref": ref, "expected_pin": expected_pin, "status": "PASS" if passed else "FAIL"})
            if not passed:
                failures.append(f"{kind}: action {use} is not pinned to the reviewed commit")
        if kind == "candidate":
            required = ["contents: read", "ref: ${{ github.sha }}", "pipeline.py qualify --revision \"$GITHUB_SHA\"", "branches:\n      - \"codex/**\""]
            if any(fragment not in text for fragment in required):
                failures.append("candidate: exact read-only qualification contract changed")
            if "pages:" in text or "id-token:" in text or "deploy-pages" in text:
                failures.append("candidate: deployment permission or action introduced")
        else:
            required = ["branches: [main]", "workflow_dispatch", "contents: read", "pages: write", "id-token: write", "pipeline.py release --revision \"$GITHUB_SHA\"", "pipeline.py verify-public --revision \"$GITHUB_SHA\""]
            if any(fragment not in text for fragment in required):
                failures.append("pages: exact Pages qualification contract changed")
        workflow_results[kind] = {"status": "PASS" if not failures else "FAIL", "actions": action_results, "permissions_reviewed": True}
    status = "PASS" if not failures else "FAIL"
    return {"status": status, "workflows": workflow_results, "failures": failures}


def check_origins(root: Path = ROOT) -> dict:
    failures: list[str] = []
    data_path = root / "data" / "phase7_app_data.json"
    data = load_json(data_path) if data_path.is_file() else {}
    satellite = data.get("providers", {}).get("satellite", {})
    expected_tile = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
    expected_probe = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/12/1583/655"
    if satellite.get("tile_template") != expected_tile or satellite.get("health_probe") != expected_probe or satellite.get("requires_api_key", False) is not False:
        failures.append("satellite provider is not the fixed, unauthenticated Esri configuration")
    for marker in data.get("markers", []):
        value = marker.get("maps_url", "")
        parsed = urlparse(value)
        query = parse_qs(parsed.query, keep_blank_values=True)
        if parsed.scheme != "https" or parsed.netloc != "www.google.com" or parsed.path != "/maps/search/" or parsed.fragment or parsed.username or parsed.password or set(query) != {"api", "query"} or query.get("api") != ["1"] or not query.get("query", [""])[0]:
            failures.append(f"unsafe canonical navigation URL for {marker.get('place_key', '<unknown>')}")
    runtime_files = [root / "src" / "app_phase7.js", root / "src" / "map_shell_template.html", root / "scripts" / "build_map_first.py"]
    for path in runtime_files:
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
        if re.search(r"(?<!:)http://", text):
            failures.append(f"HTTP runtime endpoint in {path.relative_to(root)}")
        for match in re.finditer(r'target=["\']_blank["\']', text):
            window = text[match.start() : match.start() + 220]
            if "noopener" not in window or "noreferrer" not in window or "referrerpolicy=\"no-referrer\"" not in window:
                failures.append(f"new-context link lacks opener/referrer controls in {path.relative_to(root)}")
    return {"status": "PASS" if not failures else "FAIL", "provider_origin": "https://server.arcgisonline.com", "navigation_origin": "https://www.google.com", "failures": failures}


def check_local_storage(root: Path = ROOT, contract: dict | None = None) -> dict:
    path = root / "src" / "app_phase7.js"
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    literal_keys = set(re.findall(r"localStorage\.(?:getItem|setItem)\(\s*['\"]([^'\"]+)", text))
    failures = sorted(literal_keys - ALLOWED_STORAGE_KEYS)
    for forbidden in ("sessionStorage", "document.cookie", "sendBeacon", "navigator.sendBeacon"):
        if forbidden in text:
            failures.append(f"forbidden browser persistence or submission API: {forbidden}")
    if re.search(r"fetch\([^)]*method\s*:\s*['\"]POST", text, flags=re.IGNORECASE):
        failures.append("background POST found in runtime")
    expected_keys = set((contract or load_json(root / "manifests" / "security_privacy_contract.json")).get("persisted_state", {}).get("storage_keys", {}))
    if expected_keys != ALLOWED_STORAGE_KEYS:
        failures.append("contract storage key set differs from the maintained allowlist")
    return {"status": "PASS" if not failures else "FAIL", "observed_literal_keys": sorted(literal_keys), "allowed_keys": sorted(ALLOWED_STORAGE_KEYS), "failures": failures}


def check_static_controls(root: Path = ROOT) -> dict:
    template = root / "src" / "map_shell_template.html"
    text = template.read_text(encoding="utf-8") if template.is_file() else ""
    failures: list[str] = []
    if '<meta name="referrer" content="no-referrer">' not in text:
        failures.append("document no-referrer meta policy is missing")
    if re.search(r"<\s*(?:iframe|object|embed)\b", text, flags=re.IGNORECASE):
        failures.append("iframe/object/embed runtime exposure found")
    if re.search(r"<script[^>]+src=[\"']https?://", text, flags=re.IGNORECASE):
        failures.append("remote script source found")
    return {"status": "PASS" if not failures else "FAIL", "referrer_policy": "no-referrer", "csp": "NOT_DEPLOYED_HOST_CONTROLLED", "failures": failures}


def check_candidate_binding(root: Path, requested_revision: str | None, contract: dict) -> dict:
    actual_revision = git_revision(root)
    failures: list[str] = []
    if requested_revision and actual_revision != requested_revision:
        failures.append(f"requested revision {requested_revision} does not match HEAD")
    source_paths = [
        "manifests/security_privacy_contract.json",
        "manifests/canonical_pipeline.json",
        "requirements-qa.txt",
        "scripts/pipeline.py",
        "scripts/build_map_first.py",
        "scripts/prepare_public_site.py",
        "scripts/package_map_first.py",
        "scripts/public_asset_rights.py",
        "scripts/security_privacy.py",
        "src/map_shell_template.html",
        "src/app_phase7.js",
        ".github/workflows/candidate-qualification.yml",
        ".github/workflows/deploy-pages.yml",
    ]
    source_paths.extend(path for entry in contract.get("dependency_inventory", []) for path in entry.get("artifact_hashes", {}))
    hashes: dict[str, str] = {}
    for relative in sorted(set(source_paths)):
        path = root / relative
        if path.is_file():
            hashes[relative] = sha256(path)
        else:
            failures.append(f"candidate source hash input missing: {relative}")
    return {"status": "PASS" if not failures else "FAIL", "candidate_head": actual_revision, "requested_revision": requested_revision, "exact_candidate_bound": not failures and bool(actual_revision), "source_hashes": hashes, "failures": failures}


def check_artifact_binding(paths: list[Path], root: Path, revision: str | None, source_hashes: dict[str, str] | None = None) -> dict:
    failures: list[str] = []
    bindings: list[dict] = []
    for base in paths:
        for relative_name in (".release-provenance.json", ".release-qualification.json", "PACKAGE_MANIFEST.json"):
            path = base / relative_name
            if not path.is_file():
                continue
            payload = load_json(path)
            tested = payload.get("tested_sha") or payload.get("candidate_head")
            passed = tested == revision
            bindings.append({"path": str(path.relative_to(root)) if path.is_relative_to(root) else str(path), "tested_sha": tested, "status": "PASS" if passed else "FAIL"})
            if not passed:
                failures.append(f"stale artifact binding: {path}")
            if path.name == "PACKAGE_MANIFEST.json" and source_hashes:
                package_files = payload.get("files", {})
                for relative, expected_hash in source_hashes.items():
                    package_hash = package_files.get(relative)
                    if package_hash is not None and package_hash != expected_hash:
                        failures.append(f"package source drift: {relative}")
            if path.name == ".release-provenance.json" and source_hashes:
                for relative, expected_hash in source_hashes.items():
                    artifact_source = base / relative
                    if artifact_source.is_file() and sha256(artifact_source) != expected_hash:
                        failures.append(f"public source drift: {relative}")
    return {"status": "PASS" if not failures else "FAIL", "bindings": bindings, "failures": failures}


def run_gate(root: Path = ROOT, requested_revision: str | None = None, extra_roots: list[Path] | None = None) -> dict:
    contract = load_json(root / "manifests" / "security_privacy_contract.json")
    revision = git_revision(root)
    source = check_candidate_binding(root, requested_revision, contract)
    production = scan_paths(production_paths(root, contract), root)
    artifacts = artifact_paths(root, extra_roots or [])
    artifact_scan = check_artifact_paths(artifacts, root)
    vendor = check_vendor_inventory(root, contract)
    requirements = check_requirements(root, contract)
    workflows = check_workflows(root, contract)
    origins = check_origins(root)
    storage = check_local_storage(root, contract)
    controls = check_static_controls(root)
    binding = check_artifact_binding(artifacts, root, revision, source["source_hashes"])
    checks = {
        "candidate_binding": source["status"] == "PASS",
        "production_secret_scan": production["status"] == "PASS",
        "artifact_secret_scan": artifact_scan["status"] == "PASS",
        "vendor_inventory": vendor["status"] == "PASS",
        "requirements_reproducible": requirements["status"] == "PASS",
        "workflow_trust": workflows["status"] == "PASS",
        "external_origins": origins["status"] == "PASS",
        "local_storage": storage["status"] == "PASS",
        "static_controls": controls["status"] == "PASS",
        "artifact_binding": binding["status"] == "PASS",
    }
    failures: list[str] = []
    for name, passed in checks.items():
        if not passed:
            failures.append(name)
    for report in (production, artifact_scan, vendor, requirements, workflows, origins, storage, controls, binding):
        failures.extend(report.get("failures", []))
    verify_required = contract.get("advisory_review", {}).get("verify_required", [])
    return {
        "schema_version": 1,
        "project": contract.get("project"),
        "gate": contract.get("gate"),
        "change": contract.get("change"),
        "status": "PASS" if not failures else "FAIL",
        "candidate_head": revision,
        "requested_revision": requested_revision,
        "exact_candidate_bound": checks["candidate_binding"] and checks["artifact_binding"],
        "checks": checks,
        "candidate_binding": source,
        "secret_scan": {"production_inputs": production, "generated_artifacts": artifact_scan},
        "dependency_inventory": vendor,
        "requirements": requirements,
        "workflows": workflows,
        "runtime": {"external_origins": origins, "local_storage": storage, "static_controls": controls},
        "artifact_binding": binding,
        "advisory_review": contract.get("advisory_review", {}),
        "verify_required": verify_required,
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision")
    parser.add_argument("--scan-root", action="append", default=[])
    args = parser.parse_args()
    report = run_gate(ROOT, args.revision, [Path(path).resolve() for path in args.scan_root])
    EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "candidate_head": report["candidate_head"], "checks": report["checks"], "failures": report["failures"][:20]}, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
