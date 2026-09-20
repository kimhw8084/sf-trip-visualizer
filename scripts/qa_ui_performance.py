"""Order-balanced headless comparison for the current-main and R2 workbench."""

from __future__ import annotations

import json
import os
import statistics
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from qa_evidence import ROOT, bind_report, candidate_identity


OUT = ROOT / "QA" / "project_os_verify" / "ui_revamp_r2" / "performance.json"
BASELINE_URL = os.environ.get("TRIP_BASELINE_URL", "http://127.0.0.1:8765/index.html")
CANDIDATE_URL = os.environ.get("TRIP_QA_URL", "http://127.0.0.1:8767/index.html")
SAMPLES = int(os.environ.get("TRIP_PERF_SAMPLES", "8"))
BLOCKS = 2


def measure(browser, label: str, url: str, pair_id: int) -> dict:
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    started = time.perf_counter()
    page.goto(url, wait_until="domcontentloaded", timeout=90000)
    dom_content_ms = (time.perf_counter() - started) * 1000
    page.wait_for_function("window.__tripApp?.map()?.isStyleLoaded()", timeout=30000)
    map_ready_ms = (time.perf_counter() - started) * 1000
    if page.locator("#recommendation").count():
        workbench_ready = "#recommendation"
        interaction_kind = "two-route-compare"
        page.wait_for_function("document.querySelector('#recommendation')?.innerText.includes('A1')", timeout=15000)
        page.locator('[data-compare-route="A2"]').click()
        page.wait_for_function("document.querySelector('#comparePanel')?.innerText.includes('A2')", timeout=10000)
    else:
        workbench_ready = ".sidebar"
        interaction_kind = "legacy-route-selection-baseline"
        page.wait_for_function("document.querySelector('.sidebar') || document.body.innerText.length > 100", timeout=15000)
        if page.locator("[data-route]").count():
            page.locator("[data-route]").first.click()
    workbench_ready_ms = (time.perf_counter() - started) * 1000
    interaction_response_ms = (time.perf_counter() - started) * 1000
    row = {
        "pair_id": pair_id,
        "label": label,
        "url": url,
        "dom_content_ms": round(dom_content_ms, 2),
        "map_visual_ready_ms": round(map_ready_ms, 2),
        "workbench_ready_ms": round(workbench_ready_ms, 2),
        "interaction_response_ms": round(interaction_response_ms, 2),
        "interaction_kind": interaction_kind,
        "workbench_ready_selector": workbench_ready,
        "dom_nodes": page.locator("body *").count(),
        "markers": page.locator(".photo-marker").count(),
        "map_layers": page.evaluate("window.__tripApp.map().getStyle().layers.length"),
    }
    page.close()
    return row


def summarize(rows: list[dict]) -> dict:
    keys = ("dom_content_ms", "map_visual_ready_ms", "workbench_ready_ms", "interaction_response_ms", "dom_nodes", "markers", "map_layers")
    return {key: {"mean": round(statistics.mean(row[key] for row in rows), 2), "median": round(statistics.median(row[key] for row in rows), 2), "stdev": round(statistics.stdev(row[key] for row in rows), 2) if len(rows) > 1 else 0} for key in keys}


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    identity = candidate_identity()
    baseline_rows: list[dict] = []
    candidate_rows: list[dict] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        pair = 0
        for block in range(BLOCKS):
            first, second = (("baseline", BASELINE_URL), ("candidate", CANDIDATE_URL)) if block % 2 == 0 else (("candidate", CANDIDATE_URL), ("baseline", BASELINE_URL))
            for _ in range(max(1, SAMPLES // BLOCKS)):
                pair += 1
                for label, url in (first, second):
                    row = measure(browser, label, url, pair)
                    (baseline_rows if label == "baseline" else candidate_rows).append(row)
        browser.close()

    paired = []
    for index in range(min(len(baseline_rows), len(candidate_rows))):
        baseline = baseline_rows[index]
        candidate = candidate_rows[index]
        paired.append({"pair": index + 1, "baseline_interaction": baseline["interaction_kind"], "candidate_interaction": candidate["interaction_kind"], "deltas": {key: round(candidate[key] - baseline[key], 2) for key in ("dom_content_ms", "map_visual_ready_ms", "workbench_ready_ms", "interaction_response_ms", "dom_nodes")}})
    report = {
        "schema_version": 2,
        "base_revision": "f9631a57d3b9e51216e082b62d80519599b84711",
        "environment": {"browser": "Chromium headless", "viewport": "1440x900", "samples_per_variant": len(baseline_rows), "blocks": BLOCKS, "ordering": "two order-balanced baseline/candidate blocks", "platform": os.uname().sysname, "python": os.sys.version.split(".")[0]},
        "baseline": {"url": BASELINE_URL, "samples": baseline_rows, "metrics": summarize(baseline_rows)},
        "candidate": {"url": CANDIDATE_URL, "samples": candidate_rows, "metrics": summarize(candidate_rows)},
        "paired_deltas": paired,
        "classification": {"status": "VERIFY_REQUIRED", "reason": "Order-balanced matched samples characterize variance, but the legacy route-toggle and R2 two-route compare are not semantically identical tasks; no performance PASS or FIX is asserted from this evidence."},
        "notes": ["DOM simplification is retained; no material regression threshold was declared.", "Native Safari, physical-device and human field performance remain separate evidence boundaries."],
    }
    bind_report(report, identity)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": report["classification"]["status"], "samples_per_variant": len(baseline_rows), "candidate": identity["sha"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
