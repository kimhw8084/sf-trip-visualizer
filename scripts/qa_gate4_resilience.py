"""Gate 4 resilience, offline, asset, and delivery-parity evidence.

The canonical pipeline invokes this file in static mode during ``fast`` and
browser mode during ``qualify``.  Optional external Satellite success is
reported separately because it is not a prerequisite for Smart-map use.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

from PIL import Image
from trip_package import DEFAULT_PACKAGE, load_package


ROOT = Path(__file__).resolve().parents[1]
ACTIVE_PACKAGE = load_package(DEFAULT_PACKAGE)
PACKAGE_PATHS = {key: ROOT / value for key, value in ACTIVE_PACKAGE["projections"].items()}
CONTRACT_PATH = ROOT / "manifests" / "runtime_resilience_contract.json"
DATA_PATH = ROOT / ACTIVE_PACKAGE["canonical_data"]
FRESHNESS_PATH = PACKAGE_PATHS["freshness"]
PHOTO_MANIFEST_PATH = PACKAGE_PATHS["photos_manifest"]
BASEMAP_MANIFEST_PATH = ROOT / ACTIVE_PACKAGE["projections"]["map_manifest"]
BUILD = ROOT / ".build"
MODULAR = BUILD / "modular" / "index.html"
STANDALONE = BUILD / "standalone" / f"{ACTIVE_PACKAGE['slug']}-standalone.html"
RASTER_TILE_BODY = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")
RASTER_PROVIDER = next((key for key, value in ACTIVE_PACKAGE["providers"].items() if value.get("kind") == "raster"), None)
VECTOR_PROVIDER = ACTIVE_PACKAGE["vector_provider_id"]
ACTIVE_DATA = ACTIVE_PACKAGE["data"]
RASTER_POLICY = ACTIVE_PACKAGE["source_policy"]["external"].get(RASTER_PROVIDER, {}) if RASTER_PROVIDER else {}
RASTER_HOST = RASTER_POLICY.get("host", "")
VECTOR_IDENTITY = ACTIVE_PACKAGE["providers"][VECTOR_PROVIDER]["identity"]
FOCUS_DATE = next(
    date["key"] for date in ACTIVE_DATA["dates"]
    if any(item.get("date_key", item.get("date")) == date["key"] and item.get("spatial_keys") for item in ACTIVE_DATA["timeline"])
    and any(leg.get("date") == date["key"] and leg.get("mode") in {"drive", "walk"} for leg in ACTIVE_DATA["legs"])
)
FOCUS_REGION = next(
    region for region in ACTIVE_DATA["region_cfg"] if region != "overall"
    and any(ACTIVE_DATA["place_region"].get(marker["place_key"]) == region for marker in ACTIVE_DATA["markers"])
)


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def revision() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def truth_projection(data: dict) -> dict:
    """Project generated data back to the CHG-61/63-owned itinerary truth."""

    # Keep the projection explicit so generated annotations cannot become a
    # second source of truth.
    markers = []
    for marker in data["markers"]:
        markers.append({key: marker[key] for key in marker if key not in {"coordinate_role", "coordinate_provenance"}})
    return {
        "routes": data["routes"],
        "dates": data["dates"],
        "region_cfg": data["region_cfg"],
        "markers": markers,
        "place_region": data["place_region"],
        "timeline": data["timeline"],
        "legs": data["legs"],
        "endpoint_anchors": data["endpoint_anchors"],
        "replan_rules": data["replan_rules"],
    }


def stable_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def extract_script_json(html: str, name: str) -> dict:
    prefix = f"window.{name}="
    for script in re.findall(r"<script[^>]*>(.*?)</script>", html, flags=re.S):
        if script.startswith(prefix):
            return json.loads(script[len(prefix) :].rstrip(";"))
    raise ValueError(f"Embedded {name} is missing")


def inspect_image(path: Path) -> dict:
    with Image.open(path) as image:
        image.load()
        return {"format": image.format, "width": image.width, "height": image.height}


def static_report() -> dict:
    contract = load(CONTRACT_PATH)
    data = load(DATA_PATH)
    photos = load(PHOTO_MANIFEST_PATH)
    basemap = load(BASEMAP_MANIFEST_PATH)
    failures: list[str] = []
    checks: dict[str, bool] = {}
    checks["contract_project"] = contract.get("project") == "sf-trip-visualizer"
    checks["contract_gate"] = contract.get("gate") == "production_readiness_gate_4"
    pipeline_contract = load(ROOT / "manifests" / "canonical_pipeline.json")
    provider_classes = {"vector" if value.get("kind") == "vector" else "raster" for value in ACTIVE_PACKAGE["providers"].values()}
    checks["canonical_authority"] = contract.get("authority", {}).get("canonical_data") == "$active_trip_package.canonical_data" and ACTIVE_PACKAGE["descriptor_path"] == pipeline_contract.get("authority", {}).get("active_trip_package")
    checks["freshness_authority"] = contract.get("authority", {}).get("freshness") == "$active_trip_package.projections.freshness"
    checks["provider_configuration_authority"] = contract.get("authority", {}).get("provider_configuration") == "$active_trip_package.providers"
    checks["providers_exact"] = provider_classes == set(contract["providers"])
    checks["smart_is_local_and_critical"] = contract["providers"]["vector"]["network_required"] is False and contract["providers"]["vector"]["critical"] is True
    checks["smart_has_no_fallback"] = "never substitute" in contract["providers"]["vector"]["failure_behavior"]
    checks["no_runtime_routing"] = contract["providers"]["vector"]["no_runtime_routing"] is True
    checks["no_runtime_remote_photos"] = contract["providers"]["vector"]["no_runtime_remote_photos"] is True
    checks["optional_raster_failure_contract"] = contract["providers"]["raster"]["network_required"] is True and contract["providers"]["raster"]["critical"] is False and "local vector" in contract["providers"]["raster"]["failure_behavior"]

    for name, passed in checks.items():
        if not passed:
            failures.append(name)

    asset_checks = []
    for item in basemap["assets"]:
        path = ROOT / item["path"]
        row = {"path": item["path"], "expected_sha256": item["sha256"], "expected_bytes": item["bytes"], "exists": path.is_file()}
        if path.is_file():
            row["bytes"] = path.stat().st_size
            row["sha256"] = digest(path)
            row["hash_match"] = row["sha256"] == item["sha256"]
            row["bytes_match"] = row["bytes"] == item["bytes"]
            if path.suffix in {".png", ".webp"}:
                try:
                    row["decode"] = inspect_image(path)
                except Exception as error:
                    row["decode_error"] = str(error)
                    row["decode"] = False
            elif path.suffix == ".json":
                try:
                    json.loads(path.read_text())
                    row["decode"] = True
                except Exception as error:
                    row["decode_error"] = str(error)
                    row["decode"] = False
            else:
                row["decode"] = path.stat().st_size > 0
        else:
            row.update({"sha256": None, "bytes": None, "hash_match": False, "bytes_match": False, "decode": False})
        asset_checks.append(row)
        if not row["exists"] or not row["hash_match"] or not row["bytes_match"] or not row["decode"]:
            failures.append(f"local asset integrity: {item['path']}")

    photo_checks = []
    for item in photos["assets"]:
        row = {"place_key": item["place_key"], "role": item["role"], "variants": {}}
        for variant, path_key, hash_key in (("thumb", "local_thumb_path", "thumb_sha256"), ("medium", "local_medium_path", "medium_sha256")):
            path = ROOT / item[path_key]
            variant_row = {"path": item[path_key], "exists": path.is_file()}
            if path.is_file():
                variant_row["sha256"] = digest(path)
                variant_row["hash_match"] = variant_row["sha256"] == item[hash_key]
                try:
                    variant_row["decode"] = inspect_image(path)
                except Exception as error:
                    variant_row["decode"] = False
                    variant_row["decode_error"] = str(error)
            else:
                variant_row.update({"sha256": None, "hash_match": False, "decode": False})
            row["variants"][variant] = variant_row
            if not variant_row["exists"] or not variant_row["hash_match"] or not variant_row["decode"]:
                failures.append(f"local photo integrity: {item[path_key]}")
        photo_checks.append(row)

    build = {"present": BUILD.is_dir(), "modular": MODULAR.is_file(), "standalone": STANDALONE.is_file()}
    artifact_checks = []
    canonical_projection = truth_projection(data)
    for label, path in (("modular", MODULAR), ("standalone", STANDALONE)):
        row = {"path": str(path.relative_to(ROOT)), "present": path.is_file()}
        if path.is_file():
            html = path.read_text()
            embedded = extract_script_json(html, "TRIP_DATA")
            row["contract_embedded"] = extract_script_json(html, "TRIP_RUNTIME_CONTRACT") == contract
            row["truth_digest"] = digest_bytes(stable_json(truth_projection(embedded)).encode())
            row["canonical_truth"] = truth_projection(embedded) == canonical_projection
            row["freshness_embedded"] = extract_script_json(html, "TRIP_FRESHNESS") == load(FRESHNESS_PATH)
            row["bilingual_embedded"] = bool(extract_script_json(html, "TRIP_I18N").get("ko_to_en"))
            runtime_text = html + ((path.parent / "src/app_phase7.js").read_text() if label == "modular" else "")
            row["local_photo_paths_present"] = all(item["local_thumb_path"] in html for item in photos["assets"] if item["role"] == "HERO") and "photoPath" in runtime_text and ACTIVE_PACKAGE["assets"]["photos"]["root"] in html
            row["no_remote_photo_urls"] = not any(url in runtime_text for url in ("upload.wikimedia.org", "thumb.wikimedia.org", "commons.wikimedia.org"))
        else:
            row.update({"contract_embedded": False, "truth_digest": None, "canonical_truth": False, "freshness_embedded": False, "bilingual_embedded": False, "local_photo_paths_present": False, "no_remote_photo_urls": False})
        artifact_checks.append(row)
        if not all(row.get(key) for key in ("present", "contract_embedded", "canonical_truth", "freshness_embedded", "bilingual_embedded", "local_photo_paths_present", "no_remote_photo_urls")):
            failures.append(f"artifact integrity: {path.relative_to(ROOT)}")

    negative_contract = {
        "missing_pmtiles": "static hash/presence failure or visible smart_failure",
        "corrupt_pmtiles": "PMTiles header/decode failure or visible smart_failure",
        "missing_font_sprite_terrain": "static hash/presence failure or visible smart_failure",
        "missing_required_photo": "static hash/presence/decode failure or visible smart_failure",
        "remote_substitution": "forbidden; provider identity must remain smart-local-vector",
    }
    return {
        "schema_version": 1,
        "status": "PASS" if not failures else "FAIL",
        "candidate_head": revision(),
        "test_mode": "static",
        "contract": str(CONTRACT_PATH.relative_to(ROOT)),
        "checks": checks,
        "assets": {"basemap": asset_checks, "photos": photo_checks},
        "artifacts": {"build": build, "forms": artifact_checks},
        "negative_failure_contract": negative_contract,
        "failures": failures,
    }


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def browser_runtime_report(modular_url: str, standalone_path: Path) -> dict:
    from playwright.sync_api import sync_playwright

    report = {"schema_version": 1, "status": "FAIL", "candidate_head": revision(), "test_mode": "browser", "modular": {}, "standalone": {}, "negative_checks": [], "deterministic_provider": {"status": "FAIL", "reason": "not attempted"}, "external_provider": {"status": "VERIFY_REQUIRED", "reason": "not attempted"}, "failures": []}

    def wait_ready(page, standalone=False):
        page.wait_for_function("window.__tripApp?.map?.()", timeout=30000)
        page.wait_for_function("window.__tripApp.map().isStyleLoaded()", timeout=30000)
        page.wait_for_function("!document.getElementById('loadingScreen')", timeout=15000)
        page.wait_for_timeout(500)

    def snapshot(page):
        return page.evaluate("window.__tripApp.runtimeSnapshot()")

    def remote_requests(requests):
        return [url for url in requests if url.startswith(("http://", "https://")) and not re.match(r"https?://(127\.0\.0\.1|localhost)(:|/)", url)]

    def smart_identity(value):
        return value == VECTOR_IDENTITY

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, timeout=90000)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()
        page.set_default_timeout(30000)
        requests: list[str] = []
        errors: list[str] = []
        page.on("request", lambda request: requests.append(request.url))
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(modular_url, wait_until="domcontentloaded", timeout=90000)
        wait_ready(page)
        initial = snapshot(page)
        initial_remote_requests = remote_requests(requests)
        core_failures = []
        if initial["provider"] != VECTOR_PROVIDER or not smart_identity(initial["provider_identity"]) or initial["local_assets"]["status"] != "ready":
            core_failures.append("smart identity/readiness")
        if remote_requests(requests):
            core_failures.append("remote Smart first-use request")
        page.locator('#modeNav [data-mode="day"]').click()
        page.locator('#dateSelect').select_option(FOCUS_DATE)
        page.locator('#mapOptionsToggle').click()
        page.wait_for_function("!document.querySelector('#mapOptionsPanel')?.hidden")
        page.locator(f'[data-region="{FOCUS_REGION}"]').click()
        page.wait_for_timeout(400)
        if page.locator(".photo-marker").count():
            page.locator(".photo-marker").first.click()
            page.wait_for_selector("#peek.show")
            page.locator("#peek [data-peek-open]").evaluate("el=>el.click()")
            page.wait_for_function("document.querySelectorAll('#placeInspector .photo-grid img').length===3", timeout=15000)
            page.locator("[data-place-back]").click()
        page.locator('[data-sheet="compact"]').click()
        page.locator("#workbenchToggle").click()
        page.locator("#langToggle").click()
        page.locator("#themeToggle").click()
        page.evaluate("()=>{const m=window.__tripApp.map();for(let i=0;i<6;i++){m.panBy([13,-9],{duration:0});m.jumpTo({zoom:10+(i%3)})}m.resize()}")
        page.set_viewport_size({"width": 390, "height": 844})
        page.evaluate("()=>window.__tripApp.map().resize()")
        page.wait_for_timeout(350)
        before_reload = snapshot(page)
        page.reload(wait_until="domcontentloaded", timeout=90000)
        wait_ready(page)
        after_reload = snapshot(page)
        preserved = before_reload["planning_state"] == after_reload["planning_state"]
        modular_snapshot = snapshot(page)
        if not preserved:
            core_failures.append("reload planning state")
        if modular_snapshot["map"]["canvas_count"] != 1 or len(set(modular_snapshot["map"]["photo_marker_keys"])) != modular_snapshot["map"]["photo_markers"]:
            core_failures.append("modular runtime object leak")

        # Block only the optional provider after Smart is already usable.
        page.route("https://**/*", lambda route: route.abort())
        stable_state = snapshot(page)["planning_state"]
        page.evaluate("provider=>window.__tripApp.chooseProvider(provider)", RASTER_PROVIDER)
        page.wait_for_function("provider=>window.__tripApp.state.provider===provider", arg=VECTOR_PROVIDER, timeout=15000)
        blocked = snapshot(page)
        for _ in range(3):
            page.evaluate("provider=>window.__tripApp.chooseProvider(provider)", RASTER_PROVIDER)
            page.wait_for_function("provider=>window.__tripApp.state.provider===provider", arg=VECTOR_PROVIDER, timeout=15000)
        repeated = snapshot(page)
        if blocked["planning_state"] != stable_state or repeated["map"]["canvas_count"] != 1 or len(set(repeated["map"]["photo_marker_keys"])) != repeated["map"]["photo_markers"]:
            core_failures.append("blocked optional-provider recovery/state")
        if repeated["runtime"]["providerStats"][RASTER_PROVIDER]["healthProbes"] > 4 or repeated["runtime"]["drawRequests"] > 18:
            core_failures.append("provider retry/request bound")
        page.unroute("https://**/*")
        report["modular"] = {"initial": initial, "before_reload": before_reload, "after_reload": after_reload, "blocked_provider": blocked, "repeated_switches": repeated, "smart_first_use_remote_requests": initial_remote_requests, "optional_provider_requests": [url for url in remote_requests(requests) if RASTER_HOST in url], "remote_requests": remote_requests(requests), "page_errors": errors, "critical_pass": not core_failures, "failures": core_failures}

        # Deterministic local-asset failure cases: no remote substitution is allowed.
        photo_manifest = load(PHOTO_MANIFEST_PATH)
        hero_asset = next(item for item in photo_manifest["assets"] if item["role"].lower() == "hero")
        hero_photo = hero_asset["local_medium_path"]
        map_config = ACTIVE_PACKAGE["assets"]["map"]
        failure_routes = {
            "missing_pmtiles": f"**/{map_config['vector_archive']}",
            "corrupt_pmtiles": f"**/{map_config['vector_archive']}",
            "missing_required_photo": f"**/{hero_photo}",
        }
        if map_config.get("relief"):
            failure_routes["missing_terrain"] = f"**/{map_config['relief']['path']}"
        for label, pattern in failure_routes.items():
            failure_context = browser.new_context(viewport={"width": 1280, "height": 800})
            failure_page = failure_context.new_page()
            failure_page.set_default_timeout(15000)
            failure_requests: list[str] = []
            failure_page.on("request", lambda request: failure_requests.append(request.url))
            if label == "corrupt_pmtiles":
                failure_page.route(pattern, lambda route: route.fulfill(status=200, content_type="application/octet-stream", body="not a PMTiles archive"))
            else:
                failure_page.route(pattern, lambda route: route.abort())
            failure_page.goto(modular_url, wait_until="domcontentloaded", timeout=90000)
            if label == "missing_required_photo":
                failure_page.wait_for_function("window.__tripApp?.state?.runtime?.mapVisualReady === true", timeout=30000)
                failure_page.locator("#modeNav [data-mode='place']").click()
                failure_page.wait_for_function(
                    "key=>!!document.querySelector(`#placeView:not([hidden]) [data-place-choice='${CSS.escape(key)}']`)" ,
                    arg=hero_asset["place_key"], timeout=15000,
                )
                failure_page.locator(f"#placeView [data-place-choice='{hero_asset['place_key']}']").click()
                failure_page.evaluate("document.querySelectorAll('#placeInspector .photo-grid img').forEach(image=>image.loading='eager')")
            failure_page.wait_for_timeout(4500)
            failure_snapshot = failure_page.evaluate("window.__tripApp?.runtimeSnapshot?.()")
            visible_failure = bool(failure_page.locator("#mapError:not([hidden])").count()) or bool(failure_page.locator("#loadingScreen.failed").count())
            row = {"case": label, "visible_failure": visible_failure, "provider": failure_snapshot.get("provider") if failure_snapshot else None, "provider_identity": failure_snapshot.get("provider_identity") if failure_snapshot else None, "remote_requests": remote_requests(failure_requests)}
            row["pass"] = visible_failure and row["provider"] == VECTOR_PROVIDER and smart_identity(row["provider_identity"]) and not row["remote_requests"]
            report["negative_checks"].append(row)
            failure_context.close()

        standalone_context = browser.new_context(viewport={"width": 1280, "height": 800})
        standalone_page = standalone_context.new_page()
        standalone_page.set_default_timeout(30000)
        standalone_requests: list[str] = []
        standalone_errors: list[str] = []
        standalone_page.on("request", lambda request: standalone_requests.append(request.url))
        standalone_page.on("pageerror", lambda error: standalone_errors.append(str(error)))
        standalone_page.route("http**", lambda route: route.abort())
        standalone_page.goto(standalone_path.resolve().as_uri(), wait_until="domcontentloaded", timeout=90000)
        wait_ready(standalone_page, standalone=True)
        ferry_date = next(item.get("date_key", item.get("date")) for marker in ACTIVE_DATA["markers"] if marker.get("place_key") == "ferry" for item in marker.get("occurrences", []))
        ferry_region = ACTIVE_DATA["place_region"]["ferry"]
        standalone_page.locator('#modeNav [data-mode="day"]').click()
        standalone_page.locator("#dateSelect").select_option(ferry_date)
        standalone_page.locator("#mapOptionsToggle").click()
        standalone_page.wait_for_function("!document.querySelector('#mapOptionsPanel')?.hidden")
        standalone_page.locator(f'[data-region="{ferry_region}"]').click()
        standalone_page.set_viewport_size({"width": 320, "height": 800})
        standalone_page.evaluate("()=>window.__tripApp.map().resize()")
        standalone_page.evaluate("window.__tripApp.whenIdle()")
        standalone_page.wait_for_function("window.__tripApp?.map()?.loaded() && !window.__tripApp.map().isMoving()", timeout=10000)
        standalone_geometry = standalone_page.evaluate("window.__tripApp.mapGeometrySnapshot()")
        ferry = next((marker for marker in standalone_geometry.get("markers", []) if marker.get("key") == "ferry"), None)
        shell = standalone_geometry.get("shell", {})
        ferry_visible = bool(ferry and ferry["rect"]["left"] >= 0 and ferry["rect"]["top"] >= 0 and ferry["rect"]["right"] <= shell.get("width", 0) and ferry["rect"]["bottom"] <= shell.get("height", 0) and not ferry.get("intersects_obstacle") and "photo-marker" in (ferry.get("center_hit") or ""))
        ferry_pointer = standalone_page.evaluate("""()=>{const marker=document.querySelector('.photo-marker[data-place-key="ferry"]');if(!marker)return null;const r=marker.getBoundingClientRect(),s=document.querySelector('.map-shell').getBoundingClientRect();return{x:r.left+r.width/2,y:r.top+r.height/2,inside:r.left>=s.left&&r.top>=s.top&&r.right<=s.right&&r.bottom<=s.bottom};}""")
        ferry_pointer_activation = False
        if ferry_visible and ferry_pointer and ferry_pointer["inside"]:
            standalone_page.evaluate("window.__tripApp.hidePreview({returnFocus:false})")
            standalone_page.mouse.click(ferry_pointer["x"], ferry_pointer["y"])
            standalone_page.wait_for_timeout(200)
            ferry_pointer_activation = standalone_page.locator("#peek.show").count() > 0
        standalone_snapshot = snapshot(standalone_page)
        standalone_row = {"snapshot": standalone_snapshot, "mobile_map_geometry": standalone_geometry, "ferry_visible_inside_map": ferry_visible, "ferry_real_pointer_activation": ferry_pointer_activation, "remote_requests": remote_requests(standalone_requests), "page_errors": standalone_errors}
        standalone_row["critical_pass"] = standalone_snapshot["provider"] == VECTOR_PROVIDER and smart_identity(standalone_snapshot["provider_identity"]) and standalone_snapshot["local_assets"]["status"] == "ready" and not standalone_row["remote_requests"] and standalone_snapshot["map"]["canvas_count"] == 1 and ferry_visible and ferry_pointer_activation
        report["standalone"] = standalone_row

        # Deterministic provider recovery: establish a successful Satellite map with
        # fulfilled probe/viewport/raster responses, then fail only subsequent remote
        # raster requests on a new viewport. Live provider availability is not used.
        deterministic_page = browser.new_page(viewport={"width": 1440, "height": 900})
        deterministic_page.set_default_timeout(30000)
        deterministic = {"phase": "success", "requests": [], "success_requests": [], "failure_requests": []}
        deterministic_failures: list[str] = []

        def deterministic_route(route):
            url = route.request.url
            deterministic["requests"].append(url)
            if deterministic["phase"] == "success":
                deterministic["success_requests"].append(url)
                route.fulfill(status=200, content_type="image/png", body=RASTER_TILE_BODY)
            else:
                deterministic["failure_requests"].append(url)
                route.abort()

        deterministic_page.route(f"https://{RASTER_HOST}/**", deterministic_route)
        try:
            deterministic_page.goto(modular_url, wait_until="domcontentloaded", timeout=90000)
            wait_ready(deterministic_page)
            deterministic_page.locator('#modeNav [data-mode="day"]').click()
            # Oct 3 has no public place-to-place corridor because the day starts
            # and ends at private lodging and the afternoon Sausalito event is
            # represented without a photo-backed marker. Exercise spatial
            # recovery on Oct 4, which has visible public route legs.
            deterministic_page.locator("#dateSelect").select_option(FOCUS_DATE)
            deterministic_page.locator("#mapOptionsToggle").click()
            deterministic_page.wait_for_function("!document.querySelector('#mapOptionsPanel')?.hidden")
            deterministic_page.locator(f'[data-region="{FOCUS_REGION}"]').click()
            deterministic_page.locator('[data-sheet="full"]').click()
            deterministic_page.locator("#langToggle").click()
            deterministic_page.locator("#themeToggle").click()
            deterministic_page.wait_for_timeout(500)
            if deterministic_page.locator(".photo-marker").count():
                deterministic_page.locator(".photo-marker").first.click()
            deterministic_page.wait_for_timeout(300)
            stable_before_raster = snapshot(deterministic_page)
            pre_raster_smart_camera = stable_before_raster.get("smart_camera")
            if not pre_raster_smart_camera or not pre_raster_smart_camera.get("spatial", {}).get("useful"):
                deterministic_failures.append("useful Smart camera/spatial context was not recorded before raster activation")
            activated = bool(deterministic_page.evaluate("provider=>window.__tripApp.chooseProvider(provider)", RASTER_PROVIDER))
            deterministic_page.wait_for_function("provider=>window.__tripApp.state.provider===provider && window.__tripApp.state.runtime.mapVisualReady===true", arg=RASTER_PROVIDER, timeout=30000)
            raster_active = snapshot(deterministic_page)
            raster_success_requests = [url for url in deterministic["success_requests"] if RASTER_POLICY.get("path_prefix", "!") in url and "health=" not in url and "viewport=" not in url]
            if not activated or raster_active["provider"] != RASTER_PROVIDER or raster_active["provider_health"].get(RASTER_PROVIDER) != "ready" or not raster_success_requests:
                deterministic_failures.append("fulfilled optional-raster activation did not establish a ready map")

            deterministic["phase"] = "failure"
            deterministic_page.evaluate("()=>window.__tripApp.map().panTo([-118.2437,34.0522],{duration:0})")
            deterministic_page.wait_for_function("provider=>window.__tripApp.state.provider===provider && window.__tripApp.state.runtime.mapVisualReady===true", arg=VECTOR_PROVIDER, timeout=30000)
            deterministic_page.wait_for_timeout(900)
            recovered = snapshot(deterministic_page)
            fallback_events = [event for event in recovered["provider_events"] if event.get("type") == "fallback_to_smart" and event.get("provider") == RASTER_PROVIDER and event.get("reason") == "tile_error"]
            tile_events = [event for event in recovered["provider_events"] if event.get("type") == "tile_error" and event.get("provider") == RASTER_PROVIDER]
            stats = recovered["runtime"]["providerStats"][RASTER_PROVIDER]
            preserved = stable_before_raster["planning_state"] == recovered["planning_state"]
            activation_state_preserved = stable_before_raster["planning_state"] == raster_active["planning_state"]
            inherited_remote_spatial = deterministic_page.evaluate("""()=>{const app=window.__tripApp,map=app.map();map.jumpTo({center:[-118.2437,34.0522],zoom:13,bearing:0,pitch:0});return app.mapSpatialSnapshot();}""")
            restored_view = recovered.get("map", {}).get("camera")
            if restored_view:
                deterministic_page.evaluate("view=>window.__tripApp.map().jumpTo(view)", restored_view)
            deterministic_page.wait_for_timeout(250)
            recovered = snapshot(deterministic_page)
            recovered_spatial = recovered.get("map", {}).get("spatial") or {}
            prior_view = pre_raster_smart_camera or {}
            recovered_view = recovered.get("map", {}).get("camera") or {}
            camera_match = bool(prior_view and recovered_view and all(abs(float(recovered_view["center"][index]) - float(prior_view["center"][index])) < 0.0001 for index in (0, 1)) and abs(float(recovered_view["zoom"]) - float(prior_view["zoom"])) < 0.01)
            spatial_recovery = {
                "pre_raster_smart_camera": pre_raster_smart_camera,
                "recovered_smart_camera": recovered.get("smart_camera"),
                "recovered_map_camera": recovered_view,
                "camera_restored": camera_match,
                "inherited_remote_camera_negative_control": inherited_remote_spatial,
                "inherited_camera_was_spatially_empty": not inherited_remote_spatial.get("useful") and inherited_remote_spatial.get("markers_in_viewport", 0) == 0 and inherited_remote_spatial.get("route_features_in_viewport", 0) == 0,
                "recovered_spatial": recovered_spatial,
                "recovered_useful": bool(recovered_spatial.get("useful")),
                "recovered_markers_in_viewport": recovered_spatial.get("markers_in_viewport", 0),
                "recovered_routes_in_viewport": recovered_spatial.get("route_features_in_viewport", 0),
                "recovered_content_occupancy_ratio": recovered_spatial.get("content_occupancy_ratio", 0),
            }
            bounded = {
                "single_fallback": stats["fallbacks"] == 1 and len(fallback_events) == 1,
                "single_tile_error_episode": stats["tileErrors"] == 1 and len(tile_events) == 1,
                "one_recovery_draw": recovered["runtime"]["mapCreations"] - raster_active["runtime"]["mapCreations"] == 1,
                "single_canvas": recovered["map"]["canvas_count"] == 1,
                "unique_markers": len(set(recovered["map"]["photo_marker_keys"])) == recovered["map"]["photo_markers"],
                "bounded_failure_requests": len(deterministic["failure_requests"]) <= 48,
                "inherited_camera_negative_control": spatial_recovery["inherited_camera_was_spatially_empty"],
                "recovered_camera_or_safe_fit": spatial_recovery["camera_restored"] or (spatial_recovery["recovered_useful"] and spatial_recovery["recovered_markers_in_viewport"] > 0),
                "recovered_task_occupancy": spatial_recovery["recovered_useful"] and spatial_recovery["recovered_markers_in_viewport"] > 0 and spatial_recovery["recovered_routes_in_viewport"] > 0,
            }
            feedback_message = deterministic_page.locator("#mapError .map-error-message").inner_text() if deterministic_page.locator("#mapError:not([hidden])").count() else ""
            feedback_action = deterministic_page.locator("#smartRetry").inner_text() if deterministic_page.locator("#smartRetry").count() else ""
            feedback_visible = bool(feedback_message) and "Smart" in feedback_message
            raster_label = ACTIVE_PACKAGE["providers"][RASTER_PROVIDER].get("label_en", RASTER_PROVIDER)
            feedback_truthful = feedback_visible and "failed" not in feedback_message.lower() and raster_label in feedback_action
            feedback_dismissible = bool(deterministic_page.locator("#mapErrorDismiss").count()) and deterministic_page.locator("#mapErrorDismiss").is_visible()
            screenshot_path = ROOT / "QA" / "CHG-232" / "screenshots" / "optional_raster_failure_recovery_1440x900.png"
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            deterministic_page.screenshot(path=str(screenshot_path))
            retry_before = recovered["runtime"]["providerStats"][RASTER_PROVIDER]["healthProbes"]
            deterministic["phase"] = "success"
            retry_result = bool(deterministic_page.evaluate("provider=>window.__tripApp.chooseProvider(provider)", RASTER_PROVIDER))
            deterministic_page.wait_for_function("provider=>window.__tripApp.state.provider===provider && window.__tripApp.state.runtime.mapVisualReady===true", arg=RASTER_PROVIDER, timeout=30000)
            retry_snapshot = snapshot(deterministic_page)
            retry_allowed = retry_result and retry_snapshot["runtime"]["providerStats"][RASTER_PROVIDER]["healthProbes"] > retry_before
            deterministic_page.evaluate("async provider=>await window.__tripApp.chooseProvider(provider)", VECTOR_PROVIDER)
            deterministic_page.wait_for_function("provider=>window.__tripApp.state.provider===provider && window.__tripApp.state.runtime.mapVisualReady===true", arg=VECTOR_PROVIDER, timeout=30000)
            if not activation_state_preserved:
                deterministic_failures.append("Satellite activation changed planning/presentation state")
            if not preserved:
                deterministic_failures.append("Satellite tile failure did not preserve planning/presentation state")
            if not all(bounded.values()):
                deterministic_failures.extend([f"bounded recovery assertion failed: {name}" for name, passed in bounded.items() if not passed])
            if recovered["provider"] != VECTOR_PROVIDER or not smart_identity(recovered["provider_identity"]):
                deterministic_failures.append("recovery did not return to the local Smart provider")
            if recovered["provider_health"].get(RASTER_PROVIDER) != "failed":
                deterministic_failures.append("Optional raster health was not marked failed")
            if not recovered["map_visual_ready"]:
                deterministic_failures.append("Smart map_visual_ready did not recover")
            if not feedback_visible:
                deterministic_failures.append("Satellite recovery feedback was not visible")
            if not feedback_truthful:
                deterministic_failures.append("Optional raster recovery feedback did not truthfully describe local map recovery")
            if not feedback_dismissible:
                deterministic_failures.append("Satellite recovery feedback was not visibly dismissible")
            if not retry_allowed:
                deterministic_failures.append("explicit later optional-raster probe was not allowed")
            deterministic_row = {
                "status": "PASS" if not deterministic_failures and recovered["provider"] == VECTOR_PROVIDER and smart_identity(recovered["provider_identity"]) and recovered["provider_health"].get(RASTER_PROVIDER) == "failed" and recovered["map_visual_ready"] and preserved and feedback_visible and all(bounded.values()) and retry_allowed else "FAIL",
                "mode": "deterministic_fulfilled_then_failed_remote_raster",
                "activation": {"result": activated, "provider": raster_active["provider"], "provider_health": raster_active["provider_health"], "success_requests": len(deterministic["success_requests"]), "raster_success_requests": len(raster_success_requests), "snapshot": raster_active},
                "recovery": {"provider": recovered["provider"], "provider_identity": recovered["provider_identity"], "provider_health": recovered["provider_health"], "raster_stats": stats, "tile_error_events": tile_events, "fallback_events": fallback_events, "activation_state_preserved": activation_state_preserved, "planning_state_preserved": preserved, "feedback_visible": feedback_visible, "feedback_truthful": feedback_truthful, "feedback_dismissible": feedback_dismissible, "map_visual_ready": recovered["map_visual_ready"], "spatial_recovery": spatial_recovery, "snapshot": recovered},
                "retry_allowed": retry_allowed,
                "bounded": bounded,
                "failure_requests": len(deterministic["failure_requests"]),
                "screenshot": str(screenshot_path.relative_to(ROOT)),
                "screenshot_sha256": digest(screenshot_path),
                "failures": deterministic_failures,
            }
        except Exception as error:
            deterministic_failures.append(f"deterministic optional-raster recovery: {type(error).__name__}: {error}")
            deterministic_row = {"status": "FAIL", "mode": "deterministic_fulfilled_then_failed_remote_raster", "failure_requests": len(deterministic["failure_requests"]), "failures": deterministic_failures}
        finally:
            deterministic_page.close()
        report["deterministic_provider"] = deterministic_row

        # Best-effort real-provider success probe. A network failure is explicit VERIFY_REQUIRED.
        provider_page = browser.new_page(viewport={"width": 1280, "height": 800})
        provider_requests: list[str] = []
        provider_page.on("request", lambda request: provider_requests.append(request.url))
        provider_page.goto(modular_url, wait_until="domcontentloaded", timeout=90000)
        wait_ready(provider_page)
        provider_success = bool(provider_page.evaluate("provider=>window.__tripApp.chooseProvider(provider)", RASTER_PROVIDER)) if RASTER_PROVIDER else False
        if provider_success and provider_page.evaluate("provider=>window.__tripApp.state.provider===provider", RASTER_PROVIDER):
            report["external_provider"] = {"status": "PASS", "provider": RASTER_PROVIDER, "success_requests": len([url for url in provider_requests if RASTER_HOST in url]), "note": "optional provider success path independently observed in this environment"}
            provider_page.route(f"https://{RASTER_HOST}/**", lambda route: route.abort())
            provider_page.evaluate("()=>window.__tripApp.map().jumpTo({center:[-122.42,37.78],zoom:12})")
            try:
                provider_page.wait_for_function("provider=>window.__tripApp.state.provider===provider", arg=VECTOR_PROVIDER, timeout=15000)
                report["external_provider"]["post_switch_tile_failure_recovery"] = "PASS"
            except Exception:
                report["external_provider"]["post_switch_tile_failure_recovery"] = "VERIFY_REQUIRED"
        else:
            report["external_provider"] = {"status": "VERIFY_REQUIRED", "reason": "Optional raster health/viewport success was not independently established; local vector qualification remains network-independent", "provider": RASTER_PROVIDER, "requests": len(provider_requests)}
        provider_page.close()
        standalone_context.close()
        context.close()
        browser.close()

    report["status"] = "PASS" if report["modular"].get("critical_pass") and report["standalone"].get("critical_pass") and report["deterministic_provider"].get("status") == "PASS" and all(row["pass"] for row in report["negative_checks"]) and not report["modular"].get("page_errors") and not report["standalone"].get("page_errors") else "FAIL"
    report["failures"] = report["modular"].get("failures", []) + report["deterministic_provider"].get("failures", []) + [f"negative case: {row['case']}" for row in report["negative_checks"] if not row["pass"]]
    return report


def delivery_report(public_dir: Path | None = None) -> dict:
    data = load(DATA_PATH)
    contract = load(CONTRACT_PATH)
    canonical = truth_projection(data)
    rows = []
    for label, path in (("modular", MODULAR), ("standalone", STANDALONE)):
        html = path.read_text() if path.is_file() else ""
        embedded = extract_script_json(html, "TRIP_DATA") if html else {}
        rows.append({"form": label, "path": str(path.relative_to(ROOT)), "sha256": digest(path) if path.is_file() else None, "truth_digest": digest_bytes(stable_json(truth_projection(embedded)).encode()) if embedded else None, "truth_matches": bool(embedded) and truth_projection(embedded) == canonical, "freshness_matches": bool(embedded) and extract_script_json(html, "TRIP_FRESHNESS") == load(FRESHNESS_PATH), "contract_matches": bool(embedded) and extract_script_json(html, "TRIP_RUNTIME_CONTRACT") == contract})
    if public_dir:
        public_index = public_dir / "index.html"
        html = public_index.read_text() if public_index.is_file() else ""
        embedded = extract_script_json(html, "TRIP_DATA") if html else {}
        rows.append({"form": "public_staging", "path": str(public_index.relative_to(ROOT)) if public_index.is_relative_to(ROOT) else str(public_index), "sha256": digest(public_index) if public_index.is_file() else None, "exact_modular": public_index.is_file() and MODULAR.is_file() and public_index.read_bytes() == MODULAR.read_bytes(), "truth_digest": digest_bytes(stable_json(truth_projection(embedded)).encode()) if embedded else None, "truth_matches": bool(embedded) and truth_projection(embedded) == canonical, "freshness_matches": bool(embedded) and extract_script_json(html, "TRIP_FRESHNESS") == load(FRESHNESS_PATH), "contract_matches": bool(embedded) and extract_script_json(html, "TRIP_RUNTIME_CONTRACT") == contract})
    failures = []
    if not all(row.get("truth_matches") and row.get("freshness_matches") and row.get("contract_matches") for row in rows):
        failures.append("truth/freshness/contract parity")
    if public_dir and not rows[-1].get("exact_modular"):
        failures.append("public is not an exact modular copy")
    return {"schema_version": 1, "status": "PASS" if not failures else "FAIL", "candidate_head": revision(), "test_mode": "delivery_parity", "forms": rows, "failures": failures}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("static", "browser", "parity"), required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--public-dir")
    args = parser.parse_args()
    if args.mode == "static":
        report = static_report()
    elif args.mode == "browser":
        report = browser_runtime_report(os.environ.get("TRIP_QA_URL", "http://127.0.0.1:8766/index.html"), Path(os.environ.get("TRIP_STANDALONE_PATH", str(STANDALONE))))
    else:
        report = delivery_report(Path(args.public_dir) if args.public_dir else None)
    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "candidate_head": report["candidate_head"], "mode": report["test_mode"], "failures": report.get("failures", [])}, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
