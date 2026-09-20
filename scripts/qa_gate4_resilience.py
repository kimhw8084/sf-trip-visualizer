"""Gate 4 resilience, offline, asset, and delivery-parity evidence.

The canonical pipeline invokes this file in static mode during ``fast`` and
browser mode during ``qualify``.  Optional external Satellite success is
reported separately because it is not a prerequisite for Smart-map use.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "manifests" / "runtime_resilience_contract.json"
DATA_PATH = ROOT / "data" / "phase7_app_data.json"
FRESHNESS_PATH = ROOT / "manifests" / "trip_freshness.json"
PHOTO_MANIFEST_PATH = ROOT / "manifests" / "asset_manifest.json"
BASEMAP_MANIFEST_PATH = ROOT / "manifests" / "map_first_basemap_manifest.json"
PROVIDER_MANIFEST_PATH = ROOT / "manifests" / "basemap_provider_manifest.json"
BUILD = ROOT / ".build"
MODULAR = BUILD / "modular" / "index.html"
STANDALONE = BUILD / "standalone" / "SF_Smart_Minority_Map_First_Standalone.html"


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
    providers = {}
    for key, provider in data["providers"].items():
        providers[key] = {field: provider.get(field) for field in ("tile_template", "health_probe", "requires_api_key", "default_fallback")}
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
        "providers": providers,
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
    provider_manifest = load(PROVIDER_MANIFEST_PATH)
    failures: list[str] = []
    checks: dict[str, bool] = {}
    checks["contract_project"] = contract.get("project") == "sf-trip-visualizer"
    checks["contract_gate"] = contract.get("gate") == "production_readiness_gate_4"
    checks["canonical_authority"] = contract.get("authority", {}).get("canonical_data") == "data/phase7_app_data.json"
    checks["freshness_authority"] = contract.get("authority", {}).get("freshness") == "manifests/trip_freshness.json"
    checks["provider_manifest_authority"] = contract.get("authority", {}).get("provider_manifest") == "manifests/basemap_provider_manifest.json" and provider_manifest.get("user_selectable_provider_count") == 2 and all(key in provider_manifest for key in ("vector", "satellite"))
    checks["providers_exact"] = set(data["providers"]) == {"vector", "satellite"} and set(contract["providers"]) == {"vector", "satellite"}
    checks["smart_is_local_and_critical"] = contract["providers"]["vector"]["network_required"] is False and contract["providers"]["vector"]["critical"] is True
    checks["smart_has_no_fallback"] = "never substitute" in contract["providers"]["vector"]["failure_behavior"]
    checks["no_runtime_routing"] = contract["providers"]["vector"]["no_runtime_routing"] is True
    checks["no_runtime_remote_photos"] = contract["providers"]["vector"]["no_runtime_remote_photos"] is True

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
            row["local_photo_paths_present"] = all(item["local_thumb_path"] in html for item in photos["assets"] if item["role"] == "HERO") and "photoPath" in runtime_text and "assets/photos/" in runtime_text
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

    report = {"schema_version": 1, "status": "FAIL", "candidate_head": revision(), "test_mode": "browser", "modular": {}, "standalone": {}, "negative_checks": [], "external_provider": {"status": "VERIFY_REQUIRED", "reason": "not attempted"}, "failures": []}

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
        return str(value or "").startswith("MapLibre 4.7.1+sf-trip-visualizer-r6")

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
        if initial["provider"] != "vector" or not smart_identity(initial["provider_identity"]) or initial["local_assets"]["status"] != "ready":
            core_failures.append("smart identity/readiness")
        if remote_requests(requests):
            core_failures.append("remote Smart first-use request")
        page.locator('[data-mode="day"]').click()
        page.locator('#dateSelect').select_option("10/3")
        page.locator('[data-region="sf"]').click()
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
        page.evaluate("async()=>await window.__tripApp.chooseProvider('satellite')")
        page.wait_for_function("window.__tripApp.state.provider==='vector'", timeout=15000)
        blocked = snapshot(page)
        for _ in range(3):
            page.evaluate("async()=>await window.__tripApp.chooseProvider('satellite')")
            page.wait_for_function("window.__tripApp.state.provider==='vector'", timeout=15000)
        repeated = snapshot(page)
        if blocked["planning_state"] != stable_state or repeated["map"]["canvas_count"] != 1 or len(set(repeated["map"]["photo_marker_keys"])) != repeated["map"]["photo_markers"]:
            core_failures.append("blocked Satellite recovery/state")
        if repeated["runtime"]["providerStats"]["satellite"]["healthProbes"] > 4 or repeated["runtime"]["drawRequests"] > 18:
            core_failures.append("provider retry/request bound")
        page.unroute("https://**/*")
        report["modular"] = {"initial": initial, "before_reload": before_reload, "after_reload": after_reload, "blocked_provider": blocked, "repeated_switches": repeated, "smart_first_use_remote_requests": initial_remote_requests, "optional_provider_requests": [url for url in remote_requests(requests) if "arcgisonline.com" in url], "remote_requests": remote_requests(requests), "page_errors": errors, "critical_pass": not core_failures, "failures": core_failures}

        # Deterministic local-asset failure cases: no remote substitution is allowed.
        failure_routes = {
            "missing_pmtiles": "**/assets/vector/sf_trip.pmtiles",
            "corrupt_pmtiles": "**/assets/vector/sf_trip.pmtiles",
            "missing_required_photo": "**/assets/photos/thumb/ferry__hero.webp",
            "missing_terrain": "**/assets/vector/yosemite_hillshade_shadow.webp",
        }
        for label, pattern in failure_routes.items():
            failure_page = context.new_page()
            failure_page.set_default_timeout(15000)
            failure_requests: list[str] = []
            failure_page.on("request", lambda request: failure_requests.append(request.url))
            if label == "corrupt_pmtiles":
                failure_page.route(pattern, lambda route: route.fulfill(status=200, content_type="application/octet-stream", body="not a PMTiles archive"))
            else:
                failure_page.route(pattern, lambda route: route.abort())
            failure_page.goto(modular_url, wait_until="domcontentloaded", timeout=90000)
            failure_page.wait_for_timeout(4500)
            failure_snapshot = failure_page.evaluate("window.__tripApp?.runtimeSnapshot?.()")
            visible_failure = bool(failure_page.locator("#mapError:not([hidden])").count()) or bool(failure_page.locator("#loadingScreen.failed").count())
            row = {"case": label, "visible_failure": visible_failure, "provider": failure_snapshot.get("provider") if failure_snapshot else None, "provider_identity": failure_snapshot.get("provider_identity") if failure_snapshot else None, "remote_requests": remote_requests(failure_requests)}
            row["pass"] = visible_failure and row["provider"] == "vector" and smart_identity(row["provider_identity"]) and not row["remote_requests"]
            report["negative_checks"].append(row)
            failure_page.close()

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
        if standalone_page.locator(".photo-cluster").count():
            standalone_page.locator(".photo-cluster").first.click()
            standalone_page.wait_for_timeout(900)
        visible_key = standalone_page.evaluate("[...document.querySelectorAll('.photo-marker')].find(x=>x.style.display!=='none')?.dataset.placeKey||null")
        if visible_key:
            standalone_page.locator(f".photo-marker[data-place-key='{visible_key}']").click(force=True)
            standalone_page.wait_for_timeout(300)
        standalone_page.set_viewport_size({"width": 390, "height": 844})
        standalone_page.evaluate("()=>window.__tripApp.map().resize()")
        standalone_snapshot = snapshot(standalone_page)
        standalone_row = {"snapshot": standalone_snapshot, "remote_requests": remote_requests(standalone_requests), "page_errors": standalone_errors}
        standalone_row["critical_pass"] = standalone_snapshot["provider"] == "vector" and smart_identity(standalone_snapshot["provider_identity"]) and standalone_snapshot["local_assets"]["status"] == "ready" and not standalone_row["remote_requests"] and standalone_snapshot["map"]["canvas_count"] == 1
        report["standalone"] = standalone_row

        # Best-effort real-provider success probe. A network failure is explicit VERIFY_REQUIRED.
        provider_page = browser.new_page(viewport={"width": 1280, "height": 800})
        provider_requests: list[str] = []
        provider_page.on("request", lambda request: provider_requests.append(request.url))
        provider_page.goto(modular_url, wait_until="domcontentloaded", timeout=90000)
        wait_ready(provider_page)
        provider_success = bool(provider_page.evaluate("async()=>await window.__tripApp.chooseProvider('satellite')"))
        if provider_success and provider_page.evaluate("window.__tripApp.state.provider==='satellite'"):
            report["external_provider"] = {"status": "PASS", "provider": "satellite", "success_requests": len([url for url in provider_requests if "arcgisonline.com" in url]), "note": "optional success path independently observed in this environment"}
            provider_page.route("https://server.arcgisonline.com/**", lambda route: route.abort())
            provider_page.evaluate("()=>window.__tripApp.map().jumpTo({center:[-122.42,37.78],zoom:12})")
            try:
                provider_page.wait_for_function("window.__tripApp.state.provider==='vector'", timeout=15000)
                report["external_provider"]["post_switch_tile_failure_recovery"] = "PASS"
            except Exception:
                report["external_provider"]["post_switch_tile_failure_recovery"] = "VERIFY_REQUIRED"
        else:
            report["external_provider"] = {"status": "VERIFY_REQUIRED", "reason": "Satellite health/viewport success was not independently established; Smart qualification remains network-independent", "requests": len(provider_requests)}
        provider_page.close()
        standalone_context.close()
        context.close()
        browser.close()

    report["status"] = "PASS" if report["modular"].get("critical_pass") and report["standalone"].get("critical_pass") and all(row["pass"] for row in report["negative_checks"]) and not report["modular"].get("page_errors") and not report["standalone"].get("page_errors") else "FAIL"
    report["failures"] = report["modular"].get("failures", []) + [f"negative case: {row['case']}" for row in report["negative_checks"] if not row["pass"]]
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
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "candidate_head": report["candidate_head"], "mode": report["test_mode"], "failures": report.get("failures", [])}, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
