"""Decisive direct-open regression for the generated file:// standalone artifact."""

import json
import re
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

from qa_config import STANDALONE_PATH
from qa_evidence import bind_report, candidate_identity


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "QA" / "CHG-188" / "standalone"
OUT.mkdir(parents=True, exist_ok=True)
ROUTES = tuple(sorted(json.loads((ROOT / "data/phase7_app_data.json").read_text())["routes"]))
REGIONS = ("overall", "sf", "monterey", "yosemite")
DAYS = ("all", "10/3", "10/6", "10/8", "10/11")


def exercise(page):
    errors = []
    console_errors = []
    failed_requests = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
    page.on("requestfailed", lambda request: failed_requests.append(request.url))
    page.goto(STANDALONE_PATH.resolve().as_uri(), wait_until="domcontentloaded", timeout=120000)
    page.wait_for_function("window.__tripApp?.map()?.isStyleLoaded()", timeout=120000)
    page.wait_for_function("window.__tripApp?.state?.runtime?.mapVisualReady", timeout=120000)

    initial = page.evaluate("window.__tripApp.runtimeSnapshot()")
    probes = []
    for route in ROUTES:
        for region in REGIONS:
            for date in DAYS:
                probe = page.evaluate(
                    """async ({route,region,date}) => {
                      const a=window.__tripApp;
                      a.state.routes=new Set([route]); a.state.primaryRoute=route;
                      a.state.date=date; a.state.region=region; a.state.selected=null; a.setMode('day');
                      await a.drawMap(false); await a.whenIdle();
                      const snap=a.runtimeSnapshot();
                      return {route,region,date,canvas:snap.map.canvas_count,markers:snap.map.photo_markers,
                        features:a.visibleRouteFeatures().length,provider:snap.provider,localAssets:snap.local_assets.status,
                        useful:snap.map.spatial?.useful,failures:snap.local_assets.failures.length};
                    }""",
                    {"route": route, "region": region, "date": date},
                )
                probes.append(probe)

    for _ in range(3):
        page.locator("#mapOptionsToggle").click(); page.locator("#mapOptionsToggle").click()
        page.locator('[data-mode="place"]').click(); page.locator('[data-mode="day"]').click(); page.locator('[data-mode="decide"]').click()
        page.locator('[data-sheet="compact"]').click(); page.locator("#workbenchToggle").click(); page.locator('[data-sheet="full"]').click(); page.locator("#workbenchToggle").click(); page.locator("#workbenchToggle").click()
        page.locator("#langToggle").click(); page.locator("#langToggle").click()
        page.locator("#themeToggle").click(); page.locator("#themeToggle").click()
        page.locator('[data-mode="day"]').click(); page.locator("#dateSelect").select_option("10/8"); page.locator("#dateSelect").select_option("all")
        page.evaluate("async()=>{const a=window.__tripApp;a.selectPlace('ferry',{focus:false});a.hidePreview({returnFocus:false});await a.drawMap(false);await a.whenIdle()}")
        page.wait_for_timeout(120)

    page.route("https://server.arcgisonline.com/**", lambda route: route.abort())
    page.evaluate("window.__tripApp.chooseProvider('satellite')")
    page.wait_for_timeout(3300)
    recovery = page.evaluate("window.__tripApp.runtimeSnapshot()")
    page.mouse.wheel(0, -900); page.mouse.wheel(0, 900)
    page.evaluate("async(route)=>{const a=window.__tripApp;a.state.routes=new Set([route]);a.state.primaryRoute=route;a.state.region='yosemite';a.state.date='10/8';await a.drawMap(false);await a.whenIdle()}", ROUTES[0])
    continued = page.evaluate("window.__tripApp.runtimeSnapshot()")
    page.unroute("https://server.arcgisonline.com/**")
    final = page.evaluate("window.__tripApp.runtimeSnapshot()")
    unexpected_console_errors = [message for message in console_errors if "server.arcgisonline.com" not in message and "ERR_FAILED" not in message]
    unexpected_failed_requests = [url for url in failed_requests if "server.arcgisonline.com" not in url]
    result = {
        "status": "PASS", "mode": "file://", "standalone": str(STANDALONE_PATH.relative_to(ROOT)),
        "initial": initial, "probes": probes, "recovery": recovery, "continued": continued, "final": final,
        "page_errors": errors, "console_errors": console_errors, "failed_requests": failed_requests,
        "assertions": {
            "all_active_routes_exercised": set(row["route"] for row in probes) == set(ROUTES),
            "all_regions_exercised": len({row["region"] for row in probes}) == 4,
            "all_probes_use_smart": all(row["provider"] == "vector" and row["localAssets"] == "ready" and row["canvas"] == 1 for row in probes),
            "spatial_content_remains_useful_or_explicit_sparse": all(row["useful"] or (row["markers"] == 0 and row["features"] == 0) for row in probes),
            "no_asset_failures": all(row["failures"] == 0 for row in probes),
            "satellite_recovers_once": bool(recovery["provider_events"]) and recovery["provider"] == "vector" and any(event["type"] == "fallback_to_smart" for event in recovery["provider_events"]),
            "smart_continues_after_recovery": continued["provider"] == "vector" and continued["map"]["canvas_count"] == 1 and continued["map"]["spatial"]["useful"],
            "no_duplicate_canvas": final["map"]["canvas_count"] == 1,
            "no_duplicate_markers": len(final["map"]["photo_marker_keys"]) == len(set(final["map"]["photo_marker_keys"])),
            "no_local_runtime_errors": not errors and not unexpected_console_errors and not unexpected_failed_requests,
        },
    }
    result["unexpected_console_errors"] = unexpected_console_errors
    result["unexpected_failed_requests"] = unexpected_failed_requests
    result["status"] = "PASS" if all(result["assertions"].values()) else "FAIL"
    page.screenshot(path=str(OUT / "standalone_file_origin_final.png"), full_page=True)
    return result


def negative_control():
    source = STANDALONE_PATH.read_text()
    broken = re.sub(r'("assets/vector/(?:fonts|sprites)/[^"\\]+":")[^"]*"', r'\1x"', source, count=1)
    if broken == source:
        return {"status": "FAIL", "reason": "could not produce missing-asset fixture"}
    with tempfile.TemporaryDirectory(prefix="sf-trip-standalone-negative-") as directory:
        path = Path(directory) / "missing-embedded-asset.html"
        path.write_text(broken)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            page.goto(path.resolve().as_uri(), wait_until="domcontentloaded", timeout=120000)
            page.wait_for_timeout(1800)
            snapshot = page.evaluate("()=>({text:document.querySelector('#mapError .map-error-message')?.textContent||'',events:window.__tripApp?.state?.runtime?.events||[],local:window.__tripApp?.state?.runtime?.localAssets||{}})")
            browser.close()
    intended = "Missing embedded asset" in snapshot["text"] or any("Missing embedded asset" in str(event) for event in snapshot["events"] + snapshot["local"].get("failures", []))
    return {"status": "PASS" if intended else "FAIL", "oracle": "explicit_missing_embedded_asset", "snapshot": snapshot}


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    positive = exercise(page)
    browser.close()

negative = negative_control()
report = {"schema_version": 2, "status": "PASS" if positive["status"] == "PASS" and negative["status"] == "PASS" else "FAIL", "candidate": candidate_identity()["sha"], "candidate_tree": candidate_identity()["tree"], "positive": positive, "negative_control": negative}
bind_report(report, candidate_identity())
(OUT / "standalone.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"status": report["status"], "positive": positive["status"], "negative_control": negative["status"], "probes": len(positive.get("probes", []))}, ensure_ascii=False, indent=2))
raise SystemExit(0 if report["status"] == "PASS" else 1)
