"""Browser evidence for the current single-route Day → Place decision surface."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from qa_config import MODULAR_URL
from qa_evidence import ROOT, bind_report, candidate_identity

sys.path.insert(0, str(ROOT / "scripts"))
from validate_trip_data import active_route_contract_failures  # noqa: E402


OUT = ROOT / "QA" / "CHG-188" / "route_surface.json"
SCREENSHOTS = ROOT / "QA" / "CHG-188" / "screenshots"
DATA = json.loads((ROOT / "data/phase7_app_data.json").read_text())
I18N = json.loads((ROOT / "data/translations.json").read_text())
ROUTE_IDS = sorted(DATA["routes"])
report = bind_report({"schema_version": 2, "status": "FAIL", "route_ids": ROUTE_IDS, "screenshots": [], "desktop": {}, "mobile": {}, "negative_controls": {}, "errors": []}, candidate_identity())


def snapshot(page, name, viewport):
    path = SCREENSHOTS / f"{name}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(path), full_page=True)
    entry = {"path": str(path.relative_to(ROOT)), "candidate": report["candidate"], "candidate_tree": report["candidate_tree"], "browser": "chromium", "viewport": f"{viewport[0]}x{viewport[1]}", "language": page.evaluate("document.documentElement.lang"), "theme": page.evaluate("document.documentElement.dataset.theme"), "state": name}
    report["screenshots"].append(entry)
    return entry["path"]


def audit_dom(page):
    return page.evaluate(
        """() => {
          const a=window.__tripApp, dataRoutes=Object.keys(a.DATA.routes||{}), active=new Set(dataRoutes);
          const routeAttrs=[...document.querySelectorAll('[data-route],[data-compare-route]')].map(el=>el.dataset.route||el.dataset.compareRoute).filter(Boolean);
          const refs=new Set([...a.DATA.markers.flatMap(m=>[...(m.routes||[]),...(m.occurrences||[]).map(o=>o.route)]),...a.DATA.timeline.flatMap(t=>t.routes||[]),...a.DATA.legs.flatMap(l=>l.routes||[])]);
          const stale=[...new Set([...routeAttrs,...refs])].filter(route=>!active.has(route));
          const comparisonCount=document.querySelectorAll('[data-compare-route],#comparePanel,.route-compare,.route-membership,.membership-cell,.inspector-membership').length;
          const visibleText=document.body.innerText||'';
          const legacyRouteLabels=[...new Set(visibleText.match(/\bRoute [BCDE]\b/g)||[])];
          return {dataRoutes,routeAttrs,routeReferences:[...refs],stale,legacyRouteLabels,comparisonCount,routeCards:document.querySelectorAll('#routeCards .route-card').length,routeControls:document.querySelectorAll('#routeCards [data-route],#recommendation [data-route]').length};
        }"""
    )


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.set_default_timeout(30000)
    page.on("pageerror", lambda error: report["errors"].append(str(error)))
    page.goto(MODULAR_URL, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_function("window.__tripApp?.map()?.isStyleLoaded()", timeout=30000)
    page.wait_for_function("window.__tripApp?.state?.runtime?.mapVisualReady", timeout=30000)

    meta = DATA["routes"][ROUTE_IDS[0]]
    korean_title = I18N.get("en_to_ko", {}).get(meta["title"], meta["title"])
    report["desktop"]["decide"] = {"title_visible": meta["title"] in page.locator("#recommendation").inner_text() or korean_title in page.locator("#recommendation").inner_text(), "route_card_count": page.locator("#routeCards .route-card").count(), "decision_cells": page.locator("#recommendation .decision-cell").count(), "route_code": page.locator("#recommendation .route-code").first.inner_text(), "comparison_chrome": page.locator("[data-compare-route],#comparePanel,.route-compare,.route-membership,.membership-cell").count()}
    snapshot(page, "single_route_decide_1440x900", (1440, 900))
    page.locator('[data-mode="day"]').click()
    page.locator("#dateSelect").select_option("10/5")
    report["desktop"]["day"] = {"visible": page.locator("#dayView").is_visible(), "contains_pier39": "PIER 39" in page.locator("#dayPlan").inner_text(), "contains_fortune": "Fortune" in page.locator("#dayPlan").inner_text(), "contains_ghirardelli": "Ghirardelli" in page.locator("#dayPlan").inner_text(), "contains_recovery": "회복" in page.locator("#dayPlan").inner_text() or "recovery" in page.locator("#dayPlan").inner_text().lower()}
    snapshot(page, "single_route_day_1005_1440x900", (1440, 900))
    page.set_viewport_size({"width": 390, "height": 844})
    page.locator("#dateSelect").select_option("all")
    page.locator('[data-mode="place"]').click()
    page.wait_for_selector("#placeView:not([hidden]) .place-list-item")
    report["mobile"] = {"overflow": page.evaluate("document.documentElement.scrollWidth-innerWidth"), "role_badges": page.locator("#placeInspector .place-role").count(), "matrix_chrome": page.locator(".route-membership,.membership-cell,.inspector-membership,[data-compare-route],#comparePanel").count()}
    snapshot(page, "single_route_place_390x844", (390, 844))
    report["dom_audit"] = audit_dom(page)

    # Negative control: stale multi-route runtime payload must fail the route-set oracle.
    report["negative_controls"]["stale_route_data"] = {
        route: active_route_contract_failures(set(ROUTE_IDS) | {route}, set(ROUTE_IDS), set(ROUTE_IDS), set(ROUTE_IDS) | {route})
        for route in ("B", "C", "D", "E")
    }
    # Negative control: every retired route label/selector must be visible to the UI oracle.
    report["negative_controls"]["route_ui_leaks"] = {}
    for route in ("B", "C", "D", "E"):
        leak_result = page.evaluate("""route => {const el=document.createElement('button');el.dataset.route=route;el.textContent=`Route ${route}`;document.body.append(el);const attrs=[...document.querySelectorAll('[data-route]')].map(x=>x.dataset.route);const labels=[...new Set((document.body.innerText||'').match(/\\bRoute [BCDE]\\b/g)||[])];const leaked={attrs:attrs.includes(route),labels:labels.includes(`Route ${route}`)};el.remove();return {...leaked,failed:leaked.attrs&&leaked.labels}}""", route)
        report["negative_controls"]["route_ui_leaks"][route] = leak_result
    browser.close()

active = report["dom_audit"]
route_set_ok = ROUTE_IDS == ["A"] and report["desktop"]["decide"]["title_visible"] and report["desktop"]["decide"]["route_card_count"] == 1 and report["desktop"]["decide"]["decision_cells"] == 4
decide_ok = report["desktop"]["decide"]["comparison_chrome"] == 0
day_ok = report["desktop"]["day"]["visible"] and all(report["desktop"]["day"][key] for key in ("contains_pier39", "contains_fortune", "contains_ghirardelli"))
mobile_ok = report["mobile"]["overflow"] == 0 and report["mobile"]["role_badges"] == len(DATA["markers"]) and report["mobile"]["matrix_chrome"] == 0
single_route_ui_ok = active["dataRoutes"] == ROUTE_IDS and not active["stale"] and not active["legacyRouteLabels"] and active["comparisonCount"] == 0 and active["routeCards"] == 1
negatives_ok = all(bool(report["negative_controls"]["stale_route_data"][route]) for route in ("B", "C", "D", "E")) and all(report["negative_controls"]["route_ui_leaks"][route]["failed"] for route in ("B", "C", "D", "E"))
report["checks"] = {"configured_single_route": route_set_ok, "decision_surface_has_no_compare_chrome": decide_ok, "day_place_must_items_visible": day_ok, "mobile_place_roles_and_reflow": mobile_ok, "no_active_route_leakage": single_route_ui_ok, "stale_data_and_ui_negative_controls_rejected": negatives_ok, "candidate_screenshots_bound": len(report["screenshots"]) == 3}
report["status"] = "PASS" if not report["errors"] and all(report["checks"].values()) else "FAIL"
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"status": report["status"], "checks": report["checks"], "screenshots": report["screenshots"], "errors": report["errors"]}, ensure_ascii=False, indent=2))
raise SystemExit(0 if report["status"] == "PASS" else 1)
