"""Render every nonempty route/date/region composition in the new shell."""

import itertools
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

from qa_config import MODULAR_URL


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "QA" / "map_first" / "exhaustive_states.json"
ROUTES = ("A1", "A2", "B1", "B2")
REGIONS = ("overall", "sf", "monterey", "yosemite")
DATES = ("all", "10/3", "10/4", "10/5", "10/6", "10/7", "10/8", "10/9", "10/10", "10/11")


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.set_default_timeout(600000)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(MODULAR_URL, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_function("window.__tripApp?.map()?.isStyleLoaded()", timeout=30000)
    rows = []
    for size in range(1, 5):
        for routes in itertools.combinations(ROUTES, size):
            result = page.evaluate(
                """async ({routes,dates,regions})=>{const a=window.__tripApp,s=a.state.task,out=[];s.routes=new Set(routes);s.primaryRoute=routes[0];s.compareRoutes=new Set();a.setMode('day');for(const date of dates)for(const region of regions){s.date=date;s.region=region;s.selected=null;await a.drawMap(false);const expected=a.DATA.markers.filter(a.markerVisible).length,markers=document.querySelectorAll('.photo-marker').length,features=a.visibleRouteFeatures(),fail=[];if(markers!==expected)fail.push('marker_count');if(new Set([...document.querySelectorAll('.photo-marker')].map(x=>x.dataset.placeKey)).size!==markers)fail.push('duplicate_marker');if(document.querySelectorAll('.maplibregl-canvas').length!==1)fail.push('canvas_count');if(document.documentElement.scrollWidth>innerWidth)fail.push('overflow');if(date!=='all'&&features.some(f=>f.properties.date!==date))fail.push('cross_date_leg');out.push({routes:routes.join(','),date,region,markers,features:features.length,failures:fail})}return out}""",
                {"routes": routes, "dates": DATES, "regions": REGIONS},
            )
            rows.extend(result)
            print("Rendered", ",".join(routes), len(result), "states", flush=True)
    browser.close()

report = {"browser": "Chromium real MapLibre render", "expected_states": 600, "rendered_states": len(rows), "failed_states": [row for row in rows if row["failures"]], "page_errors": errors, "status": "PASS" if len(rows) == 600 and not errors and not any(row["failures"] for row in rows) else "FAIL", "rows": rows}
OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({key: report[key] for key in ("status", "rendered_states", "failed_states", "page_errors")}, ensure_ascii=False, indent=2), flush=True)
raise SystemExit(0 if report["status"] == "PASS" else 1)
