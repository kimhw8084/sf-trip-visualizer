#!/usr/bin/env python3
"""Assemble Pages from the exact build that passed release qualification."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / ".build" / "modular"
DEFAULT_OUTPUT = ROOT / ".public-site"
QUALIFICATION = ROOT / "QA" / "release" / "qualification.json"
PROVENANCE = ".release-provenance.json"


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def tree_digest(root: Path, exclude: set[str] | None = None) -> tuple[str, int, int]:
    exclude = exclude or set()
    hasher = hashlib.sha256()
    files = [path for path in sorted(root.rglob("*")) if path.is_file() and str(path.relative_to(root)) not in exclude]
    for path in files:
        relative = str(path.relative_to(root)).encode()
        hasher.update(relative)
        hasher.update(b"\0")
        hasher.update(bytes.fromhex(digest(path)))
        hasher.update(b"\n")
    return hasher.hexdigest(), len(files), sum(path.stat().st_size for path in files)


def current_revision() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", default=str(DEFAULT_SOURCE), help="canonical generated modular build")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT), help="Pages staging directory")
    parser.add_argument("--revision", required=True, help="exact checkout SHA that qualified the build")
    args = parser.parse_args()
    source = Path(args.source_dir)
    if not source.is_absolute():
        source = ROOT / source
    output = Path(args.output_dir)
    if not output.is_absolute():
        output = ROOT / output
    source = source.resolve()
    output = output.resolve()
    if output == ROOT or ROOT in output.parents and output.name in {"src", "vendor", "assets", "data", ".build"}:
        raise SystemExit(f"Refusing unsafe public output directory: {output}")
    if not source.is_dir() or not (source / "index.html").is_file():
        raise SystemExit(f"Canonical modular build is missing: {source}")
    if not QUALIFICATION.is_file():
        raise SystemExit("No QA/release/qualification.json; public assembly is gated on full qualification.")
    qualification = json.loads(QUALIFICATION.read_text())
    head = current_revision()
    if qualification.get("status") != "PASS":
        raise SystemExit("Full qualification is not PASS; refusing to assemble public output.")
    if qualification.get("candidate_head") != args.revision or head != args.revision:
        raise SystemExit("Qualification SHA does not match the exact checkout revision; refusing to assemble public output.")
    build = json.loads((ROOT / ".build" / "build_manifest.json").read_text())
    expected_manifest_sha = qualification.get("build", {}).get("manifest_sha256")
    if expected_manifest_sha != digest(ROOT / ".build" / "build_manifest.json"):
        raise SystemExit("The build manifest changed after qualification; refusing to assemble public output.")
    expected_build_sha = qualification.get("build", {}).get("modular_index_sha256")
    if expected_build_sha != build.get("modular", {}).get("sha256") or expected_build_sha != digest(source / "index.html"):
        raise SystemExit("The modular build changed after qualification; refusing to assemble public output.")
    expected_standalone_sha = qualification.get("build", {}).get("standalone_sha256")
    standalone = ROOT / ".build" / "standalone" / "SF_Smart_Minority_Map_First_Standalone.html"
    if not expected_standalone_sha or expected_standalone_sha != digest(standalone):
        raise SystemExit("The standalone build changed after qualification; refusing to assemble public output.")

    if output.exists():
        shutil.rmtree(output)
    shutil.copytree(source, output)
    shutil.copy2(QUALIFICATION, output / ".release-qualification.json")
    (output / ".nojekyll").touch()
    artifact_sha, file_count, byte_count = tree_digest(output, {PROVENANCE})
    provenance = {
        "schema_version": 1,
        "project": "sf-trip-visualizer",
        "tested_sha": args.revision,
        "qualification_sha256": digest(QUALIFICATION),
        "build_manifest_sha256": digest(ROOT / ".build" / "build_manifest.json"),
        "modular_index_sha256": digest(source / "index.html"),
        "artifact_sha256_excluding_provenance": artifact_sha,
        "artifact_file_count_excluding_provenance": file_count,
        "artifact_bytes_excluding_provenance": byte_count,
    }
    (output / PROVENANCE).write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"output": str(output), "tested_sha": args.revision, "files": file_count + 1, "bytes": byte_count + (output / PROVENANCE).stat().st_size}, ensure_ascii=False))


if __name__ == "__main__":
    main()
