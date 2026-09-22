"""Order-balanced startup comparison for exact main and the candidate."""

from __future__ import annotations

import json
import os
import platform
import statistics
import time

from playwright.sync_api import sync_playwright

from qa_evidence import ROOT, bind_report, candidate_identity


OUT = ROOT / "QA" / "project_os_verify" / "ui_revamp_r5" / "performance.json"
BASELINE_URL = os.environ.get("TRIP_BASELINE_URL", "http://127.0.0.1:8765/index.html")
BASELINE_REVISION = os.environ.get("TRIP_BASELINE_REVISION", "not_provided")
R2_URL = os.environ.get("TRIP_R2_URL")
CANDIDATE_URL = os.environ.get("TRIP_QA_URL", "http://127.0.0.1:8768/index.html")
SAMPLES = max(8, int(os.environ.get("TRIP_PERF_SAMPLES", "8")))
BLOCKS = 2
VIEWPORT = {"width": 1440, "height": 900}
VARIANTS = (("baseline", BASELINE_URL),) + (("r2_reference", R2_URL),) if R2_URL else (("baseline", BASELINE_URL),)
VARIANTS = VARIANTS + (("r5_candidate", CANDIDATE_URL),)


def wait_workbench(page) -> tuple[str, str]:
    if page.locator("#recommendation").count():
        page.wait_for_function("document.querySelector('#recommendation')?.innerText.includes('A')", timeout=30000)
        return "decision-workbench", "#recommendation"
    page.wait_for_function("document.querySelector('.sidebar') || document.body.innerText.length > 100", timeout=30000)
    return "legacy-itinerary", ".sidebar"


def wait_map(page) -> str:
    if page.locator("#recommendation").count():
        page.wait_for_function("window.__tripApp?.state?.runtime?.mapVisualReady === true", timeout=30000)
        return "runtime.mapVisualReady"
    page.wait_for_function("window.__tripApp?.map()?.isStyleLoaded()", timeout=30000)
    return "map.isStyleLoaded"


def measure(browser, label: str, url: str, sample: int, block: int, order: int) -> dict:
    page = browser.new_page(viewport=VIEWPORT)
    started = time.perf_counter()
    page.goto(url, wait_until="domcontentloaded", timeout=90000)
    dom_content_ms = (time.perf_counter() - started) * 1000
    interaction_kind, selector = wait_workbench(page)
    decision_ready_ms = (time.perf_counter() - started) * 1000
    readiness_method = wait_map(page)
    map_visual_ready_ms = (time.perf_counter() - started) * 1000
    snapshot = page.evaluate("window.__tripApp?.runtimeSnapshot?.() || null")
    row = {
        "sample": sample,
        "block": block,
        "order": order,
        "label": label,
        "url": url,
        "dom_content_ms": round(dom_content_ms, 2),
        "decision_workbench_ready_ms": round(decision_ready_ms, 2),
        "map_visual_ready_ms": round(map_visual_ready_ms, 2),
        "readiness_method": readiness_method,
        "interaction_kind": interaction_kind,
        "workbench_ready_selector": selector,
        "dom_nodes": page.locator("body *").count(),
        "markers": page.locator(".photo-marker").count(),
        "map_layers": page.evaluate("window.__tripApp?.map()?.getStyle?.()?.layers?.length || 0"),
        "startup_marks": (snapshot or {}).get("startup", {}).get("marks", []),
    }
    page.close()
    return row


def summarize(rows: list[dict]) -> dict:
    keys = ("dom_content_ms", "decision_workbench_ready_ms", "map_visual_ready_ms", "dom_nodes", "markers", "map_layers")
    return {key: {"mean": round(statistics.mean(row[key] for row in rows), 2), "median": round(statistics.median(row[key] for row in rows), 2), "stdev": round(statistics.stdev(row[key] for row in rows), 2) if len(rows) > 1 else 0} for key in keys}


def paired(rows: dict[str, list[dict]], left: str, right: str) -> dict:
    keys = ("dom_content_ms", "decision_workbench_ready_ms", "map_visual_ready_ms", "dom_nodes")
    deltas = []
    for index, (left_row, right_row) in enumerate(zip(rows[left], rows[right]), start=1):
        deltas.append({"pair": index, "deltas": {key: round(right_row[key] - left_row[key], 2) for key in keys}, "right_slower": {key: right_row[key] > left_row[key] for key in keys}})
    summary = {}
    for key in keys:
        values = [row["deltas"][key] for row in deltas]
        summary[key] = {"mean": round(statistics.mean(values), 2), "median": round(statistics.median(values), 2), "stdev": round(statistics.stdev(values), 2) if len(values) > 1 else 0, "slower_count": sum(value > 0 for value in values), "material_slower_200ms_count": sum(value > 200 for value in values)}
    block_direction = []
    for block in range(BLOCKS):
        block_rows = [row for row in deltas if rows[left][row["pair"] - 1]["block"] == block]
        block_direction.append({"block": block, "mean_deltas": {key: round(statistics.mean(row["deltas"][key] for row in block_rows), 2) for key in keys}, "right_slower": {key: all(row["deltas"][key] > 0 for row in block_rows) for key in keys}})
    return {"left": left, "right": right, "samples": deltas, "summary": summary, "block_direction": block_direction}


def classify(comparison: dict) -> dict:
    map_delta = comparison["summary"]["map_visual_ready_ms"]
    dom_delta = comparison["summary"]["dom_content_ms"]
    decision_delta = comparison["summary"]["decision_workbench_ready_ms"]
    material = map_delta["mean"] > 250 or dom_delta["mean"] > 250 or decision_delta["mean"] > 250
    consistent_material = map_delta["material_slower_200ms_count"] >= 6 or dom_delta["material_slower_200ms_count"] >= 6 or decision_delta["material_slower_200ms_count"] >= 6
    if material or consistent_material:
        return {"status": "FIX_REQUIRED", "reason": "R5 shows a material, consistent first-use regression against current main."}
    if (map_delta["mean"] > 0 and map_delta["slower_count"] >= 5) or (dom_delta["mean"] > 0 and dom_delta["slower_count"] >= 5) or (decision_delta["mean"] > 0 and decision_delta["slower_count"] >= 5):
        return {"status": "VERIFY_REQUIRED", "reason": "R5 removes the hundreds-of-ms failure pattern, but residual direction remains noisy or mildly slower."}
    return {"status": "PASS", "reason": "The candidate has no material or consistently slower first-use regression against exact transported main; per-sample variance is retained for review."}


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    identity = candidate_identity()
    rows = {label: [] for label, _url in VARIANTS}
    order = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        browser_version = browser.version
        sample_per_block = max(1, SAMPLES // BLOCKS)
        for block in range(BLOCKS):
            variant_order = VARIANTS if block % 2 == 0 else tuple(reversed(VARIANTS))
            for _sample in range(sample_per_block):
                for order_index, (label, url) in enumerate(variant_order):
                    sample_index = len(rows[label]) + 1
                    order.append({"block": block, "sample": sample_index, "order": order_index, "label": label})
                    rows[label].append(measure(browser, label, url, sample_index, block, order_index))
        browser.close()

    comparisons = {"baseline_vs_candidate": paired(rows, "baseline", "r5_candidate")}
    if R2_URL:
        comparisons.update({"baseline_vs_r2": paired(rows, "baseline", "r2_reference"), "r2_vs_candidate": paired(rows, "r2_reference", "r5_candidate")})
    report = {
        "schema_version": 3,
        "status": "RUNNING",
        "change": "CHG-157 R5",
        "baseline_revision": BASELINE_REVISION,
        "base_revision": "f9631a57d3b9e51216e082b62d80519599b84711",
        "r2_reference": {"sha": "4a2520a8fb40ec789784fccf513de78f26318507", "tree": "1d42515d23cc6f1995e3ccc8f41da6802321dcf5"},
        "r2_authoritative_recorded_reference": {
            "evidence_head": "a620d94b75b982073aa71ac4a1a49161b403a290",
            "source_replay_contract": "Exact R2 source/build replay is retained in r2_reference_samples; these recorded qualification values remain the authoritative R2 defect record.",
            "samples_per_variant": 8,
            "baseline_map_visual_ready_mean_ms": 1070.76,
            "r2_map_visual_ready_mean_ms": 1569.07,
            "map_visual_ready_pair_slower_count": 8,
            "map_visual_ready_mean_delta_ms": 498.31,
            "baseline_dom_content_mean_ms": 114.8,
            "r2_dom_content_mean_ms": 451.2,
            "dom_content_pair_slower_count": 8,
        },
        "environment": {"browser": "Chromium headless", "browser_version": browser_version, "viewport": "1440x900", "samples_per_variant": len(rows["baseline"]), "blocks": BLOCKS, "ordering": order, "platform": platform.system(), "python": os.sys.version.split(".")[0]},
        "baseline": {"url": BASELINE_URL, "samples": rows["baseline"], "metrics": summarize(rows["baseline"])},
        "r2_reference_samples": {"url": R2_URL, "samples": rows.get("r2_reference", []), "metrics": summarize(rows["r2_reference"]) if R2_URL else None, "status": "RUN" if R2_URL else "NOT_RUN"},
        "r5_candidate_samples": {"url": CANDIDATE_URL, "samples": rows["r5_candidate"], "metrics": summarize(rows["r5_candidate"])},
        "comparisons": comparisons,
        "classification": classify(comparisons["baseline_vs_candidate"]),
        "interaction_qualification": "The route-toggle and two-route compare tasks remain semantically non-equivalent; no interaction-response PASS is asserted here.",
        "notes": ["R5 uses runtime.mapVisualReady for the candidate and map.isStyleLoaded for the legacy baseline; both methods are recorded per sample.", "Decision shell readiness is recorded separately from map readiness.", "The authoritative R2 qualification distribution is preserved explicitly; the fresh replay is labeled separately because local replay timing differs from the recorded R2 environment.", "Native Safari, physical-device and independent-human field performance remain separate evidence boundaries."],
    }
    report["status"] = report["classification"]["status"]
    bind_report(report, identity)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": report["classification"]["status"], "samples_per_variant": len(rows["baseline"]), "candidate": identity["sha"], "map_delta_ms": comparisons["baseline_vs_candidate"]["summary"]["map_visual_ready_ms"]["mean"]}, ensure_ascii=False))
    return 0 if report["classification"]["status"] in {"PASS", "VERIFY_REQUIRED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
