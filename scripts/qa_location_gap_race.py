"""Regression coverage for stale map callbacks during location-gap filtering."""

from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

from qa_config import MODULAR_URL
from qa_loading import wait_for_application_ready


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "QA/map_first/location_gap_race.json"


def exercise(page) -> dict:
    return page.evaluate(
        """
        async ({iterations}) => {
          const app = window.__tripApp;
          const routeSets = [
            Object.keys(app.DATA.routes),
            ['A1'],
            ['B1', 'B2'],
            ['A2'],
          ];
          const dates = ['all', '10/5'];
          const regions = ['overall', 'sf'];
          const exceptions = [];
          app.selectPlace('pier39', {focus:false, openDetails:true});
          for (let i = 0; i < iterations; i++) {
            try {
              app.state.routes = new Set(routeSets[i % routeSets.length]);
              app.state.date = dates[i % dates.length];
              app.state.region = regions[i % regions.length];
              app.state.selected = 'pier39';
              app.renderDetail('pier39');
              app.renderTimeline();
              app.drawMap(false, {waitForVisual:false});
              const map = app.map();
              if (map) {
                map.jumpTo({center:[-122.42 + (i % 5) * .03, 37.75 + (i % 7) * .02], zoom:7 + (i % 10)});
                map.fire('moveend');
                map.fire('zoomend');
              }
            } catch (error) {
              exceptions.push({iteration:i, message:error.message, stack:error.stack});
            }
          }
          await app.whenIdle();
          const expected = app.DATA.markers.filter(app.markerVisible).map(marker => marker.place_key);
          const actual = [...document.querySelectorAll('.photo-marker')].map(marker => marker.dataset.placeKey);
          return {
            exceptions,
            expected,
            actual,
            canvas: document.querySelectorAll('.maplibregl-canvas').length,
            selected: app.state.selected,
            tab: app.state.tab,
            detailsActive: document.getElementById('detailsPane')?.classList.contains('active'),
            detailHeading: document.querySelector('#detailsPane h2')?.innerText || '',
            detailPhotos: document.querySelectorAll('#detailsPane .photo-slot img').length,
          };
        }
        """,
        {"iterations": 80},
    )


def run_browser(browser_name: str) -> dict:
    errors = []
    with sync_playwright() as playwright:
        browser = getattr(playwright, browser_name).launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.on("pageerror", lambda error: errors.append({"message": str(error), "stack": getattr(error, "stack", None)}))
        try:
            page.goto(MODULAR_URL, wait_until="domcontentloaded", timeout=90000)
            page.wait_for_function("window.__tripApp?.map()?.isStyleLoaded()", timeout=30000)
            wait_for_application_ready(page, timeout=30000)
            checks = exercise(page)
            checks["page_errors"] = errors
            checks["browser"] = browser_name
            checks["status"] = "PASS" if (
                not errors
                and not checks["exceptions"]
                and checks["actual"] == checks["expected"]
                and len(checks["actual"]) == len(set(checks["actual"]))
                and checks["canvas"] == 1
                and checks["selected"] == "pier39"
                and checks["tab"] == "details"
                and checks["detailsActive"]
                and checks["detailPhotos"] == 3
            ) else "FAIL"
            return checks
        finally:
            browser.close()


reports = [run_browser(browser_name) for browser_name in ("chromium", "webkit")]
report = {"status": "PASS" if all(row["status"] == "PASS" for row in reports) else "FAIL", "browsers": reports}
OUTPUT.parent.mkdir(parents=True, exist_ok=True)
OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(json.dumps(report, ensure_ascii=False, indent=2))
