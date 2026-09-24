"""Candidate-bound browser QA for CHG-204 operations and cost/readiness."""

from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

from qa_config import MODULAR_URL
from qa_evidence import ROOT, bind_report, candidate_identity
import security_privacy


OUT = ROOT / "QA" / "CHG-204" / "location_gap"
OUT.mkdir(parents=True, exist_ok=True)
report = bind_report({"status": "FAIL", "checks": {}, "screenshots": [], "errors": []}, candidate_identity())


def capture(page, name):
    findings = security_privacy.scan_text(page.locator("body").inner_text(), "active rendered UI")
    key = f"visible_ui_privacy_{name}"
    report["checks"][key] = not findings
    if findings:
        report["errors"].append("visible UI privacy scan failed; screenshot was withheld")
        return
    path = OUT / f"{name}.png"
    page.screenshot(path=str(path), full_page=True)
    report["screenshots"].append(str(path.relative_to(ROOT)))


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()
    page.set_default_timeout(30000)
    page.on("pageerror", lambda error: report["errors"].append("browser page error"))
    page.goto(MODULAR_URL, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_function("window.__tripApp?.map()?.isStyleLoaded()", timeout=30000)
    page.evaluate(
        """async()=>{const a=window.__tripApp;a.state.task.date='10/5';a.state.task.region='overall';a.state.task.selected=null;a.setMode('day');await a.drawMap(false)}"""
    )
    report["checks"]["runtime_contract"] = page.evaluate(
        """()=>{const a=window.__tripApp,d=a.DATA,removed=new Set(['bay_lights','exploratorium','musee','academy','coit','bixby','mariposa']);
          return {routes:Object.keys(d.routes),places:d.markers.length,timeline:d.timeline.length,legs:d.legs.length,dates:d.dates.map(x=>x.key),removed:[...removed].filter(k=>d.markers.some(m=>m.place_key===k)),newPhysical:['cantor_arts','rodin_garden','stanford_quad','baker_beach','aquatic_park','alamo_square','carmel_beach'].filter(k=>!d.markers.some(m=>m.place_key===k)),nonphoto:(d.non_photo_itinerary_identities||[]).map(x=>x.key),dayFacts:document.querySelector('#dayHeader').innerText}}"""
    )
    report["checks"]["oct5_order"] = page.evaluate(
        """()=>{const keys=[...document.querySelectorAll('#dayPlan [data-day-place]')].map(x=>x.dataset.dayPlace);const order=['alcatraz','pier39','ghirardelli','aquatic_park','cable_car','lombard','north_beach','fortune','chinatown'];return {keys,ordered:order.every((k,i)=>keys.indexOf(k)>=0&&(i===0||keys.indexOf(order[i-1])<keys.indexOf(k))),facts:document.querySelector('#dayHeader').innerText}}"""
    )
    capture(page, "cost_readiness_1440_ko_light_day")

    page.locator("#openCostCockpit").click()
    page.wait_for_function("document.querySelector('#costCockpit')?.open")
    report["checks"]["cost_starts_unselected"] = page.evaluate(
        """()=>({dialog:document.querySelector('#costCockpit').getAttribute('aria-labelledby'),scenario:document.querySelector('#costScenarioSelect').value,lowerBound:document.querySelector('.cost-scenario h3')?.innerText||'',localOnly:document.querySelector('.local-only')?.innerText||'',alcatraz:!!document.querySelector('[data-readiness-status="alcatraz"]')})"""
    )
    report["checks"]["freshness_default"] = page.evaluate(
        """()=>{const item=document.querySelector('[data-readiness-status="alcatraz"]');const record=window.TRIP_FRESHNESS?.records?.find(x=>x.fact_id==='alcatraz_first_departure');return {status:record?.status,rendered:item?.closest('.readiness-card')?.querySelector('[data-freshness-status]')?.dataset.freshnessStatus}}"""
    )
    page.evaluate("""()=>{const r=window.TRIP_FRESHNESS.records.find(x=>x.fact_id==='alcatraz_first_departure');r.status='STALE';window.__tripApp.setMode('day')}""")
    report["checks"]["stale_fact_visible"] = page.locator('[data-readiness-status="alcatraz"]').evaluate("e=>e.closest('.readiness-card').querySelector('[data-freshness-status]')?.dataset.freshnessStatus")
    page.evaluate("""()=>{const r=window.TRIP_FRESHNESS.records.find(x=>x.fact_id==='alcatraz_first_departure');r.status='RECHECK_REQUIRED';window.__tripApp.setMode('day')}""")
    page.locator("#costScenarioSelect").select_option("us_resident_annual_pass")
    report["checks"]["scenario"] = page.locator(".cost-scenario h3").inner_text()
    page.locator('[data-readiness-status="alcatraz"]').select_option("user_marked_booked")
    report["checks"]["local_status_storage"] = page.evaluate(
        """()=>{const v=JSON.parse(localStorage.getItem(window.TRIP_ATLAS_STATE.storageKey)||'{}');return {status:v.readiness?.alcatraz||null,identity:v.tripIdentity||null,scenario:v.costScenario||null}}"""
    )
    page.locator("#langToggle").click()
    page.wait_for_function("document.documentElement.lang==='en'")
    page.wait_for_function("document.querySelector('#costCockpit')?.open && document.querySelector('#costScenarioSelect')?.value==='us_resident_annual_pass'")
    report["checks"]["english_and_state"] = page.evaluate(
        """()=>({heading:document.querySelector('#costCockpitHeading').innerText,lowerBound:document.querySelector('.cost-scenario h3').innerText,booked:document.querySelector('[data-readiness-status="alcatraz"]').value,hangul:(document.querySelector('#costCockpitContent').innerText.match(/[가-힣]/g)||[]).length})"""
    )
    page.locator("#themeToggle").click()
    page.wait_for_function("document.documentElement.dataset.theme==='dark'")
    report["checks"]["keyboard_close"] = page.evaluate("""()=>{document.querySelector('#costCockpitClose').focus();return document.activeElement.id}""")
    page.keyboard.press("Escape")
    page.wait_for_function("!document.querySelector('#costCockpit').open")
    page.wait_for_timeout(50)
    report["checks"]["focus_return"] = page.evaluate("document.activeElement?.id||null")
    page.set_viewport_size({"width": 390, "height": 844})
    page.locator("#openCostCockpit").click()
    page.wait_for_function("document.querySelector('#costCockpit')?.open")
    report["checks"]["mobile_sheet"] = page.evaluate(
        """()=>{const d=document.querySelector('#costCockpit'),r=d.getBoundingClientRect(),s=d.querySelector('.cost-cockpit-panel');return {overflow:document.documentElement.scrollWidth-innerWidth,bottom:Math.abs(r.bottom-innerHeight),visible:s.clientHeight>0,dialogWidth:r.width,viewport:innerWidth}}"""
    )
    capture(page, "cost_readiness_390_en_dark_mobile")
    browser.close()

data = report["checks"]["runtime_contract"]
order = report["checks"]["oct5_order"]
initial = report["checks"]["cost_starts_unselected"]
status = report["checks"]["local_status_storage"]
english = report["checks"]["english_and_state"]
mobile = report["checks"]["mobile_sheet"]
report["checks"]["all_routes_and_places"] = data["routes"] == ["A"] and data["places"] == 39 and data["timeline"] == 77 and data["legs"] == 32 and len(data["dates"]) == 11 and not data["removed"] and not data["newPhysical"] and {"gabrielson_park", "outpost", "valley_loop_walk", "sentinel_beach"} <= set(data["nonphoto"])
report["checks"]["final_day_content"] = order["ordered"] and "07:15" in order["facts"] and "13:45" in order["facts"]
report["checks"]["analysis_scenario_only"] = initial["scenario"] == "" and initial["lowerBound"] == "" and initial["localOnly"] and initial["alcatraz"]
report["checks"]["freshness_is_recheck_gated"] = report["checks"]["freshness_default"] == {"status": "RECHECK_REQUIRED", "rendered": "RECHECK_REQUIRED"} and report["checks"]["stale_fact_visible"] == "STALE"
report["checks"]["resident_lower_bound"] = "$652.80" in report["checks"]["scenario"]
report["checks"]["local_user_checklist"] = status["status"] == "user_marked_booked" and status["identity"] == "sf-family-2026-final" and status["scenario"] == "us_resident_annual_pass"
report["checks"]["language_theme_state"] = "Cost and readiness" in english["heading"] and "$652.80" in english["lowerBound"] and english["booked"] == "user_marked_booked" and english["hangul"] == 0
report["checks"]["escape_returns_focus"] = report["checks"]["focus_return"] == "openCostCockpit"
report["checks"]["mobile_reflow"] = mobile["overflow"] == 0 and mobile["visible"] and mobile["dialogWidth"] <= mobile["viewport"] + 1 and mobile["bottom"] <= 2
report["status"] = "PASS" if not report["errors"] and all(value is True for value in report["checks"].values()) else "FAIL"
OUT.mkdir(parents=True, exist_ok=True)
(OUT / "location_gap_visuals.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"status": report["status"], "checks": report["checks"], "errors": report["errors"]}, ensure_ascii=False, indent=2))
raise SystemExit(0 if report["status"] == "PASS" else 1)
