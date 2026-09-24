"""Download selected real photographs and build local photo derivatives/manifest."""
from __future__ import annotations

import hashlib
import io
import json
import argparse
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parents[1]
API = "https://commons.wikimedia.org/w/api.php"
ROLES = ["HERO", "EXPERIENCE", "SCALE_CONTEXT"]
HEADERS = {"User-Agent": "SFTripPersonalPhotoAcquisition/1.0 (local personal trip map; contact: codex@openai.com)"}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch(url: str) -> tuple[bytes, str]:
    session = requests.Session()
    session.headers.update(HEADERS)
    for attempt in range(6):
        try:
            response = session.get(url, timeout=60)
            if response.status_code in (429, 500, 502, 503, 504):
                time.sleep(1.5 * 2 ** attempt)
                continue
            response.raise_for_status()
            return response.content, response.headers.get("Content-Type", "")
        except (requests.Timeout, requests.ConnectionError):
            time.sleep(1.5 * 2 ** attempt)
    raise RuntimeError(f"Unable to download {url}")


def scaled_commons_urls(titles: list[str]) -> dict[str, str]:
    urls = {}
    session = requests.Session()
    session.headers.update(HEADERS)
    for start in range(0, len(titles), 40):
        params = {
            "action": "query", "format": "json", "titles": "|".join(titles[start:start + 40]),
            "prop": "imageinfo", "iiprop": "url|size", "iiurlwidth": 1600,
        }
        for attempt in range(6):
            response = session.get(API, params=params, timeout=45)
            if response.status_code in (429, 500, 502, 503, 504):
                time.sleep(2 ** attempt)
                continue
            response.raise_for_status()
            break
        else:
            raise RuntimeError("Commons scaled image lookup failed")
        for page in response.json().get("query", {}).get("pages", {}).values():
            info = (page.get("imageinfo") or [None])[0]
            if info:
                urls[page["title"]] = info.get("thumburl") or info["url"]
    return urls


def dhash(image: Image.Image) -> str:
    gray = image.convert("L").resize((9, 8))
    bits = 0
    for y in range(8):
        for x in range(8):
            bits = (bits << 1) | (gray.getpixel((x, y)) > gray.getpixel((x + 1, y)))
    return f"{bits:016x}"


def save_jpeg(image: Image.Image, path: Path) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=90, optimize=True, progressive=True)
    data = buffer.getvalue()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data


def save_webp(image: Image.Image, path: Path, quality: int) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, "WEBP", quality=quality, method=6)
    data = buffer.getvalue()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data


def localize(entry: dict, candidate: dict, download_url: str, index: int) -> dict:
    raw, source_mime = fetch(download_url)
    image = Image.open(io.BytesIO(raw))
    image.load()
    image = ImageOps.exif_transpose(image).convert("RGB")
    if image.width < 600 or image.height < 300:
        raise ValueError(f"Too small for {entry['place_key']} {entry['role']}: {image.size}")
    original_path = ROOT / entry["local_original_path"]
    thumb_path = ROOT / entry["local_thumb_path"]
    medium_path = ROOT / entry["local_medium_path"]
    original = save_jpeg(image, original_path)
    thumb = save_webp(ImageOps.fit(image, (128, 128), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5)), thumb_path, 86)
    medium_image = ImageOps.contain(image, (1200, 900), method=Image.Resampling.LANCZOS)
    medium = save_webp(medium_image, medium_path, 88)
    entry.update({
        "selected_source_page": candidate["page_url"],
        "selected_source_title": candidate["title"],
        "source_image_url": candidate["source_url"],
        "download_url": download_url,
        "source_mime": source_mime,
        "source_sha256": sha256(raw),
        "selection_status": "VISUALLY_REVIEWED_REAL_PHOTO",
        "selection_contact_sheet": f"QA/photo_candidates/sheets/{entry['place_key']}.jpg",
        "selection_contact_index": index,
        "localization_status": "LOCALIZED_AND_DECODED",
        "sha256": sha256(original),
        "thumb_sha256": sha256(thumb),
        "medium_sha256": sha256(medium),
        "width": image.width,
        "height": image.height,
        "thumb_width": 128,
        "thumb_height": 128,
        "medium_width": medium_image.width,
        "medium_height": medium_image.height,
        "mime": "image/jpeg",
        "thumb_mime": "image/webp",
        "medium_mime": "image/webp",
        "perceptual_dhash": dhash(image),
        "source_license": candidate.get("license"),
        "source_artist": candidate.get("artist"),
        "subject_review": "Place and role visually checked against candidate contact sheet and source title/page.",
    })
    return entry


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", nargs="*", help="localize these reviewed places without rewriting other assets")
    args = parser.parse_args()
    selection = json.loads((ROOT / "manifests" / "photo_selection.json").read_text())["choices"]
    candidates = json.loads((ROOT / "QA" / "photo_candidates" / "candidates.json").read_text())
    manifest_path = ROOT / "manifests" / "asset_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    entries = {(x["place_key"], x["role"]): x for x in manifest["assets"]}
    jobs = []
    selected_places = args.only or list(selection)
    for place in selected_places:
        indexes = selection.get(place)
        if not indexes:
            raise ValueError(f"No reviewed three-photo selection for {place}")
        if len(indexes) != 3 or len(set(indexes)) != 3:
            raise ValueError(f"Selection must contain three distinct photos: {place}")
        for role, index in zip(ROLES, indexes):
            jobs.append((entries[(place, role)], candidates[place][index], index))
    expected = manifest["required_assets"]
    if args.only and len(jobs) != len(args.only) * len(ROLES):
        raise ValueError(f"Expected three reviewed assets per selected place, got {len(jobs)}")
    if not args.only and len(jobs) != expected:
        raise ValueError(f"Expected {expected} jobs, got {len(jobs)}")
    titles = [candidate["title"] for _, candidate, _ in jobs if candidate["title"].startswith("File:")]
    commons_urls = scaled_commons_urls(titles)
    results = []
    errors = []
    with ThreadPoolExecutor(max_workers=5) as pool:
        pending = {}
        for entry, candidate, index in jobs:
            download_url = commons_urls.get(candidate["title"], candidate["source_url"])
            future = pool.submit(localize, entry, candidate, download_url, index)
            pending[future] = (entry["place_key"], entry["role"])
        for future in as_completed(pending):
            place, role = pending[future]
            try:
                results.append(future.result())
                print("localized", place, role, flush=True)
            except Exception as exc:
                errors.append(f"{place} {role}: {exc}")
                print("FAILED", errors[-1], flush=True)
    localized = [item for item in manifest["assets"] if item.get("localization_status") == "LOCALIZED_AND_DECODED"]
    manifest["localized_originals"] = len(localized)
    manifest["localized_thumbnails"] = len(localized)
    manifest["localized_medium"] = len(localized)
    manifest["decodable_originals"] = len(localized)
    manifest["deduped_assets"] = len({x["sha256"] for x in localized})
    manifest["status"] = f"LOCALIZED_{len(localized)}_PENDING_INTEGRITY_CHECK" if not errors else "LOCALIZATION_INCOMPLETE"
    manifest["blocking_condition"] = None if not errors else errors
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(json.dumps({"localized": len(results), "unique_hashes": manifest["deduped_assets"], "errors": errors}, ensure_ascii=False), flush=True)
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
