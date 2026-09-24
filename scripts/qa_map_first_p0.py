"""Independent CHG-157 checks for truth, photos, map identity, and Place ownership."""

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

from qa_config import MODULAR_URL


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "QA" / "CHG-188" / "map_first_p0"
OUT.mkdir(parents=True, exist_ok=True)
ACTIVE_ROUTE_IDS = sorted(json.loads((ROOT / "data/phase7_app_data.json").read_text())["routes"])
report = {"status": "FAIL", "checks": {}, "detail_reviews": [], "errors": [], "remote_photo_requests": []}
local_origin = MODULAR_URL.rsplit("/", 1)[0] + "/"


def check(name, actual, expected):
    report["checks"][name] = {"actual": actual, "expected": expected, "pass": actual == expected}


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.set_default_timeout(30000)
    page.on("pageerror", lambda error: report["errors"].append(str(error)))
    page.on(
        "request",
        lambda request: report["remote_photo_requests"].append(request.url)
        if "photo" in request.url.lower() and not request.url.startswith(local_origin)
        else None,
    )
    page.goto(MODULAR_URL, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_function("window.__tripApp?.map()?.isStyleLoaded()", timeout=30000)
    page.wait_for_function(
        "[...document.querySelectorAll('.photo-marker img')].every(x=>x.complete&&x.naturalWidth>0)",
        timeout=15000,
    )

    expected_places = page.evaluate("window.__tripApp.DATA.markers.length")
    expected_route_markers = page.evaluate("ids=>window.__tripApp.DATA.markers.filter(m=>m.routes.some(r=>ids.includes(r))).length", ACTIVE_ROUTE_IDS)
    check("active_route_marker_objects", page.locator(".photo-marker").count(), expected_route_markers)
    check("active_route_marker_place_keys_unique", page.locator(".photo-marker").evaluate_all("xs=>new Set(xs.map(x=>x.dataset.placeKey)).size"), expected_route_markers)
    check("all_marker_hero_thumbs_decode", page.locator(".photo-marker img").evaluate_all("xs=>xs.every(x=>x.complete&&x.naturalWidth>0)"), True)
    check("configured_route_layers_present", page.evaluate("ids=>ids.every(r=>!!window.__tripApp.map().getLayer('trip-local-'+r))", ACTIVE_ROUTE_IDS), True)
    check("provider_controls_are_single_owner", page.locator("#providerControls [data-provider]").count(), 2)
    check("date_control_is_single_owner", page.locator("#dateSelect").count(), 1)
    check("legacy_surface_absence", page.locator("#dateRibbon,#mapSchedule,#mapFocus,#routeTip,#mobileDate,#mobileProvider,#previewCard,#detailsPane").count(), 0)

    page.locator('[data-mode="place"]').click()
    keys = page.evaluate("window.__tripApp.DATA.markers.map(x=>x.place_key)")
    for key in keys:
        page.evaluate("key=>{window.__tripApp.state.task.selected=key;window.__tripApp.setMode('place')}", key)
        page.wait_for_function("document.querySelectorAll('#placeInspector .photo-slot img').length===3")
        page.wait_for_function(
            "[...document.querySelectorAll('#placeInspector .photo-slot img')].every(x=>x.complete&&x.naturalWidth>0)",
            timeout=15000,
        )
        review = page.evaluate(
            """key=>{const a=window.__tripApp,marker=a.DATA.markers.find(x=>x.place_key===key);return {
              key, decoded:[...document.querySelectorAll('#placeInspector .photo-slot img')].every(x=>x.complete&&x.naturalWidth>0),
              occurrences:document.querySelectorAll('#placeInspector .occurrence').length,
              decisions:document.querySelectorAll('#placeInspector .decision-rule').length,
              whyNow:document.querySelector('#placeInspector .place-glance')?.innerText.includes('왜 지금') || document.querySelector('#placeInspector .place-glance')?.innerText.includes('Why now'),
              directions:document.querySelectorAll('#placeInspector .directions a').length,
              expectedDecisions:marker.decision_rules?.length||0,
              threeRoles:document.querySelectorAll('#placeInspector .photo-slot').length===3,
            }}""",
            key,
        )
        review["correct"] = review["decoded"] and review["threeRoles"] and review["whyNow"] and review["directions"] == 1 and review["decisions"] == review["expectedDecisions"]
        report["detail_reviews"].append(review)
    check("all_place_inspectors_complete", sum(row["correct"] for row in report["detail_reviews"]), expected_places)

    page.locator("#langToggle").click()
    page.wait_for_function("document.documentElement.lang==='en'")
    page.evaluate("()=>{window.__tripApp.state.task.selected='ferry';window.__tripApp.setMode('place')}")
    page.wait_for_function("document.querySelectorAll('#placeInspector .photo-slot img').length===3")
    english_hangul = page.evaluate("document.querySelector('#placeInspector').innerText.split('\\n').filter(x=>/[가-힣]/.test(x))")
    check("english_place_has_no_mixed_critical_copy", english_hangul, [])
    page.locator("#themeToggle").click()
    check("english_dark_mode", page.evaluate("document.documentElement.lang==='en'&&document.documentElement.dataset.theme==='dark'"), True)
    page.locator("#langToggle").click()
    check("korean_dark_mode", page.evaluate("document.documentElement.lang==='ko'&&document.documentElement.dataset.theme==='dark'"), True)

    page.set_viewport_size({"width": 390, "height": 844})
    page.wait_for_timeout(250)
    check("mobile_no_horizontal_overflow", page.evaluate("document.documentElement.scrollWidth<=innerWidth"), True)
    check("mobile_one_workbench", page.locator("#workbench").count(), 1)
    check("mobile_one_map_canvas", page.locator(".maplibregl-canvas").count(), 1)
    page.locator('[data-sheet="compact"]').click()
    check("mobile_compact_is_explicit", page.locator('#workbench[data-sheet="compact"]').count(), 1)
    page.locator('[data-sheet="expanded"]').click()
    check("mobile_expanded_is_explicit", page.locator('#workbench[data-sheet="expanded"]').count(), 1)
    browser.close()

check("no_remote_photo_requests", report["remote_photo_requests"], [])
report["passed"] = sum(row["pass"] for row in report["checks"].values())
report["total"] = len(report["checks"])
report["status"] = "PASS" if report["passed"] == report["total"] and not report["errors"] else "FAIL"
(OUT / "p0_independent.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"status": report["status"], "passed": report["passed"], "total": report["total"], "details": len(report["detail_reviews"]), "errors": report["errors"]}, ensure_ascii=False, indent=2))
raise SystemExit(0 if report["status"] == "PASS" else 1)
