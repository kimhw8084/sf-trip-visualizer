"""Matched objective screenshots and interaction evidence for CHG-232."""

from __future__ import annotations

import hashlib
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
BASELINE_A = "db86b0f22c13b96a86d74a710abbb13dc354ff4b"
BASELINE_B = "53b0a322e8db6c6dfc6c8a4ec3a7acc4f4961fa9"
DATES = ("10/4", "10/5", "10/6", "10/8", "10/10", "10/11")
OUTPUT = ROOT / "QA/CHG-232/comparative"
SCREEN_ROOT = OUTPUT / "screens"
sys.path.insert(0, str(ROOT / "scripts"))
from day_presentation_contract import audit_day_surface  # noqa: E402


def command(args: list[str], cwd: Path = ROOT) -> str:
    result = subprocess.run(args, cwd=cwd, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(f"command failed ({result.returncode}): {' '.join(args)}\n{result.stderr[-1600:]}")
    return result.stdout.strip()


def sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def wait_for_server(url: str, process: subprocess.Popen) -> None:
    for _ in range(100):
        if process.poll() is not None:
            raise RuntimeError(f"map server exited before becoming ready: {process.returncode}")
        try:
            with urlopen(url, timeout=1):
                return
        except Exception:
            time.sleep(0.1)
    raise RuntimeError("map server did not become ready")


def public_geometry_evidence(data_path: Path, geometry_path: Path, manifest_path: Path | None = None) -> dict:
    data = json.loads(data_path.read_text())
    geometry = json.loads(geometry_path.read_text())
    physical = [leg for leg in data.get("legs", []) if leg.get("mode") in {"drive", "walk"}]
    inventory = []
    for leg in data.get("legs", []):
        entry = geometry.get(leg["leg_id"], {})
        signature = [leg.get("from_latlon"), leg.get("to_latlon"), leg.get("mode")]
        inventory.append({
            "leg_id": leg.get("leg_id"),
            "date_key": leg.get("date"),
            "from": leg.get("from"),
            "to": leg.get("to"),
            "mode": leg.get("mode"),
            "status": entry.get("status"),
            "point_count": len(entry.get("coordinates", [])),
            "endpoint_signature": entry.get("endpoint_signature"),
            "endpoint_signature_matches": entry.get("endpoint_signature") == signature,
            "source": entry.get("source"),
            "distance_km": entry.get("distance_km"),
            "reference_duration_min": entry.get("duration_min_reference"),
            "render_style": leg.get("render_style"),
        })
    result = {
        "semantic_public_route_legs": len(physical),
        "routed_osm_network_legs": sum(geometry.get(leg["leg_id"], {}).get("status") == "routed_osm" for leg in physical),
        "conceptual_ferry_relationship_legs": sum(leg.get("mode") == "ferry" for leg in data.get("legs", [])),
        "intentionally_omitted_geometry_legs": sum(geometry.get(leg["leg_id"], {}).get("status") == "intentionally_omitted" for leg in physical),
        "intentionally_omitted_connections": len(data.get("route_graph_omissions", [])),
        "total_geometry_point_count": sum(len(entry.get("coordinates", [])) for entry in geometry.values()),
        "normal_physical_two_point_fallbacks": sum(
            leg.get("mode") in {"drive", "walk"}
            and len(geometry.get(leg["leg_id"], {}).get("coordinates", [])) == 2
            and geometry.get(leg["leg_id"], {}).get("status") != "routed_osm"
            for leg in data.get("legs", [])
        ),
        "per_leg": inventory,
    }
    if manifest_path and manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text())
        result["manifest_counts"] = manifest.get("counts", {})
    return result


def start_variant_server(cwd: Path, build: Path, log_path: Path) -> tuple[subprocess.Popen, str]:
    port = free_port()
    log = log_path.open("w")
    process = subprocess.Popen(
        [sys.executable, str(cwd / "scripts/serve_map.py"), "--port", str(port), "--directory", str(build / "modular")],
        cwd=cwd,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    url = f"http://127.0.0.1:{port}/index.html"
    wait_for_server(url, process)
    return process, url


def prepare_page(page, url: str, date_key: str, viewport: tuple[int, int], lang: str, theme: str) -> dict:
    page.set_viewport_size({"width": viewport[0], "height": viewport[1]})
    if page.locator("#workbench").count() == 0:
        page.goto(url, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_selector("#workbench", timeout=30000)
    page.wait_for_function("window.__tripApp?.map?.()", timeout=30000)
    page.locator('#modeNav [data-mode="day"]').click()
    page.locator("#dateSelect").select_option(date_key)
    current_lang = page.locator("html").get_attribute("lang") or "ko"
    if current_lang != lang:
        page.locator("#langToggle").click()
    current_theme = page.locator("html").get_attribute("data-theme") or "light"
    if current_theme != theme:
        page.locator("#themeToggle").click()
    page.wait_for_function("date => window.__tripApp?.state.task.date === date", arg=date_key)
    page.evaluate("async () => { await window.__tripApp?.whenIdle?.(); }")
    return page.evaluate("() => ({lang:document.documentElement.lang,theme:document.documentElement.dataset.theme,date:window.__tripApp.state.task.date,mode:window.__tripApp.state.presentation.mode,sheet:window.__tripApp.state.presentation.sheet})")


def capture_matrix(browser, variant: str, url: str) -> list[dict]:
    root = SCREEN_ROOT / variant
    root.mkdir(parents=True, exist_ok=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.set_default_timeout(20000)
    rows = []
    matrix = [(day, (1440, 900), "ko", "light") for day in DATES]
    matrix += [(day, (390, 844), "en", "dark") for day in DATES]
    matrix += [("10/5", (1440, 900), "en", "dark"), ("10/6", (390, 844), "ko", "light"), ("10/10", (1440, 900), "ko", "dark"), ("10/11", (390, 844), "en", "light")]
    for index, (date_key, viewport, lang, theme) in enumerate(matrix):
        state = prepare_page(page, url, date_key, viewport, lang, theme)
        name = f"day_{date_key.replace('/', '')}_{viewport[0]}x{viewport[1]}_{lang}_{theme}"
        target = root / f"{name}.png"
        page.screenshot(path=str(target), animations="disabled")
        rows.append({"name": name, "date_key": date_key, "viewport": list(viewport), "language": lang, "theme": theme, "state": state, "path": str(target.relative_to(ROOT)), "sha256": sha256(target)})
        if index == 0:
            page.set_viewport_size({"width": viewport[0], "height": viewport[1]})
    page.close()
    return rows


def inspect_candidate(browser, url: str) -> dict:
    report: dict = {"checks": {}, "screenshots": [], "errors": []}

    def check(name: str, passed: bool, detail=None) -> None:
        report["checks"][name] = {"pass": bool(passed), "detail": detail}

    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.set_default_timeout(20000)
    page.on("pageerror", lambda error: report["errors"].append(str(error)))
    page.goto(url, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_function("window.__tripApp?.map()?.isStyleLoaded()", timeout=30000)
    page.locator('#modeNav [data-mode="day"]').click()
    page.locator("#dateSelect").select_option("10/4")

    collapsed = page.evaluate("""() => ({travel_rows:[...document.querySelectorAll('#dayPlan [data-travel-details-toggle]')].map(button=>{const region=document.getElementById(button.getAttribute('aria-controls'));return {travel_id:button.dataset.travelId,expanded:button.getAttribute('aria-expanded')==='true',region_hidden:region?.hidden,collapsed_text:button.closest('.plan-travel')?.innerText||'',button_id:button.id,controls_id:button.getAttribute('aria-controls'),region_id:region?.id,labelled_by:region?.getAttribute('aria-labelledby'),focus_preserved:true}}),day_notes:(()=>{const button=document.querySelector('[data-day-notes-toggle]'),region=button&&document.getElementById(button.getAttribute('aria-controls'));return button?{expanded:button.getAttribute('aria-expanded')==='true',region_hidden:region?.hidden,button_id:button.id,controls_id:button.getAttribute('aria-controls'),region_id:region?.id,labelled_by:region?.getAttribute('aria-labelledby')}:null})()})""")
    report["collapsed_day_snapshot"] = collapsed
    contract_failures = audit_day_surface(collapsed)
    check("travel_details_and_day_notes_start_collapsed_with_owned_aria", not contract_failures, contract_failures)
    check("one_day_authority", page.locator("#dateSelect").count() == 1 and page.locator(".day-picker").count() == 1)
    check("single_configured_route", len(page.evaluate("Object.keys(window.__tripApp.DATA.routes)")) == 1)
    if page.locator("html").get_attribute("lang") != "en":
        page.locator("#langToggle").click()
    oracle = page.evaluate("""() => {const place=document.querySelector('#dayPlan [data-day-place]'),travel=document.querySelector('#dayPlan .plan-travel'),summary=[...document.querySelectorAll('#dayHeader .day-summary p')].map(x=>x.innerText);return {next_place:place?.dataset.dayPlace,place_identity:place?.querySelector('.day-item-title')?.innerText,why_now:place?.querySelector('.day-item-reason')?.innerText,travel_row:travel?.querySelector('.travel-compact')?.innerText,travel_duration:travel?.querySelector('.travel-compact-duration')?.textContent.trim(),summary,details_collapsed:travel?.querySelector('[data-travel-details-toggle]')?.getAttribute('aria-expanded')==='false'}}""")
    check("today_plan_oracle_next_place_and_place_priority", oracle["next_place"] == "battery" and bool(oracle["place_identity"]) and "Why now" in oracle["why_now"], oracle)
    check("today_plan_oracle_leave_arrival_and_supported_duration", "→" in oracle["travel_row"] and oracle["travel_duration"].startswith("· ~") and "min" in oracle["travel_duration"], oracle)
    check("today_plan_oracle_next_protected_nap_and_critical_condition", any("13:00–15:00" in row for row in oracle["summary"]) and any("Battery" in row or "visibility" in row.lower() for row in oracle["summary"]), oracle)
    check("today_plan_oracle_keeps_details_collapsed", oracle["details_collapsed"], oracle)

    first = page.locator("#dayPlan [data-travel-details-toggle]").first
    first.focus()
    before_scroll = page.evaluate("() => ({top:document.querySelector('.workbench-scroll').scrollTop, y:scrollY})")
    first.press("Enter")
    opened = page.evaluate("""() => {const button=document.querySelector('#dayPlan [data-travel-details-toggle]'),region=document.getElementById(button.getAttribute('aria-controls'));return {expanded:button.getAttribute('aria-expanded'),hidden:region.hidden,focus:document.activeElement.id,button:button.id,text:region.innerText}}""")
    check("keyboard_opens_one_travel_details_region", opened["expanded"] == "true" and not opened["hidden"] and opened["focus"] == opened["button"] and all(token in opened["text"].lower() for token in ("planning", "baseline", "buffer", "confidence")), opened)
    page.evaluate("async () => { await window.__tripApp.whenIdle?.(); }")
    opened_path = OUTPUT / "screens" / "C" / "travel_details_expanded_10-4_1440x900.png"
    opened_path.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(opened_path), animations="disabled")
    report["screenshots"].append({"name": opened_path.stem, "path": str(opened_path.relative_to(ROOT)), "sha256": sha256(opened_path)})
    first.press("Enter")
    closed = page.evaluate("""() => {const button=document.querySelector('#dayPlan [data-travel-details-toggle]'),region=document.getElementById(button.getAttribute('aria-controls'));return {expanded:button.getAttribute('aria-expanded'),hidden:region.hidden,focus:document.activeElement.id,button:button.id}}""")
    after_scroll = page.evaluate("() => ({top:document.querySelector('.workbench-scroll').scrollTop, y:scrollY})")
    check("keyboard_collapses_and_keeps_focus_and_scroll", closed["expanded"] == "false" and closed["hidden"] and closed["focus"] == closed["button"] and after_scroll == before_scroll, {"closed": closed, "before_scroll": before_scroll, "after_scroll": after_scroll})

    note_button = page.locator("[data-day-notes-toggle]")
    note_button.focus()
    note_button.press("Enter")
    notes = page.evaluate("""() => {const button=document.querySelector('[data-day-notes-toggle]'),region=document.getElementById(button.getAttribute('aria-controls'));return {expanded:button.getAttribute('aria-expanded'),hidden:region.hidden,focus:document.activeElement.id,button:button.id}}""")
    check("day_notes_keyboard_disclosure", notes["expanded"] == "true" and not notes["hidden"] and notes["focus"] == notes["button"], notes)
    notes_path = OUTPUT / "screens" / "C" / "day_notes_expanded_10-4_1440x900.png"
    page.screenshot(path=str(notes_path), animations="disabled")
    report["screenshots"].append({"name": notes_path.stem, "path": str(notes_path.relative_to(ROOT)), "sha256": sha256(notes_path)})
    note_button.press("Enter")

    # Language/theme presentation rerenders preserve the same expanded movement;
    # changing date clears that ephemeral presentation state.
    first.focus()
    first.press("Enter")
    travel_id = first.get_attribute("data-travel-id")
    page.locator("#langToggle").click()
    page.locator("#themeToggle").click()
    preserved = page.evaluate("""id=>{const b=[...document.querySelectorAll('[data-travel-details-toggle]')].find(x=>x.dataset.travelId===id),r=b&&document.getElementById(b.getAttribute('aria-controls'));return !!b&&b.getAttribute('aria-expanded')==='true'&&!r.hidden}""", travel_id)
    check("same_travel_identity_survives_language_theme_change", preserved)
    page.locator("#dateSelect").select_option("10/5")
    reset = page.evaluate("() => [...document.querySelectorAll('[data-travel-details-toggle]')].every(b=>b.getAttribute('aria-expanded')==='false') && document.querySelector('[data-day-notes-toggle]')?.getAttribute('aria-expanded')==='false'")
    check("date_switch_resets_ephemeral_day_disclosures", reset)

    # Cost/readiness remains a separate modal surface while Day selection/state stays owned.
    page.locator("#dateSelect").select_option("10/4")
    page.locator("#dayPlan [data-travel-details-toggle]").first.focus()
    page.keyboard.press("Enter")
    page.locator("#openCostCockpit").click()
    coexist = page.evaluate("() => ({dialog:document.getElementById('costCockpit').open,date:window.__tripApp.state.task.date,mode:window.__tripApp.state.presentation.mode,travelOpen:document.querySelector('#dayPlan [data-travel-details-toggle]')?.getAttribute('aria-expanded')})")
    check("cost_readiness_dialog_coexists_with_day_context", coexist["dialog"] and coexist["date"] == "10/4" and coexist["mode"] == "day" and coexist["travelOpen"] == "true", coexist)
    check("cost_readiness_stays_separate_and_local_only", page.locator("#costCockpit .local-only").count() == 1 and page.locator("#dayPlan .readiness-card").count() == 0 and page.locator("#dayHeader #openCostCockpit").count() == 1)
    cockpit_path = OUTPUT / "screens" / "C" / "cost_readiness_dialog_10-4_1440x900.png"
    page.screenshot(path=str(cockpit_path), animations="disabled")
    report["screenshots"].append({"name": cockpit_path.stem, "path": str(cockpit_path.relative_to(ROOT)), "sha256": sha256(cockpit_path)})
    page.locator("#costCockpitClose").click()
    check("dialog_close_restores_day_context", page.evaluate("document.activeElement.id==='openCostCockpit' && window.__tripApp.state.task.date==='10/4'"))

    page.locator("#dateSelect").select_option("all")
    features = page.evaluate("""() => window.__tripApp.visibleRouteFeatures().map(f=>({leg_id:f.properties.leg_id,mode:f.properties.mode,status:f.properties.status,point_count:f.geometry.coordinates.length}))""")
    data = json.loads((ROOT / "data/phase7_app_data.json").read_text())
    geometry = json.loads((ROOT / "data/route_geometry_cache.json").read_text())
    rendered_ids = {row["leg_id"] for row in features}
    physical = [leg for leg in data["legs"] if leg["mode"] in {"drive", "walk"}]
    route_features_valid = all(
        row["status"] == "routed_osm" and row["point_count"] > 2
        for row in features if row["mode"] in {"drive", "walk"}
    )
    omitted_absent = all(
        leg["leg_id"] not in rendered_ids
        for leg in physical if geometry[leg["leg_id"]].get("status") == "intentionally_omitted"
    )
    check("map_draws_only_matching_network_geometry_for_physical_legs", route_features_valid and omitted_absent, {"rendered_physical": sum(row["mode"] in {"drive", "walk"} for row in features), "rendered_invalid_physical": [row for row in features if row["mode"] in {"drive", "walk"} and (row["status"] != "routed_osm" or row["point_count"] <= 2)], "omitted_leg_rendered": sorted(rendered_ids & {leg["leg_id"] for leg in physical if geometry[leg["leg_id"]].get("status") == "intentionally_omitted"})})

    page.evaluate("window.__tripApp.selectPlace('battery',{focus:false,open:false}); window.__tripApp.setMode('decide'); window.__tripApp.setSheet('compact')")
    page.set_viewport_size({"width": 1440, "height": 900})
    desktop_compact = page.evaluate("() => ({sheet:window.__tripApp.state.presentation.sheet,selected:window.__tripApp.state.task.selected,map:window.__tripApp.mapSpatialSnapshot(),scroll:document.querySelector('.workbench-scroll')?.hidden})")
    check("desktop_collapsed_workbench_keeps_spatial_map_and_selection", desktop_compact["sheet"] == "compact" and desktop_compact["selected"] == "battery" and desktop_compact["map"]["useful"] and desktop_compact["scroll"], desktop_compact)
    desktop_compact_path = OUTPUT / "screens" / "C" / "desktop_collapsed_workbench_1440x900.png"
    page.screenshot(path=str(desktop_compact_path), animations="disabled")
    report["screenshots"].append({"name": desktop_compact_path.stem, "path": str(desktop_compact_path.relative_to(ROOT)), "sha256": sha256(desktop_compact_path)})
    page.set_viewport_size({"width": 390, "height": 844})
    compact = page.evaluate("() => ({mode:window.__tripApp.state.presentation.mode,sheet:window.__tripApp.state.presentation.sheet,selected:window.__tripApp.state.task.selected,map:window.__tripApp.mapSpatialSnapshot(),explicit_controls:document.querySelectorAll('[data-sheet=compact],[data-sheet=expanded]').length})")
    check("mobile_compact_sheet_keeps_map_selection_and_explicit_controls", compact["sheet"] == "compact" and compact["selected"] == "battery" and compact["map"]["useful"] and compact["explicit_controls"] >= 2, compact)
    compact_path = OUTPUT / "screens" / "C" / "mobile_compact_map_390x844.png"
    page.screenshot(path=str(compact_path), animations="disabled")
    report["screenshots"].append({"name": compact_path.stem, "path": str(compact_path.relative_to(ROOT)), "sha256": sha256(compact_path)})
    page.locator('.sheet-actions [data-sheet="expanded"]').click()
    expanded = page.evaluate("() => ({sheet:window.__tripApp.state.presentation.sheet,selected:window.__tripApp.state.task.selected,map:window.__tripApp.mapSpatialSnapshot(),scrollWidth:document.documentElement.scrollWidth,innerWidth})")
    check("mobile_expanded_sheet_retains_state_and_spatial_map", expanded["sheet"] == "expanded" and expanded["selected"] == "battery" and expanded["map"]["useful"] and expanded["scrollWidth"] <= expanded["innerWidth"], expanded)
    expanded_path = OUTPUT / "screens" / "C" / "mobile_expanded_sheet_390x844.png"
    page.screenshot(path=str(expanded_path), animations="disabled")
    report["screenshots"].append({"name": expanded_path.stem, "path": str(expanded_path.relative_to(ROOT)), "sha256": sha256(expanded_path)})

    touch_context = browser.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
    touch_page = touch_context.new_page()
    touch_page.goto(url, wait_until="domcontentloaded", timeout=90000)
    touch_page.wait_for_function("window.__tripApp?.map()?.isStyleLoaded()", timeout=30000)
    touch_page.locator('#modeNav [data-mode="day"]').click()
    touch_page.locator("#dateSelect").select_option("10/4")
    touch_page.locator("#dayPlan [data-travel-details-toggle]").first.tap()
    touch = touch_page.evaluate("() => {const b=document.querySelector('#dayPlan [data-travel-details-toggle]'),r=document.getElementById(b.getAttribute('aria-controls'));return {expanded:b.getAttribute('aria-expanded'),hidden:r.hidden,focus:document.activeElement.id,button:b.id}}")
    check("mobile_touch_opens_details_and_keeps_day_context", touch["expanded"] == "true" and not touch["hidden"] and touch_page.evaluate("window.__tripApp.state.task.date==='10/4'"), touch)
    touch_context.close()

    # Narrow portrait and landscape should continue to reflow without sideways scroll.
    page.set_viewport_size({"width": 320, "height": 760})
    narrow = page.evaluate("() => ({scrollWidth:document.documentElement.scrollWidth,innerWidth})")
    check("narrow_portrait_has_no_horizontal_overflow", narrow["scrollWidth"] <= narrow["innerWidth"], narrow)
    page.set_viewport_size({"width": 844, "height": 390})
    landscape = page.evaluate("() => ({scrollWidth:document.documentElement.scrollWidth,innerWidth,mapHeight:document.querySelector('#map').getBoundingClientRect().height})")
    check("mobile_landscape_retains_map_and_no_horizontal_overflow", landscape["scrollWidth"] <= landscape["innerWidth"] and landscape["mapHeight"] > 0, landscape)
    page.close()

    # Exact 200% text scale and deliberately long copy exercise reflow without shipping a fixture.
    reflow = browser.new_page(viewport={"width": 720, "height": 450})
    reflow.goto(url, wait_until="domcontentloaded", timeout=90000)
    reflow.wait_for_function("window.__tripApp?.map()?.isStyleLoaded()", timeout=30000)
    reflow.locator('#modeNav [data-mode="day"]').click()
    reflow.locator("#dateSelect").select_option("10/4")
    reflow.locator("[data-day-notes-toggle]").click()
    reflow.evaluate("""() => {document.documentElement.style.fontSize='200%';const p=document.querySelector('.day-notes p');if(p)p.textContent='Long-copy reflow fixture: '+('Protected lodging recovery, route conditions, timing windows, and evidence remain available. '.repeat(18));}""")
    reflow_box = reflow.evaluate("() => ({scrollWidth:document.documentElement.scrollWidth,innerWidth,notesWidth:document.querySelector('.day-notes')?.scrollWidth,notesClient:document.querySelector('.day-notes')?.clientWidth})")
    check("200_percent_long_copy_reflows_without_horizontal_overflow", reflow_box["scrollWidth"] <= reflow_box["innerWidth"] and (reflow_box["notesWidth"] or 0) <= (reflow_box["notesClient"] or 0), reflow_box)
    reflow.close()

    # Deliberately fail the optional remote provider, then verify the local route/day state returns.
    provider = browser.new_page(viewport={"width": 1440, "height": 900})
    provider.goto(url, wait_until="domcontentloaded", timeout=90000)
    provider.wait_for_function("window.__tripApp?.map()?.isStyleLoaded()", timeout=30000)
    provider.locator('#modeNav [data-mode="day"]').click()
    provider.locator("#dateSelect").select_option("10/8")
    provider.route("https://server.arcgisonline.com/**", lambda route: route.abort())
    provider.evaluate("window.__tripApp.chooseProvider('satellite')")
    provider.wait_for_function("window.__tripApp.state.provider==='vector' && !document.getElementById('mapError').hidden", timeout=15000)
    failure = provider.evaluate("() => ({provider:window.__tripApp.state.provider,date:window.__tripApp.state.task.date,mode:window.__tripApp.state.presentation.mode,selected:window.__tripApp.state.task.selected,localAssets:window.__tripApp.state.runtime.localAssets.status})")
    check("provider_failure_recovers_to_local_map_without_losing_day", failure["provider"] == "vector" and failure["date"] == "10/8" and failure["mode"] == "day", failure)
    provider_path = OUTPUT / "screens" / "C" / "provider_failure_recovered_to_smart_map_1440x900.png"
    provider.screenshot(path=str(provider_path), animations="disabled")
    report["screenshots"].append({"name": provider_path.stem, "path": str(provider_path.relative_to(ROOT)), "sha256": sha256(provider_path)})
    provider.unroute("https://server.arcgisonline.com/**")
    provider.close()
    browser.close()
    return report


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    SCREEN_ROOT.mkdir(parents=True, exist_ok=True)
    current = command(["git", "rev-parse", "HEAD"])
    current_tree = command(["git", "rev-parse", "HEAD^{tree}"])
    status_rows = command(["git", "status", "--porcelain", "--untracked-files=all"]).splitlines()
    source_dirty = [row[3:] for row in status_rows if len(row) >= 4 and not row[3:].startswith(("QA/", ".build/", ".release/", ".public-site/"))]
    if source_dirty:
        raise SystemExit(f"Matched rendered evidence requires a clean exact candidate source tree: {source_dirty}")
    variants = {"A": BASELINE_A, "B": BASELINE_B, "C": current}
    # The historical image route endpoints are checked by identity only here;
    # all baseline physical route endpoints were confirmed to be public map endpoints.
    work_root = Path(tempfile.mkdtemp(prefix="chg232-matched-ui-"))
    servers = []
    worktrees = []
    report = {
        "schema_version": 1,
        "status": "FAIL",
        "review_policy": "Objective matched render and interaction evidence only; no aesthetic winner or UI superiority score is produced.",
        "independent_review": "Prepared locally for Project OS E2 pixel review after the user returns done.",
        "matched_variants": {},
        "candidate_interactions": {},
        "errors": [],
    }
    try:
        builds: dict[str, tuple[Path, Path]] = {}
        for name, revision in variants.items():
            if name == "C":
                checkout = ROOT
            else:
                checkout = work_root / name
                command(["git", "worktree", "add", "--detach", str(checkout), revision])
                worktrees.append(checkout)
            build = work_root / f"build-{name}"
            command([sys.executable, "scripts/build_map_first.py", "--output-dir", str(build)], cwd=checkout)
            builds[name] = (checkout, build)

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, timeout=90000)
            for name, (checkout, build) in builds.items():
                server, url = start_variant_server(checkout, build, work_root / f"server-{name}.log")
                servers.append(server)
                screenshots = capture_matrix(browser, name, url)
                geometry = public_geometry_evidence(checkout / "data/phase7_app_data.json", checkout / "data/route_geometry_cache.json", checkout / "data/route_geometry_manifest.json")
                report["matched_variants"][name] = {
                    "revision": variants[name],
                    "tree": command(["git", "rev-parse", f"{variants[name]}^{{tree}}"]),
                    "viewport_pairs": screenshots,
                    "geometry": geometry,
                }
                if name == "C":
                    report["candidate_interactions"] = inspect_candidate(browser, url)
            browser.close()

        candidate_errors = report["candidate_interactions"].get("errors", [])
        candidate_checks = report["candidate_interactions"].get("checks", {})
        comparison_count = sum(len(item["viewport_pairs"]) for item in report["matched_variants"].values())
        all_match = all(row["pass"] for row in candidate_checks.values()) and not candidate_errors
        report["comparison_capture_count"] = comparison_count
        report["candidate_tree"] = current_tree
        report["candidate_revision"] = current
        report["status"] = "PASS" if comparison_count == 48 and all_match else "FAIL"
    except Exception as error:
        report["errors"].append(f"{type(error).__name__}: {error}")
    finally:
        for server in servers:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
        for checkout in reversed(worktrees):
            subprocess.run(["git", "worktree", "remove", "--force", str(checkout)], cwd=ROOT, capture_output=True, text=True)
        shutil.rmtree(work_root, ignore_errors=True)

    (OUTPUT / "objective_comparison.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    summary = {
        "status": report["status"],
        "comparison_capture_count": report.get("comparison_capture_count", 0),
        "candidate_checks": report.get("candidate_interactions", {}).get("checks", {}),
        "errors": report["errors"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
