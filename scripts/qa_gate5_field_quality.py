"""Gate 5 field-quality evidence: rendered UX, accessibility, browser matrix, and baseline.

This is a focused suite attached to the canonical pipeline. It records objective
browser observations and screenshots; it is not a substitute for independent
visual/usability acceptance or WCAG certification.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import socket
import statistics
import sys
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from qa_config import MODULAR_URL
from qa_loading import wait_for_application_ready
from qa_map_visual_integrity import crop_map, image_from_path, integrity_result


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "manifests" / "gate5_field_quality_contract.json"
DEFAULT_OUTPUT = ROOT / "QA/gate5/candidate.json"
BASELINE_OUTPUT = ROOT / "QA/gate5/baseline.json"
PAIRED_COMPARISON_OUTPUT = ROOT / "QA/gate5/paired_comparison.json"
PERFORMANCE_SUMMARY_OUTPUT = ROOT / "QA/gate5/performance_summary.log"
FINDING_MATRIX = ROOT / "QA/gate5/finding_matrix.json"
BASE_REVISION = "75d1f127dd5ce332df54e205e9a3d152de7af176"
SOURCE_EXCLUDED_PREFIXES = ("QA/", ".build/", ".release/", ".public-site/")
MATRIX = (("chromium", 1440, 900, False), ("chromium", 834, 1112, True), ("chromium", 390, 844, True), ("firefox", 1440, 900, False), ("firefox", 834, 1112, True), ("firefox", 390, 844, True), ("webkit", 1440, 900, False), ("webkit", 834, 1112, True), ("webkit", 390, 844, True))


def revision(root: Path = ROOT) -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()


def evidence_path(path: str) -> bool:
    return path.startswith(SOURCE_EXCLUDED_PREFIXES)


def status_paths(root: Path = ROOT) -> list[str]:
    rows = subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=all"], cwd=root, text=True
    ).splitlines()
    paths = []
    for row in rows:
        if len(row) < 4:
            continue
        path = row[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        if not evidence_path(path):
            paths.append(path)
    return paths


def candidate_fingerprint(root: Path = ROOT) -> dict:
    paths = subprocess.check_output(
        ["git", "ls-files", "-co", "--exclude-standard"], cwd=root, text=True
    ).splitlines()
    included = []
    for path in sorted(paths):
        if evidence_path(path):
            continue
        full = root / path
        if full.is_file():
            included.append((path, hashlib.sha256(full.read_bytes()).hexdigest()))
    payload = "\n".join(f"{path}\0{digest}" for path, digest in included).encode()
    return {
        "sha256": hashlib.sha256(payload).hexdigest(),
        "file_count": len(included),
        "tracked_head": revision(root),
        "worktree_dirty": bool(status_paths(root)),
        "excluded_from_hash": list(SOURCE_EXCLUDED_PREFIXES),
    }


def source_binding(expected_revision: str | None = None, root: Path = ROOT) -> dict:
    checked_out = revision(root)
    fingerprint = candidate_fingerprint(root)
    source_dirty = bool(status_paths(root))
    revision_matches = expected_revision is None or checked_out == expected_revision
    if not revision_matches:
        return {
            "schema_version": 1,
            "binding": "mismatch",
            "status": "VERIFY_REQUIRED",
            "claimed_revision": expected_revision,
            "checked_out_revision": checked_out,
            "source_worktree_dirty": source_dirty,
            "source_fingerprint": fingerprint,
            "reason": "checked-out revision does not match the claimed candidate revision",
        }
    if source_dirty:
        return {
            "schema_version": 1,
            "binding": "source_fingerprint",
            "status": "VERIFY_REQUIRED" if expected_revision else "RECORDED",
            "claimed_revision": expected_revision,
            "checked_out_revision": checked_out,
            "source_worktree_dirty": True,
            "source_fingerprint": fingerprint,
            "reason": "source files changed after checkout; evidence is bound to the fingerprint, not to HEAD",
        }
    return {
        "schema_version": 1,
        "binding": "exact_commit",
        "status": "PASS",
        "claimed_revision": expected_revision,
        "checked_out_revision": checked_out,
        "source_worktree_dirty": False,
        "source_fingerprint": fingerprint,
        "reason": "clean checkout is bound to the exact checked-out revision",
    }


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def quantiles(values: list[float]) -> dict:
    if not values:
        return {"count": 0, "min": None, "median": None, "p95": None, "max": None, "mean": None, "stdev": None}
    values = sorted(float(v) for v in values)
    result = {"count": len(values), "values": [round(value, 3) for value in values], "min": values[0], "median": statistics.median(values), "max": values[-1], "mean": statistics.mean(values), "stdev": statistics.stdev(values) if len(values) > 1 else 0.0}
    if len(values) >= 3:
        index = min(len(values) - 1, math.ceil(len(values) * 0.95) - 1)
        result["p95"] = values[index]
    else:
        result["p95"] = None
    return {key: round(value, 3) if isinstance(value, float) else value for key, value in result.items()}


def wait_ready(page, url: str = MODULAR_URL) -> dict:
    milestones = {}
    page.goto(url, wait_until="domcontentloaded", timeout=90000)
    milestones["dom_content_loaded"] = page.evaluate("performance.now()")
    page.wait_for_function("window.__tripApp?.map()?.isStyleLoaded()", timeout=30000)
    milestones["smart_style_ready"] = page.evaluate("performance.now()")
    page.wait_for_function("document.querySelectorAll('.photo-marker').length===window.TRIP_DATA.markers.filter(window.__tripApp.markerVisible).length", timeout=30000)
    wait_for_application_ready(page, timeout=30000)
    milestones["map_visual_ready"] = page.evaluate("performance.now()")
    milestones["markers_timeline_ready"] = page.evaluate("performance.now()")
    page.wait_for_function("document.querySelector('[data-route]') && document.querySelector('[data-provider]')", timeout=10000)
    milestones["first_actionable_state"] = page.evaluate("performance.now()")
    page.wait_for_timeout(120)
    return milestones


def errors_for(page, errors: list, console_errors: list, failed_requests: list) -> None:
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("console", lambda message: console_errors.append(message.text[:500]) if message.type == "error" else None)
    page.on("requestfailed", lambda request: failed_requests.append({"url": request.url, "failure": request.failure}))


def screenshot(page, root: Path, name: str) -> str:
    path = root / f"{name}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(path), full_page=True)
    return rel(path)


def js_checks(page) -> dict:
    return page.evaluate(
        """() => {
          const visible = el => { const r=el.getBoundingClientRect(), s=getComputedStyle(el); return s.display!=='none' && s.visibility!=='hidden' && r.width>0 && r.height>0; };
          const actionable = [...document.querySelectorAll('button,select,a,[tabindex]:not([tabindex="-1"])')].filter(visible);
          const focusable = actionable.map(el => ({tag:el.tagName.toLowerCase(),id:el.id,cls:el.className,text:(el.innerText||el.getAttribute('aria-label')||'').trim().slice(0,90),role:el.getAttribute('role'),name:el.getAttribute('aria-label')||el.innerText?.trim().slice(0,80),rect:(()=>{const r=el.getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height}})()}));
          const overflow = document.documentElement.scrollWidth - document.documentElement.clientWidth;
          const critical = [...document.querySelectorAll('[data-route],[data-route-info],[data-region],[data-provider],#dateSelect,#mobileDate,#mobileRegion,#mobileProvider,#themeToggle,#langToggle,#panelToggle,#panelClose,#panelReopen,#panelSmaller,#panelLarger,.tab,.panel-resizer')].filter(visible);
          const occluded = critical.map(el=>{const r=el.getBoundingClientRect(),x=Math.max(0,Math.min(innerWidth-1,r.left+r.width/2)),y=Math.max(0,Math.min(innerHeight-1,r.top+r.height/2)),hit=document.elementFromPoint(x,y);return {id:el.id||el.dataset.route||el.dataset.routeInfo||el.dataset.region||el.dataset.provider||el.dataset.tab||el.className,hit:!!hit && (hit===el||el.contains(hit)),w:r.width,h:r.height}});
          const semantics = {routes:[...document.querySelectorAll('[data-route]')].every(x=>x.getAttribute('aria-pressed')!==null), providers:[...document.querySelectorAll('[data-provider]')].every(x=>x.getAttribute('aria-pressed')!==null), regions:[...document.querySelectorAll('[data-region]')].every(x=>x.getAttribute('aria-pressed')!==null), tabs:[...document.querySelectorAll('[role=tab]')].every(x=>x.getAttribute('aria-selected')!==null&&x.getAttribute('aria-controls')!==null), tabpanels:[...document.querySelectorAll('[role=tabpanel]')].every(x=>x.id&&x.getAttribute('aria-labelledby')), panel:document.querySelector('#panelResizer')?.getAttribute('aria-valuenow')!==null};
          const focus = document.activeElement ? {tag:document.activeElement.tagName,id:document.activeElement.id,cls:document.activeElement.className,text:(document.activeElement.innerText||document.activeElement.getAttribute('aria-label')||'').trim().slice(0,80)} : null;
          return {overflow,focusable,critical_count:critical.length,occluded,semantics,focus,canvas:document.querySelectorAll('.maplibregl-canvas').length,markers:document.querySelectorAll('.photo-marker').length,clusters:document.querySelectorAll('.photo-cluster').length,layers:window.__tripApp?.map()?.getStyle()?.layers?.length||0};
        }"""
    )


def contrast_checks(page) -> list[dict]:
    return page.evaluate(
        """() => {
          const canvas=document.createElement('canvas'),ctx=canvas.getContext('2d');
          const parse=value=>{const srgb=String(value).match(/color\\(srgb\\s+([0-9.]+)\\s+([0-9.]+)\\s+([0-9.]+)(?:\\s*\\/\\s*([0-9.]+))?/);if(srgb)return [Number(srgb[1])*255,Number(srgb[2])*255,Number(srgb[3])*255,Number(srgb[4]??1)];ctx.fillStyle='#000';ctx.fillStyle=value;const normalized=ctx.fillStyle,m=normalized.match(/rgba?\\(([^)]+)\\)/);if(m){const p=m[1].split(',').map(Number);return [p[0],p[1],p[2],p[3]??1]}const h=normalized.replace('#','');if(h.length===3)return [...h].map(x=>parseInt(x+x,16)).concat(1);if(h.length>=6)return [parseInt(h.slice(0,2),16),parseInt(h.slice(2,4),16),parseInt(h.slice(4,6),16),1];return null};
          const effectiveBackground=el=>{let node=el;while(node){const value=getComputedStyle(node).backgroundColor,parsed=parse(value);if(parsed&&parsed[3]>.05)return parsed;node=node.parentElement}return parse(getComputedStyle(document.body).backgroundColor)};
          const lum=rgb=>{const c=rgb.slice(0,3).map(v=>v/255).map(v=>v<=.03928?v/12.92:Math.pow((v+.055)/1.055,2.4));return .2126*c[0]+.7152*c[1]+.0722*c[2]};
          const ratio=(a,b)=>{const x=lum(a),y=lum(b);return (Math.max(x,y)+.05)/(Math.min(x,y)+.05)};
          const rows=[];for(const sel of ['.brand','.group-label','.provider-state','.ctl','.ctl.active','.tab','.tab.active','.timeline-card','.tl-reason','.map-badge','.map-slot','.preview-action','.muted']){const el=document.querySelector(sel);if(!el)continue;const s=getComputedStyle(el),fg=parse(s.color),bg=effectiveBackground(el),value=fg&&bg?Number(ratio(fg,bg).toFixed(2)):null;rows.push({selector:sel,ratio:value,pass:value===null||value>=4.5,foreground:s.color,background:bg,fontSize:s.fontSize})}return rows;
        }"""
    )


def reflow_checks(page) -> dict:
    page.set_viewport_size({"width": 720, "height": 900})
    page.evaluate("document.documentElement.style.zoom='2'")
    page.wait_for_timeout(120)
    result = page.evaluate(
        """() => {
          const selectors=['#activeFilterSummary','#fieldSummaryText','#branchLegendText','#mobileDate','#mobileRegion','#mobileProvider','#detailsPane h2','.map'];
          const hidden=selectors.filter(sel=>{const el=document.querySelector(sel);if(!el)return true;const r=el.getBoundingClientRect(),s=getComputedStyle(el);return s.display==='none'||s.visibility==='hidden'||r.width===0||r.height===0});
          return {viewport:{width:innerWidth,height:innerHeight},overflow:document.documentElement.scrollWidth-innerWidth,hidden_critical:hidden,focusable:document.querySelectorAll('button,select,a,[tabindex]:not([tabindex="-1"])').length};
        }"""
    )
    page.evaluate("document.documentElement.style.zoom=''")
    page.set_viewport_size({"width": 1440, "height": 900})
    return result


def reduced_motion_check(page) -> dict:
    page.emulate_media(reduced_motion="reduce")
    page.goto(MODULAR_URL, wait_until="domcontentloaded", timeout=90000)
    result = page.evaluate(
        """() => { const el=document.querySelector('#loadingScreen')||document.body; const pseudo=document.querySelector('.loading-progress'); const s=getComputedStyle(el); const p=pseudo?getComputedStyle(pseudo,'::after'):null; return {media:matchMedia('(prefers-reduced-motion: reduce)').matches,animation:s.animationDuration,transition:s.transitionDuration,progressAnimation:p?.animationDuration||null}; }"""
    )
    page.emulate_media(reduced_motion="no-preference")
    return result


def map_visual_integrity(page, shots: Path, name: str, clean_reference: Path) -> dict:
    """Capture only the map canvas and compare it with the clean same-state capture."""

    path = shots / f"{name}_map_visual.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    selectors = ".map-badge,.date-ribbon,.map-schedule,.map-focus,.preview-card,.route-tip,.maplibregl-control-container,.maplibregl-marker"
    saved = page.evaluate("""selectors => [...document.querySelectorAll(selectors)].map(element => element.getAttribute('style'))""", selectors)
    try:
        page.evaluate("""selectors => document.querySelectorAll(selectors).forEach(element => element.style.setProperty('display','none','important'))""", selectors)
        page.locator("#map").screenshot(path=str(path))
    finally:
        page.evaluate("""({selectors, saved}) => [...document.querySelectorAll(selectors)].forEach((element, index) => saved[index] === null ? element.removeAttribute('style') : element.setAttribute('style', saved[index]))""", {"selectors": selectors, "saved": saved})
    current = image_from_path(path)
    reference = image_from_path(clean_reference)
    box = page.locator("#map").bounding_box()
    if not box:
        return {"status": "VERIFY_REQUIRED", "reason": "map element has no rendered bounds", "screenshot": rel(path)}
    reference = crop_map(reference, tuple(round(box[key]) for key in ("x", "y", "width", "height")))
    if reference.size != current.size:
        reference = reference.resize(current.size)
    result = integrity_result(current, reference)
    result["screenshot"] = rel(path)
    result["clean_reference"] = rel(clean_reference)
    return result


def run_workflow(page, shots: Path, touch: bool = False, url: str = MODULAR_URL) -> dict:
    checks = {"first_view": {}, "flows": {}, "accessibility": {}, "states": {}, "screenshots": []}
    checks["first_view"] = page.evaluate("""()=>({trip:document.querySelector('.brand')?.innerText,routeControls:[...document.querySelectorAll('[data-route]')].map(x=>x.innerText.trim()),routeGuide:document.querySelector('.route-guide')?.innerText||'',filter:document.querySelector('#activeFilterSummary')?.innerText||'',freshness:document.querySelector('#freshnessNote')?.innerText||'',provider:document.querySelector('#providerState')?.innerText||'',branchLegend:document.querySelector('#mapRouteLegend')?.innerText||''})""")
    checks["screenshots"].append(screenshot(page, shots, "overall_1440_ko_light" if not touch else "overall_390_ko_light"))
    page.locator('[data-route="A2"]').click()
    page.locator('#dateSelect' if not touch else '#mobileDate').select_option('10/8')
    if not touch:
        page.locator('[data-region="yosemite"]').click()
    else:
        page.locator('#mobileRegion').select_option('yosemite')
    page.wait_for_timeout(250)
    checks["flows"]["filter_state"] = page.evaluate("""()=>({routes:[...document.querySelectorAll('[data-route][aria-pressed=true]')].map(x=>x.dataset.route),date:window.__tripApp.state.date,region:window.__tripApp.state.region,markers:document.querySelectorAll('.photo-marker').length,timeline:document.querySelectorAll('[data-timeline]').length})""")
    checks["screenshots"].append(screenshot(page, shots, "filtered_1440_ko_light" if not touch else "filtered_390_ko_light"))
    marker = page.locator('.photo-marker').first
    if marker.count():
        marker.focus()
        page.keyboard.press('Enter')
        page.wait_for_timeout(180)
        checks["flows"]["marker_preview"] = page.evaluate("""()=>({preview:document.getElementById('previewCard')?.classList.contains('show'),focus:document.activeElement?.className,detail:document.querySelector('#detailsPane .photo-grid img')?.naturalWidth||0})""")
        action = page.locator('#previewCard .preview-action')
        if action.count():
            action.focus(); page.keyboard.press('Enter'); page.wait_for_timeout(100)
        checks["flows"]["preview_to_details"] = page.evaluate("""()=>({tab:window.__tripApp.state.tab,selected:window.__tripApp.state.selected,details:document.querySelectorAll('#detailsPane .photo-grid img').length,focus:document.activeElement?.className||document.activeElement?.id})""")
    checks["screenshots"].append(screenshot(page, shots, "detail_390_ko_light" if touch else "detail_1440_ko_light"))
    checks["flows"]["panel"] = page.evaluate("""()=>{const b=document.querySelector('#panelToggle');b?.click();return {hidden:document.getElementById('app').classList.contains('panel-hidden'),reopen:document.getElementById('panelReopen')?.offsetParent!==null,focusOverlay:document.getElementById('mapFocus')?.classList.contains('show')}}""")
    if page.locator('#mapFocus.show').count():
        checks["flows"]["panel"]["overlay_intercepted_reopen"] = True
        page.locator('#mapFocus .map-focus-head button').click(force=True)
    page.locator('#panelReopen').click(); page.wait_for_timeout(160)
    checks["flows"]["panel"]["restored"] = page.evaluate("()=>({hidden:document.getElementById('app').classList.contains('panel-hidden'),focus:document.activeElement?.id||document.activeElement?.className})")
    checks["flows"]["panel"]["focus_return"] = checks["flows"]["panel"]["restored"]["focus"] in ("panelToggle", "detailsPane")
    if not touch:
        info = page.locator('[data-route-info="A1"]'); info.focus(); page.keyboard.press('Enter'); page.wait_for_timeout(80)
        checks["flows"]["route_explanation"] = page.evaluate("()=>({visible:document.getElementById('routeExplain')?.classList.contains('show'),expanded:document.querySelector('[data-route-info=A1]')?.getAttribute('aria-expanded'),close:document.querySelector('#routeExplain .route-explain-close')?.getAttribute('aria-label')})")
        page.keyboard.press('Escape'); page.wait_for_timeout(60)
        checks["flows"]["route_explanation"]["escape_hidden"] = page.evaluate("()=>!document.getElementById('routeExplain')?.classList.contains('show')")
    page.locator('#langToggle').click(); page.wait_for_timeout(120)
    checks["flows"]["language"] = page.evaluate("()=>({lang:document.documentElement.lang,brand:document.querySelector('.brand')?.innerText,filter:document.querySelector('#activeFilterSummary')?.innerText,detail:document.querySelector('#detailsPane')?.innerText.slice(0,180)})")
    page.locator('#themeToggle').click(); page.wait_for_timeout(180)
    checks["flows"]["theme"] = page.evaluate("()=>({theme:document.documentElement.dataset.theme,background:getComputedStyle(document.body).backgroundColor})")
    checks["screenshots"].append(screenshot(page, shots, "detail_390_en_dark" if touch else "detail_1440_en_dark"))
    checks["accessibility"] = {"dom": js_checks(page), "contrast": contrast_checks(page), "reflow_200": reflow_checks(page), "reduced_motion": reduced_motion_check(page)}
    return checks


def keyboard_checks(page, url: str = MODULAR_URL) -> dict:
    page.goto(url, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_function("window.__tripApp?.map()?.isStyleLoaded()", timeout=30000)
    wait_for_application_ready(page, timeout=30000)
    focusable = page.locator('button,select,a,[tabindex]:not([tabindex="-1"])')
    order=[]
    for _ in range(min(80, focusable.count()+8)):
        page.keyboard.press('Tab')
        order.append(page.evaluate("()=>({id:document.activeElement?.id||'',cls:document.activeElement?.className||'',text:(document.activeElement?.innerText||document.activeElement?.getAttribute('aria-label')||'').trim().slice(0,80)})"))
    marker = page.locator('.photo-marker').first
    marker.focus(); page.keyboard.press('Enter'); page.wait_for_timeout(100)
    preview_focus = page.evaluate("()=>document.activeElement?.className||document.activeElement?.id")
    page.keyboard.press('Escape')
    return {"tab_order":order,"unique_focus_targets":len({json.dumps(x,sort_keys=True) for x in order}),"marker_enter_focus":preview_focus,"escape_preview_hidden":page.evaluate("()=>!document.getElementById('previewCard')?.classList.contains('show')"),"escape_focus_target":page.evaluate("()=>({tag:document.activeElement?.tagName||'',id:document.activeElement?.id||'',cls:document.activeElement?.className||''})"),"escape_focus_return":page.evaluate("()=>document.activeElement?.classList.contains('photo-marker')||document.activeElement?.classList.contains('photo-cluster')"),"semantics":js_checks(page)["semantics"]}


def provider_recovery(page, url: str = MODULAR_URL) -> dict:
    page.goto(url, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_function("window.__tripApp?.map()?.isStyleLoaded()", timeout=30000)
    wait_for_application_ready(page, timeout=30000)
    page.route("https://**/*", lambda route: route.abort())
    before = page.evaluate("()=>window.__tripApp.runtimeSnapshot()")
    started = time.perf_counter(); page.evaluate("async()=>await window.__tripApp.chooseProvider('satellite')"); page.wait_for_function("window.__tripApp.state.provider==='vector'", timeout=15000)
    elapsed = (time.perf_counter()-started)*1000
    after = page.evaluate("()=>window.__tripApp.runtimeSnapshot()")
    return {"elapsed_ms":round(elapsed,3),"before":before,"after":after,"state_preserved":before["planning_state"]==after["planning_state"],"smart_active":after["provider"]=="vector","canvas":after["map"]["canvas_count"],"fallback_note":page.locator('#fallbackNote').inner_text()}


def sparse_state_checks(page, url: str = MODULAR_URL) -> dict:
    page.goto(url, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_function("window.__tripApp?.map()?.isStyleLoaded()", timeout=30000)
    wait_for_application_ready(page, timeout=30000)
    page.evaluate("""async()=>{const a=window.__tripApp;a.state.routes=new Set(['A1']);a.state.date='10/3';a.state.region='yosemite';a.state.selected=null;a.renderTimeline();a.renderDetail(null);await a.drawMap(false)}""")
    page.wait_for_timeout(140)
    sparse=page.evaluate("""()=>({timelineEmpty:!!document.querySelector('#timelinePane .empty'),detailsEmpty:!!document.querySelector('#detailsPane .empty'),markers:document.querySelectorAll('.photo-marker').length,filter:document.querySelector('#activeFilterSummary')?.innerText,overflow:document.documentElement.scrollWidth-innerWidth})""")
    page.evaluate("""async()=>{const a=window.__tripApp;a.state.routes=new Set(Object.keys(a.DATA.routes));a.state.date='all';a.state.region='overall';a.renderTimeline();a.renderDetail(null);await a.drawMap(false)}""")
    return {"sparse_empty":sparse,"freshness_visible":bool(page.locator('#freshnessNote').inner_text())}


def interaction_samples(page, count: int, url: str = MODULAR_URL) -> dict:
    operations = {"route": [], "date": [], "region": [], "preview": [], "preview_actionability": [], "preview_handler": [], "detail": [], "panel": [], "provider_recovery": []}
    page.goto(url, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_function("window.__tripApp?.map()?.isStyleLoaded()", timeout=30000); wait_for_application_ready(page, timeout=30000)
    for _ in range(count):
        for name, action in (("route", lambda: page.locator('[data-route=A2]').click()), ("date", lambda: page.locator('#dateSelect').select_option('10/8')), ("region", lambda: page.locator('[data-region=yosemite]').click())):
            started=time.perf_counter(); action(); page.wait_for_timeout(40); operations[name].append((time.perf_counter()-started)*1000)
        page.evaluate("async()=>await window.__tripApp.whenIdle()")
        marker=page.locator('.photo-marker:visible').first
        started=time.perf_counter(); marker.focus(); actionability=(time.perf_counter()-started)*1000
        page.wait_for_function("document.getElementById('previewCard')?.classList.contains('show')", timeout=5000)
        operations['preview_actionability'].append(actionability)
        operations['preview'].append((time.perf_counter()-started)*1000)
        page.evaluate("()=>{window.__tripApp.hidePreview();document.activeElement?.blur()}")
        handler_started=time.perf_counter()
        page.evaluate("()=>[...document.querySelectorAll('.photo-marker')].find(el=>getComputedStyle(el).display!=='none'&&getComputedStyle(el).visibility!=='hidden')?.focus()")
        page.wait_for_function("document.getElementById('previewCard')?.classList.contains('show')", timeout=5000)
        operations['preview_handler'].append((time.perf_counter()-handler_started)*1000)
        action=page.locator('#previewCard .preview-action'); started=time.perf_counter(); action.click(); page.wait_for_timeout(40); operations['detail'].append((time.perf_counter()-started)*1000)
        started=time.perf_counter(); page.locator('#panelToggle').click(); page.wait_for_timeout(40)
        if page.locator('#mapFocus.show').count(): page.locator('#mapFocus .map-focus-head button').click(force=True)
        page.locator('#panelReopen').click(); page.wait_for_timeout(40); operations['panel'].append((time.perf_counter()-started)*1000)
        started=time.perf_counter(); page.route("https://**/*", lambda route: route.abort()); page.evaluate("async()=>await window.__tripApp.chooseProvider('satellite')"); page.wait_for_function("window.__tripApp.state.provider==='vector'", timeout=15000); operations['provider_recovery'].append((time.perf_counter()-started)*1000); page.unroute("https://**/*")
    return {key: quantiles(value) for key, value in operations.items()}


def _package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def performance_environment_signature(
    browser_name: str,
    browser_version: str,
    viewport: dict,
    has_touch: bool,
    is_mobile: bool,
    phase: str,
    sample_count: int,
) -> dict:
    display_backend = "x11" if os.environ.get("DISPLAY") else "wayland" if os.environ.get("WAYLAND_DISPLAY") else "none"
    return {
        "schema_version": 1,
        "os": {"system": platform.system(), "release": platform.release(), "version": platform.version()},
        "architecture": {"machine": platform.machine(), "bits": platform.architecture()[0]},
        "browser": {
            "family": browser_name,
            "runtime_version": browser_version,
            "playwright_version": _package_version("playwright"),
        },
        "execution": {
            "mode": "ci" if os.environ.get("CI") else "local",
            "ci_value": os.environ.get("CI"),
            "headless": True,
            "display_backend": display_backend,
            "software_gl": os.environ.get("LIBGL_ALWAYS_SOFTWARE"),
        },
        "device_emulation": {
            "viewport": {"width": viewport["width"], "height": viewport["height"]},
            "device_scale_factor": 1,
            "has_touch": has_touch,
            "is_mobile": is_mobile,
            "user_agent": "playwright-default",
        },
        "sample_conditions": {
            "sample_count": sample_count,
            "measurement_profile": "gate5-performance-r4-paired-blocks-v1",
            "server": "local-http",
            "network": "default-playwright-context",
            "cold_condition": "new-context-and-page",
            "warm_condition": "same-page-reload-readiness-after-cold-sample",
            "browser_cache_condition": "isolated-new-context",
            "runner_order_condition": "alternated-paired-same-browser-process",
            "ready_milestones": ["dom_content_loaded", "smart_style_ready", "markers_timeline_ready", "first_actionable_state"],
            "interaction_repeat_count": 1,
        },
    }


def performance_sample(playwright, browser, url: str, source: dict | None = None) -> dict:
    context = browser.new_context(viewport={"width": 1440, "height": 900}, has_touch=False, is_mobile=False)
    page = context.new_page()
    errors, console_errors, failed = [], [], []
    errors_for(page, errors, console_errors, failed)
    request_urls = []
    page.on("request", lambda request: request_urls.append(request.url))
    try:
        milestones = wait_ready(page, url)
        snapshot = page.evaluate("()=>window.__tripApp.runtimeSnapshot()")
        resources = page.evaluate("()=>({resources:performance.getEntriesByType('resource').length,transfer:performance.getEntriesByType('resource').reduce((s,x)=>s+(x.transferSize||0),0),longtasks:performance.getEntriesByType('longtask').map(x=>x.duration),memory:performance.memory?{used:performance.memory.usedJSHeapSize,total:performance.memory.totalJSHeapSize,limit:performance.memory.jsHeapSizeLimit}:null})")
        warm = wait_ready(page, url)
        interaction = interaction_samples(page, 1, url)
        return {
            "cold": {"milestones": milestones, "errors": errors, "console_errors": console_errors, "failed_requests": failed, "resources": resources, "remote_requests": [url for url in request_urls if url.startswith(("http://", "https://")) and "127.0.0.1" not in url and "localhost" not in url], "snapshot": snapshot},
            "warm": warm,
            "interactions": interaction,
        }
    finally:
        page.close()
        context.close()


def aggregate_performance_samples(rows: list[dict], phase: str, browser_version: str, source: dict | None, sample_count: int) -> dict:
    def merge_operation_rows(values):
        merged = {}
        for row in values:
            for key, value in row.items():
                merged.setdefault(key, []).append(value["median"])
        return {key: quantiles(value) for key, value in merged.items()}

    cold = [row["cold"] for row in rows]
    warm = [row["warm"] for row in rows]
    longtasks = [task for row in cold for task in row["resources"]["longtasks"]]
    memory = [row["resources"]["memory"] for row in cold]
    return {
        "browser": "Chromium",
        "viewport": {"width": 1440, "height": 900},
        "phase": phase,
        "sample_count": sample_count,
        "environment_signature": performance_environment_signature("chromium", browser_version, {"width": 1440, "height": 900}, False, False, phase, sample_count),
        "source_binding": source,
        "cold_milestones": {key: quantiles([row["milestones"][key] for row in cold]) for key in cold[0]["milestones"]},
        "warm_milestones": {key: quantiles([row[key] for row in warm]) for key in warm[0]},
        "interactions": merge_operation_rows([row["interactions"] for row in rows]),
        "request_behavior": {"resources": quantiles([row["resources"]["resources"] for row in cold]), "transfer_bytes": quantiles([row["resources"]["transfer"] for row in cold]), "remote_requests": sum(len(row["remote_requests"]) for row in cold), "failed_requests": sum(len(row["failed_requests"]) for row in cold)},
        "runtime_growth": {"map_creations": quantiles([row["snapshot"]["runtime"]["mapCreations"] for row in cold]), "map_removals": quantiles([row["snapshot"]["runtime"]["mapRemovals"] for row in cold]), "markers": quantiles([row["snapshot"]["map"]["photo_markers"] for row in cold]), "canvas": quantiles([row["snapshot"]["map"]["canvas_count"] for row in cold])},
        "longtasks_ms": quantiles(longtasks),
        "memory_js_heap": memory,
        "raw_samples": [{"cold_milestones": row["cold"]["milestones"], "warm_milestones": row["warm"], "interactions": row["interactions"]} for row in rows],
        "limitations": ["Chromium CI memory/long-task APIs are capability-dependent; no phone/device result is asserted.", "Each sample uses a fresh Playwright browser context and page; paired runs share only the browser process and host."]
    }


def performance_samples(playwright, samples: int, phase: str, shots: Path, url: str = MODULAR_URL, source: dict | None = None) -> dict:
    browser = playwright.chromium.launch(headless=True, timeout=90000)
    try:
        rows = [performance_sample(playwright, browser, url, source) for _ in range(samples)]
        return aggregate_performance_samples(rows, phase, browser.version, source, samples)
    finally:
        browser.close()


def signature_differences(candidate: dict, baseline: dict) -> list[dict]:
    differences = []

    def walk(left, right, path: str) -> None:
        if isinstance(left, dict) and isinstance(right, dict):
            for key in sorted(set(left) | set(right)):
                if key not in left or key not in right:
                    differences.append({"field": f"{path}.{key}", "candidate": left.get(key), "baseline": right.get(key)})
                else:
                    walk(left[key], right[key], f"{path}.{key}")
            return
        if left != right:
            differences.append({"field": path, "candidate": left, "baseline": right})

    walk(candidate, baseline, "environment")
    return differences


def _binding_issue(binding: dict | None, label: str) -> str | None:
    if not binding:
        return f"{label} source binding is missing"
    if binding.get("binding") != "exact_commit" or binding.get("status") != "PASS" or binding.get("source_worktree_dirty"):
        return f"{label} source binding is not an exact clean commit"
    claimed = binding.get("claimed_revision")
    checked_out = binding.get("checked_out_revision")
    if claimed and checked_out and claimed != checked_out:
        return f"{label} source binding revision/fingerprint mismatch"
    return None


def _metric_value(sample: dict, group: str, key: str):
    value = sample.get(group, {}).get(key)
    if isinstance(value, dict):
        return value.get("median")
    return value


MIN_PAIRED_PAIRS = 6
MIN_PAIRED_BLOCKS = 2
MIN_PAIRS_PER_BLOCK = 2


def _paired_metric_evidence(paired_measurements: list[dict], group: str, key: str) -> dict:
    rows = []
    for pair in paired_measurements:
        candidate_value = _metric_value(pair.get("candidate", {}), group, key)
        baseline_value = _metric_value(pair.get("baseline", {}), group, key)
        if candidate_value is None or baseline_value is None:
            continue
        delta = float(candidate_value) - float(baseline_value)
        relative = (delta / float(baseline_value) * 100.0) if baseline_value else None
        rows.append(
            {
                "pair": pair.get("pair"),
                "block": pair.get("block") or pair.get("block_id") or "unlabeled",
                "order": pair.get("order"),
                "candidate": round(float(candidate_value), 3),
                "baseline": round(float(baseline_value), 3),
                "delta": round(delta, 3),
                "relative_delta_pct": round(relative, 3) if relative is not None else None,
            }
        )

    deltas = [row["delta"] for row in rows]
    baselines = [row["baseline"] for row in rows]
    relative_deltas = [row["relative_delta_pct"] for row in rows if row["relative_delta_pct"] is not None]
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(str(row["block"]), []).append(row)

    blocks = []
    for block, block_rows in grouped.items():
        block_deltas = [row["delta"] for row in block_rows]
        order_counts = {"candidate>baseline": 0, "baseline>candidate": 0}
        for row in block_rows:
            order = row.get("order") or []
            if list(order) == ["candidate", "baseline"]:
                order_counts["candidate>baseline"] += 1
            elif list(order) == ["baseline", "candidate"]:
                order_counts["baseline>candidate"] += 1
        median_delta = statistics.median(block_deltas)
        blocks.append(
            {
                "block": block,
                "pair_count": len(block_rows),
                "order_counts": order_counts,
                "deltas": quantiles(block_deltas),
                "median_delta": round(median_delta, 3),
                "direction": "candidate_slower" if median_delta > 0 else "candidate_not_slower",
            }
        )

    block_medians = [block["median_delta"] for block in blocks]
    center = statistics.median(deltas) if deltas else 0.0
    deviations = [abs(delta - center) for delta in deltas]
    mad_sigma = 1.4826 * statistics.median(deviations) if deviations else 0.0
    block_stdev = statistics.stdev(block_medians) if len(block_medians) > 1 else 0.0
    relative_center = statistics.median(relative_deltas) if relative_deltas else 0.0
    relative_deviations = [abs(delta - relative_center) for delta in relative_deltas]
    relative_mad_sigma = 1.4826 * statistics.median(relative_deviations) if relative_deviations else 0.0
    relative_block_deltas = []
    for block in blocks:
        values = [row["relative_delta_pct"] for row in grouped[block["block"]] if row["relative_delta_pct"] is not None]
        if values:
            relative_block_deltas.append(statistics.median(values))
    relative_block_stdev = statistics.stdev(relative_block_deltas) if len(relative_block_deltas) > 1 else 0.0
    noise_envelope = max(mad_sigma, block_stdev)
    relative_noise_envelope = max(relative_mad_sigma, relative_block_stdev)
    balanced_blocks = all(
        block["pair_count"] >= MIN_PAIRS_PER_BLOCK
        and all(count > 0 for count in block["order_counts"].values())
        for block in blocks
    )
    sufficient = len(rows) >= MIN_PAIRED_PAIRS and len(blocks) >= MIN_PAIRED_BLOCKS and balanced_blocks
    positive_pairs = sum(delta > 0 for delta in deltas)
    negative_pairs = sum(delta < 0 for delta in deltas)
    block_positive = bool(blocks) and all(block["median_delta"] > 0 for block in blocks)
    block_nonpositive = bool(blocks) and all(block["median_delta"] <= 0 for block in blocks)
    block_direction_consistent = block_positive or block_nonpositive
    stable_non_regression = sufficient and block_nonpositive and all(delta <= noise_envelope for delta in deltas)
    decisive_regression = (
        sufficient
        and block_positive
        and positive_pairs == len(deltas)
        and center > noise_envelope
        and all(block["median_delta"] > noise_envelope for block in blocks)
    )
    return {
        "pair_count": len(rows),
        "block_count": len(blocks),
        "rows": rows,
        "blocks": blocks,
        "order_balanced": balanced_blocks,
        "sufficient": sufficient,
        "positive_pairs": positive_pairs,
        "negative_pairs": negative_pairs,
        "consistent_candidate_slower": bool(rows) and all(delta > 0 for delta in deltas),
        "direction_consistent_across_blocks": block_direction_consistent,
        "ambiguous_direction": not sufficient or not block_direction_consistent,
        "baseline_jitter": quantiles(baselines),
        "delta_distribution": quantiles(deltas),
        "relative_delta_distribution_pct": quantiles(relative_deltas),
        "noise_estimate": {
            "pair_delta_mad_sigma_ms": round(mad_sigma, 3),
            "block_median_stdev_ms": round(block_stdev, 3),
            "noise_envelope_ms": round(noise_envelope, 3),
            "relative_pair_delta_mad_sigma_pct": round(relative_mad_sigma, 3),
            "relative_block_median_stdev_pct": round(relative_block_stdev, 3),
            "relative_noise_envelope_pct": round(relative_noise_envelope, 3),
        },
        "materiality_guard_ms": round(noise_envelope, 3),
        "materiality_guard_relative_pct": round(relative_noise_envelope, 3),
        "stable_non_regression": stable_non_regression,
        "decisive_regression": decisive_regression,
        "rationale": (
            "all order-balanced paired deltas are slower in every block and exceed the observed paired noise envelope"
            if decisive_regression
            else "all balanced blocks are non-slower and positive pair noise stays within the observed envelope"
            if stable_non_regression
            else "paired direction, block materiality, or the minimum balanced evidence design is unresolved"
        ),
    }


def compare_performance(candidate: dict, baseline: dict | None, paired_measurements: list[dict] | None = None) -> dict:
    candidate_signature = candidate.get("environment_signature") if candidate else None
    baseline_signature = baseline.get("environment_signature") if baseline else None
    base_result = {
        "candidate_environment_signature": candidate_signature,
        "baseline_environment_signature": baseline_signature,
        "method": "paired order-balanced blocks are primary; distribution guard is recorded but cannot override paired evidence",
        "candidate_revision": (candidate_signature or {}).get("source_revision") or (candidate.get("source_binding") or {}).get("checked_out_revision") if candidate else None,
        "baseline_revision": (baseline_signature or {}).get("source_revision") or (baseline.get("source_binding") or {}).get("checked_out_revision") if baseline else None,
        "comparisons": [],
        "failures": [],
    }
    if not baseline:
        return {**base_result, "status": "VERIFY_REQUIRED", "reason": "Exact-base performance evidence was not found; no regression guard can be derived."}
    if not candidate_signature or not baseline_signature:
        return {**base_result, "status": "VERIFY_REQUIRED", "reason": "Both performance samples must carry an environment signature before a hard comparison is allowed.", "mismatch": [{"field": "environment_signature", "candidate": candidate_signature, "baseline": baseline_signature}]}
    binding_mismatches = [issue for issue in (_binding_issue(candidate.get("source_binding"), "candidate"), _binding_issue(baseline.get("source_binding"), "baseline")) if issue]
    if binding_mismatches:
        return {**base_result, "status": "VERIFY_REQUIRED", "reason": "Source/revision binding is incomplete or mismatched; a hard comparison is not evidence-supported.", "mismatch": [{"field": "source_binding", "reason": issue} for issue in binding_mismatches]}
    mismatches = signature_differences(candidate_signature, baseline_signature)
    if mismatches:
        return {**base_result, "status": "VERIFY_REQUIRED", "reason": "Performance environments are materially incompatible; a hard regression conclusion is not evidence-supported.", "mismatch": mismatches}
    comparisons=[]; failures=[]; verify_reasons=[]
    if paired_measurements is None:
        return {**base_result, "status": "VERIFY_REQUIRED", "reason": "Paired same-runner evidence is required for a hard performance classification; distribution-only evidence is non-decisive."}
    for group in ("cold_milestones","warm_milestones","interactions"):
        cand_group=candidate.get(group,{})
        base_group=baseline.get(group,{})
        for key, cstats in cand_group.items():
            bstats=base_group.get(key)
            metric=f"{group}.{key}"
            if not bstats or bstats.get("count",0)<3 or cstats.get("count",0)<3:
                comparisons.append({"metric":metric,"status":"VERIFY_REQUIRED","reason":"sample count below evidence guard","baseline":bstats,"candidate":cstats}); verify_reasons.append(metric); continue
            distribution_guard=max(bstats["max"], bstats["mean"]+3*bstats.get("stdev",0))
            pair_evidence = _paired_metric_evidence(paired_measurements, group, key)
            if pair_evidence["decisive_regression"]:
                status="FAIL"
            elif pair_evidence["stable_non_regression"]:
                status="PASS"
            else:
                status="VERIFY_REQUIRED"
                verify_reasons.append(metric)
            comparisons.append({"metric":metric,"baseline":bstats,"candidate":cstats,"distribution_guard":round(distribution_guard,3),"guard":round(distribution_guard,3),"status":status,"pair_evidence":pair_evidence,"rationale":pair_evidence["rationale"],"note":"The unpaired baseline guard is retained for audit only and cannot convert a slower paired result to PASS." if cstats["median"]<=distribution_guard and pair_evidence["decisive_regression"] else None})
            if status=="FAIL": failures.append(metric)
    return {**base_result, "status":"FAIL" if failures else "VERIFY_REQUIRED" if verify_reasons else "PASS","comparisons":comparisons,"failures":failures,"verify_reasons":verify_reasons}


def free_local_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def wait_for_server(url: str, process: subprocess.Popen) -> None:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("temporary base QA server exited before becoming ready")
        try:
            with urlopen(url, timeout=1):
                return
        except Exception:
            time.sleep(0.2)
    raise RuntimeError(f"temporary base QA server did not become ready at {url}")


def _comparison_sample(row: dict) -> dict:
    return {"cold_milestones": row["cold"]["milestones"], "warm_milestones": row["warm"], "interactions": row["interactions"]}


def _terminate_server(server: subprocess.Popen | None) -> None:
    if server is None:
        return
    server.terminate()
    try:
        server.wait(timeout=5)
    except subprocess.TimeoutExpired:
        server.kill()


def same_environment_paired_samples(
    playwright,
    shots: Path,
    candidate_source: dict,
    candidate_url: str = MODULAR_URL,
    block_count: int = 2,
    pairs_per_block: int = 4,
) -> dict:
    """Measure isolated base/candidate pairs in independent balanced blocks.

    Each block uses a fresh browser process and each side of every pair uses a
    fresh context/page. The order is balanced inside every block, while the
    first side is reversed between blocks. This makes paired deltas primary and
    leaves enough observations to expose block-to-block jitter.
    """
    worktree = None
    server = None
    temporary = None
    browser = None
    try:
        temporary = tempfile.mkdtemp(prefix="gate5-base-", dir=ROOT.parent)
        worktree = Path(temporary) / "source"
        added = subprocess.run(
            ["git", "worktree", "add", "--detach", "--quiet", str(worktree), BASE_REVISION],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        if added.returncode:
            raise RuntimeError(f"could not create detached base worktree: {added.stderr.strip()}")
        build = worktree / ".build"
        built = subprocess.run(
            [sys.executable, str(worktree / "scripts/build_map_first.py"), "--output-dir", str(build)],
            cwd=worktree,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if built.returncode:
            raise RuntimeError(f"detached base build failed: {built.stderr[-1200:]}")
        port = free_local_port()
        url = f"http://127.0.0.1:{port}/index.html"
        server = subprocess.Popen(
            [sys.executable, str(worktree / "scripts/serve_map.py"), "--port", str(port), "--directory", str(build / "modular")],
            cwd=worktree,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )
        wait_for_server(url, server)
        base_binding = source_binding(BASE_REVISION, worktree)
        if base_binding["binding"] != "exact_commit" or base_binding["status"] != "PASS":
            raise RuntimeError(f"detached base source binding was not exact: {base_binding}")
        candidate_rows, baseline_rows, paired_measurements, schedule = [], [], [], []
        browser_version = None
        pair_index = 0
        order_by_block = []
        for block_index in range(block_count):
            browser = playwright.chromium.launch(headless=True, timeout=90000)
            browser_version = browser.version
            block_orders = []
            try:
                for pair_in_block in range(pairs_per_block):
                    pair_index += 1
                    first_candidate = (block_index + pair_in_block) % 2 == 0
                    order = ("candidate", "baseline") if first_candidate else ("baseline", "candidate")
                    block_orders.append("candidate>baseline" if first_candidate else "baseline>candidate")
                    pair_rows = {}
                    for position, side in enumerate(order, start=1):
                        source = candidate_source if side == "candidate" else base_binding
                        sample = performance_sample(playwright, browser, candidate_url if side == "candidate" else url, source)
                        pair_rows[side] = _comparison_sample(sample)
                        (candidate_rows if side == "candidate" else baseline_rows).append(sample)
                        schedule.append({"block": block_index + 1, "pair": pair_index, "pair_in_block": pair_in_block + 1, "position": position, "side": side, "revision": source.get("checked_out_revision"), "fresh_context": True})
                    paired_measurements.append({"block": block_index + 1, "pair": pair_index, "pair_in_block": pair_in_block + 1, "order": list(order), "candidate": pair_rows["candidate"], "baseline": pair_rows["baseline"]})
            finally:
                browser.close()
                browser = None
            order_by_block.append(block_orders)
        total_pairs = len(paired_measurements)
        candidate_samples = aggregate_performance_samples(candidate_rows, "candidate", browser_version, candidate_source, total_pairs)
        baseline_samples = aggregate_performance_samples(baseline_rows, "baseline", browser_version, base_binding, total_pairs)
        comparison = compare_performance(candidate_samples, baseline_samples, paired_measurements)
        return {
            "status": "PASS",
            "revision": BASE_REVISION,
            "source_binding": base_binding,
            "samples": baseline_samples,
            "candidate_samples": candidate_samples,
            "comparison": comparison,
            "paired_measurements": paired_measurements,
            "measurement_schedule": {
                "method": "two-independent-order-balanced-blocks-same-runner",
                "block_count": block_count,
                "pairs_per_block": pairs_per_block,
                "total_pairs": total_pairs,
                "sample_count_per_side": total_pairs,
                "order_by_block": order_by_block,
                "fresh_context_per_measurement": True,
                "independent_browser_process_per_block": True,
                "same_runner_environment": True,
                "candidate_server": {"url": candidate_url, "build": ".build/modular", "isolated": True},
                "baseline_server": {"url": url, "build": str(build / "modular"), "revision": BASE_REVISION, "isolated": True},
                "schedule": schedule,
            },
        }
    except Exception as error:
        return {"status": "VERIFY_REQUIRED", "revision": BASE_REVISION, "reason": str(error)}
    finally:
        if browser is not None:
            browser.close()
        _terminate_server(server)
        if worktree is not None:
            subprocess.run(["git", "worktree", "remove", "--force", str(worktree)], cwd=ROOT, capture_output=True, text=True)
            try:
                worktree.parent.rmdir()
            except OSError:
                pass
        elif temporary is not None:
            try:
                Path(temporary).rmdir()
            except OSError:
                pass


def same_environment_base_samples(playwright, shots: Path, source: dict) -> dict:
    """Compatibility wrapper exposing the baseline side of the paired run."""

    paired = same_environment_paired_samples(playwright, shots, source)
    if paired.get("status") != "PASS":
        return paired
    return {"status": "PASS", "revision": BASE_REVISION, "source_binding": paired["source_binding"], "samples": paired["samples"], "measurement_schedule": paired["measurement_schedule"]}
def matrix_case(playwright, browser_name: str, width: int, height: int, touch: bool, phase: str, shots: Path) -> dict:
    browser=getattr(playwright,browser_name).launch(headless=True,timeout=90000); context=browser.new_context(viewport={"width":width,"height":height},has_touch=touch,is_mobile=width<=390); page=context.new_page(); errors=[]; console_errors=[]; failed=[]; errors_for(page,errors,console_errors,failed); row={"browser":browser_name,"viewport":{"width":width,"height":height},"touch":touch,"errors":errors,"console_errors":console_errors,"failed_requests":failed}
    try:
        wait_ready(page); row["checks"]=js_checks(page); overall_name=f"{browser_name}_{width}_overall"; row["visual"]={"screenshot":screenshot(page,shots,overall_name)}; row["visual"]["map_visual_integrity"]=map_visual_integrity(page,shots,overall_name,ROOT/"QA/gate5/screenshots/baseline"/f"{browser_name}_{width}_overall.png"); page.locator('[data-route=A2]').click(); page.wait_for_timeout(100); page.locator('[data-tab=details]').click(); page.wait_for_timeout(100); row["checks"]["detail"]=js_checks(page); detail_name=f"{browser_name}_{width}_detail"; row["visual"]["detail_screenshot"]=screenshot(page,shots,detail_name); row["visual"]["detail_map_visual_integrity"]=map_visual_integrity(page,shots,detail_name,ROOT/"QA/gate5/screenshots/baseline"/f"{browser_name}_{width}_detail.png"); row["status"]="PASS" if not errors and not console_errors and row["checks"]["canvas"]==1 and row["checks"]["overflow"]==0 and all(x["hit"] for x in row["checks"]["occluded"]) and row["visual"]["map_visual_integrity"].get("status")=="PASS" and row["visual"]["detail_map_visual_integrity"].get("status")=="PASS" else "FAIL"
    except Exception as error: row["status"]="UNVERIFIED"; row["error"]=f"{type(error).__name__}: {error}"
    browser.close(); return row


def finding_matrix(report: dict) -> dict:
    rows=[]
    rows.append({"finding":"E2 independent multimodal visual/usability acceptance","status":"VERIFY_REQUIRED","evidence":"candidate screenshots and objective checks only; implementation agent cannot self-certify"})
    rows.append({"finding":"real phone/device performance","status":"VERIFY_REQUIRED","evidence":"desktop Chromium performance APIs only; no field-device claim"})
    comparison = report.get("performance", {}).get("comparison", {})
    if comparison.get("status") != "PASS":
        rows.append({"finding":"same-environment performance comparability","status":comparison.get("status", "VERIFY_REQUIRED"),"evidence":{"reason":comparison.get("reason"),"mismatch":comparison.get("mismatch"),"candidate_environment_signature":comparison.get("candidate_environment_signature"),"baseline_environment_signature":comparison.get("baseline_environment_signature")}})
    binding = report.get("source_binding", {})
    if binding.get("status") != "PASS":
        rows.append({"finding":"exact candidate source binding","status":binding.get("status", "VERIFY_REQUIRED"),"evidence":binding})
    rows.append({"finding":"Gate 4 preservation","status":report.get("gate4_reference","VERIFY_REQUIRED"),"evidence":"canonical qualification QA/release/gate4.json when available"})
    rows.extend({"finding":f"browser {row['browser']} {row['viewport']['width']}x{row['viewport']['height']}","status":row.get("status","UNVERIFIED"),"evidence":row.get("visual",{})} for row in report.get("browser_matrix",[]))
    return {"schema_version":1,"candidate_head":report["candidate_head"],"candidate_fingerprint":report["candidate_fingerprint"],"rows":rows}


def gate4_reference(report: dict) -> str:
    path = ROOT / "QA/release/gate4_runtime.json"
    if not path.is_file():
        return "VERIFY_REQUIRED"
    try:
        evidence = json.loads(path.read_text())
    except json.JSONDecodeError:
        return "VERIFY_REQUIRED"
    if evidence.get("candidate_head") != report["candidate_head"]:
        return "VERIFY_REQUIRED"
    return "PASS" if evidence.get("status") == "PASS" else str(evidence.get("status", "VERIFY_REQUIRED"))


def performance_summary(report: dict) -> str:
    performance = report.get("performance", {})
    comparison = performance.get("comparison", {})
    schedule = performance.get("measurement_schedule", {}) or {}
    same_base = performance.get("same_environment_baseline", {}) or {}
    lines = [
        "gate5_performance_summary schema=1",
        f"baseline_revision={comparison.get('baseline_revision') or same_base.get('revision')}",
        f"candidate_revision={report.get('candidate_head')}",
        f"candidate_source_binding={json.dumps(report.get('source_binding', {}), sort_keys=True, separators=(',', ':'))}",
        f"baseline_source_binding={json.dumps(same_base.get('source_binding', {}), sort_keys=True, separators=(',', ':'))}",
        f"candidate_environment_signature={json.dumps(comparison.get('candidate_environment_signature'), sort_keys=True, separators=(',', ':'))}",
        f"baseline_environment_signature={json.dumps(comparison.get('baseline_environment_signature'), sort_keys=True, separators=(',', ':'))}",
        f"measurement_method={schedule.get('method', comparison.get('method'))}",
        f"measurement_order={','.join(schedule.get('order', [])) or 'unavailable'}",
        f"sample_count_candidate={performance.get('samples', {}).get('sample_count')}",
        f"sample_count_baseline={(same_base.get('samples') or {}).get('sample_count')}",
    ]
    for row in comparison.get("comparisons", []):
        lines.append("metric=" + row.get("metric", "") + " sample_count_baseline=" + str((row.get("baseline") or {}).get("count")) + " sample_count_candidate=" + str((row.get("candidate") or {}).get("count")) + " baseline_distribution=" + json.dumps(row.get("baseline"), sort_keys=True, separators=(",", ":")) + " candidate_distribution=" + json.dumps(row.get("candidate"), sort_keys=True, separators=(",", ":")) + " distribution_guard=" + str(row.get("distribution_guard", row.get("guard"))) + " paired_evidence=" + json.dumps(row.get("pair_evidence"), sort_keys=True, separators=(",", ":")) + " rationale=" + json.dumps(row.get("rationale"), sort_keys=True) + " status=" + str(row.get("status")))
    lines.append(f"status={comparison.get('status')}")
    lines.append(f"failing_metrics={json.dumps(comparison.get('failures', []), sort_keys=True)}")
    lines.append(f"verify_metrics={json.dumps(comparison.get('verify_reasons', []), sort_keys=True)}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--phase",choices=("baseline","candidate"),default="candidate")
    parser.add_argument("--output",default=str(DEFAULT_OUTPUT))
    parser.add_argument("--expected-revision",help="exact candidate revision claimed by canonical qualification")
    args=parser.parse_args()
    output=Path(args.output); output=output if output.is_absolute() else ROOT/output; output.parent.mkdir(parents=True,exist_ok=True)
    shot_root=ROOT/"QA/gate5/screenshots"/args.phase; shot_root.mkdir(parents=True,exist_ok=True)
    binding=source_binding(args.expected_revision)
    report={"schema_version":1,"status":"FAIL","gate":"production_readiness_gate_5","phase":args.phase,"candidate_head":revision(),"candidate_fingerprint":binding["source_fingerprint"],"source_binding":binding,"captured_at":now(),"environment":{"platform":platform.platform(),"python":sys.version.split()[0],"ci":os.environ.get("CI"),"url":MODULAR_URL,"playwright":None},"contract":rel(CONTRACT_PATH),"browser_matrix":[],"workflow":{},"performance":{},"verify_required":[],"failures":[]}
    if binding["binding"] == "mismatch":
        report["status"]="VERIFY_REQUIRED"
        report["verify_required"].append(binding["reason"])
        output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
        FINDING_MATRIX.parent.mkdir(parents=True,exist_ok=True); FINDING_MATRIX.write_text(json.dumps(finding_matrix(report),ensure_ascii=False,indent=2)+"\n")
        print(json.dumps({"status":report["status"],"phase":args.phase,"candidate_head":report["candidate_head"],"failures":report["failures"],"verify_required":report["verify_required"]},ensure_ascii=False,indent=2))
        return 1
    with sync_playwright() as playwright:
        report["environment"]["playwright"]="sync_api"
        report["environment"]["browser_versions"]={}
        for browser_name in ("chromium","firefox","webkit"):
            browser=getattr(playwright,browser_name).launch(headless=True); report["environment"]["browser_versions"][browser_name]=browser.version; browser.close()
        for browser_name,width,height,touch in MATRIX:
            report["browser_matrix"].append(matrix_case(playwright,browser_name,width,height,touch,args.phase,shot_root))
        browser=playwright.chromium.launch(headless=True,timeout=90000); context=browser.new_context(viewport={"width":1440,"height":900}); page=context.new_page(); errors=[]; console_errors=[]; failed=[]; errors_for(page,errors,console_errors,failed); wait_ready(page); report["workflow"]["main"]=run_workflow(page,shot_root); report["workflow"]["states"]=sparse_state_checks(page); report["workflow"]["keyboard"]=keyboard_checks(page); report["workflow"]["provider_recovery"]=provider_recovery(page); page.close(); context.close(); browser.close()
        if args.phase == "candidate":
            paired = same_environment_paired_samples(playwright, shot_root, binding)
            report["performance"]["samples"] = paired.get("candidate_samples", {})
            report["performance"]["same_environment_baseline"] = {
                "status": paired.get("status", "VERIFY_REQUIRED"),
                "revision": paired.get("revision", BASE_REVISION),
                "source_binding": paired.get("source_binding"),
                "samples": paired.get("samples"),
                "measurement_schedule": paired.get("measurement_schedule"),
                "reason": paired.get("reason"),
            }
            report["performance"]["measurement_schedule"] = paired.get("measurement_schedule", {})
            report["performance"]["paired_measurements"] = paired.get("paired_measurements", [])
            comparison = paired.get("comparison") or compare_performance(report["performance"]["samples"], paired.get("samples"), paired.get("paired_measurements"))
            comparison["baseline_source"] = "temporary_detached_worktree_order_balanced"
            comparison["baseline_revision"] = BASE_REVISION
            baseline_artifact = {
                "schema_version": 1,
                "status": "PASS" if paired.get("status") == "PASS" and paired.get("samples") else "VERIFY_REQUIRED",
                "gate": "production_readiness_gate_5",
                "phase": "baseline",
                "candidate_head": BASE_REVISION,
                "source_binding": paired.get("source_binding"),
                "captured_at": now(),
                "performance": {"samples": paired.get("samples"), "measurement_schedule": paired.get("measurement_schedule")},
            }
            BASELINE_OUTPUT.write_text(json.dumps(baseline_artifact, ensure_ascii=False, indent=2) + "\n")
            PAIRED_COMPARISON_OUTPUT.write_text(json.dumps({"schema_version": 1, "candidate_revision": report["candidate_head"], "baseline_revision": BASE_REVISION, "candidate_source_binding": binding, "baseline_source_binding": paired.get("source_binding"), "candidate_environment_signature": (report["performance"].get("samples") or {}).get("environment_signature"), "baseline_environment_signature": (paired.get("samples") or {}).get("environment_signature"), "measurement_schedule": paired.get("measurement_schedule"), "paired_measurements": paired.get("paired_measurements", []), "comparison": comparison}, ensure_ascii=False, indent=2) + "\n")
        else:
            report["performance"]["samples"] = performance_samples(playwright, 3, args.phase, shot_root, source=binding)
            comparison = compare_performance(report["performance"]["samples"], None)
    report["performance"]["comparison"]=comparison
    report["verify_required"]=["E2 independent multimodal visual/usability acceptance","real field-device performance and memory claim"]
    report["failures"]=[f"browser {r['browser']} {r['viewport']['width']} status={r.get('status')}" for r in report["browser_matrix"] if r.get("status")!="PASS"]
    dom=report["workflow"].get("main",{}).get("accessibility",{}).get("dom",{})
    accessibility=report["workflow"].get("main",{}).get("accessibility",{})
    reflow=accessibility.get("reflow_200",{})
    motion=accessibility.get("reduced_motion",{})
    contrast_failures=[row["selector"] for row in accessibility.get("contrast",[]) if row.get("pass") is False]
    if dom and (dom.get("overflow",0)>0 or not all(dom.get("semantics",{}).values()) or any(not x.get("hit") for x in dom.get("occluded",[])) or reflow.get("overflow",0)>0 or reflow.get("hidden_critical") or not motion.get("media") or contrast_failures):
        report["failures"].append("main rendered accessibility/occlusion checks")
    if not report["workflow"].get("keyboard",{}).get("escape_preview_hidden",False): report["failures"].append("keyboard Escape preview close")
    if not report["workflow"].get("keyboard",{}).get("escape_focus_return",False) or not report["workflow"].get("main",{}).get("flows",{}).get("panel",{}).get("focus_return",False): report["failures"].append("focus return after overlay/panel")
    sparse=report["workflow"].get("states",{}).get("sparse_empty",{})
    if not sparse.get("timelineEmpty") or not sparse.get("detailsEmpty") or sparse.get("overflow",0)>0 or not report["workflow"].get("states",{}).get("freshness_visible"): report["failures"].append("empty/sparse/freshness state feedback")
    if report["performance"]["comparison"].get("status")=="FAIL": report["failures"].append("evidence-derived performance regression guard")
    elif args.phase=="candidate" and report["performance"]["comparison"].get("status")!="PASS":
        report["verify_required"].append("same-environment performance comparison: " + report["performance"]["comparison"].get("reason", "comparison is not evidence-complete"))
    if binding["status"]!="PASS" and args.expected_revision:
        report["verify_required"].append("exact candidate source binding is not a clean checked-out revision")
    report["gate4_reference"] = gate4_reference(report)
    report["status"]="FAIL" if report["failures"] else "VERIFY_REQUIRED" if (args.phase=="candidate" and (report["performance"]["comparison"].get("status")!="PASS" or (args.expected_revision and binding["status"]!="PASS"))) else "PASS"
    summary = performance_summary(report)
    PERFORMANCE_SUMMARY_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    PERFORMANCE_SUMMARY_OUTPUT.write_text(summary)
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    FINDING_MATRIX.parent.mkdir(parents=True,exist_ok=True); FINDING_MATRIX.write_text(json.dumps(finding_matrix(report),ensure_ascii=False,indent=2)+"\n")
    print(summary, end="")
    print(json.dumps({"status":report["status"],"phase":args.phase,"candidate_head":report["candidate_head"],"failures":report["failures"],"verify_required":report["verify_required"]},ensure_ascii=False,indent=2))
    return 0 if report["status"]=="PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
