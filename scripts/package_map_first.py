#!/usr/bin/env python3
"""Package the exact qualified modular, standalone, and public artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import zipfile
from pathlib import Path

from public_asset_rights import audit_tree, load_contract, load_json


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / ".build"
PUBLIC = ROOT / ".public-site"
QUALIFICATION = ROOT / "QA" / "CHG-188" / "release" / "qualification.json"
DEFAULT_DESTINATION = ROOT / ".release" / "package"
DEFAULT_ARCHIVE = ROOT / ".release" / "package.zip"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_hashes(root: Path) -> dict[str, str]:
    return {str(path.relative_to(root)): digest(path) for path in sorted(root.rglob("*")) if path.is_file() and path.name != "PACKAGE_MANIFEST.json"}


def copy_tree(source: Path, target: Path) -> None:
    if not source.is_dir():
        raise SystemExit(f"Missing package input directory: {source}")
    shutil.copytree(source, target)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", default=str(DEFAULT_DESTINATION))
    parser.add_argument("--archive", default=str(DEFAULT_ARCHIVE))
    parser.add_argument("--revision", required=True)
    args = parser.parse_args()
    destination = Path(args.destination)
    archive = Path(args.archive)
    if not destination.is_absolute():
        destination = ROOT / destination
    if not archive.is_absolute():
        archive = ROOT / archive
    destination = destination.resolve()
    archive = archive.resolve()
    if destination == ROOT or ROOT in destination.parents and destination.name in {"src", "vendor", "assets", "data"}:
        raise SystemExit(f"Refusing unsafe package directory: {destination}")
    qualification = json.loads(QUALIFICATION.read_text()) if QUALIFICATION.is_file() else {}
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if qualification.get("status") != "PASS" or qualification.get("candidate_head") != args.revision or head != args.revision:
        raise SystemExit("A PASS qualification for the exact checkout is required before packaging.")
    build_manifest = BUILD / "build_manifest.json"
    if qualification.get("build", {}).get("manifest_sha256") != digest(build_manifest) or qualification.get("build", {}).get("modular_index_sha256") != digest(BUILD / "modular" / "index.html") or qualification.get("build", {}).get("standalone_sha256") != digest(BUILD / "standalone" / "SF_Smart_Minority_Map_First_Standalone.html"):
        raise SystemExit("Qualified build inputs changed after qualification; refusing to package.")
    for required in (BUILD / "modular" / "index.html", BUILD / "standalone" / "SF_Smart_Minority_Map_First_Standalone.html", PUBLIC / "index.html", PUBLIC / ".release-provenance.json"):
        if not required.is_file():
            raise SystemExit(f"Missing qualified release input: {required}")
    if destination.exists():
        shutil.rmtree(destination)
    if archive.exists():
        archive.unlink()
    destination.mkdir(parents=True)

    for relative in ("README.md", "TRIP_VISUALIZER_SCHEMA.md", "requirements-qa.txt"):
        shutil.copy2(ROOT / relative, destination / relative)
    for folder in ("src", "data", "manifests", "scripts", "vendor"):
        copy_tree(ROOT / folder, destination / folder)
    for folder in ("assets/vector/fonts", "assets/vector/sprites", "assets/photos/thumb", "assets/photos/medium"):
        copy_tree(ROOT / folder, destination / folder)
    for relative in ("assets/vector/sf_trip.pmtiles", "assets/vector/yosemite_hillshade_source.png", "assets/vector/yosemite_hillshade_shadow.webp"):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    copy_tree(BUILD / "modular", destination / "artifacts/modular")
    copy_tree(BUILD / "standalone", destination / "artifacts/standalone")
    copy_tree(PUBLIC, destination / "artifacts/public")
    for relative in ("QA/CHG-188/photo_integrity.json", "QA/CHG-188/map_first_full", "QA/CHG-188/route_surface.json", "QA/CHG-188/release"):
        source = ROOT / relative
        if source.is_dir():
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.mkdir(parents=True, exist_ok=True)
            for path in sorted(source.rglob("*")):
                if path.is_file() and path.name not in {"gate4.json", "public_asset_rights_package.json"} and (path.suffix == ".json" or path.name == "VISUAL_REVIEW.md"):
                    target_path = destination / path.relative_to(ROOT)
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, target_path)
        elif source.is_file():
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

    contract = load_contract()
    photo_manifest = load_json(ROOT / "manifests" / "asset_manifest.json")
    public_audit = audit_tree(destination / "artifacts/public", contract=contract, manifest=photo_manifest, mode="pages")
    package_audit = audit_tree(destination, contract=contract, manifest=photo_manifest, mode="public-package")
    package_rights_report = ROOT / "QA" / "CHG-188" / "release" / "public_asset_rights_package.json"
    package_rights_report.parent.mkdir(parents=True, exist_ok=True)
    package_rights_report.write_text(json.dumps({"public_tree": public_audit, "package_tree": package_audit}, ensure_ascii=False, indent=2) + "\n")
    if public_audit["status"] != "PASS" or package_audit["status"] != "PASS":
        shutil.rmtree(destination)
        raise SystemExit("Public package rights audit failed: " + json.dumps({"public_tree": public_audit["failures"], "package_tree": package_audit["failures"]}, ensure_ascii=False))

    files = tree_hashes(destination)
    package_manifest = {
        "schema_version": 1,
        "project": "sf-trip-visualizer",
        "tested_sha": args.revision,
        "qualification_sha256": digest(QUALIFICATION),
        "file_count_excluding_manifest": len(files),
        "files": files,
    }
    (destination / "PACKAGE_MANIFEST.json").write_text(json.dumps(package_manifest, ensure_ascii=False, indent=2) + "\n")
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=3, allowZip64=True) as zip_file:
        for path in sorted(destination.rglob("*")):
            if not path.is_file():
                continue
            info = zipfile.ZipInfo(str(Path(destination.name) / path.relative_to(destination)))
            info.date_time = (1980, 1, 1, 0, 0, 0)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            zip_file.writestr(info, path.read_bytes())
    print(json.dumps({"folder": str(destination), "zip": str(archive), "tested_sha": args.revision, "files": len(files) + 1, "zip_sha256": digest(archive)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
