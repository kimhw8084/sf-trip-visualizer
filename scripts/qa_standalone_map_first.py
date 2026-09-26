"""Decisive direct-open regression for the generated file:// standalone artifact."""

import json
import re
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

from qa_config import STANDALONE_PATH
from qa_evidence import bind_report, candidate_identity


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "QA" / "CHG-232" / "standalone"
OUT.mkdir(parents=True, exist_ok=True)
ROUTES = tuple(sorted(json.loads((ROOT / "data/phase7_app_data.json").read_text())["routes"]))
REGIONS = ("overall", "sf", "monterey", "yosemite")
DAYS = ("all", "10/2", "10/3", "10/6", "10/8", "10/11", "10/12")


def watch_browser(page, errors, console_errors, failed_requests, requests):
    page.add_init_script("""(() => {
      window.__tripFetches = [];
      window.__tripPmtilesRanges = new Set();
      window.__tripPmtilesReadCount = 0;
      const originalFetch = window.fetch.bind(window);
      window.fetch = (input, init) => {
        const url = typeof input === 'string' ? input : input?.url || String(input);
        const safeUrl = url.startsWith('data:') ? `${url.slice(0, url.indexOf(','))},<embedded>` : url;
        window.__tripFetches.push({url: safeUrl, stack: (new Error()).stack});
        return originalFetch(input, init);
      };
      const originalSlice = File.prototype.slice;
      File.prototype.slice = function(start, end, type) {
        if (this.name === 'sf_trip.pmtiles') {
          window.__tripPmtilesReadCount += 1;
          window.__tripPmtilesRanges.add(`${start}-${end}`);
        }
        return originalSlice.call(this, start, end, type);
      };
    })()""")
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
    page.on("request", lambda request: requests.append(request.url))
    page.on("requestfailed", lambda request: failed_requests.append({"url": request.url, "failure": request.failure}))


def explore_standalone(page):
    page.evaluate("()=>{window.__tripMapErrors=[];window.__tripApp.map().on('error',e=>window.__tripMapErrors.push({sourceId:e.sourceId||null,message:String(e.error?.message||e.message||e.error||''),url:e.error?.url||e.url||null}));}")
    if page.evaluate("window.__tripApp.state.presentation.mode") != "day":
        page.locator('button.mode-button[data-mode="day"]').click()
    zones = [
        ("sf", "10/5", [[-122.48, 37.82], [-122.56, 37.96], [-122.39, 37.77]]),
        ("monterey", "10/6", [[-121.90, 36.60], [-121.92, 36.55], [-121.78, 36.68]]),
        ("yosemite", "10/8", [[-119.59, 37.74], [-119.40, 37.76], [-119.77, 37.72]]),
    ]
    explored = []
    for region, date, centers in zones:
        page.evaluate("({center})=>{window.__tripApp.map().jumpTo({center,zoom:10.2});}", {"center": centers[0]})
        page.wait_for_timeout(60)
        page.locator("#dateSelect").select_option(date)
        page.wait_for_timeout(60)
        if page.evaluate("window.__tripApp.state.task.region") != region:
            page.locator("#mapOptionsToggle").click()
            page.locator(f'[data-region="{region}"]').click()
        page.wait_for_function("region=>window.__tripApp?.state?.task?.region===region", arg=region)
        page.wait_for_timeout(180)
        for center in centers:
            for zoom in (8.7, 11.5, 13.8):
                page.evaluate("({center,zoom})=>{window.__tripApp.map().jumpTo({center,zoom});}", {"center": center, "zoom": zoom})
                page.wait_for_timeout(70)
            box = page.locator("#map").bounding_box()
            if box:
                x, y = box["x"] + box["width"] * .64, box["y"] + box["height"] * .52
                page.mouse.move(x, y); page.mouse.down(); page.mouse.move(x - 78, y + 46, steps=4); page.mouse.up()
                page.mouse.wheel(0, -125)
                page.wait_for_timeout(100)
            explored.append({"region": region, "date": date, "center": center, "zoom_levels": [8.7, 11.5, 13.8], "pan_gesture": bool(box)})
        page.wait_for_timeout(180)

    page.locator("#dateSelect").select_option("all")
    if page.evaluate("window.__tripApp.state.task.region") != "overall":
        page.locator("#mapOptionsToggle").click()
        page.locator('[data-region="overall"]').click()
    page.wait_for_timeout(180)
    page.evaluate("window.__tripApp.fitVisibleMap()")
    page.wait_for_timeout(250)
    snapshot = page.evaluate("window.__tripApp.runtimeSnapshot()")
    metrics = page.evaluate("""()=>({
      fetches:window.__tripFetches||[], pmtiles_ranges:[...(window.__tripPmtilesRanges||[])], pmtiles_read_count:window.__tripPmtilesReadCount||0,
      map_errors:window.__tripMapErrors||[],
      embedded_hillshade:!!window.EMBEDDED_MAP_ASSETS?.['assets/vector/yosemite_hillshade_shadow.webp'],
      remote_resources:performance.getEntriesByType('resource').map(row=>row.name).filter(url=>/^https?:/i.test(url))
    })""")
    return {"explored": explored, "snapshot": snapshot, "metrics": metrics}


def exercise(page):
    errors = []
    console_errors = []
    failed_requests = []
    requests = []
    watch_browser(page, errors, console_errors, failed_requests, requests)
    page.route("http://**", lambda route: route.abort())
    page.route("https://**", lambda route: route.abort())
    page.goto(STANDALONE_PATH.resolve().as_uri(), wait_until="domcontentloaded", timeout=120000)
    page.wait_for_function("window.__tripApp?.map()?.isStyleLoaded()", timeout=120000)
    page.wait_for_function("window.__tripApp?.state?.runtime?.mapVisualReady", timeout=120000)

    initial = page.evaluate("window.__tripApp.runtimeSnapshot()")
    initial_ranges = set(page.evaluate("[...(window.__tripPmtilesRanges||[])]"))
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
                        features:snap.map.spatial?.route_features||0,provider:snap.provider,localAssets:snap.local_assets.status,
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

    exploration = explore_standalone(page)
    smart_snapshot = exploration["snapshot"]
    smart_fetches = exploration["metrics"]["fetches"]
    smart_map_errors = exploration["metrics"]["map_errors"]
    smart_remote_requests = [url for url in requests if url.startswith(("http://", "https://"))]
    smart_failed_requests = list(failed_requests)
    explored_ranges = set(exploration["metrics"]["pmtiles_ranges"])
    initial_range_count = len(initial_ranges)
    added_range_count = len(explored_ranges - initial_ranges)

    page.unroute("http://**")
    page.unroute("https://**")
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
    unexpected_failed_requests = [row for row in failed_requests if "server.arcgisonline.com" not in row["url"]]
    result = {
        "status": "PASS", "mode": "file://", "standalone": str(STANDALONE_PATH.relative_to(ROOT)),
        "initial": initial, "probes": probes, "direct_open_exploration": exploration,
        "smart_local_network_evidence": {"fetches": smart_fetches, "remote_requests": smart_remote_requests, "failed_requests": smart_failed_requests, "pmtiles_total_reads": exploration["metrics"]["pmtiles_read_count"], "pmtiles_initial_unique_ranges": initial_range_count, "pmtiles_ranges_after_exploration": len(explored_ranges), "new_pmtiles_ranges": added_range_count},
        "smart_snapshot_after_exploration": smart_snapshot, "smart_map_errors": smart_map_errors,
        "recovery": recovery, "continued": continued, "final": final,
        "page_errors": errors, "console_errors": console_errors, "failed_requests": failed_requests,
        "assertions": {
            "all_active_routes_exercised": set(row["route"] for row in probes) == set(ROUTES),
            "all_regions_exercised": len({row["region"] for row in probes}) == 4,
            "all_probes_use_smart": all(row["provider"] == "vector" and row["localAssets"] == "ready" and row["canvas"] == 1 for row in probes),
            "spatial_content_remains_useful_or_explicit_sparse": all(row["useful"] or (row["markers"] == 0 and row["features"] == 0) for row in probes),
            "no_asset_failures": all(row["failures"] == 0 for row in probes),
            "repeated_sf_monterey_yosemite_exploration": len(exploration["explored"]) == 9 and {row["region"] for row in exploration["explored"]} == {"sf", "monterey", "yosemite"} and all(row["pan_gesture"] and len(row["zoom_levels"]) >= 3 for row in exploration["explored"]),
            "standalone_hillshade_is_embedded_in_map_asset_bytes": exploration["metrics"]["embedded_hillshade"],
            "new_pmtiles_ranges_read_during_exploration": added_range_count >= 10,
            "no_duplicate_canvas_or_markers_after_smart_exploration": smart_snapshot["map"]["canvas_count"] == 1 and len(smart_snapshot["map"]["photo_marker_keys"]) == len(set(smart_snapshot["map"]["photo_marker_keys"])),
            "smart_standalone_usable_after_repeated_exploration": smart_snapshot["provider"] == "vector" and smart_snapshot["provider_health"]["vector"] == "ready" and smart_snapshot["local_assets"]["status"] == "ready" and not smart_snapshot["local_assets"]["failures"] and smart_snapshot["map_visual_ready"] and smart_snapshot["map"]["canvas_count"] == 1 and smart_snapshot["map"]["spatial"]["useful"] and smart_snapshot["map"]["spatial"]["markers_in_viewport"] >= 3 and smart_snapshot["map"]["spatial"]["route_features_in_viewport"] >= 1,
            "no_fetch_for_smart_embedded_resources": not smart_fetches,
            "no_remote_request_during_smart_exploration": not smart_remote_requests and not exploration["metrics"]["remote_resources"],
            "no_smart_maplibre_errors": not smart_map_errors,
            "no_smart_local_failed_request": not smart_failed_requests,
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
    embedded_branch = "if (window.EMBEDDED_MAP_ASSETS) {"
    force_local_fetch = "if (window.EMBEDDED_MAP_ASSETS && path !== 'assets/vector/yosemite_hillshade_shadow.webp') {"
    file_guard = "if (location.protocol === 'file:') throw new Error(`Missing embedded asset ${path}`);"
    if embedded_branch not in source or file_guard not in source:
        return {"status": "FAIL", "reason": "could not produce local-fetch negative control"}
    broken = source.replace(embedded_branch, force_local_fetch, 1).replace(file_guard, "", 1)
    with tempfile.TemporaryDirectory(prefix="sf-trip-standalone-negative-") as directory:
        path = Path(directory) / "embedded-hillshade-fetch-regression.html"
        path.write_text(broken)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            fetches = []
            page.add_init_script("""(() => { const original=window.fetch.bind(window); window.__negativeFetches=[]; window.fetch=(input,init)=>{const url=typeof input==='string'?input:input?.url||String(input);window.__negativeFetches.push(url);return original(input,init)}; })()""")
            page.goto(path.resolve().as_uri(), wait_until="domcontentloaded", timeout=120000)
            page.wait_for_function("window.__tripApp?.state?.runtime?.mapVisualReady", timeout=120000)
            page.wait_for_timeout(700)
            snapshot = page.evaluate("()=>({text:document.querySelector('#mapError .map-error-message')?.textContent||'',events:window.__tripApp?.state?.runtime?.events||[],local:window.__tripApp?.state?.runtime?.localAssets||{},fetches:window.__negativeFetches||[]})")
            browser.close()
    local_fetch_seen = any("assets/vector/yosemite_hillshade_shadow.webp" in url for url in snapshot["fetches"])
    regression_detected = snapshot["local"].get("status") == "failed" and "map_runtime" in snapshot["text"] and "Failed to fetch" in snapshot["text"]
    return {"status": "PASS" if local_fetch_seen and regression_detected else "FAIL", "oracle": "embedded_hillshade_local_fetch_is_detected", "local_fetch_seen": local_fetch_seen, "regression_detected": regression_detected, "snapshot": snapshot}


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
