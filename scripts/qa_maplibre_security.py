#!/usr/bin/env python3
"""Focused browser regression for the local MapLibre sanitizer backport."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE_REVISION = "61511ac0485aa145522a6567b484d2cc9aa97e20"
STOCK_JS_SHA256 = "be9633c4d870e26fb37f1cfe5c5a77181667114003ea16207ac7850d8da8add1"
PATCHED_JS_SHA256 = "3e259a3d0e8d97c8e4d005cf21b86bba933818a80fe4b1fc4e402ff8c2318675"
PAYLOAD = (
    '<details open onload="window.__maplibreSecuritySentinel += 1" '
    'ontoggle="window.__maplibreSecuritySentinel += 2">inert</details>'
    '<a href="javascript:window.__maplibreSecuritySentinel += 4" '
    'onclick="window.__maplibreSecuritySentinel += 8">inert link</a>'
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def maplibre_entry(root: Path = ROOT) -> dict:
    contract = json.loads((root / "manifests/security_privacy_contract.json").read_text())
    return next(entry for entry in contract["dependency_inventory"] if entry["id"] == "maplibre-gl-js")


def static_contract_checks(root: Path = ROOT) -> dict:
    entry = maplibre_entry(root)
    javascript = root / "vendor/maplibre-gl.js"
    renderer = root / "src/app_phase7.js"
    regression = Path(__file__)
    failures: list[str] = []
    identity = entry.get("local_backport", {})
    if entry.get("version") != identity.get("identity"):
        failures.append("MapLibre contract version is not the explicit local patched identity")
    if identity.get("base_tag") != "v4.7.1" or identity.get("upstream_security_patch_commit") != "1da69f3cd913a39fa948708e01478663bf48bc27":
        failures.append("MapLibre local backport provenance is not bound to v4.7.1 and the exact upstream security patch")
    if identity.get("upstream_sanitizer_introduction_commit") != "506090de1202f58c35175802bc0342494c5f5893":
        failures.append("MapLibre sanitizer backport source is not bound to the reviewed upstream implementation")
    if not javascript.is_file() or sha256(javascript) != PATCHED_JS_SHA256:
        failures.append("MapLibre patched artifact hash is not the reviewed candidate hash")
    text = javascript.read_text(encoding="utf-8", errors="replace") if javascript.is_file() else ""
    for marker in ("DOMParser", "isPossiblyDangerous", "Array.from(t.attributes", "innerHTML"):
        if marker not in text:
            failures.append(f"MapLibre artifact is missing sanitizer marker: {marker}")
    renderer_text = renderer.read_text(encoding="utf-8") if renderer.is_file() else ""
    if "customAttribution" in renderer_text:
        failures.append("maintained renderer exposes an unreviewed custom attribution path")
    for marker in ("© OpenStreetMap contributors · Protomaps", "Tiles © Esri and contributors"):
        if marker not in renderer_text:
            failures.append(f"maintained renderer is missing fixed attribution: {marker}")
    regression_text = regression.read_text(encoding="utf-8")
    for marker in ("GHSA-jrc7-96c5-q579", "ontoggle", "__maplibreSecuritySentinel", "AttributionControl"):
        if marker not in regression_text:
            failures.append(f"MapLibre regression is missing required assertion marker: {marker}")
    return {"status": "PASS" if not failures else "FAIL", "failures": failures}


def stock_fixture(root: Path = ROOT) -> str:
    data = subprocess.check_output(
        ["git", "show", f"{BASE_REVISION}:vendor/maplibre-gl.js"],
        cwd=root,
    )
    if hashlib.sha256(data).hexdigest() != STOCK_JS_SHA256:
        raise RuntimeError("exact-main stock MapLibre fixture hash changed")
    return data.decode("utf-8")


def exercise(page, javascript: str) -> dict:
    page.set_content("<!doctype html><div id='host'></div>")
    page.add_script_tag(content=javascript)
    return page.evaluate(
        """(payload) => new Promise(resolve => {
            window.__maplibreSecuritySentinel = 0;
            const map = {
                style: {stylesheet: {}, sourceCaches: {}},
                on() {},
                off() {},
                getCanvasContainer() { return {offsetWidth: 800}; },
                _getUIString() { return 'test'; }
            };
            const control = new maplibregl.AttributionControl({compact: false, customAttribution: payload});
            const container = control.onAdd(map);
            document.querySelector('#host').append(container);
            setTimeout(() => {
                const inner = container.querySelector('.maplibregl-ctrl-attrib-inner');
                const attributes = [...inner.querySelectorAll('*')].flatMap(element =>
                    [...element.attributes].map(attribute => ({name: attribute.name, value: attribute.value}))
                );
                resolve({
                    version: maplibregl.getVersion(),
                    html: inner.innerHTML,
                    dangerous_attributes: attributes.filter(attribute =>
                        attribute.name.startsWith('on') ||
                        ((attribute.name === 'href' || attribute.name === 'src') && /^(?:javascript|data):/i.test(attribute.value))
                    ),
                    sentinel: window.__maplibreSecuritySentinel
                });
            }, 50);
        })""",
        PAYLOAD,
    )


def run_browser_regression(root: Path = ROOT) -> dict:
    from playwright.sync_api import sync_playwright

    patched = (root / "vendor/maplibre-gl.js").read_text(encoding="utf-8")
    stock = stock_fixture(root)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            patched_result = exercise(page, patched)
            stock_result = exercise(page, stock)
        finally:
            browser.close()
    failures: list[str] = []
    if patched_result["dangerous_attributes"] or patched_result["sentinel"] != 0:
        failures.append("patched MapLibre AttributionControl retained or executed the inert dangerous payload")
    if not stock_result["dangerous_attributes"]:
        failures.append("stock exact-main 4.7.1 fixture did not demonstrate the expected vulnerable assertion")
    return {
        "status": "PASS" if not failures else "FAIL",
        "advisory": "GHSA-jrc7-96c5-q579 / CVE-2026-85061",
        "patched": patched_result,
        "stock_fixture": {"revision": BASE_REVISION, "sha256": STOCK_JS_SHA256, **stock_result},
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision")
    parser.add_argument("--output", type=Path, default=ROOT / "QA/CHG-188/release/maplibre_security.json")
    args = parser.parse_args()
    result = {"status": "FAIL", "candidate_head": args.revision, "static": static_contract_checks(ROOT)}
    try:
        if args.revision:
            actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
            result["candidate_head"] = actual
            if actual != args.revision:
                raise RuntimeError(f"requested revision {args.revision} does not match HEAD {actual}")
        if result["static"]["status"] != "PASS":
            raise RuntimeError("; ".join(result["static"]["failures"]))
        result["browser"] = run_browser_regression(ROOT)
        if result["browser"]["status"] != "PASS":
            raise RuntimeError("; ".join(result["browser"]["failures"]))
        result["status"] = "PASS"
    except Exception as error:
        result.setdefault("failures", []).append(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "candidate_head": result.get("candidate_head"), "failures": result.get("failures", [])}))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
