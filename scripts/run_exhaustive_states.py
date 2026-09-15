"""Render every nonempty route/date/region filter composition in real Chromium."""

import itertools
import json
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "QA/exhaustive_states.json"
ROUTES = ("A1", "A2", "B1", "B2")
REGIONS = ("overall", "sf", "monterey", "yosemite")
DATES = ("all", "10/3", "10/4", "10/5", "10/6", "10/7", "10/8", "10/9", "10/10", "10/11")


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.set_default_timeout(600000)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto("http://127.0.0.1:8766/index.html", wait_until="domcontentloaded", timeout=90000)
    page.wait_for_function("window.__tripApp && document.querySelectorAll('.photo-marker').length===window.__tripApp.DATA.markers.length")
    rows = []
    for size in range(1, 5):
        for routes in itertools.combinations(ROUTES, size):
            result = page.evaluate(
                """async ({routes,dates,regions})=>{
                  const a=window.__tripApp,s=a.state,out=[];
                  s.routes=new Set(routes);
                  for(const date of dates)for(const region of regions){
                    s.date=date;s.region=region;s.selected=null;a.renderTimeline();
                    await a.drawMap(false);
                    const expectedMarkers=a.DATA.markers.filter(a.markerVisible),expectedTimeline=a.DATA.timeline.filter(a.timelineVisible);
                    const expectedLegs=a.DATA.legs.filter(a.legVisible),expectedFeatures=a.visibleRouteFeatures();
                    const markers=[...document.querySelectorAll('.photo-marker')],timeline=document.querySelectorAll('[data-timeline]');
                    const map=a.map();
                    if(!map.getSource('trip-routes'))await new Promise(resolve=>map.once('load',resolve));
                    const actualFeatures=map.getSource('trip-routes')?._data?.features||[];
                    const pointInView=(m)=>{const p=map.project([m.lon,m.lat]),c=map.getCanvas();return p.x>=-2&&p.x<=c.clientWidth+2&&p.y>=-2&&p.y<=c.clientHeight+2};
                    const failures=[];
                    if(markers.length!==expectedMarkers.length)failures.push('marker_count');
                    if(timeline.length!==expectedTimeline.length)failures.push('timeline_count');
                    if(new Set(markers.map(m=>m.dataset.placeKey)).size!==markers.length)failures.push('duplicate_physical_marker');
                    if(document.querySelectorAll('.maplibregl-canvas').length!==1)failures.push('canvas_count');
                    if(actualFeatures.length!==expectedFeatures.length)failures.push('route_feature_count');
                    if(expectedLegs.some(l=>date!=='all'&&l.date!==date))failures.push('cross_date_leg');
                    if((region!=='overall'||date!=='all')&&expectedMarkers.some(m=>!pointInView(m)))failures.push('marker_outside_fitted_view');
                    out.push({routes:routes.join(','),date,region,markers:markers.length,timeline:timeline.length,legs:expectedLegs.length,features:actualFeatures.length,failures});
                  }
                  return out;
                }""",
                {"routes": routes, "dates": DATES, "regions": REGIONS},
            )
            rows.extend(result)
            print("Rendered", ",".join(routes), len(result), "states; failures", sum(bool(x["failures"]) for x in result), flush=True)
    browser.close()

report = {
    "browser": "Chromium real MapLibre/Plotly render",
    "expected_states": 15 * 10 * 4,
    "rendered_states": len(rows),
    "failed_states": [row for row in rows if row["failures"]],
    "page_errors": errors,
    "status": "PASS" if len(rows) == 600 and not errors and all(not row["failures"] for row in rows) else "FAIL",
    "rows": rows,
}
OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({key: report[key] for key in ("status", "rendered_states", "failed_states", "page_errors")}, ensure_ascii=False, indent=2), flush=True)
