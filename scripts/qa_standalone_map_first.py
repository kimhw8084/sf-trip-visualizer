"""Verify the large standalone file really loads local vector tiles without HTTP."""

import json
from pathlib import Path

from playwright.sync_api import sync_playwright
from qa_config import STANDALONE_PATH


ROOT = Path(__file__).resolve().parents[1]
URL = STANDALONE_PATH.resolve().as_uri()
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    errors = []
    requests = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: requests.append(request.url))
    page.goto(URL, wait_until="domcontentloaded", timeout=120000)
    page.wait_for_function("window.__tripApp && window.__tripApp.map()?.isStyleLoaded()", timeout=120000)
    page.wait_for_timeout(1500)
    result = page.evaluate("""()=>({provider:window.__tripApp.state.provider,health:window.__tripApp.state.providerHealth,clusters:document.querySelectorAll('.photo-cluster').length,features:window.__tripApp.visibleRouteFeatures().length,layers:window.__tripApp.map().getStyle().layers.length,decoded:[...document.querySelectorAll('.photo-cluster img')].every(x=>x.complete&&x.naturalWidth>0)})""")
    result["remote_requests"] = [url for url in requests if url.startswith("http")]
    result["page_errors"] = errors
    path = ROOT / "QA/map_first/standalone_1280.png"
    page.screenshot(path=str(path))
    (ROOT / "QA/map_first/standalone.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    browser.close()
