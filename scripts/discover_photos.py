"""Collect inspectable real-photo candidates from Wikimedia Commons.

This is an acquisition aid, not an automatic photo selector. Human review of the
contact sheets is required before anything is promoted into asset_manifest.json.
"""
from __future__ import annotations

import json
import argparse
import re
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "QA" / "photo_candidates"
API = "https://commons.wikimedia.org/w/api.php"
QUERIES = {
    "ferry": "Ferry Building Farmers Market San Francisco",
    "exploratorium": "Exploratorium Pier 15 San Francisco",
    "bay_lights": "The Bay Lights Bay Bridge San Francisco",
    "ggb": "Golden Gate Bridge south San Francisco",
    "muir": "Muir Woods National Monument trail",
    "battery": "Battery Spencer Golden Gate Bridge",
    "palace": "Palace of Fine Arts San Francisco",
    "crissy": "Crissy Field San Francisco beach",
    "alcatraz": "Alcatraz island cellhouse",
    "north_beach": "North Beach Washington Square San Francisco",
    "fortune": "Golden Gate Fortune Cookie Factory San Francisco",
    "coit": "Coit Tower San Francisco murals",
    "lombard": "Lombard Street crooked block San Francisco",
    "musee": "Musee Mecanique San Francisco",
    "point_lobos": "Point Lobos State Natural Reserve California",
    "lone_cypress": "Lone Cypress Pebble Beach 17 Mile Drive",
    "aquarium": "Monterey Bay Aquarium kelp forest",
    "cooks": "Cooks Meadow Yosemite Valley",
    "tunnel_view": "Tunnel View Yosemite Valley",
    "valley_view": "Valley View Yosemite",
    "washburn": "Washburn Point Yosemite",
    "glacier": "Glacier Point Yosemite",
    "mariposa": "Mariposa Grove giant sequoias Yosemite",
    "painted": "Painted Ladies Alamo Square San Francisco",
    "twin_peaks": "Twin Peaks San Francisco overlook",
    "botanical": "San Francisco Botanical Garden",
    "academy": "California Academy of Sciences San Francisco",
    "lands_end": "Lands End Coastal Trail San Francisco",
    "pier39": 'intitle:"Pier 39" sea lions',
    "tunnel_tops": 'intitle:"Presidio Tunnel Tops"',
    "bixby": 'incategory:"Bixby Creek Bridge"',
    "ghirardelli": 'incategory:"Ghirardelli Square"',
    "cable_car": 'incategory:"Cable cars in San Francisco"',
    "carmel": 'incategory:"Carmel-by-the-Sea, California"',
    "el_capitan": 'intitle:"El Capitan Meadow"',
    "monterey_wharf": 'intitle:"Fisherman’s Wharf" Monterey OR intitle:"Fisherman\'s Wharf" Monterey',
}
EXTRA_QUERIES = {
    "exploratorium": ["Exploratorium exhibit visitors San Francisco", "Exploratorium indoor exhibits Pier 15"],
    "coit": ["Coit Tower exterior San Francisco"],
    "cooks": ["Cook's Meadow Yosemite Falls boardwalk", "Cook's Meadow Yosemite Valley"],
    "valley_view": ["Valley View Yosemite Merced River El Capitan"],
    "botanical": ["San Francisco Botanical Garden Golden Gate Park garden", "San Francisco Botanical Garden pond flowers", "Strybing Arboretum San Francisco"],
    "fortune": ["Golden Gate Fortune Cookie Company Chinatown Ross Alley"],
    "pier39": ['intitle:"Pier 39" K Dock', 'intitle:"Pier 39" sea lion viewing'],
    "tunnel_tops": ['intitle:"Outpost" playground Presidio', '"Tunnel Tops" San Francisco'],
    "bixby": ['intitle:"Bixby Creek Bridge" coast', 'intitle:"Bixby Bridge" California'],
    "ghirardelli": ['intitle:"Ghirardelli Square" sign', 'intitle:"Ghirardelli Square" plaza'],
    "cable_car": ['intitle:"Powell Hyde" cable car', 'intitle:"San Francisco cable car" passengers'],
    "carmel": ['intitle:"Carmel Beach" California', 'intitle:"Ocean Avenue" Carmel'],
    "el_capitan": ['intitle:"El Capitan Meadow" climbers', 'El Capitan Yosemite Valley meadow'],
    "monterey_wharf": ['intitle:"Fisherman\'s Wharf" Monterey', 'intitle:"Old Fisherman\'s Wharf" Monterey'],
}


def request(session: requests.Session, params: dict) -> dict:
    for attempt in range(5):
        response = session.get(API, params=params, timeout=30)
        if response.status_code in (429, 500, 502, 503, 504):
            time.sleep(2 ** attempt)
            continue
        response.raise_for_status()
        return response.json()
    raise RuntimeError(f"Commons API failed: {params}")


def image_pages(session: requests.Session, titles: list[str] | None = None, search: str | None = None) -> list[dict]:
    params = {
        "action": "query",
        "format": "json",
        "prop": "imageinfo",
        "iiprop": "url|size|extmetadata",
        "iiurlwidth": 640,
    }
    if titles:
        params["titles"] = "|".join(titles)
    else:
        params.update(generator="search", gsrsearch=search, gsrnamespace=6, gsrlimit=15)
    data = request(session, params)
    return sorted(data.get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 999))


def clean_text(s: str) -> str:
    return re.sub(r"<[^>]+>", " ", s).replace("&amp;", "&").strip()


def candidate(page: dict) -> dict | None:
    info = (page.get("imageinfo") or [None])[0]
    if not info or info.get("width", 0) < 650 or info.get("height", 0) < 450:
        return None
    title = page.get("title", "")
    if not re.search(r"\.(jpe?g|png|webp)$", title, re.I):
        return None
    meta = info.get("extmetadata", {})
    return {
        "title": title,
        "page_url": info.get("descriptionurl"),
        "source_url": info.get("url"),
        "preview_url": info.get("thumburl") or info.get("url"),
        "width": info.get("width"),
        "height": info.get("height"),
        "description": clean_text(meta.get("ImageDescription", {}).get("value", ""))[:500],
        "categories": meta.get("Categories", {}).get("value", "")[:350],
        "artist": clean_text(meta.get("Artist", {}).get("value", ""))[:200],
        "license": meta.get("LicenseShortName", {}).get("value", ""),
    }


def download_preview(session: requests.Session, url: str, target: Path) -> bool:
    if target.exists():
        return True
    try:
        response = session.get(url, timeout=35)
        response.raise_for_status()
        target.write_bytes(response.content)
        with Image.open(target) as im:
            im.verify()
        return True
    except Exception:
        target.unlink(missing_ok=True)
        return False


def sheet(place: str, items: list[dict]) -> None:
    tile_w, tile_h, cols = 320, 245, 4
    rows = max(1, (len(items) + cols - 1) // cols)
    canvas = Image.new("RGB", (cols * tile_w, rows * tile_h), "#f5f5f5")
    draw = ImageDraw.Draw(canvas)
    for idx, item in enumerate(items):
        x, y = idx % cols * tile_w, idx // cols * tile_h
        path = OUT / "previews" / place / f"{idx:02d}.jpg"
        if path.exists():
            with Image.open(path) as im:
                thumb = ImageOps.contain(im.convert("RGB"), (tile_w - 12, 185))
                canvas.paste(thumb, (x + (tile_w - thumb.width) // 2, y + 2))
        label = f"{idx:02d} {item['title'][5:49]}"
        draw.text((x + 5, y + 188), label, fill="#111111")
        draw.text((x + 5, y + 210), f"{item['width']}x{item['height']} {item['license']}", fill="#555555")
    canvas.save(OUT / "sheets" / f"{place}.jpg", quality=88)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", nargs="*", choices=QUERIES)
    parser.add_argument("--extra", action="store_true")
    args = parser.parse_args()
    manifest = json.loads((ROOT / "manifests" / "asset_manifest.json").read_text())
    selected = {}
    for asset in manifest["assets"]:
        url = asset.get("selected_source_page") or ""
        if "/wiki/File:" in url:
            title = "File:" + unquote(url.split("/wiki/File:", 1)[1]).replace("_", " ")
            selected.setdefault(asset["place_key"], []).append(title)
    (OUT / "previews").mkdir(parents=True, exist_ok=True)
    (OUT / "sheets").mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update({"User-Agent": "SFTripPersonalPhotoAcquisition/1.0 (local personal trip map; contact: codex@openai.com)"})
    candidate_path = OUT / "candidates.json"
    all_candidates = json.loads(candidate_path.read_text()) if candidate_path.exists() else {}
    for place in args.only or QUERIES:
        items = all_candidates.get(place, []) if args.extra else []
        pages = []
        if args.extra:
            for query in EXTRA_QUERIES.get(place, []):
                pages += image_pages(session, search=query)
        else:
            pages = image_pages(session, titles=selected.get(place)) if selected.get(place) else []
            pages += image_pages(session, search=QUERIES[place])
        seen = {item["source_url"] for item in items}
        for page in pages:
            item = candidate(page)
            if item and item["source_url"] not in seen:
                seen.add(item["source_url"])
                items.append(item)
        place_dir = OUT / "previews" / place
        place_dir.mkdir(exist_ok=True)
        for idx, item in enumerate(items):
            path = place_dir / f"{idx:02d}.jpg"
            item["preview_local"] = str(path.relative_to(ROOT)) if download_preview(session, item["preview_url"], path) else None
        all_candidates[place] = items
        sheet(place, items)
        print(place, len(items), sum(bool(x["preview_local"]) for x in items), flush=True)
        candidate_path.write_text(json.dumps(all_candidates, ensure_ascii=False, indent=2))
        time.sleep(0.2)


if __name__ == "__main__":
    main()
