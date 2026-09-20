"""Matched headless-browser performance evidence for current-main vs CHG-157."""

from __future__ import annotations

import json
import os
import statistics
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "QA" / "project_os_verify" / "ui_revamp_r1" / "performance.json"
BASELINE_URL = os.environ.get("TRIP_BASELINE_URL", "http://127.0.0.1:8765/index.html")
CANDIDATE_URL = os.environ.get("TRIP_QA_URL", "http://127.0.0.1:8767/index.html")
SAMPLES = int(os.environ.get("TRIP_PERF_SAMPLES", "3"))


def measure(browser, label: str, url: str) -> dict:
    rows = []
    for sample in range(SAMPLES):
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        started = time.perf_counter()
        page.goto(url, wait_until="domcontentloaded", timeout=90000)
        dom_content_ms = (time.perf_counter() - started) * 1000
        page.wait_for_function("window.__tripApp?.map()?.isStyleLoaded()", timeout=30000)
        map_ready_ms = (time.perf_counter() - started) * 1000
        page.wait_for_function("document.querySelector('#recommendation')?.innerText.includes('A1') || document.querySelector('.sidebar') || document.body.innerText.length > 100", timeout=15000)
        workbench_ready_ms = (time.perf_counter() - started) * 1000
        if page.locator('[data-compare-route="A2"]:visible').count():
            interaction_kind = "two-route-compare"
            page.locator('[data-compare-route="A2"]:visible').click()
            page.wait_for_function("document.querySelector('#comparePanel')?.innerText.includes('A2')", timeout=10000)
        elif page.locator('[data-route]:visible').count():
            interaction_kind = "legacy-route-selection-baseline"
            page.locator('[data-route]:visible').first.click()
            page.wait_for_timeout(120)
        else:
            interaction_kind = "document-ready-only"
        compare_response_ms = (time.perf_counter() - started) * 1000
        rows.append({
            "sample": sample + 1,
            "dom_content_ms": round(dom_content_ms, 2),
            "map_visual_ready_ms": round(map_ready_ms, 2),
            "workbench_ready_ms": round(workbench_ready_ms, 2),
            "compare_response_ms": round(compare_response_ms, 2),
            "interaction_kind": interaction_kind,
            "dom_nodes": page.locator("body *").count(),
            "markers": page.locator(".photo-marker").count(),
            "map_layers": page.evaluate("window.__tripApp.map().getStyle().layers.length"),
        })
        page.close()
    metrics = {key: {"mean": round(statistics.mean(row[key] for row in rows), 2), "stdev": round(statistics.stdev(row[key] for row in rows), 2) if len(rows) > 1 else 0} for key in ("dom_content_ms", "map_visual_ready_ms", "workbench_ready_ms", "compare_response_ms", "dom_nodes", "markers", "map_layers")}
    return {"label": label, "url": url, "samples": rows, "metrics": metrics}


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    baseline = measure(browser, "current-main baseline", BASELINE_URL)
    candidate = measure(browser, "CHG-157 candidate", CANDIDATE_URL)
    browser.close()

report = {
    "schema_version": 1,
    "base_revision": "f9631a57d3b9e51216e082b62d80519599b84711",
    "candidate_revision": os.environ.get("TRIP_CANDIDATE_SHA", "WORKTREE"),
    "environment": {"browser": "Chromium headless", "viewport": "1440x900", "samples_per_variant": SAMPLES, "ordering": "baseline then candidate", "platform": os.uname().sysname, "python": os.sys.version.split()[0]},
    "baseline": baseline,
    "candidate": candidate,
    "interpretation": {"status": "VERIFY_REQUIRED", "reason": "Matched local samples record milestones and variance, but no universal threshold is asserted; hosted-Linux release performance and human/device evidence remain external.", "task_effort_proxy": "One compare-control interaction after load; this is not a human usability score."},
}
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"status": report["interpretation"]["status"], "baseline": baseline["metrics"], "candidate": candidate["metrics"]}, ensure_ascii=False, indent=2))
