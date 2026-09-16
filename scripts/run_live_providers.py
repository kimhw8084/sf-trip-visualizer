"""Verify live USGS Topo, OSM, and Esri tile rendering in local Chromium."""

raise SystemExit("DEPRECATED LEGACY ENTRY POINT: provider-era suite; use python3 scripts/pipeline.py qualify")

import json
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / "QA/screenshots"
PROVIDERS = {
    "light": "basemap.nationalmap.gov",
    "osm": "tile.openstreetmap.org",
    "satellite": "server.arcgisonline.com",
}

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    errors, console_errors, dialogs, requests, responses = [], [], [], [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
    page.on("dialog", lambda dialog: (dialogs.append(dialog.message), dialog.dismiss()))
    page.on("request", lambda request: requests.append(request.url) if request.url.startswith("http") else None)
    page.on("response", lambda response: responses.append({"url": response.url, "status": response.status}) if response.url.startswith("http") else None)
    page.goto((ROOT / "index.html").as_uri())
    page.wait_for_function("window.__tripApp && document.querySelectorAll('.photo-marker').length===28")
    page.wait_for_timeout(700)
    default_remote = len(requests)
    page.locator("[data-region=sf]").first.click()
    page.evaluate("()=>window.__tripApp.whenIdle()")
    rows = []
    for name, domain in PROVIDERS.items():
        before = len(responses)
        page.locator(f"[data-provider={name}]").first.click()
        page.wait_for_function("name=>window.__tripApp.state.provider===name||window.__tripApp.state.providerHealth[name]==='failed'", arg=name)
        page.evaluate("()=>window.__tripApp.whenIdle()")
        page.wait_for_timeout(2800)
        matching = [r for r in responses[before:] if domain in r["url"]]
        shot = SHOTS / f"final_live_provider_{name}.png"
        page.screenshot(path=str(shot))
        row = {
            "provider": name,
            "domain": domain,
            "active_after": page.evaluate("window.__tripApp.state.provider"),
            "health": page.evaluate("name=>window.__tripApp.state.providerHealth[name]", name),
            "matching_http_200_responses": sum(r["status"] == 200 for r in matching),
            "photo_markers": page.locator(".photo-marker").count(),
            "map_canvas": page.locator(".maplibregl-canvas").count(),
            "screenshot": str(shot.relative_to(ROOT)),
        }
        row["status"] = "PASS" if row["active_after"] == name and row["health"] == "ready" and row["matching_http_200_responses"] > 0 and row["photo_markers"] == 19 and row["map_canvas"] == 1 else "FAIL"
        rows.append(row)
    browser.close()

remote_photos = [url for url in requests if "upload.wikimedia" in url or "/photos/" in url]
report = {
    "status": "PASS" if default_remote == 0 and not errors and not console_errors and not dialogs and not remote_photos and all(row["status"] == "PASS" for row in rows) else "FAIL",
    "default_remote_requests": default_remote,
    "remote_photo_requests": remote_photos,
    "page_errors": errors,
    "console_errors": console_errors,
    "browser_dialogs": dialogs,
    "providers": rows,
}
(ROOT / "QA/final_live_providers.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
