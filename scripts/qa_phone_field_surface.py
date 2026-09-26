#!/usr/bin/env python3
"""Exact-candidate field-surface screenshots and mobile execution oracles."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import threading
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

from build_map_first import build
from qa_evidence import ROOT, candidate_identity
from serve_map import RangeHandler
from trip_package import DEFAULT_PACKAGE, load_package


FIXTURE_PACKAGE = "packages/portability-fixture/trip.json"
OUT = ROOT / "QA" / "CHG-232" / "phone_field_surface.json"
SCREENSHOTS = ROOT / "QA" / "CHG-232" / "screenshots" / "field_surface"
FIXTURE_BUILD = ROOT / ".build" / "portability-fixture"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class QuietRangeHandler(RangeHandler):
    def log_message(self, _format, *_args):
        pass


def serve(directory: Path) -> tuple[ThreadingHTTPServer, threading.Thread, str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietRangeHandler, directory=str(directory)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, f"http://127.0.0.1:{server.server_port}/index.html"


def screenshot(page, filename: str, viewport: tuple[int, int], screenshots: list[dict], state: str) -> None:
    path = SCREENSHOTS / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(path), full_page=False, animations="disabled")
    screenshots.append({
        "path": str(path.relative_to(ROOT)), "sha256": sha256(path),
        "viewport": f"{viewport[0]}x{viewport[1]}", "state": state,
        "lang": page.evaluate("document.documentElement.lang"),
        "theme": page.evaluate("document.documentElement.dataset.theme"),
    })


def inspect_page(page, package: dict, *, mobile: bool) -> dict:
    return page.evaluate("""({mobile}) => {
      const app=window.__tripApp, snap=app.runtimeSnapshot(), day=document.querySelector('#dayView:not([hidden])');
      const next=day?.querySelector('#dayPlan > :first-child'), rect=next?.getBoundingClientRect();
      const nextVisiblePx=rect?Math.max(0,Math.min(innerHeight,rect.bottom)-Math.max(0,rect.top)):0;
      return {title:document.title, package:window.TRIP_PACKAGE.trip_identity, mode:app.state.presentation.mode,
        date:app.state.task.date, route:app.state.task.primaryRoute, region:app.state.task.region,
        mobile_first_use_day:!mobile || app.state.presentation.mode==='day',
        horizontal_overflow:document.documentElement.scrollWidth>innerWidth+1,
        map_canvas_count:snap.map.canvas_count, map_ready:snap.map_visual_ready,
        map_markers:snap.map.photo_markers+snap.map.clusters, route_features:snap.map.spatial?.route_features||0,
        day_items:day?.querySelectorAll('.day-item,.plan-card').length||0,
        first_day_text:day?.querySelector('.day-item-title,.travel-compact-title')?.textContent||'',
        next_item_visible_px:nextVisiblePx,
        next_item_text:next?.textContent?.trim().replace(/\\s+/g,' ')||'',
        fixture_notice:!document.querySelector('#fixtureNotice')?.hidden,
        local_assets:snap.local_assets.status, provider:snap.provider,
        visible_view:day?.getBoundingClientRect().toJSON()||null};
    }""", {"mobile": mobile})


def run(expected_revision: str | None = None, output: Path = OUT) -> dict:
    identity = candidate_identity(expected_revision)
    if expected_revision and identity["sha"] != expected_revision:
        raise RuntimeError(f"Screenshot candidate mismatch: expected {expected_revision}, found {identity['sha']}")
    output = output if output.is_absolute() else ROOT / output
    active = load_package(DEFAULT_PACKAGE)
    fixture = load_package(FIXTURE_PACKAGE)
    route_day = next(
        day["key"] for day in active["data"]["dates"]
        if any(leg.get("date") == day["key"] and leg.get("mode") in {"drive", "walk"} for leg in active["data"]["legs"])
    )
    active_vector_provider = active["vector_provider_id"]
    fixture_vector_provider = fixture["vector_provider_id"]
    active_standalone = ROOT / ".build" / "standalone" / f"{active['slug']}-standalone.html"
    active_modular = ROOT / ".build" / "modular" / "index.html"
    if not active_modular.is_file() or not active_standalone.is_file():
        raise RuntimeError("Build the active package before capturing the field surface")
    fixture_manifest = build(FIXTURE_BUILD, fixture["descriptor_path"])
    fixture_modular = FIXTURE_BUILD / "modular" / "index.html"
    sf_server, sf_thread, sf_url = serve(active_modular.parent)
    fixture_server, fixture_thread, fixture_url = serve(fixture_modular.parent)
    SCREENSHOTS.mkdir(parents=True, exist_ok=True)
    screenshots: list[dict] = []
    errors: dict[str, list[str]] = {}
    surfaces: dict[str, dict] = {}
    filters: dict[str, dict] = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)

        def open_surface(name: str, url: str, viewport: tuple[int, int], *, mobile: bool = True):
            context = browser.new_context(viewport={"width": viewport[0], "height": viewport[1]}, device_scale_factor=2, is_mobile=mobile, has_touch=mobile)
            page = context.new_page()
            errors[name] = []
            page.on("pageerror", lambda error: errors[name].append(str(error)))
            page.goto(url, wait_until="domcontentloaded", timeout=90000)
            page.wait_for_function("window.__tripApp?.state?.runtime?.mapVisualReady===true", timeout=90000)
            page.wait_for_timeout(250)
            return context, page

        context, page = open_surface("sf_390", sf_url, (390, 844))
        sf390 = inspect_page(page, active, mobile=True)
        screenshot(page, "sf-mobile-390x844-ko-light.png", (390, 844), screenshots, "first-use Day view, active package")
        page.locator("#dateSelect").select_option(route_day)
        page.wait_for_function("()=>window.__tripApp.state.runtime.mapVisualReady && window.__tripApp.mapSpatialSnapshot().route_features_in_viewport>0")
        sf_route_390 = inspect_page(page, active, mobile=True)
        screenshot(page, "sf-mobile-route-day-390x844-ko-light.png", (390, 844), screenshots, "selected SF day with local route geometry and day plan")
        place_day = active["data"]["dates"][1]["key"]
        page.locator("#dateSelect").select_option(place_day)
        page.locator("#modeNav [data-mode='place']").click()
        page.wait_for_function("document.querySelectorAll('#placeView [data-place-choice]').length>0", timeout=15000)
        page.locator("#placeView [data-place-choice]").first.click()
        page.evaluate("document.querySelectorAll('#placeInspector .photo-grid img').forEach(image=>image.loading='eager')")
        page.wait_for_function("()=>{const images=[...document.querySelectorAll('#placeInspector .photo-grid img')];return images.length===3&&images.every(image=>image.complete&&image.naturalWidth>0)}", timeout=20000)
        place_context = page.evaluate("""()=>({
          place:document.querySelector('#placeInspector .place-title-row h3')?.textContent||'',
          photos:[...document.querySelectorAll('#placeInspector .photo-grid img')].map(image=>({src:image.getAttribute('src'),complete:image.complete&&image.naturalWidth>0})),
          freshness_facts:document.querySelectorAll('#placeInspector .place-freshness').length,
          decision_rules:document.querySelectorAll('#placeInspector .decision-rule').length,
          directions_handoff:!!document.querySelector('#placeInspector .directions a')
        })""")
        screenshot(page, "sf-mobile-place-photos-390x844-ko-light.png", (390, 844), screenshots, "selected SF place with local photos and field context")
        page.locator("#langToggle").click()
        page.locator("#themeToggle").click()
        page.wait_for_timeout(120)
        context.close()

        context, page = open_surface("sf_320", sf_url, (320, 800))
        page.locator("#langToggle").click()
        page.locator("#themeToggle").click()
        page.wait_for_timeout(120)
        sf320 = inspect_page(page, active, mobile=True)
        screenshot(page, "sf-mobile-320x800-en-dark.png", (320, 800), screenshots, "first-use Day view, English dark theme")
        page.locator("#dateSelect").select_option(route_day)
        page.wait_for_function("()=>window.__tripApp.state.runtime.mapVisualReady && window.__tripApp.mapSpatialSnapshot().route_features_in_viewport>0")
        sf_route_320 = inspect_page(page, active, mobile=True)
        screenshot(page, "sf-mobile-route-day-320x800-en-dark.png", (320, 800), screenshots, "selected SF day with local route geometry, English dark theme")
        context.close()

        context, page = open_surface("sf_desktop", sf_url, (1440, 900), mobile=False)
        page.locator("#modeNav [data-mode='day']").click()
        page.locator("#dateSelect").select_option(route_day)
        page.wait_for_function("()=>window.__tripApp.state.runtime.mapVisualReady && window.__tripApp.mapSpatialSnapshot().route_features_in_viewport>0")
        page.wait_for_timeout(120)
        desktop = inspect_page(page, active, mobile=False)
        screenshot(page, "sf-desktop-1440x900-ko-light.png", (1440, 900), screenshots, "selected day with map and route context")
        context.close()

        context, page = open_surface("sf_raster_failure", sf_url, (390, 844))
        raster_id = next(key for key, value in active["providers"].items() if value.get("kind") == "raster")
        raster_host = active["source_policy"]["external"][raster_id]["host"]
        page.route(f"https://{raster_host}/**", lambda route: route.abort())
        page.evaluate("provider=>window.__tripApp.chooseProvider(provider)", raster_id)
        page.wait_for_function("provider=>window.__tripApp.state.provider===provider && !document.querySelector('#mapError').hidden", arg=active_vector_provider, timeout=15000)
        recovery = inspect_page(page, active, mobile=True)
        screenshot(page, "sf-mobile-raster-failure-smart-recovery-390x844.png", (390, 844), screenshots, "optional raster failure returns to local Smart")
        context.close()

        context, page = open_surface("fixture", fixture_url, (390, 844))
        page.locator("#langToggle").click()
        page.wait_for_timeout(120)
        fixture_surface = inspect_page(page, fixture, mobile=True)
        screenshot(page, "fixture-mobile-primary-390x844-en.png", (390, 844), screenshots, "non-shipping fixture first-use Day view")
        route = sorted(fixture["data"]["routes"])[-1]
        region = sorted(key for key in fixture["data"]["region_cfg"] if key != "overall")[-1]
        date = fixture["data"]["dates"][-1]["key"]
        page.locator("#modeNav [data-mode='decide']").click()
        page.locator(f"[data-route='{route}']").click()
        page.locator("#modeNav [data-mode='day']").click()
        page.locator("#dateSelect").select_option(date)
        page.locator("#mapOptionsToggle").click()
        page.locator(f"[data-region='{region}']").click()
        page.wait_for_function("({route,date,region})=>{const s=window.__tripApp.state.task;return s.primaryRoute===route&&s.date===date&&s.region===region}", arg={"route": route, "date": date, "region": region})
        filtered = inspect_page(page, fixture, mobile=True)
        page.locator("#modeNav [data-mode='place']").click()
        page.wait_for_function("document.querySelectorAll('#placeView:not([hidden]) [data-place-choice]').length>0")
        page.locator("#placeView [data-place-choice]").first.click()
        page.wait_for_function("document.querySelectorAll('#placeInspector .photo-grid img').length===3")
        page.evaluate("document.querySelectorAll('#placeInspector .photo-grid img').forEach(image=>image.loading='eager')")
        page.wait_for_function("()=>{const images=[...document.querySelectorAll('#placeInspector .photo-grid img')];return images.length===3&&images.every(image=>image.complete&&image.naturalWidth>0)}", timeout=20000)
        place_photos = page.locator("#placeInspector .photo-grid img").evaluate_all("images=>images.map(img=>({src:img.getAttribute('src'),complete:img.complete&&img.naturalWidth>0}))")
        fixture_links = page.evaluate("""()=>({
          directions:document.querySelector('#placeInspector .directions a')?.href||'',
          official:window.TRIP_FRESHNESS.records.flatMap(fact=>fact.source?.source_urls||[]).map(url=>window.__tripSecurity.safeOfficialSourceUrl(url)).filter(Boolean),
          blocked_arbitrary:!window.__tripSecurity.safeOfficialSourceUrl('https://outside.juniper.test/conditions'),
          blocked_explicit_default_port:!window.__tripSecurity.safeOfficialSourceUrl('https://agency.juniper.test:443/conditions')
        })""")
        direction_policy = fixture["source_policy"]["external"]["directions"]
        direction_url = urlparse(fixture_links["directions"])
        allowed_official_hosts = set(fixture["source_policy"]["official_sources"]["hosts"])
        source_policy_proof = {
            "directions_host": direction_url.hostname,
            "directions_path_allowed": direction_url.path in direction_policy["paths"],
            "official_hosts": sorted({urlparse(url).hostname for url in fixture_links["official"]}),
            "blocked_arbitrary_host": fixture_links["blocked_arbitrary"],
            "blocked_explicit_port": fixture_links["blocked_explicit_default_port"],
        }
        source_policy_proof["pass"] = (
            direction_url.scheme == direction_policy["scheme"] and direction_url.hostname == direction_policy["host"]
            and direction_url.path in direction_policy["paths"]
            and bool(source_policy_proof["official_hosts"])
            and source_policy_proof["blocked_arbitrary_host"] and source_policy_proof["blocked_explicit_port"]
            and set(source_policy_proof["official_hosts"]) <= allowed_official_hosts
        )
        filters["fixture"] = {
            "selected_route": filtered["route"], "selected_date": filtered["date"], "selected_region": filtered["region"],
            "visible_day_items": filtered["day_items"], "place_photo_assets": place_photos,
            "source_policy": source_policy_proof,
            "pass": filtered["route"] == route and filtered["date"] == date and filtered["region"] == region and filtered["day_items"] > 0 and len(place_photos) == 3 and all(item["complete"] for item in place_photos) and source_policy_proof["pass"],
        }
        fixture_raster = next(key for key, value in fixture["providers"].items() if value.get("kind") == "raster")
        fixture_raster_host = fixture["source_policy"]["external"][fixture_raster]["host"]
        page.route(f"https://{fixture_raster_host}/**", lambda route: route.abort())
        page.evaluate("provider=>window.__tripApp.chooseProvider(provider)", fixture_raster)
        page.wait_for_function("provider=>window.__tripApp.state.provider===provider&&!document.querySelector('#mapError').hidden", arg=fixture_vector_provider, timeout=15000)
        fixture_raster_recovery = page.evaluate("()=>({provider:window.__tripApp.state.provider,map_ready:window.__tripApp.state.runtime.mapVisualReady,local_assets:window.__tripApp.state.runtime.localAssets.status,error:!document.querySelector('#mapError').hidden})")
        context.close()
        browser.close()
    sf_ok = all(not row["horizontal_overflow"] and row["mobile_first_use_day"] and row["map_canvas_count"] == 1 and row["next_item_visible_px"] >= 48 for row in (sf390, sf320))
    route_surface_ok = all(
        row["date"] == route_day and row["route_features"] > 0 and row["map_markers"] > 0
        and not row["horizontal_overflow"] and row["next_item_visible_px"] >= 48
        for row in (sf_route_390, sf_route_320)
    )
    fixture_provider_ok = fixture_raster_recovery["provider"] == fixture_vector_provider and fixture_raster_recovery["map_ready"] and fixture_raster_recovery["local_assets"] == "ready" and fixture_raster_recovery["error"]
    fixture_ok = fixture_surface["mobile_first_use_day"] and fixture_surface["fixture_notice"] and fixture_surface["map_canvas_count"] == 1 and fixture_surface["next_item_visible_px"] >= 48 and filters["fixture"]["pass"] and fixture_provider_ok
    place_ok = len(place_context["photos"]) == 3 and all(photo["complete"] for photo in place_context["photos"])
    recovery_ok = recovery["provider"] == active_vector_provider and recovery["map_ready"] and recovery["mobile_first_use_day"] and not recovery["horizontal_overflow"]
    page_errors = {name: messages for name, messages in errors.items() if messages}
    if page_errors:
        raise RuntimeError("Field surface browser errors: " + json.dumps(page_errors, ensure_ascii=False))
    if not (sf_ok and route_surface_ok and fixture_ok and place_ok and recovery_ok and not desktop["horizontal_overflow"]):
        raise RuntimeError("Field surface oracle failed: " + json.dumps({"sf390": sf390, "sf320": sf320, "sf_route_390": sf_route_390, "sf_route_320": sf_route_320, "place": place_context, "fixture": fixture_surface, "filters": filters, "recovery": recovery}, ensure_ascii=False))
    report = {
        "schema_version": 1, "status": "PASS", "candidate_head": identity["sha"], "candidate_tree": identity["tree"],
        "active_package": active["trip_identity"], "fixture_package": fixture["trip_identity"],
        "fixture_build": {"path": str(FIXTURE_BUILD.relative_to(ROOT)), "manifest_sha256": sha256(FIXTURE_BUILD / "build_manifest.json"), "artifact": fixture_manifest["standalone"]["path"]},
        "screenshots": screenshots,
        "surfaces": {"sf_390x844": sf390, "sf_320x800": sf320, "sf_route_390x844": sf_route_390, "sf_route_320x800": sf_route_320, "sf_place_390x844": place_context, "sf_desktop_1440x900": desktop, "fixture_390x844": fixture_surface, "provider_failure_recovery": recovery},
        "fixture_filter_and_photo_proof": filters,
        "fixture_provider_failure_recovery": fixture_raster_recovery,
        "checks": {"sf_phone_first_use": sf_ok, "sf_mobile_route_context": route_surface_ok, "sf_place_photos_local": place_ok, "fixture_same_renderer_build_and_run": fixture_ok, "fixture_route_date_region_filters": filters["fixture"]["pass"], "fixture_provider_policy_and_recovery": fixture_provider_ok, "provider_failure_recovers_to_local_map": recovery_ok, "desktop_no_overflow": not desktop["horizontal_overflow"], "browser_errors": not page_errors},
        "verification_boundaries": {"chromium_device_emulation": "executed", "native_safari": "VERIFY_REQUIRED", "real_iphone_or_ipad": "VERIFY_REQUIRED"},
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "screenshots": len(screenshots), "report": str(output.relative_to(ROOT))}, ensure_ascii=False))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-revision")
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    run(args.expected_revision, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
