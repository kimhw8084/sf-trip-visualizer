#!/usr/bin/env python3
"""Build the authored calm field atlas into modular and standalone artifacts."""

from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import json
import os
import shutil
from pathlib import Path

from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
from trip_package import DEFAULT_PACKAGE, load_package, validate_portable_data

ENGINE_FILES = (
    "src/app_phase7.css", "src/app_phase7.js", "src/atlas_messages.js", "src/atlas_state.js", "src/runtime_loader.js", "src/map_first.css",
    "vendor/maplibre-gl.css", "vendor/maplibre-gl.js", "vendor/trip-vector.js", "vendor/plotly.min.js",
)


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def tree_hashes(root: Path) -> dict[str, str]:
    return {str(path.relative_to(root)): digest(path) for path in sorted(root.rglob("*")) if path.is_file() and path.name != "build_manifest.json"}


def copy_runtime(modular: Path, package: dict) -> None:
    for relative in ENGINE_FILES:
        source = ROOT / relative
        if not source.is_file():
            raise SystemExit(f"Missing required runtime file: {relative}")
        target = modular / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    package_assets = package["assets"]
    paths = [package_assets["photos"]["thumb_dir"], package_assets["photos"]["medium_dir"], *package_assets["map"]["local_resources"]]
    copied = set()
    for relative in paths:
        if relative in copied:
            continue
        copied.add(relative)
        source = ROOT / relative
        target = modular / relative
        if source.is_dir():
            shutil.copytree(source, target)
        elif source.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        else:
            raise SystemExit(f"Missing required package asset: {relative}")


def build(output_root: Path, package_path: str | Path | None = None) -> dict:
    package = load_package(package_path)
    data = package["data"]
    trip_contract = validate_portable_data(package)
    output_root = output_root.resolve()
    if output_root == ROOT or any(output_root == ROOT / part for part in ("src", "vendor", "assets", "data")):
        raise SystemExit(f"Refusing unsafe generated output directory: {output_root}")
    if output_root.exists():
        shutil.rmtree(output_root)
    modular_dir, standalone_dir = output_root / "modular", output_root / "standalone"
    modular_dir.mkdir(parents=True)
    standalone_dir.mkdir(parents=True)

    paths = {key: ROOT / value for key, value in package["projections"].items()}
    role_matrix = json.loads(paths["route_roles"].read_text())
    route_schedules = json.loads(paths["route_schedules"].read_text())
    research_ledger = json.loads(paths["research_ledger"].read_text())
    photo_manifest = json.loads(paths["photos_manifest"].read_text())
    place_count, photo_count = len(data["markers"]), len(photo_manifest["assets"])
    if place_count != len(role_matrix["places"]):
        raise SystemExit("Canonical place/role projection invariant failed before build; refusing to emit artifacts.")
    if sorted(data.get("routes", {})) != sorted(role_matrix.get("route_ids", [])) or data.get("route_roles") != role_matrix.get("places"):
        raise SystemExit("Canonical route-role projection is stale; refusing to emit artifacts.")
    if not data.get("routes") or any(set(roles) != set(data["routes"]) for roles in role_matrix.get("places", {}).values()):
        raise SystemExit("Canonical route-role source must define at least one route and one role per route/place.")
    if sorted(data.get("route_day_models", {})) != sorted(route_schedules.get("routes", {})):
        raise SystemExit("Canonical route-day projection is stale; refusing to emit artifacts.")
    if sum(bool(route.get("recommended")) for route in data["routes"].values()) != 1:
        raise SystemExit("Canonical route metadata must contain exactly one recommended strategy.")
    coordinate_audit_path = paths.get("coordinate_audit")
    coordinate_audit = {row["place_key"]: row for row in json.loads(coordinate_audit_path.read_text())} if coordinate_audit_path else {}
    for marker in data["markers"]:
        audit = coordinate_audit.get(marker["place_key"])
        if audit:
            marker["coordinate_role"] = audit["coordinate_type"]
            marker["coordinate_provenance"] = audit["verification_source"]
    data["phase2_frozen"] = False
    data["phase2_note"] = f"{photo_count} local photographs for {place_count} places, with local thumbnails and medium derivatives."

    geometry = json.loads(paths["route_geometry"].read_text())
    translations = json.loads(paths["translations"].read_text())
    freshness = json.loads(paths["freshness"].read_text())
    runtime_contract = json.loads((ROOT / "manifests" / "runtime_resilience_contract.json").read_text())
    template = BeautifulSoup((ROOT / "src" / "map_shell_template.html").read_text(), "html.parser")
    template.title.string = package["display_title"]
    title = template.select_one(".brand")
    if title:
        title.string = package["display_title"]
    subtitle = template.select_one(".sub")
    if subtitle:
        subtitle.string = package["subtitle"]["ko"]
    head = template.head
    head.append(template.new_tag("link", rel="stylesheet", href="vendor/maplibre-gl.css"))
    head.append(template.new_tag("link", rel="stylesheet", href="src/map_first.css"))
    photo_assets = {}
    photo_root = package["assets"]["photos"]["root"].rstrip("/")
    for item in photo_manifest["assets"]:
        key = item["place_key"]
        photo_assets.setdefault(key, {})[item["role"].lower()] = {
            "thumb": item["local_thumb_path"], "medium": item["local_medium_path"]
        }
        for field in ("local_thumb_path", "local_medium_path"):
            if not item[field].startswith(photo_root + "/") or not (ROOT / item[field]).is_file():
                raise SystemExit(f"Photo manifest path is outside the package photo root or missing: {item[field]}")
    runtime_assets = copy.deepcopy(package["assets"])
    runtime_assets["map"]["local_resource_directories"] = [
        relative for relative in runtime_assets["map"]["local_resources"] if (ROOT / relative).is_dir()
    ]
    package_runtime = {
        "trip_identity": package["trip_identity"], "display_title": package["display_title"],
        "subtitle": package["subtitle"], "slug": package["slug"], "currency": package["currency"],
        "is_non_shipping_fixture": bool(package.get("is_non_shipping_fixture")),
        "providers": package["providers"], "source_policy": package["source_policy"],
        "assets": runtime_assets, "photo_assets": photo_assets,
    }
    package_script = template.new_tag("script")
    package_script.string = "window.TRIP_PACKAGE=" + json.dumps(package_runtime, ensure_ascii=False, separators=(",", ":")) + ";"
    template.select_one("#tripData").insert_before(package_script)
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
    copy_runtime(modular_dir, package)

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
    photos = {}
    for asset in photo_manifest["assets"]:
        for field in ("local_thumb_path", "local_medium_path"):
            path = asset[field]
            photos[path] = "data:image/webp;base64," + base64.b64encode((ROOT / path).read_bytes()).decode("ascii")
    embed_photos = standalone.new_tag("script")
    embed_photos.string = "window.EMBEDDED_PHOTOS=" + json.dumps(photos, separators=(",", ":")) + ";"
    app_inline.insert_before(embed_photos)
    assets = {}
    for relative in package["assets"]["map"]["local_resources"]:
        path = ROOT / relative
        files = sorted(item for item in path.rglob("*") if item.is_file()) if path.is_dir() else [path]
        for asset_path in files:
            if asset_path == ROOT / package["assets"]["map"]["vector_archive"]:
                continue
            assets[str(asset_path.relative_to(ROOT))] = base64.b64encode(asset_path.read_bytes()).decode("ascii")
    embed_assets = standalone.new_tag("script")
    embed_assets.string = "window.EMBEDDED_MAP_ASSETS=" + json.dumps(assets, separators=(",", ":")) + ";"
    app_inline.insert_before(embed_assets)
    vector = base64.b64encode((ROOT / package["assets"]["map"]["vector_archive"]).read_bytes()).decode("ascii")
    vector_script = standalone.new_tag("script")
    vector_script.string = "window.EMBEDDED_VECTOR=" + json.dumps(vector) + ";"
    app_inline.insert_before(vector_script)
    # Keep the released artifact name stable; the authored shell inside is the atlas redesign.
    standalone_name = f"{package['slug']}-standalone.html"
    standalone_path = standalone_dir / standalone_name
    standalone_path.write_text(str(standalone))
    alias = package.get("compatibility_alias")
    if alias:
        if Path(alias).name != alias or not alias.endswith(".html"):
            raise SystemExit("Invalid standalone compatibility alias in package descriptor")
        os.link(standalone_path, standalone_dir / alias)

    manifest = {
        "schema_version": 2,
        "package_descriptor": package["descriptor_path"],
        "trip_identity": package["trip_identity"],
        "display_title": package["display_title"],
        "slug": package["slug"],
        "currency": package["currency"],
        "is_non_shipping_fixture": bool(package.get("is_non_shipping_fixture")),
        "canonical_data": package["canonical_data"],
        "runtime_contract": "trip package provider configuration",
        "trip_contract": trip_contract,
        "counts": {"places": place_count, "photos": photo_count, "timeline_cards": len(data["timeline"]), "route_legs": len(data["legs"]), "routes": len(data["routes"]), "active_route_ids": sorted(data["routes"])},
        "modular": {"path": str((modular_dir / "index.html").relative_to(output_root)), "sha256": digest(modular_dir / "index.html")},
        "standalone": {"path": str(standalone_path.relative_to(output_root)), "sha256": digest(standalone_path), "compatibility_alias": alias},
        "files": tree_hashes(output_root),
    }
    (output_root / "build_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    manifest["files"] = tree_hashes(output_root)
    (output_root / "build_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"output": str(output_root), "package": package["trip_identity"], "modular": str(modular_dir / "index.html"), "standalone": str(standalone_path), "files": len(manifest["files"]), "counts": manifest["counts"]}, ensure_ascii=False))
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default=str(ROOT / ".build"), help="generated build directory")
    parser.add_argument("--package", default=DEFAULT_PACKAGE, help="trip package descriptor path")
    args = parser.parse_args()
    requested = Path(args.output_dir)
    build(requested if requested.is_absolute() else ROOT / requested, args.package)


if __name__ == "__main__":
    main()
