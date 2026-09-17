"""Independent P0 checks for every photo panel, geo drift and control sync."""

import json
from pathlib import Path

from playwright.sync_api import sync_playwright
from qa_config import MODULAR_URL


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "QA/map_first"
URL = MODULAR_URL
LOCAL_ORIGIN = URL.rsplit("/", 1)[0] + "/"
result = {"checks": {}, "detail_reviews": [], "errors": [], "remote_photo_requests": []}


def check(name, actual, expected):
    result["checks"][name] = {"actual": actual, "expected": expected, "pass": actual == expected}


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.on("pageerror", lambda error: result["errors"].append(str(error)))
    page.on("request", lambda request: result["remote_photo_requests"].append(request.url) if "photo" in request.url.lower() and not request.url.startswith(LOCAL_ORIGIN) else None)
    page.goto(URL, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_function("window.__tripApp?.map()?.isStyleLoaded()", timeout=30000)
    page.wait_for_function("[...document.querySelectorAll('.photo-marker img')].every(x=>x.complete&&x.naturalWidth>0)", timeout=15000)
    expected_places = page.evaluate("window.__tripApp.DATA.markers.length")
    check("physical_marker_objects", page.locator(".photo-marker").count(), expected_places)
    check("all_marker_hero_thumbs_decode", page.locator(".photo-marker img").evaluate_all("xs=>xs.every(x=>x.complete&&x.naturalWidth>0)"), True)
    check("marker_place_keys_unique", page.locator(".photo-marker").evaluate_all("xs=>new Set(xs.map(x=>x.dataset.placeKey)).size"), expected_places)
    check("date_ribbon_days", page.locator(".day-chip").count(), 10)
    check("default_day_summary_cards", page.locator(".map-slot").count(), 9)
    check("desktop_provider_choices", page.locator("[data-provider]").evaluate_all("xs=>xs.map(x=>x.dataset.provider)"), ["vector", "satellite"])
    check("mobile_provider_choices", page.locator("#mobileProvider option").evaluate_all("xs=>xs.map(x=>x.value)"), ["vector", "satellite"])
    check("route_layers_four_colors", page.evaluate("""()=>{const a=window.__tripApp,m=a.map();return ['A1','A2','B1','B2'].every(r=>m.getPaintProperty('trip-transfer-'+r,'line-color')===a.DATA.routes[r].color&&m.getPaintProperty('trip-local-'+r,'line-color')===a.DATA.routes[r].color)}"""), True)

    # Real UI toggles, not just state mutation.
    for route in ("A1", "A2", "B1", "B2"):
        page.locator(f'[data-route="{route}"]').click()
        page.evaluate("()=>window.__tripApp.whenIdle()")
        check(f"toggle_{route}_off", page.locator(f'[data-route="{route}"]').get_attribute("aria-pressed"), "false")
        page.locator(f'[data-route="{route}"]').click()
        page.evaluate("()=>window.__tripApp.whenIdle()")
        check(f"toggle_{route}_on", page.locator(f'[data-route="{route}"]').get_attribute("aria-pressed"), "true")
    for date in ("10/3", "10/4", "10/5", "10/6", "10/7", "10/8", "10/9", "10/10", "10/11", "all"):
        page.locator(f'.day-chip[data-day="{date}"]').click()
        page.wait_for_function("date=>window.__tripApp.state.date===date", arg=date)
        page.evaluate("()=>window.__tripApp.whenIdle()")
        check(f"date_{date}_control_sync", page.locator("#dateSelect").input_value(), date)
        check(f"date_{date}_marker_count", page.locator(".photo-marker").count(), page.evaluate("window.__tripApp.DATA.markers.filter(window.__tripApp.markerVisible).length"))
    for region in ("sf", "monterey", "yosemite", "overall"):
        page.locator(f'[data-region="{region}"]').click()
        page.evaluate("()=>window.__tripApp.whenIdle()")
        expected_region = page.evaluate("region=>window.__tripApp.DATA.markers.filter(m=>region==='overall'||window.__tripApp.DATA.place_region[m.place_key]===region).length", region)
        check(f"region_{region}_marker_count", page.locator(".photo-marker").count(), expected_region)

    page.locator('[data-tab="details"]').click()
    keys = page.evaluate("window.__tripApp.DATA.markers.map(x=>x.place_key)")
    for key in keys:
        page.evaluate("key=>window.__tripApp.renderDetail(key)", key)
        page.wait_for_function("[...document.querySelectorAll('#detailsPane .photo-slot img')].length===3&&[...document.querySelectorAll('#detailsPane .photo-slot img')].every(x=>x.complete&&x.naturalWidth>0)", timeout=15000)
        review = page.evaluate("""key=>{const a=window.__tripApp,x=a.DATA.markers.find(m=>m.place_key===key);return {key,roles:[...document.querySelectorAll('#detailsPane .photo-slot')].map(y=>y.dataset.photoRole),paths:[...document.querySelectorAll('#detailsPane .photo-slot')].map(y=>y.dataset.photoPath),decoded:[...document.querySelectorAll('#detailsPane .photo-slot img')].every(y=>y.complete&&y.naturalWidth>0),timings:document.querySelectorAll('#detailsPane .fact .timeline-card').length,maps:document.querySelectorAll('#detailsPane .maps-link').length,why:document.querySelector('#detailsPane .detail-glance')?.innerText.includes('왜 지금?'),englishPrimary:!/[가-힣]/.test(document.querySelector('#detailsPane h2')?.innerText||''),koreanSubtitle:!!document.querySelector('#detailsPane .place-korean')?.innerText,routeChips:document.querySelectorAll('#detailsPane .routechips .chip').length,expectedRouteChips:x.routes.filter(r=>a.state.routes.has(r)).length,decisionRules:document.querySelectorAll('#detailsPane .decision').length,expectedDecisionRules:x.decision_rules?.length||0,summary:document.querySelectorAll('#detailsPane .fact').length>=3}}""", key)
        review["correct"] = review["roles"] == ["HERO", "EXPERIENCE", "SCALE_CONTEXT"] and review["paths"] == [f"assets/photos/medium/{key}__{role}.webp" for role in ("hero", "experience", "scale_context")] and review["decoded"] and review["maps"] == 1 and review["why"] and review["englishPrimary"] and review["koreanSubtitle"] and review["routeChips"] == review["expectedRouteChips"] and review["decisionRules"] == review["expectedDecisionRules"] and review["summary"]
        result["detail_reviews"].append(review)
    check(f"all_{expected_places}_detail_panels_correct", sum(x["correct"] for x in result["detail_reviews"]), expected_places)
    check("ferry_identical_timing_deduplicated", next(x["timings"] for x in result["detail_reviews"] if x["key"] == "ferry"), 1)
    check("mariposa_distinct_timings_retained", next(x["timings"] for x in result["detail_reviews"] if x["key"] == "mariposa"), 2)

    page.locator("#langToggle").click()
    page.wait_for_function("document.documentElement.lang==='en'")
    english_failures = []
    for key in keys:
        page.evaluate("key=>window.__tripApp.renderDetail(key)", key)
        untranslated = page.evaluate("document.getElementById('detailsPane').innerText.split('\\n').filter(x=>/[가-힣]/.test(x))")
        if untranslated:
            english_failures.append({"key": key, "lines": untranslated})
    check("english_details_with_hangul", english_failures, [])
    page.evaluate("()=>{const a=window.__tripApp;a.state.routes=new Set(['A1','A2','B1','B2']);a.state.date='all';a.state.region='overall';a.renderTimeline();a.renderDetail(null)}")
    english_ui_hangul = page.evaluate("document.body.innerText.split('\\n').filter(x=>/[가-힣]/.test(x)&&x.trim()!=='한국어')")
    check("english_complete_ui_with_hangul", english_ui_hangul, [])
    check("english_light_mode", page.evaluate("document.documentElement.lang==='en'&&document.documentElement.dataset.theme==='light'"), True)
    page.locator("#themeToggle").click()
    page.wait_for_function("document.documentElement.dataset.theme==='dark'&&window.__tripApp.map().isStyleLoaded()")
    check("english_dark_mode", page.evaluate("document.documentElement.lang==='en'&&document.documentElement.dataset.theme==='dark'"), True)
    page.screenshot(path=str(OUT / "theme_english_dark_1440.png"))
    page.locator("#langToggle").click()
    page.wait_for_function("document.documentElement.lang==='ko'")
    check("korean_dark_mode", page.evaluate("document.documentElement.lang==='ko'&&document.documentElement.dataset.theme==='dark'"), True)
    page.screenshot(path=str(OUT / "theme_korean_dark_1440.png"))
    page.locator("#themeToggle").click()
    page.wait_for_function("document.documentElement.dataset.theme==='light'&&window.__tripApp.map().isStyleLoaded()")
    check("korean_light_mode", page.evaluate("document.documentElement.lang==='ko'&&document.documentElement.dataset.theme==='light'"), True)
    page.evaluate("()=>{window.__tripApp.state.selected=null;window.__tripApp.renderDetail(null)}")
    check(f"unselected_details_browse_{expected_places}_stops", page.locator(".stop-browser-card").count(), expected_places)

    # MapLibre projection is the source of truth after pan, zoom and live resize.
    page.evaluate("()=>window.__tripApp.map().jumpTo({center:[-122.42,37.78],zoom:11.5})")
    page.wait_for_timeout(350)
    drift_expr = """()=>{const a=window.__tripApp,m=a.map(),r=document.getElementById('map').getBoundingClientRect();return [...document.querySelectorAll('.photo-marker')].filter(e=>e.style.display!=='none').map(e=>{const v=a.DATA.markers.find(x=>x.place_key===e.dataset.placeKey),p=m.project([v.lon,v.lat]),b=e.getBoundingClientRect();return Math.hypot(b.left+b.width/2-r.left-p.x,b.top+b.height/2-r.top-p.y)})}"""
    drift = page.evaluate(drift_expr)
    result["max_marker_drift_px"] = round(max(drift), 3)
    check("marker_drift_under_one_px", max(drift) < 1, True)
    for step in range(6):
        page.evaluate("step=>{const m=window.__tripApp.map();m.panBy([17,-11],{duration:0});m.jumpTo({zoom:11.4+(step%2)*.5})}", step)
    page.wait_for_timeout(350)
    check("one_canvas_after_pan_zoom", page.locator(".maplibregl-canvas").count(), 1)
    check("marker_drift_after_pan_zoom_under_one_px", max(page.evaluate(drift_expr)) < 1, True)
    for width in (1440, 1280, 1024, 768, 430, 390):
        page.set_viewport_size({"width": width, "height": 900 if width >= 768 else 844})
        page.wait_for_timeout(250)
        check(f"resize_{width}_no_overflow", page.evaluate("document.documentElement.scrollWidth<=innerWidth"), True)
        check(f"resize_{width}_one_canvas", page.locator(".maplibregl-canvas").count(), 1)
        check(f"resize_{width}_marker_drift_under_one_px", max(page.evaluate(drift_expr)) < 1, True)
    browser.close()

check("no_remote_photo_requests", result["remote_photo_requests"], [])
result["passed"] = sum(x["pass"] for x in result["checks"].values())
result["total"] = len(result["checks"])
result["status"] = "PASS" if result["passed"] == result["total"] and not result["errors"] else "FAIL"
(OUT / "p0_independent.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"status": result["status"], "passed": result["passed"], "total": result["total"], "details": len(result["detail_reviews"]), "max_marker_drift_px": result.get("max_marker_drift_px"), "errors": result["errors"]}, ensure_ascii=False, indent=2))
