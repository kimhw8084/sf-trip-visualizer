"""Real-browser smoke and visual capture for the map-first edition."""

import json
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
URL = "http://127.0.0.1:8766/index_map_first.html"
out = ROOT / "QA/map_first"
out.mkdir(parents=True, exist_ok=True)
rows = []

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
    errors = []
    failed = []
    console = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("console", lambda message: console.append({"type": message.type, "text": message.text[:500]}))
    page.on("requestfailed", lambda request: failed.append({"url": request.url, "failure": request.failure}))
    page.goto(URL, wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(12000)
    state = page.evaluate("""()=>({app:!!window.__tripApp,provider:window.__tripApp?.state.provider,health:window.__tripApp?.state.providerHealth,theme:document.documentElement.dataset.theme,lang:document.documentElement.lang,canvas:document.querySelectorAll('.maplibregl-canvas').length,clusters:document.querySelectorAll('.photo-cluster').length,slots:document.querySelectorAll('.map-slot').length,routes:window.__tripApp?.visibleRouteFeatures().length,mapLayers:window.__tripApp?.map()?.getStyle()?.layers?.length||0,zoom:window.__tripApp?.map()?.getZoom()})""")
    page.screenshot(path=str(out / "smoke_1440.png"), full_page=True)
    rows.append({"state": state, "errors": errors, "console": console[-30:], "failed_requests": failed[:30]})
    (out / "smoke.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    browser.close()
