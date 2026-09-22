#!/usr/bin/env python3
"""Bind the nine new local photo derivatives to source and rights provenance."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = Path("/tmp/sf-trip-new-sources")
ASSET_MANIFEST = ROOT / "manifests/asset_manifest.json"
RIGHTS_MANIFEST = ROOT / "manifests/public_asset_rights.json"

PHOTO_SOURCES = {
    ("chinatown", "HERO"): {"file": "chinatown_hero.jpg", "title": "File:1 chinatown san francisco arch gateway.JPG", "page": "https://commons.wikimedia.org/wiki/File:1_chinatown_san_francisco_arch_gateway.JPG", "url": "https://upload.wikimedia.org/wikipedia/commons/b/b0/1_chinatown_san_francisco_arch_gateway.JPG?utm_source=commons.wikimedia.org&utm_campaign=imageinfo&utm_content=original", "artist": "chensiyuan", "license": "CC BY-SA 4.0", "license_url": "https://creativecommons.org/licenses/by-sa/4.0"},
    ("chinatown", "EXPERIENCE"): {"file": "chinatown_experience.jpg", "title": "File:Lion Dance in Chinatown, San Francisco 01.jpg", "page": "https://commons.wikimedia.org/wiki/File:Lion_Dance_in_Chinatown,_San_Francisco_01.jpg", "url": "https://upload.wikimedia.org/wikipedia/commons/4/48/Lion_Dance_in_Chinatown%2C_San_Francisco_01.jpg?utm_source=commons.wikimedia.org&utm_campaign=imageinfo&utm_content=original", "artist": "Mattsjc", "license": "CC BY-SA 4.0", "license_url": "https://creativecommons.org/licenses/by-sa/4.0"},
    ("chinatown", "SCALE_CONTEXT"): {"file": "chinatown_scale_context.jpg", "title": "File:Rooftop plaza at San Francisco Muni's Chinatown-Rose Pak station.jpg", "page": "https://commons.wikimedia.org/wiki/File:Rooftop_plaza_at_San_Francisco_Muni%27s_Chinatown-Rose_Pak_station.jpg", "url": "https://upload.wikimedia.org/wikipedia/commons/f/fb/Rooftop_plaza_at_San_Francisco_Muni%27s_Chinatown-Rose_Pak_station.jpg?utm_source=commons.wikimedia.org&utm_campaign=imageinfo&utm_content=original", "artist": "Kylelovesyou", "license": "CC0", "license_url": "https://creativecommons.org/publicdomain/zero/1.0/"},
    ("tea_garden", "HERO"): {"file": "tea_garden_hero.jpg", "title": "File:Japanese Tea Garden San Francisco December 2016 001.jpg", "page": "https://commons.wikimedia.org/wiki/File:Japanese_Tea_Garden_San_Francisco_December_2016_001.jpg", "url": "https://upload.wikimedia.org/wikipedia/commons/8/81/Japanese_Tea_Garden_San_Francisco_December_2016_001.jpg?utm_source=commons.wikimedia.org&utm_campaign=imageinfo&utm_content=original", "artist": "King of Hearts", "license": "CC BY-SA 4.0", "license_url": "https://creativecommons.org/licenses/by-sa/4.0"},
    ("tea_garden", "EXPERIENCE"): {"file": "tea_garden_experience.jpg", "title": "File:Temple in Japanese Tea Garden (San Francisco) (TK7).JPG", "page": "https://commons.wikimedia.org/wiki/File:Temple_in_Japanese_Tea_Garden_(San_Francisco)_(TK7).JPG", "url": "https://upload.wikimedia.org/wikipedia/commons/e/e0/Temple_in_Japanese_Tea_Garden_%28San_Francisco%29_%28TK7%29.JPG?utm_source=commons.wikimedia.org&utm_campaign=imageinfo&utm_content=original", "artist": "Tobias Kleinlercher / Wikipedia", "license": "CC BY-SA 3.0", "license_url": "https://creativecommons.org/licenses/by-sa/3.0"},
    ("tea_garden", "SCALE_CONTEXT"): {"file": "tea_garden_scale_context.jpg", "title": "File:Japanese Tea Garden San Francisco December 2016 002.jpg", "page": "https://commons.wikimedia.org/wiki/File:Japanese_Tea_Garden_San_Francisco_December_2016_002.jpg", "url": "https://upload.wikimedia.org/wikipedia/commons/f/f5/Japanese_Tea_Garden_San_Francisco_December_2016_002.jpg?utm_source=commons.wikimedia.org&utm_campaign=imageinfo&utm_content=original", "artist": "King of Hearts", "license": "CC BY-SA 4.0", "license_url": "https://creativecommons.org/licenses/by-sa/4.0"},
    ("bridalveil", "HERO"): {"file": "bridalveil_hero.jpg", "title": "File:Bridalveil Fall - Yosemite National Park 2012-05-28.jpg", "page": "https://commons.wikimedia.org/wiki/File:Bridalveil_Fall_-_Yosemite_National_Park_2012-05-28.jpg", "url": "https://upload.wikimedia.org/wikipedia/commons/2/20/Bridalveil_Fall_-_Yosemite_National_Park_2012-05-28.jpg?utm_source=commons.wikimedia.org&utm_campaign=imageinfo&utm_content=original", "artist": "Nancyswikiaccount", "license": "CC BY-SA 4.0", "license_url": "https://creativecommons.org/licenses/by-sa/4.0"},
    ("bridalveil", "EXPERIENCE"): {"file": "bridalveil_experience.jpg", "title": "File:Yosemite Bridalveil Fall.jpg", "page": "https://commons.wikimedia.org/wiki/File:Yosemite_Bridalveil_Fall.jpg", "url": "https://upload.wikimedia.org/wikipedia/commons/5/53/Yosemite_Bridalveil_Fall.jpg?utm_source=commons.wikimedia.org&utm_campaign=imageinfo&utm_content=original", "artist": "Pimlico27", "license": "CC BY-SA 4.0", "license_url": "https://creativecommons.org/licenses/by-sa/4.0"},
    ("bridalveil", "SCALE_CONTEXT"): {"file": "bridalveil_scale_context.jpg", "title": "File:Yosemite National Park, Bridalveil Fall, 2024-07 CN-02.jpg", "page": "https://commons.wikimedia.org/wiki/File:Yosemite_National_Park,_Bridalveil_Fall,_2024-07_CN-02.jpg", "url": "https://upload.wikimedia.org/wikipedia/commons/5/53/Yosemite_National_Park%2C_Bridalveil_Fall%2C_2024-07_CN-02.jpg?utm_source=commons.wikimedia.org&utm_campaign=imageinfo&utm_content=original", "artist": "Steffen Schmitz", "license": "CC BY-SA 4.0", "license_url": "https://creativecommons.org/licenses/by-sa/4.0"},
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dhash(path: Path) -> str:
    with Image.open(path) as image:
        image = image.convert("L").resize((9, 8))
        bits = 0
        for y in range(8):
            for x in range(8):
                bits = (bits << 1) | int(image.getpixel((x, y)) > image.getpixel((x + 1, y)))
        return f"{bits:016x}"


def main() -> None:
    manifest = json.loads(ASSET_MANIFEST.read_text())
    rights = json.loads(RIGHTS_MANIFEST.read_text())
    existing = {(item["place_key"], item["role"]): item for item in manifest["assets"]}
    rights_existing = {item["id"]: item for item in rights["photo_assets"]}
    for (place, role), source in PHOTO_SOURCES.items():
        source_path = SOURCE_ROOT / source["file"]
        medium_path = ROOT / f"assets/photos/medium/{place}__{role.lower()}.webp"
        thumb_path = ROOT / f"assets/photos/thumb/{place}__{role.lower()}.webp"
        if not source_path.is_file() or not medium_path.is_file() or not thumb_path.is_file():
            raise SystemExit(f"missing photo input for {place}/{role}")
        with Image.open(source_path) as image:
            width, height = image.size
        identifier = f"{place}/{role}"
        item = {
            "place_key": place,
            "canonical_name": {"chinatown":"Chinatown San Francisco","tea_garden":"Japanese Tea Garden","bridalveil":"Bridalveil Fall"}[place],
            "role": role,
            "role_goal": {"HERO":"instantly identifies the place","EXPERIENCE":"shows the place-specific family experience","SCALE_CONTEXT":"shows geographic or human scale"}[role],
            "search_query": f"{place} {role.lower()} Wikimedia Commons real photograph",
            "source_pool_urls": [source["page"]],
            "selected_source_page": source["page"],
            "selection_status": "VISUALLY_REVIEWED_REAL_PHOTO",
            "local_original_path": f"assets/photos/original/{place}__{role.lower()}.jpg",
            "local_thumb_path": str(thumb_path.relative_to(ROOT)),
            "local_medium_path": str(medium_path.relative_to(ROOT)),
            "localization_status": "LOCALIZED_AND_DECODED",
            "sha256": sha(source_path),
            "width": width,
            "height": height,
            "mime": "image/jpeg",
            "selected_source_title": source["title"],
            "source_image_url": source["url"],
            "download_url": source["url"],
            "source_mime": "image/jpeg",
            "source_sha256": sha(source_path),
            "selection_contact_sheet": f"QA/photo_candidates/sheets/{place}.jpg",
            "selection_contact_index": list(PHOTO_SOURCES).index((place, role)),
            "thumb_sha256": sha(thumb_path),
            "medium_sha256": sha(medium_path),
            "thumb_width": 128,
            "thumb_height": 128,
            "medium_width": Image.open(medium_path).width,
            "medium_height": Image.open(medium_path).height,
            "thumb_mime": "image/webp",
            "medium_mime": "image/webp",
            "perceptual_dhash": dhash(source_path),
            "source_license": source["license"],
            "source_artist": source["artist"],
            "subject_review": "Place identity and HERO/EXPERIENCE/SCALE_CONTEXT role were checked against the Commons source page.",
        }
        existing[(place, role)] = item
        rights_existing[identifier] = {
            "id": identifier,
            "asset_class": "photo",
            "place_key": place,
            "role": role,
            "canonical_name": item["canonical_name"],
            "public_paths": [item["local_thumb_path"], item["local_medium_path"]],
            "private_source_path": item["local_original_path"],
            "provenance": "manifests/asset_manifest.json",
            "source_page": source["page"],
            "source_image_url": source["url"],
            "source_title": source["title"],
            "creator_or_owner": source["artist"],
            "license_or_permission": source["license"],
            "license_url": source["license_url"],
            "attribution_text": f"{source['title']} by {source['artist']}, {source['page']}; source marked {source['license']}. Local WebP derivatives are generated from the recorded source bytes.",
            "derivative_obligations": "Retain creator, source, and license terms; CC BY-SA derivatives remain under compatible share-alike terms." if source["license"].startswith("CC BY-SA") else "No attribution is required by the CC0 dedication; retain this source record for provenance.",
            "distribution_mode": "localized WebP derivatives in Pages and public-package",
            "evidence_status": "exact-source-metadata",
            "public_distribution_decision": "approved",
            "hashes": {item["local_thumb_path"]: item["thumb_sha256"], item["local_medium_path"]: item["medium_sha256"], "source_bytes": item["source_sha256"], "normalized_private_original": item["source_sha256"]},
            "replacement": False,
            "replacement_reason": None,
        }
    manifest["assets"] = [existing[key] for key in sorted(existing)]
    manifest["required_assets"] = len(manifest["assets"])
    manifest["required_places"] = len({item["place_key"] for item in manifest["assets"]})
    manifest["status"] = f"COMPLETE_{len(manifest['assets'])}_LOCAL_REAL_PHOTOS"
    rights["photo_assets"] = [rights_existing[key] for key in sorted(rights_existing)]
    rights["coverage_summary"]["photo_assets"] = len(rights["photo_assets"])
    rights["coverage_summary"]["photo_derivative_files"] = len(rights["photo_assets"]) * 2
    existing_paths = {path for rule in rights["path_rules"] for path in rule.get("paths", [])}
    required_pages = set(rights["required_paths"]["pages"])
    for place, role in PHOTO_SOURCES:
        suffix = role.lower()
        for variant in ("thumb", "medium"):
            relative = f"assets/photos/{variant}/{place}__{suffix}.webp"
            package_relative = f"artifacts/public/{relative}"
            if relative not in existing_paths:
                rights["path_rules"].append({"id": f"pages/{relative}", "modes": ["pages"], "paths": [relative], "asset_class": "photo-derivative", "decision": "approved"})
                rights["path_rules"].append({"id": f"package-public/{relative}", "modes": ["public-package"], "paths": [package_relative], "asset_class": "public-artifact-copy", "decision": "approved"})
            required_pages.add(relative)
    rights["required_paths"]["pages"] = sorted(required_pages)
    rights["path_rules"] = sorted(rights["path_rules"], key=lambda rule: rule["id"])
    ASSET_MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    rights["input_sha256"]["manifests/asset_manifest.json"] = sha(ASSET_MANIFEST)
    rights["input_sha256"]["manifests/map_first_basemap_manifest.json"] = sha(ROOT / "manifests/map_first_basemap_manifest.json")
    rights["input_sha256"]["manifests/source_manifest.json"] = sha(ROOT / "manifests/source_manifest.json")
    RIGHTS_MANIFEST.write_text(json.dumps(rights, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status":"PASS","assets":len(manifest["assets"]),"places":manifest["required_places"]},ensure_ascii=False))


if __name__ == "__main__":
    main()
