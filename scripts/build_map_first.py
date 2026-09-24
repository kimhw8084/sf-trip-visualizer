#!/usr/bin/env python3
"""Build the authored calm field atlas into modular and standalone artifacts."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import shutil
from pathlib import Path

from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "phase7_app_data.json"
ROLE_MATRIX_PATH = ROOT / "data" / "route_role_matrix.json"
ROUTE_SCHEDULES_PATH = ROOT / "data" / "route_schedules.json"
RESEARCH_LEDGER_PATH = ROOT / "data" / "route_research_ledger.json"
PHOTO_MANIFEST_PATH = ROOT / "manifests" / "asset_manifest.json"
FRESHNESS_MANIFEST_PATH = ROOT / "manifests" / "trip_freshness.json"
RUNTIME_CONTRACT_PATH = ROOT / "manifests" / "runtime_resilience_contract.json"
COORDINATE_AUDIT_PATH = ROOT / "data" / "coordinate_audit.json"
MODULAR_FILES = (
    "src/app_phase7.css", "src/app_phase7.js", "src/atlas_messages.js", "src/atlas_state.js", "src/runtime_loader.js", "src/map_first.css",
    "vendor/maplibre-gl.css", "vendor/maplibre-gl.js", "vendor/trip-vector.js", "vendor/plotly.min.js",
    "assets/vector/sf_trip.pmtiles", "assets/vector/yosemite_hillshade_shadow.webp",
)
MODULAR_DIRECTORIES = ("assets/vector/fonts", "assets/vector/sprites", "assets/photos/thumb", "assets/photos/medium")


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def tree_hashes(root: Path) -> dict[str, str]:
    return {str(path.relative_to(root)): digest(path) for path in sorted(root.rglob("*")) if path.is_file() and path.name != "build_manifest.json"}


def copy_runtime(modular: Path) -> None:
    for relative in MODULAR_FILES:
        source = ROOT / relative
        if not source.is_file():
            raise SystemExit(f"Missing required runtime file: {relative}")
        target = modular / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    for relative in MODULAR_DIRECTORIES:
        source = ROOT / relative
        if not source.is_dir():
            raise SystemExit(f"Missing required runtime directory: {relative}")
        shutil.copytree(source, modular / relative)


def build(output_root: Path) -> dict:
    output_root = output_root.resolve()
    if output_root == ROOT or any(output_root == ROOT / part for part in ("src", "vendor", "assets", "data")):
        raise SystemExit(f"Refusing unsafe generated output directory: {output_root}")
    if output_root.exists():
        shutil.rmtree(output_root)
    modular_dir, standalone_dir = output_root / "modular", output_root / "standalone"
    modular_dir.mkdir(parents=True)
    standalone_dir.mkdir(parents=True)

    data = json.loads(DATA_PATH.read_text())
    role_matrix = json.loads(ROLE_MATRIX_PATH.read_text())
    route_schedules = json.loads(ROUTE_SCHEDULES_PATH.read_text())
    research_ledger = json.loads(RESEARCH_LEDGER_PATH.read_text())
    photo_manifest = json.loads(PHOTO_MANIFEST_PATH.read_text())
    place_count, photo_count = len(data["markers"]), len(photo_manifest["assets"])
    if (place_count, photo_count) != (len(role_matrix["places"]), len(role_matrix["places"]) * 3):
        raise SystemExit("Canonical place/photo invariant failed before build; refusing to emit artifacts.")
    if sorted(data.get("routes", {})) != sorted(role_matrix.get("route_ids", [])) or data.get("route_roles") != role_matrix.get("places"):
        raise SystemExit("Canonical route-role projection is stale; refusing to emit artifacts.")
    if not data.get("routes") or any(set(roles) != set(data["routes"]) for roles in role_matrix.get("places", {}).values()):
        raise SystemExit("Canonical route-role source must define at least one route and one role per route/place.")
    if sorted(data.get("route_day_models", {})) != sorted(route_schedules.get("routes", {})):
        raise SystemExit("Canonical route-day projection is stale; refusing to emit artifacts.")
    if sorted(data["providers"]) != ["satellite", "vector"]:
        raise SystemExit("Canonical provider invariant failed before build; refusing to emit artifacts.")
    if sum(bool(route.get("recommended")) for route in data["routes"].values()) != 1:
        raise SystemExit("Canonical route metadata must contain exactly one recommended strategy.")

    data["providers"]["vector"] = {
        "label": "Local Protomaps vector · OpenStreetMap data",
        "identity": "MapLibre 4.7.1+sf-trip-visualizer-r6 · local PMTiles",
        "failure_domain": "local bundled PMTiles",
        "attribution": "© OpenStreetMap contributors · Protomaps",
        "requires_api_key": False,
        "status_at_build": "LOCAL_VECTOR_PM_TILES_READY",
    }
    coordinate_audit = {row["place_key"]: row for row in json.loads(COORDINATE_AUDIT_PATH.read_text())}
    for marker in data["markers"]:
        audit = coordinate_audit.get(marker["place_key"])
        if audit:
            marker["coordinate_role"] = audit["coordinate_type"]
            marker["coordinate_provenance"] = audit["verification_source"]
    data["phase2_frozen"] = False
    data["phase2_note"] = f"{photo_count} local real photographs for {place_count} places, with local thumbnails and medium derivatives."

    geometry = json.loads((ROOT / "data" / "route_geometry_cache.json").read_text())
    translations = json.loads((ROOT / "data" / "translations.json").read_text())
    freshness = json.loads(FRESHNESS_MANIFEST_PATH.read_text())
    runtime_contract = json.loads(RUNTIME_CONTRACT_PATH.read_text())
    template = BeautifulSoup((ROOT / "src" / "map_shell_template.html").read_text(), "html.parser")
    template.title.string = "Smart Minority · SF / Monterey / Yosemite Field Atlas"
    head = template.head
    head.append(template.new_tag("link", rel="stylesheet", href="vendor/maplibre-gl.css"))
    head.append(template.new_tag("link", rel="stylesheet", href="src/map_first.css"))
    template.select_one("#tripData").string = "window.TRIP_DATA=" + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";"
    runtime_loader = template.select_one('script[src="src/runtime_loader.js"]')
    for name, payload in (("TRIP_ROUTE_GEOMETRY", geometry), ("TRIP_I18N", translations), ("TRIP_FRESHNESS", freshness), ("TRIP_RESEARCH_LEDGER", research_ledger), ("TRIP_RUNTIME_CONTRACT", runtime_contract)):
        script = template.new_tag("script")
        script.string = f"window.{name}=" + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";"
        runtime_loader.insert_before(script)
    early = template.new_tag("script")
    early.string = "window.__tripStartupMarks=[];window.__tripLoadStarted=performance.now();window.__tripStartupMark=(name,detail={})=>window.__tripStartupMarks.push({name,at_ms:Math.round((performance.now()-window.__tripLoadStarted)*100)/100,...detail});window.__tripStartupMark('html_parse_start');document.addEventListener('DOMContentLoaded',()=>window.__tripStartupMark('dom_content_loaded'),{once:true});try{const t=localStorage.getItem('trip_theme');document.documentElement.dataset.theme=t==='dark'?'dark':'light'}catch{document.documentElement.dataset.theme='light'}"
    head.insert(0, early)
    (modular_dir / "index.html").write_text(str(template))
    copy_runtime(modular_dir)

    standalone = BeautifulSoup(str(template), "html.parser")
    credits = standalone.select_one(".credits-link")
    if credits:
        credits["href"] = "../public/ATTRIBUTION.md"
    for link in standalone.find_all("link", rel="stylesheet"):
        style = standalone.new_tag("style")
        style.string = (ROOT / link["href"]).read_text()
        link.replace_with(style)
    for script in standalone.find_all("script", src=True):
        if script["src"] != "src/runtime_loader.js":
            inline = standalone.new_tag("script")
            inline.string = (ROOT / script["src"]).read_text()
            script.replace_with(inline)
            continue
        inline_scripts = []
        for relative in ("src/atlas_messages.js", "src/atlas_state.js", "vendor/maplibre-gl.js", "vendor/trip-vector.js", "vendor/plotly.min.js", "src/app_phase7.js"):
            inline = standalone.new_tag("script")
            inline.string = (ROOT / relative).read_text()
            inline_scripts.append(inline)
        script.replace_with(inline_scripts[0])
        cursor = inline_scripts[0]
        for inline in inline_scripts[1:]:
            cursor.insert_after(inline)
            cursor = inline
    app_inline = standalone.find_all("script")[-1]
    hillshade_path = ROOT / "assets/vector/yosemite_hillshade_shadow.webp"
    hillshade = standalone.new_tag("script")
    hillshade.string = "window.EMBEDDED_HILLSHADE=" + json.dumps("data:image/webp;base64," + base64.b64encode(hillshade_path.read_bytes()).decode("ascii")) + ";"
    app_inline.insert_before(hillshade)
    photos = {}
    for asset in photo_manifest["assets"]:
        for field in ("local_thumb_path", "local_medium_path"):
            path = asset[field]
            photos[path] = "data:image/webp;base64," + base64.b64encode((ROOT / path).read_bytes()).decode("ascii")
    embed_photos = standalone.new_tag("script")
    embed_photos.string = "window.EMBEDDED_PHOTOS=" + json.dumps(photos, separators=(",", ":")) + ";"
    app_inline.insert_before(embed_photos)
    assets = {}
    for path in sorted((ROOT / "assets/vector/fonts").rglob("*.pbf")) + sorted((ROOT / "assets/vector/sprites").glob("*")):
        assets[str(path.relative_to(ROOT))] = base64.b64encode(path.read_bytes()).decode("ascii")
    embed_assets = standalone.new_tag("script")
    embed_assets.string = "window.EMBEDDED_MAP_ASSETS=" + json.dumps(assets, separators=(",", ":")) + ";"
    app_inline.insert_before(embed_assets)
    vector = base64.b64encode((ROOT / "assets/vector/sf_trip.pmtiles").read_bytes()).decode("ascii")
    vector_script = standalone.new_tag("script")
    vector_script.string = "window.EMBEDDED_VECTOR=" + json.dumps(vector) + ";"
    app_inline.insert_before(vector_script)
    # Keep the released artifact name stable; the authored shell inside is the atlas redesign.
    standalone_path = standalone_dir / "SF_Smart_Minority_Map_First_Standalone.html"
    standalone_path.write_text(str(standalone))

    manifest = {
        "schema_version": 2,
        "canonical_data": str(DATA_PATH.relative_to(ROOT)),
        "runtime_contract": str(RUNTIME_CONTRACT_PATH.relative_to(ROOT)),
        "counts": {"places": place_count, "photos": photo_count, "timeline_cards": len(data["timeline"]), "route_legs": len(data["legs"]), "routes": len(data["routes"]), "active_route_ids": sorted(data["routes"])},
        "modular": {"path": str((modular_dir / "index.html").relative_to(output_root)), "sha256": digest(modular_dir / "index.html")},
        "standalone": {"path": str(standalone_path.relative_to(output_root)), "sha256": digest(standalone_path)},
        "files": tree_hashes(output_root),
    }
    (output_root / "build_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    manifest["files"] = tree_hashes(output_root)
    (output_root / "build_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"output": str(output_root), "modular": str(modular_dir / "index.html"), "standalone": str(standalone_path), "files": len(manifest["files"]), "counts": manifest["counts"]}, ensure_ascii=False))
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default=str(ROOT / ".build"), help="generated build directory")
    args = parser.parse_args()
    requested = Path(args.output_dir)
    build(requested if requested.is_absolute() else ROOT / requested)


if __name__ == "__main__":
    main()
