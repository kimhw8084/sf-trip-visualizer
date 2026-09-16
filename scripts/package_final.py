"""Create an immutable P0 handoff folder, SHA-256 manifest, and complete ZIP."""

raise SystemExit("DEPRECATED LEGACY ENTRY POINT: use python3 scripts/pipeline.py package")

import hashlib
import json
import shutil
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NAME = "SF_Trip_Golden_Template_v2_2026-09-13"
DEST = ROOT / NAME
ZIP = ROOT / f"{NAME}.zip"
if DEST.exists() or ZIP.exists():
    raise SystemExit("Final folder/ZIP already exists; inspect before choosing a new package name.")

qa = json.loads((ROOT / "QA/final_acceptance.json").read_text())
cross = json.loads((ROOT / "QA/final_cross_browser.json").read_text())
live = json.loads((ROOT / "QA/final_live_providers.json").read_text())
integrity = json.loads((ROOT / "QA/photo_integrity.json").read_text())
exhaustive = json.loads((ROOT / "QA/exhaustive_states.json").read_text())
visual = json.loads((ROOT / "QA/visual_spots.json").read_text())
if qa["status"] != "PASS" or live["status"] != "PASS" or integrity["status"] != "PASS" or exhaustive["status"] != "PASS" or exhaustive["rendered_states"] != 600 or visual["status"] != "PASS" or any(row["status"] != "PASS" for row in cross):
    raise SystemExit("QA or photo integrity is not PASS; refusing to package.")

files = [
    "README.md", "PHASE2_UNBLOCK_STATUS.md", "P0_PROOF_REPORT.md", "requirements-qa.txt",
    "SF_Smart_Minority_P0_Final_Standalone.html", "index.html", "index_phase7.html",
    "SF_Trip_Smart_Minority_4_Itineraries_Data(1).json",
    "SF_Trip_4_Routes_VISUAL_MASTER_MAP_v2_Data(1).json",
]
for folder in ("src", "vendor", "assets/photos", "assets/basemap", "data", "manifests", "scripts"):
    files.extend(str(p.relative_to(ROOT)) for p in (ROOT / folder).rglob("*") if p.is_file() and p.suffix != ".pyc" and p.name != "photo_acquisition_queue.json")
qa_files = [
    "QA/final_acceptance.json", "QA/final_cross_browser.json", "QA/final_live_providers.json", "QA/exhaustive_states.json", "QA/visual_spots.json", "QA/visual_review.md", "QA/photo_integrity.json", "QA/phase8_acceptance.json",
    "QA/phase8_run.log", "QA/phase6_7_final_qa.json", "QA/provider_ready_fixture_qa.json",
    "QA/phase7_dimensions.json", "QA/photo_candidates/candidates.json",
]
files.extend(qa_files)
for folder in ("QA/screenshots", "QA/photo_review", "QA/photo_candidates/sheets"):
    files.extend(str(p.relative_to(ROOT)) for p in (ROOT / folder).rglob("*") if p.is_file() and (folder != "QA/screenshots" or (p.name.startswith("final_") and p.name != "final_provider_light_watermark_rejected.png")))

DEST.mkdir()
for name in sorted(set(files)):
    source = ROOT / name
    if not source.is_file():
        raise SystemExit(f"Missing required package file: {name}")
    target = DEST / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)

hashes = {}
for file in sorted(DEST.rglob("*")):
    if file.is_file():
        hashes[str(file.relative_to(DEST))] = hashlib.sha256(file.read_bytes()).hexdigest()
sha_manifest = {"algorithm": "SHA-256", "file_count": len(hashes), "files": hashes}
(DEST / "MANIFEST_SHA256.json").write_text(json.dumps(sha_manifest, indent=2) + "\n")
(ROOT / "MANIFEST_SHA256.json").write_text(json.dumps(sha_manifest, indent=2) + "\n")

with zipfile.ZipFile(ZIP, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
    for file in sorted(DEST.rglob("*")):
        if file.is_file():
            archive.write(file, arcname=str(Path(NAME) / file.relative_to(DEST)))

print(json.dumps({
    "folder": str(DEST), "zip": str(ZIP), "files_hashed": len(hashes),
    "zip_sha256": hashlib.sha256(ZIP.read_bytes()).hexdigest(),
    "zip_bytes": ZIP.stat().st_size,
    "qa_checks": f"{qa['passed_checks']}/{qa['total_checks']}",
    "photo_originals": integrity["present_decodable_originals"],
}, indent=2))
