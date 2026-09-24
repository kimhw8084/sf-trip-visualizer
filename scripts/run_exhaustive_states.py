"""Render every nonempty route/date/region composition in the new shell."""

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

from qa_config import MODULAR_URL


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "QA" / "CHG-204" / "exhaustive_states.json"
DATA = json.loads((ROOT / "data/phase7_app_data.json").read_text())
ROUTES = tuple(sorted(DATA["routes"]))
REGIONS = ("overall", *sorted(key for key in DATA["region_cfg"] if key != "overall"))
DATES = ("all", *(item["key"] for item in DATA["dates"]))
ROUTE_SETS = tuple(dict.fromkeys([*( (route,) for route in ROUTES), ROUTES]))


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.set_default_timeout(600000)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(MODULAR_URL, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_function("window.__tripApp?.map()?.isStyleLoaded()", timeout=30000)
    rows = []
    for routes in ROUTE_SETS:
        result = page.evaluate(
            """async ({routes,dates,regions})=>{const a=window.__tripApp,s=a.state.task,out=[];s.routes=new Set(routes);s.primaryRoute=routes[0];a.setMode('day');for(const date of dates)for(const region of regions){s.date=date;s.region=region;s.selected=null;await a.drawMap(false);const expected=a.DATA.markers.filter(a.markerVisible).length,markers=document.querySelectorAll('.photo-marker').length,features=a.visibleRouteFeatures(),fail=[];if(markers!==expected)fail.push('marker_count');if(new Set([...document.querySelectorAll('.photo-marker')].map(x=>x.dataset.placeKey)).size!==markers)fail.push('duplicate_marker');if(document.querySelectorAll('.maplibregl-canvas').length!==1)fail.push('canvas_count');if(document.documentElement.scrollWidth>innerWidth)fail.push('overflow');if(date!=='all'&&features.some(f=>f.properties.date!==date))fail.push('cross_date_leg');if([...s.routes].some(route=>!Object.keys(a.DATA.routes).includes(route)))fail.push('stale_route_id');out.push({routes:routes.join(','),date,region,markers,features:features.length,failures:fail})}return out}""",
            {"routes": routes, "dates": DATES, "regions": REGIONS},
        )
        rows.extend(result)
        print("Rendered", ",".join(routes), len(result), "states", flush=True)
    browser.close()

expected_states = len(ROUTE_SETS) * len(DATES) * len(REGIONS)
report = {"browser": "Chromium real MapLibre render", "route_sets": [list(row) for row in ROUTE_SETS], "expected_states": expected_states, "rendered_states": len(rows), "failed_states": [row for row in rows if row["failures"]], "page_errors": errors, "status": "PASS" if len(rows) == expected_states and not errors and not any(row["failures"] for row in rows) else "FAIL", "rows": rows}
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({key: report[key] for key in ("status", "rendered_states", "failed_states", "page_errors")}, ensure_ascii=False, indent=2), flush=True)
raise SystemExit(0 if report["status"] == "PASS" else 1)
