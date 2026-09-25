"""Verify all local photo originals and derivatives, hashes, roles, and duplicates."""
from __future__ import annotations

import argparse
import hashlib
import json
from itertools import combinations
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "manifests" / "asset_manifest.json"
ROLES = {"HERO", "EXPERIENCE", "SCALE_CONTEXT"}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inspect(path: Path) -> dict:
    with Image.open(path) as image:
        image.load()
        return {"width": image.width, "height": image.height, "format": image.format}


def main(runtime_only: bool = False) -> None:
    manifest = json.loads(MANIFEST.read_text())
    assets = manifest["assets"]
    required_assets = manifest["required_assets"]
    required_places = manifest["required_places"]
    failures = []
    confirmed = []
    original_unavailable = 0
    present_decodable = {"original": 0, "thumb": 0, "medium": 0}
    per_place = {}
    for item in assets:
        place, role = item["place_key"], item["role"]
        per_place.setdefault(place, set()).add(role)
        for variant, path_key, hash_key in [
            ("original", "local_original_path", "sha256"),
            ("thumb", "local_thumb_path", "thumb_sha256"),
            ("medium", "local_medium_path", "medium_sha256"),
        ]:
            path = ROOT / item[path_key]
            if variant == "original" and runtime_only and not path.is_file():
                original_unavailable += 1
                continue
            if not path.is_file():
                failures.append(f"missing {place} {role} {variant}: {path}")
                continue
            try:
                dimensions = inspect(path)
            except Exception as exc:
                failures.append(f"undecodable {place} {role} {variant}: {exc}")
                continue
            present_decodable[variant] += 1
            if digest(path) != item.get(hash_key):
                failures.append(f"hash mismatch {place} {role} {variant}")
            if variant == "original" and (dimensions["width"] != item.get("width") or dimensions["height"] != item.get("height")):
                failures.append(f"dimension mismatch {place} {role}")
            if variant == "thumb" and (dimensions["width"], dimensions["height"]) != (128, 128):
                failures.append(f"wrong thumbnail dimensions {place} {role}")
        if item.get("selection_status") != "VISUALLY_REVIEWED_REAL_PHOTO" or not item.get("selected_source_page") or not item.get("source_image_url"):
            failures.append(f"missing provenance/review {place} {role}")
        confirmed.append(item)
    if len(assets) != required_assets or len(per_place) != required_places:
        failures.append(f"wrong asset/place count {len(assets)}/{len(per_place)}")
    for place, roles in per_place.items():
        if roles != ROLES:
            failures.append(f"wrong roles for {place}: {sorted(roles)}")
    hashes = [x.get("sha256") for x in confirmed]
    if len(set(hashes)) != len(hashes):
        failures.append("exact duplicate original hashes")
    near = []
    for left, right in combinations(assets, 2):
        a, b = int(left["perceptual_dhash"], 16), int(right["perceptual_dhash"], 16)
        distance = (a ^ b).bit_count()
        if distance <= 5:
            near.append({"left": left["place_key"] + "/" + left["role"], "right": right["place_key"] + "/" + right["role"], "distance": distance})
    report = {
        "required": required_assets,
        "present_decodable_originals": present_decodable["original"],
        "present_decodable_thumbnails": present_decodable["thumb"],
        "present_decodable_medium": present_decodable["medium"],
        "places_with_exact_roles": sum(roles == ROLES for roles in per_place.values()),
        "unique_original_hashes": len(set(hashes)),
        "near_duplicate_review_queue": near,
        "runtime_only": runtime_only,
        "originals_unavailable_locally": original_unavailable,
        "original_verification": "separate source/rights gate; manifest provenance retained" if runtime_only else "local bytes decoded and hash checked",
        "failures": failures,
        "status": "PASS" if not failures else "FAIL",
    }
    out = ROOT / "QA" / "CHG-232" / "photo_integrity.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    if not runtime_only:
        manifest.update({
            "localized_originals": report["present_decodable_originals"],
            "localized_thumbnails": report["present_decodable_thumbnails"],
            "localized_medium": report["present_decodable_medium"],
            "decodable_originals": report["present_decodable_originals"],
            "deduped_assets": report["unique_original_hashes"],
            "status": f"COMPLETE_{required_assets}_LOCAL_REAL_PHOTOS" if not failures else "INTEGRITY_FAILED",
            "blocking_condition": None if not failures else failures,
        })
        MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-only", action="store_true", help="validate tracked runtime derivatives while preserving the separate original-photo source/rights gate")
    main(parser.parse_args().runtime_only)
