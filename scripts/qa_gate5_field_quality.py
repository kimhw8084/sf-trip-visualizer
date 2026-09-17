"""Gate 5 field-quality evidence: rendered UX, accessibility, browser matrix, and baseline.

This is a focused suite attached to the canonical pipeline. It records objective
browser observations and screenshots; it is not a substitute for independent
visual/usability acceptance or WCAG certification.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import statistics
import sys
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from qa_config import MODULAR_URL


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "manifests" / "gate5_field_quality_contract.json"
DEFAULT_OUTPUT = ROOT / "QA/gate5/candidate.json"
FINDING_MATRIX = ROOT / "QA/gate5/finding_matrix.json"
MATRIX = (("chromium", 1440, 900, False), ("chromium", 834, 1112, True), ("chromium", 390, 844, True), ("firefox", 1440, 900, False), ("firefox", 834, 1112, True), ("firefox", 390, 844, True), ("webkit", 1440, 900, False), ("webkit", 834, 1112, True), ("webkit", 390, 844, True))


def revision() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def candidate_fingerprint() -> dict:
    paths = subprocess.check_output(
        ["git", "ls-files", "-co", "--exclude-standard"], cwd=ROOT, text=True
    ).splitlines()
    included = []
    for path in sorted(paths):
        if path.startswith(("QA/", ".build/")):
            continue
        full = ROOT / path
        if full.is_file():
            included.append((path, hashlib.sha256(full.read_bytes()).hexdigest()))
    payload = "\n".join(f"{path}\0{digest}" for path, digest in included).encode()
    status = subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=all"], cwd=ROOT, text=True
    )
    return {
        "sha256": hashlib.sha256(payload).hexdigest(),
        "file_count": len(included),
        "tracked_head": revision(),
        "worktree_dirty": bool(status.strip()),
        "excluded_from_hash": ["QA/", ".build/"],
    }


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def quantiles(values: list[float]) -> dict:
    if not values:
        return {"count": 0, "min": None, "median": None, "p95": None, "max": None, "mean": None, "stdev": None}
    values = sorted(float(v) for v in values)
    result = {"count": len(values), "min": values[0], "median": statistics.median(values), "max": values[-1], "mean": statistics.mean(values), "stdev": statistics.stdev(values) if len(values) > 1 else 0.0}
    if len(values) >= 3:
        index = min(len(values) - 1, math.ceil(len(values) * 0.95) - 1)
        result["p95"] = values[index]
    else:
        result["p95"] = None
    return {key: round(value, 3) if isinstance(value, float) else value for key, value in result.items()}


def wait_ready(page) -> dict:
    milestones = {}
    page.goto(MODULAR_URL, wait_until="domcontentloaded", timeout=90000)
    milestones["dom_content_loaded"] = page.evaluate("performance.now()")
    page.wait_for_function("window.__tripApp?.map()?.isStyleLoaded()", timeout=30000)
    milestones["smart_style_ready"] = page.evaluate("performance.now()")
    page.wait_for_function("document.querySelectorAll('.photo-marker').length===window.__tripApp.DATA.markers.length", timeout=30000)
    page.wait_for_function("document.querySelectorAll('[data-timeline]').length>0 && !document.getElementById('loadingScreen')", timeout=30000)
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


def run_workflow(page, shots: Path, touch: bool = False) -> dict:
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


def keyboard_checks(page) -> dict:
    page.goto(MODULAR_URL, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_function("window.__tripApp?.map()?.isStyleLoaded()", timeout=30000)
    page.wait_for_function("!document.getElementById('loadingScreen')", timeout=30000)
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


def provider_recovery(page) -> dict:
    page.goto(MODULAR_URL, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_function("window.__tripApp?.map()?.isStyleLoaded()", timeout=30000)
    page.wait_for_function("!document.getElementById('loadingScreen')", timeout=30000)
    page.route("https://**/*", lambda route: route.abort())
    before = page.evaluate("()=>window.__tripApp.runtimeSnapshot()")
    started = time.perf_counter(); page.evaluate("async()=>await window.__tripApp.chooseProvider('satellite')"); page.wait_for_function("window.__tripApp.state.provider==='vector'", timeout=15000)
    elapsed = (time.perf_counter()-started)*1000
    after = page.evaluate("()=>window.__tripApp.runtimeSnapshot()")
    return {"elapsed_ms":round(elapsed,3),"before":before,"after":after,"state_preserved":before["planning_state"]==after["planning_state"],"smart_active":after["provider"]=="vector","canvas":after["map"]["canvas_count"],"fallback_note":page.locator('#fallbackNote').inner_text()}


def sparse_state_checks(page) -> dict:
    page.goto(MODULAR_URL, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_function("window.__tripApp?.map()?.isStyleLoaded()", timeout=30000)
    page.wait_for_function("!document.getElementById('loadingScreen')", timeout=30000)
    page.evaluate("""async()=>{const a=window.__tripApp;a.state.routes=new Set(['A1']);a.state.date='10/3';a.state.region='yosemite';a.state.selected=null;a.renderTimeline();a.renderDetail(null);await a.drawMap(false)}""")
    page.wait_for_timeout(140)
    sparse=page.evaluate("""()=>({timelineEmpty:!!document.querySelector('#timelinePane .empty'),detailsEmpty:!!document.querySelector('#detailsPane .empty'),markers:document.querySelectorAll('.photo-marker').length,filter:document.querySelector('#activeFilterSummary')?.innerText,overflow:document.documentElement.scrollWidth-innerWidth})""")
    page.evaluate("""async()=>{const a=window.__tripApp;a.state.routes=new Set(Object.keys(a.DATA.routes));a.state.date='all';a.state.region='overall';a.renderTimeline();a.renderDetail(null);await a.drawMap(false)}""")
    return {"sparse_empty":sparse,"freshness_visible":bool(page.locator('#freshnessNote').inner_text())}


def interaction_samples(page, count: int) -> dict:
    operations = {"route": [], "date": [], "region": [], "preview": [], "detail": [], "panel": [], "provider_recovery": []}
    page.goto(MODULAR_URL, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_function("window.__tripApp?.map()?.isStyleLoaded()", timeout=30000); page.wait_for_function("!document.getElementById('loadingScreen')", timeout=30000)
    for _ in range(count):
        for name, action in (("route", lambda: page.locator('[data-route=A2]').click()), ("date", lambda: page.locator('#dateSelect').select_option('10/8')), ("region", lambda: page.locator('[data-region=yosemite]').click())):
            started=time.perf_counter(); action(); page.wait_for_timeout(40); operations[name].append((time.perf_counter()-started)*1000)
        marker=page.locator('.photo-marker').first
        started=time.perf_counter(); marker.focus(); page.wait_for_timeout(60)
        if not page.locator('#previewCard.show').count():
            page.evaluate("()=>window.__tripApp.showPreview(document.querySelector('.photo-marker')?.dataset.placeKey,{})")
        operations['preview'].append((time.perf_counter()-started)*1000)
        action=page.locator('#previewCard .preview-action'); started=time.perf_counter(); action.click(); page.wait_for_timeout(40); operations['detail'].append((time.perf_counter()-started)*1000)
        started=time.perf_counter(); page.locator('#panelToggle').click(); page.wait_for_timeout(40)
        if page.locator('#mapFocus.show').count(): page.locator('#mapFocus .map-focus-head button').click(force=True)
        page.locator('#panelReopen').click(); page.wait_for_timeout(40); operations['panel'].append((time.perf_counter()-started)*1000)
        started=time.perf_counter(); page.route("https://**/*", lambda route: route.abort()); page.evaluate("async()=>await window.__tripApp.chooseProvider('satellite')"); page.wait_for_function("window.__tripApp.state.provider==='vector'", timeout=15000); operations['provider_recovery'].append((time.perf_counter()-started)*1000); page.unroute("https://**/*")
    return {key: quantiles(value) for key, value in operations.items()}


def performance_samples(playwright, samples: int, phase: str, shots: Path) -> dict:
    browser=playwright.chromium.launch(headless=True, timeout=90000); cold=[]; warm=[]; interactions=[]; request_rows=[]; runtime_rows=[]; longtasks=[]; memory=[]
    for index in range(samples):
        context=browser.new_context(viewport={"width":1440,"height":900}); page=context.new_page(); errors=[]; console_errors=[]; failed=[]; errors_for(page,errors,console_errors,failed); request_urls=[]; page.on("request",lambda request: request_urls.append(request.url)); milestones=wait_ready(page); snap=page.evaluate("()=>window.__tripApp.runtimeSnapshot()"); resources=page.evaluate("()=>({resources:performance.getEntriesByType('resource').length,transfer:performance.getEntriesByType('resource').reduce((s,x)=>s+(x.transferSize||0),0),longtasks:performance.getEntriesByType('longtask').map(x=>x.duration),memory:performance.memory?{used:performance.memory.usedJSHeapSize,total:performance.memory.totalJSHeapSize,limit:performance.memory.jsHeapSizeLimit}:null})"); cold.append({"milestones":milestones,"errors":errors,"console_errors":console_errors,"failed_requests":failed,"resources":resources,"remote_requests":[u for u in request_urls if u.startswith(('http://','https://')) and '127.0.0.1' not in u and 'localhost' not in u],"snapshot":snap});
        warm.append(wait_ready(page)); interactions.append(interaction_samples(page,1)); runtime_rows.append(page.evaluate("()=>window.__tripApp.runtimeSnapshot()")); longtasks.extend(resources["longtasks"]); memory.append(resources["memory"]); page.close(); context.close()
    browser.close();
    def merge_operation_rows(rows):
        out={};
        for row in rows:
            for key,value in row.items(): out.setdefault(key,[]).append(value["median"])
        return {key:quantiles(value) for key,value in out.items()}
    return {"browser":"Chromium","viewport":{"width":1440,"height":900},"phase":phase,"sample_count":samples,"cold_milestones":{key:quantiles([row["milestones"][key] for row in cold]) for key in cold[0]["milestones"]},"warm_milestones":{key:quantiles([row[key] for row in warm]) for key in warm[0]},"interactions":merge_operation_rows(interactions),"request_behavior":{"resources":quantiles([row["resources"]["resources"] for row in cold]),"transfer_bytes":quantiles([row["resources"]["transfer"] for row in cold]),"remote_requests":sum(len(row["remote_requests"]) for row in cold),"failed_requests":sum(len(row["failed_requests"]) for row in cold)},"runtime_growth":{"map_creations":quantiles([row["snapshot"]["runtime"]["mapCreations"] for row in cold]),"map_removals":quantiles([row["snapshot"]["runtime"]["mapRemovals"] for row in cold]),"markers":quantiles([row["snapshot"]["map"]["photo_markers"] for row in cold]),"canvas":quantiles([row["snapshot"]["map"]["canvas_count"] for row in cold])},"longtasks_ms":quantiles(longtasks),"memory_js_heap":memory,"limitations":["Chromium CI memory/long-task APIs are capability-dependent; no phone/device result is asserted.","warm milestone sampling reuses the same page after a reload."]}


def compare_performance(candidate: dict, baseline: dict | None) -> dict:
    if not baseline: return {"status":"VERIFY_REQUIRED","reason":"Exact-base performance evidence was not found; no regression guard can be derived."}
    comparisons=[]; failures=[]
    for group in ("cold_milestones","warm_milestones","interactions"):
        cand_group=candidate.get(group,{})
        base_group=baseline.get(group,{})
        for key, cstats in cand_group.items():
            bstats=base_group.get(key)
            if not bstats or bstats.get("count",0)<3 or cstats.get("count",0)<3:
                comparisons.append({"metric":f"{group}.{key}","status":"VERIFY_REQUIRED","reason":"sample count below evidence guard"}); continue
            guard=max(bstats["max"], bstats["mean"]+3*bstats.get("stdev",0))
            status="PASS" if cstats["median"]<=guard else "FAIL"
            if status=="FAIL" and bstats.get("stdev",0)<1.0:
                status="VERIFY_REQUIRED"
            comparisons.append({"metric":f"{group}.{key}","baseline":bstats,"candidate":cstats,"guard":round(guard,3),"status":status,"note":"Baseline spread is below 1 ms; a hard regression conclusion is not evidence-supported." if status=="VERIFY_REQUIRED" else None});
            if status=="FAIL": failures.append(f"{group}.{key}")
    return {"status":"FAIL" if failures else "PASS","method":"candidate median <= max(baseline max, baseline mean + 3*baseline stdev) for matching exact environment","comparisons":comparisons,"failures":failures}


def matrix_case(playwright, browser_name: str, width: int, height: int, touch: bool, phase: str, shots: Path) -> dict:
    browser=getattr(playwright,browser_name).launch(headless=True,timeout=90000); context=browser.new_context(viewport={"width":width,"height":height},has_touch=touch,is_mobile=width<=390); page=context.new_page(); errors=[]; console_errors=[]; failed=[]; errors_for(page,errors,console_errors,failed); row={"browser":browser_name,"viewport":{"width":width,"height":height},"touch":touch,"errors":errors,"console_errors":console_errors,"failed_requests":failed}
    try:
        wait_ready(page); row["checks"]=js_checks(page); row["visual"]={"screenshot":screenshot(page,shots,f"{browser_name}_{width}_overall")}; page.locator('[data-route=A2]').click(); page.wait_for_timeout(100); page.locator('[data-tab=details]').click(); page.wait_for_timeout(100); row["checks"]["detail"]=js_checks(page); row["visual"]["detail_screenshot"]=screenshot(page,shots,f"{browser_name}_{width}_detail"); row["status"]="PASS" if not errors and not console_errors and row["checks"]["canvas"]==1 and row["checks"]["overflow"]==0 and all(x["hit"] for x in row["checks"]["occluded"]) else "FAIL"
    except Exception as error: row["status"]="UNVERIFIED"; row["error"]=f"{type(error).__name__}: {error}"
    browser.close(); return row


def finding_matrix(report: dict) -> dict:
    rows=[]
    rows.append({"finding":"E2 independent multimodal visual/usability acceptance","status":"VERIFY_REQUIRED","evidence":"candidate screenshots and objective checks only; implementation agent cannot self-certify"})
    rows.append({"finding":"real phone/device performance","status":"VERIFY_REQUIRED","evidence":"desktop Chromium performance APIs only; no field-device claim"})
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


def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument("--phase",choices=("baseline","candidate"),default="candidate"); parser.add_argument("--output",default=str(DEFAULT_OUTPUT)); args=parser.parse_args(); output=Path(args.output); output=output if output.is_absolute() else ROOT/output; output.parent.mkdir(parents=True,exist_ok=True); shot_root=ROOT/"QA/gate5/screenshots"/args.phase; shot_root.mkdir(parents=True,exist_ok=True)
    report={"schema_version":1,"status":"FAIL","gate":"production_readiness_gate_5","phase":args.phase,"candidate_head":revision(),"candidate_fingerprint":candidate_fingerprint(),"captured_at":now(),"environment":{"platform":platform.platform(),"python":sys.version.split()[0],"ci":os.environ.get("CI"),"url":MODULAR_URL,"playwright":None},"contract":rel(CONTRACT_PATH),"browser_matrix":[],"workflow":{},"performance":{},"verify_required":[],"failures":[]}
    with sync_playwright() as playwright:
        report["environment"]["playwright"]="sync_api"
        report["environment"]["browser_versions"]={}
        for browser_name in ("chromium","firefox","webkit"):
            browser=getattr(playwright,browser_name).launch(headless=True); report["environment"]["browser_versions"][browser_name]=browser.version; browser.close()
        for browser_name,width,height,touch in MATRIX:
            report["browser_matrix"].append(matrix_case(playwright,browser_name,width,height,touch,args.phase,shot_root))
        browser=playwright.chromium.launch(headless=True,timeout=90000); context=browser.new_context(viewport={"width":1440,"height":900}); page=context.new_page(); errors=[]; console_errors=[]; failed=[]; errors_for(page,errors,console_errors,failed); wait_ready(page); report["workflow"]["main"]=run_workflow(page,shot_root); report["workflow"]["states"]=sparse_state_checks(page); report["workflow"]["keyboard"]=keyboard_checks(page); report["workflow"]["provider_recovery"]=provider_recovery(page); page.close(); context.close(); browser.close()
        report["performance"]["samples"]=performance_samples(playwright,3,args.phase,shot_root)
    baseline=None
    base_path=ROOT/"QA/gate5/baseline.json"
    if args.phase=="candidate" and base_path.is_file():
        try: baseline=json.loads(base_path.read_text()).get("performance",{}).get("samples")
        except json.JSONDecodeError: baseline=None
    report["performance"]["comparison"]=compare_performance(report["performance"]["samples"],baseline)
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
    report["gate4_reference"] = gate4_reference(report)
    report["status"]="PASS" if not report["failures"] else "FAIL"
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    FINDING_MATRIX.parent.mkdir(parents=True,exist_ok=True); FINDING_MATRIX.write_text(json.dumps(finding_matrix(report),ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"status":report["status"],"phase":args.phase,"candidate_head":report["candidate_head"],"failures":report["failures"],"verify_required":report["verify_required"]},ensure_ascii=False,indent=2))
    return 0 if report["status"]=="PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
