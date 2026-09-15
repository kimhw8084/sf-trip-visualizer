"""Package only the tested map-first build, local assets, evidence and hashes."""

import hashlib
import json
import shutil
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NAME = "SF_Trip_Universal_Golden_36Places_2026-09-14"
DEST = ROOT / NAME
ARCHIVE = ROOT / f"{NAME}.zip"
if DEST.exists() or ARCHIVE.exists():
    raise SystemExit("Final package already exists; inspect it before choosing another name.")


def load(name):
    return json.loads((ROOT / name).read_text())


full = load("QA/map_first/full_acceptance.json")
p0 = load("QA/map_first/p0_independent.json")
standalone = load("QA/map_first/standalone.json")
photos = load("QA/photo_integrity.json")
gap = load("QA/map_first/location_gap_visuals.json")
exhaustive = load("QA/exhaustive_states.json")
cross_browser = load("QA/final_cross_browser.json")
visual_spots = load("QA/visual_spots.json")
dynamics = load("QA/map_first/interaction_dynamics.json")
continuity = load("QA/map_first/route_continuity.json")
route_panel = load("QA/route_panel/route_explanations_panel.json")
expected_places = photos["places_with_exact_roles"]
expected_assets = photos["required"]
if not (
    full["status"] == "PASS"
    and full["checks"]["matrix"]["states"] == 600
    and not full["checks"]["matrix"]["failed"]
    and p0["status"] == "PASS"
    and len(p0["detail_reviews"]) == expected_places == 36
    and photos["status"] == "PASS"
    and photos["present_decodable_originals"] == expected_assets == 108
    and photos["present_decodable_thumbnails"] == expected_assets
    and photos["present_decodable_medium"] == expected_assets
    and gap["status"] == "PASS"
    and exhaustive["status"] == "PASS"
    and exhaustive["rendered_states"] == 600
    and all(row["status"] == "PASS" for row in cross_browser)
    and visual_spots["status"] == "PASS"
    and dynamics["status"] == "PASS"
    and continuity["status"] == "PASS"
    and route_panel["status"] == "PASS"
    and standalone["provider"] == "vector"
    and standalone["decoded"]
    and not standalone["remote_requests"]
    and not standalone["page_errors"]
):
    raise SystemExit("Fresh P0, photo or standalone evidence is not PASS; refusing to package.")

files = {
    "README.md", "P0_PROOF_REPORT.md", "PHASE2_UNBLOCK_STATUS.md", "LOCATION_COVERAGE_AUDIT.md", "ROUTE_REGRET_AUDIT_2026-09-15.md", "TRIP_VISUALIZER_SCHEMA.md",
    "requirements-qa.txt", "handoff(1).txt", "SF_Trip_FINAL_SELECTION_50Criteria_2026-09-13.xlsx",
    "index.html", "index_map_first.html",
    "SF_Smart_Minority_Map_First_Standalone.html",
    "SF_Trip_Smart_Minority_4_Itineraries_Data(1).json",
    "SF_Trip_4_Routes_VISUAL_MASTER_MAP_v2_Data(1).json",
    "QA/photo_integrity.json",
    "QA/photo_candidates/candidates.json",
    "vendor/maplibre-gl.js", "vendor/maplibre-gl.css", "vendor/trip-vector.js",
}
for folder in ("src", "data", "manifests", "assets/photos", "assets/vector/fonts", "assets/vector/sprites", "QA/photo_review", "QA/photo_candidates/sheets", ".audit_workbook"):
    files.update(str(path.relative_to(ROOT)) for path in (ROOT / folder).rglob("*") if path.is_file() and path.name != "offline_basemap_manifest.json")
files.update({
    "assets/vector/sf_trip.pmtiles",
    "assets/vector/yosemite_hillshade_source.png",
    "assets/vector/yosemite_hillshade_shadow.webp",
})
for script in (
    "build_map_first.py", "serve_map.py", "cache_route_geometry.py", "refresh_map_first_manifests.py",
    "build_hillshade.py", "build_i18n.py", "collect_i18n.py", "translate_local.swift",
    "discover_photos.py", "external_photo_candidates.py", "localize_photos.py", "photo_review_sheets.py",
    "check_photo_integrity.py", "qa_map_first.py", "qa_map_first_full.py",
    "qa_map_first_p0.py", "qa_standalone_map_first.py", "qa_location_gap_visuals.py",
    "run_exhaustive_states.py", "run_cross_browser.py", "run_visual_spots.py",
    "apply_location_gap_audit.py", "expand_photo_manifest.py", "add_official_candidates.py",
    "audit_selection_workbook.mjs", "package_map_first.py", "audit_route_continuity.py", "qa_interaction_dynamics.py",
    "qa_route_explanations_panel.py", "refresh_package_hashes.py",
):
    files.add("scripts/" + script)
files.update({"QA/exhaustive_states.json", "QA/final_cross_browser.json", "QA/visual_spots.json"})
files.update({"QA/route_panel/route_explanations_panel.json"})
files.update({
    "QA/map_first/full_acceptance.json", "QA/map_first/filter_matrix.json",
    "QA/map_first/p0_independent.json", "QA/map_first/standalone.json",
    "QA/map_first/location_gap_visuals.json", "QA/map_first/interaction_dynamics.json",
    "QA/map_first/route_continuity.json",
    "QA/map_first/VISUAL_REVIEW.md",
})
files.update(full["screenshots"])
files.update(gap["screenshots"])
files.update(dynamics["screenshots"])
files.update(route_panel["desktop"].get(key) for key in ("tooltip_screenshot", "resized_screenshot", "english_tooltip_screenshot"))
files.add(route_panel["route_repair"]["screenshot"])
files.update(row["screenshot"] for row in route_panel["mobile"].values())
files.update(row["screenshot"] for row in cross_browser)
files.update(row["screenshot"] for row in visual_spots["rows"])
files.update({"QA/map_first/theme_english_dark_1440.png", "QA/map_first/theme_korean_dark_1440.png", "QA/map_first/standalone_1280.png"})

DEST.mkdir()
for name in sorted(files):
    source = ROOT / name
    if not source.is_file():
        raise SystemExit(f"Missing package input: {name}")
    target = DEST / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


hashes = {str(path.relative_to(DEST)): digest(path) for path in sorted(DEST.rglob("*")) if path.is_file()}
(DEST / "MANIFEST_SHA256.json").write_text(json.dumps({"algorithm": "SHA-256", "file_count": len(hashes), "files": hashes}, ensure_ascii=False, indent=2) + "\n")
with zipfile.ZipFile(ARCHIVE, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=3, allowZip64=True) as zip_file:
    for path in sorted(DEST.rglob("*")):
        if path.is_file():
            zip_file.write(path, arcname=str(Path(NAME) / path.relative_to(DEST)))

print(json.dumps({"folder": str(DEST), "zip": str(ARCHIVE), "files_hashed": len(hashes), "zip_bytes": ARCHIVE.stat().st_size, "zip_sha256": digest(ARCHIVE), "browser_checks": f"{p0['passed']}/{p0['total']}", "photo_originals": photos["present_decodable_originals"]}, indent=2))
