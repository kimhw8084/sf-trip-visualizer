"""Candidate-bound browser QA for CHG-232 operations and cost/readiness."""

from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

from qa_config import MODULAR_URL
from qa_evidence import ROOT, bind_report, candidate_identity
import security_privacy


OUT = ROOT / "QA" / "CHG-232" / "location_gap"
OUT.mkdir(parents=True, exist_ok=True)
CANONICAL_DATA = json.loads((ROOT / "data" / "phase7_app_data.json").read_text())
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


def render_day(page, date_key):
    page.evaluate(
        """async date=>{const a=window.__tripApp;a.state.task.date=date;a.state.task.region='overall';a.state.task.selected=null;a.setMode('day');await a.drawMap(false)}""",
        date_key,
    )
    return page.locator("#dayPlan").inner_text()


def compact_travel_contract(page, expected_rows):
    return page.evaluate(
        """expected => {
          const toggles=[...document.querySelectorAll('#dayPlan [data-travel-details-toggle]')];
          const rows=[...document.querySelectorAll('#dayPlan .plan-travel')];
          const audit=['static schedule plan','no independent reference','schedule-derived','independent baseline','source confidence','basis and source','method:','freshness','confidence'];
          const texts=rows.map(row=>row.innerText.toLowerCase());
          const allCollapsed=toggles.every(button=>{
            const region=document.getElementById(button.getAttribute('aria-controls'));
            return button.getAttribute('aria-expanded')==='false' && region?.hidden===true;
          });
          const liveNavigationCues=rows.map(row=>row.innerText).join('\\n').split('Check live navigation before leaving').length-1;
          return {
            travel_rows:rows.length,
            disclosure_buttons:toggles.length,
            all_collapsed:allCollapsed,
            live_navigation_cues:liveNavigationCues,
            audit_absent:!texts.some(text=>audit.some(term=>text.includes(term))),
            compact_default:rows.length===expected && toggles.length===expected && allCollapsed && liveNavigationCues>=expected && !texts.some(text=>audit.some(term=>text.includes(term)))
          };
        }""",
        expected_rows,
    )


def verify_travel_details(page, capture_name=None):
    button = page.locator("#dayPlan [data-travel-details-toggle]").first
    button_id = button.get_attribute("id")
    region_id = button.get_attribute("aria-controls")
    button.click()
    page.wait_for_function(
        """ids => {const b=document.getElementById(ids.button),r=document.getElementById(ids.region);return b?.getAttribute('aria-expanded')==='true' && r && !r.hidden}""",
        arg={"button": button_id, "region": region_id},
    )
    evidence = page.evaluate(
        """ids => {
          const button=document.getElementById(ids.button),region=document.getElementById(ids.region);
          const text=region.innerText.toLowerCase();
          const expected=['planning vs live navigation','schedule-derived range','separate buffer','independent baseline','confidence','method','basis and source','freshness','privacy classification'];
          return {
            expanded:button?.getAttribute('aria-expanded')==='true',
            owned:button?.getAttribute('aria-controls')===region?.id && region?.getAttribute('aria-labelledby')===button?.id,
            focus_preserved:document.activeElement===button,
            evidence_fields:Object.fromEntries(expected.map(term=>[term,text.includes(term)])),
            day_context:!!document.querySelector('#dayHeader')?.innerText && !!document.querySelector('#dayPlan [data-day-place]')?.innerText,
            text:region?.innerText||''
          };
        }""",
        {"button": button_id, "region": region_id},
    )
    evidence["evidence_complete"] = all(evidence["evidence_fields"].values())
    if capture_name:
        capture(page, capture_name)
    button.click()
    page.wait_for_function(
        """ids => {const b=document.getElementById(ids.button),r=document.getElementById(ids.region);return b?.getAttribute('aria-expanded')==='false' && r?.hidden===true}""",
        arg={"button": button_id, "region": region_id},
    )
    evidence["collapse_restored"] = (
        page.locator(f"#{button_id}").get_attribute("aria-expanded") == "false"
        and page.evaluate("id => document.activeElement?.id === id", button_id)
    )
    return evidence


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
          return {routes:Object.keys(d.routes),places:d.markers.length,timeline:d.timeline.length,legs:d.legs.length,travelRanges:(d.travel_ranges||[]).length,dates:d.dates.map(x=>x.key),removed:[...removed].filter(k=>d.markers.some(m=>m.place_key===k)),newPhysical:['cantor_arts','rodin_garden','stanford_quad','baker_beach','aquatic_park','alamo_square','carmel_beach'].filter(k=>!d.markers.some(m=>m.place_key===k)),nonphoto:(d.non_photo_itinerary_identities||[]).map(x=>x.key),dayFacts:document.querySelector('#dayHeader').innerText}}"""
    )
    report["checks"]["oct5_order"] = page.evaluate(
        """()=>{const keys=[...document.querySelectorAll('#dayPlan [data-day-place]')].map(x=>x.dataset.dayPlace);const order=['alcatraz','pier39','ghirardelli','aquatic_park','cable_car','lombard','north_beach','fortune','chinatown'];return {keys,ordered:order.every((k,i)=>keys.indexOf(k)>=0&&(i===0||keys.indexOf(order[i-1])<keys.indexOf(k))),facts:document.querySelector('#dayHeader').innerText}}"""
    )
    capture(page, "cost_readiness_1440_ko_light_day")

    page.locator("#langToggle").click()
    page.wait_for_function("document.documentElement.lang==='en'")
    day_contracts = {}
    for date_key in ("10/4", "10/6"):
        day_text = render_day(page, date_key)
        travel_rows = [
            item for item in CANONICAL_DATA["timeline"]
            if item.get("date_key") == date_key and item.get("kind") == "travel"
        ]
        expected_cues = len(travel_rows)
        actual_cues = day_text.count("Static schedule plan:")
        actual_rechecks = day_text.count("Check live navigation before leaving")
        compact_contract = compact_travel_contract(page, expected_cues)
        day_contracts[date_key] = {
            "travel_rows": expected_cues,
            "static_plan_cues": actual_cues,
            "live_navigation_cues": actual_rechecks,
            "disclosure_buttons": compact_contract["disclosure_buttons"],
            "all_details_collapsed": compact_contract["all_collapsed"],
            "audit_absent_by_default": compact_contract["audit_absent"],
            "compact_default_scan": compact_contract["compact_default"],
        }
        if date_key == "10/4":
            start = day_text.find("Golden Gate Bridge south-side overlook")
            end = day_text.find("Mill Valley lodging", start + 1)
            day_contracts[date_key]["return_row_visible_and_ordered"] = start >= 0 and end > start
            report["checks"]["oct4_return_row"] = day_contracts[date_key]["return_row_visible_and_ordered"]
            capture(page, "oct4_day_1440_en_light")
        else:
            sequence = (
                "Monterey Bay Aquarium → Stage Coach Lodge",
                "Stage Coach Lodge check-in and reset",
                "Stage Coach Lodge → Old Fisherman’s Wharf",
                "Old Fisherman's Wharf",
                "Old Fisherman’s Wharf → Stage Coach Lodge",
            )
            positions = [day_text.find(label) for label in sequence]
            day_contracts[date_key]["separate_places_and_movements_in_order"] = all(
                position >= 0 for position in positions
            ) and positions == sorted(positions)
            report["checks"]["oct6_place_sequence"] = day_contracts[date_key]["separate_places_and_movements_in_order"]
            capture(page, "oct6_day_1440_en_light")
        if date_key == "10/4":
            evidence = verify_travel_details(page, "oct4_travel_details_expanded_1440_en_light")
            report["checks"]["1004_travel_details_evidence"] = (
                evidence["expanded"]
                and evidence["owned"]
                and evidence["focus_preserved"]
                and evidence["evidence_complete"]
                and evidence["day_context"]
                and evidence["collapse_restored"]
            )
            day_contracts[date_key]["expanded_evidence"] = evidence
        page.locator(".workbench-scroll").evaluate("e=>e.scrollTop=e.scrollHeight")
        page.wait_for_timeout(100)
        scrolled_to_end = page.locator(".workbench-scroll").evaluate(
            "e=>Math.ceil(e.scrollTop+e.clientHeight)>=e.scrollHeight"
        )
        date_id = f"10{int(date_key.split('/')[1]):02d}"
        report["checks"][f"{date_id}_desktop_rows_scrolled_into_view"] = scrolled_to_end
        capture(page, f"oct{date_key.split('/')[1]}_day_rows_1440_en_light")
        page.locator(".workbench-scroll").evaluate("e=>e.scrollTop=0")
        date_id = f"10{int(date_key.split('/')[1]):02d}"
        report["checks"][f"{date_id}_compact_default"] = day_contracts[date_key]["compact_default_scan"]
    report["checks"]["rendered_day_contracts"] = day_contracts
    render_day(page, "10/5")

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
    page.locator("#costCockpitClose").click()
    if page.locator("html").get_attribute("lang") != "en":
        page.locator("#langToggle").click()
        page.wait_for_function("document.documentElement.lang==='en'")
    page.locator("#openCostCockpit").click()
    page.wait_for_function("document.querySelector('#costCockpit')?.open && document.querySelector('#costScenarioSelect')?.value==='us_resident_annual_pass'")
    report["checks"]["english_and_state"] = page.evaluate(
        """()=>({heading:document.querySelector('#costCockpitHeading').innerText,lowerBound:document.querySelector('.cost-scenario h3').innerText,booked:document.querySelector('[data-readiness-status="alcatraz"]').value,hangul:(document.querySelector('#costCockpitContent').innerText.match(/[가-힣]/g)||[]).length})"""
    )
    page.locator("#costCockpitClose").click()
    page.locator("#themeToggle").click()
    page.wait_for_function("document.documentElement.dataset.theme==='dark'")
    page.locator("#openCostCockpit").click()
    page.wait_for_function("document.querySelector('#costCockpit')?.open && document.querySelector('#costScenarioSelect')?.value==='us_resident_annual_pass'")
    report["checks"]["state_after_theme"] = page.evaluate(
        """()=>({theme:document.documentElement.dataset.theme,booked:document.querySelector('[data-readiness-status="alcatraz"]').value,scenario:document.querySelector('#costScenarioSelect').value})"""
    )
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
    page.locator("#costCockpitClose").click()
    page.wait_for_function("!document.querySelector('#costCockpit').open")
    for date_key in ("10/4", "10/6"):
        render_day(page, date_key)
        travel_rows = [
            item for item in CANONICAL_DATA["timeline"]
            if item.get("date_key") == date_key and item.get("kind") == "travel"
        ]
        expected_cues = len(travel_rows)
        compact_contract = compact_travel_contract(page, expected_cues)
        date_id = f"10{int(date_key.split('/')[1]):02d}"
        report["checks"][f"{date_id}_mobile_compact_default"] = compact_contract["compact_default"]
        capture(page, f"oct{date_key.split('/')[1]}_day_390_en_dark_mobile")
        page.locator(".workbench-scroll").evaluate("e=>e.scrollTop=e.scrollHeight")
        page.wait_for_timeout(100)
        scrolled_to_end = page.locator(".workbench-scroll").evaluate(
            "e=>Math.ceil(e.scrollTop+e.clientHeight)>=e.scrollHeight"
        )
        report["checks"][f"{date_id}_mobile_rows_scrolled_into_view"] = scrolled_to_end
        capture(page, f"oct{date_key.split('/')[1]}_day_rows_390_en_dark_mobile")
        page.locator(".workbench-scroll").evaluate("e=>e.scrollTop=0")
    browser.close()

data = report["checks"]["runtime_contract"]
order = report["checks"]["oct5_order"]
initial = report["checks"]["cost_starts_unselected"]
status = report["checks"]["local_status_storage"]
english = report["checks"]["english_and_state"]
mobile = report["checks"]["mobile_sheet"]
report["checks"]["all_routes_and_places"] = (
    data["routes"] == list(CANONICAL_DATA["routes"])
    and data["routes"] == ["A"]
    and data["places"] == len(CANONICAL_DATA["markers"])
    and data["timeline"] == len(CANONICAL_DATA["timeline"])
    and data["legs"] == len(CANONICAL_DATA["legs"])
    and data["travelRanges"] == len(CANONICAL_DATA["travel_ranges"])
    and len(data["dates"]) == len(CANONICAL_DATA["dates"])
    and not data["removed"]
    and not data["newPhysical"]
    and {"gabrielson_park", "outpost", "valley_loop_walk", "sentinel_beach"} <= set(data["nonphoto"])
)
report["checks"]["final_day_content"] = order["ordered"] and "07:15" in order["facts"] and "13:45" in order["facts"]
report["checks"]["analysis_scenario_only"] = initial["scenario"] == "" and initial["lowerBound"] == "" and initial["localOnly"] and initial["alcatraz"]
report["checks"]["freshness_is_recheck_gated"] = report["checks"]["freshness_default"] == {"status": "RECHECK_REQUIRED", "rendered": "RECHECK_REQUIRED"} and report["checks"]["stale_fact_visible"] == "STALE"
report["checks"]["resident_lower_bound"] = "$652.80" in report["checks"]["scenario"]
report["checks"]["local_user_checklist"] = status["status"] == "user_marked_booked" and status["identity"] == "sf-family-2026-final" and status["scenario"] == "us_resident_annual_pass"
report["checks"]["language_theme_state"] = "Cost and readiness" in english["heading"] and "$652.80" in english["lowerBound"] and english["booked"] == "user_marked_booked" and english["hangul"] == 0
report["checks"]["readiness_state_survives_theme"] = report["checks"]["state_after_theme"] == {"theme": "dark", "booked": "user_marked_booked", "scenario": "us_resident_annual_pass"}
report["checks"]["escape_returns_focus"] = report["checks"]["focus_return"] == "openCostCockpit"
report["checks"]["mobile_reflow"] = mobile["overflow"] == 0 and mobile["visible"] and mobile["dialogWidth"] <= mobile["viewport"] + 1 and mobile["bottom"] <= 2
required_boolean_checks = (
    "visible_ui_privacy_cost_readiness_1440_ko_light_day",
    "visible_ui_privacy_cost_readiness_390_en_dark_mobile",
    "visible_ui_privacy_oct4_day_1440_en_light",
    "visible_ui_privacy_oct6_day_1440_en_light",
    "visible_ui_privacy_oct4_day_390_en_dark_mobile",
    "visible_ui_privacy_oct6_day_390_en_dark_mobile",
    "visible_ui_privacy_oct4_day_rows_1440_en_light",
    "visible_ui_privacy_oct6_day_rows_1440_en_light",
    "visible_ui_privacy_oct4_day_rows_390_en_dark_mobile",
    "visible_ui_privacy_oct6_day_rows_390_en_dark_mobile",
    "all_routes_and_places",
    "final_day_content",
    "oct4_return_row",
    "oct6_place_sequence",
    "1004_travel_details_evidence",
    "1004_compact_default",
    "1006_compact_default",
    "1004_mobile_compact_default",
    "1006_mobile_compact_default",
    "1004_desktop_rows_scrolled_into_view",
    "1006_desktop_rows_scrolled_into_view",
    "1004_mobile_rows_scrolled_into_view",
    "1006_mobile_rows_scrolled_into_view",
    "analysis_scenario_only",
    "freshness_is_recheck_gated",
    "resident_lower_bound",
    "local_user_checklist",
    "language_theme_state",
    "readiness_state_survives_theme",
    "escape_returns_focus",
    "mobile_reflow",
)
report["status"] = "PASS" if not report["errors"] and all(report["checks"].get(name) is True for name in required_boolean_checks) else "FAIL"
OUT.mkdir(parents=True, exist_ok=True)
(OUT / "location_gap_visuals.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"status": report["status"], "checks": report["checks"], "errors": report["errors"]}, ensure_ascii=False, indent=2))
raise SystemExit(0 if report["status"] == "PASS" else 1)
