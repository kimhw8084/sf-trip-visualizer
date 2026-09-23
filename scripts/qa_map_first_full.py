"""Full Chromium acceptance for the calm field atlas shell."""

import itertools
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

from qa_evidence import bind_report, candidate_identity
from qa_config import MODULAR_URL


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "QA" / "CHG-188" / "map_first_full"
OUT.mkdir(parents=True, exist_ok=True)
ROUTES = tuple(sorted(json.loads((ROOT / "data/phase7_app_data.json").read_text())["routes"]))
DATES = ("all", "10/3", "10/4", "10/5", "10/6", "10/7", "10/8", "10/9", "10/10", "10/11")
REGIONS = ("overall", "sf", "monterey", "yosemite")
report = bind_report(
    {"status": "FAIL", "checks": {}, "matrix": [], "screenshots": [], "errors": [], "console_errors": [], "failed_requests": []},
    candidate_identity(),
)


def check(name, passed, detail=None):
    report["checks"][name] = {"pass": bool(passed), "detail": detail}


def capture(page, name):
    path = OUT / f"{name}.png"
    page.screenshot(path=str(path), full_page=True)
    report["screenshots"].append(str(path.relative_to(ROOT)))


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True, timeout=90000)
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.set_default_timeout(30000)
    page.on("pageerror", lambda error: report["errors"].append(str(error)))
    page.on("console", lambda message: report["console_errors"].append(message.text[:500]) if message.type == "error" else None)
    page.on("requestfailed", lambda request: report["failed_requests"].append({"url": request.url, "failure": request.failure}))
    page.goto(MODULAR_URL, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_function("window.__tripApp?.map()?.isStyleLoaded()", timeout=30000)
    page.wait_for_function("document.querySelectorAll('.photo-marker').length===window.__tripApp.DATA.markers.length", timeout=15000)

    check("shell_ready", page.locator("#workbench").count() == 1 and page.locator("#map").count() == 1)
    check("no_artificial_splash", page.locator("#loadingScreen").count() == 0)
    check("initial_recommendation", ROUTES[0] in page.locator("#recommendation").inner_text() and page.locator("#recommendation .decision-cell").count() == 4)
    check("configured_route_cards", page.locator("#routeCards .route-card").count() == len(ROUTES))
    check("single_route_has_no_comparison_chrome", page.locator("[data-compare-route],#comparePanel,.route-compare,.route-membership,.membership-cell").count() == 0)
    capture(page, "default_1440_ko_light")

    page.locator('[data-mode="day"]').click()
    page.locator("#dateSelect").select_option("10/8")
    dense = page.locator("#dayPlan").inner_text()
    page.locator("#dateSelect").select_option("10/9")
    sparse_nonspatial = page.locator("#dayPlan .plan-card").count()
    check("day_semantics_and_nonspatial_content", any(word in dense for word in ("필수", "핵심", "회복", "택1", "조건부")) and sparse_nonspatial > 0)
    check("single_date_authority", page.locator("#dateSelect").count() == 1 and page.locator(".day-picker").count() == 1)
    page.locator("#dateSelect").select_option("10/8")
    capture(page, "day_1008_1440")

    page.locator(".photo-marker").first.click()
    page.wait_for_selector("#peek.show")
    check("peek_single_overlay", page.locator("#peek.show").count() == 1 and page.locator("#peek [data-peek-open]").count() == 1)
    page.locator("#peek [data-peek-open]").evaluate("element=>element.click()")
    page.wait_for_function("window.__tripApp.state.presentation.mode==='place'")
    check("place_inspector_three_roles", page.locator("#placeInspector .photo-slot img").count() == 3 and page.locator("#placeInspector .place-glance").count() == 1)
    page.locator("[data-place-back]").click()
    check("place_returns_to_day", page.evaluate("window.__tripApp.state.presentation.mode") == "day" and page.locator("#dateSelect").input_value() == "10/8")
    capture(page, "place_inspector_1440")

    # Exercise nonempty state combinations without retaining the old duplicate UI.
    route_sets = tuple(dict.fromkeys((ROUTES, *((route,) for route in ROUTES))))
    for routes, date, region in itertools.product(route_sets, ("all", "10/8", "10/9"), ("overall", "sf", "monterey", "yosemite")):
        result = page.evaluate(
            """async ({routes,date,region})=>{const a=window.__tripApp,s=a.state.task;s.routes=new Set(routes);s.primaryRoute=routes[0];s.date=date;s.region=region;s.selected=null;a.setMode('day');await a.drawMap(false);const expected=a.DATA.markers.filter(a.markerVisible).length,actual=document.querySelectorAll('.photo-marker').length,features=a.visibleRouteFeatures(),fail=[];if(actual!==expected)fail.push('markers');if(document.querySelectorAll('.maplibregl-canvas').length!==1)fail.push('canvas');if(document.documentElement.scrollWidth>innerWidth)fail.push('overflow');if(date!=='all'&&features.some(f=>f.properties.date!==date))fail.push('cross_date_route');if([...s.routes].some(route=>!Object.keys(a.DATA.routes).includes(route)))fail.push('route_set');return {routes,date,region,markers:actual,expected,features:features.length,failures:fail}}""",
            {"routes": routes, "date": date, "region": region},
        )
        report["matrix"].append(result)

    page.locator("#langToggle").click()
    page.wait_for_function("document.documentElement.lang==='en'")
    page.locator('[data-mode="decide"]').click()
    check("english_critical_surface", all(text in page.locator("body").inner_text() for text in ("Decide", "Day", "Place", "Route strategy")))
    page.locator("#themeToggle").click()
    check("dark_tokens_applied", page.evaluate("document.documentElement.dataset.theme==='dark'"))
    capture(page, "english_dark_1440")

    # Optional Satellite failure must leave the local plan usable and stateful.
    page.locator('[data-mode="day"]').click()
    page.locator("#dateSelect").select_option("10/8")
    page.route("https://server.arcgisonline.com/**", lambda route: route.abort())
    page.evaluate("window.__tripApp.chooseProvider('satellite')")
    page.wait_for_timeout(3500)
    failure = page.evaluate("()=>({provider:window.__tripApp.state.provider,date:window.__tripApp.state.date,mode:window.__tripApp.state.presentation.mode,error:!document.getElementById('mapError').hidden,smart:window.__tripApp.state.providerHealth.vector})")
    check("satellite_failure_preserves_plan", failure["provider"] == "vector" and failure["date"] == "10/8" and failure["error"] and failure["smart"] in ("ready", "failed"), failure)
    page.unroute("https://server.arcgisonline.com/**")

    page.set_viewport_size({"width": 390, "height": 844})
    page.wait_for_timeout(300)
    check("mobile_reflow", page.evaluate("document.documentElement.scrollWidth<=innerWidth") and page.locator("#workbench[data-sheet]").count() == 1)
    page.locator('[data-sheet="compact"]').click()
    check("mobile_compact_reachable", page.locator('#workbench[data-sheet="compact"]').count() == 1)
    page.locator('[data-sheet="expanded"]').click()
    check("mobile_expanded_reachable", page.locator('#workbench[data-sheet="expanded"]').count() == 1)
    capture(page, "mobile_expanded_390")
    browser.close()

report["matrix_failures"] = [row for row in report["matrix"] if row["failures"]]
def expected_network_event(row):
    url = row["url"]
    return "server.arcgisonline.com" in url or (
        url.endswith("/assets/vector/sf_trip.pmtiles") and row["failure"] == "net::ERR_ABORTED"
    )


expected_network_events = [row for row in report["failed_requests"] if expected_network_event(row)]
unexpected_network_events = [row for row in report["failed_requests"] if not expected_network_event(row)]
intentional_provider_failure = any("server.arcgisonline.com" in row["url"] for row in expected_network_events)
expected_resource_console = "Failed to load resource: net::ERR_FAILED"
unexpected_console_errors = [
    message
    for message in report["console_errors"]
    if message != expected_resource_console or not intentional_provider_failure
]
report["expected_network_events"] = expected_network_events
report["unexpected_network_events"] = unexpected_network_events
report["unexpected_console_errors"] = unexpected_console_errors
report["status"] = "PASS" if not report["errors"] and not unexpected_console_errors and not unexpected_network_events and all(row["pass"] for row in report["checks"].values()) and not report["matrix_failures"] else "FAIL"
(OUT / "full_acceptance.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"status": report["status"], "checks": report["checks"], "matrix_states": len(report["matrix"]), "matrix_failures": len(report["matrix_failures"]), "errors": report["errors"]}, ensure_ascii=False, indent=2))
raise SystemExit(0 if report["status"] == "PASS" else 1)
