"""QA for Decide comparison and the single responsive workbench owner."""

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

from qa_config import MODULAR_URL


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "QA" / "route_panel"
OUT.mkdir(parents=True, exist_ok=True)
report = {"status": "FAIL", "route_explanations": [], "desktop": {}, "mobile": {}, "errors": []}


def snapshot(page, name):
    path = OUT / f"{name}.png"
    page.screenshot(path=str(path), full_page=True)
    return str(path.relative_to(ROOT))


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.set_default_timeout(30000)
    page.on("pageerror", lambda error: report["errors"].append(str(error)))
    page.goto(MODULAR_URL, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_function("window.__tripApp?.map()?.isStyleLoaded()", timeout=30000)

    for route in ("A", "B", "C", "D", "E"):
        card = page.locator(f'.route-card:has([data-compare-route="{route}"])')
        text = card.inner_text()
        report["route_explanations"].append({"route": route, "human_title": len(text) > 10, "score_profile": "score" in text.lower() or "/10" in text, "compare_control": card.locator('[data-compare-route]').count() == 1})

    page.locator('[data-compare-route="B"]').click()
    report["desktop"] = {"compare": page.locator("#comparePanel").inner_text(), "compare_visible": page.locator("#comparePanel").count() == 1, "screenshot": snapshot(page, "decide_compare_1440")}
    page.locator('[data-sheet="compact"]').click()
    report["desktop"]["compact"] = page.locator('#workbench[data-sheet="compact"]').count() == 1 and page.locator(".workbench-scroll").is_hidden()
    page.locator("#workbenchToggle").click()
    report["desktop"]["expanded"] = page.locator('#workbench[data-sheet="expanded"]').count() == 1 and not page.locator(".workbench-scroll").is_hidden()

    page.set_viewport_size({"width": 390, "height": 844})
    page.wait_for_timeout(250)
    report["mobile"]["initial"] = page.evaluate("()=>({overflow:document.documentElement.scrollWidth-innerWidth,map:document.getElementById('map').getBoundingClientRect().height,workbench:document.getElementById('workbench').getBoundingClientRect().height})")
    for sheet in ("compact", "expanded", "full"):
        page.locator(f'[data-sheet="{sheet}"]').click()
        report["mobile"][sheet] = {"active": page.locator(f'#workbench[data-sheet="{sheet}"]').count() == 1, "overflow": page.evaluate("document.documentElement.scrollWidth-innerWidth")}
    report["mobile"]["screenshot"] = snapshot(page, "workbench_mobile_390")
    browser.close()

route_pass = len(report["route_explanations"]) == 5 and all(row["human_title"] and row["score_profile"] and row["compare_control"] for row in report["route_explanations"])
compare_pass = report["desktop"]["compare_visible"] and all(value in report["desktop"]["compare"] for value in ("A", "B"))
responsive_pass = report["desktop"]["compact"] and report["desktop"]["expanded"] and report["mobile"]["initial"]["overflow"] == 0 and all(row["active"] and row["overflow"] == 0 for key, row in report["mobile"].items() if key in ("compact", "expanded", "full"))
report["status"] = "PASS" if not report["errors"] and route_pass and compare_pass and responsive_pass else "FAIL"
(OUT / "route_explanations_panel.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"status": report["status"], "routes": report["route_explanations"], "mobile": report["mobile"], "errors": report["errors"]}, ensure_ascii=False, indent=2))
raise SystemExit(0 if report["status"] == "PASS" else 1)
