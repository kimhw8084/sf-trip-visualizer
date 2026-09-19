"""Shared Gate 6 public-asset contract, notice rendering, and tree audit."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "manifests" / "public_asset_rights.json"
PHOTO_MANIFEST = ROOT / "manifests" / "asset_manifest.json"


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def load_contract(path: Path = CONTRACT) -> dict:
    return load_json(path)


def _matches(rule: dict, relative: str) -> bool:
    return relative in rule.get("paths", []) or any(fnmatch.fnmatchcase(relative, pattern) for pattern in rule.get("patterns", []))


def _rules_for(contract: dict, relative: str, mode: str) -> list[dict]:
    return [rule for rule in contract.get("path_rules", []) if mode in rule.get("modes", []) and _matches(rule, relative)]


def _photo_index(contract: dict) -> dict[str, dict]:
    return {item["id"]: item for item in contract.get("photo_assets", [])}


def _manifest_photo_index(manifest: dict) -> dict[str, dict]:
    return {f'{item["place_key"]}/{item["role"]}': item for item in manifest.get("assets", [])}


def validate_contract(contract: dict, manifest: dict) -> list[str]:
    failures: list[str] = []
    if contract.get("schema_version") != 1:
        failures.append("unsupported rights contract schema")
    if contract.get("project") != "sf-trip-visualizer":
        failures.append("rights contract project mismatch")
    input_hashes = contract.get("input_sha256", {})
    for relative, expected in input_hashes.items():
        path = ROOT / relative
        if not path.is_file() or digest(path) != expected:
            failures.append(f"rights input binding mismatch: {relative}")
    if not contract.get("decision_vocabulary") or "approved" not in contract["decision_vocabulary"]:
        failures.append("rights contract has no approved decision vocabulary")
    manifest_photos = _manifest_photo_index(manifest)
    rights_photos = _photo_index(contract)
    if set(manifest_photos) != set(rights_photos):
        failures.append("photo rights rows do not exactly cover asset_manifest.json")
    for identifier, item in rights_photos.items():
        source = manifest_photos.get(identifier)
        if not source:
            continue
        if item.get("public_distribution_decision") != "approved":
            failures.append(f"photo {identifier} is not public-approved")
        if item.get("evidence_status") in {"verify-required", "unknown", "missing"}:
            failures.append(f"photo {identifier} has unresolved evidence")
        if item.get("source_page") != source.get("selected_source_page") or item.get("source_image_url") != source.get("source_image_url"):
            failures.append(f"photo {identifier} provenance binding mismatch")
        for field in ("creator_or_owner", "license_or_permission", "license_url", "attribution_text"):
            if not item.get(field):
                failures.append(f"photo {identifier} missing {field}")
        expected_paths = [source.get("local_thumb_path"), source.get("local_medium_path")]
        if sorted(item.get("public_paths", [])) != sorted(expected_paths):
            failures.append(f"photo {identifier} public path binding mismatch")
        expected_hashes = {
            source.get("local_thumb_path"): source.get("thumb_sha256"),
            source.get("local_medium_path"): source.get("medium_sha256"),
        }
        for path, expected_hash in expected_hashes.items():
            if item.get("hashes", {}).get(path) != expected_hash:
                failures.append(f"photo {identifier} hash binding mismatch: {path}")
        license_name = source.get("source_license", "")
        if license_name.startswith("CC BY") or license_name == "FAL":
            if not source.get("source_artist"):
                failures.append(f"photo {identifier} attribution creator missing")
            if not source.get("selected_source_page"):
                failures.append(f"photo {identifier} attribution source missing")
    family_ids = {family.get("id") for family in contract.get("asset_families", [])}
    for family in contract.get("asset_families", []):
        if family.get("public_distribution_decision") != "approved":
            failures.append(f"asset family {family.get('id')} is not public-approved")
        for field in ("provenance", "license_or_permission", "attribution_text", "derivative_obligations", "evidence_status"):
            if not family.get(field):
                failures.append(f"asset family {family.get('id')} missing {field}")
    if len(family_ids) != len(contract.get("asset_families", [])):
        failures.append("duplicate asset family id")
    return failures


def render_attribution(contract: dict) -> str:
    lines = [
        "# Public asset attribution",
        "",
        "Generated from `manifests/public_asset_rights.json` for the exact public candidate. This is an operational attribution and release-eligibility record, not legal advice.",
        "",
        "## Required map and data credits",
        "",
        "- © OpenStreetMap contributors · Protomaps. The local PMTiles archive is an ODbL Produced Work/data distribution; preserve the [Open Database License 1.0](https://opendatacommons.org/licenses/odbl/1-0/) notice and [OSM copyright/attribution](https://www.openstreetmap.org/copyright).",
        "- Map services and data available from U.S. Geological Survey, National Geospatial Program.",
        "",
        "## Photo sources",
        "",
        "Every photo below is shipped only as local thumb/medium derivatives. `CC BY` and `CC BY-SA` rows retain creator, source and license links; `CC BY-SA`/FAL rows are not silently relicensed.",
        "",
        "| Place / role | Creator | Source and license | Shipped derivatives |",
        "| --- | --- | --- | --- |",
    ]
    for item in sorted(contract.get("photo_assets", []), key=lambda row: row["id"]):
        source = f'[{item["source_title"]}]({item["source_page"]}) — {item["license_or_permission"]} ([license/source terms]({item["license_url"]}))'
        derivatives = ", ".join(f'`{path}`' for path in item["public_paths"])
        lines.append(f'| `{item["id"]}` | {item["creator_or_owner"]} | {source}<br>{item["derivative_obligations"]} | {derivatives} |')
    lines.extend([
        "",
        "## Distribution boundary",
        "",
        "The public tree contains the derivatives listed above. Private originals, offline basemap caches, and unshipped contour source images remain outside the public artifact. See `THIRD_PARTY_NOTICES.md` for software, font, sprite, map-data and relief-source notices.",
        "",
    ])
    return "\n".join(lines)


def render_third_party_notices(contract: dict) -> str:
    lines = [
        "# Third-party notices",
        "",
        "Generated deterministically from `manifests/public_asset_rights.json`. Preserve these notices with any redistribution of the candidate.",
        "",
    ]
    families = [family for family in contract.get("asset_families", []) if family.get("asset_class") != "photo-derivative"]
    for family in sorted(families, key=lambda row: row["id"]):
        license_urls = family.get("license_url", [])
        if isinstance(license_urls, str):
            license_urls = [license_urls] if license_urls else []
        license_text = " ".join(f"[license/source terms]({url})" for url in license_urls)
        lines.extend([
            f'## {family["id"]}',
            "",
            f'- Asset class: `{family["asset_class"]}`.',
            f'- Shipped/local paths: {", ".join(f"`{path}`" for path in family.get("paths", []))}.',
            f'- Provenance/source: {family["provenance"]}.',
            f'- Creator/owner: {family.get("creator_or_owner", "recorded in contract")}.',
            f'- License/permission basis: {family["license_or_permission"]}.' + (f' {license_text}.' if license_text else ""),
            f'- Attribution: {family["attribution_text"]}',
            f'- Derivative/share-alike obligations: {family["derivative_obligations"]}',
            f'- Evidence status: `{family["evidence_status"]}`; public distribution decision: `{family["public_distribution_decision"]}`.',
            "",
        ])
    return "\n".join(lines)


def notice_paths(mode: str) -> tuple[str, str, str]:
    if mode == "pages":
        return "ATTRIBUTION.md", "THIRD_PARTY_NOTICES.md", ".public-asset-rights.json"
    if mode == "public-package":
        return "artifacts/public/ATTRIBUTION.md", "artifacts/public/THIRD_PARTY_NOTICES.md", "artifacts/public/.public-asset-rights.json"
    raise ValueError(f"unsupported public distribution mode: {mode}")


def write_notices(tree: Path, contract: dict, manifest: dict, mode: str) -> None:
    attribution, third_party, embedded = notice_paths(mode)
    (tree / attribution).write_text(render_attribution(contract))
    (tree / third_party).write_text(render_third_party_notices(contract))
    embedded_path = tree / embedded
    embedded_path.parent.mkdir(parents=True, exist_ok=True)
    embedded_path.write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n")


def audit_tree(tree: Path, contract: dict | None = None, manifest: dict | None = None, mode: str = "pages", require_provenance: bool = True) -> dict:
    contract = contract or load_contract()
    manifest = manifest or load_json(PHOTO_MANIFEST)
    failures = validate_contract(contract, manifest)
    if not tree.is_dir():
        failures.append(f"candidate tree missing: {tree}")
        return {"status": "FAIL", "mode": mode, "tree": str(tree), "failures": failures}
    files = []
    for path in sorted(tree.rglob("*")):
        relative = path.relative_to(tree).as_posix()
        if path.is_symlink():
            failures.append(f"symlink is not a registered public asset: {relative}")
        elif path.is_file():
            files.append((relative, path))
    required = list(contract.get("required_paths", {}).get(mode, []))
    if mode == "pages" and not require_provenance:
        required = [path for path in required if path != ".release-provenance.json"]
    for required_path in required:
        if not (tree / required_path).is_file():
            failures.append(f"required public asset/notice missing: {required_path}")
    for relative, path in files:
        if any(fnmatch.fnmatchcase(relative, pattern) for pattern in contract.get("private_only_paths", [])):
            failures.append(f"private-only asset leaked into {mode}: {relative}")
        rules = _rules_for(contract, relative, mode)
        if not rules:
            failures.append(f"unregistered shipped file: {relative}")
        elif len(rules) != 1:
            failures.append(f"ambiguous rights registration for {relative}: {[rule['id'] for rule in rules]}")
        else:
            if rules[0].get("decision") != "approved":
                failures.append(f"registered but not approved for {mode}: {relative}")
    embedded_path = tree / notice_paths(mode)[2]
    if embedded_path.is_file():
        try:
            embedded = load_json(embedded_path)
            if embedded != contract:
                failures.append("embedded rights manifest is stale or does not match the candidate contract")
        except Exception as exc:
            failures.append(f"embedded rights manifest is invalid: {exc}")
    expected_attribution = render_attribution(contract)
    expected_third_party = render_third_party_notices(contract)
    attribution_path = tree / notice_paths(mode)[0]
    third_party_path = tree / notice_paths(mode)[1]
    if attribution_path.is_file() and attribution_path.read_text() != expected_attribution:
        failures.append("generated attribution is stale or nondeterministic")
    if third_party_path.is_file() and third_party_path.read_text() != expected_third_party:
        failures.append("generated third-party notices are stale or nondeterministic")
    for binding in contract.get("hash_bindings", []):
        if mode not in binding.get("modes", []):
            continue
        path = tree / binding["path"]
        if not path.is_file():
            failures.append(f"hash-bound public asset missing: {binding['path']}")
        elif digest(path) != binding["sha256"]:
            failures.append(f"hash-bound public asset mismatch: {binding['path']}")
    if mode == "pages":
        remote_photo = re.compile(r"https?://[^\"' )>]+\.(?:jpe?g|png|webp)(?:\?[^\"' )>]*)?", re.IGNORECASE)
        for relative, path in files:
            if relative not in {"index.html", "src/app_phase7.js", "src/map_first.css"}:
                continue
            if remote_photo.search(path.read_text(errors="ignore")):
                failures.append(f"remote photo dependency in public tree: {relative}")
    counts: dict[str, int] = {}
    for relative, _ in files:
        rules = _rules_for(contract, relative, mode)
        if rules:
            asset_class = rules[0].get("asset_class", "unclassified")
            counts[asset_class] = counts.get(asset_class, 0) + 1
    return {"status": "PASS" if not failures else "FAIL", "mode": mode, "tree": str(tree), "file_count": len(files), "approved_file_counts_by_class": dict(sorted(counts.items())), "failures": failures}


def audit_and_report(tree: Path, mode: str, report: Path | None = None, require_provenance: bool = True) -> dict:
    result = audit_tree(tree, mode=mode, require_provenance=require_provenance)
    if report:
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result
