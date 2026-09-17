"""Build the canonical map-first modular and standalone artifacts.

This component is intentionally read-only with respect to authored inputs. It
materializes all build products below the supplied generated output directory.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import shutil
from pathlib import Path

from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "phase7_app_data.json"  # Current authored data; see canonical_pipeline.json.
DEFAULT_OUTPUT = ROOT / ".build"
PHOTO_MANIFEST_PATH = ROOT / "manifests" / "asset_manifest.json"
FRESHNESS_MANIFEST_PATH = ROOT / "manifests" / "trip_freshness.json"
RUNTIME_CONTRACT_PATH = ROOT / "manifests" / "runtime_resilience_contract.json"
COORDINATE_AUDIT_PATH = ROOT / "data" / "coordinate_audit.json"

MODULAR_FILES = (
    "src/app_phase7.css",
    "src/app_phase7.js",
    "src/map_first.css",
    "vendor/plotly.min.js",
    "vendor/maplibre-gl.css",
    "vendor/maplibre-gl.js",
    "vendor/trip-vector.js",
    "assets/vector/sf_trip.pmtiles",
    "assets/vector/yosemite_hillshade_shadow.webp",
)
MODULAR_DIRECTORIES = (
    "assets/vector/fonts",
    "assets/vector/sprites",
    "assets/photos/thumb",
    "assets/photos/medium",
)


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def tree_hashes(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): digest(path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != "build_manifest.json"
    }


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
    if output_root == ROOT or ROOT in output_root.parents and output_root.name in {"src", "vendor", "assets", "data"}:
        raise SystemExit(f"Refusing unsafe generated output directory: {output_root}")
    if output_root.exists():
        shutil.rmtree(output_root)
    modular_dir = output_root / "modular"
    standalone_dir = output_root / "standalone"
    modular_dir.mkdir(parents=True)
    standalone_dir.mkdir(parents=True)

    data = json.loads(DATA_PATH.read_text())
    photo_manifest = json.loads(PHOTO_MANIFEST_PATH.read_text())
    place_count = len(data["markers"])
    photo_count = len(photo_manifest["assets"])
    if (place_count, photo_count, len(data["timeline"]), len(data["legs"])) != (36, 108, 79, 41):
        raise SystemExit("Canonical product invariant failed before build; refusing to emit artifacts.")
    if sorted(data["providers"]) != ["satellite", "vector"]:
        raise SystemExit("Canonical provider invariant failed before build; refusing to emit artifacts.")

    # These are build-time annotations on a loaded copy, never writes to DATA_PATH.
    data["providers"]["vector"] = {
        "label": "Local Protomaps vector · OpenStreetMap data",
        "failure_domain": "local bundled PMTiles",
        "attribution": "© OpenStreetMap contributors · Protomaps",
        "requires_api_key": False,
        "status_at_build": "LOCAL_VECTOR_PM_TILES_READY".replace(" ", ""),
    }
    data["providers"] = {key: value for key, value in data["providers"].items() if key in {"vector", "satellite"}}
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
    template.title.string = "Smart Minority · SF / Monterey / Yosemite Map"
    template.select_one(".sub")["data-i18n"] = "subtitle"
    template.select_one(".sub").string = f"Four routes · nine days · {photo_count} real photos · {place_count} verified places"
    for label in template.select(".group-label"):
        label["data-i18n"] = label.get_text(strip=True).lower()
    route_group = template.select_one("[data-route]").parent
    for button in route_group.select("[data-route]"):
        button.decompose()
    for route, meta in data["routes"].items():
        pair = template.new_tag("span", attrs={"class": "route-control-pair"})
        button = template.new_tag("button", attrs={"class": "ctl routeCtl active", "data-route": route, "aria-pressed": "true"})
        swatch = template.new_tag("span", attrs={"class": f'route-swatch {meta.get("pattern", "solid")}', "style": f'color:{meta["color"]}'})
        button.append(swatch)
        button.append(route)
        info = template.new_tag("button", attrs={"class": "route-info", "data-route-info": route, "type": "button", "aria-label": f"Explain route {route}", "aria-expanded": "false", "aria-controls": "routeExplain"})
        info.string = "i"
        pair.append(button)
        pair.append(info)
        route_group.append(pair)
    for select_id in ("dateSelect", "mobileDate"):
        select = template.select_one(f"#{select_id}")
        select.clear()
        all_option = template.new_tag("option", value="all")
        all_option.string = "All dates"
        select.append(all_option)
        for item in data["dates"]:
            option = template.new_tag("option", value=item["key"])
            option.string = item["label"]
            select.append(option)
    region_group = template.select_one("[data-region]").parent
    for button in region_group.select("[data-region]"):
        button.decompose()
    mobile_region = template.select_one("#mobileRegion")
    mobile_region.clear()
    for index, (region, meta) in enumerate(data["region_cfg"].items()):
        button = template.new_tag("button", attrs={"class": "ctl active" if index == 0 else "ctl", "data-region": region, "data-i18n": region, "aria-pressed": "true" if index == 0 else "false"})
        button.string = meta["label"]
        region_group.append(button)
        option = template.new_tag("option", value=region)
        option.string = meta["label"]
        mobile_region.append(option)
    provider_group = template.select_one("[data-provider]").parent
    for button in provider_group.select("[data-provider]"):
        button.decompose()
    mobile_provider = template.select_one("#mobileProvider")
    mobile_provider.clear()
    for index, provider in enumerate(data["providers"]):
        label = "Smart map" if provider == "vector" else "Satellite + labels"
        button = template.new_tag("button", attrs={"class": "ctl active" if index == 0 else "ctl", "data-provider": provider, "data-i18n": provider})
        button.string = label
        provider_group.append(button)
        option = template.new_tag("option", value=provider)
        option.string = label
        mobile_provider.append(option)
    for tab in template.select(".tab"):
        tab["data-i18n"] = tab["data-tab"]
    overview = template.select_one("#routeOverview")
    overview.extract()
    overview["class"] = "route-overview"
    guide = template.new_tag("details", attrs={"class": "route-guide", "open": "open"})
    guide_summary = template.new_tag("summary", attrs={"data-i18n": "compare"})
    guide_summary.string = "Compare four strategies"
    guide.append(guide_summary)
    guide.append(overview)
    summary = template.new_tag("div", attrs={"id": "fieldSummary", "class": "field-summary"})
    summary.append(BeautifulSoup('<strong data-i18n="tripOverview"></strong><p id="fieldSummaryText"></p><p id="branchLegendText" class="branch-legend"></p>', "html.parser"))
    template.select_one(".sidebar").insert(0, summary)
    template.select_one(".sidebar").insert(1, guide)
    actions = template.new_tag("div", attrs={"class": "utility-actions"})
    for button_id, text in (("themeToggle", "☾ Dark"), ("langToggle", "EN"), ("panelToggle", "Hide panel")):
        button = template.new_tag("button", id=button_id, attrs={"class": "utility-button", "type": "button"})
        button.string = text
        actions.append(button)
    template.select_one(".provider-state").insert_before(actions)
    mapwrap = template.select_one(".mapwrap")
    for tag, ident, cls in (("div", "dateRibbon", "date-ribbon"), ("div", "mapFocus", "map-focus"), ("div", "mapSchedule", "map-schedule"), ("div", "routeTip", "route-tip")):
        mapwrap.append(template.new_tag(tag, id=ident, attrs={"class": cls}))
    badge = template.select_one(".map-badge")
    badge.clear()
    badge.append(BeautifulSoup('<b id="activeFilterSummary"></b><div id="mapRouteLegend" class="map-route-legend"></div><span data-i18n="conceptual"></span><span id="fallbackNote"></span><span id="freshnessNote"></span>', "html.parser"))
    loading = BeautifulSoup(
        '<div id="loadingScreen" role="status" aria-live="polite">'
        '<img id="loadingHero" class="loading-hero" src="assets/photos/medium/ggb__hero.webp" alt="Golden Gate Bridge">'
        '<div class="loading-shade"></div><div class="loading-card">'
        '<div class="loading-kicker">SMART MINORITY · FAMILY FIELD MAP</div>'
        '<div class="loading-title">여행 전체를<br>한눈에 연결합니다</div>'
        '<div class="loading-subtitle">Connecting every day, route, decision, and real photograph into one field-ready map.</div>'
        '<div class="loading-progress" aria-hidden="true"></div>'
        '<div id="loadingStatus" class="loading-status">로컬 스마트 지도와 실제 사진을 준비하는 중…</div>'
        f'<div class="loading-foot"><span>{place_count} VERIFIED PLACES</span><span>{photo_count} LOCAL PHOTOS</span><span>4 ROUTE STRATEGIES</span></div>'
        '</div></div>',
        "html.parser",
    )
    template.body.insert(0, loading)
    early_script = template.new_tag("script")
    early_script.string = "window.__tripLoadStarted=performance.now();try{document.documentElement.dataset.theme=localStorage.getItem('trip_theme')||'light'}catch{document.documentElement.dataset.theme='light'}"
    template.head.insert(0, early_script)
    for href in ("vendor/maplibre-gl.css", "src/map_first.css"):
        template.head.append(template.new_tag("link", rel="stylesheet", href=href))
    scripts = [script for script in template.find_all("script") if script is not early_script]
    if len(scripts) != 3:
        raise SystemExit(f"Unexpected template script layout: {len(scripts)} script tags")
    scripts[0].decompose()
    scripts[1].string = "window.TRIP_DATA=" + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";"
    for name, payload in (("TRIP_ROUTE_GEOMETRY", geometry), ("TRIP_I18N", translations), ("TRIP_FRESHNESS", freshness), ("TRIP_RUNTIME_CONTRACT", runtime_contract)):
        script = template.new_tag("script")
        script.string = f"window.{name}=" + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";"
        scripts[2].insert_before(script)
    for src in ("vendor/maplibre-gl.js", "vendor/trip-vector.js"):
        scripts[2].insert_before(template.new_tag("script", src=src))
    scripts[2].insert_before(template.new_tag("script", id="embeddedVector"))
    modular = str(template)
    (modular_dir / "index.html").write_text(modular)
    copy_runtime(modular_dir)

    standalone = BeautifulSoup(modular, "html.parser")
    for link in standalone.find_all("link", rel="stylesheet"):
        style = standalone.new_tag("style")
        style.string = (ROOT / link["href"]).read_text()
        link.replace_with(style)
    for script in standalone.find_all("script", src=True):
        inline = standalone.new_tag("script")
        inline.string = (ROOT / script["src"]).read_text()
        script.replace_with(inline)
    hillshade_path = ROOT / "assets/vector/yosemite_hillshade_shadow.webp"
    embed_hillshade = standalone.new_tag("script")
    embed_hillshade.string = "window.EMBEDDED_HILLSHADE=" + json.dumps("data:image/webp;base64," + base64.b64encode(hillshade_path.read_bytes()).decode("ascii")) + ";"
    standalone.find_all("script")[-1].insert_before(embed_hillshade)
    photos = {}
    for asset in photo_manifest["assets"]:
        for field in ("local_thumb_path", "local_medium_path"):
            path = asset[field]
            photos[path] = "data:image/webp;base64," + base64.b64encode((ROOT / path).read_bytes()).decode("ascii")
    embed_photos = standalone.new_tag("script")
    embed_photos.string = "window.EMBEDDED_PHOTOS=" + json.dumps(photos, separators=(",", ":")) + ";"
    standalone.find_all("script")[-1].insert_before(embed_photos)
    loading_path = ROOT / "assets/photos/medium/ggb__hero.webp"
    standalone.select_one("#loadingHero")["src"] = "data:image/webp;base64," + base64.b64encode(loading_path.read_bytes()).decode("ascii")
    map_assets = {}
    for path in sorted((ROOT / "assets/vector/fonts").rglob("*.pbf")) + sorted((ROOT / "assets/vector/sprites").glob("*")):
        map_assets[str(path.relative_to(ROOT))] = base64.b64encode(path.read_bytes()).decode("ascii")
    embed_assets = standalone.new_tag("script")
    embed_assets.string = "window.EMBEDDED_MAP_ASSETS=" + json.dumps(map_assets, separators=(",", ":")) + ";"
    standalone.find_all("script")[-1].insert_before(embed_assets)
    standalone_text = str(standalone)
    vector_base64 = base64.b64encode((ROOT / "assets/vector/sf_trip.pmtiles").read_bytes()).decode("ascii")
    standalone_text = standalone_text.replace('<script id="embeddedVector"></script>', '<script>window.EMBEDDED_VECTOR="' + vector_base64 + '";</script>')
    standalone_path = standalone_dir / "SF_Smart_Minority_Map_First_Standalone.html"
    standalone_path.write_text(standalone_text)

    manifest = {
        "schema_version": 1,
        "canonical_data": str(DATA_PATH.relative_to(ROOT)),
        "runtime_contract": str(RUNTIME_CONTRACT_PATH.relative_to(ROOT)),
        "counts": {"places": place_count, "photos": photo_count, "timeline_cards": len(data["timeline"]), "route_legs": len(data["legs"])},
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
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT), help="generated build directory; defaults to .build")
    args = parser.parse_args()
    requested = Path(args.output_dir)
    build(requested if requested.is_absolute() else ROOT / requested)


if __name__ == "__main__":
    main()
