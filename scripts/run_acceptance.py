"""Real Chromium regression suite for the final local-photo map package."""

import json
from io import BytesIO
from pathlib import Path
from PIL import Image
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / "QA/screenshots"
SHOTS.mkdir(parents=True, exist_ok=True)
URL = (ROOT / "index.html").as_uri()
STANDALONE = (ROOT / "SF_Smart_Minority_P0_Final_Standalone.html").as_uri()
result = {"browser": "Playwright Chromium (real headless browser)", "checks": {}, "screenshots": [], "page_errors": []}


def check(name, actual, expected=True):
    passed = actual == expected
    result["checks"][name] = {"pass": passed, "actual": actual, "expected": expected}
    if not passed:
        print("FAIL", name, actual, "expected", expected)


def shot(page, name):
    path = SHOTS / f"final_{name}.png"
    page.screenshot(path=str(path))
    result["screenshots"].append(str(path.relative_to(ROOT)))


def settle(page, ms=450):
    page.wait_for_timeout(ms)
    if page.evaluate("!!window.__tripApp"):
        page.evaluate("()=>window.__tripApp.whenIdle()")


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
    page.on("pageerror", lambda error: result["page_errors"].append(str(error)))
    http_requests = []
    page.on("request", lambda request: http_requests.append(request.url) if request.url.startswith("http") else None)
    page.goto(URL)
    settle(page, 1100)
    check("initial_physical_place_markers", page.locator(".photo-marker").count(), 28)
    check("initial_aggregate_markers", page.locator(".photo-cluster").count(), 3)
    check("initial_visible_timeline_slots", page.locator("[data-timeline]").count(), 71)
    check("initial_maplibre_canvas", page.locator(".maplibregl-canvas").count(), 1)
    check("initial_broken_photo_markers", page.locator(".photo-marker img").evaluate_all("es=>es.filter(e=>!e.complete||e.naturalWidth===0).length"), 0)
    check("initial_remote_requests", len(http_requests), 0)
    shot(page, "1440_overall")

    matrix = page.evaluate("""() => {const a=window.__tripApp,s=a.state,dates=['all',...a.DATA.dates.map(x=>x.key)],regions=['overall','sf','monterey','yosemite'],out=[];
      for(const route of ['A1','A2','B1','B2'])for(const date of dates)for(const region of regions){s.routes=new Set([route]);s.date=date;s.region=region;
        const markers=a.DATA.markers.filter(a.markerVisible),timeline=a.DATA.timeline.filter(a.timelineVisible),legs=a.DATA.legs.filter(a.legVisible);
        out.push({route,date,region,markers:markers.length,timeline:timeline.length,legs:legs.length,
          invalid:markers.some(m=>!m.routes.includes(route))||timeline.some(t=>!t.routes.includes(route)||date!=='all'&&t.date_key!==date)||legs.some(l=>{let from=a.DATA.markers.find(m=>m.place_key===l.from),to=a.DATA.markers.find(m=>m.place_key===l.to);return !l.routes.includes(route)||date!=='all'&&l.date!==date||from&&to&&(!from.occurrences.some(o=>o.route===route&&o.date.startsWith(l.date))||!to.occurrences.some(o=>o.route===route&&o.date.startsWith(l.date)))} )});
      }s.routes=new Set(['A1','A2','B1','B2']);s.date='all';s.region='overall';return out;}""")
    check("state_matrix_size", len(matrix), 160)
    check("state_matrix_invalid_compositions", sum(x["invalid"] for x in matrix), 0)
    result["state_matrix"] = matrix
    suppressed = page.evaluate("""()=>{const d=window.__tripApp.DATA,m=Object.fromEntries(d.markers.map(x=>[x.place_key,x]));return d.legs.filter(l=>m[l.from]&&m[l.to]&&!l.routes.some(r=>m[l.from].occurrences.some(o=>o.route===r&&o.date.startsWith(l.date))&&m[l.to].occurrences.some(o=>o.route===r&&o.date.startsWith(l.date)))).map(l=>l.leg_id)}""")
    check("cross_day_conceptual_legs_suppressed", len(suppressed), 3)
    result["cross_day_suppressed_leg_ids"] = suppressed

    for route in ("A1", "A2", "B1", "B2"):
        page.locator(f"[data-route={route}]").click()
        settle(page, 220)
        page.locator(f"[data-route={route}]").click()
        settle(page, 220)
    check("all_route_toggles_restored", page.evaluate("[...window.__tripApp.state.routes].sort().join(',')"), "A1,A2,B1,B2")
    for date in ["10/3", "10/4", "10/5", "10/6", "10/7", "10/8", "10/9", "10/10", "10/11", "all"]:
        page.locator("#dateSelect").select_option(date)
        expected = page.evaluate("window.__tripApp.DATA.markers.filter(window.__tripApp.markerVisible).length")
        page.wait_for_function("n=>document.querySelectorAll('.photo-marker').length===n", arg=expected, timeout=5000)
        settle(page, 140)
        check(f"date_{date}_visible_marker_count", page.locator(".photo-marker").count(), expected)
    for region in ("sf", "monterey", "yosemite", "overall"):
        page.locator(f"[data-region={region}]").click()
        settle(page, 280)
        check(f"region_{region}_marker_count", page.locator(".photo-marker").count(), {"sf": 19, "monterey": 3, "yosemite": 6, "overall": 28}[region])
        shot(page, f"1440_{region}")

    for route in ("A2", "B1", "B2"):
        page.locator(f"[data-route={route}]").click()
        settle(page, 180)
    page.locator("#dateSelect").select_option("10/9")
    page.locator("[data-region=yosemite]").click()
    settle(page, 600)
    check("A1_10_9_yosemite_markers", page.locator(".photo-marker").count(), 1)
    check("A1_10_9_yosemite_timeline", page.locator("[data-timeline]").count(), 1)
    check("A1_10_9_yosemite_flex", "FLEX" in page.locator("[data-timeline]").first.inner_text(), True)
    check("A1_10_9_yosemite_no_cross_day_leg", page.evaluate("window.__tripApp.DATA.legs.filter(window.__tripApp.legVisible).length"), 0)
    shot(page, "A1_10_9_yosemite")

    page.reload()
    settle(page, 850)
    page.locator("[data-timeline]").first.click()
    settle(page, 400)
    check("timeline_select_place", page.evaluate("window.__tripApp.state.selected"), "ferry")
    check("timeline_selected_photo_marker_visible", page.locator(".photo-marker[data-place-key=ferry]").evaluate("e=>getComputedStyle(e).display!=='none'"), True)
    check("timeline_focus_zoom_offline_at_native_topo_detail", page.evaluate("(()=>{const z=document.getElementById('map')._fullLayout.map._subplot.map.getZoom();return z>=11.9&&z<=12.1})()"), True)
    page.locator("[data-tab=details]").click()
    settle(page, 320)
    check("ferry_detail_exactly_three_photos", page.locator("#detailsPane .photo-slot img").count(), 3)
    check("ferry_detail_broken_photos", page.locator("#detailsPane .photo-slot img").evaluate_all("es=>es.filter(e=>!e.complete||e.naturalWidth===0).length"), 0)
    check("ferry_detail_deduped_timing_cards", page.locator("#detailsPane .timeline-card").count(), 1)
    check("ferry_detail_four_route_chips", page.locator("#detailsPane .chip").count(), 4)
    check("ferry_detail_google_maps", page.locator("#detailsPane .maps-link").count(), 1)
    shot(page, "1440_ferry_detail")
    page.evaluate("window.__tripApp.selectPlace('mariposa',{focus:true,openDetails:true})")
    settle(page, 200)
    check("mariposa_detail_exactly_three_photos", page.locator("#detailsPane .photo-slot img").count(), 3)
    check("mariposa_detail_distinct_timing_cards", page.locator("#detailsPane .timeline-card").count(), 2)
    shot(page, "1440_mariposa_detail")

    detail_reviews = []
    for key in page.evaluate("window.__tripApp.DATA.markers.map(x=>x.place_key)"):
        page.evaluate("key=>window.__tripApp.renderDetail(key)", key)
        page.wait_for_function("[...document.querySelectorAll('#detailsPane .photo-slot img')].length===3&&[...document.querySelectorAll('#detailsPane .photo-slot img')].every(e=>e.complete&&e.naturalWidth>0)", timeout=8000)
        paths = page.locator("#detailsPane .photo-slot").evaluate_all("es=>es.map(e=>e.dataset.photoPath)")
        expected_paths = [f"assets/photos/medium/{key}__{role}.webp" for role in ("hero", "experience", "scale_context")]
        detail_reviews.append({"place_key": key, "paths": paths, "correct": paths == expected_paths})
    check("all_28_details_have_exact_local_role_paths", sum(x["correct"] for x in detail_reviews), 28)
    result["all_place_detail_review"] = detail_reviews

    page.evaluate("window.__tripApp.selectPlace('ferry',{focus:true,openDetails:false})")
    settle(page, 350)
    page.locator(".photo-marker[data-place-key=ferry]").hover()
    settle(page, 180)
    check("hover_preview_visible", page.locator("#previewCard.show").count(), 1)
    check("hover_preview_real_photo", page.locator("#previewCard .preview-media").evaluate("e=>e.complete&&e.naturalWidth>0"), True)
    check("hover_preview_why_now", "Why now?" in page.locator("#previewCard").inner_text(), True)
    shot(page, "1440_hover_preview")

    drift = page.evaluate("""() => {const m=document.getElementById('map')._fullLayout.map._subplot.map,r=document.getElementById('map').getBoundingClientRect(),a=window.__tripApp.DATA.markers,visible=[...document.querySelectorAll('.photo-marker')].filter(e=>getComputedStyle(e).display!=='none');return visible.map(e=>{let v=a.find(x=>x.place_key===e.dataset.placeKey),p=m.project([v.lon,v.lat]),b=e.getBoundingClientRect();return Math.hypot((b.left+b.width/2-r.left)-p.x,(b.top+b.height/2-r.top)-p.y)});}""")
    check("max_marker_position_drift_at_most_one_pixel", round(max(drift), 2) <= 1, True)
    result["max_marker_position_drift_pixels"] = round(max(drift), 2)
    for i in range(8):
        page.evaluate("i=>{let m=document.getElementById('map')._fullLayout.map._subplot.map;m.panBy([11,-7],{duration:0});m.zoomTo(12.8+(i%2)*.7,{duration:0});}", i)
    settle(page, 350)
    check("pan_zoom_canvas_retained", page.locator(".maplibregl-canvas").count(), 1)
    check("pan_zoom_photo_markers_retained", page.locator(".photo-marker").count(), 28)
    shot(page, "1440_pan_zoom")
    for width in (1024, 768, 430, 390, 1440):
        page.set_viewport_size({"width": width, "height": 900 if width >= 1024 else 844})
        settle(page, 350)
        check(f"live_resize_{width}_no_overflow", page.evaluate("document.documentElement.scrollWidth<=innerWidth"), True)
        check(f"live_resize_{width}_map_canvas", page.locator(".maplibregl-canvas").count(), 1)
        check(f"live_resize_{width}_marker_drift_at_most_one_pixel", page.evaluate("""()=>{const m=document.getElementById('map')._fullLayout.map._subplot.map,r=document.getElementById('map').getBoundingClientRect(),e=document.querySelector('.photo-marker[data-place-key=ferry]'),v=window.__tripApp.DATA.markers.find(x=>x.place_key==='ferry'),p=m.project([v.lon,v.lat]),b=e.getBoundingClientRect();return Math.hypot((b.left+b.width/2-r.left)-p.x,(b.top+b.height/2-r.top)-p.y)<=1}"""), True)

    # Exercise both success and failure health paths without relying on remote tile availability.
    provider = page.evaluate("""async()=>{const a=window.__tripApp,original=window.Image;return {before:a.state.provider,health:a.state.providerHealth}}""")
    result["provider_before"] = provider
    for name in ("light", "osm", "satellite"):
        page.route("https://**/*", lambda route: route.abort())
        page.locator(f"[data-provider={name}]").click()
        settle(page, 2900)
        check(f"provider_{name}_failure_fallback", page.evaluate("window.__tripApp.state.provider"), "offline")
        page.unroute("https://**/*")
    # Local success fixture: the probe image and tile requests receive an actual decodable PNG.
    tile_buffer = BytesIO()
    Image.new("RGB", (256, 256), (220, 235, 240)).save(tile_buffer, "PNG")
    png = tile_buffer.getvalue()
    page.route("https://**/*", lambda route: route.fulfill(status=200, content_type="image/png", body=png))
    page.locator("[data-provider=osm]").click()
    settle(page, 900)
    check("provider_local_success_ready", page.evaluate("window.__tripApp.state.provider"), "osm")
    check("provider_local_success_canvas", page.locator(".maplibregl-canvas").count(), 1)
    shot(page, "1440_provider_ready_fixture")
    page.unroute("https://**/*")
    page.route("https://**/*", lambda route: route.abort())
    page.evaluate("document.getElementById('map')._fullLayout.map._subplot.map.panBy([450,350],{duration:0})")
    settle(page, 3600)
    check("provider_post_success_pan_tile_failure_fallback", page.evaluate("window.__tripApp.state.provider"), "offline")
    page.unroute("https://**/*")
    page.route("https://**/*", lambda route: route.fulfill(status=200, content_type="image/png", body=png) if "health=" in route.request.url else route.abort())
    page.locator("[data-provider=osm]").click()
    settle(page, 3200)
    check("provider_probe_success_viewport_failure_fallback", page.evaluate("window.__tripApp.state.provider"), "offline")
    page.unroute("https://**/*")
    page.locator("[data-provider=offline]").click()
    settle(page, 350)
    check("no_remote_photo_requests", sum("photo" in url.lower() or "upload.wikimedia" in url for url in http_requests), 0)
    result["http_request_count"] = len(http_requests)

    page.close()
    for width, height in ((1440, 900), (1280, 800), (1024, 768), (768, 800), (430, 844), (390, 844)):
        mobile = width <= 430
        context = browser.new_context(viewport={"width": width, "height": height}, has_touch=mobile, is_mobile=mobile)
        screen = context.new_page()
        screen.on("pageerror", lambda error: result["page_errors"].append(str(error)))
        screen.goto(URL)
        settle(screen, 750)
        check(f"width_{width}_no_horizontal_overflow", screen.evaluate("document.documentElement.scrollWidth<=innerWidth"), True)
        check(f"width_{width}_canvas", screen.locator(".maplibregl-canvas").count(), 1)
        check(f"width_{width}_broken_marker_images", screen.locator(".photo-marker img").evaluate_all("es=>es.filter(e=>!e.complete||e.naturalWidth===0).length"), 0)
        shot(screen, f"width_{width}")
        if mobile:
            screen.locator("[data-timeline]").first.tap()
            settle(screen, 350)
            marker = screen.locator(".photo-marker[data-place-key=ferry]")
            marker.tap()
            settle(screen, 180)
            check(f"width_{width}_tap_preview_photo", screen.locator("#previewCard .preview-media").evaluate("e=>e.complete&&e.naturalWidth>0"), True)
            check(f"width_{width}_tap_detail_three_photos", screen.locator("#detailsPane .photo-slot img").count(), 3)
            shot(screen, f"width_{width}_tap_detail")
        context.close()

    standalone = browser.new_page(viewport={"width": 1280, "height": 800})
    standalone.on("pageerror", lambda error: result["page_errors"].append(str(error)))
    remote = []
    standalone.on("request", lambda request: remote.append(request.url) if request.url.startswith("http") else None)
    standalone.goto(STANDALONE)
    settle(standalone, 900)
    check("standalone_28_markers", standalone.locator(".photo-marker").count(), 28)
    check("standalone_no_remote_requests", len(remote), 0)
    standalone.locator("[data-timeline]").first.click()
    standalone.locator("[data-tab=details]").click()
    standalone.wait_for_function("[...document.querySelectorAll('#detailsPane .photo-slot img')].length===3&&[...document.querySelectorAll('#detailsPane .photo-slot img')].every(e=>e.complete&&e.naturalWidth>0)", timeout=8000)
    check("standalone_detail_photo_data_uris", standalone.locator("#detailsPane .photo-slot img").evaluate_all("es=>es.length===3&&es.every(e=>e.src.startsWith('data:image/webp;base64,')&&e.complete&&e.naturalWidth>0)"), True)
    standalone.close()
    browser.close()

result["passed_checks"] = sum(x["pass"] for x in result["checks"].values())
result["total_checks"] = len(result["checks"])
result["status"] = "PASS" if result["passed_checks"] == result["total_checks"] and not result["page_errors"] else "FAIL"
(ROOT / "QA/final_acceptance.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"status": result["status"], "passed": result["passed_checks"], "total": result["total_checks"], "page_errors": result["page_errors"]}, indent=2))
